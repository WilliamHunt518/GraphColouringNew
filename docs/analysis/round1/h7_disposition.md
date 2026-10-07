# H7 · Does disposition toward AI affect uptake and trust, for one assistant or both?

Script: `scripts/analysis_round1/h7_disposition.py` (prints every number below). Pre-registration:
`docs/analysis/HYPOTHESES_ROUND1.md` §3 H7 and the 2026-10-07 amendments. P09 excluded. P01 has no
battery (it ran `study-v1.0`, before the AIAS-4 battery existed), so n = 32 people.
Participants are named by ID only.

## 1 · Primary (confirmatory)

**Model.** Binomial GEE on strategic decisions with an exchangeable working correlation, clustered
on participant (`build_findings_synthesis.gee`):
`took ~ aias_z + ncolours + ndrones + C(scenario) + C(run) + idx`. `aias_z` is AIAS-4 (the
`score_attitudes` composite, 1–10) z-scored across the 32 people, so each person counts once. It is
not weighted by decisions. Mean = 8.00, SD = 1.21.

| | |
|---|---|
| **AIAS-4 odds ratio per SD** | **0.80**, 95% CI [0.50, 1.27], p = .34 |
| per scale point | 0.83 [0.57, 1.22] |
| n | 587 decisions, 32 people (all strategic decisions, residuals included; the model uses composition, not category) |
| Mancl–DeRouen bias-reduced sandwich (check) | 0.80 [0.47, 1.35], p = .40 |
| **Verdict** | **NOT SUPPORTED.** The interval includes 1. The point estimate is *negative*: people with more positive attitudes to AI took cards slightly less often, which is the opposite of the naive prediction. |

**Detectable effect (Monte-Carlo, 400 simulated datasets per effect size).** The real design was
held fixed: the same 587 rows, covariates, cluster sizes and the observed AIAS values. Outcomes
were simulated from a random-intercept logistic model fitted without AIAS (Bayesian mixed GLM, VB
fit). Its between-person SD is σ_u = 1.55 on the logit scale, a latent ICC of .42. Each simulated
dataset was refitted with the exact primary GEE.

- **Type-I error.** The nominal robust-SE test rejects **9.5%** of the time under the null. The
  sandwich estimator with 32 clusters is anti-conservative.
- **80% power, nominal test:** marginal (GEE-scale) OR ≈ **1.91 per SD**, or ≈ 0.52 in the
  negative direction. On the conditional scale that is OR ≈ 2.40.
- **80% power, size-corrected to a true 5%** (critical |z| = 2.20): marginal OR ≈ **2.0 per SD**
  (≈ 0.50 negative).
- **Person-level cross-check:** Spearman at n = 32 can detect ρ ≥ .48. This matches the synthesis
  page.

So the study could only have detected roughly a doubling (or halving) of the odds of taking a card
per SD of AIAS. The observed CI [0.50, 1.27] rules out a large *positive* effect (OR > 1.27). It
does not rule out a moderate negative one.

## 2 · Sensitivity: `study-v1.12+` cohort (n = 24)

| Specification | OR per SD [95% CI] | p | n |
|---|---|---|---|
| Full-sample z | 0.72 [0.42, 1.23] | .23 | 449 decisions, 24 people |
| Re-z within cohort (SD 1.10) | 0.74 [0.45, 1.21] | .23 | same |

The result is the same direction and also null, slightly more negative.

## 3 · Asymmetry (the pre-registered secondary), then other exploratory analyses

None of the analyses in §3 is confirmatory. Every test is listed in the analysis log (§4).

### 3a · Steiger's test for dependent correlations (person level, n = 32)

**Formula.** Steiger (1980), eq. 15, the pooled "Z2*" form. Variable 1 is AIAS; variables 2 and 3
are the strategic and tactical measures, which share the AIAS variable.

- z_ij = atanh(r_ij), and r̄ = (r12 + r13)/2
- ψ = r23(1 − 2r̄²) − ½ r̄²(1 − 2r̄² − r23²)
- c = ψ / (1 − r̄²)²
- Z = (z12 − z13)·√(n − 3) / √(2 − 2c)

The test is reported for Pearson and for Spearman. Spearman is an approximation here, so a
person-bootstrap 95% CI on the difference (5,000 resamples) is reported beside it.

| Pair (AIAS with…) | strategic r | tactical r | r23 | diff [boot 95%] | Steiger Z, p |
|---|---|---|---|---|---|
| Trust: strategic vs tactical (Spearman) | +.02 | +.22 | .25 | −.20 [−.61, +.19] | −0.90, .37 |
| Trust (Pearson) | +.14 | +.35 | .18 | −.22 [−.64, +.21] | −0.96, .34 |
| Card uptake vs tactical consult (Spearman) | −.15 | +.00 | .28 | −.15 [−.61, +.31] | −0.70, .49 |
| Card uptake vs tactical consult (Pearson) | −.14 | +.06 | .43 | −.20 [−.62, +.24] | −1.01, .31 |
| Card uptake vs keep-unmodified (Spearman) | −.15 | +.05 | .30 | −.20 [−.65, +.26] | −0.89, .37 |
| Card uptake vs keep-unmodified (Pearson) | −.14 | +.13 | .45 | −.27 [−.69, +.18] | −1.40, .16 |

- **No asymmetry is detectable.** The difference between the two correlations would need to be
  about **.60–.62** for 80% power.
- **The direction is the reverse of the hypothesis.** Where there is any lean, AIAS goes with the
  *tactical* tier, not the strategic one.

### 3b · Stacked models with an AIAS × tier interaction

| Model | Interaction (tactical vs strategic AIAS slope) | Notes |
|---|---|---|
| Session-level trust (1–7), Gaussian GEE, 128 ratings; `trust ~ aias_z*C(tier) + C(scenario) + C(run)` | b = +0.13 [−0.34, +0.59], p = .59 | Tier main effect +0.82 [0.36, 1.28]: the known trust gap |
| Decision-level: strategic `took` stacked with tactical `accept` (1,196 rows; tier-specific scenario/run/idx) | ratio of ORs 1.42 [0.84, 2.40], p = .19 | |
| Decision-level: strategic `took` stacked with tactical `consult` | ratio of ORs 1.32 [0.78, 2.21], p = .30 | |

**Tactical-only fits** (exploratory, same AIAS term):

- **Consult:** OR 1.06 [0.61, 1.86].
- **Keep unmodified:** OR 1.20 [0.62, 2.30]. The exchangeable GEE diverged (NaN) with plan size in
  the model, so this was refitted with an independence working correlation, still cluster-robust.
  The stacked models converged as exchangeable.
- The tactical decision table reproduces `load_people()`'s session consult and accept rates exactly
  (0 mismatches).

**Tier-specific trust fits** (exploratory). Strategic trust: b = +0.17 [−0.30, +0.63], p = .48.
**Tactical trust: b = +0.29 [+0.005, +0.58], p = .046.** This is one nominal hit among roughly 40
exploratory tests in this report. It is not tested by any confirmatory family, and its interaction
with tier is null (p = .59), so it is not evidence of asymmetry. The person-level Spearman the
synthesis page uses gives ρ = .22, p = .23.

### 3c · Bespoke scales in the primary model (exploratory; α = .53 / .48)

Each scale was entered alone, in place of AIAS, as a z-scored person covariate.

| Scale | OR per SD [95% CI] | p |
|---|---|---|
| Verification | 0.93 [0.66, 1.31] | .67 |
| Delegation | 0.89 [0.66, 1.21] | .47 |
| "Trust AI more for suggesting than deciding" | 0.92 [0.68, 1.25] | .59 |
| "Human should make the final decision" | 0.95 [0.66, 1.37] | .79 |
| "Hard to tell when AI has erred" | 0.85 [0.56, 1.30] | .46 |

All five are null. With these reliabilities they are uninformative either way.

### 3d · Disposition vs *change* in trust between sessions (link to H5)

- Strategic trust fell by a mean of −0.76 and tactical trust rose by +0.15 (n = 33).
- AIAS vs Δ strategic trust: ρ = −.08, p = .67. AIAS vs Δ tactical trust: ρ = +.24, p = .18.
- Verification: ρ = −.11 (strategic) and +.27 (tactical), p ≥ .14.
- Delegation: ρ = +.20 (strategic) and +.01 (tactical), p ≥ .27.
- As a model, strategic trust ~ AIAS × run: b = −0.08 [−0.46, +0.30], p = .67.

**Disposition does not predict who lost strategic trust.** This supports H5 by elimination: the drop
is not a trait being expressed, so a session-1 experience account is not competing with a
disposition account.

### 3e · Robustness of the primary estimate (exploratory specifications)

| Specification | OR per SD [95% CI] | p |
|---|---|---|
| Genuine missions only (residuals out, n = 545) | 0.82 [0.52, 1.30] | .39 |
| + illogical-card flag + game (`planIndex`) | 0.80 [0.50, 1.27] | .34 |
| AIAS as z of within-sample ranks (ceiling-robust) | 0.75 [0.47, 1.18] | .21 |
| Drop the lowest-AIAS person (influence) | 0.69 [0.41, 1.15] | .15 |
| No covariates | 0.85 [0.56, 1.28] | .43 |
| Independence working correlation | 0.81 [0.51, 1.29] | .37 |
| AIAS < 7 vs ≥ 7 (only 4 people below 7) | 2.58 [0.66, 10.1] (low vs high) | .17 |

The OR is 0.69–0.85 in every specification, and every interval includes 1. The negative direction
is consistent: the four least AI-positive operators took cards *more*. This is a post-hoc
observation, not a finding.

## 4 · Analysis log (in order)

1. Read the pre-registration, CLAUDE.md, STUDY_BUILD §10, `analyse_disposition()` and the synthesis
   payload (`DATA.disposition`: α .80/.53/.48, AIAS mean 8.0, 0/40 Holm, detectable ρ .478).
2. Checked the build version and battery presence per participant. P01 is `study-v1.0` with no
   battery, and the v1.12+ cohort is 24 people. All of them have the battery.
3. **Primary GEE, as specified.** OR 0.80 [0.50, 1.27]. Not supported. Also printed the naive-SE p
   (.25), for information only.
4. Detectable effect, first pass (40 simulations per β, a test run). Noticed type-I error ≈ .10 at
   β = 0.
5. Reran with 400 simulations per β. Added a size-corrected critical value from the empirical null,
   and a Mancl–DeRouen bias-reduced SE on the primary as a check (p = .40). One simulated fit
   diverged at β = 1.25 and is dropped and counted.
6. v1.12+ sensitivity, with the full-sample z and again with a within-cohort z.
7. Steiger tests (Spearman and Pearson) with bootstrap CIs, for trust and for two uptake pairings
   (took vs consult, took vs keep-unmodified). Computed the detectable ρ difference.
8. Stacked trust model (AIAS × tier), plus tier-specific trust fits. The tactical-trust fit gave
   p = .046 (flagged above as exploratory).
9. Stacked decision-level models (took + accept, took + consult). **Failure:** the tactical-only
   `accept` GEE returned NaN. Diagnosed as the exchangeable fit diverging, not separation: GLM and
   independence-GEE estimates agree at b ≈ +0.18. Added `gee_safe`, which falls back to independence
   and labels it.
10. Bespoke scales and the two delegation single items, plus the error-detectability item, in the
    primary model (5 tests).
11. Disposition × Δ trust: 6 Spearman tests and one AIAS × run model.
12. Robustness grid for the primary (7 specifications), and a person-level Spearman sanity check
    (reproduces the synthesis page exactly: took −.149, consult .005, accept .046, trust_s .017,
    trust_t .218).

**Exploratory count:** about 45 tests beyond the primary (12 Steiger rows, 3 interactions, 4
tier-specific fits, 5 scales, 7 Δ-trust tests, 7 robustness specifications, 5 sanity correlations,
and 2 sensitivity fits). One is nominally significant (tactical trust, p = .046), against the
roughly 2 expected by chance. Nothing here should enter the confirmatory family except the primary.

## 5 · Traps from §2 and how they were handled

- **1 · No failures injected.** Not directly relevant, since this is a trait analysis. It means
  "trust" here is trust in two perfect-by-design assistants whose only flaws are the top-up and
  Suggest's blind spot.
- **2 / 3 · Illogical cards are nested in single-type missions.** `ncolours` (effectively binary)
  and `ndrones` are in every model. Adding the `odd` flag left the AIAS OR unchanged (0.80).
- **4 · Residuals.** Category is not used, so residuals stay in the primary. Excluding them changes
  the OR to 0.82.
- **5 / 6 · Decision time and the meaning of "manual".** Decision time is not an outcome here.
  `took` treats every manual choice (pre-emptive or post-card) as not taking a card. This is the
  specified outcome; the split of manual choices is H4's.
- **7 · Before/after.** Not used.
- **8 · Debrief quotes.** Not used.
- **9 · n = 33 (32 here).** Detectable effects are stated for every test: ρ ≥ .48 person-level, a ρ
  difference ≥ .60 for Steiger, and a GEE OR ≈ 1.9–2.0 per SD (size-corrected).
- **Ceiling (AIAS mean 8.0/10, SD 1.21).** 87.5% of people score ≥ 7, two score at or below the
  scale midpoint (5.0 and 5.5), and two score 10. A rank-based AIAS (z of ranks) gives OR 0.75, so
  there is no change in conclusion. A median/7-split leaves only 4 "low" people. The sample cannot
  speak to sceptics.
- **Few clusters (not in §2, found here).** The GEE sandwich SE with 32 clusters gives 9.5% type-I
  error. This matters for every GEE in round 1, not just H7. The primary is null either way.

## 6 · Contradictions and refinements of the brief and the synthesis page

- **Brief Finding 1 caveat.** It says "n = 32 can only detect ρ ≥ .48" and "none of the attitudes we
  measured predicts it". Both are confirmed. Suggested refinement: the single pre-specified test gives
  OR 0.80 per SD [0.50, 1.27]. That **excludes a meaningful positive effect** of AI attitude on card
  uptake (OR > 1.27 per SD), which is a stronger statement than "weak evidence". It cannot exclude a
  moderate negative one.
- **Synthesis "Nor does disposition predict what they reported afterwards — not for either
  assistant".** This is true by Spearman (ρ = .22, p = .23). A session-level GEE on tactical trust
  gives p = .046, and Pearson gives r = .35. This is exploratory, but the wording "not for either
  assistant" slightly overstates. Suggest softening it to: "no reliable link; if anything, a weak
  positive link with *tactical* trust only".
- **Not tested by the page before: the tier asymmetry.** It is null (Steiger p ≥ .16, interaction
  p ≥ .19). Whatever lean exists is towards the tactical tier, the reverse of the hypothesis that
  attitude matters more where the operator decides.
- **The new H5 link.** Disposition does not predict the drop in strategic trust (ρ = −.08).
- **Methodological flag for the supervisor.** The GEE robust SE with 32 clusters is anti-conservative
  (9.5% vs 5%). Every round-1 GEE result near p = .05 should be checked with
  `fit(cov_type='bias_reduced')`.

## 7 · Reproduce

```
cd G:/Files/Code/GraphColouringNew
C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h7_disposition.py          # ~3 min, 400 sims/β
C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h7_disposition.py --nsim 40  # quick check
```

All simulation and bootstrap randomness is seeded (numpy `default_rng(20261007)` and `default_rng(7)`).
