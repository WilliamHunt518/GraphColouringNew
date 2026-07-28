# OLD DRAFTS — DO NOT USE

**Everything in this folder is superseded / deprecated. Do not treat any of it as current
plans, design intent, or ground truth.** It is kept only for historical reference and will
likely be replaced by newer drafts soon.

Ignore this folder unless you are *specifically* asked to look at old material.

## Contents

- **`FUTURE_NAIVE_TACTICAL_AGENT.md`** — a design note (never implemented) proposing an
  organically-fallible, ordering-blind tactical planner that would let the Tactical Assistant
  deadlock on its own. **We are NOT going ahead with this.** Lockouts are handled the way the
  current code does it: detected live, then either auto-rerouted (`fixLockouts` on) or surfaced
  to the operator for a human fix with an agent Suggest option (`fixLockouts` off). See
  `CLAUDE.md` → "Scheduling deadlocks" for the live behaviour.

- **`paper/`** — an earlier paper draft (`main.tex`, `tactical_agent_revised.tex`,
  `ScopeOfAutonomy-2.pdf`, `figs/`). Superseded; new drafts will be added elsewhere when ready.
  Do not cite or sync code against this draft.
