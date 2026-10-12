#!/usr/bin/env python3
"""Pass 2 · AREA `style` — "Who the operator is".

Read-only over Results/. Writes docs/analysis/register/pass2/style.json and prints every number the
findings in docs/analysis/register/pass2/style.findings.yaml quote. Run from the repo root:

    python scripts/register/pass2/style.py

What it recomputes (the existing loaders do the parsing; P09 excluded everywhere):

1 · FINGERPRINT. Each session -> the ten H1 habits (h1_archetypes.features), median-imputed and
    z-scored WITHIN GAME (so the game's own demands are removed). Session-1 profile i is compared
    with all 33 session-2 profiles by Euclidean distance; "hit" = own session-2 is the nearest.
    Same pipeline as scripts/analysis_combined/extras.py (fingerprint), plus what the new charts
    need: the full 33 x 33 rank matrix, each person's profile pair, and own-vs-other profile
    correlations. Permutation null: session-2 labels shuffled, 10 000 draws.
2 · HABIT BY HABIT. Per habit: session-1 vs session-2 Spearman (game-adjusted z), bootstrap CI over
    people, Holm across the ten. Pre-empting the cards separately on its raw rate (share of a
    session's strategic decisions committed manually before the cards loaded).
3 · THE RELIANCE AXIS. Person-level PCA of the ten pooled habits (round 1 H1); loadings as
    correlations with the axis; habit-by-habit Spearman grid; per person card uptake vs Suggest use.
4 · WHO VS WHAT. McFadden pseudo-R2 of card-taking from the mission (+ scenario, run, timing), from
    the person, and from both (build_findings_synthesis.individual, recomputed).
5 · DISPOSITION. build_findings_synthesis.analyse_disposition (40 tests, Holm) as is.
6 · TRUST, BETWEEN VS WITHIN. Game-centred reliance and trust; between = person means, within =
    session-2 minus session-1 change. Spearman with Fisher CIs.
7 · PAYOFF, BETWEEN VS WITHIN. Decision-level GEE (round 1 H10 primary); session-level GEE
    (bias-reduced) of four outcomes on within/between card uptake; throughput (missions never
    allocated) on the session reliance axis (round 2 C2); half-weights check (P01/P02 dropped).
8 · QUALITATIVE GROUPS. Counts (and unprompted counts) for C01, C02, C08, C23-C28 and how each group
    used the assistants (descriptive Mann-Whitney only). C02 (one person) located on every habit.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import types
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

BASE = Path(__file__).resolve().parents[3]
for p in ('scripts', 'scripts/analysis_round1', 'scripts/analysis_round2', 'scripts/analysis_combined'):
    sys.path.insert(0, str(BASE / p))
warnings.filterwarnings('ignore')

# h1_archetypes imports scikit-learn at module level, but nothing used here needs it (PCA is done
# with numpy below). Stub it when it is not installed so the plain `python` runs this.
try:
    import sklearn  # noqa: F401
except ImportError:
    sk = types.ModuleType('sklearn')
    for sub, names in (('decomposition', ['PCA']), ('metrics', ['adjusted_rand_score']),
                       ('mixture', ['GaussianMixture']), ('manifold', ['TSNE'])):
        m = types.ModuleType('sklearn.' + sub)
        for n in names:
            setattr(m, n, None)
        sys.modules['sklearn.' + sub] = m
        setattr(sk, sub, m)
    sys.modules['sklearn'] = sk

OUT = BASE / 'docs' / 'analysis' / 'register' / 'pass2' / 'style.json'
QUAL = BASE / 'docs' / 'analysis' / 'qual'
EXCLUDE = {'P09'}
HALF = {'P01', 'P02'}
SEED = 20261012
N_PERM = 10000
N_BOOT = 2000

LABEL = {
    'took': 'Takes the strategy card', 'preempt': 'Goes manual before the cards load',
    'edit': 'Edits a card instead of taking it', 'consult': 'Presses Suggest on tactical plans',
    'keep': 'Keeps the Suggest plan unchanged', 'recSug': 'Presses Suggest in recovery',
    'netSecs': 'Time spent per strategic decision', 'dSmall': 'Drones vs card, single-type missions',
    'dLarge': 'Drones vs card, multi-type missions', 'previews': 'Previews cards before choosing',
}
SHORT = {'took': 'Card taken', 'preempt': 'Pre-empts cards', 'edit': 'Edits card', 'consult': 'Suggest (plan)',
         'keep': 'Keeps Suggest plan', 'recSug': 'Suggest (recovery)', 'netSecs': 'Decision time',
         'dSmall': 'Drones, 1-type', 'dLarge': 'Drones, multi-type', 'previews': 'Previews'}
TIER = {'took': 'strategic', 'preempt': 'strategic', 'edit': 'strategic', 'previews': 'strategic',
        'netSecs': 'strategic', 'dSmall': 'strategic', 'dLarge': 'strategic',
        'consult': 'tactical', 'keep': 'tactical', 'recSug': 'tactical'}


def hdr(s):
    print('\n' + '=' * 96 + '\n' + s + '\n' + '=' * 96)


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def r(x, d=3):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, d) if np.isfinite(x) else None


def spear(x, y):
    """Spearman with a Fisher-z interval (SE 1.06/sqrt(n-3), Fieller et al.)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = ~(np.isnan(x) | np.isnan(y))
    x, y = x[ok], y[ok]
    rho, p = stats.spearmanr(x, y)
    n = len(x)
    z, se = np.arctanh(np.clip(rho, -.999, .999)), 1.06 / np.sqrt(max(n - 3, 1))
    return dict(rho=r(rho), lo=r(np.tanh(z - 1.96 * se)), hi=r(np.tanh(z + 1.96 * se)), p=r(p, 5), n=int(n))


def holm(ps):
    order = np.argsort(ps)
    out, run = [None] * len(ps), 0.0
    for k, i in enumerate(order):
        run = max(run, min(1.0, ps[i] * (len(ps) - k)))
        out[i] = run
    return out


def pca_np(X):
    """PCA on the rows of X (columns already standardised): components (rows), explained-variance
    ratio, and eigenvalues of the correlation matrix (variance with ddof=0)."""
    Xc = X - X.mean(0)
    U, s, Vt = np.linalg.svd(Xc, full_matrices=False)
    ev = s ** 2 / len(X)
    return Vt, ev / ev.sum(), ev


def gee_br(formula, d, family='gaussian'):
    fam = sm.families.Binomial() if family == 'binomial' else sm.families.Gaussian()
    m = smf.gee(formula, 'pid', data=d, family=fam, cov_struct=sm.cov_struct.Exchangeable())
    try:
        return m.fit(cov_type='bias_reduced')
    except Exception:
        return m.fit()


def term(m, name, scale=1.0):
    lo, hi = m.conf_int().loc[name]
    return dict(est=r(scale * m.params[name], 4), lo=r(scale * lo, 4), hi=r(scale * hi, 4), p=r(m.pvalues[name], 5))


# ════════════════════════════════════════════════════════════════════════════════════════════
# data
# ════════════════════════════════════════════════════════════════════════════════════════════

def load():
    import h1_archetypes as h1
    import build_findings_synthesis as b
    import h4_h10_data as H
    import wD_common as WD
    S, T, R, SESS = quiet(h1.parse)
    dec = quiet(b.load_decisions)
    dec = dec[~dec.pid.isin(EXCLUDE)].copy()
    HS, HD = quiet(H.sessions), quiet(H.decisions)
    WS = quiet(WD.build)[0]
    sess, people = quiet(b.load_people)
    return dict(h1=h1, b=b, S=S, T=T, R=R, SESS=SESS, dec=dec, HS=HS, HD=HD, WS=WS, sess=sess, people=people)


# ════════════════════════════════════════════════════════════════════════════════════════════
# 1 + 2 · fingerprint, habit by habit
# ════════════════════════════════════════════════════════════════════════════════════════════

def ranks_of(A, B):
    D = np.sqrt(((A[:, None, :] - B[None, :, :]) ** 2).sum(-1))
    n = len(A)
    rab = np.array([(D[i] < D[i, i]).sum() + 1 for i in range(n)])
    rba = np.array([(D[:, j] < D[j, j]).sum() + 1 for j in range(n)])
    return D, rab, rba


def fingerprint(L, rng):
    hdr('1 · Fingerprint: does a session-1 profile pick out the same person in session 2?')
    h1, cols = L['h1'], L['h1'].FEATURES
    F = h1.features(L['S'], L['T'], L['R'], ['pid', 'run'])
    F[['pid', 'run']] = pd.DataFrame(F.key.tolist(), index=F.index)
    g = L['dec'].groupby(['pid', 'run']).agg(scenario=('scenario', 'first'), plan=('planIndex', 'first'))
    F = F.join(g, on=['pid', 'run'])
    F['game'] = F.scenario.astype(str) + '|' + F.plan.astype(str)
    Z, nmiss = quiet(h1.impute_z, F, cols, by='game')
    Z[cols] = Z[cols].fillna(0.0)
    both = Z.groupby('pid').run.nunique()
    Z = Z[Z.pid.isin(both[both == 2].index)].sort_values(['pid', 'run']).reset_index(drop=True)
    X = Z[cols].to_numpy()
    run = Z.run.to_numpy()
    pids = Z[Z.run == 1].pid.tolist()
    comps, evr, _ = pca_np(X)
    v1 = comps[0] * (1 if comps[0][cols.index('took')] >= 0 else -1)
    pc1 = X @ v1
    A, B = X[run == 1], X[run == 2]
    Xr = X - np.outer(X @ v1, v1)
    Ar, Br = Xr[run == 1], Xr[run == 2]
    n = len(A)

    def test(A_, B_, label):
        D, rab, rba = ranks_of(A_, B_)
        hit = ((rab == 1).mean() + (rba == 1).mean()) / 2
        mrank = (rab.mean() + rba.mean()) / 2
        nh, nr = np.empty(N_PERM), np.empty(N_PERM)
        for k in range(N_PERM):
            pm = rng.permutation(n)
            _, a_, b_ = ranks_of(A_, B_[pm])
            nh[k] = ((a_ == 1).mean() + (b_ == 1).mean()) / 2
            nr[k] = (a_.mean() + b_.mean()) / 2
        p_h = (1 + (nh >= hit).sum()) / (1 + N_PERM)
        p_r = (1 + (nr <= mrank).sum()) / (1 + N_PERM)
        top3 = ((rab <= 3).mean() + (rba <= 3).mean()) / 2
        print('%-30s own session nearest: %d/%d (s1->s2), %d/%d (s2->s1); chance 1; p = %.4f | mean rank %.1f '
              '(chance %.1f), p = %.4f | own in top 3: %.0f%% (chance %.0f%%)'
              % (label, (rab == 1).sum(), n, (rba == 1).sum(), n, p_h, mrank, nr.mean(), p_r, 100 * top3, 300 / n))
        # rank matrix: for row i (session-1 profile), the rank of every session-2 profile
        RK = np.argsort(np.argsort(D, axis=1), axis=1) + 1
        return dict(hitsAB=int((rab == 1).sum()), hitsBA=int((rba == 1).sum()), hit=r(hit, 4), pHit=r(p_h, 5),
                    meanRank=r(mrank, 2), nullRank=r(nr.mean(), 2), pRank=r(p_r, 5), top3=r(top3, 3),
                    null95=r(np.percentile(nh, 95) * n, 2), ranksAB=[int(x) for x in rab],
                    ranksBA=[int(x) for x in rba], rankMatrix=RK.tolist())

    out = dict(n=n, pids=pids, cols=cols, labels=[LABEL[c] for c in cols], short=[SHORT[c] for c in cols],
               tier=[TIER[c] for c in cols], imputed={k: int(v) for k, v in nmiss.items() if v},
               pc1Share=r(evr[0]))
    out['all'] = test(A, B, 'all ten habits')
    out['beyond'] = test(Ar, Br, 'reliance axis removed')
    out['relianceOnly'] = test(pc1[run == 1][:, None], pc1[run == 2][:, None], 'reliance axis alone')
    # display order: by the person's mean reliance-axis score (so neighbours in the matrix rely alike)
    prs = (pc1[run == 1] + pc1[run == 2]) / 2
    order = np.argsort(-prs)
    out['order'] = [int(i) for i in order]
    out['pc1Person'] = [r(v, 3) for v in prs]
    # profile correlations: own pair vs every other pairing
    Rm = np.corrcoef(A, B)[:n, n:]
    own = np.diag(Rm)
    other = np.array([np.delete(Rm[i], i).mean() for i in range(n)])
    beat = int((own > other).sum())
    print('profile r with own other session: median %.2f; with other people\'s: median %.2f; own beats mean other '
          'for %d of %d (sign test p = %.4f)' % (np.median(own), np.median(other), beat, n,
                                                 stats.binomtest(beat, n, .5).pvalue))
    out['profileR'] = dict(own=[r(v) for v in own], otherMean=[r(v) for v in other], ownMedian=r(np.median(own)),
                           otherMedian=r(np.median(other)), beat=beat, pSign=r(stats.binomtest(beat, n, .5).pvalue, 5))
    out['profiles'] = [dict(pid=p_, s1=[r(v, 2) for v in A[i]], s2=[r(v, 2) for v in B[i]],
                            rank=int(out['all']['ranksAB'][i]), rankBA=int(out['all']['ranksBA'][i]),
                            rankBeyond=int(out['beyond']['ranksAB'][i]))
                       for i, p_ in enumerate(pids)]

    hdr('2 · Habit by habit: session 1 vs session 2, same person (game-adjusted z), Spearman')
    rows = []
    brng = np.random.default_rng(SEED + 1)
    for j, c in enumerate(cols):
        a, bb = A[:, j], B[:, j]
        rho, p = stats.spearmanr(a, bb)
        boots = []
        for _ in range(N_BOOT):
            ix = brng.integers(0, n, n)
            if np.ptp(a[ix]) > 0 and np.ptp(bb[ix]) > 0:
                boots.append(stats.spearmanr(a[ix], bb[ix])[0])
        rel = max(rho, 0.0)
        rel2 = 2 * rel / (1 + rel) if rel > 0 else 0.0
        strata = lambda q: (4 * np.sqrt(q / (1 - q)) + 1) / 3 if 0 < q < 1 else 1.0
        rows.append(dict(k=c, label=LABEL[c], tier=TIER[c], rho=r(rho), p=r(p, 5),
                         lo=r(np.percentile(boots, 2.5)), hi=r(np.percentile(boots, 97.5)),
                         strata1=r(strata(rel), 2), strata2=r(strata(rel2), 2), loading=r(v1[j])))
    for row, ph in zip(rows, holm([x['p'] for x in rows])):
        row['pHolm'] = r(ph, 5)
    for row in sorted(rows, key=lambda x: -x['rho']):
        print('  %-40s rho %.2f [%.2f, %.2f]  p %.4f  Holm %.4f  levels: 1 session %.1f, 2 sessions %.1f'
              % (row['label'], row['rho'], row['lo'], row['hi'], row['p'], row['pHolm'], row['strata1'], row['strata2']))
    out['retest'] = rows
    s1pc, s2pc = pc1[run == 1], pc1[run == 2]
    out['pc1Retest'] = spear(s1pc, s2pc)
    print('session reliance score (PC1 of the 66 session profiles) s1 vs s2:', out['pc1Retest'])
    return out, Z


def preempt(L):
    hdr('2b · Pre-empting the cards: share of a session\'s strategic decisions committed before the cards loaded')
    S = L['S']
    p = S[S.residual == 0]
    rate = p.groupby(['pid', 'run']).agg(rate=('early', 'mean'), n=('early', 'size'), k=('early', 'sum')).reset_index()
    w = rate.pivot(index='pid', columns='run')
    w = w.dropna()
    sp = spear(w['rate'][1], w['rate'][2])
    never = int(((w['k'][1] == 0) & (w['k'][2] == 0)).sum())
    man = S[S.manual == 1]
    share_pre = float(man.early.mean())
    # session-2 rate of people who did / did not pre-empt in session 1
    did1 = w['k'][1] > 0
    print('Spearman s1 vs s2 %s; never in either session: %d of %d; share of manual choices that were pre-emptive %.2f'
          % (sp, never, len(w), share_pre))
    print('session-2 pre-empt rate: those who pre-empted in session 1 %.2f (n %d) vs those who did not %.2f (n %d)'
          % (w['rate'][2][did1].mean(), did1.sum(), w['rate'][2][~did1].mean(), (~did1).sum()))
    pts = [dict(pid=pid, a=r(w['rate'][1][pid]), b=r(w['rate'][2][pid]), na=int(w['n'][1][pid]), nb=int(w['n'][2][pid]),
                ka=int(w['k'][1][pid]), kb=int(w['k'][2][pid])) for pid in w.index]
    return dict(spearman=sp, never=never, n=int(len(w)), shareOfManual=r(share_pre), decisions=int(len(p)),
                preempted=int(p.early.sum()), s2IfDid=r(w['rate'][2][did1].mean()), s2IfNot=r(w['rate'][2][~did1].mean()),
                nDid=int(did1.sum()), points=pts)


# ════════════════════════════════════════════════════════════════════════════════════════════
# 3 · the reliance axis
# ════════════════════════════════════════════════════════════════════════════════════════════

def axis(L):
    hdr('3 · The reliance axis (person-level PCA of the ten habits, both sessions pooled)')
    h1, cols = L['h1'], L['h1'].FEATURES
    F = h1.features(L['S'], L['T'], L['R'], 'pid')
    F['pid'] = F.key
    pids = sorted(L['S'].pid.unique())
    F = F.set_index('pid').loc[pids].reset_index()
    Zdf, _ = quiet(h1.impute_z, F)
    Zx = Zdf[cols].to_numpy()
    comps, evr, ev = pca_np(Zx)
    if comps[0][cols.index('took')] < 0:
        comps[0] *= -1
    load = comps[0] * np.sqrt(ev[0])
    sc = Zx @ comps[0]
    sc = sc / sc.std()
    print('PC1 share %.1f%%, eigenvalues %s, Kaiser keeps %d' % (100 * evr[0], np.round(ev[:4], 2), int((ev > 1).sum())))
    for c, v in sorted(zip(cols, load), key=lambda t: -t[1]):
        print('   loading %-40s %+.2f' % (LABEL[c], v))
    # session-level scores on the same axis (habits z-scored within run x scenario, as round 1)
    FS = h1.features(L['S'], L['T'], L['R'], ['pid', 'run'])
    FS['pid'] = [k[0] for k in FS.key]
    FS['run'] = [k[1] for k in FS.key]
    scen = L['SESS'].set_index(['pid', 'run']).scenario
    FS['scenario'] = [scen.get((p, q)) for p, q in zip(FS.pid, FS.run)]
    FS['cell'] = FS.run.astype(str) + FS.scenario
    FSz, _ = quiet(h1.impute_z, FS, cols, by='cell')
    FS['sPC1'] = FSz[cols].to_numpy() @ comps[0]
    FS['sPC1'] = FS.sPC1 / FS.sPC1.std(ddof=0)
    w_nos = comps[0].copy()
    w_nos[cols.index('netSecs')] = 0.0            # the same axis with decision speed taken out
    FS['sPC1_nos'] = FSz[cols].to_numpy() @ w_nos
    FS['sPC1_nos'] = FS.sPC1_nos / FS.sPC1_nos.std(ddof=0)
    wide = FS.pivot(index='pid', columns='run', values='sPC1').loc[pids]
    st = spear(wide[1], wide[2])
    print('person score on the axis, session 1 vs 2:', st)
    # habit correlation grid (Spearman, person level, pooled habits)
    Rm, Pm = stats.spearmanr(Zdf[cols].to_numpy())
    npairs = len(cols) * (len(cols) - 1) // 2
    nsig = int(sum(Pm[i, j] < .05 for i in range(len(cols)) for j in range(i + 1, len(cols))))
    print('habit pairs correlated at p < .05: %d of %d' % (nsig, npairs))
    tc = spear(F.took, F.consult)
    print('card uptake vs Suggest use (person level, raw rates):', tc)
    pts = [dict(pid=p_, took=r(F.took[i]), consult=r(F.consult[i]), recSug=r(F.recSug[i]), pc1=r(sc[i]),
                s1=r(wide.loc[p_, 1]), s2=r(wide.loc[p_, 2]), n=int(F.nS[i]), nT=int(F.nT[i]))
           for i, p_ in enumerate(pids)]
    return dict(share=r(evr[0]), eigen=[r(v, 3) for v in ev], kaiser=int((ev > 1).sum()),
                loadings=[dict(k=c, label=LABEL[c], tier=TIER[c], v=r(v)) for c, v in zip(cols, load)],
                retest=st, corr=dict(cols=cols, short=[SHORT[c] for c in cols],
                                     rho=[[r(Rm[i, j], 2) for j in range(len(cols))] for i in range(len(cols))],
                                     p=[[r(Pm[i, j], 4) for j in range(len(cols))] for i in range(len(cols))]),
                corrSig=dict(n=nsig, of=npairs), tookConsult=tc, people=pts,
                tookRange=[r(F.took.min()), r(F.took.max())]), dict(zip(pids, sc)), FS[['pid', 'run', 'sPC1', 'sPC1_nos']]


# ════════════════════════════════════════════════════════════════════════════════════════════
# 4 · who vs what
# ════════════════════════════════════════════════════════════════════════════════════════════

def who_vs_what(L):
    hdr('4 · How much of card-taking is the person vs the mission (McFadden pseudo-R2, descriptive)')
    df = L['dec']
    fit = lambda f: smf.logit(f, df).fit(disp=0, method='bfgs', maxiter=4000)
    mission = 'ncolours + ndrones + C(scenario) + C(run) + idx'
    m_m = quiet(fit, 'took ~ ' + mission)
    m_p = quiet(fit, 'took ~ C(pid)')
    m_b = quiet(fit, 'took ~ ' + mission + ' + C(pid)')
    out = dict(mission=r(m_m.prsquared), person=r(m_p.prsquared), both=r(m_b.prsquared), n=int(len(df)),
               people=int(df.pid.nunique()))
    rates = df.groupby('pid').took.mean()
    out['rates'] = dict(lo=r(rates.min()), hi=r(rates.max()), median=r(rates.median()),
                        high=int((rates >= .9).sum()), low=int((rates <= .25).sum()))
    w = df.groupby(['pid', 'run']).took.mean().unstack().dropna()
    out['tookRetest'] = spear(w[1], w[2])
    print(out)
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
# 5 · disposition
# ════════════════════════════════════════════════════════════════════════════════════════════

def disposition(L):
    hdr('5 · Disposition (AIAS-4, verification, delegation, experience) vs behaviour — 40 tests, Holm')
    D = quiet(L['b'].analyse_disposition, L['sess'], L['people'])
    cells = [dict(pred=c['predictor'], predLabel=c['predictorLabel'], beh=c['behaviour'], behLabel=c['behaviourLabel'],
                  rho=r(c.get('rho')), p=r(c.get('p'), 4), holm=r(c.get('holm'), 4), n=c.get('n')) for c in D['cells']]
    print('tests %d, nominal p < .05: %d, Holm survivors: %d, detectable |rho| at 80%% power %.2f (n %d)'
          % (D['nTests'], D['nNominal'], D['nHolm'], D['detectable'], D['nDetect']))
    for c in cells:
        if c['p'] is not None and c['p'] < .05:
            print('   nominal:', c['predLabel'], '×', c['behLabel'], 'rho', c['rho'], 'p', c['p'], 'Holm', c['holm'])
    bats = [dict(key=x['key'], label=x['label'], mean=r(x['mean'], 2), sd=r(x['sd'], 2), top=x['top'],
                 lo=r(x['lo'], 2), hi=r(x['hi'], 2)) for x in D['batteries']]
    print('batteries:', bats)
    return dict(cells=cells, nTests=D['nTests'], nNominal=D['nNominal'], nHolm=D['nHolm'],
                detectable=r(D['detectable'], 2), nDetect=D['nDetect'], batteries=bats,
                stem=D['sample']['fieldStem'], n=D['sample']['n'])


# ════════════════════════════════════════════════════════════════════════════════════════════
# 6 · trust: between vs within
# ════════════════════════════════════════════════════════════════════════════════════════════

def between_within(S, x, y):
    """S: one row per session with pid, run, game. Both columns game-centred, then
    between = person means, within = session-2 minus session-1 change."""
    d = S[['pid', 'run', 'game', x, y]].dropna().copy()
    for c in (x, y):
        d[c + '_c'] = d[c] - d.groupby('game')[c].transform('mean')
    keep = d.groupby('pid').run.nunique()
    d = d[d.pid.isin(keep[keep == 2].index)]
    bm = d.groupby('pid')[[x + '_c', y + '_c']].mean()
    w = d.pivot(index='pid', columns='run', values=[x + '_c', y + '_c'])
    dx, dy = w[x + '_c'][2] - w[x + '_c'][1], w[y + '_c'][2] - w[y + '_c'][1]
    return dict(between=spear(bm[x + '_c'], bm[y + '_c']), within=spear(dx, dy),
                ptsB=[dict(pid=p_, x=r(bm.loc[p_, x + '_c']), y=r(bm.loc[p_, y + '_c'])) for p_ in bm.index],
                ptsW=[dict(pid=p_, x=r(dx[p_]), y=r(dy[p_])) for p_ in dx.index])


def trust(L):
    hdr('6 · Reliance and trust: between people vs within a person (game-centred)')
    S = L['WS']
    out = {}
    for key, x, y in (('strategic', 'took', 'trust_s'), ('tactical', 'consult', 'trust_t')):
        res = between_within(S, x, y)
        # GEE with within/between split, game fixed (bias-reduced)
        d = S[['pid', 'run', 'game', x, y]].dropna().copy()
        d[x + '_b'] = d.groupby('pid')[x].transform('mean')
        d[x + '_w'] = d[x] - d[x + '_b']
        m = gee_br('%s ~ %s_w + %s_b + C(game)' % (y, x, x), d)
        res['geeWithin'] = term(m, x + '_w', .25)
        res['geeBetween'] = term(m, x + '_b', .25)
        out[key] = res
        print('%-9s between %s | within %s' % (key, res['between'], res['within']))
        print('          GEE per +25 points of reliance: within %s, between %s (trust points, 1-7)'
              % (res['geeWithin'], res['geeBetween']))
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
# 7 · payoff
# ════════════════════════════════════════════════════════════════════════════════════════════

def payoff(L, FSpc):
    hdr('7 · Payoff: between people vs within a person')
    import build_findings_synthesis as b
    out = {}
    # decision level (round 1 H10 primary): mission completed in full ~ card + composition + game + person mean
    def dec_model(D):
        d = D.dropna(subset=['full']).copy()
        d['took_pm'] = d.groupby('pid').took.transform('mean')
        m = b.gee('full ~ took + ncolours + ndrones + C(game) + took_pm', d, binomial=True)
        w, bt = m.conf_int().loc['took'], m.conf_int().loc['took_pm']
        se = m.bse['took']
        return dict(withinOR=r(np.exp(m.params['took'])), withinLo=r(np.exp(w[0])), withinHi=r(np.exp(w[1])),
                    withinP=r(m.pvalues['took'], 4), betweenOR=r(np.exp(m.params['took_pm'])),
                    betweenLo=r(np.exp(bt[0])), betweenHi=r(np.exp(bt[1])), betweenP=r(m.pvalues['took_pm'], 4),
                    between25=r(np.exp(.25 * m.params['took_pm'])), detectLo=r(np.exp(-2.8 * se), 2),
                    detectHi=r(np.exp(2.8 * se), 2), n=int(m.nobs), people=int(d.pid.nunique()),
                    rawCard=r(d[d.took == 1].full.mean()), rawManual=r(d[d.took == 0].full.mean()))
    D = L['HD']
    out['decision'] = dec_model(D)
    out['decisionNoHalf'] = dec_model(D[~D.pid.isin(HALF)])
    print('decision level (mission completed in full):', out['decision'])
    print('   without P01/P02:', out['decisionNoHalf'])

    # session level
    S = L['HS'].copy()
    S = S.merge(FSpc, on=['pid', 'run'], how='left')
    S['run2'] = (S.run == 2).astype(int)
    S['z'] = S.groupby('game').score_rescaled.transform(lambda v: (v - v.mean()) / v.std())
    S['best'] = S.score_rescaled / S.groupby('game').score_rescaled.transform('max')
    S['eff'] = S.scoreEff
    S['unalloc'] = S.unallocMissions
    # score efficiency, share of best human score and benchmark share are each the session score divided by a
    # per-game constant, so once standardised within game they ARE the z-score (P01/P02's raw efficiency aside):
    # one score outcome, not four
    chk = S.dropna(subset=['eff']).copy()
    for c in ('eff', 'best'):
        chk[c + '_z'] = chk.groupby('game')[c].transform(lambda v: (v - v.mean()) / v.std())
    nh = ~chk.pid.isin(HALF)
    print('within-game z of efficiency vs score z: r = %.4f (without P01/P02 %.4f); best-share z vs score z r = %.4f'
          % (np.corrcoef(chk.eff_z, chk.z)[0, 1], np.corrcoef(chk.eff_z[nh], chk.z[nh])[0, 1],
             np.corrcoef(chk.best_z, chk.z)[0, 1]))
    OUTC = [('z', 'Session score (z within game)'), ('unalloc', 'Missions never allocated')]
    rows = []

    def sess_models(S_, tag):
        res = []
        for y, lab in OUTC:
            d = S_.dropna(subset=[y, 'uptake']).copy()
            d['y'] = (d[y] - d.groupby('game')[y].transform('mean')) / d.groupby('game')[y].transform('std')
            d['uptake_b'] = d.groupby('pid').uptake.transform('mean')
            d['uptake_w'] = d.uptake - d.uptake_b
            m = gee_br('y ~ uptake_w + uptake_b + C(game) + run2', d)
            for comp in ('w', 'b'):
                t = term(m, 'uptake_' + comp, .25)
                res.append(dict(y=y, label=lab, comp='within' if comp == 'w' else 'between', sample=tag, **t))
        return res
    rows = sess_models(S, 'all')
    for x in rows:
        print('   %-45s %-8s per +25 pts uptake: %+.3f SD [%+.3f, %+.3f] p = %.4f'
              % (x['label'], x['comp'], x['est'], x['lo'], x['hi'], x['p']))
    rows_nh = sess_models(S[~S.pid.isin(HALF)], 'noHalf')
    print('   without P01/P02:')
    for x in rows_nh:
        print('   %-45s %-8s %+.3f SD [%+.3f, %+.3f] p = %.4f' % (x['label'], x['comp'], x['est'], x['lo'], x['hi'], x['p']))
    out['session'] = rows
    out['sessionNoHalf'] = rows_nh
    # throughput on the session reliance axis (round 2 C2): raw count per SD
    d = S.dropna(subset=['sPC1', 'unalloc']).copy()
    d['sPC1_b'] = d.groupby('pid').sPC1.transform('mean')
    d['sPC1_w'] = d.sPC1 - d.sPC1_b
    m = gee_br('unalloc ~ sPC1_w + sPC1_b + C(game) + run2', d)
    d['nos_b'] = d.groupby('pid').sPC1_nos.transform('mean')
    d['nos_w'] = d.sPC1_nos - d.nos_b
    m2 = gee_br('unalloc ~ nos_w + nos_b + C(game) + run2', d)
    d['up_b'] = d.groupby('pid').uptake.transform('mean')
    d['up_w'] = d.uptake - d.up_b
    m3 = gee_br('unalloc ~ up_w + up_b + C(game) + run2', d)
    out['throughput'] = dict(within=term(m, 'sPC1_w'), between=term(m, 'sPC1_b'),
                             withinNoSpeed=term(m2, 'nos_w'), withinUptake25=term(m3, 'up_w', .25),
                             betweenUptake25=term(m3, 'up_b', .25),
                             meanUnalloc=r(S.unalloc.mean(), 2), n=int(m.nobs))
    print('   same axis without decision speed, within: %s; card uptake alone, within per +25 pts: %s'
          % (out['throughput']['withinNoSpeed'], out['throughput']['withinUptake25']))
    print('throughput (missions never allocated per SD of session reliance): within %s, between %s; mean %.2f/session'
          % (out['throughput']['within'], out['throughput']['between'], S.unalloc.mean()))
    # mission completion, per person: between = uptake vs completion beyond what the missions predict;
    # within = the same person's card missions vs their own manual missions
    d = D.dropna(subset=['full']).copy()
    me = smf.logit('full ~ ncolours + ndrones + C(game)', d).fit(disp=0)
    d['exp'] = me.predict(d)
    pp = d.groupby('pid').agg(up=('took', 'mean'), obs=('full', 'mean'), exp=('exp', 'mean'), n=('full', 'size'))
    pp['adj'] = pp.obs - pp.exp
    sp_b = spear(pp.up, pp.adj)
    card = d[d.took == 1].groupby('pid').agg(c=('full', 'mean'), nc=('full', 'size'), ce=('exp', 'mean'))
    man = d[d.took == 0].groupby('pid').agg(m=('full', 'mean'), nm=('full', 'size'), me=('exp', 'mean'))
    cm = card.join(man, how='inner')
    cm = cm[(cm.nc >= 2) & (cm.nm >= 2)]
    cm['diffAdj'] = (cm.c - cm.ce) - (cm.m - cm.me)
    better, worse = int((cm.diffAdj > 0).sum()), int((cm.diffAdj < 0).sum())
    wil = stats.wilcoxon(cm.diffAdj) if len(cm) >= 6 else None
    print('completion beyond expectation ~ uptake (between people): %s' % sp_b)
    print('own card vs own manual missions (people with >= 2 of each, n = %d): card better for %d, worse for %d; '
          'median adjusted difference %+.3f, Wilcoxon p = %.3f' % (len(cm), better, worse, cm.diffAdj.median(),
                                                                  wil.pvalue if wil else np.nan))
    out['completion'] = dict(
        between=sp_b, people=[dict(pid=p_, up=r(v.up), obs=r(v.obs), exp=r(v.exp), adj=r(v.adj), n=int(v.n))
                              for p_, v in pp.iterrows()],
        within=dict(n=int(len(cm)), better=better, worse=worse, median=r(cm.diffAdj.median()),
                    p=r(wil.pvalue, 4) if wil else None),
        pairs=[dict(pid=p_, card=r(v.c), nc=int(v.nc), man=r(v.m), nm=int(v.nm), cardExp=r(v.ce), manExp=r(v.me),
                    diffAdj=r(v.diffAdj)) for p_, v in cm.iterrows()])
    # chart data: between (person means, game-centred) and within (s2 - s1 change), score z and never-allocated
    out['bwScore'] = between_within(S, 'uptake', 'z')
    out['bwUnalloc'] = between_within(S, 'uptake', 'unalloc')
    print('chart: score z ~ uptake  between %s within %s' % (out['bwScore']['between'], out['bwScore']['within']))
    print('chart: never allocated ~ uptake  between %s within %s' % (out['bwUnalloc']['between'], out['bwUnalloc']['within']))
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
# 8 · qualitative groups
# ════════════════════════════════════════════════════════════════════════════════════════════

def qual(L, ax, fp_pc):
    hdr('8 · Qualitative groups: who said it, and how did they use the assistants? (descriptive)')
    M = pd.read_csv(QUAL / 'codes_matrix.csv')
    M = M[~M.pid.isin(EXCLUDE)].set_index('pid')
    E = pd.read_csv(QUAL / 'evidence.csv')
    led = E.groupby(['code', 'pid']).led.min()
    people = {p['pid']: p for p in ax['people']}
    dec = L['dec']
    secs = dec.groupby('pid').secs.median()
    S = L['S']
    pre = S[S.residual == 0].groupby('pid').early.mean()
    meas = dict(took=lambda p: people[p]['took'], consult=lambda p: people[p]['consult'],
                pc1=lambda p: people[p]['pc1'], preempt=lambda p: float(pre.get(p, np.nan)),
                secs=lambda p: float(secs.get(p, np.nan)))
    pids = sorted(people)
    out = {}
    for code in ('C01', 'C02', 'C08', 'C23', 'C24', 'C25', 'C26', 'C27', 'C28'):
        inn = [p for p in pids if M.loc[p, code] == 1]
        rest = [p for p in pids if p not in inn]
        unprompted = sum(1 for p in inn if (code, p) in led.index and led[(code, p)] == 0)
        row = dict(n=len(inn), unprompted=int(unprompted), of=len(pids), who=inn)
        for k, f in meas.items():
            a = [f(p) for p in inn if f(p) is not None and np.isfinite(f(p))]
            bb = [f(p) for p in rest if f(p) is not None and np.isfinite(f(p))]
            pv = stats.mannwhitneyu(a, bb).pvalue if len(a) >= 2 and len(bb) >= 2 else None
            row[k] = dict(inMean=r(np.mean(a)) if a else None, restMean=r(np.mean(bb)), p=r(pv, 4))
        out[code] = row
        print('%s: %d of %d (%d unprompted) | cards %s vs %s (p %s) | Suggest %s vs %s (p %s) | axis %s vs %s (p %s)'
              % (code, len(inn), len(pids), unprompted, row['took']['inMean'], row['took']['restMean'], row['took']['p'],
                 row['consult']['inMean'], row['consult']['restMean'], row['consult']['p'],
                 row['pc1']['inMean'], row['pc1']['restMean'], row['pc1']['p']))
    # C02 is one person: where do they sit on each habit (percentile among the 33)?
    c02 = out['C02']['who']
    loc = {}
    for p in c02:
        for k, f in meas.items():
            vals = np.array([f(q) for q in pids], float)
            v = f(p)
            loc[k] = dict(value=r(v), pct=r(stats.percentileofscore(vals[np.isfinite(vals)], v, kind='mean') / 100, 3))
        print('C02 %s:' % p, loc)
    out['C02loc'] = loc
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════

def main():
    rng = np.random.default_rng(SEED)
    L = load()
    print('people %d, strategic decisions %d (P09 excluded)' % (L['dec'].pid.nunique(), len(L['dec'])))
    fp, _ = fingerprint(L, rng)
    pre = preempt(L)
    ax, pc_person, FSpc = axis(L)
    wvw = who_vs_what(L)
    disp = disposition(L)
    tr = trust(L)
    pay = payoff(L, FSpc)
    q = qual(L, ax, pc_person)
    r1 = json.loads((BASE / 'docs' / 'analysis' / 'round1' / 'results.json').read_text(encoding='utf-8'))
    e2 = json.loads((BASE / 'docs' / 'analysis' / 'combined' / 'extras2.json').read_text(encoding='utf-8'))
    AN = e2['archNull']
    types_ = dict(dbic=r1['h1']['dbic'], ari=r1['h1']['ari'], jaccard=r1['h1']['jaccard'],
                  nullDbicShare=r1['h1']['nullDbicShare'],
                  arch=[dict(k=k, obs=AN['observed'][k], mean=AN['nulls']['stable'][k]['mean'],
                             lo=AN['nulls']['stable'][k]['lo'], hi=AN['nulls']['stable'][k]['hi'],
                             p=AN['nulls']['stable'][k]['pAbove']) for k in ('expl3', 'same', 'prof1', 'prof2')],
                  aias=r1['h7'])
    games = {g: dict(tasks=r(v['tasks'], 2), missions=r(v['missions'], 2), penalty=r(v['penalty'], 1))
             for g, v in e2['personExtra']['gameMeans'].items()}
    hdr('Methods · game load (tasks completed per session, from extras2)')
    print(games, '| max/min tasks %.2f' % (max(v['tasks'] for v in games.values()) / min(v['tasks'] for v in games.values())))
    out = dict(generated='2026-10-12', fingerprint=fp, preempt=pre, axis=ax, whoVsWhat=wvw, disposition=disp,
               trust=tr, payoff=pay, qual=q, types=types_, games=games)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(',', ':')), encoding='utf-8')
    print('\nwrote', OUT.relative_to(BASE), '(%.0f kB)' % (OUT.stat().st_size / 1024))


if __name__ == '__main__':
    main()
