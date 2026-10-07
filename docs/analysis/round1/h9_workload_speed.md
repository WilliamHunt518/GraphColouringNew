# H9 · Does momentary workload push operators onto the assistant? (+ speed vs accuracy)

Script: `scripts/analysis_round1/h9_workload_speed.py` (prints every number below). P09 excluded.
Primary as pre-registered in `docs/analysis/HYPOTHESES_ROUND1.md` §3 H9 (amended 2026-10-07). All
p-values are raw; Holm correction across the 10 primary tests is the supervisor's job. Participants
are referred to by ID; debrief material by quote ID only.

## 1 · Primary test

**Model.** GEE logit (binomial, exchangeable, clustered on participant, `build_findings_synthesis.gee`)
`took ~ q_w + q_pm + ncolours + ndrones + C(scenario) + C(run)`, where `took` = card taken as-is (the
builder's definition) and `q` = **other** missions queued when the strategic panel opened
(`context.missionsQueued` on the last `strategic_modal_opened` before the choice, minus 1 for the
mission itself), `q_w` = q centred within person, `q_pm` = person mean.

| | OR per extra queued mission | 95% CI | p | n |
|---|---|---|---|---|
| **All 33** | **1.039** | 0.947 – 1.140 | 0.418 | 606 decisions / 33 people |

**Verdict: NOT SUPPORTED.** The estimate is near 1 and the interval excludes the effect sizes that
matter: with this SE the test had 80% power for OR ≥ 1.14 per queued mission (≈ 1.7 across the
0-to-4 range most decisions span), so a moderate load effect on card-taking is unlikely, not merely
undetected. The between-person term goes the other way (OR 0.53 [0.31, 0.94], p = .028): people who
typically face longer queues take cards *less* — but those are the slower, more manual operators who
build their own queues (§5), so this is not a load effect either.

Raw uptake by queue length is flat: 0.64 (q = 0), 0.71, 0.70, 0.60, 0.61 (q ≥ 4).

## 2 · v1.12+ sensitivity (n = 24)

OR **1.030** [0.922, 1.152], p = 0.598, 449 decisions. Same conclusion (detectable OR ≈ 1.17).

## 3 · Secondary (all exploratory)

### 3a · Robustness of the null (Section C of the output)

Every specification is null, ORs 0.94 – 1.33, none with an interval excluding 1:
+ position in session (1.013), + elapsed (1.009), residuals dropped (1.043), game FE instead of
scenario (1.039), centred within person-session (1.060), queue excluding missions awaiting only a
tactical plan (1.047), queue at the *first* open of the mission (1.043), any-queue binary (1.142),
+ previous decision's choice (1.015), person fixed-effects conditional logit (1.050 [0.930, 1.184]),
single-type only (0.960), three-type only (1.102 [0.969, 1.252]), Strategic Heavy only (1.025),
Tactical Heavy only (1.334 [0.924, 1.927]), q capped at 3 (1.054), no controls (0.987).
**Exogenous load** — non-residual mission arrivals in the preceding 30/60/120 s, fixed by the seeded
game and so not buildable by the operator's slowness: OR 0.939 / 0.994 / 0.976 per arrival (all
p > .38); v1.12+: 0.954 / 0.969.

### 3b · What load *does* move at the strategic tier (post hoc)

Load does not shift card vs manual, but I checked whether it changes *which kind* of manual:

| route (all 606 decisions) | OR per queued mission | robust to + idx? | exogenous arrivals60 | v1.12+ |
|---|---|---|---|---|
| pre-emptive manual (before cards readable) | 1.14 [1.02, 1.28] p=.026 | no: 1.09 p=.14 | 1.01 | 1.16 p=.058 |
| manual after reveal, unedited | 0.92 p=.20 | 1.07 | 1.07 | 0.86 p=.063 |
| edited a card | **0.79 [0.69, 0.90] p<.001** | yes: 0.74 p=.004 | 0.90 p=.17 | 0.79 p=.004 |

Conditional on going manual, pre-emption rises with queue on three-type missions (OR 1.48
[1.17, 1.86], n = 115) but not on single-type ones. **Read this cautiously:** the pre-emption
association disappears once position in session is controlled (queue and pre-emption both grow over a
session), and neither result replicates on the exogenous arrivals measure. The fall in card edits
under load is the most robust (survives idx and v1.12+) but rests on 35 edits from 10 people.
Suggestive at most: *under load, operators stop fine-tuning cards*, rather than taking more of them.
Aggressive-vs-Conservative given a card: OR 0.90, p = .19. Decision time does not shrink with the
queue (−0.39 s per mission, p = .19).

### 3c · Tactical consult, keep-unmodified and recovery Suggest

Load at `tactical_opened` (the strategic-choice moment); plan size (log drones × tasks) and ncolours
controlled.

- **Consulted Suggest ~ queue: OR 1.143 [1.035, 1.262], p = .008** (n = 630/33); kept unmodified (of
  all) 1.132 p = .014 — the same signal, since 96% of consulted plans are kept. Kept | consulted:
  1.039, p = .77. Survives game FE (1.153) and dropping residuals (1.144), v1.5+ (1.120 p=.046), but
  **not v1.12+ (1.093 [0.973, 1.228], p = .13)**, **not + elapsed time (1.083, p = .17)** and **not
  the exogenous arrivals measure (1.009, p = .85)**. Consulting rises by OR 1.12 per minute into the
  session (p = .007) and the tactical queue correlates with elapsed time (ρ = .31). Best reading:
  within-session learning/drift towards Suggest that happens to coincide with queue build-up, not a
  load response. It is the closest thing to support for H9 in the data and it does not hold up.
- Other tactical plans pending: OR 0.79, p = .14.
- **Recovery Suggest** (194 episodes, 33 people; pressed in 41%): ~ queue OR 1.068 p = .19; v1.5+
  1.099 p = .12; v1.12+ 1.011 p = .80.

### 3d · Drones available as a separate pressure

- Card-taking ~ drones available (within person): OR 0.988 per drone [0.964, 1.013] (0.94 per 5
  drones), p = .34; slack (available − needed) 0.987; "tight" (slack < 5) 1.16 p = .50; tasks pending
  1.013; missions active 1.022. Raw uptake is 0.72 when slack < 5 vs 0.64 otherwise, but this is
  composition (it vanishes in the model). **No reserve-pressure effect on the strategic tier.**
- Tactical consult ~ drones available: 0.993, p = .60.
- **Recovery Suggest ~ drones available: OR 1.076 per drone [1.028, 1.126], p = .002**, robust to
  elapsed (1.076), v1.5+ (1.081 p=.008), v1.12+ (1.074 p=.013). Direction is *opposite* to H9: when
  the hub is depleted (high pressure), operators press recovery Suggest *less*. Not explained here;
  plausibly a depleted hub coincides with a busy moment in which operators abandon or patch by hand
  rather than consult (H3 owns recovery — worth cross-checking against its abandonment data).

### 3e · Speed vs accuracy (the 2026-10-07 extension)

**(1) Does using the assistant save time?**

*Strategic tier* (`secs` = panel open → choice; cards are unappliable until `deployEnabledAtMs`, the
slower card's 4–5 s reveal; manual is never gated):

| route | n | raw median | net of forced reveal |
|---|---|---|---|
| card as-is | 397 | 10.8 s | 6.0 s |
| manual before cards loaded | 97 | 8.2 s | 8.2 s |
| manual after cards loaded | 112 | 18.4 s | 18.4 s |

Within person, controlling composition/scenario/run: a card is **2.5 s faster raw** [−5.0, −0.04],
p = .046 (log scale −14%), **7.2 s faster net of the forced wait** [−9.7, −4.7]. The saving is entirely
on three-type missions (raw −5.2 s [−7.6, −2.8]); on **single-type missions a card is not faster raw
(+3.0 s [−1.9, +7.8])**, because pre-emptive manual beats the reveal — exactly what P29 says
(`P29/manual_override/1469`). (Builder's non-centred model, reproduced: manual +2.79 s, p = .013.)

*End to end*: no detectable saving. Panel open → tactical deployment: card −2.6 s (p = .19), Suggest
−2.5 s (p = .39); mission arrival → deployment: card −3.8 s (p = .65), Suggest +10.3 s (p = .25)
(592 missions). Arrival → deployment is dominated by queue wait (median ≈ 78–89 s in every route cell).

*Tactical tier* (`tactical_opened` → `tactical_confirmed`; Suggest reveals the plan at 1 entry/s —
`MapDisplay.tsx`, 1000 ms since before v1.0 — and Deploy cannot beat the reveal: confirm − last
Suggest − entries×1 s has 5th percentile +0.6 s):

| route | n | median open→confirm | idle before first action | engaged (first action→confirm) | plan size (median drones×tasks) |
|---|---|---|---|---|---|
| hand-built | 144 | 20.1 s | 6.3 s | 11.3 s | 15 |
| Suggest, kept | 468 | 21.8 s | 5.6 s | 13.6 s | 24 |
| Suggest, edited | 18 | 56.4 s | 6.7 s | 23.0 s | 49 |

Within person, controlling log plan size: Suggest-kept is **16% faster** than hand-built (log
−0.168 [−0.313, −0.023], p = .023); consulted at all −0.122 (p = .074); edited is **60% slower**
(+0.474, p = .007). Net of the forced reveal, Suggest is ~43% faster (log −0.57). Engaged time does not
differ (−0.04, p = .57) — the ~8 s reveal eats most of the saving. By plan-size tercile: small
14.2 vs 14.9 s, mid 23.9 vs 21.8 s, **large 44.6 vs 25.6 s** (hand vs Suggest); the
consulted × size interaction is in that direction but ns (−0.126, p = .10). Exact person × size-band
matching (43 cells, 25 people): Suggest ×0.86, faster for 14 of 25, Wilcoxon p = .35.

**Post hoc, prompted by P15/P27:** with Suggest, operators are **4.8× more likely to open another
strategic panel before confirming** (OR 4.83 [2.33, 10.02], p < .001, same latency and plan size;
46% vs 19% of plans). The tactical assistant's time value is parallelism — working on something else
while it reveals (`P15/agent_comparison/1812`, `P18/scenario_comparison/1577`) — more than a shorter
planning clock.

**(2) Time pressure and personal pace**

- NASA-TLX temporal demand vs card uptake: session ρ = −.14 (p = .25), person-level ρ = −.18
  (p = .33), within-person change ρ = −.21 (p = .24); decision-level GEE OR 0.94 per 5 TLX points
  (p = .76). **No link.**
- **Temporal demand vs tactical consulting is *negative***: session ρ = −.35 (p = .005),
  between-person ρ = −.37 (p = .032), within-person change OLS +order b = −0.017 per TLX point
  [−0.032, −0.002], p = .031 (Spearman −.33, p = .062); keep-unmodified similar but weaker
  (between ρ = −.34, p = .054). The opposite of "pressure → reliance"; plausibly reverse causation
  (hand-building plans *is* what feels time-pressured), since the TLX is filled after the session.
- Personal pace (between person) vs reliance: median net card deliberation ρ = −.06 (n = 31);
  post-reveal manual time ρ = +.31 (n = 15, p = .27); pick-up speed (arrival → first open) ρ = −.24
  (p = .18) with card uptake, −.02 with consulting; hand-built s/drone vs consulting ρ = +.35 (n = 20,
  p = .13). **No pace–reliance relation** detectable at n ≈ 33 (detectable ρ ≈ .48).

**(3) Speed–quality trade-off**

- *Projected completion* (`finalProjectedCompletion − agentProjectedCompletion`; same scheduler). For
  kept plans this gap is pure confirmation-delay cost (ρ = .65 with delay; plan = agent's), so delay
  must be held fixed. At equal delay (B-spline), **hand-built plans project 44.7 s later**
  [17.5, 71.8], p = .001, driven by a tail: P(gap > 30 s) OR 8.4 [2.6, 27.7]. At confirms ≤ 12 s the
  difference is +3.3 s [1.2, 5.3]; medians are near zero in every delay band up to 20 s.
- *Realised* (clean missions: completed in full, no drone failure, n = 298): realised completion minus
  the agent's projection is **+5.1 s [0.5, 9.6] later for hand-built plans** at equal delay (p = .030).
  Projections are exact for kept plans (mean error 0.0 s) but pessimistic for hand plans (mean −20 s),
  so the projected 45 s overstates the real cost by an order of magnitude.
- Completion in full (OR 0.90 for kept vs hand, p = .82), log duration from allocation (−0.066,
  p = .23), mission penalty (+1.5, p = .50): no detectable difference. Edited-Suggest plans look worst
  descriptively (n = 9 completed) but are too few to model.
- Strategic companion (H10 owns it): card missions run 14% shorter from allocation (log −0.145
  [−0.232, −0.057], p = .001); completion in full OR 0.43 (p = .18), penalty −1.2 (p = .35).

**Net: there is no speed–accuracy trade-off to find.** Where the assistant saves time (three-type
strategic decisions, large tactical plans) its output is at least as good: tactical plans kept as
suggested finish slightly sooner than hand-built ones, and card missions finish sooner after
allocation. The time it saves, though, is small (2–5 s strategic; ~16% tactical, mostly eaten by the
reveal) and does not carry through to faster deployment end to end.

### 3f · Debriefs (quote IDs; existence checked by the script)

- *Values the assistant for speed* (10 people): `P11/verification/1811`, `P20/agent_comparison/1620`,
  `P22/agent_comparison/1776`, `P24/verification/1689`, `P26/general_ai_disposition/1828`,
  `P26/agent_comparison/1717`, `P28/agent_comparison/1796`, `P28/verification/1833`,
  `P29/general_ai_disposition/1656`, `P30/agent_comparison/1540`, `P31/overall_experience/1750`,
  `P32/scenario_comparison/1497`.
- *Finds the assistant slow* (6): `P29/manual_override/1469`, `P11/agent_comparison/1781`,
  `P26/agent_comparison/1717`, `P27/design_suggestions/1750`, `P15/agent_comparison/1812`,
  `P20/agent_comparison/1620` (who corrects his own ranking once he remembers the reveal).
- *Hands over when overwhelmed* (9): `P11/scenario_comparison/1964`, `P18/scenario_comparison/1577`,
  `P32/scenario_comparison/1497`, `P33/verification/1653`, `P35/verification/1729`,
  `P35/agent_comparison/1699`, `P15/agent_comparison/1812`, `P22/agent_comparison/1776`,
  `P24/verification/1660`, `P25/verification/1490`.

These three groups do not rely more: card uptake 0.59 / 0.61 / 0.58 vs 0.67 / 0.65 / 0.67 for everyone
else; tactical consult 0.75 / 0.61 / 0.69 vs 0.76 / 0.78 / 0.78. Per-person within-session queue ×
card-taking correlations (29 people with variation): median ρ = .05, 18 positive vs 11 negative (sign
test p = .27). Of the 8 load-delegation speakers with variation, 6 have positive ρ (.05 – .37) and 2
negative (P18 −.04, P32 −.21) — a weak lean in the stated direction, not a reliable one. What people
say about speed is largely *true at the level of the tool* (cards are faster on complex missions,
Suggest faster on big plans, and it allows parallel work) but it does not show up as load-contingent
behaviour.

## 4 · Analysis log (in order)

1. Read HYPOTHESES_ROUND1 (§1, §2, H9, amendments), CLAUDE.md, `decision_features.py`,
   `build_findings_synthesis.py`, `study_analysis.py`, EVENT_LOGGING.md, brief template.
2. Inspected raw events. Found `context.missionsQueued` counts the mission being opened (≥ 1 at every
   open — asserted) and missions with a strategic choice but an unconfirmed tactical plan (status stays
   `queued`; `gameReducer.buildContext`). Defined q = missionsQueued − 1; kept the logged quantity as
   primary, with the tactical-pending-excluded version as robustness.
3. Wrote my own loader (needed `missionId`, context, arrival times) and asserted it reproduces
   `load_decisions()` row for row (606 rows: choice, composition, `took`, `secs`, reveal identical);
   asserted file order = `seq` order in every session.
4. Primary + v1.12+ → null. Computed detectable OR from the SE.
5. Checked mechanical links: person-mean q correlates with median decision time (ρ = .49) and pick-up
   wait (ρ = .50); within session, q rises 0.02 per second the previous decision took (p = .022).
   So added exogenous recent-arrivals measures (30/60/120 s), lagged choice, within person-session
   centring, idx/elapsed, game FE, conditional logit, composition and scenario strata. All null.
6. Noticed card-time `latencyMs` ≠ timestamp difference on 2 reopened missions (latency 22/9 s vs
   62 s); used the builder's convention (last open → choice) throughout. Two rows, immaterial.
7. Secondary: pre-emptive-manual | manual vs q came out OR 1.23 (p = .001) → added (post hoc) the
   four-way route decomposition, + idx, exogenous and v1.12+ checks. Pre-emption effect is a
   time-in-session confound; edit reduction survives idx and v1.12+ but not the exogenous measure.
8. Tactical consult vs q came out OR 1.14 (p = .008) → added (post hoc) + elapsed, game FE, residuals,
   exogenous, v1.5+/v1.12+. Fails elapsed, exogenous and v1.12+; consult rises with elapsed itself.
9. Recovery Suggest: q null; drones available positive (unexpected direction) → checked elapsed,
   v1.5+, v1.12+: robust. Reported, not interpreted further (H3's territory).
10. Speed, strategic: raw vs net of `deployEnabledAtMs` (verified = max card reveal, and card choice is
    always ≥ 0.96 s after it). Split by drone types after seeing the pooled result.
11. Speed, tactical: found the Suggest progressive reveal (1 entry/s, `MapDisplay.tsx`; constant since
    before v1.0 per `git log -L`), verified empirically that confirm never precedes the reveal end.
    Added engaged time (first Suggest/drag → confirm) and the interleaving count after reading
    P15/P27; the interleaving test (OR 4.8) is post hoc.
12. Quality: first fit of projected gap ~ log(time spent) on hand plans gave b = +95 — recognised this
    is delay cost, not quality (gap grows with delay even for kept plans, whose plan is the agent's).
    Replaced with delay-adjusted models (spline, ≤ 12/20 s windows), then (post hoc) a realised
    analogue on clean missions, which shows the projected penalty for hand plans is mostly not realised.
13. TLX temporal demand: session, person, and within-person (Δ run2 − run1 with order dummy) tests;
    personal-pace measures chosen to be route-fixed so pace is not mechanically the reliance rate.
14. Quotes: grouped all coded quotes mentioning speed/time/overwhelm by reading them; IDs verified.

## 5 · Traps from §2

1. **No failures injected** — no ε effects possible; recovery Suggest's blind spot is the only agent
   "error" and is not part of this hypothesis.
2. **Illogical cards nested in single-type missions** — not an H9 predictor; composition is controlled
   and single/three-type strata are reported separately.
3. **Drone types effectively binary** — strata (1 vs 3 types) reported; `C(ncolours)` robustness given.
4. **Residuals** — primary keeps them (no category used, as the builder's main models); dropping them
   changes nothing (OR 1.043).
5. **Forced reveal inside decision time** — critical here. All strategic timing is reported raw *and*
   net of `deployEnabledAtMs`; the queue model of decision time controls the route. The tactical tier
   has an analogous, previously undocumented forced wait (Suggest reveals 1 drone-task entry per second,
   ~8 s for a median plan); timings are reported raw, net of it, and as engaged time.
6. **Manual is not one behaviour** — decomposed into pre-emptive / post-reveal / edited (§3b), which is
   where the only strategic load signal appears.
7. **Before/after is not a baseline** — not applicable (no event study); time-in-session is the
   analogous trap here, because queue length grows over a session: every load effect was re-tested with
   idx/elapsed and with the exogenous arrivals measure. That is what removed the two apparent positives.
8. **Quotes are post-session, single coder** — used only to frame and to group people, never aligned to
   decisions.
9. **n = 33** — person-level correlations (TLX, pace) can only detect ρ ≳ .48; stated with each null.

Additional, H9-specific: **queue length is endogenous to the operator** (slow/manual operators build
their own queues; between-person ρ = .49 with decision time), so the within-person term is the only
interpretable one, and the exogenous arrivals measure is the cleanest check. **Tactical latency is not
working time** (planning can be deferred and interleaved; 19–46% of plans have another strategic panel
opened in between), hence the engaged-time measure.

## 6 · Against the current brief and synthesis page

- **Finding 2 ("within a person, the mission decides")** is reinforced: the momentary state of the
  game adds nothing to composition. The `SIMPLE_MYSELF` quotes about handing over when overwhelmed
  describe mission size and complexity, not queue pressure — and the people who say it do not show it
  in their decisions. If the brief cites P11's overwhelm quote (`P11/scenario_comparison/1964`) as
  evidence of a load mechanism, it should say the logs do not support a moment-to-moment version of it.
- **Finding 3 ("manual is mostly not rejection"; "Manual is never the faster route")**: the brief's
  caveat that manual "is never the faster route" is **wrong for single-type missions**: there a card is
  not faster raw (+3.0 s, ns; pre-emptive manual median 8.2 s vs card 10.8 s). The +2.8 s pooled figure
  includes the forced reveal; net of it, cards are 7.2 s faster within person, entirely on three-type
  missions. Suggest rewording: "Manual is never faster on multi-type missions; on single-type missions a
  pre-emptive manual allocation beats waiting for the cards — which is P29's stated reason."
- **Synthesis page, workload**: "Workload / took a card" ρ = −.14 is reproduced for *temporal* demand
  (−.14). New: temporal demand is *negatively* related to tactical consulting at every level
  (session −.35, person −.37, within-person b < 0), not reported on the page.
- **New, for the tier comparison (Finding 4)**: the tactical Suggest has its own forced reveal (1 s per
  drone-task entry) that is not mentioned anywhere in the reports; a timing comparison between tiers
  must account for both waits. And the measurable time value of Suggest is parallel work (OR 4.8 for
  opening another strategic panel), consistent with P15/P18/P32.

## 7 · Reproduce

```
cd G:/Files/Code/GraphColouringNew
C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h9_workload_speed.py
```

Deterministic; ~1 min. Reads `Results/Participants/*.json` and (for quote-ID checks)
`Results/Narration/*_s1/quotes.json`; writes nothing.
