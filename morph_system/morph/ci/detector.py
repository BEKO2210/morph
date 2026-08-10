from __future__ import annotations

import json
from pathlib import Path


def detect_commands(repo: Path) -> list[str]:
    commands: list[str] = []
    package = repo / "package.json"
    if package.exists():
        try:
            scripts = json.loads(package.read_text(encoding="utf-8")).get("scripts", {})
        except Exception:
            scripts = {}
        runner = "npm"
        if (repo / "pnpm-lock.yaml").exists():
            runner = "pnpm"
        elif (repo / "yarn.lock").exists():
            runner = "yarn"
        for name in ("test", "typecheck", "lint", "build"):
            if name in scripts:
                commands.append(f"{runner} run {name}")
    if (repo / "pyproject.toml").exists() or (repo / "pytest.ini").exists() or (repo / "tests").exists():
        commands.append("python3 -m pytest -q")
    if (repo / "go.mod").exists():
        commands.append("go test ./...")
    if (repo / "Cargo.toml").exists():
        commands.extend(["cargo test --quiet", "cargo check --quiet"])
    if (repo / "pom.xml").exists():
        commands.append("mvn test -q")
    if (repo / "gradlew").exists():
        commands.append("./gradlew test")
    # stable de-duplication
    seen = set()
    return [c for c in commands if not (c in seen or seen.add(c))]
