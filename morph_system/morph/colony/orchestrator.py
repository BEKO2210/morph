from __future__ import annotations

import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..adapters import make_adapter
from ..ci.detector import detect_commands
from ..ci.runner import run_check, pass_ratio
from ..config import MorphConfig
from ..core.fitness import FitnessInputs, compute
from ..core.graph import build_lightweight_graph, stress_field
from ..core.homeostasis import sense
from ..git.worktrees import WorktreeManager, Worktree
from ..memory.store import MemoryStore
from ..ui import make_reporter
from ..util import filter_ignored_status, json_dump, run_cmd, slug
from .hypotheses import generate, Hypothesis
from .roles import builder, predator, guardian, Review


class CandidateAborted(Exception):
    """Raised when a candidate's Builder step fails outright (even after
    transient retries). The failure is already journaled to disk before
    this is raised; the caller just needs to skip this hypothesis."""


def _apply_winner_patch(repo: Path, patch_file: Path) -> None:
    """Apply a winner without letting a failed strategy dirty the base tree."""
    attempts = (
        ["git", "apply"],
        ["git", "apply", "--3way"],
    )
    check_errors: list[str] = []
    for command in attempts:
        check = run_cmd([*command, "--check", str(patch_file)], cwd=repo)
        if check.returncode != 0:
            check_errors.append(check.stderr.strip())
            continue
        applied = run_cmd([*command, str(patch_file)], cwd=repo)
        if applied.returncode != 0:
            raise RuntimeError(
                "Winner patch passed preflight but failed while applying: "
                f"{applied.stderr}"
            )
        return
    detail = "\n".join(error for error in check_errors if error)
    raise RuntimeError(f"Winner selected but patch could not be applied: {detail}")


ZERO_FITNESS_INPUTS = FitnessInputs(
    tests_ratio=0.0, predator_score=0.0, guardian_score=0.0,
    minimality=0.0, dependency_stability=0.0, blast_radius=0.0, task_signal=0.0,
)


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
    status: str = "scored"  # "scored" | "builder-no-change"


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


def _safe_review(role_fn, label: str, adapter, wt_path, base, task, **agent_kwargs) -> Review:
    """Run predator/guardian. A persistently broken review (non-transient,
    or transient retries exhausted) must not destroy the whole MORPH run —
    it degrades this candidate to maximum severity with a traceable
    finding instead, so selection gates reject it explicitly."""
    report = agent_kwargs.get("report")
    try:
        return role_fn(adapter, wt_path, base, task, **agent_kwargs)
    except Exception as exc:
        if report:
            report(f"{label} review failed: {exc}")
        return Review(1.0, 0.0, [f"{label}-review-failed: {exc}"], "")


def _evaluate(
    adapter, manager, wt, hyp, task, cfg, checks, stress, antibodies, generation,
    *, run_dir: Path, candidate_id: str, report: Callable[[str], None], echo: bool,
    inherited: bool = False,
) -> Candidate:
    instruction = hyp.theory
    if inherited:
        instruction = (
            "You inherited the current best candidate patch. Preserve its correct behavior, then pursue this mutation pressure: "
            + hyp.theory
        )

    agent_kwargs = dict(
        report=report, echo=echo,
        retries=cfg.agent_max_retries, backoff_s=cfg.agent_retry_backoff_s, heartbeat_s=cfg.progress_heartbeat_s,
    )

    journal: dict = {"id": candidate_id, "generation": generation, "hypothesis": hyp.to_dict(), "status": "builder-running"}
    json_dump(run_dir / f"{candidate_id}.json", journal)

    report(f"Builder started ({candidate_id})")
    t0 = time.monotonic()
    try:
        out = builder(
            adapter, wt.path, task, instruction, list(stress.items()), antibodies,
            log_path=run_dir / f"{candidate_id}.builder.log", **agent_kwargs,
        )
    except Exception as exc:
        journal.update(status="builder-failed", error=str(exc))
        json_dump(run_dir / f"{candidate_id}.json", journal)
        report(f"Builder failed ({candidate_id}): {exc}")
        raise CandidateAborted(candidate_id) from exc
    builder_duration = time.monotonic() - t0

    changed = manager.changed_files(wt)
    patch = manager.patch(wt)
    (run_dir / f"{candidate_id}.patch").write_text(patch, encoding="utf-8")
    journal.update(status="builder-done", builder_output=out, changed_files=changed, builder_duration_s=round(builder_duration, 1))
    json_dump(run_dir / f"{candidate_id}.json", journal)
    report(f"Builder completed in {builder_duration:.0f}s ({candidate_id}) — {len(changed)} files changed")

    if not changed:
        # An empty diff is a distinct, explicit outcome. MORPH must not
        # silently continue into normal Predator/Guardian review and
        # fitness-based selection as if this were an ordinary candidate.
        journal["status"] = "builder-no-change"
        json_dump(run_dir / f"{candidate_id}.json", journal)
        report(f"Builder produced no changes ({candidate_id}) — builder-no-change, skipping review")
        no_change = Review(1.0, 1.0, ["builder produced no changes"], "")
        return Candidate(
            hyp, wt, out, [], no_change, no_change, compute(ZERO_FITNESS_INPUTS, cfg.homeostasis),
            [], 0, patch, generation, status="builder-no-change",
        )

    h, minimality, dep_stability, blast = _candidate_metrics(wt, changed, cfg)

    tests = []
    for command in checks:
        report(f"Running {command} ({candidate_id})")
        tests.append(run_check(wt.path, command, cfg.timeout_seconds))
        json_dump(run_dir / f"{candidate_id}.checks.json", [t.to_dict() for t in tests])
    if checks:
        report(f"Checks completed ({candidate_id}) — {sum(t.passed for t in tests)}/{len(tests)} passed")

    report(f"Predator review started ({candidate_id})")
    pred = _safe_review(predator, "predator", adapter, wt.path, wt.base, task, log_path=run_dir / f"{candidate_id}.predator.log", **agent_kwargs)
    journal["predator"] = pred.__dict__
    json_dump(run_dir / f"{candidate_id}.json", journal)
    report(f"Predator review completed ({candidate_id}) — severity {pred.severity:.2f}")

    report(f"Guardian review started ({candidate_id})")
    guard = _safe_review(guardian, "guardian", adapter, wt.path, wt.base, task, log_path=run_dir / f"{candidate_id}.guardian.log", **agent_kwargs)
    journal["guardian"] = guard.__dict__
    json_dump(run_dir / f"{candidate_id}.json", journal)
    report(f"Guardian review completed ({candidate_id}) — severity {guard.severity:.2f}")

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

    journal.update(status="scored", tests=[t.to_dict() for t in tests], fitness=fitness.to_dict())
    json_dump(run_dir / f"{candidate_id}.json", journal)

    return Candidate(hyp, wt, out, tests, pred, guard, fitness, changed, h.diff_lines, patch, generation, status="scored")


def run_once(
    repo: Path, task: str, adapter_name: str, cfg: MorphConfig, *,
    apply: bool, commit: bool, push: bool, keep_worktrees: bool = False, verbose: bool = False,
) -> dict:
    repo = repo.resolve()
    if run_cmd(["git", "rev-parse", "--git-dir"], cwd=repo).returncode != 0:
        raise RuntimeError("MORPH must be run inside a Git repository.")
    base = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo, check=True).stdout.strip()
    start_status = run_cmd(["git", "status", "--porcelain"], cwd=repo).stdout
    base_dirty = filter_ignored_status(start_status, cfg.ignore_paths)
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
    report = make_reporter(run_dir)
    memory = MemoryStore(repo)
    manager = WorktreeManager(repo, run_id)

    candidates: list[Candidate] = []
    try:
        try:
            report("Sensing repository")
            baseline = sense(repo, ignore_paths=cfg.ignore_paths)
            tracked_files = run_cmd(["git", "ls-files"], cwd=repo).stdout.splitlines()
            graph = build_lightweight_graph(repo)
            seeds = _seed_stress(task, tracked_files)
            stress = stress_field(graph, seeds) if seeds else {}
            antibodies = memory.antibodies()

            report(f"Generating {max(1, cfg.clones)} hypotheses")
            hypotheses = generate(
                adapter, repo, task, _repo_summary(repo), max(1, cfg.clones),
                log_path=run_dir / "hypotheses.log", report=report, echo=verbose,
                retries=cfg.agent_max_retries, backoff_s=cfg.agent_retry_backoff_s, heartbeat_s=cfg.progress_heartbeat_s,
            )
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

            # Generation 0: causal diversity.
            for i, hyp in enumerate(hypotheses):
                report(f"Generating hypothesis {i+1}/{len(hypotheses)}: {hyp.name}")
                wt = manager.create(f"g0-clone-{i+1}-{hyp.name}", base)
                try:
                    cand = _evaluate(
                        adapter, manager, wt, hyp, task, cfg, all_checks, stress, antibodies, 0,
                        run_dir=run_dir, candidate_id=f"g0-candidate-{i+1}", report=report, echo=verbose,
                    )
                except CandidateAborted:
                    continue
                candidates.append(cand)

            # Clonal evolution: current winner reproduces under distinct mutation pressures.
            mutation_pressures = [
                Hypothesis("minimalize", "Reduce the patch to the smallest root-cause change; remove incidental churn and preserve compatibility."),
                Hypothesis("harden", "Harden the inherited solution against edge cases, invalid state, concurrency, security and platform variance without broadening scope."),
                Hypothesis("simplify", "Improve structural clarity and maintainability while preserving behavior; prefer deleting accidental complexity over adding abstractions."),
                Hypothesis("performance", "Preserve correctness while removing avoidable hot-path cost, redundant I/O, repeated work or unnecessary allocations."),
            ]
            eligible = [c for c in candidates if c.status == "scored"]
            if eligible:
                parent = max(eligible, key=lambda c: c.fitness.score)
                for generation in range(1, max(0, int(cfg.clone_evolution)) + 1):
                    children: list[Candidate] = []
                    for j, hyp in enumerate(mutation_pressures[: max(1, int(cfg.evolution_children))]):
                        candidate_id = f"g{generation}-candidate-{j+1}"
                        wt = manager.create(f"g{generation}-child-{j+1}-{hyp.name}", base)
                        if parent.patch.strip():
                            patch_file = run_dir / f"g{generation}-parent.patch"
                            patch_file.write_text(parent.patch, encoding="utf-8")
                            r = run_cmd(["git", "apply", str(patch_file)], cwd=wt.path)
                            if r.returncode != 0:
                                continue
                        try:
                            cand = _evaluate(
                                adapter, manager, wt, hyp, task, cfg, all_checks, stress, antibodies, generation,
                                run_dir=run_dir, candidate_id=candidate_id, report=report, echo=verbose, inherited=True,
                            )
                        except CandidateAborted:
                            continue
                        children.append(cand)
                        candidates.append(cand)
                    scored_children = [c for c in children if c.status == "scored"]
                    if not scored_children:
                        break
                    parent = max([parent, *scored_children], key=lambda c: c.fitness.score)

            eligible = [c for c in candidates if c.status == "scored"]
            if not eligible:
                result = {
                    "run_id": run_id,
                    "status": "no-viable-candidate",
                    "adapter": adapter.name,
                    "candidate_count": len(candidates),
                    "winner": None,
                    "applied": False,
                    "committed": False,
                    "pushed": False,
                    "selection_gates": None,
                    "run_dir": str(run_dir.relative_to(repo)),
                }
                json_dump(run_dir / "result.json", result)
                report("No viable candidate produced a scored patch")
                return result

            eligible.sort(key=lambda c: c.fitness.score, reverse=True)
            winner = eligible[0]
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
                _apply_winner_patch(repo, winner_patch)
                applied = True
                report(f"Applied winner patch — {len(winner.changed_files)} files")
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
        except Exception as exc:
            json_dump(run_dir / "error.json", {
                "run_id": run_id,
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
                "candidate_count": len(candidates),
                "scored_candidates": [c.hypothesis.name for c in candidates if c.status == "scored"],
            })
            json_dump(run_dir / "result.json", {
                "run_id": run_id,
                "status": "run-failed",
                "adapter": adapter_name,
                "candidate_count": len(candidates),
                "winner": None,
                "applied": False,
                "committed": False,
                "pushed": False,
                "selection_gates": None,
                "error": str(exc),
                "run_dir": str(run_dir.relative_to(repo)),
            })
            report(f"Run failed: {exc}")
            raise
    finally:
        report("Cleaning worktrees")
        if not keep_worktrees:
            manager.cleanup_all()
