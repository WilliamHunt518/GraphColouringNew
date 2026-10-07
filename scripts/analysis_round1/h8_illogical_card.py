"""H8 -- how does an illogical Conservative card affect use of the strategic assistant, on the spot
and after the operator has (behaviourally) noticed it can happen?

    C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h8_illogical_card.py

No failures were injected (both epsilons 0). The "illogical card" is the Conservative card's ungated
15% top-up padding a drone type the mission does not use (scripts/check_conservative_topup.py).
It can occur only on a mission that leaves a type unused (here: 129 single-type and 3 two-type
decisions, 0 three-type), so every contrast below is made within single-type missions (trap 2).

Detection marker (pre-registered, operationalised here):
  the first decision, ordered over BOTH sessions (run, then position), at which the operator
    * was SHOWN an illogical Conservative card -- the card carries a type with trueAssets > 0 that
      the mission needs 0 of, AND the cards had loaded (`manualBeforeCardsLoaded` is False; a manual
      choice made during the 4-5 s reveal never saw the card), and
    * chose manual with zero of every unneeded type the card carried (from scratch, or by editing
      a card -- `editedFromStrategy`, with the `manual_allocation_edited` trail kept for audit).
  Variants: D_incl also counts pre-emptive manuals (cards not yet shown); D_edit is the strict
  "edited the unneeded type out / added-then-removed it" marker (2 events -- not testable alone).

Primary (pre-registered): within single-type missions, card uptake after vs before each person's
detection point, binomial GEE clustered on person, adjusted for position in session (`idx`) and
scenario; the detection decision itself excluded from both windows. Support = OR < 1 with its 95%
CI excluding 1.

THE SELECTION TRAP (why a null-calibrated version is reported next to it). The marker is defined by
the first post-reveal manual choice on an illogical card. So every earlier post-reveal illogical-card
decision of that person is, by construction, a card take (no manual choice ever kept the unneeded
type). The "before" window is therefore selected towards card-taking and the "after" window is not,
which manufactures a drop even if nothing changes. Two corrections are reported: (1) a null
simulation that keeps every person's own constant uptake rate, re-applies the marker, and refits the
same GEE -- the observed OR is compared with that null distribution; (2) the contrast restricted to
clean single-type cards, where the marker cannot fire, so neither window is selected.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

import h5_h8_common as H

pd.set_option('display.width', 160)
GEE, TERM = H.B.gee, H.B.term
N_SIM = 1000


def orci(t):
    return 'OR = %.2f [%.2f, %.2f], p = %.3f' % (np.exp(t['b']), np.exp(t['lo']), np.exp(t['hi']), t['p'])


def global_order(df):
    df = df.sort_values(['pid', 'run', 'idx']).copy()
    df['g'] = df.groupby('pid').cumcount()
    return df


def mark(df):
    """Flag decisions qualifying as a detection under each marker definition."""
    def touched(r):
        return any(any(a.get(c, 0) > 0 for c in r.unneeded) for a in r.edit_trail)
    man_odd = (df.odd == 1) & (df.choice == 'manual') & (df.chosen_unneeded == 0)
    df['q_main'] = (man_odd & (df.early == False)).astype(int)  # noqa: E712
    # placebo: first post-reveal manual on a CLEAN card (any composition) -- same selection
    # mechanics as q_main, but nothing illogical was there to notice
    df['q_placebo'] = ((df.odd == 0) & (df.manual == 1) & (df.early == False)).astype(int)  # noqa: E712
    df['q_incl'] = man_odd.astype(int)
    df['q_edit'] = (man_odd & ((df.editedFrom == 'Conservative')
                               | df.apply(touched, axis=1))).astype(int)
    return df


def windows(df, flag, single_only=True):
    """Per person: detection position g*, then after = g > g*, detection row dropped."""
    first = df[df[flag] == 1].groupby('pid').g.min()
    x = df[df.pid.isin(first.index)].copy()
    x['gstar'] = x.pid.map(first)
    x = x[x.g != x.gstar]
    x['after'] = (x.g > x.gstar).astype(int)
    if single_only:
        x = x[x.ncolours == 1]
    return x, first


def fit_after(x, formula='took ~ after + idx + C(scenario)'):
    if x.after.nunique() < 2 or x.took.nunique() < 2:
        return None
    try:
        return TERM(H.B._quietly(lambda: GEE(formula, x, binomial=True)), 'after')
    except Exception:
        return None


def describe_windows(x, label):
    b, a = x[x.after == 0], x[x.after == 1]
    contrib = x.groupby('pid').after.agg(['min', 'max'])
    both = int(((contrib['min'] == 0) & (contrib['max'] == 1)).sum())
    print('  %s: before %.1f%% took (n=%d), after %.1f%% (n=%d); people %d, with decisions on both '
          'sides %d' % (label, 100 * b.took.mean(), len(b), 100 * a.took.mean(), len(a),
                        x.pid.nunique(), both))
    print('     composition check: odd share before %.2f / after %.2f; run-2 share before %.2f / '
          'after %.2f; mean idx before %.1f / after %.1f'
          % (b.odd.mean(), a.odd.mean(), (b.run == 2).mean(), (a.run == 2).mean(),
             b.idx.mean(), a.idx.mean()))


def null_sim(df, flag='q_main', n_sim=N_SIM, seed=20261007, restrict=None):
    """Null: each person's choice on a few-colour mission is iid Bernoulli(own uptake rate); a
    simulated manual is pre-emptive with the person's own pre-emptive share. Marker re-applied,
    same GEE refitted. Returns the simulated log-ORs."""
    rng = np.random.default_rng(seed)
    few = df[df.ncolours < 3]
    p_take = few.groupby('pid').took.mean()
    man = few[few.manual == 1]
    glob_early = man.early.astype(float).mean()
    p_early = man.groupby('pid').early.apply(lambda s: s.astype(float).mean())
    sims = []
    for _ in range(n_sim):
        s = df.copy()
        fewmask = s.ncolours < 3
        pt = s.pid.map(p_take).fillna(0).values
        pe = s.pid.map(p_early).fillna(glob_early).values
        took = (rng.random(len(s)) < pt).astype(int)
        early = rng.random(len(s)) < pe
        s.loc[fewmask, 'took'] = took[fewmask.values]
        q = (fewmask & (s.odd == 1) & (s.took == 0)).values
        if flag == 'q_main':
            q = q & ~early
        s[flag] = q.astype(int)
        x, _ = windows(s, flag)
        if restrict is not None:
            x = restrict(x)
        t = fit_after(x)
        b = t['b'] if (t is not None and np.isfinite(t['b']) and abs(t['b']) < 10) else np.nan
        sims.append((b, rd(x)))
    return np.array(sims)


def rd(x):
    """Pooled risk difference in uptake, after minus before (robust to separation)."""
    if x.after.nunique() < 2:
        return np.nan
    return x[x.after == 1].took.mean() - x[x.after == 0].took.mean()


def calibrate(sims, obs_b, obs_rd, label):
    b, r = sims[:, 0], sims[:, 1]
    fb, fr = b[np.isfinite(b)], r[np.isfinite(r)]
    print('  %s: %d sims; GEE fits finite in %d (rest separated)' % (label, len(sims), len(fb)))
    print('    null log-OR mean %+.3f (OR %.2f), 95%% range [%+.3f, %+.3f]; observed %+.3f (OR %.2f); '
          'calibrated one-sided p = %.3f; bias-corrected OR = %.2f'
          % (fb.mean(), np.exp(fb.mean()), *np.percentile(fb, [2.5, 97.5]), obs_b, np.exp(obs_b),
             (fb <= obs_b).mean(), np.exp(obs_b - fb.mean())))
    print('    null risk difference mean %+.3f, 95%% range [%+.3f, %+.3f]; observed %+.3f; '
          'calibrated one-sided p = %.3f; bias-corrected RD = %+.3f'
          % (fr.mean(), *np.percentile(fr, [2.5, 97.5]), obs_rd, (fr <= obs_rd).mean(),
             obs_rd - fr.mean()))


def main():
    df = mark(global_order(H.decisions()))
    pv = H.versions()
    v12 = H.v112plus(pv)
    single = df[df.ncolours == 1]

    print('=' * 92)
    print('H8 · data')
    print('=' * 92)
    print('%d decisions, %d participants; single-type %d (illogical Conservative %d, clean %d)'
          % (len(df), df.pid.nunique(), len(single), single.odd.sum(), (single.odd == 0).sum()))
    o = df[df.odd == 1]
    print('illogical-card decisions: %d (single-type %d, two-type %d); Aggressive card ever padded '
          'an unused type: %d' % (len(o), (o.ncolours == 1).sum(), (o.ncolours == 2).sum(),
                                   df.aggr_odd.sum()))
    tab = o.assign(route=np.where(o.took == 1, o.choice,
                                  np.where(o.early == True, 'manual, before cards loaded',  # noqa
                                           np.where(o.editedFrom.notna(),
                                                    'manual, edited ' + o.editedFrom.fillna(''),
                                                    'manual, from scratch after reveal'))))
    print(tab.route.value_counts().to_string())
    print('manual choices on an illogical card that KEPT the unneeded type: %d'
          % ((o.manual == 1) & (o.chosen_unneeded > 0)).sum())
    for flag in ('q_main', 'q_incl', 'q_edit'):
        print('  marker %-7s qualifying decisions %3d, people with a detection point %2d'
              % (flag, df[flag].sum(), df[df[flag] == 1].pid.nunique()))
    det_people = set(df[df.q_main == 1].pid)
    first = df[df.q_main == 1].groupby('pid').agg(run=('run', 'first'), g=('g', 'min'))
    print('  detection in run 1: %d people, first in run 2: %d' % ((first.run == 1).sum(),
                                                                   (first.run == 2).sum()))
    rates = df.groupby('pid').took.mean()
    print('  overall uptake: detectors %.2f (n=%d) vs non-detectors %.2f (n=%d) -- detectors are '
          'by definition people who go manual' % (rates[rates.index.isin(det_people)].mean(),
                                                  len(det_people),
                                                  rates[~rates.index.isin(det_people)].mean(),
                                                  (~rates.index.isin(det_people)).sum()))

    print('\n' + '=' * 92)
    print('H8 · PRIMARY  single-type missions, uptake after vs before detection (GEE, idx + scenario)')
    print('=' * 92)
    x, _ = windows(df, 'q_main')
    describe_windows(x, 'ALL')
    prim = fit_after(x)
    print('  PRIMARY  ALL:    %s, n = %d decisions / %d people' % (orci(prim), len(x), x.pid.nunique()))
    xv, _ = windows(df[df.pid.isin(v12)], 'q_main')
    pv12 = fit_after(xv)
    print('  PRIMARY  v1.12+: %s, n = %d decisions / %d people' % (orci(pv12), len(xv), xv.pid.nunique()))
    verdict = 'SUPPORTED' if np.exp(prim['hi']) < 1 else 'NOT SUPPORTED'
    print('  verdict as pre-registered (OR<1, CI excludes 1): %s' % verdict)

    print('\nSelection-trap check: how many BEFORE-window decisions are post-reveal illogical cards '
          '(forced to be card takes by the marker definition)?')
    b = x[x.after == 0]
    forced = b[(b.odd == 1) & ~((b.manual == 1) & (b.early == True))]  # noqa: E712
    print('  %d of %d before-window decisions; their uptake %.0f%% (by construction 100%% unless '
          'pre-emptive)' % (len(forced), len(b), 100 * forced.took.mean() if len(forced) else np.nan))

    print('\n(1) Null-calibrated primary (each person constant uptake; marker re-applied; %d sims)'
          % N_SIM)
    calibrate(null_sim(df), prim['b'], rd(x), 'ALL')
    calibrate(null_sim(df[df.pid.isin(v12)], n_sim=N_SIM // 2), pv12['b'], rd(xv), 'v1.12+')

    print('\n(2) Clean single-type cards only (the marker cannot fire on them, so no window is '
          'selected)')
    xc = x[x.odd == 0]
    describe_windows(xc, 'clean')
    both = (xc.groupby('pid').after.nunique() == 2).sum()
    tc = fit_after(xc) if both else None
    print('  %s' % (orci(tc) if tc else 'NOT ESTIMABLE: %d people have clean single-type decisions '
                    'on both sides of their detection point' % both))

    print('\n(3) Further specifications')
    for lab, xx, form in (
            ('+ run', x, 'took ~ after + idx + C(scenario) + C(run)'),
            ('residual missions excluded', x[x.residual == 0], 'took ~ after + idx + C(scenario)'),
            ('within-person (Mundlak: + person-mean of after)',
             x.assign(after_pm=x.groupby('pid').after.transform('mean')),
             'took ~ after + after_pm + idx + C(scenario)'),
            ('people with decisions on both sides only',
             x[x.groupby('pid').after.transform('nunique') == 2], 'took ~ after + idx + C(scenario)')):
        t = fit_after(xx, form)
        print('  %-48s %s, n=%d/%d' % (lab, orci(t) if t else 'n/a', len(xx), xx.pid.nunique()))
    xi, _ = windows(df, 'q_incl')
    ti = fit_after(xi)
    print('  %-48s %s, n=%d/%d' % ('marker D_incl (pre-emptive manuals count)', orci(ti), len(xi),
                                    xi.pid.nunique()))
    calibrate(null_sim(df, flag='q_incl', n_sim=N_SIM // 2), ti['b'], rd(xi), 'D_incl null')
    xp, _ = windows(df, 'q_placebo')
    tp = fit_after(xp)
    print('  %-48s %s, n=%d/%d; before %.1f%% after %.1f%%'
          % ('PLACEBO marker: 1st post-reveal manual, CLEAN card', orci(tp) if tp else 'n/a', len(xp),
             xp.pid.nunique(), 100 * xp[xp.after == 0].took.mean(), 100 * xp[xp.after == 1].took.mean()))
    xe, fe = windows(df, 'q_edit')
    print('  marker D_edit: %d people (%s) -- NOT TESTABLE' % (len(fe), ', '.join(fe.index)))
    # Session-specific detection point (restart the clock each session)
    rows = []
    for (pid, run), g in df.groupby(['pid', 'run']):
        d = g[g.q_main == 1].idx.min()
        if pd.isna(d):
            continue
        gg = g[(g.idx != d) & (g.ncolours == 1)].copy()
        gg['after'] = (gg.idx > d).astype(int)
        rows.append(gg)
    xs = pd.concat(rows)
    ts = fit_after(xs, 'took ~ after + idx + C(scenario) + C(run)')
    print('  %-48s %s, n=%d/%d' % ('per-session detection point (+run)', orci(ts), len(xs),
                                   xs.pid.nunique()))

    print('\n' + '=' * 92)
    print('H8 · SECONDARY (exploratory)')
    print('=' * 92)
    print('\n(a) On the spot -- single-type missions, illogical vs clean Conservative card')
    s = single.copy()
    s['aggr'] = (s.choice == 'aggressive').astype(int)
    s['cons'] = (s.choice == 'conservative').astype(int)
    s['pre'] = ((s.manual == 1) & (s.early == True)).astype(int)  # noqa: E712
    s['post_manual'] = ((s.manual == 1) & (s.early != True)).astype(int)  # noqa: E712
    for y, lab in (('took', 'took a card'), ('aggr', 'took Aggressive'), ('cons', 'took Conservative'),
                   ('post_manual', 'manual AFTER the cards loaded'),
                   ('pre', 'manual BEFORE cards loaded (negative control)')):
        t = TERM(H.B._quietly(lambda: GEE('%s ~ odd + idx + C(scenario) + C(run)' % y, s,
                                          binomial=True)), 'odd')
        print('  %-46s clean %5.1f%%  illogical %5.1f%%   %s'
              % (lab, 100 * s[s.odd == 0][y].mean(), 100 * s[s.odd == 1][y].mean(), orci(t)))
    c = s[s.took == 1]
    t = TERM(H.B._quietly(lambda: GEE('cons ~ odd + idx + C(scenario) + C(run)', c, binomial=True)),
             'odd')
    print('  %-46s clean %5.1f%%  illogical %5.1f%%   %s'
          % ('Conservative | a card was taken', 100 * c[c.odd == 0].cons.mean(),
             100 * c[c.odd == 1].cons.mean(), orci(t)))
    print('  n: clean %d, illogical %d single-type decisions; clean cards come from %d people'
          % ((s.odd == 0).sum(), (s.odd == 1).sum(), s[s.odd == 0].pid.nunique()))
    sv = s[s.pid.isin(v12)]
    t = TERM(H.B._quietly(lambda: GEE('took ~ odd + idx + C(scenario) + C(run)', sv, binomial=True)),
             'odd')
    print('  v1.12+ took a card: %s (n=%d)' % (orci(t), len(sv)))

    print('\n(b) After detection: Aggressive instead, or out of the card system?')
    x2 = x.copy()
    x2['aggr'] = (x2.choice == 'aggressive').astype(int)
    x2['cons'] = (x2.choice == 'conservative').astype(int)
    for y in ('aggr', 'cons', 'manual'):
        t = fit_after(x2.assign(took=x2[y]))
        print('  %-8s before %5.1f%%  after %5.1f%%   %s (naive; same selection bias as primary)'
              % (y, 100 * x2[x2.after == 0][y].mean(), 100 * x2[x2.after == 1][y].mean(), orci(t)))
    cc = x2[x2.took == 1]
    t = fit_after(cc.assign(took=cc.cons))
    print('  Conservative share of card takes: before %.1f%% (n=%d), after %.1f%% (n=%d); %s'
          % (100 * cc[cc.after == 0].cons.mean(), (cc.after == 0).sum(),
             100 * cc[cc.after == 1].cons.mean(), (cc.after == 1).sum(), orci(t) if t else 'n/a'))
    ca = cc[cc.odd == 1]
    print('  ...on illogical cards only: before %.1f%% (n=%d), after %.1f%% (n=%d)'
          % (100 * ca[ca.after == 0].cons.mean(), (ca.after == 0).sum(),
             100 * ca[ca.after == 1].cons.mean(), (ca.after == 1).sum()))

    od = single[(single.odd == 1) & (single.took == 1)]
    print('  card takes on illogical single-type cards, Aggressive share: eventual detectors %.0f%% '
          '(n=%d), never-detectors %.0f%% (n=%d)'
          % (100 * (od[od.pid.isin(det_people)].choice == 'aggressive').mean(),
             od.pid.isin(det_people).sum(),
             100 * (od[~od.pid.isin(det_people)].choice == 'aggressive').mean(),
             (~od.pid.isin(det_people)).sum()))

    print('\n(c) Is detection earlier in session 2 than session 1? (per-session marker)')
    per = []
    for (pid, run), g in df.groupby(['pid', 'run']):
        g = g.sort_values('idx')
        shown = g[(g.odd == 1) & ~((g.manual == 1) & (g.early == True))]  # noqa: E712
        d = g[g.q_main == 1]
        per.append(dict(pid=pid, run=run, scenario=g.scenario.iloc[0], shown=len(shown),
                        detected=int(len(d) > 0),
                        exposures=int((shown.idx < d.idx.min()).sum()) if len(d) else np.nan,
                        secs=float(d.elapsed.min()) if len(d) else np.nan,
                        dec_idx=float(d.idx.min()) if len(d) else np.nan))
    per = pd.DataFrame(per)
    for run in (1, 2):
        r = per[per.run == run]
        ex = r[r.shown > 0]
        print('  run %d: shown >=1 post-reveal illogical card %d sessions; detected in %d (%.0f%% of '
              'exposed); median exposures before detection %.1f, median time %.0f s'
              % (run, len(ex), ex.detected.sum(), 100 * ex.detected.mean(), r.exposures.median(),
                 r.secs.median()))
        print('         by scenario: %s' % ex.groupby('scenario').detected.agg(['sum', 'size']).to_dict())
    w = per.pivot(index='pid', columns='run', values='exposures').dropna()
    if len(w) >= 3:
        st = stats.wilcoxon(w[1], w[2]) if (w[1] != w[2]).any() else None
        print('  detected in both runs: %d people; exposures-before-detection run1 median %.1f vs '
              'run2 %.1f; Wilcoxon p = %s' % (len(w), w[1].median(), w[2].median(),
                                              '%.3f' % st.pvalue if st else 'n/a'))
    ws = per.pivot(index='pid', columns='run', values='secs').dropna()
    if len(ws) >= 3:
        st = stats.wilcoxon(ws[1], ws[2])
        print('  ...time to detection run1 median %.0f s vs run2 %.0f s; Wilcoxon p = %.3f'
              % (ws[1].median(), ws[2].median(), st.pvalue))
    ex1 = per[(per.shown > 0)].pivot(index='pid', columns='run', values='detected').dropna()
    print('  exposed in both runs: %d people; detected s1 only %d, s2 only %d, both %d, neither %d'
          % (len(ex1), ((ex1[1] == 1) & (ex1[2] == 0)).sum(), ((ex1[1] == 0) & (ex1[2] == 1)).sum(),
             ((ex1[1] == 1) & (ex1[2] == 1)).sum(), ((ex1[1] == 0) & (ex1[2] == 0)).sum()))

    print('\n(d) Link to H5: do people who noticed show a larger strategic-trust drop?')
    sess = H.sessions()
    tr = sess.pivot(index='pid', columns='run', values='trust_s')
    dtr = (tr[2] - tr[1]).rename('d')
    order = sess[sess.run == 1].set_index('pid').scenario.map({'strategic': 'SF', 'tactical': 'TF'})
    q = H.B.load_quotes()
    coded = set(q['participants'])
    over = {i.split('/')[0] for i in H.OVERALLOC}
    first_run = df[df.q_main == 1].groupby('pid').run.min()
    det_s2 = set(df[(df.q_main == 1) & (df.run == 2)].pid)

    def mw(mask, lab, pool=dtr.index):
        a, b = dtr[pool][mask[pool]], dtr[pool][~mask[pool]]
        if len(a) < 2 or len(b) < 2:
            print('  %-58s n too small' % lab)
            return
        u = stats.mannwhitneyu(a, b, alternative='two-sided')
        rbc = 2 * u.statistic / (len(a) * len(b)) - 1
        print('  %-58s yes mean %+.2f (n=%d) vs no %+.2f (n=%d); MWU p=%.3f, rank-biserial %+.2f'
              % (lab, a.mean(), len(a), b.mean(), len(b), u.pvalue, rbc))

    idx_ = pd.Series(dtr.index, index=dtr.index)
    mw(idx_.isin(det_people), 'behavioural detector (ever)')
    mw(idx_.isin(first_run[first_run == 2].index), 'first detection in run 2 (between the two surveys)')
    mw(idx_.isin(det_s2), 'any detection in run 2')
    cpool = dtr.index[dtr.index.isin(coded)]
    mw(idx_.isin(over), 'OVERALLOC debrief mention (coded debriefs only)', pool=cpool)
    # within order (the drop is concentrated in the tactical-first group, see H5)
    for o_ in ('SF', 'TF'):
        pool = dtr.index[order.reindex(dtr.index) == o_]
        mw(idx_.isin(det_s2), 'any detection in run 2, order %s only' % o_, pool=pool)
    nd2 = df[df.run == 2].groupby('pid').q_main.sum().reindex(dtr.index).fillna(0)
    print('  # run-2 detection-qualifying decisions vs change in trust_s: '
          + H.fmt_rho(H.spearman_ci(nd2.values, dtr.values)))
    r, p, n = H.partial_spearman(nd2.values, dtr.values,
                                 pd.get_dummies(order.reindex(dtr.index), drop_first=True))
    print('    partial on order: rho=%+.3f p=%.3f n=%d' % (r, p, n))
    tf = (order.reindex(dtr.index) == 'TF').values
    print('    within TF only: ' + H.fmt_rho(H.spearman_ci(nd2.values[tf], dtr.values[tf])))
    pool = dtr.index[dtr.index.isin(coded)]
    for o_ in ('SF', 'TF'):
        pl = pool[order.reindex(pool) == o_]
        mw(idx_.isin(over), 'OVERALLOC mention, coded, order %s only' % o_, pool=pl)
    odd1 = df[df.run == 1].groupby('pid').odd.sum().reindex(dtr.index).fillna(0)
    odd2 = df[df.run == 2].groupby('pid').odd.sum().reindex(dtr.index).fillna(0)
    print('  change in illogical cards seen (run2-run1) vs change in trust_s: '
          + H.fmt_rho(H.spearman_ci((odd2 - odd1).values, dtr.values)))
    for o_ in ('SF', 'TF'):
        m = (order.reindex(dtr.index) == o_).values
        print('    within order %s: ' % o_
              + H.fmt_rho(H.spearman_ci((odd2 - odd1).values[m], dtr.values[m])))
    r, p, n = H.partial_spearman((odd2 - odd1).values, dtr.values,
                                 pd.get_dummies(order.reindex(dtr.index), drop_first=True))
    print('    partial on order: rho=%+.3f p=%.3f n=%d' % (r, p, n))

    # H5 x H8 cross-check: within the tactical-first group, are the H5 predictor (session-1 card
    # missions failed) and run-2 detection the same signal?
    import h5_trust_drop as T5
    import statsmodels.formula.api as smf
    P5 = T5.build_people(H.decisions(), sess)
    P5['det2'] = P5.pid.isin(det_s2).astype(int)
    tf5 = P5[P5.order == 'TF']
    print('  TF group: s1 card failures, run-2 detectors %.2f (n=%d) vs not %.2f (n=%d)'
          % (tf5[tf5.det2 == 1].card_bad_1.mean(), tf5.det2.sum(),
             tf5[tf5.det2 == 0].card_bad_1.mean(), (tf5.det2 == 0).sum()))
    mm = smf.ols('d_trust_s ~ card_bad_1 + det2', tf5).fit(cov_type='HC3')
    print('  TF group OLS d_trust_s ~ card_bad_1 + det2 (HC3): card_bad_1 b=%+.2f p=%.3f; det2 b=%+.2f '
          'p=%.3f; n=%d' % (mm.params['card_bad_1'], mm.pvalues['card_bad_1'], mm.params['det2'],
                            mm.pvalues['det2'], int(mm.nobs)))

    print('\n(e) Validating the behavioural marker against the debriefs (coded debriefs only, n=%d)'
          % len(coded))
    cd = sorted(p for p in coded if p in dtr.index)
    a = sum(p in det_people and p in over for p in cd)
    b_ = sum(p in det_people and p not in over for p in cd)
    c_ = sum(p not in det_people and p in over for p in cd)
    d_ = sum(p not in det_people and p not in over for p in cd)
    orr, pf = stats.fisher_exact([[a, b_], [c_, d_]])
    print('  detector & mentions %d | detector & silent %d | non-detector & mentions %d | '
          'non-detector & silent %d' % (a, b_, c_, d_))
    print('  mention rate: detectors %.0f%%, non-detectors %.0f%%; Fisher OR=%.2f p=%.3f'
          % (100 * a / max(a + b_, 1), 100 * c_ / max(c_ + d_, 1), orr, pf))
    print('  OVERALLOC holders and their marker status: ' + ', '.join(
        '%s:%s' % (p, 'det' if p in det_people else '-') for p in sorted(over)))
    # Did the people who describe it in debrief actually see illogical cards?
    seen = df.groupby('pid').odd.sum()
    print('  illogical cards seen: OVERALLOC holders median %.0f, other coded %.0f'
          % (seen[seen.index.isin(over)].median(), seen[seen.index.isin(set(cd) - over)].median()))

    print('\nPer-person detection table (for audit):')
    tab = per.pivot(index='pid', columns='run', values=['shown', 'detected', 'exposures'])
    tab.columns = ['%s_%d' % c for c in tab.columns]
    tab['d_trust_s'] = dtr
    tab['overalloc'] = tab.index.isin(over).astype(int)
    tab['coded'] = tab.index.isin(coded).astype(int)
    print(tab.round(2).to_string())


if __name__ == '__main__':
    main()
