"""Workstream D (round 2) -- shared session-level table for the trust analyses.

Read-only over `Results/Participants/*.json` (through the round-1 loaders and study_analysis.load);
writes nothing. One row per (pid, run), P09 excluded, with:

  trust_s / trust_t   mean of the six 1-7 items of the post-session trust scale (builder's load_people)
  scenario, gameIndex, game ('strategic|1' ...), order (SF/TF), swapped, version, v112
  took                strategic card uptake (share of strategic choices that were a card)
  consult / accept    tactical: share of confirms where Suggest was pressed / kept unmodified
  recoveryUse         share of recovery episodes where Suggest was pressed (study_analysis)
  single_share        share of the session's strategic decisions (cards shown) on single-type missions
  odd_seen            decisions whose Conservative card padded a drone type the mission does not use
  dom_seen            decisions whose Conservative card was dominated (no fewer drones AND no faster)
  card_bad            card missions (allocation in force) that were abandoned or ended partial/none
  score metrics       scoreEff (score / points available; scale-free), z_game (rescaled score
                      standardised within each of the four games), bench_share (rescaled score /
                      near-perfect operator on that game; unreliable on tactical|2), best_share
                      (rescaled score / best human score on that game).
                      P01 and P02 ran on half task weights: their raw score is RESCALED x2 for
                      z_game, bench_share and best_share; scoreEff needs no rescale.
  took3               card uptake on three-type missions only (extra variant X2)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'scripts' / 'analysis_round1'))

import h5_h8_common as H  # noqa: E402
import h5_trust_drop as H5  # noqa: E402
import study_analysis as SA  # noqa: E402

HALF_WEIGHTS = {'P01', 'P02'}
SWAPPED = {'P31', 'P32', 'P33', 'P34', 'P35', 'P36'}


def _quiet(fn):
    return H.B._quietly(fn)


def build():
    """Return (sessions long table, decisions table from the builder, h5 decisions table)."""
    dec_h5 = H.decisions()                       # asserts identity with the builder's table
    dec_b = _quiet(H.B.load_decisions)           # carries `dominated`
    sess = H.sessions()
    sa_sessions, _, _ = _quiet(SA.load)
    sa = pd.DataFrame(sa_sessions)
    sa = sa[~sa.pid.isin(H.EXCLUDE)]

    # card missions failed (allocation in force; h5 rule)
    mis = H5.mission_level(dec_h5)
    mis['bad'] = mis.fate.isin(H.BAD_FATES).astype(int)
    card_bad = mis[mis.took == 1].groupby(['pid', 'run']).bad.sum()
    card_n = mis[mis.took == 1].groupby(['pid', 'run']).size()

    per = dec_b.groupby(['pid', 'run']).agg(
        ndec=('took', 'size'),
        single_share=('ncolours', lambda x: float((x == 1).mean())),
        odd_seen=('odd', 'sum'), dom_seen=('dominated', 'sum'))
    took3 = dec_b[dec_b.ncolours == 3].groupby(['pid', 'run']).took.mean().rename('took3')
    took1c = dec_b[dec_b.ncolours == 1].groupby(['pid', 'run']).took.mean().rename('took1c')

    S = sess[['pid', 'run', 'scenario', 'version', 'trust_s', 'trust_t', 'took', 'consult',
              'accept']].copy()
    S = S.merge(sa[['pid', 'run', 'gameIndex', 'game', 'swapped', 'order', 'score',
                    'availablePoints', 'scoreEff', 'recoveryUse']], on=['pid', 'run'], how='left')
    S = S.merge(per.reset_index(), on=['pid', 'run'], how='left')
    S = S.merge(took3.reset_index(), on=['pid', 'run'], how='left')
    S = S.merge(took1c.reset_index(), on=['pid', 'run'], how='left')
    S['card_bad'] = [int(card_bad.get((p, r), 0)) for p, r in zip(S.pid, S.run)]
    S['card_n'] = [int(card_n.get((p, r), 0)) for p, r in zip(S.pid, S.run)]

    # performance metrics
    S['score_r'] = S.score.astype(float) * np.where(S.pid.isin(HALF_WEIGHTS), 2.0, 1.0)
    S['z_game'] = S.groupby('game').score_r.transform(lambda x: (x - x.mean()) / x.std(ddof=1))
    bench = json.loads((ROOT / 'docs' / 'reports' / 'smart_benchmark.json').read_text('utf-8'))
    bkey = {'%s|%d' % (g['complexity'], g['planIndex']): g['score'] for g in bench['games']}
    S['bench_share'] = S.score_r / S.game.map(bkey)
    S['best_share'] = S.score_r / S.groupby('game').score_r.transform('max')

    v12 = H.v112plus(H.versions())
    S['v112'] = S.pid.isin(v12).astype(int)
    S['swapped'] = S.pid.isin(SWAPPED).astype(int)
    S['tac'] = (S.scenario == 'tactical').astype(int)
    S['idx2'] = (S.gameIndex == 2).astype(int)
    S['run2'] = (S.run == 2).astype(int)
    assert S.pid.nunique() == 33 and len(S) == 66, (S.pid.nunique(), len(S))
    assert S.trust_s.notna().all() and S.trust_t.notna().all()
    # swapped participants are exactly those whose game index differs from the run number
    assert set(S[S.gameIndex != S.run].pid) == SWAPPED
    return S, dec_b, dec_h5


def wide(S: pd.DataFrame) -> pd.DataFrame:
    """One row per person: <col>_1 / <col>_2 and differences d_<col> = run 2 - run 1."""
    cols = [c for c in S.columns if c not in ('pid', 'run', 'order', 'swapped', 'v112')]
    a = S[S.run == 1].set_index('pid')
    b = S[S.run == 2].set_index('pid')
    W = pd.DataFrame(index=a.index)
    W['order'], W['swapped'], W['v112'] = a.order, a.swapped, a.v112
    for c in cols:
        W[c + '_1'], W[c + '_2'] = a[c], b[c]
        if pd.api.types.is_numeric_dtype(a[c]):
            W['d_' + c] = b[c] - a[c]
    return W.reset_index()
