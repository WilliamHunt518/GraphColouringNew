#!/usr/bin/env python3
"""
H3 (analysis round 1) -- failure recovery: does using the Tactical Assistant's Suggest still predict
fewer abandonments WITHIN a person and on FIXABLE failures -- and what happens when Suggest fails?

Pre-registered in docs/analysis/HYPOTHESES_ROUND1.md (H3 + 2026-10-07 amendments). Report:
docs/analysis/round1/h3_recovery.md. Read-only on Results/; writes nothing at all (prints only).

Run from the repo root:
    C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h3_recovery.py

Structure
  1. parse every session into recovery episodes, with a time-local reconstruction of which drones
     were on the mission (idle / executing) at the failure and at every Suggest press
  2. PRIMARY: GEE logit, abandoned ~ usedSuggest + person-mean(usedSuggest), fixable episodes,
     exchangeable within participant; all 33 + v1.12+ sensitivity
  3. robustness specifications (logged as the analysis log in the report)
  4. Suggest-press classification (solved / partial / failed / no-op) and what operators did next
  5. does experiencing a failed Suggest change later recovery Suggest use, tactical keep-unmodified
     rate, and post-session tactical trust
"""
import json, math, sys, warnings
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'scripts'))
import study_analysis as sa                       # noqa: E402  (read_session, coverable, episode_pattern)
from build_findings_synthesis import gee, term   # noqa: E402  (the shared GEE helpers)
from agent_scenario_stats import events, vrank   # noqa: E402

warnings.filterwarnings('ignore')
LOG_DIR = BASE / 'Results' / 'Participants'
EXCLUDE = {'P09'}
V112 = vrank('study-v1.12')
V15 = vrank('study-v1.5')   # recovery Suggest pool widened from idle-only to not-executing


def r3(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), 3)


# ---------------------------------------------------------------------------------------------
# 1. Parsing
# ---------------------------------------------------------------------------------------------

def parse_session(evs, pid, run):
    start = next((e for e in evs if e['type'] == 'session_start'), None)
    end = next((e for e in evs if e['type'] == 'session_ended'), None)
    if not start or not end or start.get('complexity') not in ('strategic', 'tactical'):
        return None
    ver = start.get('appVersion') or 'pre-tag'
    vr = vrank(ver)
    comps = {}
    for e in evs:
        if e['type'] == 'mission_arrived':
            comps.update(e.get('taskCompositions') or {})

    snaps = [e for e in evs if e['type'] == 'state_snapshot']
    snap_t = [s['elapsed'] for s in snaps]
    fails = [(e['elapsed'], e.get('droneId')) for e in evs if e['type'] == 'drone_failure']
    tac_open = [(e['elapsed'], e['missionId'], e.get('dronePool') or []) for e in evs if e['type'] == 'tactical_opened']
    # execution intervals per mission: [start, end) with the drones that worked the task
    iv = defaultdict(list)
    for e in evs:
        if e['type'] == 'task_completed' and e.get('startTime') is not None:
            iv[e['missionId']].append((e['startTime'], e['completionTime'], set(e.get('assetsUsed') or []), e['taskId']))
        elif e['type'] == 'task_failed' and e.get('startTime') is not None and e.get('statusBefore') == 'executing':
            iv[e['missionId']].append((e['startTime'], e['elapsed'], set(e.get('assignedAssetIds') or []), e['taskId']))
        # Fixed 2026-10-07 (combined-page follow-up): a task cut short by ABANDONMENT is logged as
        # task_requeued, not completed/failed. Without this its drones looked free while it ran, so a
        # Suggest press that the app answered "No workable plan" (the executing drone excluded) was
        # rebuilt as "solved" -- exactly in the episodes that end in abandonment. Found because three
        # operators read "No workable plan" aloud seconds after presses scored as solved.
        elif e['type'] == 'task_requeued' and e.get('statusBefore') == 'executing':
            iv[e['missionId']].append((e['elapsed'] - (e.get('executionProgress') or 0.0), e['elapsed'],
                                       set(e.get('assignedAssetIds') or []), e['taskId']))

    def snap_before(t):
        import bisect
        i = bisect.bisect_right(snap_t, t) - 1
        return snaps[i] if i >= 0 else None

    def snap_after(t):
        import bisect
        i = bisect.bisect_right(snap_t, t)
        return snaps[i] if i < len(snaps) else None

    def executing(t, m):
        out = set()
        for s0, s1, ids, _ in iv.get(m, []):
            if s0 <= t < s1:
                out |= ids
        return out

    def members(t, m):
        """Drones deployed on mission m at time t: latest snapshot, corrected for what happened since."""
        S = snap_before(t)
        st = S['elapsed'] if S else -1
        base = {a['id'] for a in (S['assets'] if S else [])
                if a.get('currentMissionId') == m and a.get('status') == 'deployed'}
        for te, mm, pool in tac_open:
            if mm == m and st < te <= t:
                base |= set(pool)
        base -= {d for te, d in fails if st < te <= t}
        A = snap_after(t)
        amem = {a['id'] for a in A['assets'] if a.get('currentMissionId') == m and a.get('status') == 'deployed'} if A else set()
        for s0, s1, ids, _ in iv.get(m, []):
            if st < s1 <= t:                      # finished executing since the snapshot
                for d in ids & base:
                    if A is not None and d not in amem:
                        base.discard(d)           # ...and flew home (no next task)
        return base

    def snap_task(t, m):
        S = snap_before(t)
        if not S:
            return {}
        mm = next((x for x in S['missions'] if x['id'] == m), None)
        return {tk['id']: tk for tk in (mm['tasks'] if mm else [])}

    def snap_cur_task(t):
        S = snap_before(t)
        return {a['id']: a.get('currentTaskId') for a in (S['assets'] if S else [])}

    episodes, presses = [], []
    open_ep = {}
    for e in evs:
        t, m, el = e['type'], e.get('missionId'), e.get('elapsed')
        if t == 'recovery_opened':
            affected = e.get('affectedTaskIds') or []
            mem = members(el, m)
            exe = executing(el, m)
            idle_logged = set(e.get('onMissionDroneIds') or [])
            recon_idle = mem - exe
            st = snap_task(el, m)
            plan = {tid: set() for tid in affected}
            for tid, tk in st.items():
                if tk.get('status') == 'pending' and tid not in plan:
                    plan[tid] = set(tk.get('assignedAssetIds') or [])
            all_live = mem | idle_logged
            ep = dict(pid=pid, run=run, version=ver, vrank=vr, scenario=start.get('complexity'),
                      missionId=m, category=e.get('missionCategory'), opened=el,
                      timeRemaining=e.get('timeRemainingInSession'), tasksRemaining=e.get('tasksRemaining'),
                      affected=affected, fixIdleLogged=bool(e.get('feasibleWithOnMissionDrones')),
                      fixIdleRecon=all(sa.coverable(comps.get(x), recon_idle) for x in affected),
                      fixAll=all(sa.coverable(comps.get(x), all_live) for x in affected),
                      reconMatch=(recon_idle == idle_logged), reconDiff=len(recon_idle ^ idle_logged),
                      nIdle=len(idle_logged), nBusy=len(exe & mem),
                      suggest=0, drags=0, events=[], plan=plan, presses=[])
            open_ep[m] = ep
        elif m in open_ep:
            ep = open_ep[m]
            if t == 'tactical_suggest_used' and e.get('recoveryMode'):
                ep['suggest'] += 1
                mem = members(el, m)
                exe = executing(el, m)
                pool = mem - exe
                if ep['vrank'] < V15:
                    # pre-v1.5: Suggest drew only on drones with no current task (idle); a drone
                    # flying to an unstarted task was not offered. Survivors of the failed task were
                    # released at the failure, so a stale snapshot showing them on it still counts.
                    cur = snap_cur_task(el)
                    pool = {d for d in pool if cur.get(d) in (None, *ep['affected'])}
                live = {k: (v & mem) for k, v in ep['plan'].items()}
                short = [k for k, v in live.items() if not sa.coverable(comps.get(k), v)]
                if not short:
                    res = 'noop'
                else:
                    ok = [k for k in short if sa.coverable(comps.get(k), pool)]
                    res = 'solved' if len(ok) == len(short) else 'partial' if ok else 'failed'
                    for k in ok:
                        ep['plan'][k] = set(pool)
                fixable_now = bool(short) and all(sa.coverable(comps.get(k), mem) for k in short)
                pr = dict(pid=pid, run=run, vrank=ep['vrank'], missionId=m, opened=ep['opened'], at=el,
                          idx=ep['suggest'], result=res, nShort=len(short),
                          fixableWithBusy=fixable_now, blind=(res in ('failed', 'partial') and fixable_now),
                          poolSize=len(pool), busyOnMission=len(exe & mem), dragsBefore=ep['drags'])
                ep['presses'].append(pr)
                ep['events'].append(('suggest', el, res))
            elif t == 'tactical_assignment_changed':
                ep['drags'] += 1
                op, d, tid = e.get('op'), e.get('droneId'), e.get('taskId')
                if op == 'assign':
                    for v in ep['plan'].values():
                        v.discard(d)
                    if tid in ep['plan']:
                        ep['plan'][tid].add(d)
                elif op == 'chain' and tid in ep['plan']:
                    ep['plan'][tid].add(d)
                elif op == 'remove' and tid in ep['plan']:
                    ep['plan'][tid].discard(d)
                elif op == 'unassign':
                    for v in ep['plan'].values():
                        v.discard(d)
                ep['events'].append(('drag', el, op))
            elif t in ('failure_recovery', 'mission_abandoned'):
                rec = t == 'failure_recovery'
                ep.update(outcome='recovered' if rec else 'abandoned', closed=el,
                          agentPlan=bool(e.get('wasAgentSuggested')) if rec else None,
                          stillUnassigned=len(e.get('tasksStillUnassigned') or []) if rec else None)
                ep['events'].append(('recovered' if rec else 'abandoned', el, None))
                episodes.append(open_ep.pop(m))
    for ep in open_ep.values():
        ep.update(outcome='unresolved', closed=sa.SESSION_S, agentPlan=None, stillUnassigned=None)
        ep['events'].append(('session_end', sa.SESSION_S, None))
        episodes.append(ep)
    for ep in episodes:
        for pr in ep['presses']:
            pr['outcome'] = ep['outcome']
            # what the operator did right after this press
            evs_after = [x for x in ep['events'] if x[1] >= pr['at'] and not (x[0] == 'suggest' and x[1] == pr['at'])]
            nxt = evs_after[0][0] if evs_after else 'none'
            pr['next'] = {'suggest': 'retry Suggest', 'drag': 'edit by hand', 'recovered': 'deploy',
                          'abandoned': 'abandon', 'session_end': 'left open'}.get(nxt, nxt)
            pr['dragsAfter'] = len([x for x in ep['events'] if x[0] == 'drag' and x[1] >= pr['at']])
            pr['agentPlan'] = ep['agentPlan']
        del ep['plan']
    return dict(start=start, episodes=episodes, version=ver, vrank=vr)


def surveys(evs):
    sv = {e['surveyName']: (e.get('responses') or {}) for e in evs if e['type'] == 'survey_response'}
    mean = lambda d: float(np.mean(list(d.values()))) if d else None
    return mean(sv.get('trust_tactical')), mean(sv.get('trust_strategic'))


def load_all():
    eps, trust = [], []
    for f in sorted(LOG_DIR.glob('P*.json')):
        pid = f.stem
        if pid in EXCLUDE:
            continue
        d = json.loads(f.read_text(encoding='utf-8'))
        for i, s in enumerate(d.get('sessions') or []):
            evs = events(s)
            r = parse_session(evs, pid, i + 1)
            if not r:
                continue
            eps += r['episodes']
            tt, ts = surveys(evs)
            trust.append(dict(pid=pid, run=i + 1, vrank=r['vrank'], trustTac=tt, trustStrat=ts,
                              scenario=r['start'].get('complexity')))
    # join the study_analysis pattern + its original feasibleWithBusy (for comparison)
    _, decisions, sa_eps = sa.load()
    key = lambda e: (e['pid'], e['run'], e['missionId'], round(e['opened'], 3))
    pat = {key(e): e for e in sa_eps}
    for e in eps:
        o = pat.get(key(e))
        e['pattern'] = o['pattern'] if o else None
        e['fixBusyOrig'] = o['feasibleWithBusy'] if o else None
    decisions = [d for d in decisions if d['pid'] not in EXCLUDE]
    return eps, pd.DataFrame(trust), decisions


# ---------------------------------------------------------------------------------------------
# 2-3. Primary + robustness
# ---------------------------------------------------------------------------------------------

def or_row(m, name):
    t = term(m, name)
    return dict(OR=r3(math.exp(t['b'])), lo=r3(math.exp(t['lo'])), hi=r3(math.exp(t['hi'])), p=r3(t['p']), b=r3(t['b']))


def episode_frame(eps, fix_key='fixAll', cohort='all', keep_unresolved=False):
    rows = []
    for e in eps:
        if not e[fix_key]:
            continue
        if cohort == 'v112' and e['vrank'] < V112:
            continue
        if cohort == 'v15' and e['vrank'] < V15:
            continue
        if e['outcome'] == 'unresolved' and not keep_unresolved:
            continue
        rows.append(dict(pid=e['pid'], run=e['run'], abandoned=float(e['outcome'] != 'recovered'),
                         sug=float(e['suggest'] > 0), tacScen=float(e['scenario'] == 'tactical'),
                         run2=float(e['run'] == 2), timeLeft=(e['timeRemaining'] or 0) / 60,
                         idleFix=float(e['fixIdleLogged']), cat=e['category'],
                         catn='ABCDE'.index(e['category']) if e['category'] in 'ABCDE' else 2,
                         drags=float(e['drags'] > 0)))
    df = pd.DataFrame(rows)
    df['pm_sug'] = df.groupby('pid').sug.transform('mean')
    df['w_sug'] = df.sug - df.pm_sug
    return df


def describe_frame(df):
    s = df[df.sug == 1]; n = df[df.sug == 0]
    within = df.groupby('pid').sug.agg(lambda x: 0 < x.mean() < 1)
    ab_within = df[df.pid.isin(within[within].index)]
    return dict(n=len(df), people=int(df.pid.nunique()),
                withSuggest=f"{int(s.abandoned.sum())}/{len(s)} abandoned ({s.abandoned.mean():.0%})",
                withoutSuggest=f"{int(n.abandoned.sum())}/{len(n)} abandoned ({n.abandoned.mean():.0%})",
                peopleWithWithinVariation=int(within.sum()),
                episodesFromThem=len(ab_within),
                peopleAllSuggest=int((df.groupby('pid').sug.mean() == 1).sum()),
                peopleNoSuggest=int((df.groupby('pid').sug.mean() == 0).sum()),
                peopleWithAnyAbandon=int((df.groupby('pid').abandoned.max() == 1).sum()))


def fit(df, formula, name='sug'):
    try:
        m = gee(formula, df, binomial=True)
        return or_row(m, name)
    except Exception as ex:
        return dict(error=str(ex)[:120])


def cond_logit(df):
    from statsmodels.discrete.conditional_models import ConditionalLogit
    keep = df.groupby('pid').filter(lambda g: g.abandoned.nunique() > 1 and g.sug.nunique() > 1)
    if keep.empty:
        return dict(error='no informative clusters')
    m = ConditionalLogit(keep.abandoned.values, keep[['sug']].values, groups=keep.pid.values).fit(disp=0)
    b, se = m.params[0], m.bse[0]
    return dict(OR=r3(math.exp(b)), lo=r3(math.exp(b - 1.96 * se)), hi=r3(math.exp(b + 1.96 * se)),
                p=r3(m.pvalues[0]), n=len(keep), people=int(keep.pid.nunique()))


def detectable_or(df, alpha=0.05, power=0.8):
    """Rough minimum detectable within-person OR: the SE of the primary log-OR times (z_a + z_b)."""
    try:
        m = gee('abandoned ~ sug + pm_sug', df, binomial=True)
        se = float(m.bse['sug'])
        k = stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power)
        return dict(se=r3(se), minDetectableOR_protective=r3(math.exp(-k * se)))
    except Exception:
        return None


# ---------------------------------------------------------------------------------------------
# 5. Exposure to a failed Suggest
# ---------------------------------------------------------------------------------------------

def exposure(eps, decisions, trust, presses):
    out = {}
    by_pid = defaultdict(list)
    for e in eps:
        by_pid[e['pid']].append(e)
    # chronological key across the two runs
    tkey = lambda run, t: run * 1000 + t
    first_fail, first_press, first_ok = {}, {}, {}
    for p in sorted(presses, key=lambda p: (p['pid'], tkey(p['run'], p['at']))):
        k = tkey(p['run'], p['at'])
        first_press.setdefault(p['pid'], (k, p['run']))
        if p['blind']:
            first_fail.setdefault(p['pid'], (k, p['run']))
        if p['result'] == 'solved':
            first_ok.setdefault(p['pid'], (k, p['run']))
    users = sorted(first_press)
    exposed = sorted(first_fail)
    out['recoverySuggestUsers'] = len(users)
    out['exposedPeople'] = exposed
    out['nExposed'] = len(exposed)
    # exposure vs opportunity: presses per person among the exposed vs unexposed users
    npress = Counter(p['pid'] for p in presses)
    out['pressesPerPerson'] = dict(
        exposed=r3(np.mean([npress[p] for p in exposed])) if exposed else None,
        unexposedUsers=r3(np.mean([npress[p] for p in users if p not in first_fail])) if users else None)

    # (a) later recovery Suggest use: episodes opened AFTER the person's first failed Suggest vs
    # episodes after the first press of someone who had not (yet) had a failure. Time-varying
    # exposure, among people who had pressed Suggest at least once before the episode.
    rows = []
    for e in eps:
        pid = e['pid']
        if pid not in first_press:
            continue
        k = tkey(e['run'], e['opened'])
        if k <= first_press[pid][0]:
            continue                                            # not yet a Suggest user
        prior_fail = pid in first_fail and first_fail[pid][0] < k
        prior_ok = len([p for p in presses if p['pid'] == pid and p['result'] == 'solved' and tkey(p['run'], p['at']) < k])
        rows.append(dict(pid=pid, sug=float(e['suggest'] > 0), priorFail=float(prior_fail),
                         priorOk=float(prior_ok > 0), run2=float(e['run'] == 2), fixAll=float(e['fixAll'])))
    df = pd.DataFrame(rows)
    out['laterUse'] = dict(
        n=len(df), people=int(df.pid.nunique()),
        afterFailure=f"{int(df[df.priorFail == 1].sug.sum())}/{int((df.priorFail == 1).sum())}",
        noPriorFailure=f"{int(df[df.priorFail == 0].sug.sum())}/{int((df.priorFail == 0).sum())}",
        gee=fit(df, 'sug ~ priorFail + run2', 'priorFail') if df.priorFail.nunique() > 1 else None)
    # within-person among the exposed: their episodes before vs after their first failure
    pre, post = [], []
    for pid in exposed:
        k0 = first_fail[pid][0]
        es = by_pid[pid]
        pre_e = [e['suggest'] > 0 for e in es if tkey(e['run'], e['opened']) < k0]
        post_e = [e['suggest'] > 0 for e in es if tkey(e['run'], e['opened']) > k0]
        pre.append((pid, np.mean(pre_e) if pre_e else None, len(pre_e)))
        post.append((pid, np.mean(post_e) if post_e else None, len(post_e)))
    out['exposedPrePost'] = [dict(pid=a[0], preRate=r3(a[1]), nPre=a[2], postRate=r3(b[1]), nPost=b[2])
                             for a, b in zip(pre, post)]

    # (b) tactical keep-unmodified: DiD. Event = person's first recovery Suggest press. Exposed =
    # that press (or any press up to their first failure) failed. Tactical decisions before vs after.
    tac = [d for d in decisions if d['tier'] == 'tactical']
    rows = []
    for d in tac:
        pid = d['pid']
        if pid not in first_press:
            continue
        k = tkey(d['run'], d['elapsed'])
        ev_k = first_fail[pid][0] if pid in first_fail else first_press[pid][0]
        rows.append(dict(pid=pid, accepted=float(d['accepted']), consulted=float(d['used']),
                         post=float(k > ev_k), exposed=float(pid in first_fail),
                         run2=float(d['run'] == 2), tacScen=float(d['scenario'] == 'tactical')))
    tdf = pd.DataFrame(rows)
    tdf['postXexp'] = tdf.post * tdf.exposed
    cells = tdf.groupby(['exposed', 'post']).accepted.agg(['mean', 'size']).round(3)
    out['tacticalKeep'] = dict(
        cells={f"exposed={int(a)},post={int(b)}": dict(rate=r3(v['mean']), n=int(v['size']))
               for (a, b), v in cells.iterrows()},
        did=fit(tdf, 'accepted ~ post + exposed + postXexp + run2 + tacScen', 'postXexp'),
        didConsultedOnly=fit(tdf[tdf.consulted == 1], 'accepted ~ post + exposed + postXexp + run2 + tacScen', 'postXexp'),
        didConsult=fit(tdf, 'consulted ~ post + exposed + postXexp + run2 + tacScen', 'postXexp'))

    # (c) tactical trust (post-session). Session-level: was a failed Suggest experienced IN this
    # session? Compare trust in that session; and s1->s2 change for people exposed in s1 vs not.
    fail_sessions = {(p['pid'], p['run']) for p in presses if p['blind']}
    press_sessions = {(p['pid'], p['run']) for p in presses}
    tr = trust.copy()
    tr['failHere'] = [float((r.pid, r.run) in fail_sessions) for r in tr.itertuples()]
    tr['pressHere'] = [float((r.pid, r.run) in press_sessions) for r in tr.itertuples()]
    tr = tr.dropna(subset=['trustTac'])
    sub = tr[tr.pressHere == 1]
    out['trustSession'] = dict(
        sessionsWithFailure=dict(mean=r3(sub[sub.failHere == 1].trustTac.mean()), n=int((sub.failHere == 1).sum())),
        sessionsPressNoFailure=dict(mean=r3(sub[sub.failHere == 0].trustTac.mean()), n=int((sub.failHere == 0).sum())),
        gee_amongPressSessions=None)
    try:
        m = gee('trustTac ~ failHere + C(run) + C(scenario)', sub)
        out['trustSession']['gee_amongPressSessions'] = {k: r3(v) for k, v in term(m, 'failHere').items()}
        m2 = gee('trustTac ~ failHere + pressHere + C(run) + C(scenario)', tr)
        out['trustSession']['gee_allSessions'] = {k: r3(v) for k, v in term(m2, 'failHere').items()}
    except Exception as ex:
        out['trustSession']['error'] = str(ex)[:100]
    # change s1 -> s2 by whether the s1 session had a failed Suggest
    w = tr.pivot_table(index='pid', columns='run', values='trustTac')
    w['d'] = w[2] - w[1]
    f1 = {p for (p, r) in fail_sessions if r == 1}
    u1 = {p for (p, r) in press_sessions if r == 1}
    a = w[w.index.isin(f1)].d.dropna(); b = w[w.index.isin(u1 - f1)].d.dropna(); c = w[~w.index.isin(u1)].d.dropna()
    out['trustChange'] = dict(
        exposedS1=dict(mean=r3(a.mean()), n=len(a)), pressedS1NoFailure=dict(mean=r3(b.mean()), n=len(b)),
        noPressS1=dict(mean=r3(c.mean()), n=len(c)),
        mannWhitney_exposed_vs_pressedOK=(r3(stats.mannwhitneyu(a, b).pvalue) if len(a) and len(b) else None))
    # person-level: ever exposed vs Suggest users never exposed, mean tactical trust over both sessions
    pm = tr.groupby('pid').trustTac.mean()
    ea = pm[pm.index.isin(exposed)]; eb = pm[pm.index.isin(set(users) - set(exposed))]
    out['trustPerson'] = dict(exposed=dict(mean=r3(ea.mean()), n=len(ea)), unexposedUsers=dict(mean=r3(eb.mean()), n=len(eb)),
                              mannWhitneyP=r3(stats.mannwhitneyu(ea, eb).pvalue) if len(ea) and len(eb) else None)
    return out


# ---------------------------------------------------------------------------------------------

def main():
    eps, trust, decisions = load_all()
    print(f"episodes (P09 excluded): {len(eps)} from {len({e['pid'] for e in eps})} participants")
    print('outcomes:', dict(Counter(e['outcome'] for e in eps)))

    # --- reconstruction checks -------------------------------------------------------------
    print('\n## Reconstruction checks')
    print('idle pool reconstructed == logged onMissionDroneIds:',
          f"{sum(e['reconMatch'] for e in eps)}/{len(eps)}",
          '| mean |sym diff| when not:', r3(np.mean([e['reconDiff'] for e in eps if not e['reconMatch']] or [0])))
    print('idle-fixable reconstructed == logged flag:',
          f"{sum(e['fixIdleRecon'] == e['fixIdleLogged'] for e in eps)}/{len(eps)}")
    print('fixability crosstab (logged idle-only flag, corrected all-drones, original feasibleWithBusy):')
    print(' ', dict(Counter((e['fixIdleLogged'], e['fixAll'], e['fixBusyOrig']) for e in eps)))
    print('  idle-fixable but not all-fixable (should be 0):', sum(e['fixIdleLogged'] and not e['fixAll'] for e in eps))

    # --- descriptive split, all 33 ---------------------------------------------------------
    print('\n## Descriptive Suggest split')
    for fk in ('fixAll', 'fixIdleLogged'):
        for coh in ('all', 'v112'):
            df = episode_frame(eps, fk, coh)
            print(f'  {fk:13s} {coh:5s}', describe_frame(df))

    # --- PRIMARY -----------------------------------------------------------------------------
    print('\n## PRIMARY: GEE logit abandoned ~ usedSuggest + person-mean(usedSuggest), fixable (all live mission drones)')
    prim = {}
    for coh in ('all', 'v112'):
        df = episode_frame(eps, 'fixAll', coh)
        res = fit(df, 'abandoned ~ sug + pm_sug')
        res.update(n=len(df), people=int(df.pid.nunique()))
        res['between_pm_sug'] = fit(df, 'abandoned ~ sug + pm_sug', 'pm_sug')
        res['detectable'] = detectable_or(df)
        prim[coh] = res
        print(f'  {coh}:', res)

    # --- robustness ---------------------------------------------------------------------------
    print('\n## Robustness (analysis log)')
    specs = [
        ('R1 fixable = logged idle-only flag (as the page split)', 'fixIdleLogged', 'all', False, 'abandoned ~ sug + pm_sug'),
        ('R1b same, v1.12+', 'fixIdleLogged', 'v112', False, 'abandoned ~ sug + pm_sug'),
        ('R2 fixable = original study_analysis feasibleWithBusy', 'fixBusyOrig', 'all', False, 'abandoned ~ sug + pm_sug'),
        ('R3 unresolved counted as not recovered', 'fixAll', 'all', True, 'abandoned ~ sug + pm_sug'),
        ('R4 + run, scenario', 'fixAll', 'all', False, 'abandoned ~ sug + pm_sug + run2 + tacScen'),
        ('R5 + run, scenario, time left, idle-fixable, category', 'fixAll', 'all', False,
         'abandoned ~ sug + pm_sug + run2 + tacScen + timeLeft + idleFix + catn'),
        ('R6 v1.5+ only (current Suggest pool)', 'fixAll', 'v15', False, 'abandoned ~ sug + pm_sug'),
        ('R7 pooled (no person-mean): total association', 'fixAll', 'all', False, 'abandoned ~ sug'),
        ('R7b pooled, v1.12+', 'fixAll', 'v112', False, 'abandoned ~ sug'),
        ('R8 within-centred Suggest (w_sug) + pm', 'fixAll', 'all', False, 'abandoned ~ w_sug + pm_sug'),
    ]
    rob = []
    for lab, fk, coh, keep_u, fml in specs:
        df = episode_frame(eps, fk, coh, keep_u)
        nm = 'w_sug' if 'w_sug' in fml else 'sug'
        r = fit(df, fml, nm); r.update(n=len(df), people=int(df.pid.nunique()))
        rob.append((lab, r)); print(f'  {lab}:', r)
    for coh in ('all', 'v112'):
        r = cond_logit(episode_frame(eps, 'fixAll', coh))
        print(f'  R9 conditional (fixed-effect) logit, {coh}:', r)
        r = cond_logit(episode_frame(eps, 'fixIdleLogged', coh))
        print(f'  R9b conditional logit, idle-fixable, {coh}:', r)
    # R10: exclude pre-v1.5 participants AND people with no within-person variation is implicit in CL.
    # R11: Suggest-press timing -- is "used Suggest" partly an outcome of a long episode? episode latency
    lat = pd.DataFrame([dict(sug=e['suggest'] > 0, lat=e['closed'] - e['opened'], out=e['outcome'])
                        for e in eps if e['fixAll'] and e['outcome'] != 'unresolved'])
    print('  R11 median episode latency (s) by Suggest x outcome:',
          lat.groupby(['sug', 'out']).lat.median().round(1).to_dict())
    # R12: Suggest used AND it produced a plan, vs pressed-but-nothing (separates consultation from help)
    rows = []
    for e in eps:
        if not e['fixAll'] or e['outcome'] == 'unresolved':
            continue
        got = any(p['result'] in ('solved', 'partial') for p in e['presses'])
        rows.append(dict(pid=e['pid'], abandoned=float(e['outcome'] == 'abandoned'),
                         sugGot=float(got), sugEmpty=float(e['suggest'] > 0 and not got)))
    d12 = pd.DataFrame(rows)
    d12['pm_got'] = d12.groupby('pid').sugGot.transform('mean')
    d12['pm_empty'] = d12.groupby('pid').sugEmpty.transform('mean')
    print('  R12 three-way split abandoned rate: Suggest gave a plan',
          f"{int(d12[d12.sugGot == 1].abandoned.sum())}/{int(d12.sugGot.sum())}",
          '| Suggest pressed but gave nothing', f"{int(d12[d12.sugEmpty == 1].abandoned.sum())}/{int(d12.sugEmpty.sum())}",
          '| no Suggest', f"{int(d12[(d12.sugGot == 0) & (d12.sugEmpty == 0)].abandoned.sum())}/{int(((d12.sugGot == 0) & (d12.sugEmpty == 0)).sum())}")
    print('  R12 GEE sugGot + sugEmpty + person means:',
          dict(got=fit(d12, 'abandoned ~ sugGot + sugEmpty + pm_got + pm_empty', 'sugGot'),
               empty=fit(d12, 'abandoned ~ sugGot + sugEmpty + pm_got + pm_empty', 'sugEmpty')))

    # R13: among episodes where the operator attempted anything (a drag or a Suggest press) --
    # removes the 'abandoned without trying' episodes, which can only fall in the no-Suggest arm
    for coh in ('all', 'v112'):
        df = episode_frame(eps, 'fixAll', coh)
        df = df[(df.sug == 1) | (df.drags == 1)].copy()
        df['pm_sug'] = df.groupby('pid').sug.transform('mean')
        r = fit(df, 'abandoned ~ sug + pm_sug'); r.update(n=len(df), people=int(df.pid.nunique()))
        print(f'  R13 attempted episodes only (drag or Suggest), {coh}:', r,
              '| Suggest', f"{int(df[df.sug == 1].abandoned.sum())}/{int(df.sug.sum())}",
              '| drags only', f"{int(df[df.sug == 0].abandoned.sum())}/{int((df.sug == 0).sum())}")
    # R14: attempt type crosstab
    print('  R14 attempt type x outcome (fixable, resolved):',
          dict(Counter((('S' if e['suggest'] else '-') + ('D' if e['drags'] else '-'), e['outcome'])
                       for e in eps if e['fixAll'] and e['outcome'] != 'unresolved')))
    # R15: Suggest pressed BEFORE any manual edit (Suggest as the first move)
    rows = []
    for e in eps:
        if not e['fixAll'] or e['outcome'] == 'unresolved':
            continue
        first = next((x[0] for x in e['events'] if x[0] in ('suggest', 'drag')), None)
        rows.append(dict(pid=e['pid'], abandoned=float(e['outcome'] == 'abandoned'), sug=float(first == 'suggest')))
    d15 = pd.DataFrame(rows); d15['pm_sug'] = d15.groupby('pid').sug.transform('mean')
    print('  R15 Suggest as first move:', fit(d15, 'abandoned ~ sug + pm_sug'))

    # R16: small-sample (Mancl-DeRouen bias-reduced) sandwich SE for the primary -- 32 clusters
    import statsmodels.api as sm, statsmodels.formula.api as smf
    for coh in ('all', 'v112'):
        df = episode_frame(eps, 'fixAll', coh)
        m = smf.gee('abandoned ~ sug + pm_sug', 'pid', data=df, family=sm.families.Binomial(),
                    cov_struct=sm.cov_struct.Exchangeable()).fit(cov_type='bias_reduced')
        ci = m.conf_int().loc['sug']
        print(f'  R16 bias-reduced SE, {coh}:', dict(OR=r3(math.exp(m.params['sug'])), lo=r3(math.exp(ci[0])),
              hi=r3(math.exp(ci[1])), p=r3(m.pvalues['sug'])))
    # R17: person-level paired test -- among people with both kinds of fixable episode, abandonment
    # rate with Suggest minus without (Wilcoxon signed-rank)
    for coh in ('all', 'v112'):
        df = episode_frame(eps, 'fixAll', coh)
        g = df.groupby(['pid', 'sug']).abandoned.mean().unstack().dropna()
        dd = g[1.0] - g[0.0]
        w = stats.wilcoxon(dd) if (dd != 0).any() else None
        print(f'  R17 paired person-level, {coh}: people={len(dd)}, mean diff (Suggest - not) = {dd.mean():+.3f},',
              f'lower with Suggest {int((dd < 0).sum())}, higher {int((dd > 0).sum())}, equal {int((dd == 0).sum())},',
              f'Wilcoxon p = {r3(w.pvalue) if w else None}')

    # --- 4. Suggest-press classification -----------------------------------------------------
    presses = [p for e in eps for p in e['presses']]
    print('\n## Suggest presses in recovery')
    print('  total presses:', len(presses), '| episodes with >=1 press:', sum(e['suggest'] > 0 for e in eps),
          '| people:', len({p['pid'] for p in presses}))
    print('  result:', dict(Counter(p['result'] for p in presses)))
    print('  result, pre-v1.5:', dict(Counter(p['result'] for p in presses if p['vrank'] < V15)),
          '| v1.5+:', dict(Counter(p['result'] for p in presses if p['vrank'] >= V15)))
    print('  failed/partial with the fix available via a busy drone (blind spot):',
          sum(p['blind'] for p in presses), '| failed/partial and not fixable even with busy drones:',
          sum(p['result'] in ('failed', 'partial') and not p['blind'] for p in presses))
    # validation against the log: an episode recovered with wasAgentSuggested must have had a
    # press that returned something (v1.6+, where the flag is no longer cleared by a task finishing)
    chk = [e for e in eps if e['vrank'] >= vrank('study-v1.6') and e['suggest'] > 0 and e['outcome'] == 'recovered']
    agree = Counter((bool(e['agentPlan']), any(p['result'] in ('solved', 'partial') for p in e['presses'])) for e in chk)
    print('  validation v1.6+ recovered-with-press episodes, (wasAgentSuggested, reconstructed non-empty):', dict(agree))
    # solved press followed directly by deploy with no edits
    print('  solved presses followed by deploy with no edits:',
          sum(p['result'] == 'solved' and p['next'] == 'deploy' for p in presses),
          '/ solved', sum(p['result'] == 'solved' for p in presses))
    print('  next action after press, by result:')
    for res in ('solved', 'partial', 'failed', 'noop'):
        ps = [p for p in presses if p['result'] == res]
        print(f'    {res:8s} n={len(ps):3d}', dict(Counter(p['next'] for p in ps)), '| episode outcome:',
              dict(Counter(p['outcome'] for p in ps)))
    bl = [p for p in presses if p['blind']]
    print('  BLIND-SPOT presses (failed/partial, fixable with a busy drone): n =', len(bl),
          'people =', len({p['pid'] for p in bl}), 'episodes =', len({(p['pid'], p['run'], p['missionId'], p['opened']) for p in bl}))
    print('    next action:', dict(Counter(p['next'] for p in bl)))
    # per episode: final outcome of episodes that had a blind-spot press
    bep = [e for e in eps if any(p['blind'] for p in e['presses'])]
    print('    episode outcome:', dict(Counter(e['outcome'] for e in bep)),
          '| recovered with an agent plan in the end:', sum(bool(e['agentPlan']) for e in bep),
          '| edited by hand after the failed press:', sum(any(p['blind'] and p['dragsAfter'] > 0 for p in e['presses']) for e in bep))
    print('    patterns:', dict(Counter(e['pattern'] for e in bep)))
    for e in bep:
        print('     ', e['pid'], 'run', e['run'], e['missionId'], f"t={e['opened']:.0f}", e['outcome'], e['pattern'],
              [(round(x[1] - e['opened'], 1), x[0], x[2]) for x in e['events']][:12])
    print('  failed/partial presses by (pre-v1.5, idle-fixable at open, all-fixable at open, fixable w/ busy at press):',
          dict(Counter((p['vrank'] < V15, e['fixIdleLogged'], e['fixAll'], p['fixableWithBusy'])
                       for e in eps for p in e['presses'] if p['result'] in ('failed', 'partial'))))
    print('  non-blind failed/partial presses: next action', dict(Counter(p['next'] for p in presses
          if p['result'] in ('failed', 'partial') and not p['blind'])), '| outcome',
          dict(Counter(p['outcome'] for p in presses if p['result'] in ('failed', 'partial') and not p['blind'])))
    sta = [e for e in eps if e['pattern'] == 'suggest-then-abandon']
    print('  "suggest-then-abandon" episodes:', len(sta), '| press results:',
          dict(Counter(tuple(p['result'] for p in e['presses']) for e in sta)),
          '| v1.12+:', len([e for e in sta if e['vrank'] >= V112]),
          '| median press->abandon s:', r3(np.median([e['closed'] - e['presses'][-1]['at'] for e in sta])))
    for coh, lo in (('all', 0), ('v112', V112)):
        es = [e for e in eps if e['vrank'] >= lo and e['outcome'] == 'abandoned']
        print(f'  abandoned, {coh}: orig abandon-busy pattern', sum(e['pattern'] == 'abandon-busy' for e in es),
              '| corrected (idle-unfixable, fixable with busy drones at failure):',
              sum((not e['fixIdleLogged']) and e['fixAll'] for e in es),
              '| corrected & Suggest pressed:', sum((not e['fixIdleLogged']) and e['fixAll'] and e['suggest'] > 0 for e in es),
              '| abandon-untried (fixable idle):', sum(e['pattern'] == 'abandon-untried' for e in es))
    # first-press-only view: what does the operator do after Suggest fails the FIRST time in an episode?
    fp = [e['presses'][0] for e in eps if e['presses']]
    print('  first press per episode:', dict(Counter(p['result'] for p in fp)))
    for res in ('failed', 'partial'):
        ps = [p for p in fp if p['result'] == res]
        print(f'    first press {res}: next', dict(Counter(p['next'] for p in ps)), 'outcome', dict(Counter(p['outcome'] for p in ps)),
              '| fixable w/ busy:', sum(p['fixableWithBusy'] for p in ps))
    # pattern table, all 33 vs v1.12+
    print('  episode patterns all 33:', dict(Counter(e['pattern'] for e in eps)))
    print('  episode patterns v1.12+:', dict(Counter(e['pattern'] for e in eps if e['vrank'] >= V112)))
    # 'abandon-busy' episodes recomputed with the corrected fixability
    ab = [e for e in eps if e['outcome'] == 'abandoned']
    print('  abandoned episodes by fixability (idleLogged, all):', dict(Counter((e['fixIdleLogged'], e['fixAll']) for e in ab)),
          '| of which Suggest pressed:', dict(Counter((e['fixIdleLogged'], e['fixAll'], e['suggest'] > 0) for e in ab)))

    # --- 5. exposure --------------------------------------------------------------------------
    print('\n## Exposure to a failed Suggest (blind-spot press)')
    ex = exposure(eps, decisions, trust, presses)
    for k, v in ex.items():
        print(f'  {k}:', v)
    v112_eps = [e for e in eps if e['vrank'] >= V112]
    v112_pids = {e['pid'] for e in v112_eps}
    ex2 = exposure(v112_eps, [d for d in decisions if d['pid'] in v112_pids],
                   trust[trust.vrank >= V112], [p for p in presses if p['vrank'] >= V112])
    v15_eps = [e for e in eps if e['vrank'] >= V15]
    v15_pids = {e['pid'] for e in v15_eps}
    ex3 = exposure(v15_eps, [d for d in decisions if d['pid'] in v15_pids],
                   trust[trust.vrank >= V15], [p for p in presses if p['vrank'] >= V15])
    print('  -- v1.5+ only (current Suggest pool; drops P01-P03) --')
    for k in ('nExposed', 'exposedPeople', 'pressesPerPerson', 'laterUse', 'tacticalKeep', 'trustSession', 'trustChange', 'trustPerson'):
        print(f'  {k}:', ex3[k])
    print('  -- v1.12+ only --')
    for k in ('nExposed', 'laterUse', 'tacticalKeep', 'trustSession', 'trustChange', 'trustPerson'):
        print(f'  {k}:', ex2[k])


if __name__ == '__main__':
    main()
