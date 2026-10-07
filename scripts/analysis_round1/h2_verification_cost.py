"""H2 -- does the cost of checking explain the trust gap between the tiers?

Pre-registered primary test (docs/analysis/HYPOTHESES_ROUND1.md, H2): within the tactical tier, the
probability of keeping the plan unmodified rises with plan size while inspection time per drone
falls (GEE, person-clustered, controlling for scenario and run); support = both effects in the
predicted direction with the interaction significant.

The hypothesis text does not name the two interacting terms. Operationalisation used here, fixed
before any model was fitted (see the report's analysis log):
  A  keep-unmodified ~ size + C(scenario) + C(run)        binomial, ALL confirmed plans   (b > 0)
     (keep-unmodified as the brief defines it: consulted via Suggest AND deployed unmodified)
  B  inspection-per-drone ~ size + C(scenario) + C(run)   gaussian, consulted plans       (b < 0)
  C  keep ~ size_z * inspection-per-drone_z + C(scenario) + C(run)
                                                         binomial, consulted plans       (interaction b < 0,
                                                         i.e. size raises deference most where checking is thinnest)
  Support needs all three significant in the predicted direction, so the primary p handed to the
  Holm family is the intersection-union p = max(pA, pB, pC).

Measures
  size        = distinct drones in the agent plan x tasks in the agent plan (drones x tasks)
  inspection  = last non-recovery `tactical_suggest_used` -> `tactical_confirmed`, MINUS the forced
                Suggest reveal: MapDisplay.tsx reveals one (task, drone) pair per 1000 ms and Deploy
                is disabled until the reveal finishes (`disabled={!canDeploy || isSuggestLoading}`),
                so the raw interval contains entries x 1 s of unavoidable wait (cf. trap 5). Net
                values below 0 (timer jitter) are clipped to 0.
  per drone   = net inspection / distinct drones in the plan

Run from the repo root:  C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h2_verification_cost.py
Read-only on Results/. Prints every number the report quotes.
"""
import glob
import json
import os
import sys
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'scripts'))
from build_findings_synthesis import gee, term, load_people, EXCLUDE  # noqa: E402
from study_analysis import crossover  # noqa: E402

PARTICIPANTS = BASE / 'Results' / 'Participants'
REVEAL_S = 1.0          # MapDisplay.tsx progressive reveal step (unchanged since 8332ad1, June 2026)
NEW_BUILDS = ('study-v1.12', 'study-v1.13')
warnings.filterwarnings('ignore')
pd.set_option('display.width', 200)


def load():
    tac, strat, versions = [], [], {}
    for path in sorted(glob.glob(str(PARTICIPANTS / 'P*.json'))):
        pid = os.path.splitext(os.path.basename(path))[0]
        if pid in EXCLUDE:
            continue
        log = json.loads(Path(path).read_text(encoding='utf-8'))
        for run, events in enumerate(log['sessions'], start=1):
            start = next(e for e in events if e['type'] == 'session_start')
            scen, ver = start.get('complexity'), start.get('appVersion')
            plan_idx = start.get('planSeedIndex') or run
            versions.setdefault(pid, set()).add(ver)
            sugg, changes, opened_at = defaultdict(list), defaultdict(list), {}
            modal, previews = {}, defaultdict(list)
            for e in events:
                t, m = e['type'], e.get('missionId')
                if t == 'tactical_opened':
                    opened_at[m], sugg[m], changes[m] = e['timestamp'], [], []
                elif t == 'tactical_suggest_used' and not e.get('recoveryMode'):
                    sugg[m].append(e['timestamp'])
                elif t == 'tactical_assignment_changed' and not e.get('recoveryMode'):
                    changes[m].append(e['timestamp'])
                elif t == 'tactical_confirmed':
                    ap = e.get('agentPlan') or []
                    drones = len({a for x in ap for a in x['assetIds']})
                    tasks = len(ap)
                    entries = sum(len(x['assetIds']) for x in ap)
                    consulted = (e.get('suggestUsedCount') or 0) > 0
                    keep = int(consulted and bool(ap) and not e.get('modifiedFromAgentPlan'))
                    s = sugg.get(m) or []
                    last = s[-1] if s else None
                    raw = (e['timestamp'] - last) / 1000 if last is not None else np.nan
                    net = max(raw - entries * REVEAL_S, 0.0) if last is not None else np.nan
                    after = [c for c in changes.get(m, []) if last is not None and c > last]
                    # time from the end of the reveal to the operator's first act (an edit or Deploy):
                    # the checking that happens BEFORE any editing, free of the time edits take.
                    first = min(after) if after else e['timestamp']
                    pre = (max((first - last) / 1000 - entries * REVEAL_S, 0.0)
                           if last is not None else np.nan)
                    tac.append(dict(pid=pid, run=run, scenario=scen, version=ver, game=f'{scen}{plan_idx}',
                                    mission=m, category=e.get('missionCategory'),
                                    residual=int(str(m).endswith('-R')),
                                    consulted=int(consulted), keep=keep, drones=drones, tasks=tasks,
                                    entries=entries, size=drones * tasks, raw=raw, net=net, pre=pre,
                                    nedits=len(after), nsugg=len(s),
                                    open_to_confirm=(e.get('latencyMs') or np.nan) / 1000))
                elif t == 'strategic_modal_opened':
                    modal[m] = e
                    previews[m] = []
                elif t == 'strategic_card_previewed':
                    previews[m].append(e)
                elif t == 'strategic_choice' and m in modal:
                    mo = modal.pop(m)
                    cards = mo.get('strategiesPresented') or []
                    reveal = e.get('deployEnabledAtMs')
                    if reveal is None:
                        reveal = max([c.get('revealDelayMs') or 0 for c in cards] or [0])
                    lat = e.get('latencyMs')
                    pv = previews.pop(m, [])
                    names = [p['strategyName'] for p in pv]
                    toggles = sum(1 for a, b in zip(names, names[1:]) if a != b)
                    ndr = sum((e.get('assetsChosen') or {}).values())
                    strat.append(dict(pid=pid, run=run, scenario=scen, version=ver,
                                      choice=e.get('choiceType'),
                                      card=int(e.get('choiceType') in ('aggressive', 'conservative')),
                                      net=(max(lat - reveal, 0) / 1000) if lat is not None else np.nan,
                                      npreview=len(pv), toggles=toggles,
                                      dwell=((e['timestamp'] - pv[0]['timestamp']) / 1000) if pv else 0.0,
                                      drones=ndr))
    tac, strat = pd.DataFrame(tac), pd.DataFrame(strat)
    new = {p for p, v in versions.items() if v and all(x in NEW_BUILDS for x in v)}
    return tac, strat, new


def z(s):
    return (s - s.mean()) / s.std(ddof=0)


def fmt(t, odds=False):
    if odds:
        return 'OR %.3f [%.3f, %.3f] p=%.4f (b=%.3f)' % (np.exp(t['b']), np.exp(t['lo']), np.exp(t['hi']), t['p'], t['b'])
    return 'b %.4f [%.4f, %.4f] p=%.4f' % (t['b'], t['lo'], t['hi'], t['p'])


def primary(tac, label):
    print('\n=== PRIMARY (%s) ===' % label)
    allc = tac.copy()
    con = tac[tac.consulted == 1].copy()
    con['ipd'] = con.net / con.drones
    print('confirmed plans n=%d (people %d); consulted n=%d (people %d); kept unmodified %d (%.1f%% of all, %.1f%% of consulted)'
          % (len(allc), allc.pid.nunique(), len(con), con.pid.nunique(), allc.keep.sum(),
             100 * allc.keep.mean(), 100 * con.keep.mean()))
    print('people with >=1 consulted-but-modified plan: %d' % con[con.keep == 0].pid.nunique())
    # z-score size within each sample so the per-SD coefficient is comparable across models
    allc['size_z'] = z(allc['size'])
    con['size_z'] = z(con['size'])
    con['ipd_z'] = z(con['ipd'])
    sd_all, sd_con = allc['size'].std(ddof=0), con['size'].std(ddof=0)
    print('size (drones x tasks): mean %.1f sd %.1f (all); sd %.1f (consulted)' % (allc['size'].mean(), sd_all, sd_con))
    print('net inspection s: median %.2f IQR [%.2f, %.2f]; per drone median %.3f'
          % (con.net.median(), con.net.quantile(.25), con.net.quantile(.75), con.ipd.median()))
    mA = gee('keep ~ size_z + C(scenario) + C(run)', allc, binomial=True)
    mB = gee('ipd ~ size_z + C(scenario) + C(run)', con)
    mC = gee('keep ~ size_z * ipd_z + C(scenario) + C(run)', con, binomial=True)
    tA, tB, tC = term(mA, 'size_z'), term(mB, 'size_z'), term(mC, 'size_z:ipd_z')
    print('A keep(all) ~ size  per SD: ' + fmt(tA, True))
    print('B insp/drone ~ size per SD (s/drone): ' + fmt(tB))
    print('C keep(consulted) ~ size*insp: interaction ' + fmt(tC, True))
    print('   C main size ' + fmt(term(mC, 'size_z'), True) + ' ; main insp ' + fmt(term(mC, 'ipd_z'), True))
    dirs = (tA['b'] > 0, tB['b'] < 0, tC['b'] < 0)
    sig = (tA['p'] < .05, tB['p'] < .05, tC['p'] < .05)
    p_iut = max(tA['p'], tB['p'], tC['p'])
    verdict = 'SUPPORTED' if all(dirs) and all(sig) else 'NOT SUPPORTED'
    print('directions as predicted (A>0, B<0, C<0): %s ; significant: %s' % (dirs, sig))
    print('intersection-union primary p = %.4f -> %s' % (p_iut, verdict))
    return dict(A=tA, B=tB, C=tC, p=p_iut, verdict=verdict)


def robustness(tac):
    print('\n=== ROBUSTNESS of the primary components (exploratory) ===')
    con = tac[tac.consulted == 1].copy()
    con['ipd'] = con.net / con.drones
    con['size_z'] = z(con['size'])
    con['lsize'] = np.log(con['size'])
    # A among consulted only
    t = term(gee('keep ~ size_z + C(scenario) + C(run)', con, binomial=True), 'size_z')
    print('A\' keep|consulted ~ size: ' + fmt(t, True))
    # consult (the step where nearly all the non-keeping happens)
    a = tac.copy(); a['size_z'] = z(a['size'])
    t = term(gee('consulted ~ size_z + C(scenario) + C(run)', a, binomial=True), 'size_z')
    print('consulted(all) ~ size: ' + fmt(t, True))
    # game instead of scenario
    t = term(gee('keep ~ size_z + C(game) + C(run)', a, binomial=True), 'size_z')
    print('A with game FE: ' + fmt(t, True))
    # genuine missions only
    g = a[a.residual == 0].copy(); g['size_z'] = z(g['size'])
    t = term(gee('keep ~ size_z + C(scenario) + C(run)', g, binomial=True), 'size_z')
    print('A residuals excluded: ' + fmt(t, True))
    # elasticity: proportional checking. log(net+1) on log(size); slope<1 = proportionally less
    con['lnet'] = np.log1p(con['net'])
    t = term(gee('lnet ~ lsize + C(scenario) + C(run)', con), 'lsize')
    print('elasticity log1p(net) ~ log(size): ' + fmt(t))
    con['lraw'] = np.log(con['raw'].clip(lower=0.1))
    t = term(gee('lraw ~ lsize + C(scenario) + C(run)', con), 'lsize')
    print('elasticity log(raw, reveal NOT removed) ~ log(size): ' + fmt(t))
    t = term(gee('net ~ size_z + C(scenario) + C(run)', con), 'size_z')
    print('absolute net inspection s ~ size per SD: ' + fmt(t))
    # pre-action checking (edits' own time excluded)
    con['ppd'] = con.pre / con.drones
    t = term(gee('ppd ~ size_z + C(scenario) + C(run)', con), 'size_z')
    print('B with pre-action time per drone: ' + fmt(t))
    con['ppd_z'] = z(con['ppd'])
    m = gee('keep ~ size_z * ppd_z + C(scenario) + C(run)', con, binomial=True)
    print('C with pre-action time: interaction ' + fmt(term(m, 'size_z:ppd_z'), True)
          + ' ; main pre-action ' + fmt(term(m, 'ppd_z'), True))
    # endogeneity check: how much of the post-reveal time is editing?
    print('median net s: kept %.2f vs modified %.2f; median edits modified %.1f'
          % (con[con.keep == 1].net.median(), con[con.keep == 0].net.median(), con[con.keep == 0].nedits.median()))
    # drones and tasks separately
    con['dz'], con['tz'] = z(con.drones), z(con.tasks)
    m = gee('ipd ~ dz + tz + C(scenario) + C(run)', con)
    print('insp/drone ~ drones + tasks: drones ' + fmt(term(m, 'dz')) + ' ; tasks ' + fmt(term(m, 'tz')))
    # ratio artefact check: if absolute time were flat, per-drone time falls as 1/drones
    sp = stats.spearmanr(con['size'], con['net'])
    print('Spearman size vs absolute net inspection (decision level, ignores clustering): rho=%.3f p=%.4f n=%d' % (sp.correlation, sp.pvalue, len(con)))
    return con


def secondary_person(tac, strat, sess):
    print('\n=== SECONDARY 1: relative checking cost vs trust gap (person level, exploratory) ===')
    con = tac[tac.consulted == 1].copy()
    con['ipd'] = con.net / con.drones
    cards = strat[strat.card == 1]
    pp = pd.DataFrame(dict(
        tac_ipd=con.groupby('pid').ipd.median(),
        tac_net=con.groupby('pid').net.median(),
        strat_net=cards.groupby('pid').net.median(),
        strat_dwell=cards.groupby('pid').dwell.median(),
        strat_all=strat.groupby('pid').net.median(),
        toggles=strat.groupby('pid').toggles.mean()))
    gap = defaultdict(list)
    for s in sess:
        if s['trust_d'] is not None:
            gap[s['pid']].append(s['trust_d'])
    pp['trust_gap'] = pd.Series({k: np.mean(v) for k, v in gap.items()})
    pp['ratio'] = pp.tac_ipd / pp.strat_net
    print(pp.describe().T[['count', 'mean', '50%']])
    for x in ('ratio', 'tac_ipd', 'tac_net', 'strat_net', 'strat_dwell', 'toggles'):
        d = pp[[x, 'trust_gap']].dropna()
        d = d[np.isfinite(d[x])]
        r = stats.spearmanr(d[x], d.trust_gap)
        print('rho(%s, trust gap T-S) = %.3f p=%.4f n=%d' % (x, r.correlation, r.pvalue, len(d)))
    # direct tier comparison of checking time (the mechanism's premise)
    d = pp[['tac_net', 'strat_net']].dropna()
    w = stats.wilcoxon(d.tac_net, d.strat_net)
    print('per-person median net tactical inspection %.2f s vs net strategic card decision %.2f s; Wilcoxon p=%.4f n=%d'
          % (d.tac_net.median(), d.strat_net.median(), w.pvalue, len(d)))
    return pp


def secondary_sessions(tac):
    print('\n=== SECONDARY 2: session 1 -> 2 (exploratory) ===')
    con = tac[tac.consulted == 1].copy()
    con['ipd'] = con.net / con.drones
    rows = []
    for (pid, run), g in tac.groupby(['pid', 'run']):
        c = con[(con.pid == pid) & (con.run == run)]
        rows.append(dict(pid=pid, run=run, scenario=g.scenario.iloc[0],
                         keep=float(g.keep.mean()),
                         ipd=float(c.ipd.median()) if len(c) else None,
                         net=float(c.net.median()) if len(c) else None))
    for metric in ('ipd', 'net', 'keep'):
        res = crossover(rows, metric)
        r = res.get('run') or {}
        print('%s: run effect (run2 - run1) %s ; scenario effect (Tac - Strat) %s ; n=%s'
              % (metric, {k: r.get(k) for k in ('diff', 'ci', 'p')},
                 {k: (res.get('scenario') or {}).get(k) for k in ('diff', 'ci', 'p')}, res.get('n')))
    w = pd.DataFrame(rows).pivot(index='pid', columns='run', values='ipd').dropna()
    print('raw within-person: insp/drone fell for %d of %d (median %.3f -> %.3f s/drone)'
          % ((w[2] < w[1]).sum(), len(w), w[1].median(), w[2].median()))
    k = pd.DataFrame(rows).pivot(index='pid', columns='run', values='keep').dropna()
    print('raw within-person: keep rose for %d, fell for %d, same %d of %d'
          % ((k[2] > k[1]).sum(), (k[2] < k[1]).sum(), (k[2] == k[1]).sum(), len(k)))


def h6_link(tac, pp):
    """Exploratory: do the people who SAY they cannot check the tactical plan check it less?"""
    path = BASE / 'docs' / 'analysis' / 'round1' / 'h6_codes.csv'
    if not path.exists():
        return
    print('\n=== SECONDARY 3: stated reasons (H6 codes) vs behaviour (exploratory) ===')
    codes = pd.read_csv(path, dtype=str).fillna('').set_index('pid')
    keep = tac.groupby('pid').keep.mean()
    pp = pp.join(keep.rename('keep_rate')).join(codes[['r_cantcheck', 'pref']])
    pp['cant_T'] = pp.r_cantcheck.str.contains('T')
    for col in ('tac_ipd', 'tac_net', 'keep_rate', 'trust_gap'):
        a, b = pp[pp.cant_T][col].dropna(), pp[~pp.cant_T][col].dropna()
        u = stats.mannwhitneyu(a, b)
        print('%s: says cannot check tactical (n=%d) median %.3f vs others (n=%d) %.3f ; MWU p=%.4f'
              % (col, len(a), a.median(), len(b), b.median(), u.pvalue))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    tac, strat, new = load()
    print('participants %d; v1.12+ cohort %d: %s' % (tac.pid.nunique(), len(new), sorted(new)))
    print('note: %d consulted plans with raw interval < reveal time (clipped to 0 net)'
          % int(((tac.consulted == 1) & (tac.raw < tac.entries * REVEAL_S)).sum()))
    res = primary(tac, 'all 33')
    res_new = primary(tac[tac.pid.isin(new)], 'v1.12+ cohort')
    robustness(tac)
    print('\n--- robustness on v1.12+ ---')
    robustness(tac[tac.pid.isin(new)])
    sess, _ = load_people()
    pp = secondary_person(tac, strat, sess)
    secondary_sessions(tac)
    h6_link(tac, pp)
    print('\nSUMMARY primary all-33: p_IUT=%.4f %s ; v1.12+: p_IUT=%.4f %s'
          % (res['p'], res['verdict'], res_new['p'], res_new['verdict']))


if __name__ == '__main__':
    main()
