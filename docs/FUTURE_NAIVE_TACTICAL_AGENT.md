# Future work: an organically-fallible tactical planner (naive router)

**Status: not implemented — design note for a future session.** Captured 2026-07-15.
Owner's intent (verbatim steer): *"I'd want it to be organic and not rely on a parameter making it
dumb — rather make it not consider the ordering."*

## Goal

Let the **Tactical Assistant sometimes produce a plan that deadlocks (a lockout)** as a *natural
consequence of how it plans*, not because a knob was turned to degrade it. The mistake should be an
emergent property of an algorithm that has a genuine blind spot — it **does not reason about
cross-drone ordering / dependencies** — so lockouts appear only when the mission geometry and
resourcing happen to trigger the blind spot. No random dice, no "accuracy" multiplier that just
drops tasks.

This pairs with the existing lockout machinery: when the agent's plan deadlocks and the operator
follows it, the live detector (`gameReducer.ts` TICK step 3c) either auto-reroutes (`fixLockouts`
on) or surfaces "Lockout — help needed" (off). So the study can observe whether operators catch and
repair the agent's organic mistakes.

## Why today's agent never deadlocks

`greedyAssign()` in `src/store/gameReducer.ts` is **acyclic by construction**:

1. It processes tasks in **one global order** (`taskOrder`, i.e. most-constrained / T5→T1 first).
2. Every virtual drone is routed from the **hub** (`pos: { ...HUB }`, all `freeAt: now`), and a
   drone is only reused after it finishes its current task.

Because all drones share one starting point and one task order, every drone that gets chained
visits shared tasks in the *same* order → the induced "task depends on task" graph
(`findSchedulingCycle` in `src/utils/scheduling.ts`) can never contain a cycle. Switching from
greedy to plan-all does **not** change this — plan-all just commits the (still-acyclic) multi-hop
chains instead of collapsing them to one step. So a lockout is currently only reachable by the
*operator* manually chaining two drones through a shared task pair in opposite orders.

## The blind spot to introduce: don't consider ordering

Replace the "one global order, everyone starts at the hub" assumption with a router that optimises
**each drone locally and independently**, and never checks that the resulting per-drone orders are
mutually consistent:

> For each committed drone, **from its actual current position**, repeatedly pick the **nearest**
> task that still has unmet demand for that drone's type, assign it, move the drone there, and
> repeat until nothing needs its type. Do this per drone, independently. Emit the resulting per-drone
> routes as `droneSequences`. Never inspect cross-drone dependencies.

Why deadlocks emerge **organically and occasionally**:

- By planning time the committed team is already **loitering at different points around the zone
  perimeter** (`launchToLoiter` spreads drones by angle/slot). Routing each drone from *its own*
  position means two scarce drones shared by two tasks can pick **opposite nearest-first orders** →
  a real cross-drone cycle. `greedyAssign` never sees this because it pretends everyone starts at
  the hub.
- It only bites when the team is **tight enough that two multi-drone tasks must share the same
  drones** (e.g. a Conservative allocation, or a small committed team). With a generous team each
  task gets its own drones → no sharing → no cycle. So the lockout rate rides on **allocation
  tightness × zone geometry**, which is exactly the "emergent, not a parameter" property wanted.

The same naive router also produces plausibly *suboptimal* routing even when it doesn't deadlock, so
it reads as a genuinely weaker planner rather than a sabotaged one.

## Implementation sketch (~40–60 lines)

- New function alongside `greedyAssign`, e.g. `naiveRouteAssign(tasks, committedDrones, now)` in
  `src/store/gameReducer.ts`. Reuse `travelTime`, `TASK_PRIMARY`/`TASK_SUBSTITUTE`, `ASSET_SPEED`,
  `loiterSlot`/`interpolateAssetPosition` for real positions.
- Track remaining demand per `(taskId, type)` from primary compositions. Per drone: loop
  nearest-eligible-task → assign → decrement → advance position. Output `TaskAssignment[]` **and**
  the per-drone visit order.
- Crucial: the per-drone visit order must survive to the committed plan as `droneSequences` so the
  cycle is real. Path: it needs to flow through the **Suggest** handler (so `droneChainOrder` in
  `MapDisplay.tsx`'s `TacticalPlannerView` reflects the naive route) → `CONFIRM_TACTICAL`
  (`action.droneSequences`) → `applyTacticalAllocation` → dispatched by `pickFirstAssignment`
  (already sequence-first) → detected by step 3c. Everything downstream already honours sequences;
  only the Suggest/agent-plan source needs to carry the naive ordering.
- Seed everything via the existing `SeededRNG` if any tie-breaks are randomised, so sessions stay
  reproducible (Critical Constraint #1).

## Where to wire it in — deliberately NOT a "make it dumb" parameter

Per the owner's steer, prefer making the agent's planner *inherently* ordering-blind over gating a
smart-vs-dumb switch on `epsilonTactical`. Practical implication: if/when this replaces the current
ε_T mechanism (which drops a task at random — see `APPLY_STRATEGIC`, `hasTacticalError` /
`suppressedTaskId`), the "low tactical accuracy" condition would become *"the agent uses the naive,
ordering-blind router"* rather than *"the agent randomly omits a task."* Whether both accuracy
levels use the naive router (differing only in something else) or only the low level does is an
open methodology question — but the mistake itself should come from the blind spot, not a knob.

## Before committing to it

- Measure the **organic deadlock rate** across seeds/scenarios with the `sim/` harnesses (see
  [`SCENARIOS.md`](SCENARIOS.md) and the achievability engine) so it bites often enough to matter
  but not so often it dominates. Record any new tuning in `SCENARIOS.md` and bump the scenario
  version if fleet/geometry/demand change (never pool data across incompatible parameter sets).
- Update [`EVENT_LOGGING.md`](EVENT_LOGGING.md) if new fields/events are added (e.g. tagging a
  `tactical_opened.agentPlan` as naive-sourced).
