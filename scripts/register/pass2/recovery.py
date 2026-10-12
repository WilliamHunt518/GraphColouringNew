#!/usr/bin/env python3
"""Pass 2 · area `recovery` — "Trust, tiers and recovery".

Read-only over Results/. Writes docs/analysis/register/pass2/recovery.json and prints every number the
findings file (docs/analysis/register/pass2/recovery.findings.yaml) quotes. Run from the repo root:

    python scripts/register/pass2/recovery.py

Two findings are fed from here:

f-tier-trust — the Tactical Assistant is trusted more (tier-trust-gap, tier-preference), why the tactical
    plan is kept without much checking (tier-checking-cost), and stated vs revealed preference: does the
    person who SAYS they trust tactical more also LEAN on it more (trust-not-lead, trust-own-failures-null).
f-recovery — what operators do after Suggest says "No workable plan": wrong refusals (a fix existed, using
    a drone busy on another task) vs correct refusals (no fix existed) vs no refusal; abandonment rate and
    the activity logged between the refusal and the close (rec-blind-spot, rec-after-refusal); the
    reliance trait vs attempting a fix (rec-low-reliance-attempt); the end-of-session artefact
    (meth-time-left).

Loaders reused: build_findings_synthesis.load_people / load_decisions, h2_verification_cost.load,
h3_recovery.load_all (recovery episodes with the corrected, time-local blind-spot rebuild),
wA_common.load_episodes / pc1_scores (round-2 recovery rows + the reliance axis). P09 excluded throughout.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import warnings
from collections import Counter, defaultdict
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
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

OUT = BASE / 'docs' / 'analysis' / 'register' / 'pass2' / 'recovery.json'
PARTS = BASE / 'Results' / 'Participants'
EXCLUDE = {'P09'}
SEED = 20261012
NBOOT = 4000
rng = np.random.default_rng(SEED)


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


def hdr(s):
    print('\n' + '=' * 96 + '\n' + s + '\n' + '=' * 96)


def wilson(k, n, z=1.96):
    if not n:
        return (None, None)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    w = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (r(c - w), r(c + w))


def spear(x, y, boot=True):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    rho, p = stats.spearmanr(x, y)
    out = dict(rho=r(rho), p=r(p, 4), n=int(len(x)))
    if boot and len(x) > 4:
        bs = []
        for _ in range(NBOOT):
            i = rng.integers(0, len(x), len(x))
            if len(set(x[i])) > 1 and len(set(y[i])) > 1:
                bs.append(stats.spearmanr(x[i], y[i])[0])
        out.update(lo=r(np.nanpercentile(bs, 2.5)), hi=r(np.nanpercentile(bs, 97.5)))
    return out


def gee(formula, d, binomial=True):
    fam = sm.families.Binomial() if binomial else sm.families.Gaussian()
    m = smf.gee(formula, 'pid', data=d, family=fam, cov_struct=sm.cov_struct.Exchangeable())
    try:
        return m.fit(cov_type='bias_reduced')
    except Exception:
        return m.fit()


def term(m, name, odds=True):
    ci = m.conf_int().loc[name]
    t = np.exp if odds else (lambda v: v)
    return dict(est=r(t(m.params[name]), 3), lo=r(t(ci[0]), 3), hi=r(t(ci[1]), 3), p=r(m.pvalues[name], 4))


def mean_ci(v):
    v = np.asarray([x for x in v if x is not None and np.isfinite(x)], float)
    if len(v) < 2:
        return dict(mean=r(v.mean()) if len(v) else None, lo=None, hi=None, n=int(len(v)))
    h = stats.t.ppf(.975, len(v) - 1) * v.std(ddof=1) / np.sqrt(len(v))
    return dict(mean=r(v.mean()), lo=r(v.mean() - h), hi=r(v.mean() + h), n=int(len(v)))


# ════════════════════════════════════════════════════════════════════════════════════════════
# f-tier-trust
# ════════════════════════════════════════════════════════════════════════════════════════════

def load_sessions():
    import build_findings_synthesis as b
    sess, people = quiet(b.load_people)
    S = pd.DataFrame([{k: v for k, v in s.items() if k not in ('items_s', 'items_t')} for s in sess])
    S = S[~S.pid.isin(EXCLUDE)].copy()
    # which game each session played (planSeedIndex; absent => the session number)
    game = {}
    for f in sorted(PARTS.glob('P*.json')):
        if f.stem in EXCLUDE:
            continue
        d = json.loads(f.read_text(encoding='utf-8'))
        for run, evs in enumerate(d['sessions'], start=1):
            st = next((e for e in (evs.values() if isinstance(evs, dict) else evs)
                       if isinstance(e, dict) and e.get('type') == 'session_start'), {})
            game[(f.stem, run)] = f"{st.get('complexity')}|{st.get('planSeedIndex') or run}"
    S['game'] = [game.get((p, ru)) for p, ru in zip(S.pid, S.run)]
    items = {(s['pid'], s['run']): (s['items_s'], s['items_t']) for s in sess}
    return S, items


def trust_gap(S, items):
    hdr('A · Trust in each assistant (post-session 6-item scale, 1-7)')
    ok = S.dropna(subset=['trust_s', 'trust_t'])
    P = ok.groupby('pid')[['trust_s', 'trust_t']].mean()
    d = (P.trust_t - P.trust_s).values
    t, p = stats.ttest_rel(P.trust_t, P.trust_s)
    ci = stats.t.ppf(.975, len(d) - 1) * d.std(ddof=1) / np.sqrt(len(d))
    wil = stats.wilcoxon(P.trust_t, P.trust_s).pvalue
    gap = dict(n=int(len(d)), strategic=mean_ci(P.trust_s), tactical=mean_ci(P.trust_t),
               diff=r(d.mean()), lo=r(d.mean() - ci), hi=r(d.mean() + ci), p=r(p, 5), dz=r(d.mean() / d.std(ddof=1)),
               wilcoxonP=r(wil, 5), higherTac=int((d > 0).sum()), higherStrat=int((d < 0).sum()), tied=int((d == 0).sum()))
    print('per person (mean of their sessions): strategic %.2f, tactical %.2f, gap %+.2f [%.2f, %.2f], t p=%.4f, dz=%.2f, '
          'Wilcoxon p=%.4f; %d higher tactical, %d higher strategic, %d tied (n=%d)'
          % (P.trust_s.mean(), P.trust_t.mean(), d.mean(), d.mean() - ci, d.mean() + ci, p, gap['dz'], wil,
             gap['higherTac'], gap['higherStrat'], gap['tied'], len(d)))
    people = [dict(pid=pid, s=r(row.trust_s, 2), t=r(row.trust_t, 2)) for pid, row in P.iterrows()]
    # by game (sessions): gap within session, mean and CI per game
    byGame = []
    for g, gg in ok.groupby('game'):
        mc = mean_ci((gg.trust_t - gg.trust_s).values)
        byGame.append(dict(game=g, s=r(gg.trust_s.mean()), t=r(gg.trust_t.mean()), **{'gap' + k: v for k, v in mc.items()}))
    byGame.sort(key=lambda x: x['game'])
    for x in byGame:
        print('  game %-12s n=%2d strategic %.2f tactical %.2f gap %+.2f [%s, %s]' % (x['game'], x['gapn'], x['s'], x['t'],
                                                                                    x['gapmean'], x['gaplo'], x['gaphi']))
    # gap by session (1st vs 2nd)
    byRun = [dict(run=int(ru), s=r(g.trust_s.mean()), t=r(g.trust_t.mean()), **{'gap' + k: v for k, v in mean_ci((g.trust_t - g.trust_s).values).items()})
             for ru, g in ok.groupby('run')]
    for x in byRun:
        print('  session %d: strategic %.2f tactical %.2f gap %+.2f [%s, %s] n=%d' % (x['run'], x['s'], x['t'], x['gapmean'], x['gaplo'], x['gaphi'], x['gapn']))
    # item by item (per person mean of the item over sessions, paired)
    import build_findings_synthesis as b
    it = []
    for stem in b.TRUST_STEMS:
        vs, vt = defaultdict(list), defaultdict(list)
        for (pid, run), (a, c) in items.items():
            if pid in EXCLUDE:
                continue
            if stem in a and stem in c:
                vs[pid].append(a[stem]); vt[pid].append(c[stem])
        dd = np.array([np.mean(vt[p]) - np.mean(vs[p]) for p in vs])
        mc = mean_ci(dd)
        it.append(dict(stem=stem, label=b.TRUST_STEM_LABEL[stem], s=r(np.mean([np.mean(v) for v in vs.values()])),
                       t=r(np.mean([np.mean(v) for v in vt.values()])), diff=mc['mean'], lo=mc['lo'], hi=mc['hi'], n=mc['n'],
                       p=r(stats.ttest_1samp(dd, 0).pvalue, 4)))
        print('  item %-10s strategic %.2f tactical %.2f diff %+.2f [%.2f, %.2f] p=%.4f' % (stem, it[-1]['s'], it[-1]['t'], mc['mean'], mc['lo'], mc['hi'], it[-1]['p']))
    return dict(gap=gap, people=people, byGame=byGame, byRun=byRun, items=it), P


def stated_preference(P):
    hdr('A2 · Stated preference (round-2 coding of debriefs/interviews) vs the questionnaire gap')
    path = BASE / 'docs' / 'analysis' / 'round2' / 'wE_codes.csv'
    W = pd.read_csv(path)[['pid', 'pref']]
    W = W[~W.pid.isin(EXCLUDE)]
    cnt = W.pref.value_counts().to_dict()
    k, n = cnt.get('tactical', 0), cnt.get('tactical', 0) + cnt.get('strategic', 0)
    sign_p = stats.binomtest(k, n, .5).pvalue if n else None
    gaps = (P.trust_t - P.trust_s)
    groups = []
    for pref, g in W.groupby('pref'):
        v = [gaps.get(p) for p in g.pid if p in gaps.index]
        mc = mean_ci(v)
        groups.append(dict(pref=pref, nSaid=len(g), who=sorted(g.pid), gaps=[r(gaps.get(p), 2) for p in sorted(g.pid)], **mc))
        print('  said %-11s n=%2d   mean questionnaire gap %+.2f [%s, %s]' % (pref, len(g), mc['mean'] or 0, mc['lo'], mc['hi']))
    tv = [gaps[p] for p in W[W.pref == 'tactical'].pid if p in gaps.index]
    sv = [gaps[p] for p in W[W.pref == 'strategic'].pid if p in gaps.index]
    mw = stats.mannwhitneyu(tv, sv).pvalue if tv and sv else None
    agree = sum(1 for p in W[W.pref == 'tactical'].pid if gaps.get(p, 0) > 0) + \
        sum(1 for p in W[W.pref == 'strategic'].pid if gaps.get(p, 0) < 0)
    print('  counts %s; sign test tactical vs strategic %d of %d, p=%.3f; MWU gap tactical-sayers vs strategic-sayers p=%.3f; '
          'questionnaire sign agrees with the stated side for %d of %d' % (cnt, k, n, sign_p, mw, agree, len(tv) + len(sv)))
    return dict(counts={k_: int(v) for k_, v in cnt.items()}, signK=k, signN=n, signP=r(sign_p, 4), groups=groups,
                mwP=r(mw, 4), agree=agree, agreeOf=len(tv) + len(sv), pref=dict(zip(W.pid, W.pref)))


def checking_cost():
    hdr('B · Checking cost: what happens to consulting, keeping and checking time as the plan grows')
    import h2_verification_cost as h2
    tac, strat, new = quiet(h2.load)
    tac = tac[~tac.pid.isin(EXCLUDE)].copy()
    strat = strat[~strat.pid.isin(EXCLUDE)].copy()
    tac = tac[tac.drones > 0].copy()
    bins = [(1, 2, '1–2'), (3, 3, '3'), (4, 4, '4'), (5, 5, '5'), (6, 7, '6–7'), (8, 99, '8+')]
    rows = []
    for lo, hi, lab in bins:
        g = tac[(tac.drones >= lo) & (tac.drones <= hi)]
        if g.empty:
            continue
        c = g[g.consulted == 1]
        n, k1, k2 = len(g), int(g.consulted.sum()), int(g.keep.sum())
        net = c.net.dropna()
        rows.append(dict(label=lab, n=n, people=int(g.pid.nunique()), consulted=r(k1 / n), cLo=wilson(k1, n)[0], cHi=wilson(k1, n)[1],
                         kept=r(k2 / n), kLo=wilson(k2, n)[0], kHi=wilson(k2, n)[1],
                         nCons=len(c), keptGivenCons=r(c.keep.mean()) if len(c) else None,
                         netMed=r(net.median(), 2), netQ1=r(net.quantile(.25), 2), netQ3=r(net.quantile(.75), 2),
                         perDrone=r((net / c.drones.loc[net.index]).median(), 2), reveal=r((c.entries * h2.REVEAL_S).median(), 1)))
        x = rows[-1]
        print('  drones %-4s n=%3d  consulted %.2f  kept-unmodified %.2f  kept|consulted %s  net check median %.1f s (IQR %.1f–%.1f)  '
              'per drone %.2f s  forced reveal median %.0f s' % (lab, n, x['consulted'], x['kept'], x['keptGivenCons'], x['netMed'],
                                                                x['netQ1'], x['netQ3'], x['perDrone'], x['reveal']))
    tac['zs'] = (tac['size'] - tac['size'].mean()) / tac['size'].std(ddof=0)
    mA = term(gee('keep ~ zs + C(scenario) + C(run)', tac), 'zs')
    mCons = term(gee('consulted ~ zs + C(scenario) + C(run)', tac), 'zs')
    cc = tac[tac.consulted == 1].dropna(subset=['net']).copy()
    mKc = term(gee('keep ~ zs + C(scenario) + C(run)', cc), 'zs')
    mNet = term(gee('net ~ zs + C(scenario) + C(run)', cc, binomial=False), 'zs', odds=False)
    cc['pd'] = cc.net / cc.drones
    mPd = term(gee('pd ~ zs + C(scenario) + C(run)', cc, binomial=False), 'zs', odds=False)
    print('  per SD of plan size (drones x tasks), GEE by person + scenario + run:')
    print('    keep-unmodified (all plans) OR %s; consulted OR %s; keep | consulted OR %s' % (mA, mCons, mKc))
    print('    net check seconds b %s; net seconds per drone b %s' % (mNet, mPd))
    keepC = (int(cc.keep.sum()), len(cc))
    # strategic vs tactical net decision time, per person medians
    pt = cc.groupby('pid').net.median()
    ps = strat.dropna(subset=['net']).groupby('pid').net.median()
    both = pt.index.intersection(ps.index)
    wil = stats.wilcoxon(pt[both], ps[both]).pvalue
    print('  kept | consulted %d of %d; person-median net check tactical %.2f s vs strategy card %.2f s (n=%d, Wilcoxon p=%.2g)'
          % (keepC[0], keepC[1], pt[both].median(), ps[both].median(), len(both), wil))
    return dict(bins=rows, keepOR=mA, consultOR=mCons, keepGivenConsOR=mKc, netB=mNet, perDroneB=mPd,
                keptGivenCons=keepC, nPlans=int(len(tac)), nPeople=int(tac.pid.nunique()),
                tacMedian=r(pt[both].median(), 2), stratMedian=r(ps[both].median(), 2), timeP=r(wil, 6), timeN=int(len(both)),
                revealS=h2.REVEAL_S)


def stated_vs_revealed(S, P, pref):
    hdr('C · Stated vs revealed: does the person who trusts tactical more also lean on it more?')
    ok = S.dropna(subset=['trust_s', 'trust_t'])
    beh = S.groupby('pid')[['took', 'consult', 'accept']].mean()
    D = P.join(beh, how='inner')
    D['tgap'] = D.trust_t - D.trust_s
    D['ugapA'] = D.accept - D.took       # kept the tactical plan unmodified  minus  took a strategy card
    D['ugapC'] = D.consult - D.took      # pressed Suggest at all             minus  took a strategy card
    grp = dict(took=mean_ci(D.took), consult=mean_ci(D.consult), accept=mean_ci(D.accept),
               ugapA=mean_ci(D.ugapA), ugapC=mean_ci(D.ugapC))
    print('  group: took a card %.2f, consulted the plan %.2f, kept it unmodified %.2f; usage gap (kept - took) %+.2f [%.2f, %.2f]'
          % (D.took.mean(), D.consult.mean(), D.accept.mean(), D.ugapA.mean(), grp['ugapA']['lo'], grp['ugapA']['hi']))
    ra = spear(D.tgap, D.ugapA)
    rc = spear(D.tgap, D.ugapC)
    print('  person: trust gap vs usage gap (kept - took) rho %s [%s, %s] p %s n %d' % (ra['rho'], ra.get('lo'), ra.get('hi'), ra['p'], ra['n']))
    print('  person: trust gap vs usage gap (consulted - took) rho %s [%s, %s] p %s' % (rc['rho'], rc.get('lo'), rc.get('hi'), rc['p']))
    # quadrants
    q = Counter()
    for _, x in D.iterrows():
        q[('T' if x.tgap > 0 else 'S' if x.tgap < 0 else '0') + ('T' if x.ugapA > 0 else 'S' if x.ugapA < 0 else '0')] += 1
    print('  quadrants (trust side, usage side):', dict(q))
    # each tier on its own, person level
    lvl = dict(strat=spear(D.trust_s, D.took), tacC=spear(D.trust_t, D.consult), tacA=spear(D.trust_t, D.accept))
    print('  person: strategic trust vs took a card rho %s [%s,%s] p %s | tactical trust vs consulted %s p %s | vs kept %s p %s'
          % (lvl['strat']['rho'], lvl['strat'].get('lo'), lvl['strat'].get('hi'), lvl['strat']['p'], lvl['tacC']['rho'], lvl['tacC']['p'],
             lvl['tacA']['rho'], lvl['tacA']['p']))
    # session level, then within person (session-2 minus session-1 change in trust vs change in use)
    sess = dict(strat=spear(ok.trust_s, ok.took, boot=False), tacC=spear(ok.trust_t, ok.consult, boot=False),
                tacA=spear(ok.trust_t, ok.accept, boot=False))
    W = S.pivot_table(index='pid', columns='run', values=['trust_s', 'trust_t', 'took', 'consult', 'accept'])
    W = W.dropna()
    ch = dict(strat=spear(W.trust_s[2] - W.trust_s[1], W.took[2] - W.took[1]),
              tacA=spear(W.trust_t[2] - W.trust_t[1], W.accept[2] - W.accept[1]))
    lead = dict(strat=spear(W.trust_s[1], W.took[2] - W.took[1]), tacA=spear(W.trust_t[1], W.accept[2] - W.accept[1]))
    print('  session-level (n=%d sessions): strat trust~took %s p %s; tac trust~consulted %s p %s; tac trust~kept %s p %s'
          % (sess['strat']['n'], sess['strat']['rho'], sess['strat']['p'], sess['tacC']['rho'], sess['tacC']['p'], sess['tacA']['rho'], sess['tacA']['p']))
    print('  within person (n=%d): change in strategic trust vs change in card uptake rho %s [%s,%s] p %s; tactical trust change vs kept change %s p %s'
          % (len(W), ch['strat']['rho'], ch['strat'].get('lo'), ch['strat'].get('hi'), ch['strat']['p'], ch['tacA']['rho'], ch['tacA']['p']))
    print('  does trust LEAD: session-1 strategic trust vs change in uptake s1->s2 rho %s [%s,%s] p %s; tactical %s p %s'
          % (lead['strat']['rho'], lead['strat'].get('lo'), lead['strat'].get('hi'), lead['strat']['p'], lead['tacA']['rho'], lead['tacA']['p']))
    people = [dict(pid=pid, tgap=r(x.tgap, 2), ugapA=r(x.ugapA, 3), ugapC=r(x.ugapC, 3), ts=r(x.trust_s, 2), tt=r(x.trust_t, 2),
                   took=r(x.took, 3), consult=r(x.consult, 3), accept=r(x.accept, 3), pref=pref.get(pid, ''))
              for pid, x in D.iterrows()]
    return dict(group=grp, rhoA=ra, rhoC=rc, quadrants=dict(q), levels=lvl, session=sess, change=ch, lead=lead, people=people,
                nChange=int(len(W)))


def own_failures_null(S):
    hdr('C2 · Own bad experiences vs the change in strategic trust (trust-own-failures-null)')
    import build_findings_synthesis as b
    dec = quiet(b.load_decisions)
    dec = dec[~dec.pid.isin(EXCLUDE)]
    seen1 = dec[dec.run == 1].groupby('pid').odd.sum()
    W = S.pivot_table(index='pid', columns='run', values='trust_s').dropna()
    dts = W[2] - W[1]
    x = spear(seen1.reindex(dts.index), dts)
    print('  illogical cards seen in session 1 vs change in strategic trust s1->s2: rho %s [%s, %s] p %s n %d'
          % (x['rho'], x.get('lo'), x.get('hi'), x['p'], x['n']))
    # partial on scenario order (Strategic Heavy first or not): rank both, residualise each on order, correlate
    first = S[S.run == 1].set_index('pid').scenario.reindex(dts.index)
    o = (first == 'strategic').astype(float).values
    rk = lambda v: stats.rankdata(v)
    res = lambda v: v - np.polyval(np.polyfit(o, v, 1), o)
    xs, ys = res(rk(seen1.reindex(dts.index).values)), res(rk(dts.values))
    pr, pp = stats.pearsonr(xs, ys)
    byOrder = {k: r(dts[first == k].mean()) for k in ('strategic', 'tactical')}
    print('  ... partial on scenario order: rho %.3f p %.3f; mean change by first scenario %s' % (pr, pp, byOrder))
    print('  mean change in strategic trust %+.2f (n=%d)' % (dts.mean(), len(dts)))
    return dict(seenVsChange=x, partialOrder=dict(rho=r(pr), p=r(pp, 4)), byOrder=byOrder, meanChange=r(dts.mean()))


# ════════════════════════════════════════════════════════════════════════════════════════════
# f-recovery
# ════════════════════════════════════════════════════════════════════════════════════════════

OPERATOR = {'strategic_modal_opened', 'strategic_dismissed', 'strategic_choice', 'strategic_card_previewed',
            'manual_allocation_edited', 'tactical_confirmed', 'tactical_suggest_used', 'tactical_assignment_changed',
            'asset_recalled', 'task_reprioritised', 'mission_abandoned', 'failure_recovery'}


def raw_events():
    from agent_scenario_stats import events
    out = {}
    for f in sorted(PARTS.glob('P*.json')):
        if f.stem in EXCLUDE:
            continue
        d = json.loads(f.read_text(encoding='utf-8'))
        for run, s in enumerate(d['sessions'], start=1):
            out[(f.stem, run)] = [e for e in events(s) if e.get('type') in OPERATOR]
    return out


def episode_class(e):
    ref = [p for p in e['presses'] if p['result'] in ('failed', 'partial')]
    if any(p['blind'] for p in ref):
        return 'wrong'
    if ref:
        return 'correct'
    if e['suggest'] > 0:
        return 'solved'
    if e['drags'] > 0:
        return 'hand'
    return 'none'


CLASS_LABEL = {'wrong': 'Wrong refusal (a fix existed)', 'correct': 'Correct refusal (no fix existed)',
               'solved': 'Suggest gave a plan', 'hand': 'No Suggest, edited by hand', 'none': 'Nothing tried'}


def refusals(eps, raw):
    hdr('D · After "No workable plan": what operators did, wrong vs correct refusals vs no refusal')
    E = []
    for e in eps:
        c = episode_class(e)
        E.append(dict(pid=e['pid'], run=e['run'], mission=e['missionId'], cls=c, outcome=e['outcome'],
                      fix=bool(e['fixAll']), opened=e['opened'], closed=e['closed']))
    E = pd.DataFrame(E)
    # abandonment by class; resolved episodes (abandoned / (abandoned + recovered)); unresolved counted aside
    byClass = []
    for c in ['wrong', 'correct', 'solved', 'hand', 'none']:
        g = E[E.cls == c]
        res = g[g.outcome != 'unresolved']
        k, n = int((res.outcome == 'abandoned').sum()), len(res)
        lo, hi = wilson(k, n)
        byClass.append(dict(cls=c, label=CLASS_LABEL[c], n=n, abandoned=k, rate=r(k / n) if n else None, lo=lo, hi=hi,
                            unresolved=int((g.outcome == 'unresolved').sum()), fixable=int(g.fix.sum()),
                            people=int(g.pid.nunique())))
        print('  %-36s resolved %3d  abandoned %3d (%s) [%s, %s]  fixable %d  people %d  (+%d left open)'
              % (CLASS_LABEL[c], n, k, r(k / n, 2) if n else None, lo, hi, int(g.fix.sum()), g.pid.nunique(), byClass[-1]['unresolved']))
    # fixable-only view for the no-refusal classes, so the comparison is like-for-like
    fixOnly = []
    for c in ['solved', 'hand', 'none']:
        g = E[(E.cls == c) & E.fix & (E.outcome != 'unresolved')]
        k, n = int((g.outcome == 'abandoned').sum()), len(g)
        fixOnly.append(dict(cls=c, n=n, abandoned=k, rate=r(k / n) if n else None))
    print('  fixable-only, no refusal:', fixOnly)
    # Fisher: wrong-refusal episodes vs every other attempted fixable episode (Suggest gave a plan or hand edits)
    att = E[E.cls.isin(['solved', 'hand']) & E.fix & (E.outcome != 'unresolved')]
    w = E[(E.cls == 'wrong') & (E.outcome != 'unresolved')]
    tab = [[int((w.outcome == 'abandoned').sum()), int((w.outcome == 'recovered').sum())],
           [int((att.outcome == 'abandoned').sum()), int((att.outcome == 'recovered').sum())]]
    orr, fp = stats.fisher_exact(tab)
    print('  wrong refusal vs other ATTEMPTED fixable episodes: %s; Fisher OR %.1f p=%.4g' % (tab, orr, fp))
    # GEE with person clustering on the same contrast (people with both kinds of episodes are few: say so)
    G = pd.concat([w.assign(wr=1), att.assign(wr=0)])
    G['ab'] = (G.outcome == 'abandoned').astype(int)
    try:
        mW = term(gee('ab ~ wr', G), 'wr')
    except Exception:
        mW = None
    mixed = sorted(set(w.pid) & set(att.pid))
    print('  GEE (clustered by person) OR %s; people with a wrong refusal AND another attempted fixable episode: %d' % (mW, len(mixed)))
    # same people's other attempted fixable episodes
    same = att[att.pid.isin(set(w.pid))]
    print('  the wrong-refusal people on their OTHER attempted fixable failures: abandoned %d of %d'
          % (int((same.outcome == 'abandoned').sum()), len(same)))

    # ---- per refusal episode: what happened between the refusal and the close
    epis = []
    for e in eps:
        c = episode_class(e)
        if c not in ('wrong', 'correct'):
            continue
        ref = [p for p in e['presses'] if p['result'] in ('failed', 'partial')]
        first = ref[0]['at']
        last = ref[-1]['at']
        close = e['closed']
        ev = e['events']
        drags_after = [x[1] for x in ev if x[0] == 'drag' and x[1] > first]
        drags_before = [x[1] for x in ev if x[0] == 'drag' and x[1] <= first]
        sug_after = [x for x in ev if x[0] == 'suggest' and x[1] > first]
        others = [x for x in raw[(e['pid'], e['run'])] if first < x['elapsed'] <= close and x.get('missionId') != e['missionId']]
        presses = [dict(t=r(p['at'] - first, 2), res=p['result'], blind=bool(p['blind'])) for p in e['presses']]
        rowx = dict(pid=e['pid'], run=e['run'], mission=e['missionId'], category=e['category'], cls=c,
                    outcome=e['outcome'], verified=(e['pid'], e['run'], e['missionId']) == ('P19', 1, 'M003'),
                    failToRefusal=r(first - e['opened'], 1), refusalToClose=r(close - first, 1), lastToClose=r(close - last, 1),
                    nRefusals=len(ref), dragsBefore=len(drags_before), dragsAfter=len(drags_after),
                    suggestAfter=len(sug_after), othersAfter=len(others),
                    otherTypes=dict(Counter(x['type'] for x in others)),
                    drags=[r(t - first, 2) for t in drags_after], dragsPre=[r(t - first, 2) for t in drags_before],
                    presses=presses, timeLeft=r(480 - first, 0), fixable=bool(e['fixAll']),
                    checked=int(len(drags_after) > 0 or len(sug_after) > 0))
        epis.append(rowx)
    R = pd.DataFrame(epis)
    print('\n  refusal episodes (first refusal -> close):')
    print(R[['pid', 'run', 'mission', 'cls', 'outcome', 'failToRefusal', 'refusalToClose', 'lastToClose', 'nRefusals', 'dragsBefore',
             'dragsAfter', 'suggestAfter', 'othersAfter']].sort_values(['cls', 'outcome', 'refusalToClose']).to_string(index=False))
    summ = {}
    for (c, o), g in R.groupby(['cls', 'outcome']):
        summ[f'{c}|{o}'] = dict(n=len(g), people=int(g.pid.nunique()), medToClose=r(g.refusalToClose.median(), 1),
                                medLastToClose=r(g.lastToClose.median(), 1),
                                medFailToClose=r((g.failToRefusal + g.refusalToClose).median(), 1),
                                anyCheck=int(g.checked.sum()), anyDrag=int((g.dragsAfter > 0).sum()),
                                anyRetry=int((g.suggestAfter > 0).sum()), anyElsewhere=int((g.othersAfter > 0).sum()),
                                dragsBefore=int((g.dragsBefore > 0).sum()))
        print('  %-18s n=%2d people %2d  median first refusal->close %s s (last refusal->close %s s)  any drag after %d  '
              'any retry %d  any action elsewhere %d  dragged before the refusal %d'
              % (f'{c}|{o}', len(g), g.pid.nunique(), summ[f'{c}|{o}']['medToClose'], summ[f'{c}|{o}']['medLastToClose'],
                 summ[f'{c}|{o}']['anyDrag'], summ[f'{c}|{o}']['anyRetry'], summ[f'{c}|{o}']['anyElsewhere'], summ[f'{c}|{o}']['dragsBefore']))
    wa = R[(R.cls == 'wrong') & (R.outcome == 'abandoned')]
    noChk = wa[(wa.dragsAfter == 0) & (wa.suggestAfter == 0)]
    for k_, v_ in summ.items():
        print('    %-18s median failure->close %s s' % (k_, v_['medFailToClose']))
    print('  wrong refusal -> abandoned: %d episodes; abandoned with NO drag and NO retry after the refusal: %d; within 10 s: %d'
          % (len(wa), len(noChk), int((wa.refusalToClose <= 10).sum())))

    # baseline: how quickly do abandonments happen WITHOUT any refusal (failure -> abandon; last own action -> abandon)
    base = []
    for e in eps:
        if e['outcome'] != 'abandoned' or episode_class(e) in ('wrong', 'correct'):
            continue
        acts = [x[1] for x in e['events'] if x[0] in ('drag', 'suggest')]
        base.append(dict(cls=episode_class(e), failToClose=e['closed'] - e['opened'],
                         lastActToClose=(e['closed'] - max(acts)) if acts else None))
    B = pd.DataFrame(base)
    bstat = {c: dict(n=len(g), medFailToClose=r(g.failToClose.median(), 1),
                     medLastActToClose=r(g.lastActToClose.dropna().median(), 1) if g.lastActToClose.notna().any() else None)
             for c, g in B.groupby('cls')}
    print('  abandonments with no refusal: ', bstat)
    # strip data: seconds from the trigger to the abandonment, by kind
    strip = []
    for x in epis:
        if x['outcome'] == 'abandoned':
            strip.append(dict(kind=x['cls'], s=x['lastToClose'], pid=x['pid'], checked=x['checked'],
                              label=f"{x['pid']} s{x['run']} {x['mission']}"))
    for e in eps:
        if e['outcome'] == 'abandoned' and episode_class(e) not in ('wrong', 'correct'):
            acts = [x[1] for x in e['events'] if x[0] in ('drag', 'suggest')]
            strip.append(dict(kind='own' if acts else 'untried', s=r(e['closed'] - (max(acts) if acts else e['opened']), 1),
                              pid=e['pid'], checked=int(bool(acts)), label=f"{e['pid']} s{e['run']} {e['missionId']}"))
    return dict(byClass=byClass, fixOnly=fixOnly, fisher=dict(table=tab, OR=r(orr, 2), p=r(fp, 5)), gee=mW, mixedPeople=len(mixed),
                samePeopleOther=dict(abandoned=int((same.outcome == 'abandoned').sum()), n=len(same)),
                episodes=epis, summary=summ, noCheckAbandon=len(noChk), within10=int((wa.refusalToClose <= 10).sum()),
                nWrongAbandon=len(wa), baseline=bstat, strip=strip,
                presses=dict(total=int(sum(len(e['presses']) for e in eps)),
                             wrong=int(sum(p['blind'] for e in eps for p in e['presses'])),
                             correct=int(sum((p['result'] in ('failed', 'partial')) and not p['blind'] for e in eps for p in e['presses'])),
                             wrongPeople=int(len({e['pid'] for e in eps for p in e['presses'] if p['blind']}))))


def after_refusal():
    hdr('E · Later attempts after a person\'s first refusal (rec-after-refusal), and the reliance axis (rec-low-reliance-attempt)')
    import wA_common as c
    df = quiet(c.load_episodes)
    pc1, ev, load = quiet(c.pc1_scores)
    pc1x, _, _ = quiet(c.pc1_scores, drop=('recSug',))
    FX = df[df.fixAll].copy()
    FX['tkey'] = FX.run * 1000 + FX.opened
    out = {}
    for key, cond in (('any', lambda p: p['result'] in ('failed', 'partial')), ('wrong', lambda p: p['blind'])):
        first = {}
        for _, e in df.iterrows():
            for p in e.presses_detail:
                if cond(p):
                    first[e.pid] = min(first.get(e.pid, 1e12), e.run * 1000 + p['at'])
        f = FX[FX.pid.isin(first)].copy()
        f['ev'] = f.pid.map(first)
        f = f[~((f.tkey <= f.ev) & (f.closedAt + f.run * 1000 >= f.ev))]   # drop the exposure episode itself
        f['post'] = (f.tkey > f.ev).astype(int)
        cells = f.groupby('post').attempted.agg(['mean', 'size'])
        both = f.groupby('pid').post.agg(lambda v: 0 < v.mean() < 1)
        try:
            m = term(gee('attempted ~ post + run2', f), 'post')
        except Exception:
            m = None
        try:
            m0 = term(gee('attempted ~ post', f), 'post')
        except Exception:
            m0 = None
        pp = []
        for pid, g in f.groupby('pid'):
            a, b = g[g.post == 0], g[g.post == 1]
            pp.append(dict(pid=pid, before=r(a.attempted.mean()) if len(a) else None, nb=len(a),
                           after=r(b.attempted.mean()) if len(b) else None, na=len(b)))
        out[key] = dict(people=len(first), peopleBoth=int(both.sum()),
                        before=r(cells.loc[0, 'mean']) if 0 in cells.index else None, nBefore=int(cells.loc[0, 'size']) if 0 in cells.index else 0,
                        after=r(cells.loc[1, 'mean']) if 1 in cells.index else None, nAfter=int(cells.loc[1, 'size']) if 1 in cells.index else 0,
                        model=m, modelRaw=m0, perPerson=pp)
        print('  [%s refusal] exposed people %d (%d with fixable failures both before and after); attempted before %s (n=%s) -> after %s (n=%s); '
              'GEE OR (+session) %s; unadjusted %s' % (key, len(first), int(both.sum()), out[key]['before'], out[key]['nBefore'],
                                                       out[key]['after'], out[key]['nAfter'], m, m0))
    # reliance axis vs attempt rate (person level)
    rows = []
    for thr in (0, 31):
        g = FX[FX.timeLeft * 60 >= thr] if thr else FX
        P = g.groupby('pid').agg(rate=('attempted', 'mean'), n=('attempted', 'size'), k=('attempted', 'sum'))
        P['pc1'] = P.index.map(pc1)
        P['pc1x'] = P.index.map(pc1x)
        a = spear(P.pc1, P.rate)
        b_ = spear(P.pc1x, P.rate)
        c_ = spear(P[P.rate > 0].pc1, P[P.rate > 0].rate)
        d_ = spear(P[(P.rate > 0) & (P.rate < 1)].pc1, P[(P.rate > 0) & (P.rate < 1)].rate) if ((P.rate > 0) & (P.rate < 1)).sum() > 4 else None
        rows.append(dict(minLeft=thr, nEps=int(len(g)), nAtt=int(g.attempted.sum()), all=a, noRec=b_, noNever=c_, middle=d_,
                         never=sorted(P[P.rate == 0].index), always=int((P.rate == 1).sum()), nPeople=int(len(P)),
                         people=[dict(pid=p, rate=r(x.rate), n=int(x.n), k=int(x.k), pc1=r(x.pc1), pc1x=r(x.pc1x)) for p, x in P.iterrows()]))
        print('  fixable failures with >= %d s left: %d episodes, %d attempted; PC1 vs attempt rate rho %s [%s, %s] p %s | PC1 without '
              'the recovery-Suggest item %s p %s | without never-attempters %s [%s, %s] p %s (n %d) | never: %s; attempt every one: %d of %d'
              % (thr, len(g), g.attempted.sum(), a['rho'], a.get('lo'), a.get('hi'), a['p'], b_['rho'], b_['p'], c_['rho'], c_.get('lo'),
                 c_.get('hi'), c_['p'], c_['n'], rows[-1]['never'], rows[-1]['always'], len(P)))
    # time left: attempt rate by bin + first-move latency
    FX['tl'] = FX.timeLeft * 60
    tbins = [(0, 30, '≤ 30 s'), (30, 90, '31–90 s'), (90, 180, '1.5–3 min'), (180, 300, '3–5 min'), (300, 481, '5–8 min')]
    tl = []
    for lo, hi, lab in tbins:
        g = FX[(FX.tl > lo) & (FX.tl <= hi)] if lo else FX[FX.tl <= hi]
        k, n = int(g.attempted.sum()), len(g)
        w_ = wilson(k, n)
        tl.append(dict(label=lab, n=n, k=k, rate=r(k / n) if n else None, lo=w_[0], hi=w_[1], unresolved=int(g.unresolved.sum())))
    print('  attempt rate by time left at the failure:', [(x['label'], x['k'], x['n'], x['rate'], x['unresolved']) for x in tl])
    mtl = {}
    for thr in (0, 31):
        g = FX[FX.tl >= thr] if thr else FX
        g = c.add_within(g, 'timeLeft')
        try:
            mtl[thr] = term(gee('attempted ~ timeLeft_w + timeLeft_b', g), 'timeLeft_w')
        except Exception:
            mtl[thr] = None
    print('  attempted ~ minutes left (within person): all %s; >= 31 s left %s' % (mtl[0], mtl[31]))
    return out, rows, dict(bins=tl, modelAll=mtl[0], model31=mtl[31]), dict(pc1Var=r(ev), loadings={k: r(v, 2) for k, v in load.items()})


def first_move(eps):
    lat, late_open = [], []
    for e in eps:
        if not e['fixAll']:
            continue
        acts = [x[1] for x in e['events'] if x[0] in ('drag', 'suggest')]
        if acts:
            lat.append(min(acts) - e['opened'])
        if e['outcome'] == 'unresolved':
            late_open.append(480 - e['opened'])
    lat = np.array(lat)
    print('  first move (drag or Suggest) after a fixable failure: median %.1f s (IQR %.1f-%.1f, n=%d); fixable failures left open at the '
          'buzzer %d, of which opened with <= 12 s left: %d; their seconds left: %s'
          % (np.median(lat), np.percentile(lat, 25), np.percentile(lat, 75), len(lat), len(late_open),
             sum(1 for x in late_open if x <= 12.5), sorted(round(x, 1) for x in late_open)))
    return dict(firstMoveMed=r(np.median(lat), 1), firstMoveQ1=r(np.percentile(lat, 25), 1), firstMoveQ3=r(np.percentile(lat, 75), 1),
                nFirst=int(len(lat)), leftOpen=len(late_open), leftOpenLe12=int(sum(1 for x in late_open if x <= 12.5)),
                leftOpenSecs=sorted(r(x, 1) for x in late_open))


def main():
    S, items = load_sessions()
    trust, P = trust_gap(S, items)
    pref = stated_preference(P)
    chk = checking_cost()
    svr = stated_vs_revealed(S, P, pref['pref'])
    ofn = own_failures_null(S)

    import h3_recovery as h3
    eps = quiet(h3.load_all)[0]
    raw = raw_events()
    ref = refusals(eps, raw)
    after, rel, tleft, pcinfo = after_refusal()
    fm = first_move(eps)
    tleft.update(fm)

    res = dict(generated=pd.Timestamp.now().strftime('%Y-%m-%d %H:%M'),
               trust=trust, preference={k: v for k, v in pref.items() if k != 'pref'}, checking=chk,
               statedRevealed=svr, ownFailures=ofn,
               refusal=ref, afterRefusal=after, reliance=dict(rows=rel, **pcinfo), timeLeft=tleft,
               verified=dict(pid='P19', run=1, mission='M003',
                             note='Camera-2 failed; the Supply Drop needed 2 Lifters + 1 Camera (or 1 Lifter + 1 Camera). Two Lifters '
                                  'sat unassigned; the only Camera left was executing Search & Service (done in ~45 s). Suggest '
                                  'answered "No workable plan"; the operator abandoned about 3 s later. Chaining that Camera on '
                                  'after its current task would have saved it. Checked frame by frame on the recording.'))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, separators=(',', ':'), default=lambda o: o.item() if hasattr(o, 'item') else str(o)),
                   encoding='utf-8')
    print('\nwrote', OUT.relative_to(BASE), '(%d bytes)' % OUT.stat().st_size)


if __name__ == '__main__':
    main()
