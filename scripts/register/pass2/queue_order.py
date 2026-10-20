#!/usr/bin/env python3
"""Pass 5: would a queue-ordering assistant change anything? (the researcher's note on q-new-jobs: P27 and P32 asked
for an agent that orders the waiting missions or says what to open next; P27's rule is "the ones that can be done
first, then by criticality").

    python scripts/register/pass2/queue_order.py      # adds `queueOrder` to docs/analysis/register/pass2/load.json

For every strategic decision with two or more missions waiting (the same decisions as load.py's choice model):
  - what was opened: the oldest waiting, the most critical (category A..E, the penalty rate the operator sees), one the
    reserve could cover at that moment (available drones of every colour >= the mission's primary need), and the top
    of P27's order (coverable first, then most critical, then oldest); each against chance (1 / number waiting);
  - a conditional logit over the waiting set with oldest, newest, size, criticality (categories above the set's
    mean) and coverable, person-bootstrapped (400 draws);
  - how often the oldest waiting mission could not be covered (P32: "I know I haven't got enough ... it's kind of
    annoying that it's there").
The queue's "Sort: Score" toggle (PrimaryDisplay.tsx) is UI state that is not logged, so its use cannot be measured.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import load as LD  # noqa: E402

r = LD.r
CATS = 'ABCDE'
COLS = ('Blue', 'Red', 'Green')


def mission_info():
    """{(pid, run): {mission: dict(cat, need{colour}), '_res': [(t, available reserve)]}} from the raw logs."""
    import glob
    out = {}
    for path in sorted(glob.glob(str(LD.x2.PARTS / 'P*.json'))):
        pid = Path(path).stem
        if pid in LD.x2.EXCLUDE:
            continue
        log = json.loads(Path(path).read_text(encoding='utf-8'))
        for run, evs in enumerate(log['sessions'], start=1):
            M, res = {}, []
            for e in evs:
                if e.get('reserveStateAvailable') is not None and 'elapsed' in e:
                    res.append((e['elapsed'], e['reserveStateAvailable']))
                if e['type'] == 'mission_arrived':
                    need = {c: 0 for c in COLS}
                    for comp in (e.get('taskCompositions') or {}).values():
                        for c in COLS:
                            need[c] += (comp.get('primary') or {}).get(c, 0)
                    M[e['missionId']] = dict(cat=CATS.index(e['category']) if e.get('category') in CATS else np.nan, need=need)
            M['_res'] = res
            out[(pid, run)] = M
    return out


def reserve_at(res, t):
    best = None
    for tt, rv in res:
        if tt <= t + 1e-6:
            best = rv
        else:
            break
    return best


def decisions():
    """(D, C): one row per decision with 2+ waiting (what was opened, against chance), and one row per waiting
    mission (the conditional-logit rows)."""
    S, T, logs, said, M = LD.load()
    info = mission_info()
    rows, dec = [], []
    for di, rr in enumerate(S.itertuples()):
        w = rr.waiting
        ids = [m for _, m, _, _ in w]
        if rr.missionId not in ids or len(w) < 2:
            continue
        I = info.get((rr.pid, rr.run)) or {}
        rv = reserve_at(I.get('_res', []), rr.t - 0.5)       # just before the decision (the choice itself moves the reserve)
        if rv is None:
            continue
        cats = np.array([I.get(m, {}).get('cat', np.nan) for m in ids], float)
        if np.isnan(cats).any():
            continue
        cover = np.array([int(all(rv.get(c, 0) >= I[m]['need'][c] for c in COLS)) for m in ids])
        nd = np.array([x[2] for x in w], float)
        k = len(w)
        pick = ids.index(rr.missionId)
        # P27's order: coverable first, then most critical, then oldest (list order is oldest first)
        p27 = sorted(range(k), key=lambda j: (-cover[j], -cats[j], j))[0]
        topc = cats.max()
        dec.append(dict(pid=rr.pid, k=k, long=int(rr.st_queued > LD.VISIBLE), oldest=int(pick == 0),
                        crit=int(cats[pick] == topc), chCrit=(cats == topc).mean(), critUnique=int((cats == topc).sum() == 1),
                        cover=cover[pick], chCover=cover.mean(), anyUncover=int(cover.min() == 0),
                        p27=int(pick == p27), oldestUncover=int(cover[0] == 0), p27isOldest=int(p27 == 0)))
        for j, m in enumerate(ids):
            rows.append(dict(dec=di, pid=rr.pid, y=int(j == pick), oldest=int(j == 0), newest=int(j == k - 1),
                             size=(nd[j] - nd.mean()) / 3.0, crit=cats[j] - cats.mean(), cover=cover[j]))
    return pd.DataFrame(dec), pd.DataFrame(rows)


def main():
    rng = np.random.default_rng(LD.SEED + 77)
    D, C = decisions()
    out = dict(decisions=len(D), people=int(D.pid.nunique()))

    def share(col, ch=None, sub=None):
        X = D if sub is None else D[sub]
        o = dict(n=len(X), obs=r(X[col].mean()))
        if ch is not None:
            o['chance'] = r((X[ch] if isinstance(ch, str) else 1 / X.k).mean())
        return o
    out['opened'] = dict(
        oldest=share('oldest', 0),
        mostCritical=share('crit', 'chCrit'),
        mostCriticalWhenUnique=share('crit', 'chCrit', D.critUnique == 1),
        coverable=share('cover', 'chCover', D.anyUncover == 1),
        p27=share('p27', 0),
        p27notOldest=share('p27', 0, D.p27isOldest == 0),
    )
    out['oldestUncoverable'] = dict(n=len(D), share=r(D.oldestUncover.mean()), anyUncoverable=r(D.anyUncover.mean()))
    out['p27sameAsOldest'] = r(D.p27isOldest.mean())

    from statsmodels.discrete.conditional_models import ConditionalLogit
    feats = ['oldest', 'newest', 'size', 'crit', 'cover']

    def fit(Cx):
        m = ConditionalLogit(Cx.y.to_numpy(), Cx[feats].to_numpy(float), groups=Cx.dec.to_numpy()).fit(disp=0)
        return dict(zip(feats, np.asarray(m.params)))
    est = fit(C)
    boots = {f: [] for f in feats}
    decs = {p: g for p, g in C.groupby('pid')}
    pids = np.array(sorted(decs))
    for _ in range(400):
        pk = rng.choice(pids, len(pids), replace=True)
        Cb = pd.concat([decs[p].assign(dec=decs[p].dec.astype(str) + f'#{i}') for i, p in enumerate(pk)])
        Cb['dec'] = pd.factorize(Cb.dec)[0]
        try:
            e = fit(Cb)
        except Exception:
            continue
        for f in feats:
            boots[f].append(e[f])

    def bp(v):
        v = np.asarray(v)
        return min(1.0, 2 * min((v <= 0).mean(), (v >= 0).mean()))
    out['model'] = {f: dict(est=r(np.exp(est[f]), 3), lo=r(np.exp(np.percentile(boots[f], 2.5)), 3),
                            hi=r(np.exp(np.percentile(boots[f], 97.5)), 3), p=r(bp(boots[f]), 4)) for f in feats}
    print('decisions with 2+ waiting: %d (%d people)' % (out['decisions'], out['people']))
    for k_, v in out['opened'].items():
        print('  opened %-24s %s' % (k_, v))
    print('  oldest waiting could not be covered: %s of decisions; some waiting mission uncoverable: %s'
          % (out['oldestUncoverable']['share'], out['oldestUncoverable']['anyUncoverable']))
    print('  P27 top == oldest in %s of decisions' % out['p27sameAsOldest'])
    print('  model: ' + '  '.join('%s x%.2f [%.2f, %.2f] p=%.3f' % (f, v['est'], v['lo'], v['hi'], v['p']) for f, v in out['model'].items()))
    J = json.loads(LD.OUT.read_text(encoding='utf-8'))
    J['queueOrder'] = out
    LD.OUT.write_text(json.dumps(J, indent=1), encoding='utf-8')
    print('wrote queueOrder into', LD.OUT.relative_to(LD.BASE))


if __name__ == '__main__':
    main()
