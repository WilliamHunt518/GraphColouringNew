#!/usr/bin/env python3
"""Round 2 · workstream F · how operators handle the strategic cards.

Read-only over Results/. Writes only docs/analysis/round2/wF_specs.csv. Run from the repo root:

    C:/Users/Work/anaconda3/python.exe scripts/analysis_round2/wF_cards.py

Every variant below was written (with its expected direction) before the script was first run;
see the analysis log in docs/analysis/round2/wF_cards.md. All GEEs: exchangeable, clustered on
participant, small-sample (Mancl-DeRouen) errors via .fit(cov_type='bias_reduced'). Gate refits
(session 1 only, each scenario order, leave-one-person-out) only need the point estimate, so they
use the same model.

F1 anchoring  -- natural experiment. The same 42 missions recur across participants (fixed seed);
                 within a mission the cards' drone counts vary only because the reserve differed at
                 the time. Mission fixed effects (within-mission demeaning) hold need and composition
                 fixed. Exposed = manual allocations built from scratch AFTER the cards loaded;
                 control = manual allocations committed BEFORE the cards loaded (they never saw the
                 numbers, but share the reserve -> commit path). The anchoring estimate is the
                 card x exposed interaction (a difference-in-differences), which nets out the reverse
                 path (a fuller reserve both raises the card and lets the operator commit more).
F2 edits      -- manual allocations seeded from a card ("Edit this allocation"): what changes.
F3 discrimination -- choice on single-type missions by illogical (odd) Conservative card, and by
                 dominated card (also on three-type missions, where dominated is not tied to odd);
                 card previewing.
F4 pre-emption -- manual before the cards loaded: person vs situation.
X1, X2        -- extras (pre-stated in the report's log).
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
warnings.filterwarnings('ignore')

import statsmodels.api as sm  # noqa: E402
import statsmodels.formula.api as smf  # noqa: E402

import wF_common as F  # noqa: E402

COLS = F.COLOURS
OUT = ROOT / 'docs' / 'analysis' / 'round2' / 'wF_specs.csv'
SPECS = []
RNG_SEED = 20261007


# ── generic fitting + gates ──────────────────────────────────────────────────────────────────

def _clean(formula, data):
    # drop terms that are constant in this subsample (e.g. run in session-1-only refits)
    for col, t in (('run', ' + run'), ('scenario', ' + C(scenario)'), ('order_s', ' + order_s'),
                   ('game', ' + C(game)')):
        if col in data and data[col].nunique() < 2:
            formula = formula.replace(t, '')
    return formula


def _fit(formula, data, binom, robust=True):
    formula = _clean(formula, data)
    fam = sm.families.Binomial() if binom else sm.families.Gaussian()
    mod = smf.gee(formula, 'pid', data=data, family=fam, cov_struct=sm.cov_struct.Exchangeable())
    return mod.fit(cov_type='bias_reduced') if robust else mod.fit()


def _b(formula, data, binom, name):
    try:
        if data.pid.nunique() < 3 or len(data) < 8:
            return np.nan
        r = _fit(formula, data, binom, robust=False)
        b = float(r.params[name])
        return b if np.isfinite(b) and abs(b) < 15 else np.nan
    except Exception:
        return np.nan


def _same(a, b):
    if not np.isfinite(a) or not np.isfinite(b):
        return 'na'
    return '1' if np.sign(a) == np.sign(b) else '0'


def gates(base, prep, formula, name, binom, b_main, s1=True):
    out = {}
    out['s1'] = _same(b_main, _b(formula, prep(base[base.run == 1]), binom, name)) if s1 else 'na'
    o1 = _b(formula, prep(base[base.order_s == 1]), binom, name)
    o0 = _b(formula, prep(base[base.order_s == 0]), binom, name)
    so1, so0 = _same(b_main, o1), _same(b_main, o0)
    out['orders'] = 'na' if 'na' in (so1, so0) else ('1' if so1 == so0 == '1' else '0')
    out['o'] = (o1, o0)
    loo = []
    for p in sorted(base.pid.unique()):
        loo.append(_b(formula, prep(base[base.pid != p]), binom, name))
    loo = np.array([x for x in loo if np.isfinite(x)])
    if len(loo) and np.isfinite(b_main):
        out['loo'] = '1' if (np.sign(loo) != np.sign(b_main)).any() else '0'
        out['loo_rng'] = (loo.min(), loo.max())
    else:
        out['loo'], out['loo_rng'] = 'na', (np.nan, np.nan)
    return out


SAMPLES = {
    'S-all': lambda d: d,
    'S-v112': lambda d: d[d.v112 == 1],
    'S-s1': lambda d: d[d.run == 1],
    'S-27': lambda d: d[d.swapped == 0],
    'S-6': lambda d: d[d.swapped == 1],
}


def spec(vid, desc, base, prep, formula, name, binom, expected, outcome, predictor,
         samples=('S-all',), extra=0, notes='', game_fe=False, do_gates=True):
    """Fit one variant on each requested sample, with gates, and record a spec row per sample."""
    for code in samples:
        sub = SAMPLES[code](base)
        f = formula
        model = 'GEE %s, exch, person-clustered, bias-reduced' % ('logit' if binom else 'gaussian')
        if game_fe:
            f = formula + ' + C(game) + order_s'
            model += ' + game FE + order'
        data = prep(sub)
        row = dict(workstream='F', variant_id=vid, extra=extra, description=desc, sample=code,
                   outcome=outcome, predictor=predictor, model=model,
                   estimate_scale='OR' if binom else 'b', expected_direction=expected,
                   n_obs=len(data), n_people=data.pid.nunique() if len(data) else 0, notes=notes)
        try:
            r = _fit(f, data, binom)
            t = F.term(r, name, exp=binom)
            if code == 'S-6':
                t['p'] = np.nan
                row['notes'] = (notes + ' Descriptive only (S-6).').strip()
            row.update(estimate=t['est'], ci_lo=t['lo'], ci_hi=t['hi'], p=t['p'])
            if do_gates and code in ('S-all', 'S-v112', 'S-27'):
                g = gates(sub, prep, f, name, binom, t['b'], s1=True)
                rng = g['loo_rng']
                if binom:
                    rng = tuple(np.exp(x) for x in rng)
                row.update(s1_same_direction=g['s1'], both_orders_same_direction=g['orders'],
                           loo_sign_flip=g['loo'])
                row['notes'] = (row['notes'] + ' LOO range [%.3f, %.3f]; order est (SH-first, TH-first) b=(%.3f, %.3f).'
                                % (rng[0], rng[1], g['o'][0], g['o'][1])).strip()
            elif do_gates and code == 'S-s1':
                g = gates(sub, prep, f, name, binom, t['b'], s1=False)
                row.update(s1_same_direction='na', both_orders_same_direction=g['orders'],
                           loo_sign_flip=g['loo'])
                rng = g['loo_rng']
                if binom:
                    rng = tuple(np.exp(x) for x in rng)
                row['notes'] = (row['notes'] + ' LOO range [%.3f, %.3f].' % rng).strip()
            else:
                row.update(s1_same_direction='na', both_orders_same_direction='na', loo_sign_flip='na')
        except Exception as e:  # separation, singular design, empty cell
            row.update(estimate=np.nan, ci_lo=np.nan, ci_hi=np.nan, p=np.nan,
                       s1_same_direction='na', both_orders_same_direction='na', loo_sign_flip='na')
            row['notes'] = (notes + ' NOT ESTIMABLE: %s' % type(e).__name__).strip()
        SPECS.append(row)
        print('  %-6s %-7s %-34s est=%8.3f [%7.3f, %7.3f] p=%.4f n=%d/%d  s1=%s ord=%s loo=%s'
              % (vid, code, predictor[:34], row['estimate'], row['ci_lo'], row['ci_hi'],
                 row['p'] if np.isfinite(row['p']) else np.nan, row['n_obs'], row['n_people'],
                 row['s1_same_direction'], row['both_orders_same_direction'], row['loo_sign_flip']))


def record(**kw):
    base = dict(workstream='F', extra=0, s1_same_direction='na', both_orders_same_direction='na',
                loo_sign_flip='na', notes='')
    base.update(kw)
    SPECS.append(base)
    print('  %-6s %-7s %-34s est=%8.3f p=%s n=%s' % (kw['variant_id'], kw['sample'], kw['predictor'][:34],
                                                    kw['estimate'], kw.get('p'), kw.get('n_obs')))


def hdr(s):
    print('\n' + '=' * 100 + '\n' + s + '\n' + '=' * 100)


# ── data ─────────────────────────────────────────────────────────────────────────────────────

def load():
    d = F.decisions()
    for pre in ('cons', 'aggr', 'chosen', 'resO'):
        d[pre + '_need'] = sum(np.where(d['need_' + c] > 0, d[pre + '_' + c], 0) for c in COLS)
    d['com_need'] = d['chosen_need']
    d['mid_need'] = (d.cons_need + d.aggr_need) / 2
    d['grp'] = np.select([d.manual == 0, d.early == 1, d.editedFrom.notna()],
                         ['card', 'pre', 'edit'], 'scratch')
    d.loc[(d.manual == 1) & d.early.isna(), 'grp'] = 'unflagged'   # 2 decisions: no switch snapshot
    d['choseC'] = (d.choice == 'conservative').astype(int)
    d['choseA'] = (d.choice == 'aggressive').astype(int)
    d['preempt'] = np.where(d.grp == 'unflagged', np.nan, (d.early == 1).astype(float))
    d['netsecs'] = np.log1p(np.maximum(0, d.secs - d.reveal_s))
    # reserve could bind on a needed colour: the picker caps at the reserve, and a card capped by
    # the reserve moves with it mechanically
    d['capbind'] = 0
    for c in COLS:
        need = d['need_' + c] > 0
        d['capbind'] |= (need & (d['resC_' + c] <= np.maximum.reduce(
            [d['cons_' + c], d['aggr_' + c], d['chosen_' + c]]))).astype(int)
    # lag: the previous decision in the same session
    d = d.sort_values(['pid', 'run', 'idx']).reset_index(drop=True)
    g = d.groupby(['pid', 'run'])
    d['prev_odd'] = g.odd.shift(1)
    d['prev_dom'] = g.dominated.shift(1)
    d['prev_nc1'] = (g.ncolours.shift(1) == 1).astype(float).where(g.ncolours.shift(1).notna())
    d['nc1'] = (d.ncolours == 1).astype(int)
    return d


def demean(df, cols, by='mkey'):
    df = df.copy()
    for v in cols:
        df[v + '_dm'] = df[v] - df.groupby(by)[v].transform('mean')
    return df


# ── F1 · anchoring ────────────────────────────────────────────────────────────────────────────

def f1(d):
    hdr('F1 · ANCHORING: do manual allocations track the card numbers at a fixed mission?')
    base = d[(d.residual == 0) & d.grp.isin(['scratch', 'pre'])].copy()
    base['exposed'] = (base.grp == 'scratch').astype(int)
    print('manual, genuine missions: %d exposed (from scratch after reveal), %d control (before reveal), '
          '%d missions' % (base.exposed.sum(), (1 - base.exposed).sum(), base.mkey.nunique()))
    wm = demean(d[d.residual == 0], ['cons_need', 'aggr_need', 'res_open'])
    print('within-mission SD over all decisions: Conservative (needed colours) %.2f, Aggressive %.2f, '
          'reserve %.2f drones; r(Cons, reserve) = %.2f'
          % (wm.cons_need_dm.std(), wm.aggr_need_dm.std(), wm.res_open_dm.std(),
             np.corrcoef(wm.cons_need_dm, wm.res_open_dm)[0, 1]))

    def prep_did(x, anchor='cons_need', out='com_need', extra=()):
        return demean(x, [anchor, out, 'res_open', *extra])

    spec('F1.1', 'Anchoring DiD: manual drones (needed colours) on the Conservative card total, '
         'within mission; exposed (scratch, after reveal) vs control (before reveal)', base,
         prep_did, 'com_need_dm ~ cons_need_dm * exposed', 'cons_need_dm:exposed', False, '+',
         'drones committed, needed colours (within-mission)', 'Cons card total x saw cards',
         samples=('S-all', 'S-v112', 'S-s1', 'S-27', 'S-6'))
    spec('F1.1g', 'F1.1 with game FE and order', base, prep_did,
         'com_need_dm ~ cons_need_dm * exposed', 'cons_need_dm:exposed', False, '+',
         'drones committed, needed colours (within-mission)', 'Cons card total x saw cards', game_fe=True)
    spec('F1.2', 'Exposed only: manual drones on Conservative card total within mission (anchoring + '
         'reserve path together)', base[base.exposed == 1], prep_did, 'com_need_dm ~ cons_need_dm',
         'cons_need_dm', False, '+', 'drones committed (within-mission)', 'Cons card total')
    spec('F1.3', 'Control only (never saw the cards): the reverse path -- reserve moves the card and '
         'the commitment together', base[base.exposed == 0], prep_did, 'com_need_dm ~ cons_need_dm',
         'cons_need_dm', False, 'none', 'drones committed (within-mission)', 'Cons card total (unseen)')
    spec('F1.4', 'F1.1 + reserve (and reserve x exposed) controls', base, prep_did,
         'com_need_dm ~ cons_need_dm * exposed + res_open_dm * exposed', 'cons_need_dm:exposed', False,
         '+', 'drones committed (within-mission)', 'Cons card total x saw cards | reserve')
    spec('F1.5', 'DiD with the Aggressive card total as anchor', base,
         lambda x: prep_did(x, anchor='aggr_need'), 'com_need_dm ~ aggr_need_dm * exposed',
         'aggr_need_dm:exposed', False, '+', 'drones committed (within-mission)', 'Aggr card total x saw cards')
    spec('F1.6', 'DiD with the mean of the two cards as anchor', base,
         lambda x: prep_did(x, anchor='mid_need'), 'com_need_dm ~ mid_need_dm * exposed',
         'mid_need_dm:exposed', False, '+', 'drones committed (within-mission)', 'mean card total x saw cards')
    spec('F1.7', 'DiD on raw totals incl. the unused-colour padding', base,
         lambda x: prep_did(x, anchor='cons_total', out='committed'), 'committed_dm ~ cons_total_dm * exposed',
         'cons_total_dm:exposed', False, 'none', 'all drones committed (within-mission)',
         'Cons raw total x saw cards', notes='Padding of unused colours is never copied (round 1 H8), so a weaker slope is expected.')
    # per colour: rows = decision x needed colour, demeaned within mission x colour
    rows = []
    for c in COLS:
        x = base[base['need_' + c] > 0][['pid', 'run', 'order_s', 'v112', 'swapped', 'game', 'mkey',
                                         'exposed']].copy()
        x['colour'] = c
        x['card'] = base.loc[x.index, 'cons_' + c]
        x['chosen'] = base.loc[x.index, 'chosen_' + c]
        x['res'] = base.loc[x.index, 'resO_' + c]
        x['mc'] = x.mkey + ':' + c
        rows.append(x)
    pc = pd.concat(rows, ignore_index=True)
    spec('F1.8', 'Per needed colour: drones of that colour on the Conservative card count of that '
         'colour, within mission x colour, DiD', pc, lambda x: demean(x, ['card', 'chosen'], by='mc'),
         'chosen_dm ~ card_dm * exposed', 'card_dm:exposed', False, '+',
         'drones of colour c (within mission x colour)', 'Cons count of c x saw cards')
    spec('F1.9', 'F1.1 excluding decisions where the reserve could bind on a needed colour '
         '(removes the mechanical cap)', base[base.capbind == 0], prep_did,
         'com_need_dm ~ cons_need_dm * exposed', 'cons_need_dm:exposed', False, '+',
         'drones committed (within-mission)', 'Cons card total x saw cards | no cap')
    b10 = d[(d.residual == 0) & d.grp.isin(['scratch', 'pre', 'edit'])].copy()
    b10['exposed'] = (b10.grp != 'pre').astype(int)
    spec('F1.10', 'F1.1 with card edits counted as exposed (mechanically anchored)', b10, prep_did,
         'com_need_dm ~ cons_need_dm * exposed', 'cons_need_dm:exposed', False, '+',
         'drones committed (within-mission)', 'Cons card total x saw cards (incl. edits)')

    def prep_abs(x):
        x = x.copy()
        x['absdev'] = (x.com_need - x.mid_need).abs()
        return demean(x, ['absdev'])
    spec('F1.11', 'Proximity: |manual - card midpoint| within mission, exposed vs control',
         base, prep_abs, 'absdev_dm ~ exposed', 'exposed', False, '-',
         '|committed - card midpoint| (within-mission)', 'saw cards')

    # descriptive: where do the drones sit?
    for g_, s in base.groupby('exposed'):
        print('  %s: mean committed %.2f vs Cons %.2f / Aggr %.2f (needed colours), n=%d'
              % ('exposed' if g_ else 'control', s.com_need.mean(), s.cons_need.mean(),
                 s.aggr_need.mean(), len(s)))


# ── F2 · edits ──────────────────────────────────────────────────────────────────────────────

def f2(d):
    hdr('F2 · SENSIBLE EDITS: what operators change when they edit a card')
    e = d[d.grp == 'edit'].copy()
    e['src'] = np.where(e.editedFrom == 'Conservative', 'cons', 'aggr')
    print('edited-from-card decisions: %d (%d from Aggressive, %d from Conservative), %d people'
          % (len(e), (e.src == 'aggr').sum(), (e.src == 'cons').sum(), e.pid.nunique()))
    # unneeded colours on the card
    un = [(r.pid, r.src, c, getattr(r, r.src + '_' + c), getattr(r, 'chosen_' + c))
          for r in e.itertuples() for c in COLS if getattr(r, 'need_' + c) == 0 and getattr(r, r.src + '_' + c) > 0]
    print('edited cards that carried an unneeded colour: %d colour-slots; removed in %d' %
          (len(un), sum(1 for u in un if u[4] == 0)))
    record(variant_id='F2.1', description='Edited card carried an unneeded colour: share of those '
           'slots removed (n too small to model)', sample='S-all', outcome='unneeded colour removed',
           predictor='card carried unneeded colour', model='descriptive count',
           estimate=(sum(1 for u in un if u[4] == 0) / len(un)) if un else np.nan, ci_lo=np.nan,
           ci_hi=np.nan, estimate_scale='diff', p=np.nan, n_obs=len(un),
           n_people=len({u[0] for u in un}), expected_direction='+',
           notes='Only one edited card carried an unneeded colour (both slots removed). Not testable.')
    # per needed colour: was it reduced, given the card exceeded the badge need of that colour?
    rows = []
    for r in e.itertuples():
        for c in COLS:
            if getattr(r, 'need_' + c) == 0:
                continue
            card = getattr(r, r.src + '_' + c)
            rows.append(dict(pid=r.pid, run=r.run, order_s=r.order_s, v112=r.v112, swapped=r.swapped,
                             game=r.game, src=r.src, colour=c, card=card, final=getattr(r, 'chosen_' + c),
                             over=int(card > getattr(r, 'need_' + c)),
                             above_floor=card - getattr(r, 'floor_' + c)))
    pc = pd.DataFrame(rows)
    pc['reduced'] = (pc.final < pc.card).astype(int)
    pc['raised'] = (pc.final > pc.card).astype(int)
    print('per needed colour slot (n=%d): reduced %.0f%%, raised %.0f%%, unchanged %.0f%%'
          % (len(pc), 100 * pc.reduced.mean(), 100 * pc.raised.mean(),
             100 * (1 - pc.reduced.mean() - pc.raised.mean())))
    print(pd.crosstab([pc.src, pc.over], [pc.reduced, pc.raised], margins=True))
    spec('F2.2', 'Edited cards, per needed colour: reduced when the card committed more of it than '
         'the badges ask for', pc, lambda x: x, 'reduced ~ over', 'over', True, '+',
         'colour reduced in the edit', 'card > badge need for colour')
    spec('F2.3', 'Edited cards, per needed colour: reduced as the card sits further above the '
         'sequential floor (the minimum that can finish)', pc, lambda x: x, 'reduced ~ above_floor',
         'above_floor', True, '+', 'colour reduced in the edit', 'card - floor (drones)')
    # total change by source card
    e['delta'] = e.committed - np.where(e.src == 'cons', e.cons_total, e.aggr_total)
    for s_, lab, exp in (('aggr', 'Aggressive', '-'), ('cons', 'Conservative', 'none')):
        sub = e[e.src == s_]
        print('  edited from %s: mean change %+.2f drones (n=%d, %d people)'
              % (lab, sub.delta.mean(), len(sub), sub.pid.nunique()))
        spec('F2.4' + s_[0], 'Edited from the %s card: change in total drones (intercept)' % lab, sub,
             lambda x: x, 'delta ~ 1', 'Intercept', False, exp, 'final - card total (drones)',
             'edited from %s' % lab)
    # below the sequential floor: unsafe manual allocations by route
    m = d[(d.manual == 1) & (d.residual == 0) & d.grp.isin(['edit', 'scratch', 'pre'])].copy()
    m['below'] = sum(((m['need_' + c] > 0) & (m['chosen_' + c] < m['floor_' + c])).astype(int) for c in COLS).gt(0).astype(int)
    print('manual allocations below the sequential floor on some needed colour:')
    print(m.groupby('grp').below.agg(['mean', 'sum', 'count']))
    m['edited'] = (m.grp == 'edit').astype(int)
    spec('F2.5', 'Manual allocations below the sequential floor: edited-from-card vs built from '
         'scratch / pre-empted', m, lambda x: x, 'below ~ edited + ncolours + ndrones', 'edited', True,
         '-', 'allocation below the minimum that can finish', 'edited from card')
    # trails: does an unneeded colour ever appear in a manual build, and is it removed?
    tr = d[(d.manual == 1) & (d.residual == 0)]
    ever = fin = 0
    for r in tr.itertuples():
        un_c = [c for c in COLS if getattr(r, 'need_' + c) == 0]
        if not un_c:
            continue
        if any(a.get(c, 0) > 0 for a, _ in r.edits for c in un_c):
            ever += 1
            fin += int(any(getattr(r, 'chosen_' + c) > 0 for c in un_c))
    n_un = int((tr.ncolours < 3).sum())
    print('manual builds on missions with an unused colour: %d; an unused colour ever added: %d; '
          'kept at deploy: %d' % (n_un, ever, fin))
    record(variant_id='F2.6', description='Manual edit trails on missions with an unused colour: '
           'share where an unused colour was ever added', sample='S-all',
           outcome='unused colour ever added in the trail', predictor='(descriptive)',
           model='descriptive count', estimate=ever / n_un if n_un else np.nan, ci_lo=np.nan,
           ci_hi=np.nan, estimate_scale='diff', p=np.nan, n_obs=n_un, n_people=tr.pid.nunique(),
           expected_direction='none', notes='%d of those kept it at deploy.' % fin)


# ── F3 · discrimination ──────────────────────────────────────────────────────────────────────

def f3(d):
    hdr('F3 · DISCRIMINATION: reacting to an illogical / dominated Conservative card in the moment')
    st = d[(d.ncolours == 1) & (d.residual == 0) & (d.preempt == 0)].copy()
    st['manual_post'] = st.manual
    print('single-type, genuine, cards loaded: %d decisions (%d odd, %d clean), %d people'
          % (len(st), st.odd.sum(), (1 - st.odd).sum(), st.pid.nunique()))
    print(pd.crosstab(st.odd, st.choice, normalize='index').round(3))
    print(pd.crosstab([st.odd, st.dominated], st.choice))
    cov = ' + ndrones + C(scenario) + run'
    ident = lambda x: x  # noqa: E731
    spec('F3.1', 'Single-type, after reveal: chose Conservative ~ illogical card', st, ident,
         'choseC ~ odd' + cov, 'odd', True, '-', 'chose Conservative', 'illogical Cons card',
         samples=('S-all', 'S-v112', 'S-s1', 'S-27', 'S-6'))
    spec('F3.1g', 'F3.1 with game FE + order', st, ident, 'choseC ~ odd + ndrones', 'odd', True, '-',
         'chose Conservative', 'illogical Cons card', game_fe=True)
    spec('F3.2', 'Single-type, after reveal: chose Aggressive ~ illogical card', st, ident,
         'choseA ~ odd' + cov, 'odd', True, '+', 'chose Aggressive', 'illogical Cons card')
    spec('F3.3', 'Single-type, after reveal: manual ~ illogical card', st, ident,
         'manual_post ~ odd' + cov, 'odd', True, '+', 'manual after reveal', 'illogical Cons card')
    spec('F3.4', 'F3.1 + reserve at opening (clean single-type cards happen when the reserve is low)',
         st, ident, 'choseC ~ odd + res_open' + cov, 'odd', True, '-', 'chose Conservative',
         'illogical Cons card | reserve')

    def mundlak(x):
        x = x.copy()
        x['odd_pm'] = x.groupby('pid').odd.transform('mean')
        return x
    spec('F3.5', 'F3.1 within person (Mundlak: + person mean of odd)', st, mundlak,
         'choseC ~ odd + odd_pm' + cov, 'odd', True, '-', 'chose Conservative', 'illogical (within person)')
    tk = st[st.took == 1]
    spec('F3.6', 'Single-type card takers: Conservative (vs Aggressive) ~ illogical', tk, ident,
         'choseC ~ odd' + cov, 'odd', True, '-', 'Conservative given a card', 'illogical Cons card')
    spec('F3.7', 'Single-type, after reveal: chose Conservative ~ dominated', st, ident,
         'choseC ~ dominated' + cov, 'dominated', True, '-', 'chose Conservative', 'dominated Cons card')
    spec('F3.8', 'Single-type: Conservative ~ dominated + illogical jointly (dominated term)', st, ident,
         'choseC ~ dominated + odd' + cov, 'dominated', True, '-', 'chose Conservative',
         'dominated | illogical')
    tt = d[(d.ncolours == 3) & (d.residual == 0) & (d.preempt == 0)].copy()
    print('three-type, genuine, after reveal: %d decisions, %d with a dominated Cons card'
          % (len(tt), tt.dominated.sum()))
    print(pd.crosstab(tt.dominated, tt.choice, normalize='index').round(3))
    spec('F3.9', 'Three-type, after reveal: chose Conservative ~ dominated (dominance without the '
         'odd colour)', tt, ident, 'choseC ~ dominated' + cov, 'dominated', True, '-',
         'chose Conservative', 'dominated Cons card', samples=('S-all', 'S-v112', 'S-s1', 'S-27', 'S-6'))
    spec('F3.9r', 'F3.9 + reserve at opening (dominance arises when the top-up is large, i.e. reserve full)',
         tt, ident, 'choseC ~ dominated + res_open' + cov, 'dominated', True, '-', 'chose Conservative',
         'dominated | reserve')
    tt2 = tt[tt.took == 1]
    spec('F3.10', 'Three-type card takers: Conservative (vs Aggressive) ~ dominated', tt2, ident,
         'choseC ~ dominated' + cov, 'dominated', True, '-', 'Conservative given a card', 'dominated Cons card')
    # previewing (selecting a card is how it is previewed; picking a card requires at least one)
    print('\npreviews: decisions with both cards highlighted: %d of %d (single-type %d, three-type %d)'
          % (d.prev_both.sum(), len(d), st.prev_both.sum(), tt.prev_both.sum()))
    allpost = d[(d.residual == 0) & (d.preempt == 0) & (d.ncolours != 2)].copy()
    allpost['bad'] = ((allpost.odd == 1) | (allpost.dominated == 1)).astype(int)
    spec('F3.11', 'After reveal (single- and three-type): highlighted both cards ~ bad Cons card '
         '(illogical or dominated)', allpost, ident, 'prev_both ~ bad + nc1' + cov, 'bad', True, '+',
         'highlighted both cards', 'bad Cons card')
    # among bad-card decisions where Conservative was highlighted: moved away from it?
    pc = allpost[(allpost.prev_cons == 1)].copy()
    pc['avoidC'] = 1 - pc.choseC
    print('decisions where the Conservative card was highlighted: %d; bad %d; moved away: bad %.1f%%, clean %.1f%%'
          % (len(pc), pc.bad.sum(), 100 * pc[pc.bad == 1].avoidC.mean(), 100 * pc[pc.bad == 0].avoidC.mean()))
    spec('F3.12', 'Conservative highlighted: did not end on it ~ bad Cons card', pc, ident,
         'avoidC ~ bad + nc1' + cov, 'bad', True, '+', 'left the highlighted Cons card', 'bad Cons card',
         notes='Conditioned on a within-decision event (Cons highlighted); calibrated by within-person permutation in F3.12n.')
    # permutation null for F3.12 (risk difference, bad label shuffled within person x composition)
    rng = np.random.default_rng(RNG_SEED)

    def rd(x, lab):
        a, b = x.loc[lab == 1, 'avoidC'], x.loc[lab == 0, 'avoidC']
        return a.mean() - b.mean() if len(a) and len(b) else np.nan
    obs = rd(pc, pc.bad.values)
    keys = (pc.pid + ':' + pc.nc1.astype(str)).values
    null = []
    for _ in range(2000):
        lab = pc.bad.values.copy()
        for k in np.unique(keys):
            ix = np.where(keys == k)[0]
            lab[ix] = rng.permutation(lab[ix])
        null.append(rd(pc, lab))
    null = np.array(null)
    p_cal = float((np.abs(null - null.mean()) >= abs(obs - null.mean())).mean())
    record(variant_id='F3.12n', description='Permutation null for F3.12: risk difference with the bad-card '
           'label shuffled within person x composition (2000 draws)', sample='S-all',
           outcome='left the highlighted Cons card', predictor='bad Cons card', model='permutation, RD',
           estimate=obs, ci_lo=float(np.percentile(null, 2.5)), ci_hi=float(np.percentile(null, 97.5)),
           estimate_scale='diff', p=p_cal, n_obs=len(pc), n_people=pc.pid.nunique(),
           expected_direction='+', notes='ci_lo/ci_hi are the null 2.5/97.5 percentiles; null mean %.3f.' % null.mean())
    bad = allpost[allpost.bad == 1].copy()
    bad['avoidC'] = 1 - bad.choseC
    spec('F3.13', 'Bad Cons card decisions: avoided Conservative ~ highlighted both cards', bad, ident,
         'avoidC ~ prev_both + nc1' + cov, 'prev_both', True, '+', 'did not choose Conservative',
         'highlighted both cards', notes='Mechanically biased towards "-": choosing Conservative requires highlighting it.')
    return st


# ── F4 · pre-emption ─────────────────────────────────────────────────────────────────────────

def _crossed(df, person=True):
    df = df.copy()
    df['one'] = 1
    vc = {'mission': '0 + C(mkey)'}
    if person:
        vc['person'] = '0 + C(pid)'
    m = smf.mixedlm('preempt ~ 1', df, groups='one', vc_formula=vc, re_formula='0')
    r = m.fit(reml=False, method=['lbfgs'])
    names = list(m.exog_vc.names)
    v = dict(zip(names, r.vcomp))
    return r, v


def f4(d):
    hdr('F4 · PRE-EMPTION: manual before the cards loaded -- person or situation?')
    p = d[(d.residual == 0) & d.preempt.notna()].copy()
    print('decisions: %d, pre-empted %d (%.1f%%), people %d' % (len(p), p.preempt.sum(),
                                                               100 * p.preempt.mean(), p.pid.nunique()))
    # variance partition, crossed person x mission (linear probability)
    r_full, v = _crossed(p)
    r_mis, _ = _crossed(p, person=False)
    tot = v['person'] + v['mission'] + r_full.scale
    lr = 2 * (r_full.llf - r_mis.llf)
    p_lr = 0.5 * stats.chi2.sf(lr, 1) if lr > 0 else 1.0
    print('variance shares: person %.3f, mission %.3f, residual %.3f; LR person p=%.2g'
          % (v['person'] / tot, v['mission'] / tot, r_full.scale / tot, p_lr))
    # gates for the person share
    def share(x):
        try:
            _, vv = _crossed(x)
            rr, _ = _crossed(x)
            t = vv['person'] + vv['mission'] + rr.scale
            return vv['person'] / t
        except Exception:
            return np.nan
    s_s1 = share(p[p.run == 1])
    s_o = (share(p[p.order_s == 1]), share(p[p.order_s == 0]))
    print('person share: S-s1 %.3f; SH-first %.3f; TH-first %.3f' % (s_s1, *s_o))
    record(variant_id='F4.1', description='Variance partition of pre-emption: crossed random intercepts '
           'for person and mission (linear probability, ML); person share of variance',
           sample='S-all', outcome='pre-empted the cards', predictor='person (random intercept)',
           model='MixedLM crossed VC person + mission', estimate=v['person'] / tot, ci_lo=np.nan,
           ci_hi=np.nan, estimate_scale='rho', p=p_lr, n_obs=len(p), n_people=p.pid.nunique(),
           expected_direction='+', notes='ICC-type share; mission share %.3f; LR test vs mission-only '
           '(halved chi2). Person share S-s1 %.3f, SH-first %.3f, TH-first %.3f.'
           % (v['mission'] / tot, s_s1, s_o[0], s_o[1]))
    p1 = p[p.run == 1]
    r1, v1 = _crossed(p1)
    r1m, _ = _crossed(p1, person=False)
    t1 = v1['person'] + v1['mission'] + r1.scale
    lr1 = 2 * (r1.llf - r1m.llf)
    record(variant_id='F4.1', description='Variance partition (session 1 only)', sample='S-s1',
           outcome='pre-empted the cards', predictor='person (random intercept)',
           model='MixedLM crossed VC person + mission', estimate=v1['person'] / t1, ci_lo=np.nan,
           ci_hi=np.nan, estimate_scale='rho', p=0.5 * stats.chi2.sf(lr1, 1) if lr1 > 0 else 1.0,
           n_obs=len(p1), n_people=p1.pid.nunique(), expected_direction='+',
           notes='mission share %.3f' % (v1['mission'] / t1))
    # person share after the situation is in the model
    def crossed_fx(df, fx):
        df = df.copy()
        df['one'] = 1
        m = smf.mixedlm('preempt ~ ' + fx, df, groups='one',
                        vc_formula={'mission': '0 + C(mkey)', 'person': '0 + C(pid)'}, re_formula='0')
        r = m.fit(reml=False, method=['lbfgs'])
        return dict(zip(m.exog_vc.names, r.vcomp)), r
    vx, rx = crossed_fx(p, 'nc1 + ndrones + queued + left + res_open + run')
    print('with situation fixed effects: person var %.4f (was %.4f), mission var %.4f (was %.4f)'
          % (vx['person'], v['person'], vx['mission'], v['mission']))
    record(variant_id='F4.2', description='Person variance remaining after situational fixed effects '
           '(single-type, size, queue, time left, reserve, run): ratio to F4.1 person variance',
           sample='S-all', outcome='pre-empted the cards', predictor='person | situation',
           model='MixedLM crossed VC + fixed effects', estimate=vx['person'] / v['person'], ci_lo=np.nan,
           ci_hi=np.nan, estimate_scale='diff', p=np.nan, n_obs=len(p), n_people=p.pid.nunique(),
           expected_direction='none', notes='Descriptive ratio (1 = the situation explains none of the person differences).')
    # session-to-session stability of the person rate, raw and composition-adjusted
    rate = p.groupby(['pid', 'run']).preempt.mean().unstack()
    both = rate.dropna()
    rho, pr = stats.spearmanr(both[1], both[2])
    lo, hi = _fisher(rho, len(both))
    record(variant_id='F4.3', description='Stability: person pre-emption rate, session 1 vs 2 (Spearman)',
           sample='S-all', outcome='pre-emption rate s2', predictor='pre-emption rate s1',
           model='Spearman', estimate=rho, ci_lo=lo, ci_hi=hi, estimate_scale='rho', p=pr,
           n_obs=len(both), n_people=len(both), expected_direction='+')
    mod = _fit('preempt ~ nc1 + ndrones + queued + left + res_open + C(game)', p, True)
    p['resid'] = p.preempt - mod.fittedvalues
    rr_ = p.groupby(['pid', 'run']).resid.mean().unstack().dropna()
    rho2, pr2 = stats.spearmanr(rr_[1], rr_[2])
    lo2, hi2 = _fisher(rho2, len(rr_))
    record(variant_id='F4.4', description='Stability of the situation-adjusted pre-emption residual '
           '(observed - expected from mission/game/load model), session 1 vs 2', sample='S-all',
           outcome='adjusted rate s2', predictor='adjusted rate s1', model='Spearman on GEE residuals',
           estimate=rho2, ci_lo=lo2, ci_hi=hi2, estimate_scale='rho', p=pr2, n_obs=len(rr_),
           n_people=len(rr_), expected_direction='+')
    for sub, code in ((p[p.v112 == 1], 'S-v112'), (p[p.swapped == 0], 'S-27')):
        rt = sub.groupby(['pid', 'run']).preempt.mean().unstack().dropna()
        r_, pp_ = stats.spearmanr(rt[1], rt[2])
        l_, h_ = _fisher(r_, len(rt))
        record(variant_id='F4.3', description='Stability: person pre-emption rate s1 vs s2', sample=code,
               outcome='pre-emption rate s2', predictor='pre-emption rate s1', model='Spearman',
               estimate=r_, ci_lo=l_, ci_hi=h_, estimate_scale='rho', p=pp_, n_obs=len(rt),
               n_people=len(rt), expected_direction='+')
    print('stability rho raw %.3f (p=%.3g), adjusted %.3f (p=%.3g)' % (rho, pr, rho2, pr2))
    # gates for the stability correlations: each scenario order, leave-one-person-out
    order_of = p.groupby('pid').order_s.first()
    for row_ix, tab, r0 in ((-4, both, rho), (-3, rr_, rho2)):
        tgt = [x for x in SPECS if x['variant_id'] == ('F4.3' if r0 is rho else 'F4.4')
               and x['sample'] == 'S-all'][0]
        ro = [stats.spearmanr(tab.loc[order_of.reindex(tab.index) == o, 1],
                              tab.loc[order_of.reindex(tab.index) == o, 2])[0] for o in (1, 0)]
        loo = [stats.spearmanr(tab.drop(i)[1], tab.drop(i)[2])[0] for i in tab.index]
        tgt['both_orders_same_direction'] = '1' if all(np.sign(x) == np.sign(r0) for x in ro) else '0'
        tgt['loo_sign_flip'] = '1' if any(np.sign(x) != np.sign(r0) for x in loo) else '0'
        tgt['notes'] = (tgt['notes'] + ' Gates: SH-first rho %.3f, TH-first %.3f; LOO range [%.3f, %.3f]. '
                        'S-s1 gate not applicable (the test is s1 vs s2).' % (ro[0], ro[1], min(loo), max(loo))).strip()
        print('  gates %s: orders %.3f / %.3f, LOO [%.3f, %.3f]' % (tgt['variant_id'], ro[0], ro[1], min(loo), max(loo)))
    # F4.1 gates: person share leave-one-person-out; permutation null for the person share
    f41 = [x for x in SPECS if x['variant_id'] == 'F4.1' and x['sample'] == 'S-all'][0]
    loo = [share(p[p.pid != q]) for q in sorted(p.pid.unique())]
    f41['s1_same_direction'] = '1' if s_s1 > 0 else '0'
    f41['both_orders_same_direction'] = '1' if min(s_o) > 0 else '0'
    f41['loo_sign_flip'] = '1' if min(loo) <= 0 else '0'
    f41['notes'] += ' LOO person share [%.3f, %.3f]. A variance share cannot change sign; gates read as "stays > 0".' % (min(loo), max(loo))
    # method-of-moments ICC on mission-demeaned outcome, person labels permuted within mission
    def icc_mm(y, g):
        df_ = pd.DataFrame({'y': y, 'g': g})
        k = df_.groupby('g').y.agg(['mean', 'count'])
        n0 = (len(df_) - (k['count'] ** 2).sum() / len(df_)) / (len(k) - 1)
        msb = (k['count'] * (k['mean'] - df_.y.mean()) ** 2).sum() / (len(k) - 1)
        msw = ((df_.y - df_.g.map(k['mean'])) ** 2).sum() / (len(df_) - len(k))
        return (msb - msw) / (msb + (n0 - 1) * msw)
    y = (p.preempt - p.groupby('mkey').preempt.transform('mean')).values
    obs_icc = icc_mm(y, p.pid.values)
    rng = np.random.default_rng(RNG_SEED + 2)
    mk = p.mkey.values
    nul = []
    for _ in range(2000):
        g = p.pid.values.copy()
        for k_ in np.unique(mk):
            ix = np.where(mk == k_)[0]
            g[ix] = rng.permutation(g[ix])
        nul.append(icc_mm(y, g))
    nul = np.array(nul)
    record(variant_id='F4.1p', description='Person ICC of pre-emption after removing mission means '
           '(ANOVA estimator); person labels permuted within mission (2000 draws)', sample='S-all',
           outcome='pre-empted the cards', predictor='person', model='ANOVA ICC + permutation',
           estimate=obs_icc, ci_lo=float(np.percentile(nul, 2.5)), ci_hi=float(np.percentile(nul, 97.5)),
           estimate_scale='rho', p=float((np.sum(nul >= obs_icc) + 1) / (len(nul) + 1)), n_obs=len(p),
           n_people=p.pid.nunique(), expected_direction='+',
           notes='ci = null 2.5/97.5 percentiles; one-sided permutation p. Robust alternative to the F4.1 LR test, '
                 'which assumes normal errors on a 0/1 outcome.')
    # situational predictors (GEE logit, all at once)
    f = 'preempt ~ nc1 + ndrones + queued + left + res_open + run + C(scenario)'
    for nm, exp, lab in (('nc1', '+', 'single-type mission'), ('ndrones', '-', 'drones needed'),
                         ('queued', '+', 'missions queued (load)'), ('left', 'none', 'seconds left'),
                         ('res_open', 'none', 'reserve at opening'), ('run', 'none', 'session 2')):
        spec('F4.5', 'Situational predictors of pre-emption, joint GEE (%s term)' % lab, p, lambda x: x,
             f, nm, True, exp, 'pre-empted the cards', lab)
    spec('F4.5g', 'Single-type term with game FE + order', p, lambda x: x,
         'preempt ~ nc1 + ndrones + queued + left + res_open', 'nc1', True, '+', 'pre-empted the cards',
         'single-type mission', game_fe=True)
    spec('F4.5s', 'Single-type term, sample variants', p, lambda x: x, f.replace(' + run', ''), 'nc1', True, '+',
         'pre-empted the cards', 'single-type mission', samples=('S-v112', 'S-s1', 'S-27', 'S-6'))

    def mund(x):
        x = x.copy()
        for v_ in ('nc1', 'queued'):
            x[v_ + '_pm'] = x.groupby(['pid', 'run'])[v_].transform('mean')
            x[v_ + '_w'] = x[v_] - x[v_ + '_pm']
        return x
    fm = 'preempt ~ nc1_w + nc1_pm + queued_w + queued_pm + ndrones + C(scenario) + run'
    spec('F4.6', 'Within person-session (Mundlak): single-type', p, mund, fm, 'nc1_w', True, '+',
         'pre-empted the cards', 'single-type (within person-session)')
    spec('F4.6', 'Within person-session (Mundlak): queue length', p, mund, fm, 'queued_w', True, '+',
         'pre-empted the cards', 'queued (within person-session)')
    mm = p[p.manual == 1]
    spec('F4.7', 'Among manual choices only: pre-empted ~ single-type', mm, lambda x: x,
         'preempt ~ nc1 + ndrones + queued + C(scenario) + run', 'nc1', True, '+',
         'manual was pre-emptive', 'single-type mission')
    return p


def _fisher(r, n):
    if n <= 3 or abs(r) >= 1:
        return np.nan, np.nan
    se = np.sqrt((1 + r * r / 2) / (n - 3))
    z = np.arctanh(r)
    return float(np.tanh(z - 1.96 * se)), float(np.tanh(z + 1.96 * se))


# ── extras ────────────────────────────────────────────────────────────────────────────────────

def extras(d, st):
    hdr('EXTRAS (pre-stated in the report log)')
    tk = st[st.took == 1]
    spec('X1', 'Single-type card takers: time beyond the forced reveal ~ illogical Cons card '
         '(hesitation as in-the-moment discrimination)', tk, lambda x: x,
         'netsecs ~ odd + ndrones + C(scenario) + run', 'odd', False, '+', 'log(1 + s beyond reveal)',
         'illogical Cons card', extra=1)
    p = d[(d.residual == 0) & d.preempt.notna() & d.prev_odd.notna()].copy()

    def mund(x):
        x = x.copy()
        x['prev_odd_pm'] = x.groupby('pid').prev_odd.transform('mean')
        return x
    f = 'preempt ~ prev_odd + prev_odd_pm + prev_nc1 + nc1 + ndrones + C(scenario) + run'
    spec('X2', 'Pre-emption after an illogical Cons card on the previous decision (within person; '
         'previous and current composition held)', p, mund, f, 'prev_odd', True, '+',
         'pre-empted the cards', 'previous Cons card illogical', extra=1)
    # permutation null for X2 (lagged label shuffled within person x previous composition)
    rng = np.random.default_rng(RNG_SEED + 1)
    obs = float(_fit(f, mund(p), True, robust=False).params['prev_odd'])
    keys = (p.pid + ':' + p.prev_nc1.astype(str)).values
    null = []
    for _ in range(300):
        q = p.copy()
        lab = q.prev_odd.values.copy()
        for k in np.unique(keys):
            ix = np.where(keys == k)[0]
            lab[ix] = rng.permutation(lab[ix])
        q['prev_odd'] = lab
        try:
            null.append(float(_fit(f, mund(q), True, robust=False).params['prev_odd']))
        except Exception:
            pass
    null = np.array(null)
    p_cal = float((np.abs(null - null.mean()) >= abs(obs - null.mean())).mean())
    record(variant_id='X2n', extra=1, description='Permutation null for X2 (lagged odd label shuffled '
           'within person x previous composition, 300 draws)', sample='S-all',
           outcome='pre-empted the cards', predictor='previous Cons card illogical',
           model='permutation of GEE log-OR', estimate=float(np.exp(obs)),
           ci_lo=float(np.exp(np.percentile(null, 2.5))), ci_hi=float(np.exp(np.percentile(null, 97.5))),
           estimate_scale='OR', p=p_cal, n_obs=len(p), n_people=p.pid.nunique(), expected_direction='+',
           notes='ci = null 2.5/97.5 percentiles (OR); null mean OR %.3f.' % np.exp(null.mean()))


def main():
    d = load()
    print('%d strategic decisions, %d people (P09 excluded); routes: %s'
          % (len(d), d.pid.nunique(), d.grp.value_counts().to_dict()))
    f1(d)
    f2(d)
    st = f3(d)
    f4(d)
    extras(d, st)
    cols = ['workstream', 'variant_id', 'extra', 'description', 'sample', 'outcome', 'predictor', 'model',
            'estimate', 'ci_lo', 'ci_hi', 'estimate_scale', 'p', 'n_obs', 'n_people', 'expected_direction',
            's1_same_direction', 'both_orders_same_direction', 'loo_sign_flip', 'notes']
    out = pd.DataFrame(SPECS)[cols]
    for c in ('estimate', 'ci_lo', 'ci_hi'):
        out[c] = out[c].astype(float).round(4)
    out['p'] = out['p'].astype(float).round(5)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print('\nwrote %d spec rows to %s' % (len(out), OUT))


if __name__ == '__main__':
    main()
