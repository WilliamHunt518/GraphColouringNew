"""H7 -- Does disposition toward AI affect uptake and trust, for one assistant or both?

Pre-registered in docs/analysis/HYPOTHESES_ROUND1.md (H7, signed off 2026-10-07).

PRIMARY (confirmatory, one test): AIAS-4, z-scored across the 32 people who have it, as a
person-level covariate in the decision-level binomial GEE for card-taking (`took`), controlling for
composition (ncolours, ndrones), scenario, run and position (idx), exchangeable working correlation
clustered on participant. Support = AIAS odds-ratio 95% CI excluding 1.

Everything else in this file is EXPLORATORY and is numbered in the order it was tried (see the
analysis log in docs/analysis/round1/h7_disposition.md).

Read-only on the data. Reuses load_decisions / load_people / per_person / gee / term / alpha from
scripts/build_findings_synthesis.py and score_attitudes (via load_people) from
scripts/agent_scenario_stats.py -- nothing is re-scored here.

Run from the repo root:
    C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h7_disposition.py [--nsim 400]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'scripts'))
from build_findings_synthesis import (EXCLUDE, PARTICIPANTS, alpha, gee, load_decisions,  # noqa: E402
                                      load_people, per_person, term)
from agent_scenario_stats import AIAS_ITEMS  # noqa: E402
from study_analysis import spearman  # noqa: E402

warnings.filterwarnings('ignore')   # GEE/scipy convergence chatter; every fit is checked below
V112 = {'study-v1.12', 'study-v1.13'}
COVARS = 'ncolours + ndrones + C(scenario) + C(run) + idx'


def gee_safe(formula, data, binomial=False):
    """build_findings_synthesis.gee (exchangeable); if that fit diverges (NaN or not converged),
    refit with an independence working correlation -- still cluster-robust -- and say so."""
    m = gee(formula, data, binomial=binomial)
    if np.all(np.isfinite(m.params)) and getattr(m, 'converged', True):
        return m, 'exchangeable'
    fam = sm.families.Binomial() if binomial else sm.families.Gaussian()
    return smf.gee(formula, 'pid', data=data, family=fam,
                   cov_struct=sm.cov_struct.Independence()).fit(), 'independence (exchangeable diverged)'


def hr(title):
    print('\n' + '=' * 100 + '\n' + title + '\n' + '=' * 100)


def orfmt(t, per='per SD'):
    return (f"OR {per} = {np.exp(t['b']):.3f}  95% CI [{np.exp(t['lo']):.3f}, {np.exp(t['hi']):.3f}]"
            f"  (b = {t['b']:+.3f}, p = {t['p']:.4f})")


# ── data ──────────────────────────────────────────────────────────────────────────────────────

def zscore_people(people, key):
    """Person-level z: mean/SD over PEOPLE (one value each), not over decisions."""
    v = {p: people[p][key] for p in people if people[p].get(key) is not None}
    a = np.array(list(v.values()), float)
    return {p: (x - a.mean()) / a.std(ddof=1) for p, x in v.items()}, a.mean(), a.std(ddof=1)


def session_versions():
    out = {}
    for path in sorted(glob.glob(str(PARTICIPANTS / 'P*.json'))):
        pid = os.path.splitext(os.path.basename(path))[0]
        if pid in EXCLUDE:
            continue
        log = json.loads(Path(path).read_text(encoding='utf-8'))
        out[pid] = [next((e.get('appVersion') for e in s if e['type'] == 'session_start'), None)
                    for s in log['sessions']]
    return out


def load_tactical():
    """One row per tactical_confirmed. Definitions copied from load_people() so person rates match:
    consult = Suggest pressed at least once; accept = consulted AND agent plan deployed unmodified."""
    rows = []
    for path in sorted(glob.glob(str(PARTICIPANTS / 'P*.json'))):
        pid = os.path.splitext(os.path.basename(path))[0]
        if pid in EXCLUDE:
            continue
        log = json.loads(Path(path).read_text(encoding='utf-8'))
        for run, events in enumerate(log['sessions'], start=1):
            scen = next((e.get('complexity') for e in events if e['type'] == 'session_start'), None)
            idx = 0
            for e in events:
                if e['type'] != 'tactical_confirmed':
                    continue
                consulted = (e.get('suggestUsedCount') or 0) > 0
                fp = e.get('finalPlan') or []
                rows.append(dict(pid=pid, run=run, scenario=scen, idx=idx,
                                 consult=int(consulted),
                                 accept=int(consulted and bool(e.get('agentPlan'))
                                            and not e.get('modifiedFromAgentPlan')),
                                 ntasks=len(fp),
                                 ndrones=len(set(e.get('assetsDeployed') or []))))
                idx += 1
    return pd.DataFrame(rows)


# ── Steiger (1980) test for two dependent correlations sharing one variable ─────────────────────

def steiger(r12, r13, r23, n):
    """H0: rho12 == rho13, where 1 = AIAS, 2 and 3 = the two tier measures, r23 their correlation.

    Steiger (1980), eq. 15 (pooled-r version, 'Z2*'):
        z_ij = atanh(r_ij);  rbar = (r12 + r13) / 2
        psi  = r23 * (1 - 2 rbar^2) - 0.5 * rbar^2 * (1 - 2 rbar^2 - r23^2)
        c    = psi / (1 - rbar^2)^2                (covariance of z12 and z13, times n-3)
        Z    = (z12 - z13) * sqrt(n - 3) / sqrt(2 - 2c)
    Two-sided p from N(0,1). Applied to Spearman rho it is an approximation (rank correlations'
    Fisher-z variance is ~1.06/(n-3)); a person-bootstrap CI on the difference is reported alongside.
    """
    rbar = (r12 + r13) / 2
    psi = r23 * (1 - 2 * rbar ** 2) - 0.5 * rbar ** 2 * (1 - 2 * rbar ** 2 - r23 ** 2)
    c = psi / (1 - rbar ** 2) ** 2
    z = (np.arctanh(r12) - np.arctanh(r13)) * np.sqrt(n - 3) / np.sqrt(2 - 2 * c)
    return float(z), float(2 * stats.norm.sf(abs(z)))


def boot_diff(x, y1, y2, method, nboot=5000, seed=7):
    rng = np.random.default_rng(seed)
    x, y1, y2 = map(np.asarray, (x, y1, y2))
    corr = (lambda a, b: stats.spearmanr(a, b)[0]) if method == 'spearman' else \
        (lambda a, b: np.corrcoef(a, b)[0, 1])
    d = []
    for _ in range(nboot):
        i = rng.integers(0, len(x), len(x))
        d.append(corr(x[i], y1[i]) - corr(x[i], y2[i]))
    d = np.array(d)
    d = d[~np.isnan(d)]
    return float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def dependent_pair(label, ids, x, y1, y2):
    ok = [i for i in range(len(ids)) if None not in (x[i], y1[i], y2[i])]
    xs, a, b = (np.array([v[i] for i in ok], float) for v in (x, y1, y2))
    n = len(ok)
    print(f'\n{label}   (n = {n})')
    for method in ('spearman', 'pearson'):
        if method == 'spearman':
            r12, r13, r23 = stats.spearmanr(xs, a)[0], stats.spearmanr(xs, b)[0], stats.spearmanr(a, b)[0]
        else:
            r12, r13, r23 = np.corrcoef(xs, a)[0, 1], np.corrcoef(xs, b)[0, 1], np.corrcoef(a, b)[0, 1]
        z, p = steiger(r12, r13, r23, n)
        lo, hi = boot_diff(xs, a, b, method)
        print(f'  {method:8s}: r(AIAS, strategic) = {r12:+.3f}   r(AIAS, tactical) = {r13:+.3f}   '
              f'r(strat, tact) = {r23:+.3f}   diff = {r12 - r13:+.3f}  boot95 [{lo:+.3f}, {hi:+.3f}]   '
              f'Steiger Z = {z:+.3f}, p = {p:.4f}')
    return dict(n=n)


def steiger_detectable(r23, n, target=.8, alpha_=.05):
    """Smallest difference rho12 - rho13 (centred on 0, i.e. r12 = +d/2, r13 = -d/2) Steiger could
    detect at 80% power, using the null-centred normal approximation."""
    zc = stats.norm.ppf(1 - alpha_ / 2)
    for d in np.arange(0.01, 1.5, 0.005):
        r12, r13 = d / 2, -d / 2
        rbar = 0.0
        c = r23   # psi with rbar = 0 is r23
        mu = (np.arctanh(r12) - np.arctanh(r13)) * np.sqrt(n - 3) / np.sqrt(2 - 2 * c)
        if stats.norm.sf(zc - mu) >= target:
            return float(d)
    return None


# ── power for the primary GEE by simulation ───────────────────────────────────────────────────

def simulate_power(d, nsim, seed=20261007):
    """Monte-Carlo power for the AIAS term, holding the real design fixed.

    Generating model: random-intercept logistic, fitted to the real data WITHOUT AIAS (Bayesian
    mixed GLM, variational fit) to get the fixed effects of the covariates and the between-person SD
    sigma_u. For each conditional log-OR beta per SD of AIAS: y ~ Bern(logit^-1(X b + u_pid +
    beta * aias_z)), u_pid ~ N(0, sigma_u) independent of AIAS; then refit the exact primary GEE and
    record p < .05. GEE estimates a MARGINAL OR, attenuated relative to beta, so the mean GEE
    estimate at each beta is reported too -- the detectable effect is quoted on the marginal (GEE)
    scale, which is the scale of the observed estimate.
    """
    from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM
    glmm = BinomialBayesMixedGLM.from_formula('took ~ ' + COVARS, {'pid': '0 + C(pid)'}, d).fit_vb()
    sigma_u = float(np.exp(glmm.vcp_mean[0]))
    X = np.asarray(glmm.model.exog)
    xb = X @ glmm.fe_mean
    pids = d.pid.values
    ulist = sorted(set(pids))
    pos = np.array([ulist.index(p) for p in pids])
    az = d.aias_z.values
    rng = np.random.default_rng(seed)
    print(f'  generating model: sigma_u (person SD, logit) = {sigma_u:.3f}; '
          f'ICC(latent) = {sigma_u**2 / (sigma_u**2 + np.pi**2 / 3):.3f}; nsim = {nsim} per beta')
    res, zcrit, nfail = [], None, 0
    for beta in (0.0, 0.25, 0.5, 0.75, 1.0, 1.25):
        est, zs = [], []
        for _ in range(nsim):
            u = rng.normal(0, sigma_u, len(ulist))[pos]
            p = 1 / (1 + np.exp(-(xb + u + beta * az)))
            sim = d.copy()
            sim['took'] = rng.binomial(1, p)
            try:
                mm = gee('took ~ aias_z + ' + COVARS, sim, binomial=True)
                b, se = float(mm.params['aias_z']), float(mm.bse['aias_z'])
            except Exception:
                b, se = np.nan, np.nan
            if not (np.isfinite(b) and np.isfinite(se) and se > 0):
                nfail += 1          # diverged fit: dropped from the denominator, counted below
                continue
            est.append(b)
            zs.append(b / se)
        zs = np.abs(np.array(zs))
        if beta == 0.0:
            # The robust sandwich with 32 clusters is anti-conservative; the empirical null |z| at
            # 95% gives a size-corrected critical value, so power is also quoted at a true 5% size.
            zcrit = float(np.percentile(zs, 95))
        pw = float((zs > stats.norm.ppf(.975)).mean())
        pwc = float((zs > zcrit).mean())
        res.append((beta, pw, pwc, float(np.mean(est))))
        print(f'  conditional beta = {beta:.2f} (OR {np.exp(beta):.2f})  ->  mean GEE b = '
              f'{np.mean(est):+.3f} (marginal OR {np.exp(np.mean(est)):.2f})   power nominal = {pw:.3f}'
              f'   size-corrected = {pwc:.3f}   (fits kept {len(est)})')
    print(f'  empirical type-I error of the nominal test = {res[0][1]:.3f}; size-corrected critical |z| = '
          f'{zcrit:.3f}; diverged fits dropped in total = {nfail}')
    out = dict(sigma_u=sigma_u, grid=res)
    for col, lab in ((1, 'nominal'), (2, 'size-corrected')):
        for r0, r1 in zip(res, res[1:]):
            p0, p1 = r0[col], r1[col]
            if p0 < .8 <= p1:
                w = (.8 - p0) / (p1 - p0)
                mb = r0[3] + w * (r1[3] - r0[3])
                cb = r0[0] + w * (r1[0] - r0[0])
                print(f'  [{lab}] 80% power at conditional OR ~ {np.exp(cb):.2f} per SD, i.e. marginal (GEE) '
                      f'OR ~ {np.exp(mb):.2f} per SD (or {np.exp(-mb):.2f} in the negative direction)')
                out[lab] = (float(np.exp(cb)), float(np.exp(mb)))
                break
        else:
            print(f'  [{lab}] 80% power not reached on the grid')
    return out


# ── main ──────────────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--nsim', type=int, default=400)
    args = ap.parse_args()

    df = load_decisions()
    sess, people = load_people()
    vers = session_versions()
    az, amean, asd = zscore_people(people, 'aias')
    v112 = sorted(p for p in vers if all(v in V112 for v in vers[p]))

    hr('0 - Data')
    print(f'participants (P09 excluded): {len(people)};  with AIAS-4: {len(az)};  missing: '
          f'{sorted(set(people) - set(az))}')
    print(f'AIAS-4 (1-10): mean {amean:.3f}, SD {asd:.3f}, min {min(people[p]["aias"] for p in az):.2f}, '
          f'max {max(people[p]["aias"] for p in az):.2f}')
    vals = np.array([people[p]['aias'] for p in az])
    print(f'  share >= 7: {(vals >= 7).mean():.3f};  share <= 5.5 (scale midpoint): {(vals <= 5.5).mean():.3f};'
          f'  share at 10: {(vals == 10).mean():.3f}')
    print(f'  distribution: {sorted(vals.tolist())}')
    raw = [[people[p]['raw'][k] for k in AIAS_ITEMS] for p in az]
    print(f'  Cronbach alpha (recomputed via build_findings_synthesis.alpha): {alpha(raw):.3f}')
    print(f'v1.12+ cohort ({len(v112)}): {v112}')
    df['aias_z'] = df.pid.map(az)
    d = df.dropna(subset=['aias_z']).copy()
    print(f'strategic decisions: all {len(df)}; with AIAS {len(d)} from {d.pid.nunique()} people; '
          f'residual rows {int(d.residual.sum())}; took rate {d.took.mean():.3f}')

    # ── 1 · PRIMARY ──────────────────────────────────────────────────────────────────────────
    hr('1 - PRIMARY (confirmatory): took ~ aias_z + ncolours + ndrones + C(scenario) + C(run) + idx, '
       'binomial GEE, exchangeable, clustered on pid')
    m = gee('took ~ aias_z + ' + COVARS, d, binomial=True)
    t = term(m, 'aias_z')
    print(m.summary().tables[1])
    print(f'\nPRIMARY  AIAS-4 {orfmt(t)}   n = {len(d)} decisions, {d.pid.nunique()} people')
    print(f'  per scale point (1/SD = 1/{asd:.3f}): OR = {np.exp(t["b"] / asd):.3f} '
          f'[{np.exp(t["lo"] / asd):.3f}, {np.exp(t["hi"] / asd):.3f}]')
    print('  VERDICT: ' + ('SUPPORTED' if (t['lo'] > 0 or t['hi'] < 0) else 'NOT SUPPORTED'))
    # robust vs naive SE check
    print(f'  naive (model-based) SE p for aias_z: '
          f'{float(m.model.fit(cov_type="naive").pvalues["aias_z"]):.4f}  (robust above is primary)')
    mb = m.model.fit(cov_type='bias_reduced')
    ci = mb.conf_int().loc['aias_z']
    print(f'  Mancl-DeRouen bias-reduced sandwich (32 clusters is few): OR {np.exp(mb.params["aias_z"]):.3f} '
          f'[{np.exp(ci[0]):.3f}, {np.exp(ci[1]):.3f}] p = {float(mb.pvalues["aias_z"]):.4f}')

    hr('1b - Detectable effect for the primary GEE (Monte-Carlo, design held fixed)')
    power = simulate_power(d, args.nsim)
    n = d.pid.nunique()
    zb = stats.norm.ppf(.8) + stats.norm.ppf(.975)
    print(f'  cross-check, person-level Spearman detectable rho at n = {n}: '
          f'{np.tanh(zb / np.sqrt(n - 3)):.3f}')

    # ── 2 · v1.12+ sensitivity ─────────────────────────────────────────────────────────────
    hr('2 - Sensitivity: primary re-run on the study-v1.12+ cohort')
    dv = d[d.pid.isin(v112)].copy()
    # z is kept on the full-sample scale so ORs are per the same SD; a cohort re-z is printed too
    mv = gee('took ~ aias_z + ' + COVARS, dv, binomial=True)
    tv = term(mv, 'aias_z')
    print(f'v1.12+  AIAS-4 {orfmt(tv)}   n = {len(dv)} decisions, {dv.pid.nunique()} people')
    zc, _, sdc = zscore_people({p: people[p] for p in v112}, 'aias')
    dv['aias_zc'] = dv.pid.map(zc)
    tvc = term(gee('took ~ aias_zc + ' + COVARS, dv, binomial=True), 'aias_zc')
    print(f'v1.12+  (re-z within cohort, SD {sdc:.3f}) {orfmt(tvc)}')
    # v1.13 runs carry planSeedIndex; game is not needed for an uptake outcome per §1 (performance
    # outcomes only), but checked as a robustness term below.

    # ── 3 · asymmetry ─────────────────────────────────────────────────────────────────────────
    keys = ['took', 'consult', 'accept', 'trust_s', 'trust_t']
    per = per_person(sess, keys)
    ids = sorted(az)
    A = [people[p]['aias'] for p in ids]
    col = lambda k: [per[p][k] for p in ids]

    hr('3a - Asymmetry (exploratory, per pre-registration): Steiger dependent-correlation tests, person level')
    dependent_pair('Trust: AIAS vs strategic trust  vs  AIAS vs tactical trust', ids, A, col('trust_s'), col('trust_t'))
    dependent_pair('Uptake: AIAS vs card uptake  vs  AIAS vs tactical consult', ids, A, col('took'), col('consult'))
    dependent_pair('Uptake: AIAS vs card uptake  vs  AIAS vs tactical keep-unmodified', ids, A, col('took'), col('accept'))
    for lab, a_, b_ in (('trust', 'trust_s', 'trust_t'), ('took/consult', 'took', 'consult'),
                        ('took/accept', 'took', 'accept')):
        ok = [i for i in range(len(ids)) if None not in (col(a_)[i], col(b_)[i])]
        r23 = stats.spearmanr([col(a_)[i] for i in ok], [col(b_)[i] for i in ok])[0]
        print(f'  detectable rho difference (80% power, Steiger, r23 = {r23:+.2f}, n = {len(ok)}) for {lab}: '
              f'{steiger_detectable(r23, len(ok)):.3f}')

    hr('3b - Asymmetry: stacked models with AIAS x tier interaction (exploratory)')
    # (i) session-level trust, both tiers stacked: 2 tiers x 2 runs per person
    st = []
    for s in sess:
        if s['pid'] not in az:
            continue
        for tier, k in (('strategic', 'trust_s'), ('tactical', 'trust_t')):
            if s[k] is not None:
                st.append(dict(pid=s['pid'], run=s['run'], scenario=s['scenario'], tier=tier,
                               trust=s[k], aias_z=az[s['pid']]))
    st = pd.DataFrame(st)
    mt = gee('trust ~ aias_z * C(tier) + C(scenario) + C(run)', st)
    for nm in ('aias_z', 'C(tier)[T.tactical]', 'aias_z:C(tier)[T.tactical]'):
        tt = term(mt, nm)
        print(f'  trust (1-7) {nm:28s} b = {tt["b"]:+.3f} [{tt["lo"]:+.3f}, {tt["hi"]:+.3f}] p = {tt["p"]:.4f}')
    print(f'  (n = {len(st)} ratings, {st.pid.nunique()} people; aias_z slope for strategic = main effect;'
          f' tactical slope = main + interaction)')
    tts = term(gee('trust ~ aias_z + C(scenario) + C(run)', st[st.tier == 'strategic']), 'aias_z')
    ttt = term(gee('trust ~ aias_z + C(scenario) + C(run)', st[st.tier == 'tactical']), 'aias_z')
    print(f'  separate fits: strategic trust b = {tts["b"]:+.3f} [{tts["lo"]:+.3f}, {tts["hi"]:+.3f}] p = {tts["p"]:.3f};'
          f'  tactical trust b = {ttt["b"]:+.3f} [{ttt["lo"]:+.3f}, {ttt["hi"]:+.3f}] p = {ttt["p"]:.3f}')

    # (ii) decision-level reliance, stacked: strategic `took` + tactical `accept` (and `consult`)
    tac = load_tactical()
    tac['aias_z'] = tac.pid.map(az)
    tac = tac.dropna(subset=['aias_z'])
    chk = tac.groupby(['pid', 'run'])[['consult', 'accept']].mean()
    ref = {(s['pid'], s['run']): (s['consult'], s['accept']) for s in sess}
    mism = sum(1 for (p, r), row in chk.iterrows()
               if abs(row.consult - ref[(p, r)][0]) > 1e-9 or abs(row.accept - ref[(p, r)][1]) > 1e-9)
    print(f'\n  tactical decisions: {len(tac)} from {tac.pid.nunique()} people; consult {tac.consult.mean():.3f}, '
          f'accept {tac.accept.mean():.3f}; session-rate mismatches vs load_people: {mism}')
    tacm = {}
    for outcome in ('accept', 'consult'):
        mm, how = gee_safe(f'{outcome} ~ aias_z + ntasks + ndrones + C(scenario) + C(run) + idx', tac,
                           binomial=True)
        tacm[outcome] = term(mm, 'aias_z')
        print(f'  tactical {outcome:8s} alone: AIAS {orfmt(tacm[outcome])}  [{how}]')
        sa = d[['pid', 'run', 'scenario', 'idx', 'took', 'aias_z']].rename(columns={'took': 'y'})
        sa['tier'] = 'strategic'
        ta = tac[['pid', 'run', 'scenario', 'idx', outcome, 'aias_z']].rename(columns={outcome: 'y'})
        ta['tier'] = 'tactical'
        stk = pd.concat([sa, ta], ignore_index=True)
        ms, how = gee_safe('y ~ aias_z * C(tier) + C(tier):(C(scenario) + C(run) + idx)', stk, binomial=True)
        print(f'  stacked fit: {how}')
        ti = term(ms, 'aias_z:C(tier)[T.tactical]')
        tm = term(ms, 'aias_z')
        print(f'  stacked took vs {outcome}: AIAS (strategic slope) {orfmt(tm)}')
        print(f'      interaction AIAS x tactical: ratio of ORs = {np.exp(ti["b"]):.3f} '
              f'[{np.exp(ti["lo"]):.3f}, {np.exp(ti["hi"]):.3f}] p = {ti["p"]:.4f}  (n = {len(stk)})')

    # ── 4 · other secondary (exploratory) ─────────────────────────────────────────────────────
    hr('4a - Bespoke scales in the primary model, one at a time (exploratory; alpha .53/.48)')
    for key in ('verification', 'delegation', 'delegTrustSuggestOverDecide', 'delegHumanFinalSay',
                'errorDetectability'):
        zz, _, _ = zscore_people(people, key)
        dd = d.copy()
        dd['x'] = dd.pid.map(zz)
        dd = dd.dropna(subset=['x'])
        tx = term(gee('took ~ x + ' + COVARS, dd, binomial=True), 'x')
        print(f'  {key:30s} {orfmt(tx)}  (n people {dd.pid.nunique()})')

    hr('4b - Disposition vs CHANGE in trust between sessions (link to H5; exploratory)')
    by = {}
    for s in sess:
        by.setdefault(s['pid'], {})[s['run']] = s
    dts = {p: by[p][2]['trust_s'] - by[p][1]['trust_s'] for p in by
           if 1 in by[p] and 2 in by[p] and None not in (by[p][1]['trust_s'], by[p][2]['trust_s'])}
    dtt = {p: by[p][2]['trust_t'] - by[p][1]['trust_t'] for p in by
           if 1 in by[p] and 2 in by[p] and None not in (by[p][1]['trust_t'], by[p][2]['trust_t'])}
    print(f'  mean change in strategic trust: {np.mean(list(dts.values())):+.3f} (n = {len(dts)}); '
          f'tactical: {np.mean(list(dtt.values())):+.3f}')
    for key in ('aias', 'verification', 'delegation'):
        xs = [people[p].get(key) for p in ids]
        r1 = spearman(xs, [dts.get(p) for p in ids])
        r2 = spearman(xs, [dtt.get(p) for p in ids])
        print(f'  {key:13s} vs d(trust_s): rho = {r1["rho"]:+.3f} p = {r1["p"]:.3f} n = {r1["n"]}   |   '
              f'vs d(trust_t): rho = {r2["rho"]:+.3f} p = {r2["p"]:.3f} n = {r2["n"]}')
    # same question as a model: trust_s ~ aias_z * run (session-level, both runs)
    ss = st[st.tier == 'strategic']
    mr = gee('trust ~ aias_z * C(run) + C(scenario)', ss)
    tr = term(mr, 'aias_z:C(run)[T.2]')
    print(f'  model strategic trust ~ aias_z * run + scenario: interaction b = {tr["b"]:+.3f} '
          f'[{tr["lo"]:+.3f}, {tr["hi"]:+.3f}] p = {tr["p"]:.3f}')

    hr('4c - Robustness of the primary estimate (exploratory specifications, NOT confirmatory)')
    specs = [
        ('genuine missions only (residuals excluded)', d[d.residual == 0], 'took ~ aias_z + ' + COVARS),
        ('+ odd card + game (planIndex)', d, 'took ~ aias_z + odd + C(planIndex) + ' + COVARS),
        ('AIAS as within-sample rank (z of ranks)', None, None),
        ('drop lowest-AIAS person (influence)', d[d.aias_z > d.aias_z.min()], 'took ~ aias_z + ' + COVARS),
        ('AIAS only, no covariates', d, 'took ~ aias_z'),
        ('independence working correlation', None, None),
    ]
    for lab, data, fml in specs:
        if lab.startswith('AIAS as within'):
            rk = pd.Series({p: people[p]['aias'] for p in az}).rank()
            rz = ((rk - rk.mean()) / rk.std(ddof=1)).to_dict()
            data = d.assign(aias_z=d.pid.map(rz))
            fml = 'took ~ aias_z + ' + COVARS
        if lab.startswith('independence'):
            mi = smf.gee('took ~ aias_z + ' + COVARS, 'pid', data=d, family=sm.families.Binomial(),
                         cov_struct=sm.cov_struct.Independence()).fit()
            print(f'  {lab:45s} {orfmt(term(mi, "aias_z"))}')
            continue
        print(f'  {lab:45s} {orfmt(term(gee(fml, data, binomial=True), "aias_z"))}  (n = {len(data)})')
    lo_hi = d.assign(low=(d.pid.map(lambda p: people[p]['aias']) < 7).astype(int))
    tl = term(gee('took ~ low + ' + COVARS, lo_hi, binomial=True), 'low')
    print(f'  {"AIAS < 7 vs >= 7 (n low people = " + str(lo_hi[lo_hi.low == 1].pid.nunique()) + ")":45s} '
          f'{orfmt(tl, per="low vs high")}')

    hr('4d - Person-level sanity check against the synthesis page')
    for k in ('took', 'consult', 'accept', 'trust_s', 'trust_t'):
        r = spearman(A, col(k))
        print(f'  Spearman AIAS vs {k:8s}: rho = {r["rho"]:+.3f}, p = {r["p"]:.3f}, n = {r["n"]}')


if __name__ == '__main__':
    main()
