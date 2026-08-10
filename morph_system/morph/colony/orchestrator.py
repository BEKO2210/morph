from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from ..adapters import make_adapter
from ..ci.detector import detect_commands
from ..ci.runner import run_checks, pass_ratio
from ..config import MorphConfig
from ..core.fitness import FitnessInputs, compute
from ..core.graph import build_lightweight_graph, stress_field
from ..core.homeostasis import sense
from ..git.worktrees import WorktreeManager, Worktree
from ..memory.store import MemoryStore
from ..util import json_dump, run_cmd, slug
from .hypotheses import generate, Hypothesis
from .roles import builder, predator, guardian


@dataclass
class Candidate:
    hypothesis: Hypothesis
    worktree: Worktree
    builder_output: str
    tests: list
    predator: object
    guardian: object
    fitness: object
    changed_files: list[str]
    diff_lines: int
    patch: str
    generation: int = 0


def _repo_summary(repo: Path) -> str:
    top = run_cmd(["git", "ls-files"], cwd=repo).stdout.splitlines()[:180]
    return "Tracked files (sample):\n" + "\n".join(top)


def _candidate_metrics(wt: Worktree, changed: list[str], cfg: MorphConfig):
    h = sense(wt.path, wt.base)
    minimality = 1.0 - min(1.0, (h.diff_lines / max(1, cfg.max_diff_lines)) * 0.65 + (len(changed) / max(1, cfg.max_changed_files)) * 0.35)
    dep_stability = 1.0 - min(1.0, h.dependency_files_changed * 0.45)
    blast = 1.0 - min(1.0, h.public_surface_files_changed * 0.12 + len(changed) / 80.0)
    return h, minimality, dep_stability, blast


def _seed_stress(task: str, files: list[str]) -> list[str]:
    words = [w.lower() for w in task.replace("/", " ").replace("_", " ").split() if len(w) >= 4]
    ranked = []
    for f in files:
        score = sum(w in f.lower() for w in words)
        if score:
            ranked.append((score, f))
    ranked.sort(reverse=True)
    return [f for _, f in ranked[:8]]


def _evaluate(adapter, manager, wt, hyp, task, cfg, checks, stress, antibodies, generation, inherited=False) -> Candidate:
    instruction = hyp.theory
    if inherited:
        instruction = (
            "You inherited the current best candidate patch. Preserve its correct behavior, then pursue this mutation pressure: "
            + hyp.theory
        )
    out = builder(adapter, wt.path, task, instruction, list(stress.items()), antibodies)
    changed = manager.changed_files(wt)
    patch = manager.patch(wt)
    h, minimality, dep_stability, blast = _candidate_metrics(wt, changed, cfg)
    tests = run_checks(wt.path, checks, cfg.timeout_seconds)
    pred = predator(adapter, wt.path, wt.base, task)
    guard = guardian(adapter, wt.path, wt.base, task)
    task_signal = 1.0 if changed else 0.0
    fitness = compute(FitnessInputs(
        tests_ratio=pass_ratio(tests),
        predator_score=max(0.0, 1.0 - pred.severity),
        guardian_score=max(0.0, 1.0 - guard.severity),
        minimality=minimality,
        dependency_stability=dep_stability,
        blast_radius=blast,
        task_signal=task_signal,
    ), cfg.homeostasis)
    return Candidate(hyp, wt, out, tests, pred, guard, fitness, changed, h.diff_lines, patch, generation)


def _candidate_json(c: Candidate) -> dict:
    return {
        "generation": c.generation,
        "hypothesis": c.hypothesis.to_dict(),
        "changed_files": c.changed_files,
        "diff_lines": c.diff_lines,
        "builder_output": c.builder_output,
        "tests": [t.to_dict() for t in c.tests],
        "predator": c.predator.__dict__,
        "guardian": c.guardian.__dict__,
        "fitness": c.fitness.to_dict(),
    }


def run_once(repo: Path, task: str, adapter_name: str, cfg: MorphConfig, *, apply: bool, commit: bool, push: bool, keep_worktrees: bool = False) -> dict:
    repo = repo.resolve()
    if run_cmd(["git", "rev-parse", "--git-dir"], cwd=repo).returncode != 0:
        raise RuntimeError("MORPH must be run inside a Git repository.")
    base = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo, check=True).stdout.strip()
    start_status = run_cmd(["git", "status", "--porcelain"], cwd=repo).stdout
    def relevant_status(text: str) -> list[str]:
        dirty = []
        for line in text.splitlines():
            path = line[3:] if len(line) >= 4 else line
            # Rename records can look like "old -> new"; compare both ends.
            paths = [x.strip() for x in path.split(" -> ")]
            if all(any(x == ig.rstrip("/") or x.startswith(ig) for ig in cfg.ignore_paths) for x in paths):
                continue
            dirty.append(line)
        return dirty
    base_dirty = relevant_status(start_status)
    if (apply or commit or push) and cfg.require_clean_for_apply and base_dirty:
        raise RuntimeError("Base repository has non-MORPH local changes. Commit/stash them before --apply/--commit/--push. Dirty: " + "; ".join(base_dirty[:8]))
    if push and not commit:
        raise RuntimeError("--push requires --commit.")

    adapter = make_adapter(adapter_name, cfg, cfg.timeout_seconds)
    if not adapter.available():
        raise RuntimeError(f"Adapter {adapter.name} is not available in PATH.")

    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + slug(task, 16)
    run_dir = repo / ".morph" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    memory = MemoryStore(repo)
    manager = WorktreeManager(repo, run_id)

    baseline = sense(repo)
    tracked_files = run_cmd(["git", "ls-files"], cwd=repo).stdout.splitlines()
    graph = build_lightweight_graph(repo)
    seeds = _seed_stress(task, tracked_files)
    stress = stress_field(graph, seeds) if seeds else {}
    antibodies = memory.antibodies()
    hypotheses = generate(adapter, repo, task, _repo_summary(repo), max(1, cfg.clones))
    checks = cfg.test_commands or detect_commands(repo)
    all_checks = checks + [c for c in cfg.predator_commands if c not in checks]

    json_dump(run_dir / "sensing.json", {
        "base": base,
        "baseline": baseline.to_dict(),
        "stress_field": stress,
        "hypotheses": [h.to_dict() for h in hypotheses],
        "checks": all_checks,
        "adapter": adapter.name,
        "prior_trust": memory.trust(),
    })

    candidates: list[Candidate] = []
    try:
        # Generation 0: causal diversity.
        for i, hyp in enumerate(hypotheses):
            wt = manager.create(f"g0-clone-{i+1}-{hyp.name}", base)
            cand = _evaluate(adapter, manager, wt, hyp, task, cfg, all_checks, stress, antibodies, generation=0)
            candidates.append(cand)
            json_dump(run_dir / f"g0-candidate-{i+1}.json", _candidate_json(cand))
            (run_dir / f"g0-candidate-{i+1}.patch").write_text(cand.patch, encoding="utf-8")

        # Clonal evolution: current winner reproduces under distinct mutation pressures.
        mutation_pressures = [
            Hypothesis("minimalize", "Reduce the patch to the smallest root-cause change; remove incidental churn and preserve compatibility."),
            Hypothesis("harden", "Harden the inherited solution against edge cases, invalid state, concurrency, security and platform variance without broadening scope."),
            Hypothesis("simplify", "Improve structural clarity and maintainability while preserving behavior; prefer deleting accidental complexity over adding abstractions."),
            Hypothesis("performance", "Preserve correctness while removing avoidable hot-path cost, redundant I/O, repeated work or unnecessary allocations."),
        ]
        parent = max(candidates, key=lambda c: c.fitness.score)
        for generation in range(1, max(0, int(cfg.clone_evolution)) + 1):
            children: list[Candidate] = []
            for j, hyp in enumerate(mutation_pressures[: max(1, int(cfg.evolution_children))]):
                wt = manager.create(f"g{generation}-child-{j+1}-{hyp.name}", base)
                if parent.patch.strip():
                    patch_file = run_dir / f"g{generation}-parent.patch"
                    patch_file.write_text(parent.patch, encoding="utf-8")
                    r = run_cmd(["git", "apply", str(patch_file)], cwd=wt.path)
                    if r.returncode != 0:
                        continue
                cand = _evaluate(adapter, manager, wt, hyp, task, cfg, all_checks, stress, antibodies, generation=generation, inherited=True)
                children.append(cand)
                candidates.append(cand)
                json_dump(run_dir / f"g{generation}-candidate-{j+1}.json", _candidate_json(cand))
                (run_dir / f"g{generation}-candidate-{j+1}.patch").write_text(cand.patch, encoding="utf-8")
            if not children:
                break
            parent = max([parent, *children], key=lambda c: c.fitness.score)

        candidates.sort(key=lambda c: c.fitness.score, reverse=True)
        winner = candidates[0] if candidates else None
        if not winner:
            raise RuntimeError("No candidates were produced.")
        fitness_ok = winner.fitness.score >= cfg.fitness_threshold
        checks_ok = (not cfg.require_all_checks_pass) or (not winner.tests) or all(t.passed for t in winner.tests)
        predator_ok = winner.predator.severity <= cfg.max_predator_severity
        guardian_ok = winner.guardian.severity <= cfg.max_guardian_severity
        selection_gates = {
            "fitness_ok": fitness_ok,
            "checks_ok": checks_ok,
            "predator_ok": predator_ok,
            "guardian_ok": guardian_ok,
            "checks_executed": len(winner.tests),
        }
        if fitness_ok and checks_ok and predator_ok and guardian_ok:
            status = "winner-selected"
        elif not fitness_ok:
            status = "no-winner-below-threshold"
        else:
            status = "no-winner-verification-failed"

        winner_patch = run_dir / "winner.patch"
        winner_patch.write_text(winner.patch, encoding="utf-8")
        applied = committed = pushed = False
        if apply and status == "winner-selected" and winner.patch.strip():
            if run_cmd(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip() != base:
                raise RuntimeError("Base branch moved during MORPH run; refusing to apply stale winner patch.")
            r = run_cmd(["git", "apply", "--3way", str(winner_patch)], cwd=repo)
            if r.returncode != 0:
                r = run_cmd(["git", "apply", str(winner_patch)], cwd=repo)
            if r.returncode != 0:
                raise RuntimeError(f"Winner selected but patch could not be applied: {r.stderr}")
            applied = True
            if commit:
                # Commit only the selected patch, never MORPH's own untracked
                # installation files or unrelated ignored local artifacts.
                if winner.changed_files:
                    run_cmd(["git", "add", "-A", "--", *winner.changed_files], cwd=repo, check=True)
                run_cmd(["git", "-c", "user.name=MORPH", "-c", "user.email=morph@local", "commit", "-m", f"morph: {task[:72]}"], cwd=repo, check=True)
                committed = True
                if push:
                    run_cmd(["git", "push"], cwd=repo, check=True)
                    pushed = True

        healthy = status == "winner-selected" and pass_ratio(winner.tests) >= 0.999 and winner.predator.severity <= 0.25 and winner.guardian.severity <= 0.25
        memory.update_trust(winner.changed_files, healthy)
        memory.deposit(winner.changed_files, f"{task} | fitness={winner.fitness.score:.3f}", min(0.4, winner.fitness.score * 0.35))
        if status == "winner-selected":
            memory.add_antibody({
                "task_signature": task[:240],
                "diagnosis": winner.hypothesis.theory,
                "repair_strategy": f"changed {', '.join(winner.changed_files[:12])}",
                "confidence": round(winner.fitness.score, 4),
                "verification": [t.command for t in winner.tests if t.passed],
            })

        result = {
            "run_id": run_id,
            "status": status,
            "adapter": adapter.name,
            "candidate_count": len(candidates),
            "winner": {
                "generation": winner.generation,
                "hypothesis": winner.hypothesis.to_dict(),
                "fitness": winner.fitness.to_dict(),
                "changed_files": winner.changed_files,
                "diff_lines": winner.diff_lines,
                "predator_findings": winner.predator.findings,
                "guardian_findings": winner.guardian.findings,
                "patch": str(winner_patch.relative_to(repo)),
            },
            "applied": applied,
            "committed": committed,
            "pushed": pushed,
            "selection_gates": selection_gates,
            "run_dir": str(run_dir.relative_to(repo)),
        }
        json_dump(run_dir / "result.json", result)
        return result
    finally:
        if not keep_worktrees:
            manager.cleanup_all()
