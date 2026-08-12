#!/usr/bin/env python3
"""
SAR study-export analysis.

Reads a FULL study export (the JSON that GameShell's "Download Data" produces:
{participantId, condition, complexities, seed, epsilon*, sessionScores, sessions:[[events]]})
and produces one PNG per figure plus a summary JSON.

This is the counterpart to scripts/pilot_report.py, which reads the older *mid-session snapshot*
files (they carry a `liveSession` block and only one partial session). Full exports have neither,
so they need their own reader.

Every figure is tied to a research question from docs/EVENT_LOGGING.md:
  RQ1 performance · RQ2 selective use · RQ3 deferral by tier x complexity · RQ4 failures/override

Run: python scripts/study_report.py [path/to/export.json]
Out: logs/Pilots/auto/figs/*.png  +  summary.json
"""
import json, sys, base64
from pathlib import Path
from collections import defaultdict

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BASE = Path(__file__).resolve().parent.parent
SRC  = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / 'logs/Pilots/auto/study_P-PILOT_LL_4242.json'
OUT  = SRC.parent / 'figs'
OUT.mkdir(parents=True, exist_ok=True)

# ── palette (dataviz reference instance; validated with scripts/validate_palette.js) ──────────
S1, S2, S3 = '#2a78d6', '#eb6834', '#1baf7a'      # categorical slots 1-3
GOOD, WARN, CRIT = '#0ca30c', '#fab219', '#d03b3b'  # fixed status palette
SURFACE   = '#fcfcfb'
INK       = '#0b0b0b'
INK_2     = '#52514e'
INK_MUTED = '#8a8981'
GRID      = '#e6e5e1'

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

def save(fig, name):
    fig.tight_layout()
    p = OUT / f'{name}.png'
    fig.savefig(p, facecolor=SURFACE, bbox_inches='tight')
    plt.close(fig)
    print(f'  wrote {p.relative_to(BASE)}')
    return p

def ygrid(ax):
    ax.yaxis.grid(True); ax.set_axisbelow(True); ax.xaxis.grid(False)

def barlabel(ax, bars, fmt='{:.0f}', dy=0):
    """Direct labels — identity/value is never carried by colour alone."""
    for b in bars:
        h = b.get_height()
        ax.text(b.get_x() + b.get_width()/2, h + dy, fmt.format(h),
                ha='center', va='bottom', fontsize=8, color=INK_2)

# ── load ──────────────────────────────────────────────────────────────────────────────────────
d = json.load(open(SRC))
SESSIONS = d['sessions']
NAMES = [c.capitalize() for c in d.get('complexities', [])] or [f'Session {i+1}' for i in range(len(SESSIONS))]
LABELS = {'strategic': 'Strategic Heavy', 'tactical': 'Tactical Heavy'}
NAMES = [LABELS.get(c, c.capitalize()) for c in d.get('complexities', NAMES)]
COL = [S1, S2, S3][:len(SESSIONS)]

def by(ev, t):
    return [e for e in ev if e['type'] == t]

# ── per-session metric extraction ─────────────────────────────────────────────────────────────
def extract(ev):
    o = {}
    ss = by(ev, 'session_start')[0]
    se = by(ev, 'session_ended')[0]
    o['start'], o['end'] = ss, se
    o['duration'] = se['elapsed']
    o['score'], o['points'], o['penalty'] = se['score'], se['completionPoints'], se['penaltyAccrued']

    # RQ1 — mission outcomes. mission_completed only fires when every task resolved; anything
    # still in flight at the buzzer is counted from session_ended.inFlightMissionIds.
    mc = by(ev, 'mission_completed')
    o['outcomes'] = {'all_completed': 0, 'partial': 0, 'none_completed': 0}
    for e in mc:
        o['outcomes'][e['outcome']] += 1
    o['abandoned'] = len(by(ev, 'mission_abandoned'))
    o['arrived'] = len(by(ev, 'mission_arrived'))
    o['unresolved'] = len(se['inFlightMissionIds'])
    o['mission_completed'] = mc

    # RQ2 — strategic tier. Was the CHOSEN card one the agent had degraded (isBadSuggestion)?
    modals = by(ev, 'strategic_modal_opened')
    shown = {}                     # missionId -> last set of cards shown
    for e in modals:
        shown[e['missionId']] = e['strategiesPresented']
    o['choices'] = by(ev, 'strategic_choice')
    o['dismissed'] = len(by(ev, 'strategic_dismissed'))
    o['previews'] = len(by(ev, 'strategic_card_previewed'))
    o['manual_edits'] = len(by(ev, 'manual_allocation_edited'))
    acc = {'bad': [0, 0], 'good': [0, 0]}   # [accepted, offered]
    for e in o['choices']:
        cards = shown.get(e['missionId'], [])
        if not cards:
            continue
        if e['choiceType'] == 'manual':
            for c in cards:
                acc['bad' if c['isBadSuggestion'] else 'good'][1] += 1
        else:
            picked = 'Aggressive' if e['choiceType'] == 'aggressive' else 'Conservative'
            for c in cards:
                k = 'bad' if c['isBadSuggestion'] else 'good'
                acc[k][1] += 1
                if c['name'] == picked:
                    acc[k][0] += 1
    o['card_acceptance'] = acc

    # RQ2 — tactical tier: consultation (Suggest) is distinct from following.
    tc = by(ev, 'tactical_confirmed')
    o['tactical'] = tc
    o['tac_consulted'] = sum(1 for e in tc if e['suggestUsedCount'] > 0)
    o['tac_modified'] = sum(1 for e in tc if e['modifiedFromAgentPlan'])
    o['tac_total'] = len(tc)
    o['tac_opened'] = by(ev, 'tactical_opened')
    o['tac_error_injected'] = sum(1 for e in o['tac_opened'] if e.get('hasTacticalError'))

    # RQ3 — deliberation, net of the forced card-reveal wait.
    o['strat_delib'] = [(e['latencyMs'] - e['deployEnabledAtMs']) / 1000 for e in o['choices']]
    # Forced wait only applies to agent-card choices — a manual allocation is never gated, so
    # including its 0 would drag the median toward a number nobody actually waited.
    o['strat_gate'] = [e['deployEnabledAtMs'] / 1000 for e in o['choices'] if e['choiceType'] != 'manual']
    o['tac_latency'] = [e['latencyMs'] / 1000 for e in tc]
    o['delib_by_cat'] = defaultdict(list)
    for e in o['choices']:
        o['delib_by_cat'][e['missionCategory']].append((e['latencyMs'] - e['deployEnabledAtMs']) / 1000)

    # RQ4 — the failure loop.
    o['failures'] = by(ev, 'drone_failure')
    o['rec_opened'] = by(ev, 'recovery_opened')
    o['rec_resolved'] = by(ev, 'failure_recovery')
    o['rec_latency'] = [e['latencyMs'] / 1000 for e in o['rec_resolved'] if e['latencyMs'] > 0]
    o['rec_feasible'] = sum(1 for e in o['rec_opened'] if e['feasibleWithOnMissionDrones'])
    # Override quality: committed plan's projected finish vs the agent's own estimate.
    o['override_delta'] = [(e['finalProjectedCompletion'] - e['agentProjectedCompletion'])
                           for e in tc if e['agentProjectedCompletion'] > 0]
    o['stranded'] = sum(len(e['unassignedTaskIds']) for e in tc)

    # Task-level
    o['task_completed'] = by(ev, 'task_completed')
    o['task_failed'] = by(ev, 'task_failed')
    o['fail_reasons'] = defaultdict(int)
    for e in o['task_failed']:
        o['fail_reasons'][e['reason']] += 1

    # Snapshot-derived time series (the whole point of state_snapshot)
    snaps = by(ev, 'state_snapshot')
    o['snaps'] = snaps
    o['t'] = [s['elapsed'] for s in snaps]
    o['active'] = [sum(1 for m in s['missions'] if m['status'] == 'active') for s in snaps]
    o['queued'] = [sum(1 for m in s['missions'] if m['status'] == 'queued') for s in snaps]
    o['reserve'] = [sum(1 for a in s['assets'] if a['status'] == 'available') for s in snaps]
    o['ctx_pen'] = [s['context']['penaltyAccrued'] for s in snaps]
    o['ctx_score'] = [s['context']['score'] for s in snaps]

    # Surveys — trust + workload are measured at session end, per tier.
    o['surveys'] = {e['surveyName']: e['responses'] for e in by(ev, 'survey_response')}
    return o

E = [extract(ev) for ev in SESSIONS]
X = np.arange(len(E))
W = 0.34

print(f'analysing {SRC.name}: {len(SESSIONS)} sessions, {sum(len(s) for s in SESSIONS)} events')

# ── FIG 1 · RQ1 score composition ─────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(6.4, 3.0))
pts = [e['points'] for e in E]; pen = [-e['penalty'] for e in E]; sc = [e['score'] for e in E]
b1 = ax.bar(X - W/2, pts, W, label='Points earned', color=S3, zorder=3)
b2 = ax.bar(X - W/2, pen, W, label='Penalty accrued', color=CRIT, zorder=3)
b3 = ax.bar(X + W/2 + 0.04, sc, W, label='Final score', color=S1, zorder=3)
for bars, fmt in ((b1, '{:.0f}'), (b3, '{:.0f}')):
    barlabel(ax, bars, fmt, dy=6)
for b in b2:
    ax.text(b.get_x() + b.get_width()/2, b.get_height() - 22, f'{b.get_height():.0f}',
            ha='center', va='top', fontsize=8, color=INK_2)
ax.axhline(0, color=INK_MUTED, lw=1)
ax.set_xticks(X); ax.set_xticklabels(NAMES); ax.set_ylabel('Points')
lim = max(max(pts), max(sc), max(abs(p) for p in pen)) * 1.30
ax.set_ylim(-lim, lim)
ax.set_title('RQ1 · Score composition per scenario', pad=26)
ax.legend(loc='lower center', bbox_to_anchor=(0.5, 1.0), ncols=3, borderaxespad=0)
ygrid(ax)
save(fig, 'rq1_score')

# ── FIG 2 · RQ1 mission outcomes ──────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(7.0, 2.5))
total = max(sum([e['outcomes'][k] for k in ('all_completed', 'partial', 'none_completed')])
            + e['abandoned'] + e['unresolved'] for e in E)
segs = [('all_completed', 'All tasks done', GOOD, None, '#ffffff'),
        ('partial', 'Partial', WARN, None, '#3a2c00'),
        ('none_completed', 'Nothing done', CRIT, None, '#ffffff'),
        ('abandoned', 'Abandoned', SURFACE, '//', INK_2),
        ('unresolved', 'Unresolved at buzzer', SURFACE, '..', INK_2)]
left = np.zeros(len(E))
for key, lab, col, hatch, txt in segs:
    v = np.array([e['outcomes'][key] if key in e['outcomes'] else e[key] for e in E], dtype=float)
    ax.barh(X, v, 0.46, left=left, label=lab, color=col, zorder=3,
            edgecolor=INK_MUTED if hatch else SURFACE, hatch=hatch, linewidth=1.2 if hatch else 2)
    for i, (val, l0) in enumerate(zip(v, left)):
        # Only label inside the segment when it is wide enough to hold the text; the legend
        # carries identity, so a cramped segment simply goes unlabelled rather than overflowing.
        if val > 0 and val / total > 0.06:
            ax.text(l0 + val/2, i, f'{int(val)}', ha='center', va='center',
                    fontsize=8, color=txt, fontweight='bold')
    left += v
ax.set_yticks(X); ax.set_yticklabels(NAMES, fontsize=8.5); ax.invert_yaxis()
ax.set_ylim(len(E) - 0.45, -0.55)
ax.set_xlabel('Missions'); ax.set_xlim(0, total * 1.02)
ax.set_title('RQ1 · What happened to every mission that arrived', pad=24)
ax.legend(loc='lower center', bbox_to_anchor=(0.5, 1.0), ncols=5, fontsize=7, borderaxespad=0)
ax.xaxis.grid(True); ax.set_axisbelow(True); ax.yaxis.grid(False)
save(fig, 'rq1_outcomes')

# ── FIG 3 · RQ2 strategic reliance + selective rejection ──────────────────────────────────────
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.6, 3.0))
kinds = [('aggressive', 'Aggressive', S1), ('conservative', 'Conservative', S3), ('manual', 'Manual', S2)]
bottom = np.zeros(len(E))
for k, lab, col in kinds:
    v = np.array([sum(1 for c in e['choices'] if c['choiceType'] == k) for e in E], dtype=float)
    bars = ax1.bar(X, v, 0.45, bottom=bottom, label=lab, color=col, zorder=3,
                   edgecolor=SURFACE, linewidth=2)
    for i, (val, b0) in enumerate(zip(v, bottom)):
        if val > 0:
            ax1.text(i, b0 + val/2, f'{lab[:4]} {int(val)}', ha='center', va='center',
                     fontsize=7.5, color='#ffffff', fontweight='bold')
    bottom += v
ax1.set_xticks(X); ax1.set_xticklabels(NAMES, fontsize=8); ax1.set_ylabel('Allocations')
ax1.set_ylim(0, bottom.max() * 1.16)
ax1.set_title('RQ2 · Strategic choice mix', pad=24)
ax1.legend(loc='lower center', bbox_to_anchor=(0.5, 1.0), ncols=3, fontsize=7, borderaxespad=0)
ygrid(ax1)

# selective rejection: acceptance of degraded vs sound cards
good_rate = [100 * e['card_acceptance']['good'][0] / max(1, e['card_acceptance']['good'][1]) for e in E]
bad_rate  = [100 * e['card_acceptance']['bad'][0]  / max(1, e['card_acceptance']['bad'][1])  for e in E]
bg = ax2.bar(X - W/2, good_rate, W, label='Sound card', color=S1, zorder=3)
bb = ax2.bar(X + W/2, bad_rate, W, label='Degraded card (ε)', color=CRIT, zorder=3)
barlabel(ax2, bg, '{:.0f}%', dy=1.5); barlabel(ax2, bb, '{:.0f}%', dy=1.5)
ax2.set_xticks(X); ax2.set_xticklabels(NAMES, fontsize=8); ax2.set_ylabel('Accepted when offered (%)')
ax2.set_ylim(0, max(100, max(good_rate + bad_rate) * 1.25))
ax2.set_title('RQ2 · Selective rejection of degraded cards')
ax2.legend(loc='upper right', ncols=2, fontsize=7); ygrid(ax2)
save(fig, 'rq2_strategic')

# ── FIG 4 · RQ2 tactical consultation vs follow ───────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(6.4, 3.0))
tot = [e['tac_total'] for e in E]
cons = [e['tac_consulted'] for e in E]
mod = [e['tac_modified'] for e in E]
b1 = ax.bar(X - W, tot, W, label='Plans confirmed', color=INK_MUTED, zorder=3)
b2 = ax.bar(X, cons, W, label='Agent consulted (Suggest)', color=S1, zorder=3)
b3 = ax.bar(X + W, mod, W, label='Agent plan modified', color=S2, zorder=3)
for b in (b1, b2, b3):
    barlabel(ax, b, '{:.0f}', dy=0.08)
ax.set_xticks(X); ax.set_xticklabels(NAMES); ax.set_ylabel('Tactical plans')
ax.set_ylim(0, max(tot + cons + mod) * 1.30)
ax.set_title('RQ2 · Tactical tier — consulting the agent is not the same as following it', pad=26)
ax.legend(loc='lower center', bbox_to_anchor=(0.5, 1.0), ncols=3, borderaxespad=0)
ygrid(ax)
save(fig, 'rq2_tactical')

# ── FIG 5 · RQ3 deliberation by tier ──────────────────────────────────────────────────────────
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.6, 3.0))
data = [e['strat_delib'] for e in E] + [e['tac_latency'] for e in E]
labels = [f'{n}\nstrategic' for n in NAMES] + [f'{n}\ntactical' for n in NAMES]
cols = [S1] * len(E) + [S2] * len(E)
bp = ax1.boxplot(data, patch_artist=True, widths=0.5, medianprops=dict(color=INK, lw=1.6),
                 flierprops=dict(marker='o', ms=3, mfc=INK_MUTED, mec='none', alpha=0.6))
for patch, c in zip(bp['boxes'], cols):
    patch.set_facecolor(c); patch.set_alpha(0.85); patch.set_edgecolor(SURFACE); patch.set_linewidth(2)
for w in bp['whiskers'] + bp['caps']:
    w.set_color(INK_MUTED)
ax1.set_xticklabels(labels, fontsize=7.5)
ax1.set_ylabel('Deliberation (s)')
ax1.set_title('RQ3 · Decision time by tier\n(strategic is net of the forced card wait)', fontsize=9)
ax1.legend(handles=[plt.Line2D([], [], marker='s', ls='none', ms=7, color=S1, label='Strategic tier'),
                    plt.Line2D([], [], marker='s', ls='none', ms=7, color=S2, label='Tactical tier')],
           loc='upper right', fontsize=7)
ygrid(ax1)

# Deliberation vs mission size. One dot per decision — with a handful of allocations per category
# a line through category means would invent a trend that isn't in the data.
order = ['A', 'B', 'C', 'D', 'E']
for k, (e, n, c) in enumerate(zip(E, NAMES, COL)):
    off = (k - (len(E) - 1) / 2) * 0.18
    drew = False
    for i, cat in enumerate(order):
        vals = e['delib_by_cat'].get(cat, [])
        if not vals:
            continue
        jit = np.linspace(-0.045, 0.045, len(vals))
        ax2.plot(np.full(len(vals), i + off) + jit, vals, 'o', ms=5.5, color=c,
                 mec=SURFACE, mew=1.2, zorder=3, label=n if not drew else None)
        drew = True
        ax2.plot([i + off - 0.09, i + off + 0.09], [np.mean(vals)] * 2, '-', lw=2.4, color=c, zorder=4)
        ax2.text(i + off, max(vals) + 0.35, f'n={len(vals)}', ha='center', fontsize=6.5, color=INK_MUTED)
ax2.set_xticks(range(len(order)))
ax2.set_xticklabels(order)
ax2.set_xlabel('Mission category (A smallest → E largest)')
ax2.set_ylabel('Deliberation (s)')
ax2.set_title('RQ3 · Strategic deliberation vs mission size\n(one dot per allocation; bar = mean)', fontsize=9)
_all = [v for e in E for vs in e['delib_by_cat'].values() for v in vs]
if _all:
    ax2.set_ylim(min(_all) - 1.5, max(_all) * 1.22)
ax2.legend(loc='lower right', fontsize=7); ygrid(ax2)
save(fig, 'rq3_latency')

# ── FIG 6 · RQ4 the failure loop ──────────────────────────────────────────────────────────────
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.6, 3.0))
stages = ['Drone\nfailures', 'Recovery\nraised', 'Fixable from\non-mission', 'Recovery\nresolved']
for i, (e, n, c) in enumerate(zip(E, NAMES, COL)):
    vals = [len(e['failures']), len(e['rec_opened']), e['rec_feasible'], len(e['rec_resolved'])]
    bars = ax1.bar(np.arange(4) + (i - 0.5) * W, vals, W, label=n, color=c, zorder=3)
    barlabel(ax1, bars, '{:.0f}', dy=0.05)
ax1.set_xticks(range(4)); ax1.set_xticklabels(stages, fontsize=7.5)
ax1.set_ylabel('Count'); ax1.set_title('RQ4 · Failure → recovery funnel', fontsize=9)
ax1.legend(loc='upper right'); ygrid(ax1)

# Override quality: did the committed plan beat the agent's own projection? One dot per plan —
# with ~6 plans per scenario a histogram implies a distribution the pilot cannot support.
for k, (e, n, c) in enumerate(zip(E, NAMES, COL)):
    y = len(E) - 1 - k
    vals = e['override_delta']
    if vals:
        ax2.plot(vals, np.full(len(vals), y) + np.linspace(-0.09, 0.09, len(vals)), 'o',
                 ms=6, color=c, mec=SURFACE, mew=1.2, zorder=3)
        ax2.plot([np.mean(vals)] * 2, [y - 0.2, y + 0.2], '-', lw=2.4, color=c, zorder=4)
ax2.axvline(0, color=INK, lw=1.2, zorder=2)
ax2.set_yticks(range(len(E))); ax2.set_yticklabels(list(reversed(NAMES)), fontsize=8)
ax2.set_ylim(-0.6, len(E) - 0.4)
ax2.set_xlabel('Committed plan − agent projection (s)\n← operator faster | agent faster →', fontsize=8)
ax2.set_title('RQ4 · Override quality\n(one dot per plan; bar = mean)', fontsize=9)
ax2.xaxis.grid(True); ax2.set_axisbelow(True); ax2.yaxis.grid(False)
save(fig, 'rq4_recovery')

# ── FIG 7 · snapshot-derived load timeline ────────────────────────────────────────────────────
fig, axes = plt.subplots(2, 1, figsize=(8.0, 4.4), sharex=True)
for e, n, c in zip(E, NAMES, COL):
    axes[0].plot(e['t'], e['active'], lw=2, color=c, label=f'{n} — active')
    axes[0].plot(e['t'], e['queued'], lw=1.6, ls='--', color=c, alpha=0.85, label=f'{n} — queued')
    axes[1].plot(e['t'], e['reserve'], lw=2, color=c, label=n)
axes[0].set_ylabel('Missions'); axes[0].legend(loc='upper left', ncols=2, fontsize=7)
axes[0].set_title('Operator load over the session, from state_snapshot (10 s cadence)', fontsize=9)
axes[1].set_ylabel('Drones in reserve'); axes[1].set_xlabel('Session time (s)')
axes[1].legend(loc='upper right', ncols=2, fontsize=7)
for a in axes: ygrid(a)
save(fig, 'timeline')

# ── FIG 8 · task failure reasons + end-of-session trust ───────────────────────────────────────
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.6, 3.0))
reasons = sorted({r for e in E for r in e['fail_reasons']})
for i, (e, n, c) in enumerate(zip(E, NAMES, COL)):
    vals = [e['fail_reasons'].get(r, 0) for r in reasons]
    bars = ax1.bar(np.arange(len(reasons)) + (i - 0.5) * W, vals, W, label=n, color=c, zorder=3)
    barlabel(ax1, bars, '{:.0f}', dy=0.1)
ax1.set_xticks(range(len(reasons)))
ax1.set_xticklabels([r.replace('_', '\n') for r in reasons], fontsize=7)
ax1.set_ylabel('Tasks'); ax1.set_title('Why tasks failed', fontsize=9)
_mx = max((e['fail_reasons'].get(r, 0) for e in E for r in reasons), default=1)
ax1.set_ylim(0, _mx * 1.28)
ax1.legend(loc='upper left', fontsize=7); ygrid(ax1)

trust_keys = [('trust_strategic', 'Strategic'), ('trust_tactical', 'Tactical')]
for i, (e, n, c) in enumerate(zip(E, NAMES, COL)):
    means = []
    for k, _ in trust_keys:
        r = e['surveys'].get(k, {})
        means.append(float(np.mean(list(r.values()))) if r else 0.0)
    bars = ax2.bar(np.arange(2) + (i - 0.5) * W, means, W, label=n, color=c, zorder=3)
    barlabel(ax2, bars, '{:.1f}', dy=0.05)
ax2.set_xticks(range(2)); ax2.set_xticklabels([t[1] for t in trust_keys])
ax2.set_ylim(1, 7.6); ax2.set_ylabel('Mean trust (1–7)')
ax2.set_title('End-of-session trust, by assistant tier', fontsize=9)
ax2.legend(loc='upper right'); ygrid(ax2)
save(fig, 'failures_trust')

# ── summary ───────────────────────────────────────────────────────────────────────────────────
summary = {
    'source': SRC.name,
    'participantId': d['participantId'], 'condition': d['condition'],
    'epsilonStrategic': d['epsilonStrategic'], 'epsilonTactical': d['epsilonTactical'],
    'seed': d['seed'],
    'appVersion': E[0]['start'].get('appVersion'),
    'sessions': [],
}
for e, n in zip(E, NAMES):
    summary['sessions'].append({
        'scenario': n, 'duration': e['duration'],
        'score': e['score'], 'points': e['points'], 'penalty': e['penalty'],
        'missionsArrived': e['arrived'], 'outcomes': e['outcomes'],
        'abandoned': e['abandoned'], 'unresolvedAtEnd': e['unresolved'],
        'tasksCompleted': len(e['task_completed']), 'tasksFailed': len(e['task_failed']),
        'failReasons': dict(e['fail_reasons']),
        'strategicChoices': len(e['choices']), 'modalDismissals': e['dismissed'],
        'cardPreviews': e['previews'], 'manualEdits': e['manual_edits'],
        'cardAcceptance': {k: {'accepted': v[0], 'offered': v[1]} for k, v in e['card_acceptance'].items()},
        'tacticalPlans': e['tac_total'], 'tacticalConsulted': e['tac_consulted'],
        'tacticalModified': e['tac_modified'], 'tacticalErrorsInjected': e['tac_error_injected'],
        'strandedTasks': e['stranded'],
        'medianStrategicDeliberationS': float(np.median(e['strat_delib'])) if e['strat_delib'] else None,
        'medianForcedWaitS': float(np.median(e['strat_gate'])) if e['strat_gate'] else None,
        'medianTacticalLatencyS': float(np.median(e['tac_latency'])) if e['tac_latency'] else None,
        'droneFailures': len(e['failures']), 'recoveriesOpened': len(e['rec_opened']),
        'recoveriesResolved': len(e['rec_resolved']),
        'medianRecoveryLatencyS': float(np.median(e['rec_latency'])) if e['rec_latency'] else None,
        'snapshots': len(e['snaps']),
        'surveys': {k: round(float(np.mean(list(v.values()))), 2) for k, v in e['surveys'].items()},
    })
(OUT / 'summary.json').write_text(json.dumps(summary, indent=2))
print(f'  wrote {(OUT / "summary.json").relative_to(BASE)}')
print(json.dumps(summary['sessions'], indent=2)[:1400])
