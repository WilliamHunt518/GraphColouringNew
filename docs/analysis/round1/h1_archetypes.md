# H1 · Are there operator archetypes? — round 1 report

Script: `scripts/analysis_round1/h1_archetypes.py` (read-only over `Results/`; prints every number below).
n = 33 participants (P09 excluded), 606 strategic decisions, 630 tactical confirms, 194 recovery
episodes, 66 sessions. Sensitivity cohort `study-v1.12+`: n = 24.

## 1 · Primary test (confirmatory)

**Verdict: NOT SUPPORTED.** Operators do not fall into distinct types. Reliance is a continuum. It has one
robust axis, a weaker second one, and a third carried by two people.

Specification, fixed before the first fit:
- **Features.** The 10 per-person features below, z-scored.
- **Dimension reduction.** PCA, keeping components with eigenvalue > 1 (Kaiser). That keeps 3 components, and Horn parallel
  analysis also keeps 3.
- **Model.** A Gaussian mixture with **diagonal covariance on the PC scores**, k = 1–4, n_init = 20, chosen by BIC.

| Criterion | Required | Result | Pass |
|---|---|---|---|
| 1 · k ≥ 2 beats k = 1 by ΔBIC > 10 | ΔBIC > 10 | BIC k1 378.2, **k2 376.3**, k3 382.3, k4 392.8. Best k = 2 but **ΔBIC = 1.9**. Parameters per fit: 6 / 13 / 20 / 27, on 3 dimensions | ✗ |
| 2 · bootstrap Jaccard (Hennig clusterboot, B = 500), k = 2 | min ≥ .75 | .76 (n = 26 group) and **.47** (n = 7 group) | ✗ |
| 3 · same people group together when session 1 and session 2 are clustered separately (k = 2) | ARI ≥ .5 (threshold set by me; the plan gave none) | **ARI = .04**, permutation p = .42. Run on its own, session 1 picks k = 4 (with singletons) and session 2 picks k = 1 | ✗ |

All three criteria fail. The ΔBIC of 1.9 also sits in the middle of what a population with no clusters
produces. Under a Gaussian-copula null (the observed marginals and rank correlations, no clusters, 200 sims),
42% of null datasets gave a ΔBIC ≥ 1.9. 28% exceeded the ΔBIC > 10 threshold, and the null 95th percentile
was 43.2.

The bootstrap and the copula null had 200–500 draws each, so they are approximate (Monte-Carlo error).

**The ΔBIC > 10 criterion alone has a high false-positive rate on data shaped like this.** Ceilings, ties
and skew produce spurious mixtures. The stability criteria are what carry the test.

**What it could detect.** BIC selection at n = 33 has no closed-form power. As a practical guide, a two-group
structure strong enough to beat the null's 95th percentile would need ΔBIC ≳ 43. The observed 1.9 is
nowhere near that.

### Features (per person, pooled over both sessions; outcomes held out)
| Feature | Definition |
|---|---|
| `took` | card uptake |
| `preempt` | manual choices made before the cards loaded ÷ manual choices. 4 people never chose manual → median-imputed |
| `edit` | edited-card choices ÷ strategic decisions |
| `consult` | tactical confirms where Suggest was pressed |
| `keep` | consulted plans deployed unmodified ÷ consulted. Conditional on consulting, so it is not a copy of `consult` |
| `recSug` | recovery episodes where Suggest was pressed |
| `netSecs` | log1p of the median of max(0, time-to-choice − card reveal delay). The forced 4.05–5.00 s wait is removed: median 6.9 s net against 11.6 s raw |
| `dSmall` / `dLarge` | mean (drones committed − Conservative card total) on single-type / multi-type missions, over all decisions, residuals excluded |
| `previews` | `strategic_card_previewed` events per decision |

Check: my per-person uptake matches `build_findings_synthesis.load_decisions()` exactly (max |diff| = 0,
606 = 606 rows).

## 2 · v1.12+ sensitivity (n = 24)

**NOT SUPPORTED.**

**BIC.** k1 279.6, k2 248.1, k3 245.9, **k4 225.5**, so ΔBIC = 54.1. But the k = 4 solution is 14/8/**1/1**:
two singleton "types". At k = 2 the split is 23/1. With a minimum group size of 4 people (post hoc), k = 1 wins.

**Copula null at n = 24.** ΔBIC > 10 in 66% of null sims, 95th percentile 52.5. The observed 54.1 sits at
about the null's 96th percentile (4% of null sims reached it), so on BIC alone it is only borderline above
the null, and it comes from outliers.

**Stability.** Jaccard at k = 4: .66 / .86 / .61 / .87 (min .61, fail). Session-1 vs session-2 ARI = .06 (p = .21, fail).

## 3 · Secondary results (EXPLORATORY)

### 3a · The continuum: one robust dimension, a weaker second
PCA on the 10 z-scored features. Eigenvalues: 3.07, 1.94, 1.69, 0.90, …

| | Variance | Loadings (correlation with the PC) |
|---|---|---|
| **PC1 — "reliance on the assistants, across tiers"** | 30.7% | took .92, previews .88, consult .62, dSmall .50, recSug .46, keep .42; negative: netSecs −.48, preempt −.34 |
| **PC2 — "generous commitment vs tactical deference"** | 19.4% | dLarge .73, dSmall .66, preempt .45; negative: consult −.56, keep −.48, netSecs −.47 |
| PC3 — "card editing" | 16.9% | edit .88, preempt −.58. Carried almost entirely by P04 (.53) and P24 (.62); everyone else edits ≈ 0 |

**PC1 is stable.**
- **Across bootstrap samples.** Tucker congruence with the full-sample loadings: median .94, and ≥ .85 in 75% of
  resamples.
- **Across sessions.** Projecting each session's features onto the pooled axis gives a session-1 vs session-2
  **ρ = .65 [.38, .82]**, p < .001.

**PC2 is less stable.**
- Congruence median .73, ≥ .85 in only 26% of resamples.
- Its session-to-session ρ is .51 [.18, .74].

**Neither PC is bimodal.** Bimodality coefficient .34 for PC1 and .37 for PC2, both below .555; Shapiro p = .18
and .74. PC1 scores run smoothly from P21 (−4.9) and P03 (−3.6) to P25 (+2.9), with no gap.

**Answer to the fallback question.** The style is mainly **one dimension**: a general disposition to use the
assistants that spans the strategic, tactical and recovery tiers. A weaker second dimension is about how
many drones the operator commits, beyond what the Conservative card offers.

**Per-feature session-1 vs session-2 stability.** Cell-standardised (each session's features z-scored within its run × scenario group):

| Feature | ρ |
|---|---|
| took | .57 |
| edit | .56 |
| consult | .56 |
| keep | .58 |
| recSug | .58 |
| netSecs | .51 |
| previews | .52 |
| preempt | .44 (n = 22) |
| dSmall | −.01 (n = 14) |
| dLarge | .12 |

The drone-commitment features are **not** stable within person. PC2 is therefore the least trustworthy part
of the picture.

### 3b · Do the axes relate to outcomes?
Spearman with 95% CI, n = 33 (32 for disposition). 27 tests, Holm-corrected within this exploratory set.
Detectable |ρ| at 80% power ≈ .47.

| Axis × outcome | ρ [95% CI] | p | Holm |
|---|---|---|---|
| PC1 × strategic trust | **.54 [.22, .75]** | .001 | **.033** |
| PC1 × game-residualised score efficiency | .37 [.01, .65] | .033 | .79 |
| PC1 × benchmark share (game-normalised) | .29 [−.08, .59] | .10 | 1 |
| PC1 × trust gap (tactical − strategic) | −.40 [−.66, −.04] | .022 | .56 |
| PC1 × tactical trust | .18 [−.20, .51] | .32 | 1 |
| PC1 × AIAS-4 / verification / delegation | −.11 / −.21 / −.22 | ≥ .23 | 1 |
| PC2 × trust gap | −.47 [−.71, −.12] | .006 | .17 |
| PC2 × everything else | \|ρ\| ≤ .31 | ≥ .08 | 1 |
| forced k = 2 groups × any outcome (Mann–Whitney) | — | ≥ .22 | 1 |

**Score, session-level GEE** (game-residualised score efficiency on within-person and between-person PC1):
- Between-person b = .059 per PC1 SD [.021, .098], p = .003.
- **Within-person b = .006 [−.050, .062], p = .83.**

The same split as `useVsPerf` (between-person ρ = .38, nothing within). People who rely more score a bit
better, but a session where the same person relied more did not score better.

**Disposition does not predict the reliance axis.** All |ρ| ≤ .22, which agrees with the 0-of-40 screen.

### 3c · Forced k = 2 (descriptive only; it is not a stable partition)
- **Small group:** P02, P04, P10, P15, P22, P24, P30.
- **Profile against the large group:**
  - lower uptake (.44 vs .70);
  - more editing (.24 vs .01);
  - lower recovery Suggest (.17 vs .56);
  - more drones committed on multi-type missions (+1.40 vs +0.49 over the Conservative card).
- It is better read as the "edits and over-commits" tail of the continuum than as a type. Its Jaccard is .47.

### 3d · Debrief stance against the axes
24 of 33 people are coded. A person can hold more than one stance.

| Stance | n | Mean PC1 |
|---|---|---|
| conditional | 14 | 0.01 |
| prefers tactical | 12 | 0.28 |
| distrusts both | 5 | −1.77 (sd 2.69) |
| trusts both | 2 | 0.48 |
| prefers strategic | 1 | −0.44 |

- Kruskal–Wallis on PC1 across the three stances with n ≥ 5: H = 2.95, p = .23. On PC2: p = .26.
- "Distrusts both" leans towards the low-reliance end, as you would expect, but it is not separable at this n.
- Every stance appears in both k = 2 groups.

## 4 · Analysis log (in order)
1. **Read the plan, the builder, `study_analysis`, `decision_features` and the payload.** Surveyed per-session
   counts and versions. Every session has `revealDelayMs` and `deployEnabledAtMs`.
2. **Fixed the operationalisation before fitting** (see the script docstring):
   - The 10 features, with median imputation for empty denominators.
   - `dSmall`/`dLarge` over all decisions rather than manual-only, because the manual-only version is undefined for 6 and 7 people.
   - `keep` conditional on consulting.
   - The net-time definition.
   - Primary = diag GMM on the Kaiser PCs. Reason: a diagonal mixture on correlated raw features gains BIC
     from correlation alone, whereas on PC scores the k = 1 model is the full-covariance Gaussian.
   - Session split standardised within run × scenario.
   - ARI ≥ .5 as the agreement bar.
3. **Run 1.** Primary NOT SUPPORTED (ΔBIC 1.9, Jaccard min .47, ARI .04). v1.12+ also NOT SUPPORTED (ΔBIC 54 from singletons; Jaccard .61; ARI .06).
4. **Robustness grid, 19 specifications.**
   - PCA with 1, 2, 3 or all 10 components; covariance diag, full, tied or spherical.
   - Raw z-features; rank-normal features; manual-only `dSmall`/`dLarge`; the 6 core features.
   - 16 of 19 prefer k ≥ 2, and 13 of 19 have ΔBIC > 10, **but** none passes the stability criteria. The big
     ΔBICs (up to 455) all come from specs known to manufacture components:
     - diag/spherical mixtures on correlated or tied raw features: `keep` = 1 for most people and `edit` = 0 for most;
     - full covariance on 33 points;
     - solutions with 1–2-person components.
   - The rank-normal + Kaiser spec, which removes the marginal artefacts, prefers **k = 1 by 10.7**.
5. **Gaussian-copula null calibration.** On data shaped like ours with no clusters, ΔBIC > 10 occurs 28% of
   the time at n = 33 and 66% at n = 24. This confirmed that BIC alone is not diagnostic here.
6. **Post hoc: minimum cluster size of 4** (a "type" of 1–3 people out of 33 is an outlier). Under it, the
   preferred k drops to 1 in most specs, including v1.12+. Specs that still prefer k ≥ 2 under the
   constraint are the raw-feature diag/spherical fits, which carry the artefact above.
7. **Post hoc: `previews` replaced by A↔C toggles per decision.** `previews` correlates ρ = .79 with uptake,
   largely because choosing a card means clicking it. Toggles are rare (mean .04 per decision) and correlate
   ρ = .28 with uptake. Result: k = 1 (ΔBIC −0.5), and Jaccard at a forced k = 2 = .38 / .76. Same conclusion.
8. **Fallback analysis.** PCA loadings, parallel analysis, bootstrap congruence, session-to-session stability
   of the axes, bimodality.
9. **Secondary.** Axes and forced-k = 2 groups against score (benchmark share and game-residualised
   efficiency), trust, TLX and disposition, Holm-corrected within the set. Session-level within/between GEE.
   Stance cross-tab.
10. **Abandoned.** No other variants were tried and then dropped. A latent profile model with
    non-Gaussian (beta/binomial) indicators was considered but not run. With the minimum-size result and the
    stability failures it would not change the verdict, and it would add another fork.

## 5 · Traps from §2 that applied
- **Trap 5 (forced wait).** Decision time is net of each decision's logged reveal delay.
- **Trap 6 (manual is not one behaviour).** Pre-emptive manual (`preempt`) and edited cards (`edit`) are
  separate features. The edit dimension turned out to be two people.
- **Traps 2–3 (composition).** Commitment features are split by single-type vs multi-type mission, the
  effectively binary composition axis, rather than pooled.
- **Trap 4 (residuals).** Excluded from the size-split commitment features. Kept in the rates, which do not use category.
- **Trap 9 (n = 33).** This is the core of the result:
  - k ≥ 3 solutions all contain tiny components;
  - ΔBIC is calibrated against a null and found to be non-diagnostic;
  - the minimum-size constraint is reported as post hoc.
- **Game confound.** Score outcomes are either the benchmark share (game-normalised) or score efficiency
  residualised on the game mean (scenario × `planSeedIndex`).
- **Build confound (P01–P03 on v1.0–v1.4).** Handled by the v1.12+ re-run. Same verdict.

## 6 · Relation to the current brief / synthesis
- **Consistent with brief Finding 1, and refines it.** The person-level style is real. PC1 is stable across
  sessions (ρ = .65 against .64 for uptake alone) and across bootstrap samples. But it is a **continuum,
  not types**, so "card-takers vs manual operators" language should be avoided.
- **New: the style spans the tiers.** Strategic uptake, tactical consulting, keeping the tactical plan and
  recovery Suggest all load on the same axis. The brief describes reliance tier by tier, but the per-person
  trait is largely common across them. (The tactical features load .42–.62, weaker than strategic uptake at .92.)
- **Consistent with the 0-of-40 disposition screen.** No disposition measure predicts the axis.
- **Mild tension with "self-report and behaviour move separately" (Finding 5).** Between people, the reliance
  axis tracks **strategic trust** (ρ = .54, the one secondary that survives Holm). That echoes the existing
  session-level link (ρ = .49), and Finding 5 is about within-person change. So the two are compatible:
  levels track, changes do not.
- **Score.** People higher on the axis do somewhat better, but only between people (b = .059 per SD), not
  within person. This matches the unreported `useVsPerf`, and H10 should be read alongside it.

## 7 · Reproduce
```
cd G:/Files/Code/GraphColouringNew
C:/Users/Work/anaconda3/python.exe -u scripts/analysis_round1/h1_archetypes.py
```
Takes about 15–20 minutes, mostly bootstraps and null simulations. Fully seeded (`SEED = 20261007`), so
the output is identical on a rerun.
