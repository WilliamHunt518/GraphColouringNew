#!/usr/bin/env python3
"""Follow-up analyses for the combined findings page (Results/findings_combined.html).

Read-only over Results/. Writes docs/analysis/combined/extras.json, which build_findings_synthesis.py
folds into the page payload, and prints every number the page quotes. Run from the repo root:

    C:/Users/Work/anaconda3/python.exe scripts/analysis_combined/extras.py

Four questions, each asked after rounds 1-2 and each fixed before its result was looked at:

1 · STYLE FINGERPRINT (theme 1). Round 1 found no operator TYPES (no clusters). This asks a weaker
    question that does not need clusters: is a person's whole pattern of behaviour distinctive enough
    to pick them out? Each session becomes a vector of round 1's ten H1 features, median-imputed and
    z-scored WITHIN GAME (scenario x plan index, so the game's own demands are removed). For every
    session-1 vector, the 33 session-2 vectors are ranked by Euclidean distance; a hit is the same
    person ranking first. Statistic: hit rate (both directions averaged) and mean rank of the true
    partner. Null: session-2 labels permuted, 10 000 draws, one-sided. Run twice: on all ten features,
    and with the reliance axis (PC1 of the 66 session vectors) projected out -- does anything
    idiosyncratic remain BEYOND how much someone relies? The 2-D maps (t-SNE, perplexity 10, and PCA)
    are pictures only; the hit rate is the test.
2 · DEEP QUEUES (theme 4). Round 1's load test was linear in queue length. Does reliance rise when the
    strategic queue is genuinely long -- 4 or more OTHER missions waiting when the panel opened? GEE
    (bias-reduced), within-person split of the indicator, + drone types, drones, minute, game.
3 · GIVING UP (theme 9). Who does not attempt a fixable recovery, and is it misunderstanding? Checks:
    self-rated comprehension (pre-study), experience, session 1 vs 2, first-ever fixable failure vs
    later ones, and how long a non-attempted failure sat before it was abandoned.
4 · FLAWS AND LATER USE, per assistant (theme 8). Strategic: decisions lined up on the first illogical
    card each operator saw (study-wide order, both sessions) -- and, separately, on the first moment
    they SAID they had noticed one (in-session narration, hand-coded below). Tactical: confirms lined
    up on the first Suggest press that returned "No workable plan", split by whether that refusal was
    the agent's blind spot (a fix existed using a drone busy on another task) or correct.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

BASE = Path(__file__).resolve().parents[2]
for p in ('scripts', 'scripts/analysis_round1', 'scripts/analysis_round2'):
    sys.path.insert(0, str(BASE / p))
warnings.filterwarnings('ignore')

OUT_DIR = BASE / 'docs' / 'analysis' / 'combined'
OUT = OUT_DIR / 'extras.json'
QUAL = BASE / 'docs' / 'analysis' / 'qual'
NARR = BASE / 'Results' / 'Narration'
SEED = 20261007
N_PERM = 10000


def hdr(s):
    print('\n' + '=' * 96 + '\n' + s + '\n' + '=' * 96)


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def gee(formula, d, binomial=True):
    fam = sm.families.Binomial() if binomial else sm.families.Gaussian()
    m = smf.gee(formula, 'pid', data=d, family=fam, cov_struct=sm.cov_struct.Exchangeable())
    return m.fit(cov_type='bias_reduced')


def orow(m, name):
    ci = m.conf_int().loc[name]
    return dict(OR=float(np.exp(m.params[name])), lo=float(np.exp(ci[0])), hi=float(np.exp(ci[1])),
                p=float(m.pvalues[name]))


def r(x, d=3):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), d)


# ════════════════════════════════════════════════════════════════════════════════════════════
# 1 · style fingerprint
# ════════════════════════════════════════════════════════════════════════════════════════════

FEATURE_LABEL = {
    'took': 'Takes the strategy card', 'preempt': 'Goes manual before the cards load',
    'edit': 'Edits a card rather than taking it', 'consult': 'Presses Suggest on tactical plans',
    'keep': 'Keeps the Suggest plan unchanged', 'recSug': 'Presses Suggest in recovery',
    'netSecs': 'Time spent per strategic decision', 'dSmall': 'Drones vs card, single-type missions',
    'dLarge': 'Drones vs card, multi-type missions', 'previews': 'Previews cards before choosing',
}


def match_stats(A, B):
    """A, B: (n, k) arrays, row i of each is the same person. Returns (hit rate, mean rank) of the
    true partner, both directions averaged; rank 1 = nearest."""
    D = np.sqrt(((A[:, None, :] - B[None, :, :]) ** 2).sum(-1))
    n = len(A)
    rk_ab = np.array([(D[i] < D[i, i]).sum() + 1 for i in range(n)])        # A_i looking among B
    rk_ba = np.array([(D[:, j] < D[j, j]).sum() + 1 for j in range(n)])     # B_j looking among A
    hits = ((rk_ab == 1).mean() + (rk_ba == 1).mean()) / 2
    return hits, (rk_ab.mean() + rk_ba.mean()) / 2, rk_ab, rk_ba


def perm_null(A, B, rng, n=N_PERM):
    hits, ranks = np.empty(n), np.empty(n)
    for i in range(n):
        perm = rng.permutation(len(B))
        h, m, _, _ = match_stats(A, B[perm])
        hits[i], ranks[i] = h, m
    return hits, ranks


def fingerprint():
    hdr('1 · Style fingerprint: can a person be picked out from their behaviour?')
    import h1_archetypes as h1
    from sklearn.decomposition import PCA
    from sklearn.manifold import TSNE
    S, T, R, SESS = quiet(h1.parse)
    F = h1.features(S, T, R, ['pid', 'run'])
    F[['pid', 'run']] = pd.DataFrame(F.key.tolist(), index=F.index)
    game = SESS.set_index(['pid', 'run'])
    import build_findings_synthesis as b
    dec = quiet(b.load_decisions)
    gidx = dec.groupby(['pid', 'run']).agg(scenario=('scenario', 'first'), plan=('planIndex', 'first'))
    F = F.join(gidx, on=['pid', 'run'])
    F['game'] = F.scenario.astype(str) + '|' + F.plan.astype(str)
    cols = h1.FEATURES
    Z, nmiss = quiet(h1.impute_z, F, cols, by='game')
    # a feature undefined for a whole game (no single-type missions in it) stays NaN: set to the game mean, 0
    n_all_missing = int(Z[cols].isna().sum().sum())
    Z[cols] = Z[cols].fillna(0.0)
    both = Z.groupby('pid').run.nunique()
    keep = both[both == 2].index
    Z = Z[Z.pid.isin(keep)].sort_values(['pid', 'run']).reset_index(drop=True)
    print('sessions per game:', F.game.value_counts().to_dict(), '| people with both sessions:', len(keep))
    print('imputed values (median within game):', {k: v for k, v in nmiss.items() if v},
          '| set to 0 (undefined for the whole game):', n_all_missing)

    X = Z[cols].to_numpy()
    pca = PCA().fit(X)
    pc = pca.transform(X)
    load1 = dict(zip(cols, pca.components_[0]))
    if load1['took'] < 0:                     # orient PC1 so higher = more reliance
        pc[:, 0] *= -1
        load1 = {k: -v for k, v in load1.items()}
    print('PC1 share of variance %.1f%%; loadings %s' % (100 * pca.explained_variance_ratio_[0],
                                                          {k: round(v, 2) for k, v in load1.items()}))
    A, B = X[Z.run.to_numpy() == 1], X[Z.run.to_numpy() == 2]
    pids = Z[Z.run == 1].pid.tolist()
    rng = np.random.default_rng(SEED)
    out = dict(n=len(pids), features=[dict(k=c, label=FEATURE_LABEL[c]) for c in cols],
               imputed={k: int(v) for k, v in nmiss.items() if v}, nSessions=int(len(Z)),
               pc1Share=float(pca.explained_variance_ratio_[0]),
               pc1Loadings={k: r(v) for k, v in load1.items()})

    def run_test(A_, B_, label):
        h, m, rab, rba = match_stats(A_, B_)
        nh, nr = perm_null(A_, B_, rng)
        p_h = (1 + (nh >= h).sum()) / (1 + len(nh))
        p_r = (1 + (nr <= m).sum()) / (1 + len(nr))
        n = len(A_)
        print('%-34s hit rate %.3f (%d/%d each way: %d, %d) vs chance %.3f, null 95th pct %.3f, p = %.4f'
              % (label, h, round(h * n), n, (rab == 1).sum(), (rba == 1).sum(), 1 / n,
                 np.percentile(nh, 95), p_h))
        print('%-34s mean rank of true partner %.1f (of %d) vs null mean %.1f, p = %.4f'
              % ('', m, n, nr.mean(), p_r))
        return dict(hit=float(h), hitsAB=int((rab == 1).sum()), hitsBA=int((rba == 1).sum()), chance=1 / n,
                    null95=float(np.percentile(nh, 95)), pHit=float(p_h), meanRank=float(m),
                    nullRank=float(nr.mean()), pRank=float(p_r),
                    top5=float((((rab <= 5).mean()) + ((rba <= 5).mean())) / 2),
                    ranks=[int(x) for x in rab], ranksBA=[int(x) for x in rba])

    out['all'] = run_test(A, B, 'all ten features')
    # reliance axis projected out: residual of each vector on PC1
    v1 = pca.components_[0]
    Xr = X - np.outer(X @ v1, v1)
    out['beyond'] = run_test(Xr[Z.run.to_numpy() == 1], Xr[Z.run.to_numpy() == 2], 'reliance axis (PC1) removed')
    # reliance alone: one number per session
    p1 = pc[:, :1]
    out['relianceOnly'] = run_test(p1[Z.run.to_numpy() == 1], p1[Z.run.to_numpy() == 2], 'reliance axis alone')

    # per-feature test-retest (session 1 vs 2, within-game z), Spearman
    rows = []
    for c in cols:
        a, bb = Z[Z.run == 1].set_index('pid')[c], Z[Z.run == 2].set_index('pid')[c]
        rho, p = stats.spearmanr(a, bb.loc[a.index])
        # same with the reliance axis removed (residual on PC1 score, per session)
        res = Z[c] - np.polyval(np.polyfit(pc[:, 0], Z[c], 1), pc[:, 0])
        ra = pd.Series(res[Z.run.to_numpy() == 1].to_numpy(), index=pids)
        rb = pd.Series(res[Z.run.to_numpy() == 2].to_numpy(), index=Z[Z.run == 2].pid)
        rho2, p2 = stats.spearmanr(ra, rb.loc[ra.index])
        rows.append(dict(k=c, label=FEATURE_LABEL[c], rho=r(rho), p=r(p, 4), rhoBeyond=r(rho2), pBeyond=r(p2, 4),
                         loading=r(load1[c])))
        print('  %-40s rho %.2f (p %.3f)   beyond reliance %.2f (p %.3f)   PC1 loading %.2f'
              % (FEATURE_LABEL[c], rho, p, rho2, p2, load1[c]))
    out['retest'] = rows

    # maps: t-SNE (picture only) and PCA
    ts = TSNE(n_components=2, perplexity=10, random_state=SEED, init='pca', learning_rate='auto').fit_transform(X)
    out['points'] = [dict(pid=p_, run=int(ru), tx=r(ts[i, 0]), ty=r(ts[i, 1]), px=r(pc[i, 0]), py=r(pc[i, 1]),
                          rel=r(pc[i, 0]), game=g_,
                          **{c: r(F.set_index(['pid', 'run']).loc[(p_, ru), c]) for c in cols})
                     for i, (p_, ru, g_) in enumerate(zip(Z.pid, Z.run, Z.game))]
    # how far apart is a person's own pair on the map, against random pairs? (descriptive)
    dmap = np.array([np.linalg.norm(ts[i] - ts[i + 1]) for i in range(0, len(ts), 2)])
    rnd = [np.linalg.norm(ts[i] - ts[j]) for i in range(len(ts)) for j in range(i + 1, len(ts))
           if Z.pid[i] != Z.pid[j]]
    out['mapPairRatio'] = float(np.median(dmap) / np.median(rnd))
    print('t-SNE: median own-pair distance / median other-pair distance = %.2f' % out['mapPairRatio'])
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
# 2 · deep queues
# ════════════════════════════════════════════════════════════════════════════════════════════

def deep_queue():
    hdr('2 · Deep queues: does reliance rise with 4+ other missions waiting?')
    import wB_common as w
    S, T, R, tl = quiet(w.build)
    out = {}
    for name, d, y in (('strategic', S, 'took'), ('tactical', T, 'consulted')):
        d = d.copy()
        d['q'] = d.st_queued
        d['hi4'] = (d.q >= 4).astype(int)
        d['hi4_pm'] = d.groupby('pid').hi4.transform('mean')
        d['hi4_w'] = d.hi4 - d.hi4_pm
        ppl = d.groupby('pid').hi4.max()
        m = gee(f'{y} ~ hi4_w + hi4_pm + ncolours + ndrones + emin + C(game)', d)
        within = orow(m, 'hi4_w')
        between = orow(m, 'hi4_pm')
        # dose: 0,1,2,3,4,5+
        d['qb'] = d.q.clip(upper=5)
        bins = [dict(k=int(k), label=('%d+' % k if k == 5 else str(k)), rate=float(g[y].mean()), n=int(len(g)),
                     people=int(g.pid.nunique())) for k, g in d.groupby('qb')]
        # people who saw both: their own rate at 4+ vs below
        pp = d[d.pid.isin(ppl[ppl == 1].index)].groupby(['pid', 'hi4'])[y].mean().unstack()
        diff = (pp[1] - pp[0]).dropna()
        sign = stats.wilcoxon(diff) if (diff != 0).sum() > 5 else None
        o = dict(nDecisions=int(len(d)), nHi=int(d.hi4.sum()), peopleHi=int((ppl == 1).sum()),
                 shareHi=float(d.hi4.mean()), within=within, between=between, bins=bins,
                 higher=int((diff > 0).sum()), lower=int((diff < 0).sum()), same=int((diff == 0).sum()),
                 meanDiff=float(diff.mean()), wilcoxonP=float(sign.pvalue) if sign else None)
        if name == 'strategic':
            o['byType'] = [dict(types=int(k), hi=int(hv), rate=float(g.took.mean()), n=int(len(g)))
                           for (k, hv), g in d[d.ncolours.isin([1, 3])].groupby(['ncolours', 'hi4'])]
            man = d[d.manual == 1]
            mp = gee('early ~ hi4_w + hi4_pm + ncolours + emin + C(game)', man)
            o['preempt'] = dict(rateHi=float(man[man.hi4 == 1].early.mean()), rateLo=float(man[man.hi4 == 0].early.mean()),
                                nHi=int(man.hi4.sum()), within=orow(mp, 'hi4_w'))
        out[name] = o
        print('%s: %d of %d decisions (%.0f%%) had 4+ others waiting, from %d people'
              % (name, o['nHi'], o['nDecisions'], 100 * o['shareHi'], o['peopleHi']))
        print('   rate by others waiting:', [(b_['label'], round(b_['rate'], 2), b_['n']) for b_ in bins])
        print('   within-person OR (4+ vs fewer) %.2f [%.2f, %.2f] p = %.3f; between-person OR %.3f p = %.3f'
              % (within['OR'], within['lo'], within['hi'], within['p'], between['OR'], between['p']))
        print('   people who met both: higher at 4+ %d, lower %d, same %d; mean diff %+.3f'
              % (o['higher'], o['lower'], o['same'], o['meanDiff']))
        if name == 'strategic':
            print('   by type:', o['byType'])
            print('   pre-emption among manual: 4+ %.2f vs %.2f; within OR %.2f p = %.3f'
                  % (o['preempt']['rateHi'], o['preempt']['rateLo'], o['preempt']['within']['OR'], o['preempt']['within']['p']))
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
# 3 · giving up on recovery
# ════════════════════════════════════════════════════════════════════════════════════════════

LIKERT = {'Strongly disagree': 1, 'Disagree': 2, 'Somewhat disagree': 3, 'Neutral': 4,
          'Neither agree nor disagree': 4, 'Somewhat agree': 5, 'Agree': 6, 'Strongly agree': 7}
FREQ = {'Never': 0, 'Rarely': 1, 'Occasionally': 2, 'Weekly': 3, 'Daily': 4}
EXP = {'None': 0, 'A little': 1, 'Moderate': 2, 'Extensive': 3}


def giving_up(pc1):
    hdr('3 · Giving up: who does not attempt a fixable recovery, and is it misunderstanding?')
    import wA_common as a
    E = quiet(a.load_episodes)
    F = E[E.fixAll == True].copy()  # noqa: E712
    # failures that land in the final 31 s cannot show an attempt (round 2 X3) -- excluded throughout
    F = F[F.timeRemaining >= 31].copy()
    F['wait'] = F.closed - F.opened
    pp = F.groupby('pid').agg(n=('attempted', 'size'), att=('attempted', 'mean'), tried=('attempted', 'sum'))
    demo = {}
    for f in sorted((BASE / 'Results' / 'Participants').glob('P*.json')):
        d = (json.loads(f.read_text(encoding='utf-8')).get('demographics') or {})
        und = [LIKERT.get(d.get(k)) for k in ('understand_role', 'understand_missions', 'understand_strategic',
                                               'understand_tactical', 'understand_scoring')]
        und = [u for u in und if u is not None]
        demo[f.stem] = dict(understand=np.mean(und) if und else np.nan,
                            understandTac=LIKERT.get(d.get('understand_tactical'), np.nan),
                            gaming=FREQ.get(d.get('gaming_frequency'), np.nan),
                            sim=EXP.get(d.get('sim_experience'), np.nan),
                            strategy=EXP.get(d.get('strategy_experience'), np.nan))
    pp = pp.join(pd.DataFrame(demo).T.astype(float))
    pp['reliance'] = pc1.reindex(pp.index)
    out = dict(nEpisodes=int(len(F)), nAttempted=int(F.attempted.sum()), nPeople=int(len(pp)),
               allAttempt=int((pp.att == 1).sum()), neverAttempt=sorted(pp[pp.att == 0].index.tolist()),
               understandDist={str(k): int(v) for k, v in pp.understand.round(1).value_counts().sort_index().items()},
               understandMin=float(pp.understand.min()), understandMean=float(pp.understand.mean()))
    corr = []
    for k, lab in (('understand', 'Self-rated understanding (pre-study, 5 items)'),
                   ('understandTac', 'Understood the tactical planner'),
                   ('gaming', 'Gaming frequency'), ('sim', 'Simulation experience'),
                   ('strategy', 'Strategy-game experience'), ('reliance', 'Reliance trait (PC1)')):
        x = pp.dropna(subset=[k])
        rho, p = stats.spearmanr(x[k], x.att)
        corr.append(dict(k=k, label=lab, rho=r(rho), p=r(p, 4), n=int(len(x))))
        print('  attempt rate vs %-46s rho %+.2f  p = %.3f  (n = %d)' % (lab, rho, p, len(x)))
    out['correlates'] = corr
    # learning: if not understanding were the cause, attempts should rise with exposure
    F = F.sort_values(['pid', 'seqAll'])
    F['nth'] = F.groupby('pid').cumcount() + 1
    out['byRun'] = [dict(run=int(k), rate=float(g.attempted.mean()), n=int(len(g))) for k, g in F.groupby('run')]
    out['byNth'] = [dict(k=('%d+' % k if k == 4 else str(k)), rate=float(g.attempted.mean()), n=int(len(g)))
                    for k, g in F.assign(nb=F.nth.clip(upper=4)).groupby('nb')]
    m = gee('attempted ~ nth + C(game)', F)
    out['nthModel'] = orow(m, 'nth')
    # same person, both sessions: is never-attempting a one-off or a habit?
    na = pp[pp.att < 1].index
    runs = F[F.pid.isin(na)].groupby(['pid', 'run']).attempted.agg(['mean', 'size']).reset_index()
    out['lowAttemptersByRun'] = [dict(pid=p_, run=int(ru), rate=float(mn), n=int(sz))
                                 for p_, ru, mn, sz in runs.itertuples(index=False)]
    # how long did a non-attempted failure sit before it was abandoned?
    ab = F[(F.attempted == 0) & (F.outcome == 'abandoned')]
    out['abandonWait'] = dict(n=int(len(ab)), median=float(ab.wait.median()), q1=float(ab.wait.quantile(.25)),
                              q3=float(ab.wait.quantile(.75)),
                              under10=int((ab.wait < 10).sum()), over30=int((ab.wait > 30).sum()),
                              values=[dict(pid=p_, wait=r(wt, 1)) for p_, wt in zip(ab.pid, ab.wait)])
    # harder failures? a fix that needs a drone busy on another task (Suggest cannot see it; by hand it
    # needs a chain) vs one the idle drones can cover
    ct = pd.crosstab(F.fixIdleLogged, F.attempted)
    fe = stats.fisher_exact(ct.to_numpy())
    out['byDifficulty'] = [dict(k='idle drones could fix it' if k else 'needed a drone busy on another task',
                                rate=float(g.attempted.mean()), n=int(len(g))) for k, g in F.groupby('fixIdleLogged')]
    out['difficultyFisherP'] = float(fe[1])
    nev = F[F.pid.isin(out['neverAttempt'])]
    out['neverEpisodes'] = dict(n=int(len(nev)), idleFixable=int(nev.fixIdleLogged.sum()))
    print('  attempt rate by difficulty:', [(x['k'], round(x['rate'], 2), x['n']) for x in out['byDifficulty']],
          'Fisher p = %.3f' % fe[1])
    print('  never-attempters: %d failures, %d fixable with idle drones alone' % (len(nev), nev.fixIdleLogged.sum()))
    print('  fixable failures with >= 31 s left: %d, attempted %d; %d of %d people attempted all; never: %s'
          % (len(F), F.attempted.sum(), out['allAttempt'], len(pp), out['neverAttempt']))
    print('  self-rated understanding: min %.1f, mean %.2f (1-7) -- ceiling' % (out['understandMin'], out['understandMean']))
    print('  attempt rate by session:', out['byRun'])
    print('  attempt rate by nth fixable failure of the study:', out['byNth'], ' OR per failure %.2f p = %.3f'
          % (out['nthModel']['OR'], out['nthModel']['p']))
    print('  non-attempted abandonments: n %d, wait median %.1f s (IQR %.1f-%.1f); <10 s %d, >30 s %d'
          % (len(ab), ab.wait.median(), ab.wait.quantile(.25), ab.wait.quantile(.75),
             out['abandonWait']['under10'], out['abandonWait']['over30']))
    print('  low attempters by session:', out['lowAttemptersByRun'])
    # what each never/low attempter said (codes C19-C21 + anything on failures) -- listed for the page
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════
# 4 · flaws and later use, per assistant
# ════════════════════════════════════════════════════════════════════════════════════════════

# Hand-coded from the in-session narration (Results/Narration/<PID>_s1, session segments, session time
# from segments.json; candidates pulled by keyword, every one read in context, researcher speech
# excluded). 'strict' = the participant says, during play, that a card sends drone types the mission
# does not need (or that a specific card's allocation is wrong); first such moment per person.
# 'broad' adds general remarks that a card sends too many drones. Coded 2026-10-07, before any
# behaviour around these moments was computed.
SPOKEN_STRAT = {
    # pid: (session, session-time s, strict?, gist)
    'P03': (2, 63.8, True, 'a card includes Lifters the mission does not need'),
    'P04': (1, 45.0, True, 'drones "literally not needed for that one"'),
    'P17': (1, 323.7, True, 'asks why a card sends Camera/Lifter drones the mission does not use'),
    'P19': (2, 36.4, True, 'the card "sends a bunch of extra of these even though it doesn\'t need it"'),
    'P20': (1, 239.7, True, 'Conservative card "doesn\'t make sense" -- no Lifters or Cameras needed'),
    'P29': (2, 80.1, True, 'a card "sent some green and red ones for no reason"'),
    'P30': (1, 61.2, True, 'no Lifters or Cameras needed on a Conservative card'),
    'P01': (2, 301.2, False, '"I\'m not sending four. I don\'t need three either."'),
    'P10': (1, 343.9, False, '"It sends one extra blue. I don\'t want that."'),
    'P13': (1, 250.0, False, '"Why does it have a buffer of five fast drones?"'),
    'P27': (2, 127.0, False, '"only one extra blue ... maybe some bugs"'),
    'P15': (2, 162.4, False, 'calls the AI "stupid" over one mistake'),
}
# 'strict' = the participant reacts, during play, to Suggest saying it cannot plan a fix ("No
# workable plan") or explains that it cannot because a drone is busy.
SPOKEN_TAC = {
    'P11': (1, 186.5, True, '"No workable plan."'),
    # P14 (s1 206 s, "the last suggestion sort of failed") is about a deployed plan losing a drone,
    # not Suggest refusing -- not coded.
    'P19': (1, 216.8, True, '"It\'s just no workable plan ... looks like we have to abandon"'),
    'P28': (1, 267.7, True, 'Suggest says no drones available because one "is working for the next task"'),
    'P31': (2, 341.8, True, '"Oh, no workable plan. Ah, okay, abandon them."'),   # fix genuinely impossible
    'P32': (2, 222.1, True, '"There\'s no workable plan. Oh well. We\'ll have to abandon it then."'),
}


def _qual_codes():
    try:
        M = pd.read_csv(QUAL / 'codes_matrix.csv').set_index('pid')
        return M
    except FileNotFoundError:
        return None


def flaws():
    hdr('4 · Flaws and later use, per assistant')
    import build_findings_synthesis as b
    import h3_recovery as h3
    import wB_common as w
    df = quiet(b.load_decisions)
    out = {}
    M = _qual_codes()
    narrated = sorted({p.name[:-3] for p in NARR.glob('P*_s1') if (p / 'segments.json').exists()})
    narrated = [p for p in narrated if p in set(df.pid)]
    out['narrated'] = narrated

    # ---- strategic: decisions in study order -------------------------------------------------
    d = df.sort_values(['pid', 'run', 'elapsed']).copy()
    d['seq'] = d.groupby('pid').cumcount()
    d['game'] = d.scenario.astype(str) + '|' + d.planIndex.astype(str)
    first = d[d.odd == 1].groupby('pid').seq.min()
    d = d[d.pid.isin(first.index)].copy()
    d['rel'] = d.seq - d.pid.map(first)
    said = set()
    if M is not None:
        said |= set(M.index[M.C12 == 1])
    strict = {p for p, v in SPOKEN_STRAT.items() if v[2]}
    said_any = said | strict
    d['said'] = d.pid.isin(said_any).astype(int)
    c3 = d[d.ncolours == 3].copy()
    c3['after'] = (c3.rel > 0).astype(int)

    def series(x, lo=-6, hi=12, minn=6):
        return [dict(rel=int(k), rate=float(g.took.mean()), n=int(len(g)), people=int(g.pid.nunique()))
                for k, g in x[(x.rel >= lo) & (x.rel <= hi)].groupby('rel') if len(g) >= minn]

    def binned(x, edges=((-99, -1, 'before'), (1, 5, '1–5 after'), (6, 15, '6–15 after'), (16, 999, '16+ after'))):
        return [dict(k=lab, rate=float(x[(x.rel >= a_) & (x.rel <= b_)].took.mean()),
                     n=int(((x.rel >= a_) & (x.rel <= b_)).sum())) for a_, b_, lab in edges]

    mm = gee('took ~ after + seq + C(game)', c3[c3.rel != 0])
    out['strategic'] = dict(
        people=int(d.pid.nunique()), saidPeople=sorted(said_any & set(d.pid)), qualSaid=sorted(said & set(d.pid)),
        spokenStrict=sorted(strict), firstRel=dict(median=float(first.median())),
        all=series(d), matched=series(c3),
        matchedSaid=series(c3[c3.said == 1], minn=4), matchedNotSaid=series(c3[c3.said == 0], minn=4),
        binsSaid=binned(c3[c3.said == 1]), binsNotSaid=binned(c3[c3.said == 0]),
        model=orow(mm, 'after'))
    for grp, sub in (('said', c3[c3.said == 1]), ('notSaid', c3[c3.said == 0])):
        try:
            out['strategic']['model_' + grp] = orow(gee('took ~ after + seq + C(game)', sub[sub.rel != 0]), 'after')
        except Exception as ex:
            print('  fit failed', grp, ex)
    # interaction: does the after-step differ for people who said they noticed?
    mi = gee('took ~ after * said + seq + C(game)', c3[c3.rel != 0])
    out['strategic']['interaction'] = orow(mi, 'after:said')
    S_ = out['strategic']
    print('strategic: %d people saw an illogical card; %d said they noticed (debrief/interview %d, in play %d strict)'
          % (S_['people'], len(S_['saidPeople']), len(S_['qualSaid']), len(strict)))
    print('   three-type uptake after vs before, all: OR %.2f [%.2f, %.2f] p = %.3f'
          % (S_['model']['OR'], S_['model']['lo'], S_['model']['hi'], S_['model']['p']))
    for g_ in ('said', 'notSaid'):
        if 'model_' + g_ in S_:
            mo = S_['model_' + g_]
            print('   %-8s OR %.2f [%.2f, %.2f] p = %.3f   bins %s' % (g_, mo['OR'], mo['lo'], mo['hi'], mo['p'],
                  [(x['k'], round(x['rate'], 2), x['n']) for x in S_['bins' + ('Said' if g_ == 'said' else 'NotSaid')]]))
    print('   after x said interaction OR %.2f p = %.3f' % (S_['interaction']['OR'], S_['interaction']['p']))

    # ---- strategic, aligned on the first SPOKEN noticing (in-session narration) -------------
    rows = []
    for p_, (run, t, st, gist) in SPOKEN_STRAT.items():
        if not st or p_ not in set(df.pid):
            continue
        g = df[df.pid == p_].sort_values(['run', 'elapsed']).copy()
        g['after'] = ((g.run > run) | ((g.run == run) & (g.elapsed > t))).astype(int)
        g3 = g[g.ncolours == 3]
        rows.append(dict(pid=p_, run=run, t=t, gist=gist,
                         before=r(g3[g3.after == 0].took.mean()), nBefore=int((g3.after == 0).sum()),
                         after=r(g3[g3.after == 1].took.mean()), nAfter=int((g3.after == 1).sum()),
                         beforeAll=r(g[g.after == 0].took.mean()), afterAll=r(g[g.after == 1].took.mean())))
    sp = pd.DataFrame(rows)
    allsp = []
    for p_, (run, t, st, gist) in SPOKEN_STRAT.items():
        if not st or p_ not in set(df.pid):
            continue
        g = df[df.pid == p_].copy()
        g['after'] = ((g.run > run) | ((g.run == run) & (g.elapsed > t))).astype(int)
        allsp.append(g)
    G = pd.concat(allsp)
    G['game'] = G.scenario.astype(str) + '|' + G.planIndex.astype(str)
    G3 = G[G.ncolours == 3]
    try:
        ms = orow(gee('took ~ after + C(game)', G3), 'after')
    except Exception as ex:
        ms = None
        print('  spoken model failed', ex)
    out['spokenStrategic'] = dict(people=rows, model=ms,
                                  lower=int((sp.after < sp.before).sum()), higher=int((sp.after > sp.before).sum()),
                                  same=int((sp.after == sp.before).sum()))
    print('   aligned on the first time they SAID it (n = %d, three-type missions):' % len(rows))
    for x in rows:
        print('     %s s%d %5.0fs  before %s (n %d) -> after %s (n %d)   %s'
              % (x['pid'], x['run'], x['t'], x['before'], x['nBefore'], x['after'], x['nAfter'], x['gist']))
    if ms:
        print('   pooled OR %.2f [%.2f, %.2f] p = %.3f' % (ms['OR'], ms['lo'], ms['hi'], ms['p']))

    # ---- tactical: confirms in study order, aligned on the first "No workable plan" ---------
    eps = quiet(h3.load_all)[0]
    presses = [dict(pid=e['pid'], run=e['run'], at=pr['at'], result=pr['result'], blind=pr['blind'],
                    next=pr.get('next'))
               for e in eps for pr in e['presses']]
    P = pd.DataFrame(presses)
    P['refused'] = P.result.isin(['failed', 'partial'])
    P = P.sort_values(['pid', 'run', 'at'])
    firstref = P[P.refused].groupby('pid').head(1).set_index('pid')
    S, T, R, tl = quiet(w.build)
    T = T.sort_values(['pid', 'run', 'open_ts']).copy()
    T['seq'] = T.groupby('pid').cumcount()
    T['ev'] = [((ru > firstref.loc[p_, 'run']) or (ru == firstref.loc[p_, 'run'] and ts / 1000.0 > firstref.loc[p_, 'at']))
               if p_ in firstref.index else np.nan for p_, ru, ts in zip(T.pid, T.run, T.open_ts)]
    TT = T[T.pid.isin(firstref.index)].copy()
    TT['after'] = TT.ev.astype(int)
    first_after = TT[TT.after == 1].groupby('pid').seq.min()
    TT['rel'] = TT.seq - TT.pid.map(first_after) + 1        # 1 = first confirm after the refusal
    TT = TT[TT.pid.isin(first_after.index)]
    TT['blind'] = TT.pid.map(firstref.blind).astype(int)
    sp_t = {p for p, v in SPOKEN_TAC.items() if v[2]}
    if M is not None:
        sp_t_q = set()  # no debrief code targets this; P27's debrief mention is listed on the page
    TT['said'] = TT.pid.isin(sp_t).astype(int)

    def tseries(x, lo=-8, hi=12, minn=5):
        return [dict(rel=int(k), rate=float(g.consulted.mean()), n=int(len(g)), people=int(g.pid.nunique()))
                for k, g in x[(x.rel >= lo) & (x.rel <= hi)].groupby('rel') if len(g) >= minn]

    # with 13 people the game fixed effects separate; session order (run) stands in for them
    TFORM = 'consulted ~ after + seq + lplan'
    mt = gee(TFORM, TT)
    o = dict(refusals=int(P.refused.sum()), presses=int(len(P)), refusalPeople=int(firstref.shape[0]),
             blindPresses=int(P.blind.sum()), blindPeople=sorted(P[P.blind].pid.unique().tolist()),
             firstBlind=int(firstref.blind.sum()), people=int(TT.pid.nunique()),
             series=tseries(TT), model=orow(mt, 'after'),
             before=float(TT[TT.after == 0].consulted.mean()), after=float(TT[TT.after == 1].consulted.mean()),
             nBefore=int((TT.after == 0).sum()), nAfter=int((TT.after == 1).sum()),
             spoken=sorted(sp_t), spokenInData=sorted(sp_t & set(TT.pid)))
    for grp, sub in (('blind', TT[TT.blind == 1]), ('correct', TT[TT.blind == 0])):
        o['rate_' + grp] = dict(before=r(sub[sub.after == 0].consulted.mean()), after=r(sub[sub.after == 1].consulted.mean()),
                                nBefore=int((sub.after == 0).sum()), nAfter=int((sub.after == 1).sum()),
                                people=int(sub.pid.nunique()))
        try:
            o['model_' + grp] = orow(gee(TFORM, sub), 'after')
        except Exception as ex:
            print('  fit failed', grp, ex)
    # per person before / after
    pp = TT.groupby(['pid', 'after']).consulted.mean().unstack()
    o['perPerson'] = [dict(pid=p_, before=r(row.get(0)), after=r(row.get(1)), blind=int(firstref.loc[p_, 'blind']),
                           said=int(p_ in sp_t)) for p_, row in pp.iterrows()]
    # recovery Suggest: episodes after the first refusal vs before (people who pressed at least once before)
    E = pd.DataFrame([dict(pid=e['pid'], run=e['run'], opened=e['opened'], sug=int(e['suggest'] > 0)) for e in eps])
    E = E[E.pid.isin(firstref.index)].copy()
    E['after'] = [int((ru > firstref.loc[p_, 'run']) or (ru == firstref.loc[p_, 'run'] and op > firstref.loc[p_, 'at']))
                  for p_, ru, op in zip(E.pid, E.run, E.opened)]
    o['recovery'] = dict(before=r(E[E.after == 0].sug.mean()), nBefore=int((E.after == 0).sum()),
                         after=r(E[E.after == 1].sug.mean()), nAfter=int((E.after == 1).sum()))
    # what happened right after each refusal
    o['nextAfterRefusal'] = P[P.refused].next.value_counts().to_dict()
    o['nextAfterBlind'] = P[P.blind].next.value_counts().to_dict()
    out['tactical'] = o
    print('tactical: %d Suggest presses in recovery, %d refused ("No workable plan"/partial) from %d people; %d blind-spot (%s)'
          % (o['presses'], o['refusals'], o['refusalPeople'], o['blindPresses'], ', '.join(o['blindPeople'])))
    print('   first refusal was a blind spot for %d of %d people' % (o['firstBlind'], o['refusalPeople']))
    print('   tactical Suggest consulted: before %.2f (n %d) -> after %.2f (n %d); OR %.2f [%.2f, %.2f] p = %.3f'
          % (o['before'], o['nBefore'], o['after'], o['nAfter'], o['model']['OR'], o['model']['lo'], o['model']['hi'], o['model']['p']))
    for g_ in ('blind', 'correct'):
        print('   %-8s %s  %s' % (g_, o['rate_' + g_], o.get('model_' + g_)))
    print('   recovery Suggest use: before %s (n %d) -> after %s (n %d)'
          % (o['recovery']['before'], o['recovery']['nBefore'], o['recovery']['after'], o['recovery']['nAfter']))
    print('   next action after a refusal:', o['nextAfterRefusal'], '| after a blind spot:', o['nextAfterBlind'])
    print('   spoken (in play):', o['spoken'], '| of whom in the event-study sample:', o['spokenInData'])
    # the spoken moments vs the press that preceded them: was the refusal they reacted to genuine?
    react = []
    for p_, (run, t, st, gist) in SPOKEN_TAC.items():
        pr = P[(P.pid == p_) & (P.run == run) & (P['at'] <= t + 5) & (P['at'] >= t - 60)]
        last = pr.iloc[-1] if len(pr) else None
        react.append(dict(pid=p_, run=run, t=t, gist=gist,
                          press=None if last is None else str(last.result),
                          blind=None if last is None else bool(last.blind),
                          lag=None if last is None else r(t - last['at'], 1)))
    o['spokenMatch'] = react
    for x in react:
        print('     %s s%d %5.0fs  nearest preceding press: %s blind=%s (lag %s s)  %s'
              % (x['pid'], x['run'], x['t'], x['press'], x['blind'], x['lag'], x['gist']))
    return out


# In-play remarks quoted on the page: (pid, session, substring that starts the quote, utterances to join).
# Machine transcript of the session recording (no speaker separation), so only remarks that are
# unmistakably the participant's own are used. Text is pulled verbatim from transcript.raw.json.
NARR_QUOTES = [
    ('P15', 1, 'fail this this mission', 2, 'recovery', 'abandon it'),
    ('P29', 1, 'Well, I think I did it once', 1, 'recovery'),
    ('P19', 1, "It's just no workable plan", 3, 'refusal'),
    ('P32', 2, "There's no workable plan", 3, 'refusal'),
    ('P28', 1, 'It is working for the next task', 2, 'refusal'),
    ('P17', 1, 'Why is it that the green ones', 1, 'card'),
    ('P19', 2, 'Oh, this just sends a bunch', 1, 'card'),
    ('P20', 1, "I don't think because I don't need", 1, 'card'),
]


def narration_quotes():
    out = []
    for pid, run, starts, k, theme, *until in NARR_QUOTES:
        d = NARR / (pid + '_s1')
        try:
            sj = json.loads((d / 'segments.json').read_text(encoding='utf-8'))
            tr = json.loads((d / 'transcript.raw.json').read_text(encoding='utf-8'))['segments']
        except FileNotFoundError:
            continue
        sg = [x for x in sj['segments'] if x['kind'] == 'session'][run - 1]
        us = [u for u in tr if sg['videoStart'] <= u['start'] < sg['videoEnd']]
        hit = None
        for i, u in enumerate(us):
            pos = u['text'].find(starts)
            if pos >= 0:
                hit = i
                break
        if hit is None:
            print('  narration quote not found:', pid, run, starts)
            continue
        text = ' '.join([us[hit]['text'][us[hit]['text'].find(starts):].strip()]
                        + [u['text'].strip() for u in us[hit + 1:hit + k]])
        if until and until[0] in text:
            text = text[:text.find(until[0]) + len(until[0])] + ' …'
        out.append(dict(pid=pid, run=run, t=round(us[hit]['start'] - sg['videoStart']), text=text, theme=theme))
    print('narration quotes:', len(out), 'of', len(NARR_QUOTES))
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fp = fingerprint()
    pc1 = pd.DataFrame(fp['points']).groupby('pid').rel.mean()
    res = dict(generated=pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'),
               fingerprint=fp, deepQueue=deep_queue(), givingUp=giving_up(pc1), flaws=flaws(),
               narrationQuotes=narration_quotes(),
               spokenStrategic={k: dict(run=v[0], t=v[1], strict=v[2], gist=v[3]) for k, v in SPOKEN_STRAT.items()},
               spokenTactical={k: dict(run=v[0], t=v[1], strict=v[2], gist=v[3]) for k, v in SPOKEN_TAC.items()})
    OUT.write_text(json.dumps(res, indent=1, default=lambda o: o.item() if hasattr(o, 'item') else str(o)),
                   encoding='utf-8')
    print('\nwrote', OUT.relative_to(BASE))


if __name__ == '__main__':
    main()
