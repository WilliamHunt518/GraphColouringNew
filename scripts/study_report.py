#!/usr/bin/env python3
"""
SAR study report generator.

Reads one or more FULL study exports (the JSON that GameShell's "Download Data" writes:
{participantId, condition, complexities, seed, epsilon*, sessionScores, sessions:[[events]]}),
aggregates them across participants, and writes a single self-contained HTML report with the
figures embedded. Nothing in the output is hand-written: every number, caption figure and verdict
sentence is computed from the logs.

This is the counterpart to scripts/pilot_report.py, which reads the older *mid-session snapshot*
files (they carry a `liveSession` block and one partial session) and is kept for those.

Figures map to the research questions in docs/EVENT_LOGGING.md:
  RQ1 performance · RQ2 selective use · RQ3 deferral by tier x complexity · RQ4 failures/override
plus a scenario-calibration section, which asks whether the two scenarios are equally hard once
the reward available in each is taken into account.

Usage:
  python scripts/study_report.py                          # defaults to logs/Pilots/auto
  python scripts/study_report.py logs/Study_1 --out r.html
"""
import json, sys, base64, argparse, statistics as st
from pathlib import Path
from collections import defaultdict

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BASE = Path(__file__).resolve().parent.parent

# ── palette (dataviz reference instance; validated with its validate_palette.js) ──────────────
S1, S2, S3 = '#2a78d6', '#eb6834', '#1baf7a'        # categorical slots 1-3
GOOD, WARN, CRIT = '#0ca30c', '#fab219', '#d03b3b'  # fixed status palette
SURFACE, INK, INK_2, INK_MUTED, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#8a8981', '#e6e5e1'
SCEN_LABEL = {'strategic': 'Strategic Heavy', 'tactical': 'Tactical Heavy',
              'balanced': 'Balanced', 'full': 'Full Spectrum', 'quick': 'Quick Test'}

plt.rcParams.update({
    'font.family': 'DejaVu Sans', 'font.size': 9,
    'figure.facecolor': SURFACE, 'axes.facecolor': SURFACE,
    'axes.edgecolor': GRID, 'axes.labelcolor': INK_2,
    'axes.spines.top': False, 'axes.spines.right': False,
    'xtick.color': INK_2, 'ytick.color': INK_2,
    'xtick.labelcolor': INK_2, 'ytick.labelcolor': INK_2,
    'axes.titlesize': 10, 'axes.titlecolor': INK, 'axes.titleweight': 'bold',
    'axes.titlelocation': 'left', 'axes.titlepad': 10,
    'grid.color': GRID, 'grid.linewidth': 0.8,
    'legend.frameon': False, 'legend.fontsize': 8, 'legend.labelcolor': INK_2,
    'figure.dpi': 160,
})

# two-sided t critical values at 95%, df 1..30 (avoids a scipy dependency)
_T95 = {1: 12.71, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306,
        9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
        16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086, 21: 2.080, 22: 2.074,
        23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}

def tcrit(df):
    if df <= 0: return float('nan')
    return _T95.get(df, 1.96)

def mean_ci(xs):
    """Mean and half-width of the 95% CI. Half-width is 0 for n<2."""
    xs = [x for x in xs if x is not None]
    if not xs: return (float('nan'), 0.0, 0)
    m = st.mean(xs)
    if len(xs) < 2: return (m, 0.0, len(xs))
    sd = st.stdev(xs)
    return (m, tcrit(len(xs) - 1) * sd / (len(xs) ** 0.5), len(xs))

def paired(a, b):
    """Paired difference b-a with a 95% CI. Participants supply both scenarios."""
    d = [y - x for x, y in zip(a, b)]
    m, hw, n = mean_ci(d)
    return {'diff': m, 'ci': hw, 'n': n, 'overlaps_zero': (m - hw) <= 0 <= (m + hw)}

# ── event helpers ─────────────────────────────────────────────────────────────────────────────
def by(ev, t): return [e for e in ev if e['type'] == t]

def session_metrics(ev):
    """Everything the report needs from a single session's event list."""
    o = {}
    ss, se = by(ev, 'session_start')[0], by(ev, 'session_ended')[0]
    o['duration'] = se['elapsed']
    o['score'], o['points'], o['penalty'] = se['score'], se['completionPoints'], se['penaltyAccrued']
    o['epsS'], o['epsT'] = ss['epsilonStrategic'], ss['epsilonTactical']
    o['lambda'], o['fleet'] = ss['arrivalLambda'], ss['fleet']

    arrived = by(ev, 'mission_arrived')
    o['missions_arrived'] = len(arrived)
    o['reward_available'] = sum(e['maxReward'] for e in arrived)
    # Cost of delay per point at stake: a mission's penalty rate divided by the reward it offers.
    # This is the exchange rate between time and score, and it is what makes two scenarios with
    # equal achievability still produce different final scores.
    o['delay_cost'] = st.mean([e['penaltyRate'] / e['maxReward'] for e in arrived]) if arrived else 0.0
    o['mean_penalty_rate'] = st.mean([e['penaltyRate'] for e in arrived]) if arrived else 0.0
    o['mean_max_reward'] = st.mean([e['maxReward'] for e in arrived]) if arrived else 0.0
    o['tasks_per_mission'] = st.mean([len(e['tasks']) for e in arrived]) if arrived else 0.0
    o['tasks_arrived'] = sum(len(e['tasks']) for e in arrived)
    o['tasks_completed'] = len(by(ev, 'task_completed'))
    o['tasks_failed'] = len(by(ev, 'task_failed'))

    mc = by(ev, 'mission_completed')
    o['outcomes'] = {'all_completed': 0, 'partial': 0, 'none_completed': 0}
    for e in mc: o['outcomes'][e['outcome']] += 1
    o['missions_finished'] = len(mc)
    o['abandoned'] = len(by(ev, 'mission_abandoned'))
    o['unresolved'] = len(se['inFlightMissionIds'])
    o['never_allocated'] = len({e['missionId'] for e in arrived} - {e['missionId'] for e in by(ev, 'strategic_choice')})

    # Normalised difficulty measures — the only fair way to compare scenarios whose missions carry
    # different reward. Capture = share of the reward that actually arrived which was banked.
    o['reward_capture'] = o['points'] / o['reward_available'] if o['reward_available'] else 0.0
    o['penalty_ratio'] = o['penalty'] / o['reward_available'] if o['reward_available'] else 0.0
    o['score_ratio'] = o['score'] / o['reward_available'] if o['reward_available'] else 0.0
    o['task_rate'] = o['tasks_completed'] / o['tasks_arrived'] if o['tasks_arrived'] else 0.0
    o['mission_rate'] = o['missions_finished'] / o['missions_arrived'] if o['missions_arrived'] else 0.0

    # RQ2 — strategic tier
    shown = {}
    for e in by(ev, 'strategic_modal_opened'): shown[e['missionId']] = e['strategiesPresented']
    ch = by(ev, 'strategic_choice')
    o['choices'] = len(ch)
    o['choice_mix'] = {k: sum(1 for e in ch if e['choiceType'] == k)
                       for k in ('aggressive', 'conservative', 'manual')}
    o['agent_follow'] = (sum(1 for e in ch if e['wasAgentSuggestion']) / len(ch)) if ch else 0.0
    o['dismissals'] = len(by(ev, 'strategic_dismissed'))
    o['previews'] = len(by(ev, 'strategic_card_previewed'))
    o['manual_edits'] = len(by(ev, 'manual_allocation_edited'))
    o['bad_cards_shown'] = sum(1 for cards in shown.values() for c in cards if c['isBadSuggestion'])

    # RQ2 — tactical tier
    tc = by(ev, 'tactical_confirmed')
    o['tac_plans'] = len(tc)
    o['tac_consulted'] = sum(1 for e in tc if e['suggestUsedCount'] > 0)
    o['tac_modified'] = sum(1 for e in tc if e['modifiedFromAgentPlan'])
    o['tac_stranded'] = sum(len(e['unassignedTaskIds']) for e in tc)
    o['tac_errors_injected'] = sum(1 for e in by(ev, 'tactical_opened') if e.get('hasTacticalError'))
    o['override_delta'] = [e['finalProjectedCompletion'] - e['agentProjectedCompletion']
                           for e in tc if e['agentProjectedCompletion'] > 0]

    # RQ3 — deliberation, net of the forced card reveal
    o['strat_delib'] = [(e['latencyMs'] - e['deployEnabledAtMs']) / 1000 for e in ch]
    o['strat_gate'] = [e['deployEnabledAtMs'] / 1000 for e in ch if e['choiceType'] != 'manual']
    o['tac_latency'] = [e['latencyMs'] / 1000 for e in tc]
    o['delib_by_cat'] = defaultdict(list)
    for e in ch:
        o['delib_by_cat'][e['missionCategory']].append((e['latencyMs'] - e['deployEnabledAtMs']) / 1000)
    o['time_to_allocate'] = [e['timeToAllocate'] for e in mc if e.get('timeToAllocate') is not None]

    # RQ4 — the failure loop
    o['failures'] = len(by(ev, 'drone_failure'))
    ro, fr = by(ev, 'recovery_opened'), by(ev, 'failure_recovery')
    o['rec_opened'], o['rec_resolved'] = len(ro), len(fr)
    o['rec_feasible'] = sum(1 for e in ro if e['feasibleWithOnMissionDrones'])
    o['rec_latency'] = [e['latencyMs'] / 1000 for e in fr if e['latencyMs'] > 0]
    o['lockouts'] = len(by(ev, 'lockout_detected'))

    o['fail_reasons'] = defaultdict(int)
    for e in by(ev, 'task_failed'): o['fail_reasons'][e['reason']] += 1

    # snapshot time series
    snaps = by(ev, 'state_snapshot')
    o['snapshots'] = len(snaps)
    o['t'] = [s['elapsed'] for s in snaps]
    o['active'] = [sum(1 for m in s['missions'] if m['status'] == 'active') for s in snaps]
    o['queued'] = [sum(1 for m in s['missions'] if m['status'] == 'queued') for s in snaps]
    o['reserve'] = [sum(1 for a in s['assets'] if a['status'] == 'available') for s in snaps]

    o['surveys'] = {e['surveyName']: e['responses'] for e in by(ev, 'survey_response')}
    return o

# ── load cohort ───────────────────────────────────────────────────────────────────────────────
def load(paths):
    """Returns (participants, scenarios) where scenarios maps complexity -> [session metrics]."""
    parts, scen = [], defaultdict(list)
    for p in sorted(paths):
        d = json.load(open(p))
        rec = {'pid': d['participantId'], 'seed': d['seed'], 'condition': d.get('condition'),
               'epsS': d.get('epsilonStrategic'), 'epsT': d.get('epsilonTactical'),
               'file': Path(p).name, 'sessions': []}
        for i, ev in enumerate(d['sessions']):
            if not ev or not by(ev, 'session_ended'):
                continue
            m = session_metrics(ev)
            m['scenario'] = d.get('complexities', [])[i] if i < len(d.get('complexities', [])) else f'session{i+1}'
            m['pid'] = rec['pid']
            rec['sessions'].append(m)
            scen[m['scenario']].append(m)
        parts.append(rec)
    return parts, scen

# ── figures ───────────────────────────────────────────────────────────────────────────────────
FIGS = {}

def save(fig, name):
    fig.tight_layout()
    from io import BytesIO
    buf = BytesIO()
    fig.savefig(buf, format='png', facecolor=SURFACE, bbox_inches='tight')
    plt.close(fig)
    FIGS[name] = base64.b64encode(buf.getvalue()).decode()

def ygrid(ax):
    ax.yaxis.grid(True); ax.set_axisbelow(True); ax.xaxis.grid(False)

def xgrid(ax):
    ax.xaxis.grid(True); ax.set_axisbelow(True); ax.yaxis.grid(False)

def barlabel(ax, bars, fmt='{:.0f}', dy=0):
    for b in bars:
        h = b.get_height()
        ax.text(b.get_x() + b.get_width()/2, h + dy, fmt.format(h),
                ha='center', va='bottom', fontsize=8, color=INK_2)

def paired_panel(ax, names, series, cols, title, ylabel, pct=False, fmt='{:.0f}'):
    """One dot per participant per scenario, joined within participant, with mean+CI."""
    X = np.arange(len(names))
    n = max(len(s) for s in series)
    for i in range(n):
        ys = [s[i] for s in series if i < len(s)]
        if len(ys) == len(series):
            ax.plot(X, ys, '-', color=INK_MUTED, lw=0.8, alpha=0.5, zorder=2)
    for k, (s, c) in enumerate(zip(series, cols)):
        jit = np.linspace(-0.06, 0.06, len(s))
        ax.plot(np.full(len(s), X[k]) + jit, s, 'o', ms=6, color=c, mec=SURFACE, mew=1.2, zorder=3)
        m, hw, _ = mean_ci(s)
        ax.errorbar(X[k] + 0.22, m, yerr=hw, fmt='s', ms=7, color=c, mec=SURFACE, mew=1.2,
                    ecolor=c, elinewidth=2, capsize=4, zorder=4)
        ax.text(X[k] + 0.30, m, fmt.format(m * (100 if pct else 1)), fontsize=8.5,
                color=INK, va='center', fontweight='bold')
    ax.set_xticks(X); ax.set_xticklabels(names, fontsize=8.5)
    ax.set_xlim(-0.45, len(names) - 0.35)
    ax.set_ylabel(ylabel); ax.set_title(title, fontsize=9)
    ygrid(ax)

def build_figures(scen, order):
    names = [SCEN_LABEL.get(s, s) for s in order]
    cols = [S1, S2, S3][:len(order)]
    X = np.arange(len(order))
    W = 0.34
    get = lambda s, k: [m[k] for m in scen[s]]

    # FIG calibration — the normalised difficulty comparison
    fig, axes = plt.subplots(1, 3, figsize=(9.6, 3.2))
    paired_panel(axes[0], names, [get(s, 'reward_capture') for s in order], cols,
                 'Reward captured', 'Points banked ÷ points available', pct=True, fmt='{:.0f}%')
    axes[0].set_ylim(0, 1.05)
    paired_panel(axes[1], names, [get(s, 'task_rate') for s in order], cols,
                 'Tasks completed', 'Completed ÷ arrived', pct=True, fmt='{:.0f}%')
    axes[1].set_ylim(0, 1.05)
    paired_panel(axes[2], names, [get(s, 'penalty_ratio') for s in order], cols,
                 'Penalty burden', 'Penalty ÷ points available', pct=True, fmt='{:.0f}%')
    axes[2].set_ylim(0, None)
    fig.suptitle('Scenario calibration — normalised for the reward each scenario actually offers',
                 x=0.005, ha='left', fontsize=10.5, fontweight='bold', color=INK)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    save(fig, 'calibration')

    # FIG raw score composition
    fig, ax = plt.subplots(figsize=(6.6, 3.0))
    for k, (s, c) in enumerate(zip(order, cols)):
        for j, key in enumerate(['points', 'penalty', 'score']):
            m, hw, _ = mean_ci(get(s, key))
            v = -m if key == 'penalty' else m
            e = ax.bar(j + (k - 0.5) * W, v, W, color=[S3, CRIT, S1][j], zorder=3,
                       alpha=1.0 if k == 0 else 0.72,
                       label=names[k] if j == 0 else None,
                       hatch=None if k == 0 else '///', edgecolor=SURFACE, linewidth=1.5)
            ax.errorbar(j + (k - 0.5) * W, v, yerr=hw, fmt='none', ecolor=INK_2, elinewidth=1.3, capsize=3, zorder=4)
            ax.text(j + (k - 0.5) * W, v + (14 if v >= 0 else -14), f'{m:.0f}',
                    ha='center', va='bottom' if v >= 0 else 'top', fontsize=8, color=INK_2)
    ax.axhline(0, color=INK_MUTED, lw=1)
    ax.set_xticks(range(3)); ax.set_xticklabels(['Points earned', 'Penalty accrued', 'Final score'])
    ax.set_ylabel('Points (mean ± 95% CI)')
    ax.set_title('RQ1 · Raw score composition — solid = first scenario, hatched = second', pad=24)
    ax.legend(loc='lower center', bbox_to_anchor=(0.5, 1.0), ncols=2, borderaxespad=0)
    ygrid(ax)
    save(fig, 'rq1_score')

    # FIG mission outcomes
    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    segs = [('all_completed', 'All tasks done', GOOD, None, '#ffffff'),
            ('partial', 'Partial', WARN, None, '#3a2c00'),
            ('none_completed', 'Nothing done', CRIT, None, '#ffffff'),
            ('abandoned', 'Abandoned', SURFACE, '//', INK_2),
            ('unresolved', 'Unresolved at buzzer', SURFACE, '..', INK_2)]
    tot = max(sum(np.mean([m['outcomes'][k] if k in m['outcomes'] else m[k] for m in scen[s]])
                  for k, *_ in segs) for s in order)
    left = np.zeros(len(order))
    for key, lab, col, hatch, txt in segs:
        v = np.array([np.mean([m['outcomes'][key] if key in m['outcomes'] else m[key] for m in scen[s]])
                      for s in order])
        ax.barh(X, v, 0.46, left=left, label=lab, color=col, zorder=3,
                edgecolor=INK_MUTED if hatch else SURFACE, hatch=hatch, linewidth=1.2 if hatch else 2)
        for i, (val, l0) in enumerate(zip(v, left)):
            if val > 0 and val / tot > 0.07:
                ax.text(l0 + val/2, i, f'{val:.1f}', ha='center', va='center',
                        fontsize=8, color=txt, fontweight='bold')
        left += v
    ax.set_yticks(X); ax.set_yticklabels(names, fontsize=8.5); ax.invert_yaxis()
    ax.set_ylim(len(order) - 0.45, -0.55)
    ax.set_xlabel('Missions per session (mean)'); ax.set_xlim(0, tot * 1.02)
    ax.set_title('RQ1 · What happened to every mission that arrived', pad=24)
    ax.legend(loc='lower center', bbox_to_anchor=(0.5, 1.0), ncols=5, fontsize=7, borderaxespad=0)
    xgrid(ax)
    save(fig, 'rq1_outcomes')

    # FIG RQ2 — reliance
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.0, 3.0))
    kinds = [('aggressive', 'Aggressive', S1), ('conservative', 'Conservative', S3), ('manual', 'Manual', S2)]
    bottom = np.zeros(len(order))
    for k, lab, col in kinds:
        v = np.array([np.mean([m['choice_mix'][k] for m in scen[s]]) for s in order])
        ax1.bar(X, v, 0.45, bottom=bottom, label=lab, color=col, zorder=3, edgecolor=SURFACE, linewidth=2)
        for i, (val, b0) in enumerate(zip(v, bottom)):
            if val > 0.4:
                ax1.text(i, b0 + val/2, f'{val:.1f}', ha='center', va='center',
                         fontsize=8, color='#ffffff', fontweight='bold')
        bottom += v
    ax1.set_xticks(X); ax1.set_xticklabels(names, fontsize=8); ax1.set_ylabel('Allocations per session')
    ax1.set_ylim(0, bottom.max() * 1.18)
    ax1.set_title('RQ2 · Strategic choice mix', pad=24)
    ax1.legend(loc='lower center', bbox_to_anchor=(0.5, 1.0), ncols=3, fontsize=7, borderaxespad=0)
    ygrid(ax1)

    for k, (s, c) in enumerate(zip(order, cols)):
        vals = [np.mean([m['tac_plans'] for m in scen[s]]),
                np.mean([m['tac_consulted'] for m in scen[s]]),
                np.mean([m['tac_modified'] for m in scen[s]])]
        bars = ax2.bar(np.arange(3) + (k - 0.5) * W, vals, W, color=c, zorder=3, label=names[k])
        barlabel(ax2, bars, '{:.1f}', dy=0.05)
    ax2.set_xticks(range(3))
    ax2.set_xticklabels(['Plans\nconfirmed', 'Agent\nconsulted', 'Agent plan\nmodified'], fontsize=8)
    ax2.set_ylabel('Per session'); ax2.set_title('RQ2 · Tactical tier', pad=24)
    ax2.legend(loc='lower center', bbox_to_anchor=(0.5, 1.0), ncols=2, fontsize=7, borderaxespad=0)
    ygrid(ax2)
    save(fig, 'rq2')

    # FIG RQ3 — deliberation
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.0, 3.0))
    data = [[v for m in scen[s] for v in m['strat_delib']] for s in order] + \
           [[v for m in scen[s] for v in m['tac_latency']] for s in order]
    labels = [f'{n}\nstrategic' for n in names] + [f'{n}\ntactical' for n in names]
    bcols = [S1] * len(order) + [S2] * len(order)
    bp = ax1.boxplot(data, patch_artist=True, widths=0.5, medianprops=dict(color=INK, lw=1.6),
                     flierprops=dict(marker='o', ms=3, mfc=INK_MUTED, mec='none', alpha=0.5))
    for patch, c in zip(bp['boxes'], bcols):
        patch.set_facecolor(c); patch.set_alpha(0.85); patch.set_edgecolor(SURFACE); patch.set_linewidth(2)
    for w in bp['whiskers'] + bp['caps']: w.set_color(INK_MUTED)
    ax1.set_xticklabels(labels, fontsize=7.5); ax1.set_ylabel('Seconds')
    ax1.set_title('RQ3 · Decision time by tier\n(strategic is net of the forced card wait)', fontsize=9)
    ax1.legend(handles=[plt.Line2D([], [], marker='s', ls='none', ms=7, color=S1, label='Strategic tier'),
                        plt.Line2D([], [], marker='s', ls='none', ms=7, color=S2, label='Tactical tier')],
               loc='upper right', fontsize=7)
    ygrid(ax1)

    cats = ['A', 'B', 'C', 'D', 'E']
    for k, (s, c) in enumerate(zip(order, cols)):
        off = (k - (len(order) - 1) / 2) * 0.2
        drew = False
        for i, cat in enumerate(cats):
            vals = [v for m in scen[s] for v in m['delib_by_cat'].get(cat, [])]
            if not vals: continue
            jit = np.linspace(-0.055, 0.055, len(vals))
            ax2.plot(np.full(len(vals), i + off) + jit, vals, 'o', ms=3.6, color=c,
                     alpha=0.55, mec='none', zorder=3, label=names[k] if not drew else None)
            drew = True
            ax2.plot([i + off - 0.1, i + off + 0.1], [np.mean(vals)] * 2, '-', lw=2.6, color=c, zorder=4)
    ax2.set_xticks(range(len(cats))); ax2.set_xticklabels(cats)
    ax2.set_xlabel('Mission category (A smallest → E largest)')
    ax2.set_ylabel('Deliberation (s)')
    ax2.set_title('RQ3 · Strategic deliberation vs mission size\n(one dot per allocation; bar = mean)', fontsize=9)
    ax2.legend(loc='upper left', fontsize=7); ygrid(ax2)
    save(fig, 'rq3')

    # FIG RQ4 — failure loop + override quality
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.0, 3.0))
    stages = ['Drone\nfailures', 'Recovery\nraised', 'Fixable from\non-mission', 'Recovery\nresolved']
    keys = ['failures', 'rec_opened', 'rec_feasible', 'rec_resolved']
    for k, (s, c) in enumerate(zip(order, cols)):
        vals = [np.mean([m[key] for m in scen[s]]) for key in keys]
        bars = ax1.bar(np.arange(4) + (k - 0.5) * W, vals, W, label=names[k], color=c, zorder=3)
        barlabel(ax1, bars, '{:.1f}', dy=0.05)
    ax1.set_xticks(range(4)); ax1.set_xticklabels(stages, fontsize=7.5)
    ax1.set_ylabel('Per session'); ax1.set_title('RQ4 · Failure → recovery funnel', fontsize=9)
    ax1.legend(loc='upper right', fontsize=7); ygrid(ax1)

    for k, (s, c) in enumerate(zip(order, cols)):
        y = len(order) - 1 - k
        vals = [v for m in scen[s] for v in m['override_delta']]
        if vals:
            ax2.plot(vals, np.full(len(vals), y) + np.linspace(-0.12, 0.12, len(vals)), 'o',
                     ms=4.5, color=c, mec=SURFACE, mew=0.8, alpha=0.75, zorder=3)
            ax2.plot([np.mean(vals)] * 2, [y - 0.22, y + 0.22], '-', lw=2.6, color=c, zorder=4)
    ax2.axvline(0, color=INK, lw=1.2, zorder=2)
    ax2.set_yticks(range(len(order))); ax2.set_yticklabels(list(reversed(names)), fontsize=8)
    ax2.set_ylim(-0.6, len(order) - 0.4)
    ax2.set_xlabel('Committed plan − agent projection (s)\n← operator faster | agent faster →', fontsize=8)
    ax2.set_title('RQ4 · Override quality\n(one dot per plan; bar = mean)', fontsize=9)
    xgrid(ax2)
    save(fig, 'rq4')

    # FIG timeline — mean across participants with a spread band
    fig, axes = plt.subplots(2, 1, figsize=(8.4, 4.4), sharex=True)
    for s, c, n in zip(order, cols, names):
        T = min(len(m['t']) for m in scen[s])
        t = scen[s][0]['t'][:T]
        for ax, key, ls in ((axes[0], 'active', '-'), (axes[0], 'queued', '--'), (axes[1], 'reserve', '-')):
            arr = np.array([m[key][:T] for m in scen[s]], dtype=float)
            mu, sd = arr.mean(axis=0), arr.std(axis=0)
            ax.plot(t, mu, ls, lw=2 if ls == '-' else 1.6, color=c, alpha=1 if ls == '-' else 0.85,
                    label=f'{n} — {key}' if ax is axes[0] else n)
            if ls == '-':
                ax.fill_between(t, mu - sd, mu + sd, color=c, alpha=0.13, lw=0)
    axes[0].set_ylabel('Missions'); axes[0].legend(loc='upper left', ncols=2, fontsize=7)
    axes[0].set_title('Operator load over the session, from state_snapshot (mean ± 1 SD)', fontsize=9)
    axes[1].set_ylabel('Drones in reserve'); axes[1].set_xlabel('Session time (s)')
    axes[1].legend(loc='lower left', ncols=2, fontsize=7)
    for a in axes: ygrid(a)
    save(fig, 'timeline')

    # FIG failure reasons + trust
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.0, 3.0))
    reasons = sorted({r for s in order for m in scen[s] for r in m['fail_reasons']})
    for k, (s, c) in enumerate(zip(order, cols)):
        vals = [np.mean([m['fail_reasons'].get(r, 0) for m in scen[s]]) for r in reasons]
        bars = ax1.bar(np.arange(len(reasons)) + (k - 0.5) * W, vals, W, label=names[k], color=c, zorder=3)
        barlabel(ax1, bars, '{:.1f}', dy=0.08)
    ax1.set_xticks(range(len(reasons)))
    ax1.set_xticklabels([r.replace('_', '\n') for r in reasons], fontsize=7)
    ax1.set_ylabel('Tasks per session'); ax1.set_title('Why tasks failed', fontsize=9)
    mx = max((np.mean([m['fail_reasons'].get(r, 0) for m in scen[s]]) for s in order for r in reasons), default=1)
    ax1.set_ylim(0, mx * 1.3)
    ax1.legend(loc='upper left', fontsize=7); ygrid(ax1)

    tiers = [('trust_strategic', 'Strategic'), ('trust_tactical', 'Tactical')]
    for k, (s, c) in enumerate(zip(order, cols)):
        means, errs = [], []
        for key, _ in tiers:
            per = [float(np.mean(list(m['surveys'][key].values()))) for m in scen[s] if key in m['surveys']]
            mu, hw, _ = mean_ci(per)
            means.append(mu if mu == mu else 0); errs.append(hw)
        bars = ax2.bar(np.arange(2) + (k - 0.5) * W, means, W, label=names[k], color=c, zorder=3)
        ax2.errorbar(np.arange(2) + (k - 0.5) * W, means, yerr=errs, fmt='none',
                     ecolor=INK_2, elinewidth=1.3, capsize=3, zorder=4)
        barlabel(ax2, bars, '{:.1f}', dy=0.12)
    ax2.set_xticks(range(2)); ax2.set_xticklabels([t[1] for t in tiers])
    ax2.set_ylim(1, 7.8); ax2.set_ylabel('Mean trust (1–7)')
    ax2.set_title('End-of-session trust, by assistant tier', fontsize=9)
    ax2.legend(loc='upper right', fontsize=7); ygrid(ax2)
    save(fig, 'failures_trust')

# ── HTML assembly ─────────────────────────────────────────────────────────────────────────────
def fmt(v, spec='{:.1f}'):
    return '—' if v is None or (isinstance(v, float) and v != v) else spec.format(v)

def pct(v): return fmt(v * 100, '{:.0f}') + '%'

def ci_str(m, hw, spec='{:.0f}'):
    return f'{spec.format(m)} ± {spec.format(hw)}'

def row(label, cells, metric=True):
    tds = ''.join(f'<td>{c}</td>' for c in cells)
    return f'<tr><td class="{"metric" if metric else ""}">{label}</td>{tds}</tr>'

def build_html(parts, scen, order, meta):
    names = [SCEN_LABEL.get(s, s) for s in order]
    get = lambda s, k: [m[k] for m in scen[s]]
    n_part = len(parts)
    n_sess = sum(len(p['sessions']) for p in parts)

    # ── calibration verdict, computed ────────────────────────────────────────
    verdict_rows, verdict_flags = [], []
    if len(order) == 2:
        a, b = order
        for key, label, spec, is_pct in [
            ('reward_capture', 'Reward captured', '{:.1f}', True),
            ('task_rate', 'Tasks completed', '{:.1f}', True),
            ('mission_rate', 'Missions finished', '{:.1f}', True),
            ('penalty_ratio', 'Penalty burden', '{:.1f}', True),
            ('score_ratio', 'Score ÷ reward available', '{:.1f}', True),
        ]:
            va, vb = get(a, key), get(b, key)
            if len(va) != len(vb):
                continue
            r = paired(va, vb)
            ma, _, _ = mean_ci(va)
            mb, _, _ = mean_ci(vb)
            scale = 100 if is_pct else 1
            verdict_rows.append(row(label, [
                f'{fmt(ma*scale, spec)}%' if is_pct else fmt(ma, spec),
                f'{fmt(mb*scale, spec)}%' if is_pct else fmt(mb, spec),
                f'{fmt(r["diff"]*scale, "{:+.1f}")} ± {fmt(r["ci"]*scale, spec)}',
                '<span class="ok">indistinguishable</span>' if r['overlaps_zero']
                else '<span class="differs">differs</span>',
            ]))
            verdict_flags.append(r['overlaps_zero'])
    # If penalty burden is what separates the scenarios, say why: the exchange rate between time
    # and score is set by penaltyRate ÷ maxReward, which is a property of the mission mix, not of
    # how well anyone played.
    mech = ''
    if len(order) == 2:
        da, _, _ = mean_ci(get(order[0], 'delay_cost'))
        db, _, _ = mean_ci(get(order[1], 'delay_cost'))
        if da > 0:
            ra, _, _ = mean_ci(get(order[0], 'mean_penalty_rate'))
            rb, _, _ = mean_ci(get(order[1], 'mean_penalty_rate'))
            wa, _, _ = mean_ci(get(order[0], 'mean_max_reward'))
            wb, _, _ = mean_ci(get(order[1], 'mean_max_reward'))
            mech = (
                f'<p><b>Why:</b> a second of delay costs <b>{db/da:.2f}×</b> more per point at stake in '
                f'{names[1]}. Its missions carry a mean penalty rate of {rb:.3f} pts/s against '
                f'{wb:.0f} points of reward ({db*1000:.2f} per 1000 points per second), versus '
                f'{ra:.3f} pts/s against {wa:.0f} points in {names[0]} ({da*1000:.2f}). '
                f'<code>CATEGORY_PENALTY_RATE</code> rises faster across categories than mission '
                f'reward does, so the larger missions that define {names[1]} are charged more for '
                f'the same elapsed time. Equalising the exchange rate would need the heavier '
                f'categories\' rates scaled by about {da/db:.2f}.</p>')
    n_same = sum(verdict_flags)
    n_tot = len(verdict_flags)
    if n_tot == 0:
        verdict_line = 'Only one scenario present — no calibration comparison to make.'
        verdict_class = ''
    elif n_same == n_tot:
        verdict_line = (f'All {n_tot} normalised measures are statistically indistinguishable between '
                        f'the two scenarios (paired 95% CI spans zero, n={n_part}). On this cohort the '
                        f'scenarios are equally hard once the reward each offers is accounted for.')
        verdict_class = 'ok'
    else:
        diff_names = [r.split('</td>')[0].split('>')[-1] for r, f in zip(verdict_rows, verdict_flags) if not f]
        verdict_line = (f'{n_tot - n_same} of {n_tot} normalised measures differ beyond the paired 95% CI '
                        f'(n={n_part}): {", ".join(diff_names)}. The remaining {n_same} are '
                        f'indistinguishable.')
        verdict_class = 'warn'

    # ── per-scenario summary table ───────────────────────────────────────────
    def agg(s, k, spec='{:.1f}'):
        m, hw, _ = mean_ci(get(s, k))
        return ci_str(m, hw, spec)
    def aggp(s, k):
        m, hw, _ = mean_ci(get(s, k))
        return f'{m*100:.0f}% ± {hw*100:.0f}'
    def flat(s, k, spec='{:.1f}'):
        vals = [v for m in scen[s] for v in m[k]]
        return spec.format(float(np.median(vals))) if vals else '—'

    summary_rows = ''.join([
        row('Missions arrived', [agg(s, 'missions_arrived') for s in order]),
        row('Missions finished', [agg(s, 'missions_finished') for s in order]),
        row('Missions abandoned', [agg(s, 'abandoned') for s in order]),
        row('Unresolved at buzzer', [agg(s, 'unresolved') for s in order]),
        row('Never allocated', [agg(s, 'never_allocated') for s in order]),
        row('Tasks arrived', [agg(s, 'tasks_arrived') for s in order]),
        row('Tasks completed', [agg(s, 'tasks_completed') for s in order]),
        row('Tasks per mission', [agg(s, 'tasks_per_mission') for s in order]),
        row('Mean penalty rate (pts/s)', [agg(s, 'mean_penalty_rate', '{:.3f}') for s in order]),
        row('Delay cost (pts/s per 1000 pts at stake)',
            [ci_str(mean_ci(get(s, 'delay_cost'))[0] * 1000, mean_ci(get(s, 'delay_cost'))[1] * 1000, '{:.2f}') for s in order]),
        row('Points available', [agg(s, 'reward_available', '{:.0f}') for s in order]),
        row('Points earned', [agg(s, 'points', '{:.0f}') for s in order]),
        row('Penalty accrued', [agg(s, 'penalty', '{:.0f}') for s in order]),
        row('Final score', [agg(s, 'score', '{:.0f}') for s in order]),
        row('<b>Reward captured</b>', [aggp(s, 'reward_capture') for s in order]),
        row('<b>Task completion rate</b>', [aggp(s, 'task_rate') for s in order]),
        row('<b>Penalty burden</b>', [aggp(s, 'penalty_ratio') for s in order]),
        row('Drone failures', [agg(s, 'failures') for s in order]),
        row('Recoveries raised / resolved', [f"{agg(s,'rec_opened')} / {agg(s,'rec_resolved')}" for s in order]),
        row('Scheduling lockouts', [agg(s, 'lockouts') for s in order]),
        row('Tasks stranded by a plan', [agg(s, 'tac_stranded') for s in order]),
        row('Strategic allocations', [agg(s, 'choices') for s in order]),
        row('Agent card followed', [aggp(s, 'agent_follow') for s in order]),
        row('Tactical plans confirmed', [agg(s, 'tac_plans') for s in order]),
        row('Median strategic deliberation', [flat(s, 'strat_delib') + ' s' for s in order]),
        row('Median forced card wait', [flat(s, 'strat_gate') + ' s' for s in order]),
        row('Median tactical latency', [flat(s, 'tac_latency') + ' s' for s in order]),
        row('Median recovery response', [flat(s, 'rec_latency') + ' s' for s in order]),
        row('Degraded cards shown', [agg(s, 'bad_cards_shown') for s in order]),
        row('Tactical errors injected', [agg(s, 'tac_errors_injected') for s in order]),
        row('Snapshots per session', [agg(s, 'snapshots', '{:.0f}') for s in order]),
    ])

    part_rows = ''.join(
        row(p['pid'], [f"{s['score']:.0f}" for s in p['sessions']] +
                      [f"{sum(x['score'] for x in p['sessions']):.0f}"], metric=False)
        for p in parts)

    eps = {(p['epsS'], p['epsT']) for p in parts}
    eps_line = (f'ε<sub>S</sub> = {list(eps)[0][0]:g}, ε<sub>T</sub> = {list(eps)[0][1]:g}'
                if len(eps) == 1 else 'mixed across participants')
    perfect = len(eps) == 1 and list(eps)[0] == (0, 0)

    figs_html = lambda k, cap: (
        f'<figure><img src="data:image/png;base64,{FIGS[k]}" alt="{cap}">'
        f'<figcaption>{cap}</figcaption></figure>')

    return f"""<title>SAR Study — Cohort Report</title>
<style>
  :root {{
    color-scheme: light;
    --ground:#f6f8f9; --panel:#ffffff; --ink:#101519; --ink-2:#4c565f; --ink-3:#7b868f;
    --rule:#dde3e8; --rule-soft:#eaeef1; --accent:#1f66bb; --accent-2:#c8501f;
    --ok:#0a7d16; --warn:#8a6100; --crit:#b3272b; --ok-bg:#eef7ef; --warn-bg:#fdf7e8; --plate:#fcfcfb;
    --sans: ui-sans-serif,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
    --serif: Charter,"Bitstream Charter","Iowan Old Style",Georgia,serif;
    --mono: ui-monospace,"SF Mono","Cascadia Mono",Consolas,"Liberation Mono",monospace;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      color-scheme: dark;
      --ground:#12161a; --panel:#181d22; --ink:#e9edf0; --ink-2:#a8b3bc; --ink-3:#7c868e;
      --rule:#2a333b; --rule-soft:#222a31; --accent:#62a3ea; --accent-2:#f0865a;
      --ok:#4cc45a; --warn:#e0ad3c; --crit:#ee6a6a; --ok-bg:#16241a; --warn-bg:#2a2317;
    }}
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --ground:#12161a; --panel:#181d22; --ink:#e9edf0; --ink-2:#a8b3bc; --ink-3:#7c868e;
    --rule:#2a333b; --rule-soft:#222a31; --accent:#62a3ea; --accent-2:#f0865a;
    --ok:#4cc45a; --warn:#e0ad3c; --crit:#ee6a6a; --ok-bg:#16241a; --warn-bg:#2a2317;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--ground); color:var(--ink); font-family:var(--serif);
         font-size:16.5px; line-height:1.62; -webkit-font-smoothing:antialiased; }}
  .wrap {{ max-width:1080px; margin:0 auto; padding:0 28px 96px; }}
  .col {{ max-width:68ch; }}
  header.mast {{ border-bottom:1px solid var(--rule); padding:56px 0 26px; margin-bottom:40px; }}
  .eyebrow {{ font-family:var(--sans); font-size:11px; font-weight:650; letter-spacing:.14em;
              text-transform:uppercase; color:var(--ink-3); margin:0 0 14px; }}
  h1 {{ font-family:var(--sans); font-size:clamp(30px,4.4vw,44px); line-height:1.08; font-weight:700;
        letter-spacing:-.02em; text-wrap:balance; margin:0 0 16px; }}
  .standfirst {{ font-size:18px; color:var(--ink-2); margin:0; max-width:62ch; }}
  .runmeta {{ display:flex; flex-wrap:wrap; gap:0 26px; margin-top:26px; padding-top:20px;
              border-top:1px solid var(--rule-soft); font-family:var(--mono); font-size:12.5px;
              color:var(--ink-2); }}
  .runmeta b {{ color:var(--ink); font-weight:600; }}
  section {{ margin:0 0 52px; }}
  h2 {{ font-family:var(--sans); font-size:13px; font-weight:650; letter-spacing:.12em;
        text-transform:uppercase; color:var(--ink-3); margin:0 0 18px; padding-bottom:10px;
        border-bottom:1px solid var(--rule); }}
  h3 {{ font-family:var(--sans); font-size:19px; font-weight:650; letter-spacing:-.01em;
        margin:34px 0 10px; }}
  p {{ margin:0 0 15px; }}
  code,.mono {{ font-family:var(--mono); font-size:.88em; }}
  code {{ background:var(--rule-soft); padding:1px 5px; border-radius:3px; }}
  figure {{ margin:30px 0 34px; background:var(--plate); border:1px solid var(--rule);
            border-radius:4px; overflow:hidden; }}
  figure img {{ display:block; width:100%; height:auto; }}
  figcaption {{ font-family:var(--sans); font-size:13px; line-height:1.5; color:var(--ink-2);
                padding:13px 16px; border-top:1px solid var(--rule); background:var(--panel); }}
  .tablewrap {{ overflow-x:auto; margin:22px 0 8px; }}
  table {{ border-collapse:collapse; width:100%; font-size:14px; font-family:var(--sans); }}
  th,td {{ text-align:right; padding:9px 12px; border-bottom:1px solid var(--rule-soft);
           font-variant-numeric:tabular-nums; }}
  th:first-child,td:first-child {{ text-align:left; }}
  thead th {{ font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--ink-3);
              font-weight:650; border-bottom:1px solid var(--rule); }}
  tbody tr:last-child td {{ border-bottom:none; }}
  td.metric {{ color:var(--ink-2); }}
  .ok {{ color:var(--ok); font-weight:650; }}
  .differs {{ color:var(--crit); font-weight:650; }}
  .callout {{ border:1px solid var(--rule); border-left:3px solid var(--ink-3); border-radius:3px;
              padding:18px 20px; margin:24px 0; background:var(--panel); }}
  .callout.ok {{ border-left-color:var(--ok); background:var(--ok-bg); }}
  .callout.warn {{ border-left-color:var(--warn); background:var(--warn-bg); }}
  .callout h4 {{ font-family:var(--sans); font-size:15px; font-weight:680; margin:0 0 8px; }}
  .callout p:last-child {{ margin-bottom:0; }}
  footer {{ border-top:1px solid var(--rule); padding-top:20px; margin-top:60px;
            font-family:var(--sans); font-size:13px; color:var(--ink-3); }}
  @media (max-width:620px) {{ .wrap {{ padding:0 18px 60px; }} }}
</style>
<div class="wrap">
<header class="mast">
  <p class="eyebrow">Cohort report · generated from event logs</p>
  <h1>{n_part} participants, {n_sess} sessions, {meta['events']:,} events</h1>
  <p class="standfirst">Every figure and number below is computed from the exported event logs by
  <span class="mono">scripts/study_report.py</span>. Values are mean ± 95% CI across participants
  unless stated otherwise.</p>
  <div class="runmeta">
    <span>participants <b>{n_part}</b></span>
    <span>scenarios <b>{' → '.join(names)}</b></span>
    <span>{eps_line}</span>
    <span>assistants <b>{'perfect' if perfect else 'degraded'}</b></span>
    <span>session <b>{meta['duration']:.0f} s</b></span>
    <span>build <b>{meta['appVersion']}</b></span>
  </div>
</header>

<section class="col">
  <h2>Scenario calibration</h2>
  <p>The two scenarios differ in mission size and arrival rate, so they offer different amounts of
  reward. Comparing raw scores would just measure that. These measures normalise by the reward that
  actually arrived in each session, and are compared <b>within participant</b> — each person played
  both, so the paired difference removes individual skill.</p>
  <div class="callout {verdict_class}">
    <h4>Verdict</h4>
    <p>{verdict_line}</p>
    {mech if verdict_class == 'warn' else ''}
  </div>
  <div class="tablewrap">
    <table>
      <thead><tr><th>Normalised measure</th><th>{names[0]}</th><th>{names[1] if len(names)>1 else ''}</th>
      <th>Paired difference (95% CI)</th><th>Assessment</th></tr></thead>
      <tbody>{''.join(verdict_rows)}</tbody>
    </table>
  </div>
</section>

<section>
  {figs_html('calibration', 'Normalised difficulty, one dot per participant with the pair joined; square marker is the mean with its 95% CI. Equal difficulty means the two columns sit at the same height.')}
</section>

<section>
  <h2>Per-scenario detail</h2>
  <div class="tablewrap">
    <table>
      <thead><tr><th>Measure</th><th>{names[0]}</th><th>{names[1] if len(names)>1 else ''}</th></tr></thead>
      <tbody>{summary_rows}</tbody>
    </table>
  </div>
</section>

<section>
  <h2>RQ1 · Performance</h2>
  {figs_html('rq1_score', 'Raw score composition. Error bars are 95% CIs across participants. Raw points differ between scenarios by construction — the calibration section above is the fair comparison.')}
  {figs_html('rq1_outcomes', 'Mean fate of every mission that arrived, per session.')}
</section>

<section>
  <h2>RQ2 · Use of the assistants</h2>
  {figs_html('rq2', 'Left: how allocations were made. Right: tactical plans confirmed, how often the agent was consulted via Suggest, and how often its plan was altered — consultation and compliance are logged separately because the planner starts empty.')}
</section>

<section>
  <h2>RQ3 · Where the time goes</h2>
  {figs_html('rq3', 'Strategic deliberation is net of the forced card reveal, using deployEnabledAtMs. The right panel plots one dot per allocation rather than a line through category means.')}
</section>

<section>
  <h2>RQ4 · Failures and override quality</h2>
  {figs_html('rq4', 'The failure loop is logged in three parts: the failure, what the operator was shown (recovery_opened, including whether the mission could be fixed from its own drones), and what they did about it.')}
</section>

<section>
  <h2>Session shape and outcomes</h2>
  {figs_html('timeline', 'Reconstructed from state_snapshot events alone — no operator action required. Band is ±1 SD across participants.')}
  {figs_html('failures_trust', 'Task failure causes, and end-of-session trust by assistant tier. Trust and workload are measured only at session end.')}
</section>

<section>
  <h2>Participants</h2>
  <div class="tablewrap">
    <table>
      <thead><tr><th>Participant</th>{''.join(f'<th>{n}</th>' for n in names)}<th>Total</th></tr></thead>
      <tbody>{part_rows}</tbody>
    </table>
  </div>
</section>

<footer>
  Generated by <span class="mono">scripts/study_report.py</span> from {n_part} export(s) in
  <span class="mono">{meta['source']}</span> · build <span class="mono">{meta['appVersion']}</span>
</footer>
</div>
"""

# ── main ──────────────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('inputs', nargs='*', default=[str(BASE / 'logs/Pilots/auto')])
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    paths = []
    for i in (a.inputs or [str(BASE / 'logs/Pilots/auto')]):
        p = Path(i)
        paths.extend(sorted(p.glob('study_*.json')) if p.is_dir() else [p])
    if not paths:
        sys.exit('no study_*.json exports found')

    parts, scen = load(paths)
    order = []
    for p in parts:
        for s in p['sessions']:
            if s['scenario'] not in order: order.append(s['scenario'])
    if not order:
        sys.exit('exports contain no completed sessions')

    src_dir = Path(a.inputs[0]) if a.inputs else (BASE / 'logs/Pilots/auto')
    out = Path(a.out) if a.out else (src_dir if src_dir.is_dir() else src_dir.parent) / 'report.html'

    total_events = sum(len(ev) for p in paths for ev in json.load(open(p))['sessions'])
    app_version = 'unknown'
    for p in paths:
        for ev in json.load(open(p))['sessions']:
            ssv = by(ev, 'session_start')
            if ssv and ssv[0].get('appVersion'): app_version = ssv[0]['appVersion']; break
        break
    meta = {'events': total_events, 'appVersion': app_version,
            'duration': scen[order[0]][0]['duration'], 'source': str(src_dir)}

    print(f'{len(parts)} participant(s), scenarios: {", ".join(order)}, {total_events} events')
    build_figures(scen, order)
    out.write_text(build_html(parts, scen, order, meta), encoding='utf-8')
    print(f'wrote {out}  ({out.stat().st_size/1024:.0f} KB, {len(FIGS)} figures embedded)')

    # machine-readable companion
    summary = {'participants': len(parts), 'scenarios': {}}
    for s in order:
        summary['scenarios'][s] = {
            k: dict(zip(('mean', 'ci95', 'n'), mean_ci([m[k] for m in scen[s]])))
            for k in ('score', 'points', 'penalty', 'reward_capture', 'task_rate',
                      'mission_rate', 'penalty_ratio', 'missions_arrived', 'failures',
                      'abandoned', 'unresolved', 'lockouts', 'tac_stranded')
        }
    (out.parent / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(f'wrote {out.parent / "summary.json"}')

if __name__ == '__main__':
    main()
