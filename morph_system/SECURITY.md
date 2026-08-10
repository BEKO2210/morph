# Security model

MORPH deliberately separates orchestration from model permissions.

- Temporary candidates live in isolated Git worktrees.
- Claude Builder is configured for repository file tools, not unrestricted shell execution; Predator/Guardian are read-only.
- Codex Builder uses `workspace-write`; reviews use `read-only` and non-interactive approval policy.
- MORPH itself runs only repository verification commands detected from common project manifests or explicitly configured in `morph.yaml`.
- No push occurs unless the user explicitly passes `--push`.
- Apply/commit/push refuse unrelated dirty base-tree changes.
- Temporary worktrees are force-cleaned in a `finally` path.

Treat repository-controlled test/build scripts as executable code: MORPH will run configured/detected checks. Review third-party repositories before running them with any autonomous coding agent.
