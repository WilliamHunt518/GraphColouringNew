"""H6 -- is the tactical assistant trusted more in what people SAY, and does that depend on scale?

Inputs
  docs/analysis/round1/h6_codes.csv     this coder's per-participant codes (codebook: h6_codebook.md),
                                         written before the existing stance codes were opened
  Results/Narration/*_s1/quotes.json    the existing single-coder stance codes (read-only)
  Results/Participants/P*.json           behaviour, via the builder's loaders (read-only)

Primary test (HYPOTHESES_ROUND1.md H6): among participants who state a preference
(pref in {tactical, strategic}), share preferring tactical vs 0.5, exact two-sided binomial (sign)
test. Support = significant preference for tactical AND Cohen's kappa >= .6 against the existing
stance codes.

Aggregating the existing codes to one per person. They are per QUOTE and a person can carry several
(the synthesis page's SR.stance counts the set of stances on each person's `agent_comparison`
quotes, so it sums to more than n). The reduction below was fixed after seeing that format and
before any agreement was computed; it mirrors this codebook's rule 1 (a clear ranking beats
conditionality):  exactly one tier preference present -> that tier; else distrusts_both /
prefers_neither -> neither; else trusts_both -> both; else conditional; else none.
Alternatives are reported alongside (all quote themes; conditional-first precedence).

Run from the repo root:  C:/Users/Work/anaconda3/python.exe scripts/analysis_round1/h6_stated_preference.py
"""
import glob
import json
import sys
import warnings
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import cohen_kappa_score

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_findings_synthesis import load_decisions, load_people  # noqa: E402
from h2_verification_cost import load as load_tactical  # noqa: E402

warnings.filterwarnings('ignore')
CODES = BASE / 'docs' / 'analysis' / 'round1' / 'h6_codes.csv'
MAP = {'prefers_tactical': 'tactical', 'prefers_strategic': 'strategic', 'trusts_both': 'both',
       'distrusts_both': 'neither', 'prefers_neither': 'neither', 'conditional': 'conditional'}


def reduce(stances, conditional_first=False):
    s = {MAP[x] for x in stances if x in MAP}
    tiers = s & {'tactical', 'strategic'}
    if conditional_first and 'conditional' in s:
        return 'conditional'
    if len(tiers) == 1:
        return tiers.pop()
    if 'neither' in s:
        return 'neither'
    if 'both' in s:
        return 'both'
    if 'conditional' in s:
        return 'conditional'
    return 'none'


def existing():
    out = {}
    for path in sorted(glob.glob(str(BASE / 'Results' / 'Narration' / '*_s1' / 'quotes.json'))):
        d = json.loads(Path(path).read_text(encoding='utf-8'))
        qs = d.get('quotes', [])
        out[d['participantId']] = dict(
            ac=[q['stance'] for q in qs if q['theme'] == 'agent_comparison' and q.get('stance')],
            all=[q['stance'] for q in qs if q.get('stance')])
    return out


def sign_test(codes, label):
    t = int((codes.pref == 'tactical').sum())
    s = int((codes.pref == 'strategic').sum())
    r = stats.binomtest(t, t + s, 0.5)
    ci = r.proportion_ci(method='exact')
    print('%s: tactical %d vs strategic %d of %d stating a preference (%d coded): share %.3f [%.3f, %.3f], exact p=%.4f'
          % (label, t, s, t + s, len(codes), t / (t + s), ci.low, ci.high, r.pvalue))
    return dict(t=t, s=s, p=r.pvalue, share=t / (t + s), lo=ci.low, hi=ci.high)


def kappa_block(codes, ex):
    print('\n=== Agreement with the existing stance codes ===')
    pids = sorted(set(codes.index) & set(ex))
    print('participants coded by both: %d; only here: %s' % (len(pids), sorted(set(codes.index) - set(ex))))
    mine = codes.loc[pids, 'pref']
    mine_c = codes.loc[pids].apply(lambda r: 'conditional' if r.cond != 'none' else r.pref, axis=1)
    variants = [
        ('PRIMARY: agent_comparison quotes, ranking-first vs my pref', mine, [reduce(ex[p]['ac']) for p in pids]),
        ('all quote themes, ranking-first vs my pref', mine, [reduce(ex[p]['all']) for p in pids]),
        ('agent_comparison, conditional-first vs my secondary mapping (cond!=none -> conditional)', mine_c,
         [reduce(ex[p]['ac'], True) for p in pids]),
        ('all themes, conditional-first vs my secondary mapping', mine_c, [reduce(ex[p]['all'], True) for p in pids]),
    ]
    out = {}
    for label, a, b in variants:
        a = list(a)
        k = cohen_kappa_score(a, b)
        agree = np.mean([x == y for x, y in zip(a, b)])
        # bootstrap CI over participants
        rng = np.random.default_rng(42)
        ks = []
        for _ in range(4000):
            i = rng.integers(0, len(a), len(a))
            aa, bb = [a[j] for j in i], [b[j] for j in i]
            if len(set(aa) | set(bb)) > 1:
                ks.append(cohen_kappa_score(aa, bb))
        lo, hi = np.percentile(ks, [2.5, 97.5])
        print('%s: kappa=%.3f [%.3f, %.3f] (bootstrap), raw agreement %.3f, n=%d' % (label, k, lo, hi, agree, len(a)))
        out[label] = (k, lo, hi, agree)
        if label.startswith('PRIMARY'):
            print(pd.crosstab(pd.Series(a, name='this coder'), pd.Series(b, name='existing')).to_string())
            print('disagreements:', [(p, x, y) for p, x, y in zip(pids, a, b) if x != y])
    # set-membership: is my pref among the person's existing agent_comparison stances?
    member = [codes.loc[p, 'pref'] in {MAP.get(x) for x in ex[p]['ac']} for p in pids]
    print('my pref is one of the person\'s existing agent_comparison stances for %d of %d' % (sum(member), len(pids)))
    # tactical-vs-not binary
    a = [codes.loc[p, 'pref'] == 'tactical' for p in pids]
    b = [reduce(ex[p]['ac']) == 'tactical' for p in pids]
    print('binary "prefers tactical" kappa=%.3f (agreement %.3f)' % (cohen_kappa_score(a, b), np.mean([x == y for x, y in zip(a, b)])))
    ex_codes = pd.DataFrame({'pref': [reduce(ex[p]['ac']) for p in pids]}, index=pids)
    sign_test(ex_codes, 'existing codes (reduced, primary aggregation)')
    return out


def behaviour():
    dec = load_decisions()
    sess, _ = load_people()
    tac, _, _ = load_tactical()
    pp = pd.DataFrame(index=sorted(dec.pid.unique()))
    g = dec[dec.residual == 0]
    by = g.groupby(['pid', 'ncolours']).took.mean().unstack()
    pp['took'] = dec.groupby('pid').took.mean()
    pp['took_1type'] = by.get(1)
    pp['took_3type'] = by.get(3)
    pp['comp_effect'] = pp.took_3type - pp.took_1type          # strategic: complex minus simple
    med = tac['size'].median()
    tb = tac.assign(big=(tac['size'] > med).astype(int)).groupby(['pid', 'big']).consulted.mean().unstack()
    pp['tac_size_effect'] = tb[1] - tb[0]                      # tactical: big minus small
    pp['accept'] = tac.groupby('pid').keep.mean()
    pp['consult'] = tac.groupby('pid').consulted.mean()
    s = pd.DataFrame(sess)
    pp['trust_s'] = s.groupby('pid').trust_s.mean()
    pp['trust_t'] = s.groupby('pid').trust_t.mean()
    pp['trust_gap'] = pp.trust_t - pp.trust_s
    return pp


def mwu(a, b):
    a, b = a.dropna(), b.dropna()
    if len(a) < 2 or len(b) < 2:
        return 'n too small (%d, %d)' % (len(a), len(b))
    u = stats.mannwhitneyu(a, b)
    rbc = 1 - 2 * u.statistic / (len(a) * len(b))
    return 'medians %.3f (n=%d) vs %.3f (n=%d), MWU p=%.4f, rank-biserial %.2f' % (a.median(), len(a), b.median(), len(b), u.pvalue, -rbc)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    codes = pd.read_csv(CODES, dtype=str).fillna('').set_index('pid')
    codes = codes[codes.index != 'P09']
    print('coded participants: %d' % len(codes))
    print('pref:', dict(Counter(codes.pref)))
    print('cond:', dict(Counter(codes.cond)), '| cond_load=1:', int((codes.cond_load == '1').sum()),
          '| cond_tier:', dict(Counter(codes[codes.cond != 'none'].cond_tier)))
    print('confidence:', dict(Counter(codes.confidence)), '| led:', int((codes.led == '1').sum()))
    for r in ('r_speed', 'r_accuracy', 'r_cantcheck', 'r_visible_err', 'r_autonomy', 'r_other'):
        v = codes[r]
        print('%-14s any %2d | about strategic %2d | about tactical %2d'
              % (r, (v != '').sum(), v.str.contains('S').sum(), v.str.contains('T').sum()))

    print('\n=== PRIMARY ===')
    prim = sign_test(codes, 'all 33')
    new = set(load_tactical()[2])
    sens = sign_test(codes[codes.index.isin(new)], 'v1.12+ cohort')
    hi = codes[codes.confidence != 'low']
    sign_test(hi, 'robustness: low-confidence codes dropped')
    sign_test(codes[codes.led != '1'], 'robustness: led statements dropped')
    sign_test(codes[codes.source != 'interview'], 'robustness: recorded debrief available (verbatim)')
    sign_test(codes[codes.source == 'interview'], 'robustness: written interview notes only (paraphrase)')
    ex = existing()
    kap = kappa_block(codes, ex)
    k = kap[[x for x in kap if x.startswith('PRIMARY')][0]][0]
    verdict = 'SUPPORTED' if (prim['p'] < .05 and prim['share'] > .5 and k >= .6) else 'NOT SUPPORTED'
    print('\nVERDICT (sign test p<.05 toward tactical AND kappa>=.6): p=%.4f, kappa=%.3f -> %s' % (prim['p'], k, verdict))

    print('\n=== SECONDARY (exploratory) ===')
    pp = behaviour().join(codes)
    print('-- validity: stated preference vs questionnaire trust gap (T - S)')
    print('tactical-pref vs strategic-pref:', mwu(pp[pp.pref == 'tactical'].trust_gap, pp[pp.pref == 'strategic'].trust_gap))
    print('people with trust gap > 0: tactical-pref %d/%d, strategic-pref %d/%d'
          % ((pp[pp.pref == 'tactical'].trust_gap > 0).sum(), (pp.pref == 'tactical').sum(),
             (pp[pp.pref == 'strategic'].trust_gap > 0).sum(), (pp.pref == 'strategic').sum()))
    print('questionnaire: trust gap > 0 for %d, < 0 for %d, = 0 for %d of %d; scale-based sign test p=%.4f'
          % ((pp.trust_gap > 0).sum(), (pp.trust_gap < 0).sum(), (pp.trust_gap == 0).sum(), pp.trust_gap.notna().sum(),
             stats.binomtest(int((pp.trust_gap > 0).sum()), int((pp.trust_gap != 0).sum()), .5).pvalue))
    print('stated "both"/"neither"/"conditional"/"none" people, trust gap median: %.3f (n=%d)'
          % (pp[~pp.pref.isin(['tactical', 'strategic'])].trust_gap.median(), (~pp.pref.isin(['tactical', 'strategic'])).sum()))
    print('-- stated preference vs behaviour')
    for col in ('took', 'accept', 'consult'):
        print('%s: tactical-pref vs strategic-pref: %s' % (col, mwu(pp[pp.pref == 'tactical'][col], pp[pp.pref == 'strategic'][col])))
    pp['beh_gap'] = pp.accept - pp.took
    print('accept - took: tactical-pref vs strategic-pref:', mwu(pp[pp.pref == 'tactical'].beh_gap, pp[pp.pref == 'strategic'].beh_gap))
    print('-- stated scale-conditionality vs actual composition effect')
    cx = pp.cond == 'more_assist_when_complex'
    print('strategic comp effect (took 3-type - 1-type): overall median %.3f, >0 for %d of %d'
          % (pp.comp_effect.median(), (pp.comp_effect > 0).sum(), pp.comp_effect.notna().sum()))
    print('  says more assist when complex vs rest:', mwu(pp[cx].comp_effect, pp[~cx].comp_effect))
    t = cx & pp.cond_tier.isin(['strategic', 'both', 'unspecified'])
    print('  (rule about strategic/both/unspecified) vs no rule:', mwu(pp[t].comp_effect, pp[pp.cond == 'none'].comp_effect))
    print('tactical size effect (consult big - small): overall median %.3f, >0 for %d of %d'
          % (pp.tac_size_effect.median(), (pp.tac_size_effect > 0).sum(), pp.tac_size_effect.notna().sum()))
    print('  says more assist when complex vs rest:', mwu(pp[cx].tac_size_effect, pp[~cx].tac_size_effect))
    t = cx & pp.cond_tier.isin(['tactical', 'both', 'unspecified'])
    print('  (rule about tactical/both/unspecified) vs no rule:', mwu(pp[t].tac_size_effect, pp[pp.cond == 'none'].tac_size_effect))
    print('  more_assist_when_simple people:', pp[pp.cond == 'more_assist_when_simple'][['cond_tier', 'comp_effect', 'tac_size_effect']].to_string())
    print('-- where the two streams disagree (stated tier vs scale and behaviour)')
    cols = ['pref', 'trust_gap', 'took', 'accept']
    dis = pp[((pp.pref == 'tactical') & (pp.trust_gap < 0)) | ((pp.pref == 'strategic') & (pp.trust_gap > 0))]
    print(dis[cols].round(3).to_string())


if __name__ == '__main__':
    main()
