# H5 · Does the drop in strategic trust follow the operator's own session-1 experience?

Script: `scripts/analysis_round1/h5_trust_drop.py` (shared loader `h5_h8_common.py`). Every number
below is printed by the script. P09 excluded; n = 33 (all have trust after both sessions); v1.12+
n = 24.

## 1 · Primary test

**Predictor.** Session-1 missions that failed or were abandoned after the operator took a card.
Defined as follows:

- **Session 1** is the first session the participant played (run 1).
- **A card mission** is one whose final `strategic_choice` in that session was Aggressive or
  Conservative. Three missions were allocated twice, and in those cases the allocation that was in
  force counts.
- **Failed or abandoned** means a `mission_abandoned` event, or `mission_completed.outcome` equal to
  `partial` or `none_completed`. Missions still in flight at the buzzer are not counted: the timer
  cut them off, and the operator never saw them fail. I checked that every unresolved mission with a
  choice appears in `session_ended.inFlightMissionIds`, and that no mission is both completed and
  abandoned.
- **Residuals** count as their own missions. A residual is a new allocation decision (card or
  manual) with its own route, so its fate attaches to that decision. The parent's failure is already
  counted once, as the parent's abandonment. Folding the residual's fate back into the parent would
  count one bad experience twice and credit it to the wrong choice.

**Distribution.** 28 such missions out of 190 session-1 card missions (14 abandoned, 14 partial;
11 after Conservative, 17 after Aggressive). Per person: 0 for 14 people, 1 for 12, 2 for 6 and 4
for 1.

**Outcome.** Δ strategic trust is trust_s after session 2 minus trust_s after session 1, where
trust_s is the mean of the six 1–7 items. It averaged 4.99 → 4.23, and fell for 20 people, rose for
9 and was unchanged for 4.

| | ρ | 95% CI (Fisher-z) | bootstrap CI | p | n |
|---|---|---|---|---|---|
| **Primary, all** | **−0.051** | [−0.388, +0.298] | [−0.429, +0.373] | 0.778 | 33 |

The smallest |ρ| detectable at 80% power with n = 33 is 0.47. The interval rules out a large
negative association (ρ < −0.39) but not a small or moderate one.

**Verdict: NOT SUPPORTED.**

## 2 · v1.12+ sensitivity

ρ = +0.117, 95% CI [−0.301, +0.498], p = 0.585, n = 24. The sign reverses, and the result is
still null.

Pre-registered robustness variant, normalising by the number of session-1 card missions:

- all participants: ρ = −0.012 [−0.359, +0.339], p = 0.95, n = 32;
- v1.12+: ρ = +0.148, p = 0.50;
- per **resolved** card mission: ρ = +0.064 (all), ρ = +0.262 (v1.12+).

All are null. A partial Spearman controlling for scenario order also stays null: ρ = −0.042,
p = 0.82.

## 3 · Secondary (exploratory)

**(a) Discriminant check.** The same predictor against Δ tactical trust gives ρ = −0.153
[−0.473, +0.203], p = 0.40; v1.12+ ρ = −0.237. The check is uninformative: both tiers are null, so
nothing is left to discriminate.

**(b) Other session-1 predictors against Δ strategic trust**, one at a time (n = 33). None reaches
significance except one artefact:

| Predictor | ρ | p |
|---|---|---|
| failed after manual | −0.07 | 0.71 |
| drone failures | −0.17 | 0.35 |
| missions abandoned (any route) | −0.24 | 0.18 |
| benchmark score share | −0.12 | 0.49 |
| failed after Conservative | −0.23 | 0.21 |
| failed after Aggressive | +0.06 | 0.75 |
| card missions (exposure) | −0.06 | 0.74 |
| **illogical cards seen in session 1** | **+0.40** | **0.021** |

The illogical-cards result is an **order artefact**. People who played Strategic Heavy first see
the illogical cards in session 1, and they are also the people whose trust drops least (see (h)).

**(c) Regression with all session-1 predictors** (OLS, HC3 standard errors; card failures, manual
failures, drone failures, benchmark share and order). R² = 0.18 and no predictor is significant.
Card failures: b = −0.24 [−0.89, +0.40]. The order term is the largest (TF b = −0.91, p = 0.053).

**(d) The timing in the design is backwards (found after the fact).** Trust is measured *after*
each session, so session-1 experience should already be in trust_s1, and the experience that falls
*between* the two measurements is session 2's. Every alternative test is null:

- session-1 card failures against the trust_s1 **level**: ρ = −0.08, p = 0.65;
- session-2 card failures against Δ trust: ρ = −0.27 [−0.57, +0.08], p = 0.12;
- first difference (Δ card failures against Δ strategic trust): ρ = −0.21, p = 0.23; against Δ
  tactical trust ρ = +0.13; v1.12+ ρ = −0.02;
- session-level GEE (trust_s on within-person card failures + between-person mean + run, n = 66):
  within b = −0.13 [−0.57, +0.31], p = 0.55.

So the hypothesis fails even with the more appropriate timing.

**(e) Trust change against uptake change.** ρ = +0.16, p = 0.38, as in the brief.

**(f) Debriefs** (quote IDs only).

The biggest drops in strategic trust:

| Participant | Δ strategic trust |
|---|---|
| P33 | −4.83 |
| P15 | −3.50 |
| P32 | −3.50 |
| P01 | −2.83 |
| P35 | −2.17 |
| P19 | −2.17 |
| P02 | −1.50 |
| P11 | −1.33 |

Seven of these eight have a coded debrief. The trust_trajectory quotes from those with big drops
name **noticing errors**, not failed missions:

- `P15/trust_trajectory/1985` and `P33/trust_trajectory/1785` say they could check, or had time to
  notice, only in round 2;
- `P01/trust_trajectory/1775` names one anomalous card;
- `P19/trust_trajectory/1907` and `/2001` describe over-assignment.

The only quote that names exactly the H5 mechanism is `P18/trust_trajectory/1711`: missions failed
after Conservative, leading to abandonment. P18's strategic trust actually **rose** (+0.17, rank
25 of 33), with 1 failed card mission in session 1. P01 had the most session-1 card failures (4)
and a large drop, but attributes the drop to the card's numbers.

**(g) The premise.** Card missions are not more likely to fail than manual ones (resolved missions,
GEE adjusted for composition, scenario and run): OR = 1.22 [0.83, 1.81], p = 0.31. Session 1: 18.9%
of card missions bad against 20.8% of manual ones. A failed card mission was not a distinctive
signal that the card was poor.

**(h) Where the drop sits.** This is the key exploratory finding. The 2×2 crossover
(`study_analysis.crossover`) on trust_s gives:

- run effect −0.78 [−1.24, −0.31], p = 0.002;
- **scenario effect (Tactical − Strategic Heavy) +0.48 [+0.02, +0.95], p = 0.042**;
- carry-over p = 0.57.

In v1.12+ the run effect is −0.85 (p = 0.011) and the scenario effect +0.44 (p = 0.16). Tactical
trust shows neither (run +0.16, scenario −0.16). The change therefore depends on order:

| Order | Mean Δ | Fell |
|---|---|---|
| Strategic Heavy first (SF) | −0.29 | 7 of 17 |
| Tactical Heavy first (TF) | −1.26 | 13 of 16 |

The drop is concentrated in people whose *second* session was Strategic Heavy, the scenario full of
single-type missions and therefore of illogical Conservative cards. These numbers match the
synthesis page's `selfreport.crossover` (scenario diff 0.483), which the brief's Finding 5 does not
mention.

**Post-hoc moderation (one cut among many, treat as hypothesis-generating).** The primary
correlation splits by order:

| Order | ρ | 95% CI | p | n | v1.12+ |
|---|---|---|---|---|---|
| SF | +0.45 | [−0.06, +0.78] | 0.069 | 17 | +0.61, p = 0.026 |
| TF | −0.57 | [−0.84, −0.06] | 0.022 | 16 | −0.46, p = 0.16 |

The difference between orders is z = 2.94, p = 0.003, and the rank-OLS interaction gives
p = 0.018. The TF result is not driven by one person: leave-one-out ρ ranges from −0.67 to −0.50.
The opposite signs cancel to the pooled null. I have no strong mechanism for the SF sign. In TF the
reading would be that session-1 card failures make a person more ready to lose trust once Strategic
Heavy shows them visibly odd cards. Within TF, though, session-1 card failures and run-2 detection
(H8) each carry part of the drop and neither survives jointly (card failures b = −0.63, p = 0.12;
detection b = −1.07, p = 0.12; n = 16).

## 4 · Analysis log (in order)

1. **Built a decision table** that carries mission id, fate and edit trail. It asserts row-for-row
   identity with `build_findings_synthesis.load_decisions()` (606 rows) and passes.
2. **Fate checks.** No mission has both `mission_completed` and `mission_abandoned`. All 154
   unresolved missions with a choice are in `inFlightMissionIds`. Residual depth is at most 2 (6
   residuals of residuals).
3. **Primary test** run as specified: null.
4. **Pre-registered normalised variant** (per card mission, and per resolved card mission): null.
5. **Partial correlation on order**, added because the change score carries ± the scenario effect:
   null.
6. **Discriminant check against tactical trust**: null, so uninformative.
7. **Other predictors one by one**: only illogical cards seen in session 1 is significant (+0.40),
   and it is diagnosed as order.
8. **Joint regression**: null, with order the largest term.
9. **Timing re-specification**: session-2 experience against Δ, first differences, session-level
   within-person GEE. All null. Found after the fact.
10. **Crossover decomposition**: a scenario component of the strategic trust drop (p = 0.042).
11. **Within-order split**: opposite-signed correlations, interaction p = 0.003. Post hoc.
12. **Quote check**: the one quote naming the mechanism belongs to someone whose trust rose.
13. **Premise check**: card missions do not fail more than manual ones.

## 5 · Traps from §2

- **Trap 1 (no injected failures).** The "experience" is ordinary mission failure, mostly driven by
  random drone failures, and it is no more frequent after a card than after a manual choice (3g).
  So there was little card-specific bad experience to learn from.
- **Trap 4 (residuals).** Residuals are handled as their own decisions and category is not used.
  The justification is in §1.
- **Trap 9 (n = 33).** The detectable ρ (0.47) is reported. The within-order results (n = 16–17)
  are well below adequate power and post hoc.
- **Game / scenario confound.** Order (SF/TF) sets which game came first and how many single-type
  missions someone saw. This is the confound that turned out to matter (3h).
- **Traps 2, 3, 5, 6, 7** do not apply to a person-level count. Trap 8 (debrief timing) is noted
  in 3f.

## 6 · Connections to H8, and contradictions or refinements of brief Finding 5 and the synthesis page

- **H5 × H8.** People whose first behavioural detection of the illogical card came in run 2,
  between the two trust surveys, dropped −2.05 against −0.42 (n = 7 against 26, MWU p = 0.008,
  rank-biserial −0.67). All of them are TF, so this is largely the order effect again. Within TF the
  figures are −1.83 against −0.69 (p = 0.083, rank-biserial −0.53). Debrief over-allocation
  mentioners dropped −1.40 against −0.51 (p = 0.12).
- **Finding 5 presents the drop as a run effect.** The crossover also has a scenario component:
  strategic trust is about 0.48 lower after a Strategic Heavy session. Most of the drop is in people
  who played Strategic Heavy *second*. The brief should mention this. It also gives a candidate
  explanation the brief's "second look" story is compatible with: the second look happened in the
  scenario where the flaw is visible.
- **"The drop is not explained by how many illogical cards someone saw (ρ = −.07)."** That figure
  is a pooled session-level *level* correlation. The change-on-change version is ρ = −0.32
  (p = 0.067), but it is entirely order: partial on order gives ρ = +0.03. The brief's conclusion
  stands, but for a reason the brief does not state: dose doesn't matter, scenario order does.
- **No contradiction with "behaviour barely moved".** Δ trust against Δ uptake gives ρ = +0.16.

## 7 · Reproduce

```
cd G:/Files/Code/GraphColouringNew
C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h5_trust_drop.py
```

The script is deterministic (bootstrap seed 20261007; I re-ran it and got identical output) and
runs in about 45 s. It reads
`Results/Participants/*.json` and `Results/Narration/*_s1/quotes.json`, and writes nothing.
