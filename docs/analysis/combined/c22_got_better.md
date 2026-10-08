# C22 "got better with practice": did their use of the assistants change, and is that why their workload is lower?

Script: `scripts/analysis_combined/c22_got_better.py`. It only reads data and prints every number in
this report. P09 is excluded. Quotes are labelled by participant ID only.

## The question

Six of the 33 participants were coded **C22**: they *say they got better, faster or more confident
with practice*. They are P10, P11, P15, P21, P30 and P32. Their workload was lower than everyone
else's. Workload here is the **raw NASA-TLX (RTLX)**: the plain mean of the six TLX sliders, 0–20,
with higher meaning more workload. The screening test that found the gap was one of 124 run
without correction, so the gap could be chance.

The researcher asked whether this group's **use of the assistants** changed between session 1 and
session 2, and whether that change explains their lower workload. I also checked four alternative
explanations: a stable "type of person" difference, performance, game and scenario order, and
study version. Finally I checked whether their self-report of getting better matches what the logs
show.

## Terms

- **Card uptake (`took`)**: the share of strategic decisions where the operator took the Aggressive
  or Conservative card as offered, rather than allocating manually.
- **Suggest consulted (`consult`)**: the share of tactical plans where the operator pressed Suggest.
  The planner starts empty, so pressing it is a deliberate choice.
- **Suggest kept (`keep`)**: of the plans where Suggest was consulted, the share deployed without
  changes.
- **Recovery Suggest (`recSug`)**: the share of failure-recovery episodes where Suggest was pressed.
- **Pre-emption (`preempt`)**: of the manual allocations, the share made before the cards had
  finished loading.
- **Decision time (`stratNet`, `tacNet`)**: the median per session of the log of the time taken to
  decide. The forced waits are subtracted (the card reveal, and Suggest's one entry per second). This
  is the round-2 workstream G definition.
- **Change**: session 2 minus session 1, per person. **Level**: the mean of the two sessions.
- **zgame**: session score standardised within each of the four games, so a score is compared only
  with others who played the same missions. P01 and P02 use the rescaled score.
- **Game-relative RTLX (`rtlx_g`)**: RTLX minus the mean RTLX of everyone who played that game.

## Method

The comparisons were listed in the script's docstring before any number was computed. Every
comparison is the C22 mean minus the mean of the other 27. Its p-value comes from a two-sided
permutation test: the C22 label was reshuffled at random 20,000 times. I ran **30 group
comparisons**:

- 7 reliance changes
- 7 reliance levels
- 8 workload rows
- 5 performance and design rows
- 3 accuracy changes

I also ran **17 permutation tests on adjusted coefficients** for the mediation step. None of these
47 tests is corrected for multiple comparisons. At this many tests, about two p-values below .05
are expected by chance alone. With 6 people in the group, only a large effect could be detected.
Everything below is descriptive first.

## 1 · Did their reliance change more than other people's? No.

Change from session 1 to session 2, mean per person. The table shows the mean change, the
difference between groups, and the permutation p.

| measure | C22 (n=6) | others (n=27) | diff | p |
|---|---|---|---|---|
| card uptake | −0.03 | −0.05 | +0.02 | .88 |
| Suggest consulted | +0.12 | +0.08 | +0.04 | .71 |
| Suggest kept (n=5 / 26) | 0.00 | −0.02 | +0.02 | .89 |
| recovery Suggest (n=4 / 25) | +0.04 | +0.04 | +0.01 | .99 |
| pre-emption (n=6 / 16) | −0.15 | 0.00 | −0.15 | .49 |
| strategic decision time (log) | −0.12 | −0.18 | +0.06 | .81 |
| tactical decision time (log) | −0.83 | −0.25 | −0.58 | .13 |

None of these differs between the groups. Within the group, people changed in **opposite
directions**:

- Card uptake rose for P10 and P32 and fell for P15 (0.67 → 0.12) and P30.
- Suggest consultation rose for P21 and P32 and fell for P11 and P15.

The average change is therefore close to zero, as it is for everyone else. The only notable
pattern is tactical planning time, which fell faster for the C22 group: about 56% faster against
about 22% faster, p = .13. This is a speed-up, not a change in reliance.

## 2 · Do they rely on the assistants less overall? Somewhat, and it does not explain their workload.

Level, the mean of the two sessions:

| measure | C22 | others | diff | p |
|---|---|---|---|---|
| card uptake | 0.46 | 0.71 | −0.25 | **.026** |
| Suggest consulted | 0.59 | 0.79 | −0.20 | .067 |
| Suggest kept | 0.92 | 0.94 | −0.02 | .89 |
| recovery Suggest | 0.35 | 0.51 | −0.17 | .37 |
| pre-emption | 0.51 | 0.34 | +0.17 | .33 |
| strategic / tactical decision time | similar | | | .30 / .69 |

The C22 group took fewer strategy cards and pressed Suggest somewhat less. Dropping any one member
leaves the uptake gap between −0.17 and −0.29. But reliance level is not linked to workload across
the whole sample: card uptake and mean RTLX correlate at r = −0.11, and Suggest consultation and
mean RTLX at r = −0.12.

## 3 · Does any reliance measure mediate the workload gap? No.

I regressed mean RTLX on C22 membership, n = 33. The C22 coefficient is **b = −2.42** RTLX points.
I then added each reliance measure as a covariate, one at a time:

- **Change measures** move the C22 coefficient by at most ±0.09. The exceptions are pre-emption
  change (+0.17, but on only 22 people) and tactical-time change (+0.52, to −1.90; the covariate
  correlates r = .32 with RTLX).
- **Level measures** make the C22 gap *larger*, not smaller. Card uptake takes it to −3.25 and
  Suggest consulted to −3.02. Lower reliance therefore does not account for the lower workload.
  If anything, it masks a little of it.

Only tactical-time change shrinks the gap noticeably, and only by about a fifth. That covariate
does not differ reliably between groups (p = .13). Treat it as a weak hint, not mediation.

## 4 · Is it a level difference, or a bigger drop? Mostly a level difference, clearer in session 2.

| RTLX | C22 | others | diff | perm p (means) | Mann–Whitney p |
|---|---|---|---|---|---|
| session 1 | 6.83 | 8.81 | −1.98 | .22 | .22 |
| session 2 | 6.61 | 9.48 | −2.86 | **.040** | .010 |
| change s2 − s1 | −0.22 | +0.66 | −0.88 | .49 | — |
| mean of both | 6.72 | 9.15 | −2.42 | .076 | .012 |
| game-relative, mean | −1.50 | +0.33 | −1.83 | .14 | — |

- **Neither group's workload dropped across sessions on average.** Other participants' workload
  rose by 0.66 points. The C22 group's fell by 0.22 points, but that average is driven by P32 alone
  (9.5 → 5.0). P11 went *up* by 2.5, P10 and P30 rose slightly, P15 stayed flat, and P21 fell 0.5.
  The difference in change between groups is not reliable (p = .49).
- **In session 1 the group was already below the median, but not by much.** Their session-1 ranks
  among the 33 were 5, 7, 9, 16, 17 and 21 (rank 1 = lowest workload). By session 2 all six fell
  between ranks 4 and 12. Across the sample, RTLX correlates r = .67 between session 1 and
  session 2, so workload is largely a stable trait of the person.
- The gap appears in both scenario orders. With Strategic Heavy first the group means are 6.3
  against 9.5; with Tactical Heavy first, 7.1 against 8.8. Each order has only 3 C22 members.
- The two p-values for the mean disagree: .076 for the permutation of means and .012 for the
  rank-based Mann–Whitney. All six C22 members sit below the others' median, but the means are
  pulled around by a few extreme scores among the 27.

The best reading: the group has **lower workload at both time points**, a person-level difference
that is more visible in session 2. It is not a group whose workload fell steeply.

## 5 · Alternatives: performance, order, version. None explain it.

| | C22 | others | p |
|---|---|---|---|
| zgame, mean of sessions | +0.16 | −0.04 | .64 |
| mission completion rate, mean | 0.85 | 0.81 | .25 |
| Strategic Heavy first | 3 of 6 | 14 of 27 | 1.0 |
| swapped game pairing (P31–P36) | 1 of 6 (P32) | 5 of 27 | 1.0 |
| version study-v1.12 or later | 4 of 6 | 20 of 27 | 1.0 |

The group is matched on scenario order, game pairing and version. Their average performance is not
better. Adjusting the C22 workload coefficient for performance moves it only slightly: zgame takes it
to −2.20 and completion rate to −1.97. Performance is weakly linked to lower workload across the
sample (r ≈ −.35), and accounts for at most about a fifth of the gap.

## 6 · Is the self-report accurate? Yes for score; partly for speed.

| change s1 → s2 | C22 | others | p |
|---|---|---|---|
| zgame (score within game) | **+0.86** | −0.09 | **.020** |
| completion rate | +0.04 | −0.03 | .28 |
| mean mission time (s) | −16.7 (median +7.3) | +0.7 (median +8.0) | .45 |
| tactical decision time (log), from §1 | −0.83 | −0.25 | .13 |
| strategic decision time (log), from §1 | −0.12 | −0.18 | .81 |

**All six C22 members improved their within-game score from session 1 to session 2**, by between
+0.28 and +1.95 standard deviations. *(Supervisor check, 2026-10-08: with P01/P02 left out of the game means — they played on half task weights — P21's change is −0.08, so it is five of six; the group difference is unchanged.)* Only 37% of the other 27 improved. Dropping any one member
keeps the difference between +0.73 and +1.07. Because zgame is standardised within game, the
improvement is not explained by playing an easier game second. It holds in both orders:

- Strategic Heavy first: +1.18 for the C22 group against −0.16 for the others.
- Tactical Heavy first: +0.54 against −0.02.

This is the strongest result here. It also fits what the code describes: the people who *say* they
got better *did* get better relative to their peers. It is one of 47 uncorrected tests, but the
direction was the one the code predicts, and the result is consistent across all six people.

Their speed is a weaker match. Tactical planning sped up more (not reliably), and strategic decision
time did not.

## 7 · What they said

- P10: "there was definitely an improvement further throughout session one, and in session two, you
  really find your stride"
- P11: "partly this is due to the experience, I suppose. And I was better at it the second time."
  P11 also said the first scenario made them "more reliant on" the agent because it felt harder,
  yet P11's own card uptake was 0.71 → 0.54 and RTLX *rose* 5.5 → 8.0.
- P15: "because i have more experience after the first round and now i can check": the experience
  went into checking the strategic cards for mistakes. P15's card uptake then collapsed, 0.67 → 0.12.
- P21: "I also optimized the way that they worked with the assistance", but also "it was a bit more
  mentally demanding … because I was operating at a faster pace". RTLX went 7.3 → 6.8.
- P30: "i sort of got into the rhythm of having to anticipate other problems"
- P32: "I understood the task more as I went … letting the tactical one get on with it". P32 is the
  only member whose reliance and workload moved together: Suggest consulted 0.50 → 1.00, card
  uptake 0.45 → 0.86, RTLX 9.5 → 5.0.

Most of these quotes answer the interviewer's standard question comparing the first and second
scenario, so the code was partly prompted by the interview structure. The evidence file flags none
of them as led. Two people (P11, P15) describe practice making them rely on the assistants **less**,
and one (P32) **more**. That spread is the qualitative counterpart of the near-zero average change
in §1.

## Conclusion

- **A change in reliance does not explain the lower workload.** The C22 group's change in card
  uptake, Suggest use, recovery Suggest, pre-emption and decision time does not differ from other
  people's (all p ≥ .13). Members moved in opposite directions, and controlling for any reliance
  change leaves the workload gap essentially intact.
- **It is mainly a level difference.** The group reports lower workload in both sessions. The gap is
  larger and more reliable in session 2 (−2.9 points, p = .04) than in session 1 (−2.0, p = .22).
  It does not come from a group-wide drop: on average their workload barely moved.
- **The group also relies on the assistants somewhat less overall** (card uptake 0.46 against 0.71,
  p = .026). This is not why their workload is lower; adjusting for it widens the gap.
- **Performance, order, game pairing and version do not explain it.** The group is matched on all
  three design factors. Performance absorbs at most about a fifth of the gap.
- **Their self-report is accurate for score.** All six improved within game from session 1 to
  session 2 (+0.86 SD against −0.09 for the others, p = .02).
- **Confidence: low.** The group has 6 people, 47 uncorrected tests were run, and the original
  workload gap was itself a screening finding. The most defensible statement is: *people who felt
  they improved did improve, and they report lower workload, especially once they had improved;
  their reliance on the assistants does not explain either.*
