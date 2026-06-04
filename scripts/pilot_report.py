#!/usr/bin/env python3
"""
SAR Pilot Analysis Report
Reads two mid-session snapshots from logs/Pilots/M/ and produces pilot_report.pdf.
"""

import json, io
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
from matplotlib.gridspec import GridSpec

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib import colors as rlc
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image,
    Table, TableStyle, PageBreak, HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY, TA_RIGHT

# ── paths ────────────────────────────────────────────────────────────────────
BASE    = Path(__file__).resolve().parent.parent
LOG_DIR = BASE / 'logs' / 'Pilots' / 'M'
OUT_PDF = LOG_DIR / 'pilot_report.pdf'

# ── load ─────────────────────────────────────────────────────────────────────
files = sorted(LOG_DIR.glob('*.json'))
raw = {}
for f in files:
    d = json.load(open(f))
    raw[d['participantId']] = d

d1 = raw['P-3666']   # complexity: tactical
d2 = raw['P-2673']   # complexity: strategic

# ── colours ──────────────────────────────────────────────────────────────────
C_TAC    = '#1565C0'   # tactical (P-3666) — dark blue
C_STR    = '#BF360C'   # strategic (P-2673) — dark orange
C_COMP   = '#2E7D32'   # completed
C_ABAND  = '#C62828'   # abandoned
C_ACTIV  = '#6A1B9A'   # active
C_QUEUE  = '#757575'   # queued
C_AVAIL  = '#388E3C'
C_DEPLD  = '#1976D2'
C_RETRN  = '#F57F17'
C_FAILC  = '#D32F2F'
C_AGENT  = '#1B5E20'   # agent-followed
C_MANUAL = '#E65100'   # manual

plt.rcParams.update({
    'font.family':        'DejaVu Sans',
    'font.size':          9,
    'axes.spines.top':    False,
    'axes.spines.right':  False,
    'axes.grid':          True,
    'grid.alpha':         0.25,
    'grid.linestyle':     '--',
    'figure.facecolor':   'white',
    'axes.facecolor':     'white',
})

# ── helpers ───────────────────────────────────────────────────────────────────
def fig2img(fig, dpi=150):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight', facecolor='white')
    buf.seek(0)
    plt.close(fig)
    return buf

def embed(buf_or_path, w_cm):
    img = Image(buf_or_path)
    w = w_cm * cm
    img.drawWidth  = w
    img.drawHeight = w * (img.imageHeight / img.imageWidth)
    return img

# ── data extraction ───────────────────────────────────────────────────────────
def extract(d):
    ev  = d['sessions'][0]
    out = dict(
        pid       = d['participantId'],
        complexity= d['complexity'],
        elapsed   = d['liveSession']['elapsed'],
        penalty   = d['penaltyAccrued'],
        missions  = d['liveSession']['missions'],
        assets    = d['liveSession']['assets'],
    )

    # Strategic choices — keep last per mission
    strat = {}
    for e in ev:
        if e['type'] == 'strategic_choice':
            strat[e['missionId']] = e
    out['strat'] = strat

    # Tactical confirmations — normalise field name
    tac_raw = [e for e in ev if e['type'] == 'tactical_confirmed']
    for t in tac_raw:
        t['modified'] = t.get('modifiedFromAgentPlan', False)
    out['tac'] = tac_raw

    # Modal opens: count and last timestamp per mission
    modal_ct, modal_last = {}, {}
    for e in ev:
        if e['type'] == 'strategic_modal_opened':
            mid = e['missionId']
            modal_ct[mid]   = modal_ct.get(mid, 0) + 1
            modal_last[mid] = e['elapsed']
    out['modal_ct']   = modal_ct
    out['modal_last'] = modal_last

    # Decision latency: last modal open → strategic choice (s)
    latency = {}
    for mid, e in strat.items():
        if mid in modal_last:
            latency[mid] = max(0.0, e['elapsed'] - modal_last[mid])
    out['latency'] = latency

    # Drone failures (sorted by time)
    out['failures'] = sorted(
        [{'t': e['elapsed'], 'type': e['droneType']}
         for e in ev if e['type'] == 'drone_failure'],
        key=lambda x: x['t']
    )

    # Mission outcome counts
    outcomes = {'completed': 0, 'abandoned': 0, 'active': 0, 'queued': 0}
    for m in out['missions']:
        outcomes[m['status']] = outcomes.get(m['status'], 0) + 1
    out['outcomes'] = outcomes

    # Asset state {(type, status): count}
    ast = {}
    for a in out['assets']:
        k = (a['type'], a['status'])
        ast[k] = ast.get(k, 0) + 1
    out['ast'] = ast

    return out

e1, e2 = extract(d1), extract(d2)

LABELS   = [f"P-3666\n(tactical)", f"P-2673\n(strategic)"]
COLORS   = [C_TAC, C_STR]
PILOTS   = [e1, e2]

# ═══════════════════════════════════════════════════════════════════════════════
# FIGURES
# ═══════════════════════════════════════════════════════════════════════════════

# ── Fig 1: Mission outcomes ───────────────────────────────────────────────────
def fig_outcomes():
    fig, ax = plt.subplots(figsize=(8.5, 2.6))
    cats    = ['completed', 'abandoned', 'active', 'queued']
    cmap    = [C_COMP, C_ABAND, C_ACTIV, C_QUEUE]
    labels  = ['Completed', 'Abandoned', 'Active', 'Queued']
    ys      = [0, 0.55]
    heights = [0.38] * 2

    for row, (e, y) in enumerate(zip(PILOTS, ys)):
        left = 0
        for cat, col, lbl in zip(cats, cmap, labels):
            val = e['outcomes'].get(cat, 0)
            if val > 0:
                bar = ax.barh(y, val, height=heights[row], left=left,
                              color=col, label=lbl if row == 0 else '')
                ax.text(left + val / 2, y, str(val), ha='center', va='center',
                        fontsize=8, fontweight='bold', color='white')
            left += val

    total = sum(e1['outcomes'].values())
    ax.set_xlim(0, total + 0.5)
    ax.set_yticks(ys)
    ax.set_yticklabels([f"P-3666\n(tactical, {int(e1['elapsed'])}s)",
                        f"P-2673\n(strategic, {int(e2['elapsed'])}s)"],
                       fontsize=8)
    ax.set_xlabel('Mission count')
    ax.set_title('Mission Outcomes at Snapshot', fontweight='bold', pad=8)
    ax.yaxis.grid(False)
    handles = [mpatches.Patch(color=c, label=l) for c, l in zip(cmap, labels)]
    ax.legend(handles=handles, loc='lower right', fontsize=7.5,
              framealpha=0.8, ncol=2)
    fig.tight_layout()
    return fig2img(fig)

# ── Fig 2: Strategic agent follow rate ────────────────────────────────────────
def fig_strategic_follow():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.5, 3.2))

    for ax, e, col, lbl in zip([ax1, ax2], PILOTS, COLORS, LABELS):
        choices = e['strat']
        n_agent  = sum(1 for v in choices.values() if v['wasAgentSuggestion'])
        n_manual = sum(1 for v in choices.values() if not v['wasAgentSuggestion'])
        total    = n_agent + n_manual

        bars = ax.bar(['Agent\nfollowed', 'Manual\noverride'],
                      [n_agent, n_manual],
                      color=[C_AGENT, C_MANUAL], width=0.5, zorder=3)
        for bar, val in zip(bars, [n_agent, n_manual]):
            pct = 100 * val / total if total else 0
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.05,
                    f'{val}  ({pct:.0f}%)',
                    ha='center', va='bottom', fontsize=8.5, fontweight='bold')

        ax.set_ylim(0, max(n_agent, n_manual) + 1.5)
        ax.set_ylabel('Missions', fontsize=8)
        ax.set_title(lbl.replace('\n', '  '), fontweight='bold', color=col, fontsize=9)
        ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))

    fig.suptitle('Strategic Agent Follow Rate', fontweight='bold', y=1.01, fontsize=10)
    fig.tight_layout()
    return fig2img(fig)

# ── Fig 3: Tactical modification rate ────────────────────────────────────────
def fig_tactical():
    fig, ax = plt.subplots(figsize=(8.5, 3.0))

    groups = ['Agent-suggested\n& accepted\nunmodified',
              'Agent-suggested\n& modified',
              'Manual\n(no suggestion)']
    x = np.arange(len(groups))
    w = 0.3

    for i, (e, col, lbl) in enumerate(zip(PILOTS, COLORS, LABELS)):
        tac  = e['tac']
        n_unmod  = sum(1 for t in tac if t['wasAgentSuggested'] and not t['modified'])
        n_mod    = sum(1 for t in tac if t['wasAgentSuggested'] and t['modified'])
        n_manual = sum(1 for t in tac if not t['wasAgentSuggested'])
        vals = [n_unmod, n_mod, n_manual]
        offset = (i - 0.5) * w
        bars = ax.bar(x + offset, vals, w, color=col, alpha=0.85,
                      label=lbl.replace('\n', ' '), zorder=3)
        for bar, val in zip(bars, vals):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 0.04,
                        str(val), ha='center', va='bottom', fontsize=8.5, fontweight='bold')

    ax.set_xticks(x)
    ax.set_xticklabels(groups, fontsize=8)
    ax.set_ylabel('Count')
    ax.set_title('Tactical Plan Confirmations', fontweight='bold', fontsize=10)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax.legend(fontsize=8)
    fig.tight_layout()
    return fig2img(fig)

# ── Fig 4: Decision latency per mission ───────────────────────────────────────
def fig_latency():
    fig, axes = plt.subplots(1, 2, figsize=(8.5, 3.2), sharey=False)

    for ax, e, col, lbl in zip(axes, PILOTS, COLORS, LABELS):
        mids = sorted(e['latency'].keys(),
                      key=lambda m: e['strat'][m]['elapsed'])
        lats = [e['latency'][m] for m in mids]
        short_ids = [m.replace('M00', 'M').replace('M0', 'M') for m in mids]

        xs = np.arange(len(mids))
        bars = ax.bar(xs, lats, color=col, alpha=0.85, zorder=3)
        for bar, val in zip(bars, lats):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.3,
                    f'{val:.0f}s', ha='center', va='bottom', fontsize=7.5)

        ax.set_xticks(xs)
        ax.set_xticklabels(short_ids, rotation=35, ha='right', fontsize=7.5)
        ax.set_ylabel('Seconds', fontsize=8)
        ax.set_title(lbl.replace('\n', '  '), fontweight='bold', color=col, fontsize=9)
        ax.set_ylim(0, max(lats) * 1.3 + 2 if lats else 5)

    fig.suptitle('Decision Latency (last modal open → choice)', fontweight='bold',
                 y=1.01, fontsize=10)
    fig.tight_layout()
    return fig2img(fig)

# ── Fig 5: Modal re-opens per mission ────────────────────────────────────────
def fig_modal_reopens():
    # All missions that had at least one modal open across either pilot
    all_mids = sorted(
        set(e1['modal_ct']) | set(e2['modal_ct']),
        key=lambda m: (len(m), m)
    )
    x   = np.arange(len(all_mids))
    w   = 0.35
    fig, ax = plt.subplots(figsize=(8.5, 3.0))

    for i, (e, col, lbl) in enumerate(zip(PILOTS, COLORS, LABELS)):
        vals   = [e['modal_ct'].get(m, 0) for m in all_mids]
        offset = (i - 0.5) * w
        bars   = ax.bar(x + offset, vals, w, color=col, alpha=0.85,
                        label=lbl.replace('\n', ' '), zorder=3)
        for bar, val in zip(bars, vals):
            if val > 1:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 0.04,
                        str(val), ha='center', va='bottom',
                        fontsize=8, fontweight='bold', color='black')

    ax.axhline(1, color='black', linewidth=0.8, linestyle=':', alpha=0.6,
               label='1 open (expected)')
    ax.set_xticks(x)
    short = [m.replace('M00', 'M').replace('M0', 'M') for m in all_mids]
    ax.set_xticklabels(short, rotation=35, ha='right', fontsize=7.5)
    ax.set_ylabel('Modal open count')
    ax.set_title('Strategic Modal Opens per Mission\n(>1 = re-opened after dismiss)',
                 fontweight='bold', fontsize=10)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax.legend(fontsize=8)
    fig.tight_layout()
    return fig2img(fig)

# ── Fig 6: Drone failure timeline ────────────────────────────────────────────
def fig_failures():
    fig, ax = plt.subplots(figsize=(8.5, 3.2))

    for e, col, lbl in zip(PILOTS, COLORS, LABELS):
        if not e['failures']:
            continue
        ts = [0] + [f['t'] for f in e['failures']] + [e['elapsed']]
        ys = list(range(len(ts)))
        ys[-1] = ys[-2]   # flat line to snapshot end
        ax.step(ts, ys, where='post', color=col, linewidth=2,
                label=lbl.replace('\n', ' '))
        for j, f in enumerate(e['failures'], 1):
            marker = 'D' if f['type'] == 'Blue' else ('s' if f['type'] == 'Red' else '^')
            ax.plot(f['t'], j, marker=marker, color=col, markersize=5, zorder=4)

    # legend for drone types
    for marker, label in [('D', 'Blue failure'), ('s', 'Red failure'), ('^', 'Green failure')]:
        ax.plot([], [], marker=marker, color='gray', linestyle='none',
                markersize=6, label=label)

    ax.set_xlabel('Session elapsed (s)')
    ax.set_ylabel('Cumulative failures')
    ax.set_title('Drone Failure Timeline', fontweight='bold', fontsize=10)
    ax.legend(fontsize=7.5, ncol=2, loc='upper left')
    fig.tight_layout()
    return fig2img(fig)

# ── Fig 7: Asset health at snapshot ──────────────────────────────────────────
def fig_assets():
    fig, axes = plt.subplots(1, 2, figsize=(8.5, 3.4), sharey=False)
    drone_types  = ['Blue', 'Red', 'Green']
    statuses     = ['available', 'deployed', 'returning', 'failed']
    stat_colors  = [C_AVAIL, C_DEPLD, C_RETRN, C_FAILC]
    stat_labels  = ['Available', 'Deployed', 'Returning', 'Failed']

    for ax, e, col, lbl in zip(axes, PILOTS, COLORS, LABELS):
        x = np.arange(len(drone_types))
        bottoms = np.zeros(len(drone_types))
        for stat, sc, sl in zip(statuses, stat_colors, stat_labels):
            vals = np.array([e['ast'].get((dt, stat), 0) for dt in drone_types])
            bars = ax.bar(x, vals, 0.55, bottom=bottoms, color=sc,
                          label=sl if ax == axes[0] else '', zorder=3)
            for bar, val, bot in zip(bars, vals, bottoms):
                if val > 0:
                    ax.text(bar.get_x() + bar.get_width() / 2,
                            bot + val / 2, str(int(val)),
                            ha='center', va='center', fontsize=7.5,
                            fontweight='bold', color='white')
            bottoms += vals

        ax.set_xticks(x)
        ax.set_xticklabels(drone_types)
        ax.set_ylabel('Drone count')
        ax.set_title(lbl.replace('\n', '  '), fontweight='bold', color=col, fontsize=9)
        ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))

    handles = [mpatches.Patch(color=c, label=l)
               for c, l in zip(stat_colors, stat_labels)]
    axes[0].legend(handles=handles, fontsize=7.5, loc='upper right')
    fig.suptitle('Asset Health at Snapshot', fontweight='bold', y=1.01, fontsize=10)
    fig.tight_layout()
    return fig2img(fig)

# ── Fig 8: Penalty comparison ─────────────────────────────────────────────────
def fig_penalty():
    fig, ax = plt.subplots(figsize=(4.2, 2.8))
    vals  = [e1['penalty'], e2['penalty']]
    xlbls = [f"P-3666\n(tactical)", f"P-2673\n(strategic)"]
    bars  = ax.bar(xlbls, vals, color=COLORS, width=0.4, zorder=3)
    for bar, val in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 2,
                str(val), ha='center', va='bottom',
                fontsize=10, fontweight='bold')
    ax.set_ylabel('Penalty points')
    ax.set_title('Penalty Accrued', fontweight='bold', fontsize=10)
    fig.tight_layout()
    return fig2img(fig)

# ═══════════════════════════════════════════════════════════════════════════════
# REPORTLAB DOCUMENT
# ═══════════════════════════════════════════════════════════════════════════════

styles = getSampleStyleSheet()

def S(name, **kw):
    base = styles[name]
    return ParagraphStyle(name + '_custom', parent=base, **kw)

TITLE   = S('Title',    fontSize=20, leading=24, spaceAfter=4,  textColor=rlc.HexColor('#1A237E'))
H1      = S('Heading1', fontSize=14, leading=17, spaceBefore=14, spaceAfter=4,
            textColor=rlc.HexColor('#1A237E'))
H2      = S('Heading2', fontSize=11, leading=13, spaceBefore=10, spaceAfter=3,
            textColor=rlc.HexColor('#37474F'))
BODY    = S('Normal',   fontSize=9,  leading=13, spaceAfter=4, alignment=TA_JUSTIFY)
BULLET  = S('Normal',   fontSize=9,  leading=13, spaceAfter=3,
            leftIndent=14, firstLineIndent=-10, alignment=TA_JUSTIFY)
CAPTION = S('Normal',   fontSize=7.5, leading=10, spaceAfter=6,
            textColor=rlc.HexColor('#546E7A'), alignment=TA_CENTER)
SMALL   = S('Normal',   fontSize=8,  leading=11, spaceAfter=2,
            textColor=rlc.HexColor('#546E7A'))
WARN    = S('Normal',   fontSize=9,  leading=13, spaceAfter=4,
            textColor=rlc.HexColor('#B71C1C'), alignment=TA_JUSTIFY)

HR = HRFlowable(width='100%', thickness=0.5,
                color=rlc.HexColor('#90A4AE'), spaceAfter=4, spaceBefore=4)

def caption(text):
    return Paragraph(f'<i>{text}</i>', CAPTION)

def bullet(text):
    return Paragraph(f'• {text}', BULLET)

def warn(text):
    return Paragraph(f'<b>!</b> {text}', WARN)

# ── Overview table ────────────────────────────────────────────────────────────
def overview_table():
    strat_follow = lambda e: sum(1 for v in e['strat'].values() if v['wasAgentSuggestion'])
    strat_total  = lambda e: len(e['strat'])
    tac_mod      = lambda e: sum(1 for t in e['tac'] if t['wasAgentSuggested'] and t['modified'])
    tac_agent    = lambda e: sum(1 for t in e['tac'] if t['wasAgentSuggested'])

    def pct(a, b): return f'{a}/{b} ({100*a//b if b else 0}%)' if b else '—'

    rows = [
        ['Metric', 'P-3666  (tactical)', 'P-2673  (strategic)'],
        ['Session elapsed',
         f"{int(e1['elapsed'])}s  (~{e1['elapsed']/60:.1f} min)",
         f"{int(e2['elapsed'])}s  (~{e2['elapsed']/60:.1f} min)"],
        ['Penalty accrued', str(e1['penalty']), str(e2['penalty'])],
        ['Missions arrived',
         str(sum(e1['outcomes'].values())),
         str(sum(e2['outcomes'].values()))],
        ['Missions completed',
         str(e1['outcomes']['completed']),
         str(e2['outcomes']['completed'])],
        ['Missions abandoned',
         str(e1['outcomes']['abandoned']),
         str(e2['outcomes']['abandoned'])],
        ['Strategic: agent followed',
         pct(strat_follow(e1), strat_total(e1)),
         pct(strat_follow(e2), strat_total(e2))],
        ['Tactical: agent modified',
         pct(tac_mod(e1), tac_agent(e1)),
         pct(tac_mod(e2), tac_agent(e2))],
        ['Drone failures (total)',
         str(len(e1['failures'])),
         str(len(e2['failures']))],
        ['Blue drones failed',
         str(sum(1 for f in e1['failures'] if f['type'] == 'Blue')),
         str(sum(1 for f in e2['failures'] if f['type'] == 'Blue'))],
    ]

    col_w = [5.5*cm, 5.5*cm, 5.5*cm]
    t = Table(rows, colWidths=col_w)
    t.setStyle(TableStyle([
        ('BACKGROUND',  (0, 0), (-1, 0),  rlc.HexColor('#1A237E')),
        ('TEXTCOLOR',   (0, 0), (-1, 0),  rlc.white),
        ('FONTNAME',    (0, 0), (-1, 0),  'Helvetica-Bold'),
        ('FONTSIZE',    (0, 0), (-1, 0),  8.5),
        ('FONTNAME',    (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE',    (0, 1), (-1, -1), 8),
        ('BACKGROUND',  (0, 1), (-1, -1), rlc.HexColor('#F5F5F5')),
        ('BACKGROUND',  (0, 2), (-1, 2),  rlc.HexColor('#FFEBEE')),  # penalty highlight
        ('ROWBACKGROUNDS', (0, 3), (-1, -1),
         [rlc.HexColor('#FAFAFA'), rlc.HexColor('#F0F4FF')]),
        ('ALIGN',       (1, 1), (-1, -1), 'CENTER'),
        ('ALIGN',       (0, 0), (0, -1),  'LEFT'),
        ('VALIGN',      (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID',        (0, 0), (-1, -1), 0.4, rlc.HexColor('#B0BEC5')),
        ('TOPPADDING',  (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING',(0,0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',(0, 0), (-1, -1), 6),
        ('FONTNAME',    (0, 1), (0, -1),  'Helvetica-Bold'),
    ]))
    return t

# ── Build doc ─────────────────────────────────────────────────────────────────
print('Generating figures…')
img_outcomes  = embed(fig_outcomes(),      17)
img_strat     = embed(fig_strategic_follow(), 17)
img_tac       = embed(fig_tactical(),      17)
img_latency   = embed(fig_latency(),       17)
img_modal     = embed(fig_modal_reopens(), 17)
img_failures  = embed(fig_failures(),      17)
img_assets    = embed(fig_assets(),        17)
img_penalty   = embed(fig_penalty(),       8.3)

print('Building PDF…')

doc = SimpleDocTemplate(
    str(OUT_PDF),
    pagesize=A4,
    leftMargin=2*cm, rightMargin=2*cm,
    topMargin=2*cm, bottomMargin=2*cm,
    title='SAR Study — Pilot Analysis Report',
    author='Auto-generated',
)

story = []

# ── Cover / header ────────────────────────────────────────────────────────────
story += [
    Paragraph('SAR Trust Study', TITLE),
    Paragraph('Pilot Analysis Report — Session 1 Snapshots', H1),
    Paragraph(
        'Two 7-minute pilots; one per complexity mode. Both used <i>mode=agent</i>, '
        '<i>condition=none</i>, ε=0 (perfect accuracy). '
        'Snapshots captured mid-session; sessions 2 and 3 untouched.',
        BODY),
    Spacer(1, 0.3*cm),
    overview_table(),
    Spacer(1, 0.3*cm),
]

# ══════════════════════════════════════════════════════════════════════════════
story += [
    Paragraph('Part 1: Findings', H1),
    HR,
]

# ── 1.1 Mission outcomes ──────────────────────────────────────────────────────
story += [
    Paragraph('1.1  Mission Outcomes', H2),
    Paragraph(
        'P-3666 (tactical) completed <b>zero missions</b> in 6.4 minutes and accrued 535 '
        'penalty points — 3.6× the penalty of P-2673 (strategic, 150 pts). '
        'Five missions were abandoned mid-execution; seven more sat queued and never reached '
        'allocation. P-2673 completed two missions (M001 and M003) with two abandoned, three '
        'still active, and three queued at the snapshot.',
        BODY),
    img_outcomes,
    caption('Figure 1. Mission status at snapshot. Numbers inside bars are mission counts.'),
    Spacer(1, 0.2*cm),
]

story += [
    Table([[img_penalty]],
          colWidths=[8.3*cm],
          style=[('ALIGN', (0,0), (-1,-1), 'LEFT')]),
    caption('Figure 2. Penalty accrued. P-3666 (tactical) was 3.6× worse despite following '
            'the agent more often, pointing to a difficulty imbalance rather than a behavioural one.'),
    Spacer(1, 0.2*cm),
    Paragraph(
        'The tactical complexity scenario had missions with 5–6 tasks and very high drone '
        'failure density. By elapsed 250 s (under halfway), all ten Blue drones were '
        'destroyed or failed in P-3666, leaving the operator unable to staff subsequent '
        'missions even when ready to allocate.',
        BODY),
]

# ── 1.2 Strategic agent ───────────────────────────────────────────────────────
story += [
    Paragraph('1.2  Strategic Agent Follow Rate', H2),
    Paragraph(
        'P-3666 followed the Strategic Agent in <b>5 of 6 allocated missions (83%)</b>. '
        'P-2673 followed it in only <b>2 of 7 (29%)</b>, preferring manual allocation for '
        'five missions including the first three in the session. '
        'The divergence is striking given that both runs used ε=0 (perfectly accurate agent). '
        'It is not an accuracy effect — it is likely a UI familiarity or trust-calibration '
        'effect that will need watching in the real study.',
        BODY),
    img_strat,
    caption('Figure 3. Final strategic choice per mission: agent-followed vs. manual. '
            'Percentages are of total allocated missions.'),
    Spacer(1, 0.2*cm),
]

# ── 1.3 Tactical agent ────────────────────────────────────────────────────────
story += [
    Paragraph('1.3  Tactical Agent Modification Rate', H2),
    Paragraph(
        'In both pilots, the operator modified the Tactical Agent\'s assignment plan '
        '<b>100% of the time</b> it was presented (5/5 in P-3666; 2/2 in P-2673). '
        'The plan was never accepted without drag-and-drop changes. '
        'Manual allocations (where no agent plan was shown) were always confirmed as-is.',
        BODY),
    img_tac,
    caption('Figure 4. Tactical confirmations by category. '
            '"Agent-suggested & accepted unmodified" is zero for both pilots.'),
    Spacer(1, 0.2*cm),
    Paragraph(
        'This does not necessarily mean the plan was wrong — operators may have had '
        'legitimate reasons (drone position, personal strategy). However a 100% '
        'modification rate warrants investigation before the live study.',
        BODY),
]

# ── 1.4 Decision latency ──────────────────────────────────────────────────────
story += [
    Paragraph('1.4  Decision Latency', H2),
    Paragraph(
        'Latency is measured from the last strategic modal open to the final strategic '
        'choice for each mission. Early missions in both runs were decided quickly (3–8 s). '
        'Later missions took substantially longer: up to 24 s for P-3666\'s M006, '
        'and P-2673\'s M001 remained in the modal workflow for over 35 s across three '
        'sequential opens.',
        BODY),
    img_latency,
    caption('Figure 5. Decision latency per mission (last modal open → choice). '
            'Missions in chronological order left to right.'),
    Spacer(1, 0.2*cm),
]

# ── 1.5 Modal re-opens ────────────────────────────────────────────────────────
story += [
    Paragraph('1.5  Strategic Modal Re-opens', H2),
    Paragraph(
        'Re-opening the modal (count > 1) is a proxy for hesitation or dissatisfaction '
        'with the initial options. P-2673\'s M001 was opened <b>three times</b> — the '
        'operator made two manual choices before finally deploying. '
        'Three missions across each pilot had their modals re-opened at least once. '
        'Two missions (M008 in P-3666; M008 in P-2673) had the modal open with an '
        '<b>empty strategy list</b> — the system opened the dialog but had no valid '
        'suggestions to show due to depleted reserves.',
        BODY),
    img_modal,
    caption('Figure 6. Strategic modal open count per mission. '
            'Dotted line = 1 (expected single open). '
            'Missions not present in a pilot had no modal event.'),
    Spacer(1, 0.2*cm),
]

# ── 1.6 Drone failures ────────────────────────────────────────────────────────
story += [
    Paragraph('1.6  Drone Failure Timeline', H2),
    Paragraph(
        'Both pilots experienced similar overall failure rates (~1.3–1.4 per minute). '
        'The key difference is <i>which drones</i> failed. In P-3666 (tactical), '
        'failures concentrated in Blue drones — 8 of 9 total failures were Blues — '
        'because tactical missions committed Blue drones to high-attrition Type-5 tasks. '
        'By ~250 s the entire Blue fleet was gone. '
        'P-2673\'s failures were distributed more evenly (5 Blue, 1 Red) and '
        'the fleet remained partially functional at snapshot.',
        BODY),
    img_failures,
    caption('Figure 7. Cumulative drone failures over time. '
            'Markers show drone type: ◆ Blue, ■ Red, ▲ Green.'),
    Spacer(1, 0.2*cm),
    img_assets,
    caption('Figure 8. Asset health at snapshot. '
            'Colours: green=available, blue=deployed, orange=returning, red=failed.'),
    Spacer(1, 0.2*cm),
]

# ═══════════════════════════════════════════════════════════════════════════════
story += [
    PageBreak(),
    Paragraph('Part 2: What Needs to Change', H1),
    HR,
    Paragraph(
        'These findings come from one pilot per mode with a single operator under '
        'no-noise conditions (ε=0). Confidence is limited, but several issues are '
        'structural enough to address before the live study.',
        SMALL),
    Spacer(1, 0.2*cm),
]

# ── 2.1 Difficulty balance ───────────────────────────────────────────────────
story += [
    Paragraph('2.1  Difficulty Balance — Tactical Complexity Is Too Hard', H2),
    Paragraph(
        '<b>Issue:</b> P-3666 completed zero missions in 6+ minutes and had its entire '
        'Blue fleet wiped out by the halfway point. With zero positive feedback events '
        'and a compounding penalty, a real participant would likely disengage or attribute '
        'performance failure to the interface rather than their own strategy.',
        BODY),
    bullet('Check whether the mission generator is correctly applying the "tactical" '
           'complexity parameters. If task counts and Poisson arrival rate are both set to '
           'hard levels simultaneously, the combination may be unintentional.'),
    bullet('Consider decoupling <i>mission complexity</i> (task count, drone commitment) '
           'from <i>session difficulty</i> (arrival rate). The study needs cognitive load '
           'variance, not a death spiral.'),
    bullet('Add a floor on reserve: if the reserve drops below a threshold, pause new '
           'arrivals briefly or cap the strategic agent\'s recommended commitment. '
           'Operators should not be able to commit their last Green drone.'),
    bullet('Run a calibration pass: aim for ≥1 completion per 7-minute window in both '
           'complexity modes so participants experience at least some success.'),
    Spacer(1, 0.1*cm),
    warn('This must be resolved before any condition-based between-subjects comparison '
         'is meaningful — difficulty differences will swamp condition effects.'),
]

# ── 2.2 Empty strategy modals ────────────────────────────────────────────────
story += [
    Paragraph('2.2  Empty Strategy Modal Must Not Fire', H2),
    Paragraph(
        '<b>Issue:</b> When <tt>strategiesPresented</tt> is empty the modal still opens, '
        'presenting the operator with a blank dialog. This happened on M001-R (first open) '
        'and M008 in P-3666, and M008 in P-2673. In all cases no allocation followed.',
        BODY),
    bullet('Gate the modal on <tt>strategiesPresented.length > 0</tt>. If no strategy can '
           'be generated, either skip straight to the tactical planner with a "manual '
           'allocation required" message, or show an inline notice in the mission queue.'),
    bullet('Log the "no viable strategy" event explicitly so it can be tracked in analysis.'),
]

# ── 2.3 Tactical plan modifications ─────────────────────────────────────────
story += [
    Paragraph('2.3  Tactical Plan — Investigate Why 100% Are Modified', H2),
    Paragraph(
        '<b>Issue:</b> Every tactical plan presented by the agent was edited before '
        'confirmation. This is concerning because the tactical follow-rate is one of '
        'the study\'s dependent variables — if it always floors at 0% regardless of '
        'condition, it cannot discriminate.',
        BODY),
    bullet('Audit <tt>greedyAssign()</tt> output against what was actually deployed. '
           'Check whether the suggested asset IDs differ from what the operator chose '
           'in obvious ways (e.g. agent picks B01 which is about to fail, operator '
           'manually swaps to a healthy one).'),
    bullet('Check whether the <i>display</i> of the tactical plan is clear. If operators '
           'do not recognise the agent\'s suggestion as a recommendation they should '
           'evaluate, they may edit by default as a "confirmation" action.'),
    bullet('Consider logging a finer-grained diff: which specific task assignments were '
           'changed vs. which were kept. "Modified" is a binary flag but the plan might '
           'be 90% followed with one swap.'),
    bullet('If operators are drag-dropping tasks because chaining is confusing (not because '
           'they disagree with the plan), the chaining UI may need a clearer visual '
           'explanation.'),
]

# ── 2.4 Modal re-open flow ───────────────────────────────────────────────────
story += [
    Paragraph('2.4  Strategic Modal Re-open Flow', H2),
    Paragraph(
        '<b>Issue:</b> M001 in P-2673 was opened three times with two intermediate '
        'manual choices — suggesting the operator was unsure how to adjust a custom '
        'allocation after committing, or inadvertently closed the modal.',
        BODY),
    bullet('Add a "Change allocation" button to the active mission panel so operators '
           'can revise without fully re-opening the strategic modal from scratch.'),
    bullet('If the modal is dismissed without a choice, warn the operator that the '
           'mission remains unallocated, rather than silently closing.'),
    bullet('Consider whether the manual asset-count entry UX is clear: P-2673 tried '
           'three different custom bundles (1B1R1G, then 2B, then 2B confirmed). '
           'The controls may not give enough feedback about viability.'),
]

# ── 2.5 Low strategic follow in strategic mode ────────────────────────────────
story += [
    Paragraph('2.5  Low Agent Follow Rate in Strategic Complexity Mode', H2),
    Paragraph(
        '<b>Issue:</b> P-2673 went manual on 5/7 strategic decisions despite a '
        'perfectly accurate agent (ε=0). Smaller missions (2–4 tasks, Blue-only) may '
        'make the agent\'s suggestions look over-engineered relative to "just send 2 Blues".',
        BODY),
    bullet('Verify the agent generates sensible cards for small missions. '
           'For M001 (2 tasks, Blue-only) the Conservative card recommended '
           '4B+1R+1G — the operator deployed 2 Blues and completed it fine. '
           'The suggestion may have looked wasteful.'),
    bullet('Add a third piece of information to strategy cards: <i>minimum viable '
           'bundle</i> vs. agent recommendation, so operators can calibrate how '
           'conservative the agent is being.'),
    bullet('Consider whether the strategic-mode complexity missions should include more '
           'mixed-type tasks so the agent\'s multi-drone orchestration is visibly '
           'necessary, not optional.'),
]

# ── 2.6 Logging gaps ─────────────────────────────────────────────────────────
story += [
    Paragraph('2.6  Logging Gaps', H2),
    Paragraph(
        'Analysis was limited to what the snapshot captures. Some events were not '
        'available:',
        BODY),
    bullet('<b>No failure_recovery events logged</b> — M005 and M007 in P-2673 had '
           '<tt>failureRecoveryPending: true</tt> at snapshot but no recovery actions '
           'appear in the event stream. Confirm this event fires correctly.'),
    bullet('<b>No task_failed events</b> — abandoned missions still had tasks in '
           '"executing" or "traveling" state at abandonment. It is unclear whether '
           'these fire a task_failed event.'),
    bullet('<b>Tactical modification granularity</b> — as noted above, the binary '
           '<tt>modifiedFromAgentPlan</tt> flag should be supplemented by a per-task '
           'diff for richer analysis of where operator trust breaks down.'),
    Spacer(1, 0.3*cm),
]

story += [
    HR,
    Paragraph(
        'Report generated automatically from mid-session snapshot logs. '
        'P-3666 snapshot at 384 s elapsed, P-2673 at 330 s elapsed. '
        'Both runs: mode=agent, condition=none, ε_S=ε_T=0.',
        SMALL),
]

doc.build(story)
print(f'\nDone: {OUT_PDF}')
