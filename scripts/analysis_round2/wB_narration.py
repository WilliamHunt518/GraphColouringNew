#!/usr/bin/env python3
"""Workstream B6 (round 2) -- in-session narration: moments of SPOKEN overload vs logged behaviour.

SUGGESTIVE ONLY: at most 11 sessions from 6 participants (P01, P03, P04, P05, P06, P07; PIL03 is a pilot
with no event log). No speaker diarisation exists (NARRATION.md: speaker-ID does not work), so the
researcher's own speech is in the transcript too.

RULES FIXED BEFORE ANY BEHAVIOUR AROUND THE MOMENTS WAS LOOKED AT
-----------------------------------------------------------------
Alignment (per session, from alignment.json's raw OCR reads, nothing re-run on video):
  * re-parse every raw OCR string leniently as a leading 'm:ss' (the pipeline's strict parser drops
    reads such as '5:43:' where the score's colon bleeds into the box);
  * offset_i = videoT - (480 - remaining). s1 recordings hold the whole sitting, so the reads form one
    cluster per session; the session's cluster is the EARLIEST (for *_s1) or the LARGEST (for *_s2, a
    trimmed clip) cluster of offsets within 3 s of each other;
  * keep a session only if that cluster has >= 8 reads, covers >= 300 s of session time, and the
    offsets' max deviation from their median is <= 3 s (no stall / drift bigger than the windows care
    about). The session's offset is the cluster median.
Overload moments:
  * a transcript segment whose start maps to session time 0 <= e < 480 and whose lower-cased text
    matches any pattern in STRICT (primary) or BROAD (= STRICT + pace/frustration words; secondary);
  * moments closer than 20 s to the previous kept moment are merged (the first is kept).
Behaviour around a moment t (session time):
  a) strategic queue at t (missions awaiting a strategic decision; Timeline.state) -- does the speech
     coincide with logged load at all?
  b) drone failures in the 60 s before t;
  c) card taken as-is, mean over strategic choices in [t-60, t+60];
  d) Suggest consulted, mean over tactical confirms whose first planner action is in [t-60, t+60].
Null: the same statistic at the same NUMBER of moments per session drawn at random from the starts of
ALL in-session transcript segments of that session (so the null also only samples moments when someone
was speaking); 5000 draws; two-sided p. A uniform-time null is reported alongside.
Estimate = observed mean - null mean ('diff').
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

import wB_common as c

NARR = c.BASE / 'Results' / 'Narration'
SESSIONS = ['P01_s1', 'P01_s2', 'P03_s1', 'P03_s2', 'P04_s1', 'P04_s2', 'P05_s1', 'P06_s1', 'P06_s2',
            'P07_s1', 'P07_s2', 'PIL03_s1', 'PIL03_s2']

STRICT = [r"\btoo many\b", r"\btoo much\b", r"\bso many\b", r"\boverwhelm", r"\bcan'?t keep up\b",
          r"\bcannot keep up\b", r"\bkeep(ing)? up\b", r"\blots? (of stuff |of things )?going on\b",
          r"\bstress", r"\bpanic", r"\bhectic\b", r"\bchao(s|tic)\b", r"\bstruggl", r"\blos(e|ing) track\b",
          r"\bpil(e|ed|ing) up\b", r"\bbacklog\b", r"\bjuggl", r"\bno time\b", r"\bnot enough time\b",
          r"\brunning out of time\b", r"\boh no\b", r"\boh god\b", r"\boh my god\b"]
BROAD = STRICT + [r"\bquick(ly)?\b", r"\bhurry\b", r"\brush", r"\bfaster\b", r"\bbusy\b", r"\bbehind\b",
                  r"\bdamn\b", r"\bshit\b", r"\bcrap\b", r"\bfuck", r"\bugh\b"]
MERGE_S = 20.0
WIN_S = 60.0
N_SIM = 5000
SEED = 20261007
OCR = re.compile(r'^\s*(\d):([0-5]\d)')


# ── alignment ────────────────────────────────────────────────────────────────────────────────────

def session_alignment(name):
    a = json.loads((NARR / name / 'alignment.json').read_text(encoding='utf-8'))
    pts = []
    for r in a['reads']:
        m = OCR.match(r.get('raw') or '')
        if m:
            rem = int(m.group(1)) * 60 + int(m.group(2))
            pts.append((r['videoT'], SESSION_E(rem), r['videoT'] - SESSION_E(rem)))
    pts.sort(key=lambda x: x[2])
    clusters, cur = [], []
    for p in pts:                        # single-linkage on offset, 3 s gap
        if cur and p[2] - cur[-1][2] > 3:
            clusters.append(cur)
            cur = []
        cur.append(p)
    if cur:
        clusters.append(cur)
    big = [cl for cl in clusters if len(cl) >= 5]
    if not big:
        return dict(session=name, ok=False, reason='no cluster of >= 5 reads', nreads=len(pts))
    cl = min(big, key=lambda cl: np.median([p[2] for p in cl])) if name.endswith('_s1') \
        else max(big, key=len)
    offs = np.array([p[2] for p in cl])
    es = np.array([p[1] for p in cl])
    off = float(np.median(offs))
    dev = float(np.abs(offs - off).max())
    cover = float(es.max() - es.min())
    ok = len(cl) >= 8 and cover >= 300 and dev <= 3
    return dict(session=name, ok=ok, offset=off, nreads=len(cl), cover=cover, maxdev=dev,
                pipelineOffset=a['alignment']['offset'], pipelineOk=a['alignment']['ok'],
                reason='' if ok else 'reads %d, cover %.0f s, maxdev %.1f s' % (len(cl), cover, dev))


def SESSION_E(remaining):
    return c.SESSION_S - remaining


def segments_in_session(name, offset):
    t = json.loads((NARR / name / 'transcript.raw.json').read_text(encoding='utf-8'))
    out = []
    for s in t['segments']:
        e = s['start'] - offset
        if 0 <= e < c.SESSION_S:
            out.append(dict(e=e, text=(s.get('text') or '').strip()))
    return out


def moments(segs, patterns):
    rx = re.compile('|'.join(patterns))
    hits = [s for s in segs if rx.search(s['text'].lower())]
    kept = []
    for h in hits:
        if not kept or h['e'] - kept[-1]['e'] >= MERGE_S:
            kept.append(h)
    return kept


# ── behaviour at a moment ───────────────────────────────────────────────────────────────────────

def measures_at(t_s, tl, S_sess, T_sess):
    t_ms = t_s * 1000.0
    st = tl.state(t_ms)
    s_win = S_sess[(S_sess.choice_ts >= t_ms - WIN_S * 1000) & (S_sess.choice_ts <= t_ms + WIN_S * 1000)]
    t_win = T_sess[(T_sess.first_ts >= t_ms - WIN_S * 1000) & (T_sess.first_ts <= t_ms + WIN_S * 1000)]
    return dict(queue=st['st_queued'], fail60=st['st_fail60'],
                took=s_win.took.mean() if len(s_win) else np.nan,
                consulted=t_win.consulted.mean() if len(t_win) else np.nan)


MEASURES = [('queue', 'strategic queue at the moment', '+'),
            ('fail60', 'drone failures in the 60 s before', '+'),
            ('took', 'card uptake, choices within +/-60 s', '+'),
            ('consulted', 'Suggest consulted, plans started within +/-60 s', '+')]


def pooled(vals):
    """Mean over moments of each measure (NaN-skipping), from a list of per-moment dicts."""
    D = pd.DataFrame(vals)
    return {k: float(D[k].mean()) if k in D and D[k].notna().any() else np.nan for k, _, _ in MEASURES}


def run(sp: c.Specs, S, T, tl):
    print('\n' + '=' * 110 + '\nB6 · Narration: spoken overload moments vs logged load/behaviour (SUGGESTIVE)\n' + '=' * 110)
    al = []
    for name in SESSIONS:
        r = session_alignment(name)
        pid, run_ = name.split('_s')[0], int(name.split('_s')[1])
        r['pid'], r['run'] = pid, run_
        r['hasLog'] = (pid, run_) in tl
        al.append(r)
    A = pd.DataFrame(al)
    print(A[['session', 'ok', 'hasLog', 'offset', 'pipelineOffset', 'pipelineOk', 'nreads', 'cover', 'maxdev', 'reason']]
          .to_string(index=False))
    use = A[A.ok & A.hasLog]
    print('Sessions used: %d (%s)' % (len(use), ', '.join(use.session)))

    # second alignment check: utterances naming a card vs the nearest strategic choice/preview
    rows, data = [], {}
    for r in use.itertuples():
        segs = segments_in_session(r.session, r.offset)
        tlx = tl[(r.pid, r.run)]
        S_s = S[(S.pid == r.pid) & (S.run == r.run)]
        T_s = T[(T.pid == r.pid) & (T.run == r.run)]
        ev = np.sort(np.r_[S_s.choice_ts.values, S_s.open_ts.values]) / 1000.0
        card = [s['e'] for s in segs if re.search(r'\b(aggressive|conservative)\b', s['text'].lower())]
        lags = [float(ev[np.argmin(np.abs(ev - e))] - e) for e in card] if len(ev) else []
        words = sum(len(s['text'].split()) for s in segs)
        data[r.session] = dict(segs=segs, tl=tlx, S=S_s, T=T_s, pid=r.pid, run=r.run)
        rows.append(dict(session=r.session, segments=len(segs), words=words, cardMentions=len(card),
                         medianAbsLagToStrategicEvent=np.median(np.abs(lags)) if lags else np.nan,
                         within10s=np.mean(np.abs(lags) <= 10) if lags else np.nan))
    Q = pd.DataFrame(rows)
    print('\nSpeech yield and a content check of the alignment (card names spoken vs nearest panel open/choice):')
    print(Q.round(2).to_string(index=False))

    rng = np.random.default_rng(SEED)
    out = {}
    for label, pats in (('strict', STRICT), ('broad', BROAD)):
        per = {}
        for sname, d in data.items():
            ms = moments(d['segs'], pats)
            per[sname] = ms
        n_m = {k: len(v) for k, v in per.items()}
        print('\n[%s list] overload moments per session: %s (total %d)' % (label, n_m, sum(n_m.values())))
        if label == 'strict':
            for k, v in per.items():
                for m in v:
                    print('   %s  e=%5.1f  "%s"' % (k, m['e'], m['text'][:90]))
        obs_vals, obs_by = [], {}
        for sname, ms in per.items():
            d = data[sname]
            vals = [measures_at(m['e'], d['tl'], d['S'], d['T']) for m in ms]
            obs_by[sname] = vals
            obs_vals += vals
        obs = pooled(obs_vals)
        # precompute measures at every candidate null moment (all segment starts / a uniform grid)
        cand_seg = {s: [measures_at(x['e'], data[s]['tl'], data[s]['S'], data[s]['T']) for x in data[s]['segs']]
                    for s in data}
        grid = np.arange(0.5, c.SESSION_S, 1.0)
        cand_uni = {s: [measures_at(x, data[s]['tl'], data[s]['S'], data[s]['T']) for x in grid] for s in data}

        def simulate(cands, sessions):
            sims = []
            for _ in range(N_SIM):
                vals = []
                for s in sessions:
                    k = n_m[s]
                    if k == 0:
                        continue
                    idx = rng.choice(len(cands[s]), size=k, replace=False if k <= len(cands[s]) else True)
                    vals += [cands[s][i] for i in idx]
                sims.append(pooled(vals))
            return pd.DataFrame(sims)

        sess_all = [s for s in data if n_m[s] > 0]
        nul = simulate(cand_seg, sess_all)
        nul_u = simulate(cand_uni, sess_all)
        print('  %-48s %8s %10s %10s %8s %10s %8s' % ('measure', 'observed', 'null(utt)', 'diff', 'p', 'null(unif)', 'p(unif)'))
        for key, lab, ex in MEASURES:
            o = obs[key]
            nv = nul[key].dropna().values
            nu = nul_u[key].dropna().values
            pm = float(np.mean(np.abs(nv - nv.mean()) >= abs(o - nv.mean())))
            pu = float(np.mean(np.abs(nu - nu.mean()) >= abs(o - nu.mean())))
            print('  %-48s %8.3f %10.3f %+10.3f %8.3f %10.3f %8.3f' % (lab, o, nv.mean(), o - nv.mean(), pm, nu.mean(), pu))
            # gates, by direction of (obs - null) on subsets of sessions
            def sub_diff(sessions):
                if not any(n_m[s] for s in sessions):
                    return np.nan
                ov = pooled([v for s in sessions for v in obs_by[s]])[key]
                sm_ = simulate_small(cand_seg, sessions, n_m, rng, key)
                return ov - sm_
            sign = np.sign(o - nv.mean())
            s1 = [s for s in sess_all if s.endswith('_s1')]
            d1 = sub_diff(s1)
            th = [s for s in sess_all if data[s]['pid'] in ('P01', 'P03', 'P05', 'P07')]
            shf = [s for s in sess_all if data[s]['pid'] in ('P04', 'P06')]
            dth, dsh = sub_diff(th), sub_diff(shf)
            loo = []
            for pid in sorted({data[s]['pid'] for s in sess_all}):
                loo.append(sub_diff([s for s in sess_all if data[s]['pid'] != pid]))
            loo = np.array([x for x in loo if np.isfinite(x)])
            sp.add(variant_id='B6-%s-%s' % (label, key), extra=0,
                   description='Narration (%s overload list): %s at spoken-overload moments vs random utterances'
                               % (label, lab),
                   sample='S-narr', outcome=key, predictor='spoken-overload moment (%s list)' % label,
                   model='null simulation: same number of moments per session drawn from all in-session utterances, '
                         '%d draws' % N_SIM,
                   estimate=o - nv.mean(), ci_lo=o - np.quantile(nv, .975), ci_hi=o - np.quantile(nv, .025),
                   estimate_scale='diff', p=pm,
                   n_obs=int(sum(1 for s in sess_all for v in obs_by[s] if np.isfinite(v[key]))),
                   n_people=len({data[s]['pid'] for s in sess_all}), expected_direction=ex,
                   s1_same_direction='na' if not np.isfinite(d1) else int(np.sign(d1) == sign),
                   both_orders_same_direction='na' if not (np.isfinite(dth) and np.isfinite(dsh))
                   else int(np.sign(dth) == sign and np.sign(dsh) == sign),
                   loo_sign_flip=int((np.sign(loo) != sign).any()) if len(loo) else 'na',
                   notes='S-narr: %d of the 11 aligned sessions had >= 1 moment, %d people; obs %.3f vs null %.3f; uniform-time null '
                         'mean %.3f p=%.3f; CI = obs minus the null 95%% range; LOO diff range %.3f..%.3f; '
                         'SUGGESTIVE (n tiny, no diarisation)'
                         % (len(sess_all), len({data[s]['pid'] for s in sess_all}), o, nv.mean(), nu.mean(), pu,
                            loo.min() if len(loo) else np.nan, loo.max() if len(loo) else np.nan))
        out[label] = dict(obs=obs, n=n_m)
    return A, Q, out


def simulate_small(cands, sessions, n_m, rng, key, n=1000):
    vals = []
    for _ in range(n):
        v = []
        for s in sessions:
            k = n_m[s]
            if k == 0:
                continue
            idx = rng.choice(len(cands[s]), size=k, replace=k > len(cands[s]))
            v += [cands[s][i][key] for i in idx]
        v = [x for x in v if np.isfinite(x)]
        if v:
            vals.append(np.mean(v))
    return float(np.mean(vals)) if vals else np.nan
