#!/usr/bin/env python3
"""Workstream B (round 2) -- does load / pace pressure show up somewhere other than queue length at the
moment of decision?  Variants B1-B5 of docs/analysis/HYPOTHESES_ROUND2.md §4 + three pre-stated extras.

Every test is one row of the spec table (`Specs.run`). All GEEs: binomial or gaussian, exchangeable,
clustered on participant, `cov_type='bias_reduced'`. Load predictors are centred within person
(`x_w`) with the person mean (`x_pm`) as a covariate, re-centred on every subsample. Default controls
are game fixed effects (scenario x game index) and run, plus composition.

EXTRAS (written here before any of them was run; reasons repeated in the report's analysis log):
  X1  Checking time after the Suggest reveal finishes, on kept Suggest plans, vs the queue at the last
      Suggest press (expected -). Reason: pressure may show as rubber-stamping a revealed plan rather
      than as more uptake; this is the only tactical-tier timing that is neither forced nor deferrable.
  X2  Previewing both cards before taking one, vs queue (expected -). Reason: pressure may narrow the
      comparison of the two cards rather than change whether one is taken.
  X3  Card-takers' deliberation net of the forced reveal vs the age of the oldest waiting mission
      (expected -). Reason: H9 tested decision time against queue length pooled over routes; the card
      route net of the reveal is the cleanest 'rushing' measure and the oldest-wait is a different load.

Run from the repo root:  C:/Users/Work/anaconda3/python.exe scripts/analysis_round2/wB_main.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import wB_common as c

CS = 'ncolours + ndrones + C(game) + C(run)'          # strategic controls
CT = 'lplan + ncolours + C(game) + C(run)'            # tactical controls


def hdr(s):
    print('\n' + '=' * 110 + '\n' + s + '\n' + '=' * 110)


def run_all(sp: c.Specs, S: pd.DataFrame, T: pd.DataFrame):
    T = T.copy()
    T['lplan_c'] = T.lplan - T.lplan.mean()
    S = S.copy()
    S['ncol3'] = S.threetype
    SS = c.samples(S)

    # ── B1 · other load measures ─────────────────────────────────────────────────────────────
    hdr('B1 · Other load measures -> card taken as-is (strategic) and Suggest consulted (tactical)')
    b1 = [  # (id, var in S, var in T, label, scale, expected, scale label)
        ('B1a', 'firstWait', 'firstWait', "the mission's own wait, arrival -> first opened (per 60 s)", 60, '+'),
        ('B1b', 'st_oldest', 'st_oldest', 'age of the oldest OTHER mission still waiting (per 60 s)', 60, '+'),
        ('B1c', 'st_active', 'st_active', 'missions in flight', 1, '+'),
        ('B1d', 'st_fail60', 'st_fail60', 'drone failures in the previous 60 s', 1, '+'),
        ('B1e', 'dronesAvail', 'st_dronesAvail', 'drones in reserve (per 5; fewer = more depleted)', 5, '-'),
    ]
    for vid, vs, vt, lab, sc, ex in b1:
        sp.run(vid + '-took', 'Card taken ~ ' + lab, 'S-all', S, 'took',
               '%s_w + %s_pm + %s' % (vs, vs, CS), vs + '_w', centre=[vs], expected=ex, scale=sc,
               predictor='%s (within person, x%s)' % (vs, sc))
        sp.run(vid + '-cons', 'Suggest consulted ~ ' + lab + ' [at tactical_opened]', 'S-all', T, 'consulted',
               '%s_w + %s_pm + %s' % (vt, vt, CT), vt + '_w', centre=[vt], expected=ex, scale=sc,
               predictor='%s (within person, x%s)' % (vt, sc))
    sp.run('B1f-took', 'Card taken ~ per-colour reserve slack (min over needed colours of available - needed)',
           'S-all', S, 'took', 'colslack_w + colslack_pm + %s' % CS, 'colslack_w', centre=['colslack'],
           expected='-', predictor='colslack (within person)')
    # time-in-session check on the two that are most 'pressure-like'
    for vid, vs, vt, sc in (('B1b', 'st_oldest', 'st_oldest', 60), ('B1d', 'st_fail60', 'st_fail60', 1)):
        sp.run(vid + '-took-el', 'as %s-took, + elapsed minutes' % vid, 'S-all', S, 'took',
               '%s_w + %s_pm + %s + emin' % (vs, vs, CS), vs + '_w', centre=[vs], scale=sc, expected='+' if vid != 'B1e' else '-')
        sp.run(vid + '-cons-el', 'as %s-cons, + elapsed minutes' % vid, 'S-all', T, 'consulted',
               '%s_w + %s_pm + %s + emin' % (vt, vt, CT), vt + '_w', centre=[vt], scale=sc, expected='+')
    # samples for the headline measures
    for vid, vs, vt, sc in (('B1b', 'st_oldest', 'st_oldest', 60), ('B1d', 'st_fail60', 'st_fail60', 1)):
        for code in ('S-v112', 'S-s1', 'S-27'):
            sp.run(vid + '-took', 'Card taken ~ %s' % vs, code, SS[code], 'took',
                   '%s_w + %s_pm + %s' % (vs, vs, CS), vs + '_w', centre=[vs], scale=sc, expected='+')
            sp.run(vid + '-cons', 'Suggest consulted ~ %s' % vt, code, c.samples(T)[code], 'consulted',
                   '%s_w + %s_pm + %s' % (vt, vt, CT), vt + '_w', centre=[vt], scale=sc, expected='+')

    # ── B2 · final 90 s ──────────────────────────────────────────────────────────────────────
    hdr('B2 · The final 90 s of a session (deadline pressure)')
    for y in ('took', 'early'):
        print('  raw %s by 90-s window of the session:' % y,
              S.groupby(pd.cut(S.elapsed_open, [0, 90, 180, 270, 390, 480])).agg(n=(y, 'size'), m=(y, 'mean'))
              .round(3).to_dict('index'))
    print('  raw consulted by window:', T.groupby(pd.cut(T.elapsed_open, [0, 90, 180, 270, 390, 480]))
          .agg(n=('consulted', 'size'), m=('consulted', 'mean')).round(3).to_dict('index'))
    sp.run('B2a', 'Card taken ~ decision in final 90 s', 'S-all', S, 'took',
           'final90_w + final90_pm + %s' % CS, 'final90_w', centre=['final90'], expected='+')
    sp.run('B2b', 'Card taken ~ final 90 s, net of a linear time trend', 'S-all', S, 'took',
           'final90_w + final90_pm + %s + emin' % CS, 'final90_w', centre=['final90'], expected='+')
    sp.run('B2c', 'Suggest consulted ~ final 90 s', 'S-all', T, 'consulted',
           'final90_w + final90_pm + %s' % CT, 'final90_w', centre=['final90'], expected='+')
    sp.run('B2d', 'Suggest consulted ~ final 90 s, net of linear trend', 'S-all', T, 'consulted',
           'final90_w + final90_pm + %s + emin' % CT, 'final90_w', centre=['final90'], expected='+')
    sp.run('B2e', 'Pre-emptive manual (before cards readable) ~ final 90 s, net of trend', 'S-all', S, 'early',
           'final90_w + final90_pm + %s + emin' % CS, 'final90_w', centre=['final90'], expected='+')
    sp.run('B2f', 'log strategic decision time ~ final 90 s (| route, trend)', 'S-all', S, 'lsecs',
           'final90_w + final90_pm + took + %s + emin' % CS, 'final90_w', centre=['final90'], binomial=False,
           expected='-', notes='b on log seconds; route (took) controlled because cards carry the forced reveal')
    sp.run('B2g', 'log tactical open->confirm ~ final 90 s (| consulted, plan size, trend)', 'S-all', T, 'llat',
           'final90_w + final90_pm + consulted + %s + emin' % CT, 'final90_w', centre=['final90'],
           binomial=False, expected='-')
    for code in ('S-v112', 'S-s1', 'S-27'):
        sp.run('B2b', 'Card taken ~ final 90 s, net of trend', code, SS[code], 'took',
               'final90_w + final90_pm + %s + emin' % CS, 'final90_w', centre=['final90'], expected='+')
        sp.run('B2d', 'Suggest consulted ~ final 90 s, net of trend', code, c.samples(T)[code], 'consulted',
               'final90_w + final90_pm + %s + emin' % CT, 'final90_w', centre=['final90'], expected='+')

    # robustness of B2d, ADDED AFTER SEEING B2d (logged as such in the report)
    TA = c.tactical_all()
    print('  all non-recovery planners opened: %d; unconfirmed %d (all opened in the final 90 s: %d)'
          % (len(TA), (TA.confirmed == 0).sum(), ((TA.confirmed == 0) & (TA.final90 == 1)).sum()))
    sp.run('B2d-r1', 'Suggest pressed ~ final 90 s, net of trend, incl. planners cut off by the session end',
           'S-all', TA, 'consultedAny', 'final90_w + final90_pm + %s + emin' % CT, 'final90_w', centre=['final90'],
           expected='+', notes='robustness of B2d added after seeing it')
    TL = T[T.elapsed_open >= 270]
    sp.run('B2d-r2', 'Suggest consulted: final 90 s vs the 120 s before it (no trend)', 'S-all', TL, 'consulted',
           'final90_w + final90_pm + %s' % CT, 'final90_w', centre=['final90'], expected='+',
           notes='robustness of B2d added after seeing it; local comparison 270-390 s vs 390-480 s')
    T['emin2'] = T.emin ** 2
    sp.run('B2d-r3', 'Suggest consulted ~ final 90 s, net of a quadratic trend', 'S-all', T, 'consulted',
           'final90_w + final90_pm + %s + emin + emin2' % CT, 'final90_w', centre=['final90'], expected='+',
           notes='robustness of B2d added after seeing it')
    print('  placebo: the same 90-s-window indicator (net of linear trend) at every position in the session:')
    for w0 in (0, 90, 180, 270, 300, 390):
        T['win'] = ((T.elapsed_open >= w0) & (T.elapsed_open < w0 + 90)).astype(int)
        r = c.fit_term(T, 'consulted', 'win_w + win_pm + %s + emin' % CT, 'win_w', ['win'], True)
        if r:
            print('    window %3d-%3d s: OR %.3f [%.3f, %.3f] p=%.3f' % (w0, w0 + 90, np.exp(r['b']), np.exp(r['lo']),
                                                                      np.exp(r['hi']), r['p']))

    # ── B3 · opposite: pre-emption under load ───────────────────────────────────────────────
    hdr('B3 · Opposite: under load, operators pre-empt MORE (manual before the cards are readable)')
    print('  pre-emptive manual: %d of %d decisions (%d people)' % (S.early.sum(), len(S), S[S.early == 1].pid.nunique()))
    for vid, v, lab, sc in (('B3a', 'st_oldest', 'oldest other waiting mission (per 60 s)', 60),
                            ('B3b', 'st_active', 'missions in flight', 1),
                            ('B3c', 'st_fail60', 'drone failures in previous 60 s', 1),
                            ('B3d', 'firstWait', "mission's own wait (per 60 s)", 60)):
        sp.run(vid, 'Pre-emptive manual ~ %s (+ trend)' % lab, 'S-all', S, 'early',
               '%s_w + %s_pm + %s + emin' % (v, v, CS), v + '_w', centre=[v], scale=sc, expected='+')
    sp.run('B3e', 'Pre-emptive manual ~ exogenous arrivals in prior 60 s, three-type missions (+ trend)', 'S-all',
           S[S.threetype == 1], 'early', 'st_arr60_w + st_arr60_pm + ndrones + C(game) + C(run) + emin',
           'st_arr60_w', centre=['st_arr60'], expected='+')
    for code in ('S-v112', 'S-s1', 'S-27'):
        sp.run('B3a', 'Pre-emptive manual ~ oldest waiting (per 60 s) (+ trend)', code, SS[code], 'early',
               'st_oldest_w + st_oldest_pm + %s + emin' % CS, 'st_oldest_w', centre=['st_oldest'], scale=60,
               expected='+')

    # ── B4 · constrained ─────────────────────────────────────────────────────────────────────
    hdr('B4 · Constrained: tactical tier with load at the first planner action; three-type missions only')
    T3 = T[T.threetype == 1]
    S3 = S[S.threetype == 1]
    sp.run('B4a', 'Suggest consulted ~ queue at the first planner action', 'S-all', T, 'consulted',
           'fa_queued_w + fa_queued_pm + %s' % CT, 'fa_queued_w', centre=['fa_queued'], expected='+')
    sp.run('B4b', 'Suggest consulted ~ other tactical plans pending at first action', 'S-all', T, 'consulted',
           'fa_tacPending_w + fa_tacPending_pm + %s' % CT, 'fa_tacPending_w', centre=['fa_tacPending'], expected='+')
    sp.run('B4c', 'Suggest consulted ~ exogenous arrivals in 60 s before first action (+ trend)', 'S-all', T,
           'consulted', 'fa_arr60_w + fa_arr60_pm + %s + emin' % CT, 'fa_arr60_w', centre=['fa_arr60'], expected='+')
    sp.run('B4d', 'Card taken ~ oldest waiting (per 60 s), three-type missions', 'S-all', S3, 'took',
           'st_oldest_w + st_oldest_pm + ndrones + C(game) + C(run)', 'st_oldest_w', centre=['st_oldest'], scale=60,
           expected='+')
    sp.run('B4e', 'Card taken ~ exogenous arrivals prior 60 s, three-type (+ trend)', 'S-all', S3, 'took',
           'st_arr60_w + st_arr60_pm + ndrones + C(game) + C(run) + emin', 'st_arr60_w', centre=['st_arr60'],
           expected='+')
    sp.run('B4f', 'Card taken ~ drone failures prior 60 s, three-type', 'S-all', S3, 'took',
           'st_fail60_w + st_fail60_pm + ndrones + C(game) + C(run)', 'st_fail60_w', centre=['st_fail60'],
           expected='+')
    sp.run('B4g', 'Suggest consulted ~ queue at first action, three-type missions', 'S-all', T3, 'consulted',
           'fa_queued_w + fa_queued_pm + lplan + C(game) + C(run)', 'fa_queued_w', centre=['fa_queued'], expected='+')
    sp.run('B4a-el', 'as B4a, + elapsed minutes', 'S-all', T, 'consulted',
           'fa_queued_w + fa_queued_pm + %s + emin' % CT, 'fa_queued_w', centre=['fa_queued'], expected='+',
           notes='time-in-session check (H9 lesson) added after seeing B4a')
    sp.run('B4a-strat', 'Suggest consulted ~ missions awaiting a STRATEGIC decision at first action (+ trend)', 'S-all',
           T, 'consulted', 'fa_queued_w + fa_queued_pm + fa_tacPending_w + fa_tacPending_pm + %s + emin' % CT,
           'fa_queued_w', centre=['fa_queued', 'fa_tacPending'], expected='+',
           notes='added after seeing B4a: separates strategic queue from other open tactical plans')
    sp.run('B4a-r1', 'as B4a, only plans whose first action came within 10 s of opening (no deferral)', 'S-all',
           T[(T.first_ts - T.open_ts) <= 10000], 'consulted', 'fa_queued_w + fa_queued_pm + %s' % CT, 'fa_queued_w',
           centre=['fa_queued'], expected='+', notes='robustness of B4a added after seeing it')
    sp.run('B4a-r2', "H9's measure for comparison: logged queue at tactical_opened, game FE, bias-reduced", 'S-all',
           T, 'consulted', 'q_w + q_pm + %s' % CT, 'q_w', centre=['q'], expected='+',
           notes='comparison row added after seeing B4a (H9 reported OR 1.143 with default robust errors)')
    co = T[T.consulted == 1]
    print('  mechanism (descriptive): among consulted plans, another strategic panel opened before confirming in '
          '%.0f%% when the strategic queue at first action was 0 vs %.0f%% when >= 1'
          % (100 * (co[co.fa_queued == 0].interleaved > 0).mean(), 100 * (co[co.fa_queued >= 1].interleaved > 0).mean()))
    for code in ('S-v112', 'S-s1', 'S-27'):
        sp.run('B4a', 'Suggest consulted ~ queue at first planner action', code, c.samples(T)[code], 'consulted',
               'fa_queued_w + fa_queued_pm + %s' % CT, 'fa_queued_w', centre=['fa_queued'], expected='+')

    # ── B5 · speed as the reason ─────────────────────────────────────────────────────────────
    hdr('B5 · Speed as the reason: reliance where the assistant saves most time, and load x size')
    sp.run('B5a', 'Suggest consulted ~ log plan size (drones x tasks), within person', 'S-all', T, 'consulted',
           'lplan_w + lplan_pm + ncolours + C(game) + C(run)', 'lplan_w', centre=['lplan'], expected='+',
           notes='context: plan size is where Suggest saves time (H9: 44.6 vs 25.6 s on large plans)')
    sp.run('B5b', 'Suggest consulted ~ queue x plan size (interaction)', 'S-all', T, 'consulted',
           'q_w * lplan_c + q_pm + ncolours + C(game) + C(run)', 'q_w:lplan_c', centre=['q'], expected='+')
    sp.run('B5c', 'Suggest consulted ~ exogenous arrivals x plan size (+ trend)', 'S-all', T, 'consulted',
           'arrivals60_w * lplan_c + arrivals60_pm + ncolours + C(game) + C(run) + emin', 'arrivals60_w:lplan_c',
           centre=['arrivals60'], expected='+')
    sp.run('B5d', 'Card taken ~ three-type mission, within person', 'S-all', S, 'took',
           'ncol3_w + ncol3_pm + ndrones + C(game) + C(run)', 'ncol3_w', centre=['ncol3'], expected='+',
           notes='context: cards save ~5 s on three-type missions only (H9); composition effect = brief Finding 2')
    sp.run('B5e', 'Card taken ~ queue x three-type (interaction)', 'S-all', S, 'took',
           'q_w * threetype + q_pm + ndrones + C(game) + C(run)', 'q_w:threetype', centre=['q'], expected='+')
    sp.run('B5f', 'Card taken ~ exogenous arrivals x three-type (+ trend)', 'S-all', S, 'took',
           'arrivals60_w * threetype + arrivals60_pm + ndrones + C(game) + C(run) + emin', 'arrivals60_w:threetype',
           centre=['arrivals60'], expected='+')
    for code in ('S-v112', 'S-s1', 'S-27'):
        TT = c.samples(T)[code].copy()
        TT['lplan_c'] = TT.lplan - TT.lplan.mean()
        sp.run('B5b', 'Suggest consulted ~ queue x plan size', code, TT, 'consulted',
               'q_w * lplan_c + q_pm + ncolours + C(game) + C(run)', 'q_w:lplan_c', centre=['q'], expected='+')

    # ── extras ───────────────────────────────────────────────────────────────────────────────
    hdr('Extras X1-X3 (pre-stated in the module docstring before running)')
    K = T[(T.route == 'suggest-kept')].dropna(subset=['lpostReveal', 'ls_queued'])
    print('  kept Suggest plans with a reveal: %d; post-reveal checking time median %.1f s (5th pct %.1f)'
          % (len(K), K.postReveal.median(), K.postReveal.quantile(.05)))
    sp.run('X1', 'log checking time after Suggest reveal (kept plans) ~ queue at last Suggest press', 'S-all', K,
           'lpostReveal', 'ls_queued_w + ls_queued_pm + %s' % CT, 'ls_queued_w', centre=['ls_queued'],
           binomial=False, expected='-', extra=1)
    tk = S[S.took == 1]
    print('  card-takers: previewed both cards in %.2f, any in %.2f' % (tk.bothprev.mean(), tk.anyprev.mean()))
    sp.run('X2', 'Previewed both cards before taking one ~ queue', 'S-all', tk, 'bothprev',
           'q_w + q_pm + %s' % CS, 'q_w', centre=['q'], expected='-', extra=1)
    sp.run('X3', "log card deliberation net of forced reveal ~ oldest waiting (per 60 s)", 'S-all', tk, 'lnet',
           'st_oldest_w + st_oldest_pm + %s' % CS, 'st_oldest_w', centre=['st_oldest'], scale=60,
           binomial=False, expected='-', extra=1)
    sp.run('X3-el', 'as X3, + elapsed minutes', 'S-all', tk, 'lnet',
           'st_oldest_w + st_oldest_pm + %s + emin' % CS, 'st_oldest_w', centre=['st_oldest'], scale=60,
           binomial=False, expected='-', extra=1, notes='time-in-session check added after seeing X3')
    sp.run('X3-ex', 'log card deliberation net of reveal ~ exogenous arrivals prior 60 s (+ trend)', 'S-all', tk, 'lnet',
           'st_arr60_w + st_arr60_pm + %s + emin' % CS, 'st_arr60_w', centre=['st_arr60'],
           binomial=False, expected='-', extra=1, notes='exogenous-load check added after seeing X3')
    for code in ('S-v112', 'S-s1', 'S-27'):
        sp.run('X3', 'log card deliberation net of reveal ~ oldest waiting', code, c.samples(tk)[code], 'lnet',
               'st_oldest_w + st_oldest_pm + %s' % CS, 'st_oldest_w', centre=['st_oldest'], scale=60,
               binomial=False, expected='-', extra=1)
    return sp
