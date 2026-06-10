# Scenario achievability simulation

Tools for checking that each complexity scenario is **achievable** — i.e. a
competent operator can clear most of the mission stream with the available
fleet within the session — and for re-tuning when parameters change.

Everything imports the **real** game code (`src/utils/missionGen.ts`,
`copilot.ts`, `store/gameReducer.ts`), so the numbers are exactly what the app
uses. Run with `npx tsx sim/<file>.mts`.

## `engine.mts` — faithful engine (the source of truth)

Drives the **real `gameReducer`** headlessly: missions spawn, drones travel,
tasks execute, drones fail, replacements arrive, greedy loiter and recovery all
run through the actual reducer. An automated "operator" dispatches the same
actions the UI would, under two policies so you can compare approaches:

- **SMART** — accepts the Aggressive strategy (redundancy) and always recovers
  failures. Approximates good play.
- **LEAN** — commits the minimal sequential floor (no spare), recovers slowly.
  Approximates average play.

Reports per scenario: % missions completed, % tasks completed, mean score, mean
completion time, and failures handled.

```
npx tsx sim/engine.mts --duration=480 --seeds=120          # current live source
npx tsx sim/engine.mts --pkg=PF --duration=480 --seeds=120 # a candidate package
```

Candidate rebalances live in the `PACKAGES` map (speeds / fleet / λ overrides).
`baseline` reads the live source. `PF` is the package that was applied to the
source (8-min sessions; speeds 9 / 6.8 / 5.4; Green-focused fleets). To trial a
new rebalance, add a package, run it, then port the winning numbers into
`missionGen.ts`.

Calibration target: **slightly unachievable** — SMART completes ~80–86% of
missions in good time (a true expert higher), LEAN noticeably less and with a
lower score, so smart redundancy/prioritisation is rewarded.

## `achievability.mts` — capacity floor (fast sanity check)

Computes the **irreducible-work ρ** per drone type: the minimum drone-seconds
the fleet must spend (each task's drones fly out, execute, fly back — no loiter,
no failures) ÷ supply (`fleet × duration`). Duration-independent. ρ ≥ 1 means a
scenario is impossible for *any* operator; ρ well below 1 leaves headroom. Use
it to spot the bottleneck type quickly. (It also runs a coarse greedy DES; the
faithful `engine.mts` supersedes that part.)

## `whatif.mts` / `solve.mts` — parameter search helpers

`whatif.mts` sweeps a grid of fixes (λ scale, fleet bump, Green speed, T4 Green
count) and prints bottleneck ρ_work for each. `solve.mts` inverts it: for chosen
speeds it outputs the fleet each scenario needs to hit a target ρ. Both use the
no-chaining work model, so treat their absolute fleet numbers as conservative —
always confirm a candidate with `engine.mts`.
