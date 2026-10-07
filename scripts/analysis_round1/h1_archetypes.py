#!/usr/bin/env python3
"""H1 -- Are there operator archetypes?  (analysis round 1, docs/analysis/HYPOTHESES_ROUND1.md §3)

Read-only over Results/. Prints every number the report (docs/analysis/round1/h1_archetypes.md)
quotes. Run from the repo root:

    C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h1_archetypes.py

Pre-registered primary test (frozen): Gaussian mixture / latent profile model, k = 1..4 by BIC.
SUPPORT = k>=2 beats k=1 by dBIC > 10 AND bootstrap Jaccard >= .75 AND the same people group
together when sessions 1 and 2 are clustered separately.

Operationalisation fixed BEFORE the first fit (see the report's analysis log):

* Features (10, per person, pooled over both sessions -- decisions pooled, not session rates
  averaged):
    took       card uptake (aggressive/conservative) / strategic decisions
    preempt    manual choices made before the cards loaded / manual choices
    edit       edited-card choices (editedFromStrategy set) / strategic decisions
    consult    tactical confirms with Suggest pressed / tactical confirms
    keep       consulted confirms deployed unmodified / consulted confirms (conditional, so it is
               not a copy of `consult`)
    recSug     recovery episodes with Suggest pressed / recovery episodes
    netSecs    median over strategic decisions of max(0, time-to-choice - card reveal delay), i.e.
               time spent beyond the forced 4-5 s wait (log1p-transformed)
    dSmall     mean (drones committed - Conservative card total) on single-type missions
    dLarge     same on multi-type missions          (residual missions excluded from both)
    previews   mean strategic_card_previewed events per strategic decision
  A rate whose denominator is empty is imputed with the cohort median (count reported).
  dSmall/dLarge are computed over ALL decisions, not only manual ones: the manual-only version is
  undefined for many people (some never chose manual on a given size); the manual-only variant is
  run as a robustness check.
* Primary spec: features z-scored -> PCA -> keep components with eigenvalue > 1 (Kaiser) -> GMM
  with DIAGONAL covariance on those PC scores, k = 1..4, n_init = 20, BIC. Why not diag GMM on the
  raw features: a diagonal mixture cannot represent correlated features with one component, so it
  'finds' k>=2 purely from correlation; on PC scores k=1 is the full-covariance Gaussian, so the
  k=1 baseline is fair. Full covariance on 10 raw features is not identifiable at n=33.
* Stability: Hennig (2007) bootstrap Jaccard, B = 500, min over clusters must be >= .75.
* Session agreement: features recomputed per session, z-scored within run x scenario cell (the
  scenario main effect is nuisance), same pipeline, adjusted Rand index between the two partitions
  with a permutation p.
Outcomes (score, trust, disposition, stance) are never in the clustering.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'scripts'))
warnings.filterwarnings('ignore')

import build_findings_synthesis as b  # noqa: E402
import study_analysis as sa  # noqa: E402
from agent_scenario_stats import events  # noqa: E402

from sklearn.decomposition import PCA  # noqa: E402
from sklearn.metrics import adjusted_rand_score  # noqa: E402
from sklearn.mixture import GaussianMixture  # noqa: E402

PART = BASE / 'Results' / 'Participants'
EXCLUDE = {'P09'}
FEATURES = ['took', 'preempt', 'edit', 'consult', 'keep', 'recSug', 'netSecs', 'dSmall', 'dLarge',
            'previews']
RATE_FEATURES = {'took', 'preempt', 'edit', 'consult', 'keep', 'recSug'}
SEED = 20261007
N_INIT = 20
B_BOOT = 500


def hdr(s):
    print('\n' + '=' * 100 + '\n' + s + '\n' + '=' * 100)


# ── 1 · decision-level parse ────────────────────────────────────────────────────────────────

def parse():
    """Strategic decisions (mirrors b.load_decisions's inclusion rule), tactical decisions and
    recovery episodes (via study_analysis.read_session), and session rows."""
    strat, tac, rec, sess = [], [], [], []
    for path in sorted(glob.glob(str(PART / 'P*.json'))):
        pid = os.path.splitext(os.path.basename(path))[0]
        if pid in EXCLUDE:
            continue
        log = json.loads(Path(path).read_text(encoding='utf-8'))
        starts = [e for s in log['sessions'] for e in events(s) if e['type'] == 'session_start']
        primary = starts[0]['taskPrimary']
        for run, raw in enumerate(log['sessions'], start=1):
            evs = events(raw)
            r = sa.read_session(evs, pid, run)
            if r is None:
                continue
            srow, decs, eps = r
            sess.append(srow)
            tac += [d for d in decs if d['tier'] == 'tactical']
            rec += eps
            need, residual, opened = {}, set(), {}
            for ev in evs:
                t = ev['type']
                m = ev.get('missionId')
                if t == 'mission_arrived':
                    tot = {'Blue': 0, 'Red': 0, 'Green': 0}
                    for task in ev.get('tasks', []):
                        for c, n in primary[str(task['type'])].items():
                            tot[c] += n
                    need[m] = tot
                    if ev.get('isResidual'):
                        residual.add(m)
                elif t == 'strategic_modal_opened':
                    req = need.get(m)
                    cards = {c['name']: c for c in ev.get('strategiesPresented', [])}
                    if not req or len(cards) < 2:
                        continue
                    opened[m] = dict(at=ev['timestamp'], previews=0,
                                     cons=sum(cards['Conservative']['trueAssets'].values()),
                                     aggr=sum(cards['Aggressive']['trueAssets'].values()),
                                     reveal=max(c['revealDelayMs'] for c in cards.values()),
                                     ncol=sum(1 for c in req if req[c] > 0),
                                     ndr=sum(req.values()), seq=[])
                elif t == 'strategic_card_previewed' and m in opened:
                    opened[m]['previews'] += 1
                    opened[m]['seq'].append(ev.get('strategyName'))
                elif t == 'strategic_choice' and m in opened:
                    o = opened.pop(m)
                    ct = ev.get('choiceType')
                    secs = (ev['timestamp'] - o['at']) / 1000.0
                    toggles = sum(1 for a, c in zip(o['seq'], o['seq'][1:]) if a != c)
                    strat.append(dict(
                        pid=pid, run=run, scenario=srow['scenario'], missionId=m,
                        took=int(ct in ('aggressive', 'conservative')), manual=int(ct == 'manual'),
                        early=1 if ev.get('manualBeforeCardsLoaded') else 0,
                        edit=int(ev.get('editedFromStrategy') is not None),
                        secs=secs, net=max(0.0, secs - o['reveal'] / 1000.0),
                        reveal=o['reveal'] / 1000.0,
                        previews=o['previews'], toggles=toggles,
                        committed=sum((ev.get('assetsChosen') or {}).values()),
                        cons=o['cons'], aggr=o['aggr'], ncol=o['ncol'], ndr=o['ndr'],
                        residual=int(m in residual or str(m).endswith('-R'))))
    return (pd.DataFrame(strat), pd.DataFrame(tac), pd.DataFrame(rec), pd.DataFrame(sess))


def ratio(num, den):
    return num / den if den else np.nan


def features(S, T, R, keys, manual_only_delta=False):
    """One row per key (pid, or (pid, run)) -- raw feature values, NaN where undefined."""
    rows = []
    gS, gT, gR = S.groupby(keys), T.groupby(keys), R.groupby(keys)
    for k in sorted(set(gS.groups) | set(gT.groups)):
        s = gS.get_group(k) if k in gS.groups else S.iloc[:0]
        t = gT.get_group(k) if k in gT.groups else T.iloc[:0]
        r = gR.get_group(k) if k in gR.groups else R.iloc[:0]
        man = s[s.manual == 1]
        cons_ = t[t.used == True]  # noqa: E712
        g = s[s.residual == 0]
        if manual_only_delta:
            g = g[g.manual == 1]
        d = g.committed - g.cons
        rows.append(dict(
            key=k, nS=len(s), nT=len(t), nR=len(r), nMan=len(man),
            took=ratio(s.took.sum(), len(s)),
            preempt=ratio(man.early.sum(), len(man)),
            edit=ratio(s.edit.sum(), len(s)),
            consult=ratio(t.used.sum(), len(t)),
            keep=ratio(cons_.accepted.sum(), len(cons_)),
            recSug=ratio((r.suggest > 0).sum(), len(r)),
            netSecs=np.log1p(s.net.median()) if len(s) else np.nan,
            dSmall=d[g.ncol == 1].mean() if (g.ncol == 1).any() else np.nan,
            dLarge=d[g.ncol >= 2].mean() if (g.ncol >= 2).any() else np.nan,
            previews=s.previews.mean() if len(s) else np.nan,
            toggles=s.toggles.mean() if len(s) else np.nan))
    return pd.DataFrame(rows)


def impute_z(F, cols=FEATURES, by=None, verbose=True):
    """Median-impute (within `by` groups if given), then z-score (within groups if given)."""
    X = F.copy()
    nmiss = {c: int(X[c].isna().sum()) for c in cols}
    if by is None:
        for c in cols:
            X[c] = X[c].fillna(X[c].median())
            sd = X[c].std(ddof=0)
            X[c] = (X[c] - X[c].mean()) / (sd if sd > 0 else 1)
    else:
        for c in cols:
            X[c] = X.groupby(by)[c].transform(lambda v: v.fillna(v.median()))
            X[c] = X.groupby(by)[c].transform(
                lambda v: (v - v.mean()) / (v.std(ddof=0) if v.std(ddof=0) > 0 else 1))
    if verbose:
        print('  imputed (median) values per feature:', {k: v for k, v in nmiss.items() if v})
    return X, nmiss


def rank_normal(X, cols=FEATURES):
    Y = X.copy()
    for c in cols:
        r = stats.rankdata(Y[c])
        Y[c] = stats.norm.ppf((r - .5) / len(r))
    return Y


# ── 2 · mixture machinery ───────────────────────────────────────────────────────────────────

def kaiser_pcs(Z):
    pca = PCA().fit(Z)
    ev = pca.explained_variance_ * (len(Z) - 1) / len(Z)  # eigenvalues of the correlation matrix
    keep = max(1, int((ev > 1).sum()))
    return pca, ev, keep


def fit_gmm(X, k, cov, seed=SEED, n_init=N_INIT):
    return GaussianMixture(n_components=k, covariance_type=cov, n_init=n_init, random_state=seed,
                           reg_covar=1e-6, max_iter=1000).fit(X)


def n_params(gm, d):
    return gm._n_parameters()


def bic_curve(X, cov, ks=(1, 2, 3, 4), seed=SEED):
    out = {}
    for k in ks:
        if k > len(X) - 1:
            continue
        gm = fit_gmm(X, k, cov, seed)
        out[k] = dict(bic=float(gm.bic(X)), params=int(gm._n_parameters()), model=gm,
                      sizes=sorted(Counter(gm.predict(X)).values(), reverse=True))
    best = min(out, key=lambda k: out[k]['bic'])
    best2 = min((k for k in out if k >= 2), key=lambda k: out[k]['bic'])
    return out, best, best2, out[1]['bic'] - out[best2]['bic']


def jaccard_boot(X, k, cov, B=B_BOOT, seed=SEED):
    """Hennig clusterboot: per original cluster, mean over bootstraps of the best Jaccard match,
    both partitions restricted to the points drawn into the bootstrap sample."""
    rng = np.random.default_rng(seed)
    base = fit_gmm(X, k, cov, seed).predict(X)
    labs = sorted(set(base))
    J = {c: [] for c in labs}
    n = len(X)
    for bi in range(B):
        idx = rng.integers(0, n, n)
        uniq = np.unique(idx)
        try:
            gm = fit_gmm(X[idx], k, cov, seed + bi + 1, n_init=5)
        except Exception:
            continue
        bl = gm.predict(X[uniq])
        ol = base[uniq]
        for c in labs:
            A = set(uniq[ol == c])
            if not A:
                continue
            best = 0.0
            for c2 in set(bl):
                Bs = set(uniq[bl == c2])
                best = max(best, len(A & Bs) / len(A | Bs))
            J[c].append(best)
    return {int(c): float(np.mean(v)) for c, v in J.items()}, base


def perm_ari(a, b, n=5000, seed=SEED):
    rng = np.random.default_rng(seed)
    obs = adjusted_rand_score(a, b)
    null = np.array([adjusted_rand_score(a, rng.permutation(b)) for _ in range(n)])
    return float(obs), float((np.sum(null >= obs) + 1) / (n + 1))


def run_pipeline(Z, label, covs=('diag',), use_pca=True, npc=None, show=True):
    """Z: n x p standardised matrix. Returns dict with BIC table for each covariance type."""
    if use_pca:
        pca, ev, keep = kaiser_pcs(Z)
        if npc is not None:
            keep = npc
        X = pca.transform(Z)[:, :keep]
    else:
        X, keep = Z, Z.shape[1]
    res = {}
    for cov in covs:
        curve, best, best2, dbic = bic_curve(X, cov)
        res[cov] = dict(curve=curve, best=best, best2=best2, dbic=dbic, X=X, dims=keep)
        if show:
            print('  %-34s cov=%-9s dims=%2d | ' % (label, cov, keep)
                  + '  '.join('k%d BIC=%7.1f (p=%d, sizes=%s)' % (k, v['bic'], v['params'], v['sizes'])
                              for k, v in curve.items())
                  + ' | best k=%d, dBIC(k1 - best k>=2)=%.1f' % (best, dbic)
                  + ' | [post hoc] best k with every cluster >= %d people: %d' % (MIN_SIZE, constrained_best(curve)))
    return res


MIN_SIZE = 4  # post hoc: a 'type' of 1-3 people out of 33 is an outlier, not an archetype


def constrained_best(curve):
    ok = [k for k, v in curve.items() if min(v['sizes']) >= MIN_SIZE]
    return min(ok, key=lambda k: curve[k]['bic'])


def null_calibration(Zdf, n_sims, rng, label, observed):
    """Gaussian-copula null: one latent Gaussian with the observed rank correlation, pushed through
    each feature's empirical quantile function -- skew, ceilings and ties kept, no clusters."""
    Rk = np.corrcoef(rank_normal(Zdf)[FEATURES].values.T)
    Lc = np.linalg.cholesky(Rk + 1e-9 * np.eye(len(FEATURES)))
    emp = Zdf[FEATURES].values
    n = len(emp)
    nulls = []
    for i in range(n_sims):
        G = rng.standard_normal((n, len(FEATURES))) @ Lc.T
        U = stats.norm.cdf(G)
        Xs = np.column_stack([np.quantile(emp[:, j], U[:, j], method='inverted_cdf')
                              for j in range(len(FEATURES))])
        Xs = (Xs - Xs.mean(0)) / np.where(Xs.std(0) > 0, Xs.std(0), 1)
        try:
            pc, evs, kp = kaiser_pcs(Xs)
            Xp = pc.transform(Xs)[:, :kp]
            bic = {k: fit_gmm(Xp, k, 'diag', seed=SEED + i, n_init=5).bic(Xp) for k in (1, 2, 3, 4)}
            nulls.append((min(bic, key=bic.get), bic[1] - min(bic[k] for k in (2, 3, 4))))
        except Exception:
            continue
    nb = np.array([x[0] for x in nulls])
    nd = np.array([x[1] for x in nulls])
    print('%s: null sims %d: best k >= 2 in %.0f%%, dBIC > 10 in %.0f%%, dBIC 95th pct = %.1f; '
          'observed dBIC = %.1f (share of null dBIC >= observed: %.2f)'
          % (label, len(nulls), 100 * np.mean(nb >= 2), 100 * np.mean(nd > 10),
             np.percentile(nd, 95), observed, np.mean(nd >= observed)))


def spearman_ci(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = ~(np.isnan(x) | np.isnan(y))
    x, y = x[ok], y[ok]
    r, p = stats.spearmanr(x, y)
    n = len(x)
    z, se = np.arctanh(r), 1.06 / np.sqrt(max(n - 3, 1))  # Fieller et al. SE for Spearman
    return dict(rho=float(r), lo=float(np.tanh(z - 1.96 * se)), hi=float(np.tanh(z + 1.96 * se)),
                p=float(p), n=int(n))


# ── 3 · main ────────────────────────────────────────────────────────────────────────────────

def main():
    S, T, R, SESS = parse()
    pids = sorted(S.pid.unique())
    v112 = sorted(SESS[SESS.vrank >= sa.vrank('study-v1.12')].pid.unique())
    v112 = [p for p in v112 if SESS[SESS.pid == p].vrank.min() >= sa.vrank('study-v1.12')]
    hdr('DATA')
    print('participants %d (P09 excluded); v1.12+ cohort %d' % (len(pids), len(v112)))
    print('strategic decisions %d, tactical confirms %d, recovery episodes %d, sessions %d'
          % (len(S), len(T), len(R), len(SESS)))

    # validation against the builder's decision table
    D = b.load_decisions()
    chk = pd.concat([S.groupby('pid').took.mean().rename('mine'),
                     D.groupby('pid').took.mean().rename('builder')], axis=1)
    print('check: per-person card uptake matches build_findings_synthesis.load_decisions: max |diff| = %.2g, n rows %d vs %d'
          % ((chk.mine - chk.builder).abs().max(), len(S), len(D)))
    print('check: |time-to-choice - logged latencyMs| not computed (timestamp difference used, as in the builder)')
    print('reveal delay (s): mean %.2f, range %.2f-%.2f; net decision time median %.1f s (raw %.1f s)'
          % (S.reveal.mean(), S.reveal.min(), S.reveal.max(), S.net.median(), S.secs.median()))

    # person features --------------------------------------------------------------------------
    hdr('FEATURES (per person, both sessions pooled)')
    F = features(S, T, R, 'pid')
    F['pid'] = F.key
    F = F.set_index('pid').loc[pids].reset_index()
    print(F[['pid', 'nS', 'nMan', 'nT', 'nR'] + FEATURES].round(2).to_string(index=False))
    print('\nraw feature summary:')
    print(F[FEATURES].describe().T[['mean', 'std', 'min', '50%', 'max']].round(2).to_string())
    print('\nskewness:', {c: round(float(stats.skew(F[c].dropna())), 2) for c in FEATURES})
    Zdf, _ = impute_z(F)
    Z = Zdf[FEATURES].values
    corr = pd.DataFrame(Z, columns=FEATURES).corr(method='spearman')
    print('\nSpearman correlations between features:')
    print(corr.round(2).to_string())

    # PCA --------------------------------------------------------------------------------------
    hdr('PCA of the 10 standardised features (the continuum)')
    pca, ev, keep = kaiser_pcs(Z)
    print('eigenvalues:', np.round(ev, 2))
    print('variance explained:', np.round(pca.explained_variance_ratio_, 3),
          ' cumulative:', np.round(np.cumsum(pca.explained_variance_ratio_), 3))
    print('Kaiser (eigenvalue > 1) keeps %d components' % keep)
    # Horn parallel analysis, 5000 sims, 95th percentile
    rng = np.random.default_rng(SEED)
    sims = []
    for _ in range(5000):
        Q = rng.standard_normal(Z.shape)
        Q = (Q - Q.mean(0)) / Q.std(0)
        sims.append(np.sort(np.linalg.eigvalsh(np.corrcoef(Q.T)))[::-1])
    sims = np.array(sims)
    thr95, thr50 = np.percentile(sims, 95, axis=0), np.percentile(sims, 50, axis=0)
    npa = int(np.argmax(ev <= thr95)) if (ev <= thr95).any() else len(ev)
    print('parallel analysis 95th pct thresholds:', np.round(thr95[:5], 2), '-> retain %d' % npa)
    print('parallel analysis median thresholds  :', np.round(thr50[:5], 2), '-> retain %d'
          % (int(np.argmax(ev <= thr50)) if (ev <= thr50).any() else len(ev)))
    # Orientation (sign is arbitrary): PC1 positive = more card uptake; PC2 positive = more drones
    # committed on multi-type missions.
    if pca.components_[0][FEATURES.index('took')] < 0:
        pca.components_[0] *= -1
    if pca.components_[1][FEATURES.index('dLarge')] < 0:
        pca.components_[1] *= -1
    load = pd.DataFrame(pca.components_[:4].T * np.sqrt(ev[:4]), index=FEATURES,
                        columns=['PC%d' % i for i in range(1, 5)])
    print('\nloadings (component x sqrt(eigenvalue), i.e. correlation with the PC):')
    print(load.round(2).to_string())
    # bootstrap stability of PC1/PC2 loadings (Tucker congruence with the full-sample loading)
    cong = {1: [], 2: []}
    for bi in range(1000):
        idx = rng.integers(0, len(Z), len(Z))
        Zb = Z[idx]
        Zb = (Zb - Zb.mean(0)) / np.where(Zb.std(0) > 0, Zb.std(0), 1)
        pb = PCA().fit(Zb)
        for j in (1, 2):
            v, w = pca.components_[j - 1], pb.components_[j - 1]
            cong[j].append(abs(v @ w) / (np.linalg.norm(v) * np.linalg.norm(w)))
    print('bootstrap Tucker congruence of PC loadings with full sample (median [2.5%, 97.5%]):')
    for j in (1, 2):
        print('  PC%d: %.2f [%.2f, %.2f]  share >= .85: %.2f' % (
            j, np.median(cong[j]), *np.percentile(cong[j], [2.5, 97.5]), np.mean(np.array(cong[j]) >= .85)))
    scores = pca.transform(Z)
    PCS = pd.DataFrame({'pid': pids, 'PC1': scores[:, 0], 'PC2': scores[:, 1], 'PC3': scores[:, 2]})

    # PRIMARY ----------------------------------------------------------------------------------
    hdr('PRIMARY TEST -- diag GMM on Kaiser-retained PC scores, k = 1..4, BIC')
    prim = run_pipeline(Z, 'ALL 33 (primary)', covs=('diag',))['diag']
    k_best, dbic = prim['best'], prim['dbic']
    criterion1 = (k_best >= 2) and dbic > 10
    print('criterion 1 (k>=2 wins and dBIC > 10): %s  [best k = %d, dBIC = %.1f]'
          % (criterion1, k_best, dbic))
    k_eval = k_best if k_best >= 2 else 2
    note = '' if k_best >= 2 else ' (k=1 won; k=2 evaluated descriptively only)'
    J, base_labels = jaccard_boot(prim['X'], k_eval, 'diag')
    print('criterion 2: bootstrap Jaccard at k=%d%s: %s  min = %.2f  -> %s'
          % (k_eval, note, {c: round(v, 2) for c, v in J.items()}, min(J.values()),
             min(J.values()) >= .75))

    # session split
    FS = features(S, T, R, ['pid', 'run'])
    FS['pid'] = [k[0] for k in FS.key]
    FS['run'] = [k[1] for k in FS.key]
    scen = SESS.set_index(['pid', 'run']).scenario
    FS['scenario'] = [scen.get((p, r)) for p, r in zip(FS.pid, FS.run)]
    FS['cell'] = FS.run.astype(str) + FS.scenario
    print('\nsession-level feature missingness (before imputation):')
    print({c: int(FS[c].isna().sum()) for c in FEATURES}, ' of', len(FS), 'sessions')
    FSz, _ = impute_z(FS, by='cell')
    sess_labels = {}
    for run in (1, 2):
        sub = FSz[FSz.run == run].set_index('pid').loc[pids]
        Zr = sub[FEATURES].values
        res = run_pipeline(Zr, 'session %d alone' % run, covs=('diag',))['diag']
        g = fit_gmm(res['X'], k_eval, 'diag')
        sess_labels[run] = g.predict(res['X'])
    ari, p_ari = perm_ari(sess_labels[1], sess_labels[2])
    ari_full1 = adjusted_rand_score(base_labels, sess_labels[1])
    ari_full2 = adjusted_rand_score(base_labels, sess_labels[2])
    print('criterion 3: ARI(session 1 partition, session 2 partition) at k=%d = %.2f, permutation p = %.3f'
          % (k_eval, ari, p_ari))
    print('   (pooled partition vs session 1: ARI %.2f; vs session 2: ARI %.2f)' % (ari_full1, ari_full2))
    print('   crosstab s1 x s2:\n', pd.crosstab(sess_labels[1], sess_labels[2]).to_string())
    verdict = 'SUPPORTED' if (criterion1 and min(J.values()) >= .75 and ari >= .5) else 'NOT SUPPORTED'
    print('\nPRIMARY VERDICT: %s' % verdict)

    # session-level continuity of the continuum (PC1 per session)
    for run in (1, 2):
        sub = FSz[FSz.run == run].set_index('pid').loc[pids]
        PCS['s%d_PC1' % run] = sub[FEATURES].values @ pca.components_[0]
        PCS['s%d_PC2' % run] = sub[FEATURES].values @ pca.components_[1]
    r1 = spearman_ci(PCS.s1_PC1, PCS.s2_PC1)
    r2 = spearman_ci(PCS.s1_PC2, PCS.s2_PC2)
    print('\ncontinuum stability: session-1 vs session-2 score on the pooled PC1 axis rho = %.2f [%.2f, %.2f] p = %.2g n = %d'
          % (r1['rho'], r1['lo'], r1['hi'], r1['p'], r1['n']))
    print('                     ... on the pooled PC2 axis rho = %.2f [%.2f, %.2f] p = %.2g'
          % (r2['rho'], r2['lo'], r2['hi'], r2['p']))
    print('per-feature session-1 vs session-2 Spearman (cell-standardised):')
    for c in FEATURES:
        a = FS[FS.run == 1].set_index('pid')[c].reindex(pids)
        bb = FS[FS.run == 2].set_index('pid')[c].reindex(pids)
        r = spearman_ci(a, bb)
        print('   %-9s rho = %5.2f [%5.2f, %5.2f]  p = %.3f  n = %d' % (c, r['rho'], r['lo'], r['hi'], r['p'], r['n']))

    # SENSITIVITY v1.12+ ----------------------------------------------------------------------
    hdr('SENSITIVITY -- v1.12+ cohort (re-standardised within the cohort)')
    Fv = F[F.pid.isin(v112)].reset_index(drop=True)
    Zv = impute_z(Fv)[0][FEATURES].values
    pv = run_pipeline(Zv, 'v1.12+ (n=%d)' % len(Fv), covs=('diag',))['diag']
    kv = pv['best'] if pv['best'] >= 2 else 2
    Jv, _ = jaccard_boot(pv['X'], kv, 'diag')
    sl = {}
    for run in (1, 2):
        sub = FS[(FS.run == run) & FS.pid.isin(v112)].copy()
        subz = impute_z(sub, by='cell', verbose=False)[0].set_index('pid').loc[v112]
        rr = run_pipeline(subz[FEATURES].values, 'v1.12+ session %d' % run, covs=('diag',))['diag']
        sl[run] = fit_gmm(rr['X'], kv, 'diag').predict(rr['X'])
    ariv, pariv = perm_ari(sl[1], sl[2])
    print('v1.12+: best k = %d, dBIC = %.1f; Jaccard at k=%d %s (min %.2f); session ARI %.2f (p = %.3f)'
          % (pv['best'], pv['dbic'], kv, {c: round(v, 2) for c, v in Jv.items()}, min(Jv.values()),
             ariv, pariv))
    print('v1.12+ VERDICT: %s' % ('SUPPORTED' if (pv['best'] >= 2 and pv['dbic'] > 10 and
                                               min(Jv.values()) >= .75 and ariv >= .5)
                                  else 'NOT SUPPORTED'))

    # ROBUSTNESS GRID -------------------------------------------------------------------------
    hdr('ROBUSTNESS GRID (all 33 unless stated) -- BIC by k; dBIC = BIC(k=1) - BIC(best k>=2)')
    grid = []

    def g(label, Zm, covs, use_pca=True, npc=None):
        res = run_pipeline(Zm, label, covs=covs, use_pca=use_pca, npc=npc)
        for cov, v in res.items():
            grid.append(dict(spec=label, cov=cov, dims=v['dims'], best=v['best'], dbic=round(v['dbic'], 1)))

    g('PCA 1 component', Z, ('full',), npc=1)
    g('PCA 2 components', Z, ('diag', 'full', 'tied', 'spherical'), npc=2)
    g('PCA 3 components', Z, ('diag', 'full', 'tied', 'spherical'), npc=3)
    g('PCA all 10 (rotation only)', Z, ('diag', 'spherical'), npc=10)
    g('raw z-features (no PCA)', Z, ('diag', 'spherical'), use_pca=False)
    Zr = rank_normal(Zdf)[FEATURES].values
    g('rank-normal features, Kaiser PCs', Zr, ('diag',))
    g('rank-normal features, no PCA', Zr, ('diag',), use_pca=False)
    Fm = features(S, T, R, 'pid', manual_only_delta=True)
    Fm['pid'] = Fm.key
    Fm = Fm.set_index('pid').loc[pids].reset_index()
    print('  (manual-only dSmall/dLarge missing for %d / %d people before imputation)'
          % (Fm.dSmall.isna().sum(), Fm.dLarge.isna().sum()))
    Zm = impute_z(Fm, verbose=False)[0][FEATURES].values
    g('manual-only dSmall/dLarge, Kaiser PCs', Zm, ('diag',))
    core = ['took', 'preempt', 'edit', 'consult', 'keep', 'netSecs']
    Zc = impute_z(F, cols=core, verbose=False)[0][core].values
    g('6 core features, Kaiser PCs', Zc, ('diag',))
    g('6 core features, no PCA', Zc, ('diag', 'spherical'), use_pca=False)
    print('\nsummary: %d specifications, %d with best k >= 2, %d with dBIC > 10'
          % (len(grid), sum(x['best'] >= 2 for x in grid), sum(x['dbic'] > 10 for x in grid)))
    for x in grid:
        if x['best'] >= 2 or x['dbic'] > 0:
            print('   k>=2 preferred or dBIC>0:', x)

    hdr('NULL CALIBRATION -- Gaussian-copula null with the observed marginals and correlation')
    null_calibration(Zdf, 200, rng, 'all 33, primary spec', dbic)
    null_calibration(impute_z(Fv, verbose=False)[0], 200, rng, 'v1.12+ n=24, primary spec', pv['dbic'])

    # POST HOC: previews is near-mechanically tied to taking a card (choosing a card means clicking
    # it), rho ~ .8 with uptake. Swap it for A<->C toggles per decision (genuine comparison).
    hdr('POST HOC -- previews replaced by card toggles per decision')
    F2 = F.copy()
    F2['previews'] = F2['toggles']
    print('toggles per decision: mean %.2f, sd %.2f; Spearman with took = %.2f'
          % (F2.toggles.mean(), F2.toggles.std(), stats.spearmanr(F2.toggles, F2.took)[0]))
    Z2 = impute_z(F2, verbose=False)[0][FEATURES].values
    pt = run_pipeline(Z2, 'toggles instead of previews', covs=('diag',))['diag']
    Jt, _ = jaccard_boot(pt['X'], max(pt['best'], 2), 'diag', B=200)
    print('  Jaccard at k=%d: %s' % (max(pt['best'], 2), {c: round(v, 2) for c, v in Jt.items()}))

    # SECONDARY -------------------------------------------------------------------------------
    hdr('SECONDARY (exploratory) -- what the axes / forced-k=2 groups mean')
    PCS['cluster2'] = base_labels
    desc = F.assign(cluster2=base_labels).groupby('cluster2')[FEATURES].mean().T
    desc.columns = ['k2 group %d (n=%d)' % (c, (base_labels == c).sum()) for c in desc.columns]
    print('forced k=2 (primary spec) group means of RAW features -- descriptive only:')
    print(desc.round(2).to_string())
    print('forced k=2 membership:', {int(c): [p for p, l in zip(pids, base_labels) if l == c]
                                       for c in sorted(set(base_labels))})
    # dip test proxy: bimodality coefficient of PC1
    for j in (1, 2):
        x = scores[:, j - 1]
        n = len(x)
        bc = (stats.skew(x) ** 2 + 1) / (stats.kurtosis(x) + 3 * (n - 1) ** 2 / ((n - 2) * (n - 3)))
        print('PC%d bimodality coefficient = %.3f (> .555 suggests bimodality); Shapiro p = %.3f'
              % (j, bc, stats.shapiro(x).pvalue))
    print('PC1 sorted scores:', ', '.join('%s %.1f' % (p, v) for p, v in
                                         sorted(zip(pids, scores[:, 0]), key=lambda t: t[1])))

    # outcomes
    sess_l, people = b.load_people()
    per = b.per_person(sess_l, ['trust_s', 'trust_t', 'rtlx'])
    bench = b.benchmark(D)
    bs = pd.DataFrame(bench['sessions'])
    share = bs.groupby('pid').share.mean()
    SE = SESS.copy()
    SE['gameKey'] = SE.scenario + '|' + SE.gameIndex.astype(str)
    SE['scoreEffRes'] = SE.scoreEff - SE.groupby('gameKey').scoreEff.transform('mean')
    effres = SE.groupby('pid').scoreEffRes.mean()
    O = pd.DataFrame({
        'benchShare': share.reindex(pids),
        'scoreEffGameRes': effres.reindex(pids),
        'trust_s': [per[p]['trust_s'] for p in pids],
        'trust_t': [per[p]['trust_t'] for p in pids],
        'trust_gap': [(per[p]['trust_t'] - per[p]['trust_s']) if None not in (per[p]['trust_t'], per[p]['trust_s']) else np.nan for p in pids],
        'rtlx': [per[p]['rtlx'] for p in pids],
        'aias': [people[p].get('aias') for p in pids],
        'verification': [people[p].get('verification') for p in pids],
        'delegation': [people[p].get('delegation') for p in pids]}, index=pids).astype(float)
    print('\ngame-effect check: mean scoreEff by game:', SE.groupby('gameKey').scoreEff.mean().round(3).to_dict())
    rows = []
    for ax in ('PC1', 'PC2'):
        for o in O.columns:
            r = spearman_ci(PCS[ax].values, O[o].values)
            rows.append(dict(axis=ax, outcome=o, **r))
    for o in O.columns:
        a = O[o].values[base_labels == 0]
        c = O[o].values[base_labels == 1]
        a, c = a[~np.isnan(a)], c[~np.isnan(c)]
        u = stats.mannwhitneyu(a, c)
        rows.append(dict(axis='k2 groups (MWU)', outcome=o, rho=float(np.mean(a) - np.mean(c)),
                         lo=np.nan, hi=np.nan, p=float(u.pvalue), n=len(a) + len(c)))
    res = pd.DataFrame(rows)
    res['holm'] = b.holm(list(res.p))
    print('\naxes / groups vs held-out outcomes (Spearman rho [95% CI]; for k2 rows "rho" = mean diff group0-group1):')
    print(res.round(3).to_string(index=False))
    zb = stats.norm.ppf(.8) + stats.norm.ppf(.975)
    print('detectable |rho| at 80%% power, n=33: %.2f' % np.tanh(zb / np.sqrt(30)))

    # session-level score efficiency within person: does the session with higher PC1 score better?
    long = []
    for run in (1, 2):
        sub = SE[SE.run == run].set_index('pid')
        for p in pids:
            if p in sub.index:
                long.append(dict(pid=p, run=run, pc1=PCS.set_index('pid').loc[p, 's%d_PC1' % run],
                                 eff=sub.loc[p, 'scoreEffRes']))
    L = pd.DataFrame(long)
    L['pc1_w'] = L.pc1 - L.groupby('pid').pc1.transform('mean')
    L['pc1_b'] = L.groupby('pid').pc1.transform('mean')
    m = b.gee('eff ~ pc1_w + pc1_b', L)
    print('\nGEE (session level): game-residualised score efficiency ~ within + between PC1:')
    for t in ('pc1_w', 'pc1_b'):
        tt = b.term(m, t)
        print('   %s b = %.4f [%.4f, %.4f] p = %.3f' % (t, tt['b'], tt['lo'], tt['hi'], tt['p']))

    # stance cross-tab
    q = b.load_quotes()
    st = defaultdict(set)
    for x in q['quotes']:
        if x['theme'] == 'agent_comparison' and x.get('stance'):
            st[x['pid']].add(x['stance'])
    print('\ndebrief stance (agent_comparison quotes; a person may hold >1) vs axis scores and k2 group:')
    tab = []
    P = PCS.set_index('pid')
    for p in pids:
        for s_ in sorted(st.get(p, [])):
            tab.append(dict(pid=p, stance=s_, PC1=P.loc[p, 'PC1'], PC2=P.loc[p, 'PC2'],
                            k2=int(P.loc[p, 'cluster2'])))
    tab = pd.DataFrame(tab)
    print('coded people: %d of %d' % (len(st), len(pids)))
    print(tab.groupby('stance').agg(n=('pid', 'size'), PC1_mean=('PC1', 'mean'),
                                     PC1_sd=('PC1', 'std'), PC2_mean=('PC2', 'mean'),
                                     k2_group1=('k2', 'sum')).round(2).to_string())
    print(pd.crosstab(tab.stance, tab.k2).to_string())
    # stance -> PC1 Kruskal across the three stances with n >= 5
    big = [s_ for s_, g_ in tab.groupby('stance') if len(g_) >= 5]
    if len(big) >= 2:
        kw = stats.kruskal(*[tab[tab.stance == s_].PC1 for s_ in big])
        print('Kruskal-Wallis PC1 across stances with n>=5 (%s): H = %.2f p = %.3f'
              % (', '.join(big), kw.statistic, kw.pvalue))
        kw2 = stats.kruskal(*[tab[tab.stance == s_].PC2 for s_ in big])
        print('Kruskal-Wallis PC2 across the same stances: H = %.2f p = %.3f' % (kw2.statistic, kw2.pvalue))
    print('\nper-person axis scores:')
    print(PCS[['pid', 'PC1', 'PC2', 'cluster2', 's1_PC1', 's2_PC1']].round(2).to_string(index=False))


if __name__ == '__main__':
    main()
