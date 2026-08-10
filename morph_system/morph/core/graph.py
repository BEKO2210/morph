from __future__ import annotations

import re
from collections import defaultdict, deque
from pathlib import Path

from ..util import run_cmd

IMPORT_RE = re.compile(
    r"(?:from\s+['\"]([^'\"]+)['\"]|import\s+(?:.+?\s+from\s+)?['\"]([^'\"]+)['\"]|from\s+([\w.]+)\s+import|import\s+([\w.]+))"
)


def build_lightweight_graph(repo: Path, max_files: int = 2500) -> dict[str, set[str]]:
    files = run_cmd(["git", "ls-files"], cwd=repo).stdout.splitlines()[:max_files]
    graph: dict[str, set[str]] = defaultdict(set)
    file_set = set(files)
    by_stem: dict[str, list[str]] = defaultdict(list)
    for f in files:
        by_stem[Path(f).stem].append(f)
    for rel in files:
        p = repo / rel
        if p.suffix.lower() not in {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")[:200_000]
        except OSError:
            continue
        for match in IMPORT_RE.finditer(text):
            token = next((x for x in match.groups() if x), None)
            if not token:
                continue
            stem = Path(token.replace(".", "/")).name
            for target in by_stem.get(stem, []):
                if target != rel:
                    graph[rel].add(target)
                    graph[target].add(rel)
    return graph


def stress_field(graph: dict[str, set[str]], seeds: list[str], decay: float = 0.68, depth: int = 4) -> dict[str, float]:
    stress: dict[str, float] = {}
    q: deque[tuple[str, int, float]] = deque()
    for seed in seeds:
        stress[seed] = 1.0
        q.append((seed, 0, 1.0))
    while q:
        node, d, value = q.popleft()
        if d >= depth:
            continue
        for nxt in graph.get(node, set()):
            nv = value * decay
            if nv > stress.get(nxt, 0.0):
                stress[nxt] = nv
                q.append((nxt, d + 1, nv))
    return dict(sorted(stress.items(), key=lambda kv: kv[1], reverse=True))
