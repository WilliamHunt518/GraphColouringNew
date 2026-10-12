#!/usr/bin/env python3
"""Pass-2 analysis for the area "When the assistant gets it wrong" (AREA key `flaw`).

Read-only over Results/. Writes docs/analysis/register/pass2/flaw.json and prints every number the
findings quote. Run from the repo root:

    python scripts/register/pass2/flaw.py

Cards carried: flaw-odd-card, flaw-dots, flaw-anchors-null, flaw-abandon-caution, manual-card-error,
cards-dominated-null, meth-h8-invalid, tier-flaw-visibility, q-C12, q-C15.

What it does, in the order of the researcher's pass-1 questions:

1 · REBUILT EVENT STUDY on the first illogical strategy card. The old chart counted EVERY strategic
    decision for its x position and then kept only three-type missions for the rate, so a person only
    appeared at +k if their k-th decision after the card happened to be three-type -- n went up and
    down, rel 0 never appeared and "three-type 100%" was true by construction. Here a decision's
    position is counted WITHIN the sample being plotted (the 1st, 2nd, ... three-type decision after
    the anchor), positions are also binned (1-3, 4-6, 7-9, 10+), every bin gets a person-clustered
    bootstrap CI, and each person's own binned trajectory is kept for faint lines. Samples: three-type
    missions (never carry the flaw), all missions, and the illogical-card missions themselves.
2 · BEFORE vs AFTER per group (said they noticed / did not) with uncertainty, and the group x after
    interaction (did noticers drop MORE?). Raw (linear probability, practice + game held fixed) and
    adjusted (observed minus a model's expected value). Three nulls: a label permutation for the
    interaction, and a timing-matched random-anchor placebo per group.
3 · ROBUSTNESS STRIP: every specification tried, whatever it shows.
4 · THE ADJUSTMENT explained (the expected-value model's coefficients) and the two puzzles the
    researcher raised: the +8 dip and the not-said 100% plateau (who, how many, what missions).
5 · SPOKEN ANCHOR: lined up on the moment a person SAID, during play, that a card was wrong.
6 · REFUSAL ANCHORS (flaw-anchors-null check): does strategic use fall after the first Suggest refusal?
7 · DOMINATED CARDS and card previews (cards-dominated-null), manual-on-single-type (manual-card-error),
    and the strategic-vs-tactical flaw visibility counts (tier-flaw-visibility).
"""
from __future__ import annotations

import contextlib
import glob
import io
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

BASE = Path(__file__).resolve().parents[3]
for p in ('scripts', 'scripts/analysis_round1', 'scripts/analysis_round2', 'scripts/analysis_combined'):
    sys.path.insert(0, str(BASE / p))
warnings.filterwarnings('ignore')

import extras as x1        # noqa: E402  (SPOKEN_STRAT, SPOKEN_TAC, qualitative code matrix)
import extras2 as x2       # noqa: E402  (load, add_expected, anchors_from, the old event_study)

OUT = BASE / 'docs' / 'analysis' / 'register' / 'pass2' / 'flaw.json'
SEED = 20261012
B_BOOT = 2000
N_PLACEBO = 2000
N_PERM = 5000
BINS = [(-999, -1, 'before'), (0, 0, 'card'), (1, 3, '1–3'), (4, 6, '4–6'), (7, 9, '7–9'), (10, 999, '10+')]
BIN_KEYS = [b[2] for b in BINS]
HALF_WEIGHT = {'P01', 'P02'}


def hdr(s):
    print('\n' + '=' * 100 + '\n' + s + '\n' + '=' * 100)


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def r(x, d=4):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, d) if np.isfinite(x) else None


def wilson(k, n, z=1.96):
    if n == 0:
        return (None, None)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (r(c - h), r(c + h))


def kbin(k):
    for a, b, lab in BINS:
        if a <= k <= b:
            return lab
    return None


# ════════════════════════════════════════════════════════════════════════════════════════════
# data
# ════════════════════════════════════════════════════════════════════════════════════════════

def card_details():
    """Per strategic choice: both cards' true drone totals and displayed ETAs, from the LAST modal
    opening for that mission before the choice (a dismissed-and-reopened modal shows fresh cards)."""
    rows = []
    for path in sorted(glob.glob(str(x2.PARTS / 'P*.json'))):
        pid = Path(path).stem
        if pid in x2.EXCLUDE:
            continue
        log = json.loads(Path(path).read_text(encoding='utf-8'))
        for run, evs in enumerate(log['sessions'], start=1):
            last = {}
            for e in evs:
                if e['type'] == 'strategic_modal_opened':
                    # a reopening with no cards (as load_decisions does) keeps the previous cards
                    cards = {c['name']: c for c in e.get('strategiesPresented', [])}
                    if len(cards) >= 2:
                        last[e['missionId']] = cards
                elif e['type'] == 'strategic_choice' and e['missionId'] in last:
                    c = last[e['missionId']]
                    if 'Conservative' not in c or 'Aggressive' not in c:
                        continue
                    cs, ag = c['Conservative'], c['Aggressive']
                    rows.append(dict(pid=pid, run=run, missionId=e['missionId'], choice_ts=e['timestamp'],
                                     consN=sum(cs['trueAssets'].values()), aggrN=sum(ag['trueAssets'].values()),
                                     consEta=cs.get('displayedCompletionTime'), aggrEta=ag.get('displayedCompletionTime')))
    C = pd.DataFrame(rows)
    C['dom'] = ((C.consN >= C.aggrN) & (C.consEta >= C.aggrEta)).astype(int)
    return C


def load_all():
    S, T, eps, logs, _ = quiet(x2.load)
    S = S.sort_values(['pid', 'run', 't']).reset_index(drop=True)
    T = T.sort_values(['pid', 'run', 't']).reset_index(drop=True)
    S['tc'] = S.choice_ts / 1000.0
    T['tc'] = T.confirm_ts / 1000.0
    S['seq'] = S.groupby('pid').cumcount()
    T['seq'] = T.groupby('pid').cumcount()
    S['firstRun'] = (S.groupby(['pid', 'run']).cumcount() == 0).astype(int)
    S['three'] = (S.ncolours == 3).astype(int)
    S['cons'] = (S.choice == 'conservative').astype(int)
    S['aggr'] = (S.choice == 'aggressive').astype(int)
    S['manSeen'] = ((S.choice == 'manual') & (S.early == 0)).astype(int)
    S['manEarly'] = ((S.choice == 'manual') & (S.early == 1)).astype(int)
    # the expected-value model, refitted here (identical specification to extras2.add_expected) so its
    # coefficients can be shown; values are checked against extras2's own function below
    Sx, mS = expected(S, 'took', ('st_queued', 'residual'))
    chk = quiet(x2.add_expected, S.copy(), 'took', extra=('st_queued', 'residual'))
    assert np.allclose(Sx.exp.values, chk.exp.values), 'expected model drifted from extras2'
    Tx, mT = expected(T, 'consulted', ('st_queued',))
    C = card_details()
    Sx = Sx.merge(C[['pid', 'run', 'missionId', 'choice_ts', 'consN', 'aggrN', 'consEta', 'aggrEta', 'dom']],
                  on=['pid', 'run', 'missionId', 'choice_ts'], how='left')
    assert Sx.dom.notna().all(), 'card details missing for some decisions'
    return Sx, Tx, eps, logs, mS, mT


def expected(D, y, extra):
    D = D.copy()
    g = D.groupby('pid')[y]
    s, n = g.transform('sum'), g.transform('size')
    base = (s - D[y] + 1) / (n - 1 + 2)
    D['base'] = np.log(base / (1 - base))
    rhs = 'ndrones + ntasks + ncolours + emin + C(game) + base' + ''.join(' + ' + e for e in extra)
    d = D.dropna(subset=['ndrones', 'ntasks', 'ncolours', 'emin', y])
    m = smf.glm(f'{y} ~ {rhs}', d, family=sm.families.Binomial()).fit()
    D['exp'] = m.predict(D)
    D['res'] = D[y] - D['exp']
    return D, m


def groups():
    M = x1._qual_codes()
    c12 = set(M.index[M.C12 == 1])
    strict = {p for p, v in x1.SPOKEN_STRAT.items() if v[2]}
    broad = set(x1.SPOKEN_STRAT)
    narrated = sorted({Path(p).name[:-3] for p in glob.glob(str(BASE / 'Results' / 'Narration' / 'P*_s1'))
                       if (Path(p) / 'segments.json').exists()})
    return dict(M=M, c12=c12, strict=strict, broad=broad, said=c12 | strict, narrated=narrated)


# ════════════════════════════════════════════════════════════════════════════════════════════
# positions relative to an anchor
# ════════════════════════════════════════════════════════════════════════════════════════════

def place(D, anchors):
    """side = -1 before, 0 the decision open at the anchor moment, +1 after; and `cut`, the anchor's
    place in this table's own sequence (a decision's seq if one was open at the moment, else halfway
    between the last decision before and the first after) -- used by the timing-matched placebo."""
    D = D[D.pid.isin(anchors)].copy()
    side = []
    for p, ru, t, tc in zip(D.pid, D.run, D.t, D.tc):
        ar, at = anchors[p]
        if ru < ar or (ru == ar and tc < at):
            side.append(-1)
        elif ru > ar or (ru == ar and t > at):
            side.append(1)
        else:
            side.append(0)
    D['side'] = side
    cut = {}
    for p, g in D.groupby('pid'):
        z = g[g.side == 0]
        if len(z):
            cut[p] = float(z.seq.iloc[0])
        else:
            a = g[g.side == 1]
            cut[p] = float(a.seq.min()) - 0.5 if len(a) else float(g.seq.max()) + 0.5
    D['cut'] = D.pid.map(cut)
    return D


def number(D, mask):
    """k within the sample `mask`: 1, 2, ... after; -1, -2, ... before (counted back from the anchor);
    0 the anchor decision itself."""
    X = D[mask].copy()
    X['k'] = 0
    aft = X.side == 1
    X.loc[aft, 'k'] = X[aft].groupby('pid').cumcount() + 1
    bef = X.side == -1
    X.loc[bef, 'k'] = -(X[bef].iloc[::-1].groupby('pid').cumcount() + 1).iloc[::-1]
    X['bin'] = X.k.map(kbin)
    X['after'] = (X.side == 1).astype(int)
    return X


# ════════════════════════════════════════════════════════════════════════════════════════════
# estimates
# ════════════════════════════════════════════════════════════════════════════════════════════

def boot_bins(X, y, rng, bins=BIN_KEYS):
    """Per bin: n, people, raw rate, expected, adjusted (group mean + mean residual), with 95% CIs
    from resampling PEOPLE (so one heavy contributor cannot narrow the interval)."""
    pids = sorted(X.pid.unique())
    P, K = len(pids), len(bins)
    pi = {p: i for i, p in enumerate(pids)}
    bi = {b: j for j, b in enumerate(bins)}
    sy, sr, se, cn = (np.zeros((P, K)) for _ in range(4))
    for row in X[X.bin.isin(bins)].itertuples():
        i, j = pi[row.pid], bi[row.bin]
        sy[i, j] += getattr(row, y)
        sr[i, j] += row.res
        se[i, j] += row.exp
        cn[i, j] += 1
    grand = float(X[y].mean())
    draws = rng.integers(0, P, size=(B_BOOT, P))
    W = np.zeros((B_BOOT, P))
    for b in range(B_BOOT):
        W[b] = np.bincount(draws[b], minlength=P)
    by, br, bc = W @ sy, W @ sr, W @ cn
    with np.errstate(invalid='ignore', divide='ignore'):
        raw_b, adj_b = by / bc, grand + br / bc
    out = []
    for j, b in enumerate(bins):
        n = cn[:, j].sum()
        if n == 0:
            continue
        g = X[X.bin == b]
        out.append(dict(bin=b, n=int(n), people=int((cn[:, j] > 0).sum()),
                        raw=r(sy[:, j].sum() / n), rawLo=r(np.nanpercentile(raw_b[:, j], 2.5)),
                        rawHi=r(np.nanpercentile(raw_b[:, j], 97.5)),
                        exp=r(se[:, j].sum() / n),
                        adj=r(grand + sr[:, j].sum() / n), adjLo=r(np.nanpercentile(adj_b[:, j], 2.5)),
                        adjHi=r(np.nanpercentile(adj_b[:, j], 97.5)),
                        ndrones=r(g.ndrones.mean(), 2), ntasks=r(g.ntasks.mean(), 2), queue=r(g.st_queued.mean(), 2),
                        minute=r(g.t.mean() / 60, 2), session2=r((g.run == 2).mean(), 3)))
    people = []
    for p in pids:
        i = pi[p]
        people.append(dict(pid=p, raw={b: r(sy[i, j] / cn[i, j], 3) for j, b in enumerate(bins) if cn[i, j]},
                           n={b: int(cn[i, j]) for j, b in enumerate(bins) if cn[i, j]}))
    return dict(grand=r(grand), bins=out, persons=people)


def kseries(X, y, lo=-4, hi=15):
    out = []
    grand = X[y].mean()
    for k, g in X[(X.k >= lo) & (X.k <= hi)].groupby('k'):
        n = len(g)
        lo_, hi_ = wilson(int(g[y].sum()), n)
        out.append(dict(k=int(k), n=n, people=int(g.pid.nunique()), raw=r(g[y].mean()), lo=lo_, hi=hi_,
                        exp=r(g.exp.mean()), adj=r(grand + g.res.mean()),
                        ndrones=r(g.ndrones.mean(), 2), queue=r(g.st_queued.mean(), 2) if 'st_queued' in g else None,
                        minute=r(g.t.mean() / 60, 2), session2=r((g.run == 2).mean(), 3),
                        firstRun=r(g.firstRun.mean(), 3) if 'firstRun' in g else None))
    return out


def ols_cl(formula, d, term):
    m = smf.ols(formula, d).fit(cov_type='cluster', cov_kwds={'groups': pd.factorize(d.pid)[0]}, use_t=True)
    ci = m.conf_int().loc[term]
    return dict(est=r(m.params[term]), lo=r(ci[0]), hi=r(ci[1]), p=r(m.pvalues[term], 5))


def person_diffs(X, col):
    pp = X[X.k != 0].groupby(['pid', 'after'])[col].mean().unstack()
    if 0 not in pp or 1 not in pp:
        return pd.Series(dtype=float)
    return (pp[1] - pp[0]).dropna()


def prepost(X, y, seq=True, game=True):
    """Before vs after (anchor decision excluded). est = change in percentage points (as a share)."""
    d = X[X.k != 0].copy()
    if d.after.nunique() < 2 or d.pid.nunique() < 3:
        return None
    rhs = 'after' + (' + seq' if seq else '')
    out = dict(people=int(d.pid.nunique()), nBefore=int((d.after == 0).sum()), nAfter=int((d.after == 1).sum()),
               before=r(d[d.after == 0][y].mean()), after=r(d[d.after == 1][y].mean()),
               expBefore=r(d[d.after == 0].exp.mean()), expAfter=r(d[d.after == 1].exp.mean()))
    try:
        out['raw'] = ols_cl(f'{y} ~ {rhs}' + (' + C(game)' if game and d.game.nunique() > 1 else ''), d, 'after')
    except Exception:
        out['raw'] = None
    try:
        out['adj'] = ols_cl(f'res ~ {rhs}', d, 'after')
    except Exception:
        out['adj'] = None
    pdif = person_diffs(X, 'res')
    out.update(peopleBoth=int(len(pdif)), lower=int((pdif < 0).sum()), higher=int((pdif > 0).sum()),
               personAdjDiff=r(pdif.mean()))
    return out


def interaction(X, y, grp, seq=True):
    d = X[X.k != 0].copy()
    d['g'] = d.pid.isin(grp).astype(int)
    rhs = 'after * g' + (' + seq' if seq else '')
    o = {}
    try:
        o['raw'] = ols_cl(f'{y} ~ {rhs} + C(game)', d, 'after:g')
    except Exception:
        o['raw'] = None
    try:
        o['adj'] = ols_cl(f'res ~ {rhs}', d, 'after:g')
    except Exception:
        o['adj'] = None
    return o


def label_perm(X, grp, rng):
    """Shuffle the said / not-said labels across people; how often does a random split of the same
    people show as big a difference in (after - before) adjusted change? Exact for the interaction."""
    pdif = person_diffs(X, 'res')
    lab = np.array([p in grp for p in pdif.index])
    v = pdif.values
    obs = v[lab].mean() - v[~lab].mean()
    null = np.empty(N_PERM)
    for i in range(N_PERM):
        s = rng.permutation(lab)
        null[i] = v[s].mean() - v[~s].mean()
    return dict(obs=r(obs), nullLo=r(np.percentile(null, 2.5)), nullHi=r(np.percentile(null, 97.5)),
                p=r((1 + (np.abs(null) >= abs(obs)).sum()) / (1 + N_PERM), 4), nSaid=int(lab.sum()), nNot=int((~lab).sum()))


def placebo(X, col, rng, uniform=False, window=None):
    """Timing-matched placebo: each person's anchor moved to a cut drawn from the real cuts of the
    people in this analysis (so placebo anchors are as early or late as the real ones), keeping at
    least one sample decision each side. Statistic: mean over people of (after - before) of `col`."""
    G = {p: (g.seq.to_numpy(), g[col].to_numpy()) for p, g in X.groupby('pid')}
    cuts = X.groupby('pid').cut.first().to_numpy()

    def stat_for(cutmap):
        ds = []
        for p, (sq, v) in G.items():
            c = cutmap[p]
            b, a = v[sq < c], v[sq > c]
            if window:
                a = a[:window]
            if len(b) and len(a):
                ds.append(a.mean() - b.mean())
        return np.mean(ds) if ds else np.nan

    obs = stat_for(X.groupby('pid').cut.first().to_dict())
    null = []
    for _ in range(N_PLACEBO):
        cm = {}
        for p, (sq, v) in G.items():
            for _try in range(20):
                c = (rng.integers(sq.min(), sq.max()) + 0.5) if uniform else rng.choice(cuts)
                if (sq < c).any() and (sq > c).any():
                    break
            cm[p] = c
        null.append(stat_for(cm))
    null = np.array(null)
    null = null[np.isfinite(null)]
    return dict(obs=r(obs), mean=r(null.mean()), lo=r(np.percentile(null, 2.5)), hi=r(np.percentile(null, 97.5)),
                p=r((1 + (np.abs(null - null.mean()) >= abs(obs - null.mean())).sum()) / (1 + len(null)), 4))


# ════════════════════════════════════════════════════════════════════════════════════════════
# 1-3 · the illogical card
# ════════════════════════════════════════════════════════════════════════════════════════════

def odd_anchor(S, seen_only=False):
    od = S[(S.odd == 1) & ((S.early == 0) if seen_only else True)].sort_values(['pid', 'run', 't'])
    f = od.groupby('pid').head(1)
    return {p: (ru, t + 1e-3) for p, ru, t in zip(f.pid, f.run, f.t)}


def odd_study(Sx, Tx, G, rng):
    hdr('1 · Rebuilt event study on the first illogical card')
    A = odd_anchor(Sx)
    D = place(Sx, A)
    said, notsaid = G['said'], set(D.pid) - G['said']
    print('people with an illogical card: %d; said they noticed %d (C12 %d, in-play strict %d, overlap %d); not said %d'
          % (len(A), len(said & set(D.pid)), len(G['c12']), len(G['strict']), len(G['c12'] & G['strict']), len(notsaid)))
    # when is the anchor?
    anc = D[D.side == 0]
    pre3 = D[(D.side == -1) & (D.three == 1)].groupby('pid').size().reindex(sorted(A)).fillna(0)
    preAll = D[D.side == -1].groupby('pid').size().reindex(sorted(A)).fillna(0)
    timing = dict(medianSeq=r(anc.seq.median(), 1), inRun2=int((anc.run == 2).sum()),
                  medianMinute=r((anc.t / 60).median(), 2),
                  firstOrSecond=int((anc.seq <= 1).sum()),
                  pre3=dict(median=r(pre3.median(), 1), zero=int((pre3 == 0).sum()), le1=int((pre3 <= 1).sum())),
                  preAll=dict(median=r(preAll.median(), 1), zero=int((preAll == 0).sum())),
                  anchorChoice=anc.choice.value_counts().to_dict(), anchorEarly=int(anc.early.sum()),
                  perPerson=[dict(pid=p_, seq=int(sq) + 1, run=int(ru), said=int(p_ in said))
                             for p_, sq, ru in zip(anc.pid, anc.seq, anc.run)],
                  bySaid={g: dict(medianSeq=r(anc[anc.pid.isin(s)].seq.median(), 1),
                                  pre3=r(pre3[pre3.index.isin(s)].mean(), 2))
                          for g, s in (('said', said), ('notSaid', notsaid))})
    print('anchor = decision #%s in study order (median, 0-based); %d of 33 are the 1st or 2nd decision; %d in session 2'
          % (timing['medianSeq'], timing['firstOrSecond'], timing['inRun2']))
    print('three-type decisions before the anchor per person: median %s, %d people have none, %d have <= 1'
          % (timing['pre3']['median'], timing['pre3']['zero'], timing['pre3']['le1']))
    print('by group:', timing['bySaid'], '| choice at the anchor:', timing['anchorChoice'], 'pre-empted', timing['anchorEarly'])

    samples = {
        'three': D.three == 1,
        'all': pd.Series(True, index=D.index),
        'allNoOdd': (D.odd == 0) | (D.side == 0),
        'few': D.three == 0,
    }
    res = dict(timing=timing, saidPeople=sorted(said & set(D.pid)), notSaidPeople=sorted(notsaid))
    views = {}
    for sk in ('three', 'all'):
        X = number(D, samples[sk])
        views[sk] = {}
        for gk, gs in (('said', said), ('notSaid', notsaid)):
            Xg = X[X.pid.isin(gs)]
            Xp = Xg[Xg.k != 0]
            views[sk][gk] = dict(bins=boot_bins(Xg, 'took', rng), k=kseries(Xg, 'took'),
                                 test=prepost(Xg, 'took'), placebo=placebo(Xp, 'res', rng),
                                 placeboUniform=placebo(Xp, 'res', rng, uniform=True),
                                 placeboShort=placebo(Xp, 'res', rng, window=5),
                                 placeboShortUniform=placebo(Xp, 'res', rng, uniform=True, window=5))
            print('        placebos (obs, null mean, p): timing-matched %s | uniform %s | first-5 timing-matched %s | first-5 uniform %s'
                  % tuple((views[sk][gk][k_]['obs'], views[sk][gk][k_]['mean'], views[sk][gk][k_]['p'])
                          for k_ in ('placebo', 'placeboUniform', 'placeboShort', 'placeboShortUniform')))
        views[sk]['interaction'] = interaction(X, 'took', said)
        views[sk]['perm'] = label_perm(X, said, rng)
        for gk in ('said', 'notSaid'):
            t_ = views[sk][gk]['test']
            print('%-6s %-8s %2d people  before %.2f (n %d) -> after %.2f (n %d) | expected %.2f -> %.2f | raw %+.3f [%+.3f, %+.3f] p %.3f | adj %+.3f [%+.3f, %+.3f] p %.3f | %d fell %d rose | placebo p %s'
                  % (sk, gk, t_['people'], t_['before'], t_['nBefore'], t_['after'], t_['nAfter'], t_['expBefore'], t_['expAfter'],
                     t_['raw']['est'], t_['raw']['lo'], t_['raw']['hi'], t_['raw']['p'],
                     t_['adj']['est'], t_['adj']['lo'], t_['adj']['hi'], t_['adj']['p'], t_['lower'], t_['higher'],
                     views[sk][gk]['placebo']['p']))
            print('        bins:', [(b['bin'], b['n'], b['people'], b['raw'], b['adj'], (b['adjLo'], b['adjHi'])) for b in views[sk][gk]['bins']['bins']])
        it, pm = views[sk]['interaction'], views[sk]['perm']
        print('%-6s interaction (said minus not-said change): raw %+.3f [%+.3f, %+.3f] p %.3f | adj %+.3f [%+.3f, %+.3f] p %.3f | label permutation obs %+.3f p %.3f'
              % (sk, it['raw']['est'], it['raw']['lo'], it['raw']['hi'], it['raw']['p'],
                 it['adj']['est'], it['adj']['lo'], it['adj']['hi'], it['adj']['p'], pm['obs'], pm['p']))
    res['views'] = views
    # OR for continuity with the old card (logistic GEE, three-type, practice + game)
    X3 = number(D, samples['three'])
    ors = {}
    for gk, gs in (('said', said), ('notSaid', notsaid)):
        d = X3[(X3.k != 0) & X3.pid.isin(gs)]
        try:
            ors[gk] = x2.orow(x2.gee('took ~ after + seq + C(game)', d), 'after')
        except Exception:
            ors[gk] = None
    res['oddsRatios'] = ors
    print('three-type odds ratios (GEE):', ors)

    # ---- the illogical-card missions themselves -------------------------------------------------
    O = D[D.odd == 1].copy()
    O['j'] = O.groupby('pid').cumcount() + 1
    O['jb'] = pd.cut(O.j, [0, 1, 3, 6, 99], labels=['1st', '2nd–3rd', '4th–6th', '7th+']).astype(str)
    oddv = {}
    for gk, gs in (('said', said), ('notSaid', notsaid)):
        g = O[O.pid.isin(gs)]
        rows = []
        for b in ['1st', '2nd–3rd', '4th–6th', '7th+']:
            h = g[g.jb == b]
            if not len(h):
                continue
            rows.append(dict(bin=b, n=int(len(h)), people=int(h.pid.nunique()),
                             cons=r(h.cons.mean()), aggr=r(h.aggr.mean()), manSeen=r(h.manSeen.mean()),
                             manEarly=r(h.manEarly.mean()), took=r(h.took.mean()),
                             consCI=boot_rate(h, 'cons', rng), tookCI=boot_rate(h, 'took', rng),
                             manEarlyCI=boot_rate(h, 'manEarly', rng), manSeenCI=boot_rate(h, 'manSeen', rng)))
        oddv[gk] = dict(rows=rows, n=int(len(g)), people=int(g.pid.nunique()))
    O['later'] = (O.j > 1).astype(int)
    O['g'] = O.pid.isin(said).astype(int)
    oddtests = {}
    for yk in ('cons', 'took', 'manSeen'):
        try:
            oddtests[yk] = dict(interaction=ols_cl(f'{yk} ~ later * g + C(game)', O, 'later:g'),
                                said=ols_cl(f'{yk} ~ later + C(game)', O[O.g == 1], 'later'),
                                notSaid=ols_cl(f'{yk} ~ later + C(game)', O[O.g == 0], 'later'))
        except Exception as ex:
            oddtests[yk] = dict(error=str(ex))
    O['jc'] = O.j.clip(upper=7)
    for yk in ('cons', 'took', 'manEarly', 'manSeen'):
        oddtests.setdefault(yk, {})
        try:
            oddtests[yk]['trend'] = dict(interaction=ols_cl(f'{yk} ~ jc * g + C(game)', O, 'jc:g'),
                                         said=ols_cl(f'{yk} ~ jc + C(game)', O[O.g == 1], 'jc'),
                                         notSaid=ols_cl(f'{yk} ~ jc + C(game)', O[O.g == 0], 'jc'))
        except Exception as ex:
            oddtests[yk]['trend'] = dict(error=str(ex))
    from scipy.stats import mannwhitneyu
    pp = O.groupby(['pid', 'g'])[['cons', 'took', 'manEarly', 'manSeen']].mean().reset_index()
    oddv['personLevel'] = {yk: dict(said=r(pp[pp.g == 1][yk].mean()), notSaid=r(pp[pp.g == 0][yk].mean()),
                                    p=r(mannwhitneyu(pp[pp.g == 1][yk], pp[pp.g == 0][yk]).pvalue, 4),
                                    neverSaid=int((pp[pp.g == 1][yk] == 0).sum()), neverNot=int((pp[pp.g == 0][yk] == 0).sum()))
                           for yk in ('cons', 'took', 'manEarly', 'manSeen')}
    print('  per-step trend (pp per extra illogical card; said / not / difference p):',
          {k: (v['trend'].get('said', {}).get('est'), v['trend'].get('notSaid', {}).get('est'),
               v['trend'].get('interaction', {}).get('p')) for k, v in oddtests.items()})
    print('  person-level means on illogical-card missions:', oddv['personLevel'])
    oddv['tests'] = oddtests
    oddv['overall'] = {gk: dict(cons=r(O[O.g == gi].cons.mean()), took=r(O[O.g == gi].took.mean()),
                                manSeen=r(O[O.g == gi].manSeen.mean()), manEarly=r(O[O.g == gi].manEarly.mean()),
                                n=int((O.g == gi).sum()))
                       for gk, gi in (('said', 1), ('notSaid', 0))}
    res['oddMissions'] = oddv
    print('illogical-card missions, per group and ordinal:')
    for gk in ('said', 'notSaid'):
        print('  ', gk, [(x['bin'], x['n'], x['cons'], x['aggr'], x['manSeen'], x['manEarly']) for x in oddv[gk]['rows']])
    print('  later-vs-first change (said / not / interaction):',
          {k: (v.get('said', {}).get('est'), v.get('notSaid', {}).get('est'), v.get('interaction', {}).get('est'),
               v.get('interaction', {}).get('p')) for k, v in oddtests.items()})

    # tactical Suggest after the first illogical card (does a strategic flaw spill down a tier?)
    DT = place(Tx, A)
    XT = number(DT, pd.Series(True, index=DT.index))
    res['tacticalAfterOdd'] = dict(test=prepost(XT, 'consulted', game=False), placebo=placebo(XT[XT.k != 0], 'res', rng))
    print('tactical Suggest after the first illogical card:', res['tacticalAfterOdd']['test']['adj'])
    return res, D


def boot_rate(h, col, rng, B=1000):
    pids = h.pid.unique()
    gs = {p: h[h.pid == p][col].to_numpy() for p in pids}
    vals = []
    for _ in range(B):
        sm_ = [gs[p] for p in rng.choice(pids, len(pids))]
        a = np.concatenate(sm_)
        vals.append(a.mean())
    return [r(np.percentile(vals, 2.5)), r(np.percentile(vals, 97.5))]


def robustness(Sx, G, rng):
    hdr('3 · Robustness strip: every specification of "did uptake change after the first illogical card?"')
    said_sets = dict(main=G['said'], c12=G['c12'], spokenBroad=G['c12'] | G['broad'])
    specs = []

    def run(label, family, D, mask, y='took', grp=G['said'], seq=True, kfilter=None):
        X = number(D, mask)
        if kfilter is not None:
            X = X[kfilter(X)]
        row = dict(label=label, family=family)
        for gk, gs in (('said', grp), ('notSaid', set(D.pid) - grp)):
            Xg = X[X.pid.isin(gs)]
            t_ = prepost(Xg, y, seq=seq)
            row[gk] = None if t_ is None else dict(raw=t_['raw'], adj=t_['adj'], people=t_['people'],
                                                   peopleBoth=t_['peopleBoth'], nBefore=t_['nBefore'], nAfter=t_['nAfter'],
                                                   before=t_['before'], after=t_['after'])
        row['thin'] = any(row[g] is None or row[g]['peopleBoth'] < 6 for g in ('said', 'notSaid'))
        it = interaction(X, y, grp, seq=seq)
        row['diff'] = it
        specs.append(row)
        a = lambda z: 'NA' if not z else '%+.3f [%+.3f, %+.3f] p %.3f' % (z['est'], z['lo'], z['hi'], z['p'])
        print(('THIN ' if row['thin'] else '') + '%-58s said adj %s | not adj %s | diff adj %s | diff raw %s'
              % (label, a(row['said'] and row['said']['adj']), a(row['notSaid'] and row['notSaid']['adj']),
                 a(it.get('adj')), a(it.get('raw'))))

    A = odd_anchor(Sx)
    D = place(Sx, A)
    three = D.three == 1
    run('Main: three-type missions, all later decisions', 'Main', D, three)
    run('No practice term (seq dropped)', 'Model', D, three, seq=False)
    run('Short run: first 5 three-type decisions after', 'Window', D, three, kfilter=lambda X: X.k <= 5)
    run('Long run: 6th three-type decision after onwards', 'Window', D, three, kfilter=lambda X: (X.k < 0) | (X.k >= 6))
    run('All missions', 'Sample', D, pd.Series(True, index=D.index))
    run('All missions except illogical-card ones', 'Sample', D, (D.odd == 0) | (D.side == 0))
    run('Single/two-type missions only (where the flaw appears)', 'Sample', D, D.three == 0)
    run('Residual missions dropped', 'Sample', D, three & (D.residual == 0))
    run('First decision of each session dropped', 'Sample', D, three & (D.firstRun == 0))
    Dh = D[~D.pid.isin(HALF_WEIGHT)]
    run('P01, P02 (half task weights) dropped', 'Sample', Dh, Dh.three == 1)
    As = odd_anchor(Sx, seen_only=True)
    Ds = place(Sx, As)
    run('Anchor = first illogical card actually displayed (not pre-empted)', 'Anchor', Ds, Ds.three == 1)
    run('Noticed = debrief/interview code C12 only', 'Grouping', D, three, grp=said_sets['c12'])
    run('Noticed = C12 or ANY in-play remark (broad)', 'Grouping', D, three, grp=said_sets['spokenBroad'])
    run('Noticed = in-play remark (strict) only', 'Grouping', D, three, grp=G['strict'])
    return specs


# ════════════════════════════════════════════════════════════════════════════════════════════
# 4 · the adjustment, the old dots, +8 and the not-said plateau
# ════════════════════════════════════════════════════════════════════════════════════════════

def explain_model(mS, Sx):
    hdr('4a · The expected-value model (what "expected" and "adjusted" mean)')
    names = dict(ndrones='each extra drone the mission needs', ntasks='each extra task', ncolours='each extra drone type needed',
                 emin='each minute later in the session', st_queued='each other mission waiting in the queue',
                 residual='a residual (re-queued) mission', base='the person\'s own rate on their other decisions (per logit unit)')
    rows = []
    ci = mS.conf_int()
    for k, lab in names.items():
        rows.append(dict(term=k, label=lab, b=r(mS.params[k]), lo=r(ci.loc[k, 0]), hi=r(ci.loc[k, 1]),
                         p=r(mS.pvalues[k], 5), OR=r(np.exp(mS.params[k]), 3)))
        print('  %-55s OR %.2f [%.2f, %.2f] p %.4f' % (lab, np.exp(mS.params[k]), np.exp(ci.loc[k, 0]), np.exp(ci.loc[k, 1]), mS.pvalues[k]))
    games = {k: r(np.exp(v), 3) for k, v in mS.params.items() if k.startswith('C(game)')}
    # how much the model knows: correlation of expected with observed, and with the person term alone
    from scipy.stats import pearsonr
    auc = auc_score(Sx.took.values, Sx.exp.values)
    print('  game ORs vs the reference game:', games, '| AUC of expected vs observed %.3f' % auc)
    # a worked example: one real decision
    ex = Sx.iloc[int(np.argmin(np.abs(Sx.exp - 0.6)))]
    worked = dict(pid=ex.pid, run=int(ex.run), ndrones=int(ex.ndrones), ntasks=int(ex.ntasks), ncolours=int(ex.ncolours),
                  minute=r(ex.emin, 2), queued=int(ex.st_queued), personRate=r(1 / (1 + np.exp(-ex.base)), 3),
                  expected=r(ex.exp, 3), took=int(ex.took), res=r(ex.res, 3))
    return dict(terms=rows, games=games, auc=r(auc, 3), worked=worked, n=int(mS.nobs))


def auc_score(y, s):
    y = np.asarray(y)
    s = np.asarray(s)
    pos, neg = s[y == 1], s[y == 0]
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))


def old_dots(Sx, G, D):
    """Reproduce the old chart's dots exactly (extras2.event_study), then take them apart."""
    hdr('4b · The old chart: why n moves, the not-said 100% plateau, and the +8 dip')
    A = odd_anchor(Sx)
    Sx3 = Sx.copy()
    old = {}
    for gk, gs in (('said', G['said']), ('notSaid', set(A) - G['said'])):
        e = quiet(x2.event_study, Sx3[Sx3.pid.isin(gs)], 'took', A, lo=-6, minn=4, placebo=False, subset='three')
        old[gk] = e['series']
    # check against the published numbers
    try:
        pub = json.loads((BASE / 'docs/analysis/combined/extras2.json').read_text(encoding='utf-8'))['events']['oddSplit']
        same = all(abs(a['rate'] - b['rate']) < 1e-3 and a['n'] == b['n'] and a['rel'] == b['rel']
                   for gk in ('said', 'notSaid') for a, b in zip(old[gk], pub[gk]['series']))
        print('old dots reproduce the published extras2.json:', same)
    except Exception as ex:
        same = None
        print('could not compare with extras2.json:', ex)
    # what the old x position meant: rel counted ALL decisions; how many of the people at each rel had a
    # three-type mission there
    Dall = D.copy()
    fa = Dall[Dall.side == 1].groupby('pid').seq.min()
    Dall['rel'] = Dall.seq - Dall.pid.map(fa) + 1
    comp = []
    for rel in range(-6, 13):
        g = Dall[Dall.rel == rel]
        comp.append(dict(rel=rel, peopleAtRel=int(g.pid.nunique()), threeType=int(g.three.sum())))
    # z-score per dot: (sum observed - sum expected) / sqrt(sum p(1-p)); with ~30 dots one or two beyond 2 is expected
    zs = []
    for gk, gs in (('said', G['said']), ('notSaid', set(A) - G['said'])):
        g3 = Dall[Dall.pid.isin(gs) & (Dall.three == 1)]
        for rel, g in g3[(g3.rel >= -6) & (g3.rel <= 12)].groupby('rel'):
            if len(g) < 4:
                continue
            z = (g.took.sum() - g.exp.sum()) / np.sqrt((g.exp * (1 - g.exp)).sum())
            zs.append(dict(group=gk, rel=int(rel), n=int(len(g)), raw=r(g.took.mean()), exp=r(g.exp.mean()), z=r(z, 2)))
    Z = pd.DataFrame(zs)
    print('dots beyond |z| > 1.96: %d of %d (about %.1f expected by chance)' % ((Z.z.abs() > 1.96).sum(), len(Z), 0.05 * len(Z)))
    print(Z[Z.z.abs() > 1.5].to_string(index=False))
    # the +8 dip, row by row
    g8 = Dall[(Dall.rel == 8) & (Dall.three == 1)].copy()
    g8['group'] = np.where(g8.pid.isin(G['said']), 'said', 'notSaid')
    rows8 = g8[['group', 'pid', 'run', 't', 'ndrones', 'ntasks', 'st_queued', 'firstRun', 'choice', 'took', 'exp']].copy()
    rows8['minute'] = (rows8.t / 60).round(2)
    allthree = Dall[(Dall.three == 1) & (Dall.rel >= 1)]
    same_people = allthree[allthree.pid.isin(g8.pid) & (allthree.rel != 8)]
    dip = dict(n=int(len(g8)), took=r(g8.took.mean()), exp=r(g8.exp.mean()),
               ndrones=r(g8.ndrones.mean(), 2), vsAfter=r(allthree.ndrones.mean(), 2),
               queue=r(g8.st_queued.mean(), 2), queueAfter=r(allthree.st_queued.mean(), 2),
               firstRun=r(g8.firstRun.mean(), 3), firstRunAfter=r(allthree.firstRun.mean(), 3),
               minute=r((g8.t / 60).mean(), 2), minuteAfter=r((allthree.t / 60).mean(), 2),
               samePeopleElsewhere=r(same_people.took.mean()), samePeopleElsewhereN=int(len(same_people)),
               declined=int((g8.took == 0).sum()), declinedPeople=sorted(g8[g8.took == 0].pid.tolist()),
               rows=[{k: (r(v, 3) if isinstance(v, (float, np.floating)) else (int(v) if isinstance(v, (np.integer,)) else v))
                      for k, v in rr.items()} for rr in rows8.drop(columns='t').to_dict('records')])
    print('+8: %d decisions, took %.2f vs expected %.2f; drones %.1f (all later three-type %.1f); queue %.1f (%.1f); first-of-session %.2f (%.2f); minute %.1f (%.1f); the same people on their other later three-type decisions took %.2f (n %d)'
          % (dip['n'], dip['took'], dip['exp'], dip['ndrones'], dip['vsAfter'], dip['queue'], dip['queueAfter'], dip['firstRun'],
             dip['firstRunAfter'], dip['minute'], dip['minuteAfter'], dip['samePeopleElsewhere'], dip['samePeopleElsewhereN']))
    print('   declined at +8:', dip['declinedPeople'])
    # the not-said +2/+3 dots
    ns = Dall[~Dall.pid.isin(G['said']) & (Dall.three == 1) & Dall.rel.isin([2, 3])]
    plateau = dict(pAll=r(float(np.prod(ns.exp))), n=int(len(ns)), people=sorted(ns.pid.unique().tolist()), took=r(ns.took.mean()), exp=r(ns.exp.mean()),
                   queue=r(ns.st_queued.mean(), 2), ndrones=r(ns.ndrones.mean(), 2))
    print('not-said +2/+3 dots: %d decisions from %s; all took a card; expected %.2f (chance all take one: %.3f); queue %.1f; drones %.1f'
          % (plateau['n'], plateau['people'], plateau['exp'], plateau['pAll'], plateau['queue'], plateau['ndrones']))
    return dict(reproduced=same, old=old, composition=comp, z=zs, dip8=dip, plateau=plateau)


def people_profile(Sx, Tx, G, D):
    hdr('4c · Are the people who never said it simply high-reliance people?')
    A = odd_anchor(Sx)
    rows = []
    for p in sorted(A):
        s = Sx[Sx.pid == p]
        d = D[D.pid == p]
        t = Tx[Tx.pid == p]
        pre3 = d[(d.side == -1) & (d.three == 1)]
        rows.append(dict(pid=p, said=int(p in G['said']), c12=int(p in G['c12']), spoken=int(p in G['broad']),
                         narrated=int(p in G['narrated']), took=r(s.took.mean(), 3), took3=r(s[s.three == 1].took.mean(), 3),
                         tookFew=r(s[s.three == 0].took.mean(), 3), pre3=r(pre3.took.mean(), 3) if len(pre3) else None,
                         nPre3=int(len(pre3)), suggest=r(t.consulted.mean(), 3), manEarly=r(s.manEarly.mean(), 3),
                         nOdd=int(s.odd.sum()), n=int(len(s))))
    P = pd.DataFrame(rows)
    from scipy.stats import mannwhitneyu
    comp = {}
    for k in ('took', 'took3', 'tookFew', 'pre3', 'suggest', 'manEarly', 'nOdd'):
        a, b = P[P.said == 1][k].dropna(), P[P.said == 0][k].dropna()
        u = mannwhitneyu(a, b) if len(a) > 2 and len(b) > 2 else None
        comp[k] = dict(said=r(a.mean(), 3), notSaid=r(b.mean(), 3), saidMed=r(a.median(), 3), notSaidMed=r(b.median(), 3),
                       nSaid=int(len(a)), nNot=int(len(b)), p=r(u.pvalue, 4) if u else None)
        print('  %-9s said mean %.2f (median %.2f, n %d) vs not said %.2f (%.2f, n %d)  Mann-Whitney p %s'
              % (k, a.mean(), a.median(), len(a), b.mean(), b.median(), len(b), comp[k]['p']))
    nar = P[P.said == 0]
    print('  of the %d who never said it, %d had in-play narration recorded' % (len(nar), nar.narrated.sum()))
    return dict(people=rows, compare=comp, notSaidNarrated=int(nar.narrated.sum()), notSaidN=int(len(nar)))


# ════════════════════════════════════════════════════════════════════════════════════════════
# 5 · lined up on the spoken moment
# ════════════════════════════════════════════════════════════════════════════════════════════

def spoken(Sx, G, rng):
    hdr('5 · Lined up on the moment the person SAID, during play, that a card was wrong')
    A, snapped = {}, {}
    for p, v in x1.SPOKEN_STRAT.items():
        if p not in set(Sx.pid):
            continue
        ru, t = v[0], v[1]
        s_ = Sx[(Sx.pid == p) & (Sx.run == ru)]
        covering = s_[(s_.t <= t) & (s_.tc >= t)]
        soon = s_[(s_.t > t) & (s_.t <= t + 8)]
        # only onto an ILLOGICAL card: the remark is about one, so a clean card opening next is not it
        if not len(covering) and len(soon) and soon.odd.iloc[0] == 1:
            snapped[p] = r(soon.t.iloc[0] - t, 1)
            t = float(soon.t.iloc[0]) + 1e-3
        A[p] = (ru, t)
    print('  remarks moved onto an illogical card that opened within 8 s after them (narration timing tolerance):', snapped)
    D = place(Sx, A)
    rows = []
    for p, (ru, t) in sorted(A.items()):
        d = D[D.pid == p]
        on = d[d.side == 0]
        prev_odd = d[(d.side <= 0) & (d.odd == 1)]
        # the decision on screen, or else the last before it
        ref = on.iloc[0] if len(on) else (d[d.side == -1].iloc[-1] if (d.side == -1).any() else None)
        b3, a3 = d[(d.side == -1) & (d.three == 1)], d[(d.side == 1) & (d.three == 1)]
        bA, aA = d[d.side == -1], d[d.side == 1]
        rows.append(dict(pid=p, run=ru, t=r(x1.SPOKEN_STRAT[p][1], 1), snapped=snapped.get(p), strict=bool(x1.SPOKEN_STRAT[p][2]), gist=x1.SPOKEN_STRAT[p][3],
                         onScreen=bool(len(on)), refOdd=None if ref is None else int(ref.odd),
                         refColours=None if ref is None else int(ref.ncolours),
                         refChoice=None if ref is None else ref.choice,
                         oddSeenBefore=int(len(prev_odd)),
                         firstOddSeq=r(d[d.odd == 1].seq.min(), 0), saidSeq=r(d.cut.iloc[0], 1),
                         before3=r(b3.took.mean(), 3), nBefore3=int(len(b3)), after3=r(a3.took.mean(), 3), nAfter3=int(len(a3)),
                         beforeAll=r(bA.took.mean(), 3), nBeforeAll=int(len(bA)), afterAll=r(aA.took.mean(), 3), nAfterAll=int(len(aA)),
                         adjBefore3=r(b3.res.mean(), 3), adjAfter3=r(a3.res.mean(), 3),
                         adjBeforeAll=r(bA.res.mean(), 3), adjAfterAll=r(aA.res.mean(), 3)))
        x = rows[-1]
        print('  %s s%d %5.0fs %-6s on-screen card %s (odd %s, %s types, chose %s); %d odd cards seen first | three-type %s (n %d) -> %s (n %d) | all %s (n %d) -> %s (n %d)'
              % (p, ru, t, 'strict' if x['strict'] else 'broad', x['onScreen'], x['refOdd'], x['refColours'], x['refChoice'],
                 x['oddSeenBefore'], x['before3'], x['nBefore3'], x['after3'], x['nAfter3'], x['beforeAll'], x['nBeforeAll'],
                 x['afterAll'], x['nAfterAll']))
    out = dict(people=rows)
    for setk, ps in (('strict', G['strict']), ('broad', G['broad'])):
        out[setk] = {}
        for sk, mask in (('three', D.three == 1), ('all', pd.Series(True, index=D.index))):
            X = number(D[D.pid.isin(ps)], mask[D.pid.isin(ps)])
            t_ = prepost(X, 'took')
            out[setk][sk] = dict(test=t_, bins=boot_bins(X, 'took', rng), placebo=placebo(X[X.k != 0], 'res', rng))
            if t_:
                print('  %-6s %-5s %d people: before %.2f (n %d) -> after %.2f (n %d) | raw %+.3f [%+.3f, %+.3f] p %.3f | adj %+.3f [%+.3f, %+.3f] p %.3f | %d fell %d rose | placebo p %s'
                      % (setk, sk, t_['people'], t_['before'], t_['nBefore'], t_['after'], t_['nAfter'],
                         t_['raw']['est'], t_['raw']['lo'], t_['raw']['hi'], t_['raw']['p'],
                         t_['adj']['est'], t_['adj']['lo'], t_['adj']['hi'], t_['adj']['p'], t_['lower'], t_['higher'],
                         out[setk][sk]['placebo']['p']))
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
# 6 · refusal anchors (flaw-anchors-null)
# ════════════════════════════════════════════════════════════════════════════════════════════

def refusal_anchors(Sx, Tx, eps, logs, rng):
    hdr('6 · After the first Suggest refusal: does STRATEGIC use fall? (and the wrong-refusal anchor)')
    A = quiet(x2.anchors_from, eps, logs, Sx)
    out = {}
    for ak in ('refusal', 'blind', 'failure'):
        anc = A[ak]
        out[ak] = dict(label=x2.ANCHOR_LABEL[ak], people=len(anc))
        DS, DT = place(Sx, anc), place(Tx, anc)
        for ok, D, y, mask in (('strategicAll', DS, 'took', pd.Series(True, index=DS.index)),
                               ('strategic3', DS, 'took', DS.three == 1),
                               ('tactical', DT, 'consulted', pd.Series(True, index=DT.index))):
            X = number(D, mask)
            t_ = prepost(X, y, game=(ok != 'tactical'))
            pl = placebo(X[X.k != 0], 'res', rng)
            out[ak][ok] = dict(test=t_, bins=boot_bins(X, y, rng), placebo=pl)
            print('  %-8s %-12s %2d people: %.2f (n %d) -> %.2f (n %d) | expected %.2f -> %.2f | raw %+.3f [%+.3f, %+.3f] p %.3f | adj %+.3f [%+.3f, %+.3f] p %.3f | %d fell %d rose | placebo obs %+.3f vs %+.3f p %s'
                  % (ak, ok, t_['people'], t_['before'], t_['nBefore'], t_['after'], t_['nAfter'], t_['expBefore'], t_['expAfter'],
                     t_['raw']['est'], t_['raw']['lo'], t_['raw']['hi'], t_['raw']['p'],
                     t_['adj']['est'], t_['adj']['lo'], t_['adj']['hi'], t_['adj']['p'], t_['lower'], t_['higher'],
                     pl['obs'], pl['mean'], pl['p']))
    # the abandon anchor, recorded only so the pruned card's retirement line can quote it
    ab = x2.ANCHOR_LABEL['abandon']
    DS = place(Sx, A['abandon'])
    X = number(DS, DS.three == 1)
    t_ = prepost(X, 'took')
    out['abandon3'] = dict(label=ab, people=len(A['abandon']), test=t_, placebo=placebo(X[X.k != 0], 'res', rng))
    print('  abandon  strategic3   %d people: adj %+.3f p %.3f; placebo p %s'
          % (t_['people'], t_['adj']['est'], t_['adj']['p'], out['abandon3']['placebo']['p']))
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
# 7 · dominated cards, previews, manual on single-type, visibility
# ════════════════════════════════════════════════════════════════════════════════════════════

def dominated(Sx, rng):
    hdr('7a · Dominated Conservative cards and previewing both cards')
    chk = quiet(__import__('build_findings_synthesis').load_decisions)
    print('dominated rate here %.3f vs load_decisions %.3f' % (Sx.dom.mean(), chk.dominated.mean()))
    out = dict(rate=r(Sx.dom.mean()), byTypes={int(k): dict(n=int(len(g)), dom=r(g.dom.mean()), odd=r(g.odd.mean()))
                                               for k, g in Sx.groupby('ncolours')})
    d3 = Sx[(Sx.three == 1) & (Sx.residual == 0)].copy()
    rows = []
    for dk, g in d3.groupby('dom'):
        rows.append(dict(dom=int(dk), n=int(len(g)), people=int(g.pid.nunique()),
                         cons=r(g.cons.mean()), consCI=boot_rate(g, 'cons', rng), aggr=r(g.aggr.mean()), aggrCI=boot_rate(g, 'aggr', rng),
                         man=r((g.choice == 'manual').mean()), manCI=boot_rate(g.assign(man=(g.choice == 'manual').astype(int)), 'man', rng),
                         consN=r(g.consN.mean(), 2), aggrN=r(g.aggrN.mean(), 2),
                         consEta=r(g.consEta.mean(), 1), aggrEta=r(g.aggrEta.mean(), 1)))
    out['three'] = rows
    try:
        out['model'] = x2.orow(x2.gee('cons ~ dom + ndrones + ntasks + C(game)', d3), 'dom')
    except Exception:
        out['model'] = None
    seen = d3[d3.early == 0]
    try:
        out['modelSeen'] = x2.orow(x2.gee('cons ~ dom + ndrones + ntasks + C(game)', seen), 'dom')
    except Exception:
        out['modelSeen'] = None
    ex = d3[d3.dom == 1].iloc[len(d3[d3.dom == 1]) // 2]
    out['example'] = dict(consN=int(ex.consN), aggrN=int(ex.aggrN), consEta=r(ex.consEta, 1), aggrEta=r(ex.aggrEta, 1), ndrones=int(ex.ndrones))
    print('three-type, non-residual: ', rows)
    print('Conservative ~ dominated OR', out['model'], '| cards seen only', out['modelSeen'])
    # previews: distinct cards highlighted before the choice
    pv = Sx.previews.clip(upper=2).value_counts().sort_index()
    took = Sx[Sx.took == 1].previews.clip(upper=2).value_counts().sort_index()
    out['previews'] = dict(all={int(k): int(v) for k, v in pv.items()}, cardTaken={int(k): int(v) for k, v in took.items()},
                           n=int(len(Sx)), nTook=int(Sx.took.sum()), both=int((Sx.previews >= 2).sum()),
                           bothPeople=int(Sx[Sx.previews >= 2].pid.nunique()))
    print('previews (distinct cards highlighted) all decisions:', out['previews'])
    return out


def manual_single(Sx, G, D):
    hdr('7b · Manual allocation on single-type missions, by whether the person said they noticed')
    d = Sx[(Sx.residual == 0) & (Sx.ncolours.isin([1, 3]))].copy()
    d['single'] = (d.ncolours == 1).astype(int)
    d['man'] = (d.choice == 'manual').astype(int)
    out = {}
    for gk, gs in (('main', G['said']), ('c12', G['c12'])):
        d['g'] = d.pid.isin(gs).astype(int)
        o = {}
        try:
            o['single'] = x2.orow(x2.gee('man ~ g + C(game)', d[d.single == 1]), 'g')
            o['three'] = x2.orow(x2.gee('man ~ g + C(game)', d[d.single == 0]), 'g')
            o['interaction'] = x2.orow(x2.gee('man ~ g * single + C(game)', d), 'g:single')
        except Exception as ex:
            o['error'] = str(ex)
        o['rates'] = {f'{a}_{b}': r(d[(d.g == gi) & (d.single == si)].man.mean(), 3)
                      for a, gi in (('said', 1), ('not', 0)) for b, si in (('single', 1), ('three', 0))}
        o['n'] = {f'{a}_{b}': int(((d.g == gi) & (d.single == si)).sum())
                  for a, gi in (('said', 1), ('not', 0)) for b, si in (('single', 1), ('three', 0))}
        out[gk] = o
        print(' ', gk, o)
    return out


def visibility(Sx, eps, G):
    hdr('7c · Strategic flaws are visible, tactical flaws are hidden')
    M = G['M']
    P = pd.DataFrame([dict(pid=e['pid'], run=e['run'], at=pr['at'], result=pr['result'], blind=pr['blind'])
                      for e in eps for pr in e['presses']])
    blind_people = sorted(P[P.blind].pid.unique())
    refused_people = sorted(P[P.result.isin(['failed', 'partial'])].pid.unique())
    # which spoken tactical remarks followed a WRONG refusal
    tac = []
    for p, (ru, t, st, gist) in x1.SPOKEN_TAC.items():
        pr = P[(P.pid == p) & (P.run == ru) & (P['at'] <= t + 5) & (P['at'] >= t - 60)]
        last = pr.iloc[-1] if len(pr) else None
        tac.append(dict(pid=p, blind=None if last is None else bool(last.blind), gist=gist))
    out = dict(
        strategic=dict(exposed=int(Sx[Sx.odd == 1].pid.nunique()), people=int(Sx.pid.nunique()),
                       oddDecisions=int(Sx.odd.sum()), decisions=int(len(Sx)), oddShare=r(Sx.odd.mean(), 3),
                       c12=int(len(G['c12'])), spokenStrict=int(len(G['strict'])), spokenBroad=int(len(G['broad'])),
                       saidAny=int(len(G['c12'] | G['broad'])), saidMain=int(len(G['said']))),
        tactical=dict(refusalPeople=len(refused_people), blindPeople=len(blind_people), blindPresses=int(P.blind.sum()),
                      presses=int(len(P)), refusals=int(P.result.isin(['failed', 'partial']).sum()),
                      c13=int(M.C13.sum()), c13People=sorted(M.index[M.C13 == 1]), c14=int(M.C14.sum()),
                      c13AmongBlind=int(len(set(M.index[M.C13 == 1]) & set(blind_people))),
                      spokenTac=tac),
        c15=sorted(M.index[M.C15 == 1]), c15n=int(M.C15.sum()))
    print(json.dumps(out, indent=1, default=str))
    return out


def main():
    rng = np.random.default_rng(SEED)
    Sx, Tx, eps, logs, mS, mT = load_all()
    G = groups()
    print('decisions %d strategic, %d tactical; people %d' % (len(Sx), len(Tx), Sx.pid.nunique()))
    res = dict(generated=pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'), binKeys=BIN_KEYS,
               groups=dict(said=sorted(G['said']), c12=sorted(G['c12']), strict=sorted(G['strict']), broad=sorted(G['broad']),
                           narrated=G['narrated']))
    odd, D = odd_study(Sx, Tx, G, rng)
    res['odd'] = odd
    res['strip'] = robustness(Sx, G, rng)
    res['model'] = explain_model(mS, Sx)
    res['oldDots'] = old_dots(Sx, G, D)
    res['profile'] = people_profile(Sx, Tx, G, D)
    res['spoken'] = spoken(Sx, G, rng)
    res['refusal'] = refusal_anchors(Sx, Tx, eps, logs, rng)
    res['dominated'] = dominated(Sx, rng)
    res['manualSingle'] = manual_single(Sx, G, D)
    res['visibility'] = visibility(Sx, eps, G)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, separators=(',', ':'), default=lambda o: o.item() if hasattr(o, 'item') else str(o)),
                   encoding='utf-8')
    print('\nwrote', OUT.relative_to(BASE), '(%d kB)' % (OUT.stat().st_size // 1024))


if __name__ == '__main__':
    main()
