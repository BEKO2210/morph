# MORPH architecture

```text
USER TASK
   │
   ▼
REPOSITORY SENSING ──► HOMEOSTASIS BASELINE
   │
   ▼
LIGHTWEIGHT CAUSAL/IMPORT GRAPH
   │
   ▼
STRESS FIELD
   │
   ▼
CAUSAL HYPOTHESES
   │
   ├─────────────┬─────────────┐
   ▼             ▼             ▼
WORKTREE A     WORKTREE B     WORKTREE C
   │             │             │
 BUILDER        BUILDER        BUILDER
   │             │             │
 EXECUTION      EXECUTION      EXECUTION
   │             │             │
 PREDATOR       PREDATOR       PREDATOR
   │             │             │
 GUARDIAN       GUARDIAN       GUARDIAN
   └─────────────┴─────────────┘
                 │
                 ▼
          FITNESS SELECTION
                 │
        ┌────────┴─────────┐
        │                  │
      BELOW             WINNER
    THRESHOLD               │
        │                   ├──► winner.patch
     no apply               ├──► optional apply/commit/push
                            └──► antibody + pheromone memory
                 │
                 ▼
             APOPTOSIS
       delete temp worktrees
                 │
                 ▼
                EXIT
```

## Design invariant

> MORPH does not choose a patch because an agent sounds confident. It selects repository states by executable evidence plus adversarial and homeostatic pressure.
