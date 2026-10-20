#!/usr/bin/env python3
"""Build the paper's results in prose form (v4): scripts/paper/prose.yaml, with the register as the options.

    python scripts/paper/build_prose.py <paperDir>

Run `build_paper.py tex <paperDir>` first: it writes supplement.tex and the v3 layout, and this script then replaces
results.tex, qual.tex and practitioner.tex with the prose layout. Figures come from <paperDir>/figs/results (rendered
by capture_figs.mjs, which applies scripts/paper/terms.json to every chart label).

Each finding is one block that ends in \\clearpage: its intro, then each point as paragraph -> figure (the views the
point names, with its statement caption) -> paragraph after, display quotes (as the researcher trimmed them) and, for
the practitioner, the passage's links back to the results. Every point drops a label for its register section (and
for the sections it covers via `also`), so cross-references from elsewhere still resolve.

Then the finding's options block (`options` environment, shown or hidden in main.tex with \\includecomment /
\\excludecomment): for every included section, the researcher's role and note, the register text of sections the
prose does not use, every figure view the prose does not show, the key numbers, and every highlighted quote the prose
does not use (with the researcher's per-quote comments).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_paper as B  # noqa: E402

PROSE = HERE / 'prose.yaml'
GROUPS = [('results', B.RESULTS_ORDER), ('qual', B.QUAL_ORDER), ('practitioner', [B.PRACTITIONER])]
NORM = re.compile(r"[a-z0-9]+")


def words(s):
    return ' '.join(NORM.findall(str(s).lower().replace('’', "'")))


def figfile(fid, sid, view):
    return '%s__%s__%s.png' % (fid, sid, view)


def figure(paper, fid, sid, views, caption, notes):
    """The point's figure: one view as a plain figure, several as (a), (b) panels. Labels: fig:<sec label>, and
    fig:<sec label>:<view> for each view (so \\ref{@:all} and \\ref{@} both work)."""
    base = 'fig:' + B.LABELS[fid + '#' + sid][4:]
    have = [v for v in views if (Path(paper) / 'figs' / 'results' / figfile(fid, sid, v)).exists()]
    missing = [v for v in views if v not in have]
    if missing:
        print('  WARN %s#%s: no figure for view(s) %s' % (fid, sid, ', '.join(missing)))
    if not have:
        return ''
    L = ['\\begin{figure}[H]', '\\centering']
    if len(have) == 1:
        v = have[0]
        L.append('\\includegraphics[width=\\linewidth,height=0.50\\textheight,keepaspectratio]{figs/results/%s}'
                 % figfile(fid, sid, v))
        L.append('\\caption{%s}' % caption.strip())
        L.append('\\label{%s}' % base)
        if v != 'main':
            L.append('\\label{%s:%s}' % (base, v))
    else:
        # two wide panels stack; two tall ones (width < 1.6 x height) go side by side, as do three or more
        from PIL import Image
        aspect = min(Image.open(Path(paper) / 'figs' / 'results' / figfile(fid, sid, v)).size[0] /
                     Image.open(Path(paper) / 'figs' / 'results' / figfile(fid, sid, v)).size[1] for v in have)
        cols = 1 if len(have) == 2 and aspect >= 1.6 else 2
        rows = -(-len(have) // cols)
        h_ = (0.52 if cols == 1 else 0.60) / rows - 0.05
        for i, v in enumerate(have):
            L += ['\\begin{subfigure}[t]{%s}' % ('\\linewidth' if cols == 1 else '0.495\\linewidth'), '\\centering',
                  '\\includegraphics[width=\\linewidth,height=%.2f\\textheight,keepaspectratio]{figs/results/%s}'
                  % (h_, figfile(fid, sid, v)),
                  '\\caption{%s}' % (notes.get(v) or v), '\\label{%s:%s}' % (base, v), '\\end{subfigure}']
            L.append('\\par\\smallskip' if cols == 1 or i % 2 == 1 else '\\hfill')
        L.append('\\caption{%s}' % caption.strip())
        L.append('\\label{%s}' % base)
    L.append('\\end{figure}')
    return '\n'.join(L)


def shown_text(key, qid, R, QB):
    r = R.get(key) or {}
    return (r.get('trims') or {}).get(qid) or QB[qid]['text']


def display(key, qid, R, QB):
    q = QB[qid]
    src = B.SRC.get(q.get('source'), q.get('source', ''))
    at = (' ' + str(q['at'])) if q.get('at') and q.get('source') != 'interview' else ''
    mixed = '; includes the researcher\'s words' if q.get('mixed') else ''
    out = ['\\begin{quote}\\small']
    if q.get('prompt'):
        out.append('{\\footnotesize\\textit{Researcher:} %s}\\par\\smallskip' % B.tex(q['prompt']))
    out.append("``%s''\\par\\hfill--- %s (%s%s%s)" % (B.tex(shown_text(key, qid, R, QB)).strip("`'"), q['pid'], src, at,
                                                    mixed))
    out.append('\\end{quote}')
    note = ((R.get(key) or {}).get('qnotes') or {}).get(qid)
    if note:
        # the comment package needs \begin / \end on lines of their own
        out.append('\\begin{options}\n\\noindent Your comment on this quote: %s\n\\end{options}' % B.tex(note))
    return '\n'.join(out)


def options_block(paper, f, R, QB, F, views, used_views, used_quotes, point_secs):
    """Everything the prose leaves out, section by section."""
    out = []
    for s in B.included(f, 'main', R):
        key = f['id'] + '#' + s['id']
        r = R.get(key) or {}
        part = []
        rl = B.role(f, s, R)
        head = '\\optsec{%s}' % B.tex(s['title'])
        tags = []
        if rl in B.ROLE:
            tags.append('pass 5: %s' % B.ROLE[rl])
        if s['id'] not in point_secs:
            tags.append('not used in the prose above')
        part.append(head + (' {\\footnotesize [%s]}' % '; '.join(tags) if tags else ''))
        if (r.get('note') or '').strip():
            part.append('\\noindent Your note: %s' % B.tex(r['note'].strip()))
        if s['id'] not in point_secs and s.get('text'):
            part.append('\\noindent\\regtext{%s}' % B.xref(B.tex(B.terms(B.depage(s['text'])))))
        # figure views not shown above
        vs = [v for v in (views.get(key) or [['main', [], '']])]
        extra = [(v[0], v[2]) for v in vs if (key, v[0]) not in used_views
                 and (Path(paper) / 'figs' / 'results' / figfile(f['id'], s['id'], v[0])).exists()]
        if s.get('chart') and extra:
            cells = []
            for v, note in extra:
                cells.append('\\begin{minipage}[t]{0.49\\linewidth}\\centering'
                             '\\includegraphics[width=\\linewidth,height=0.24\\textheight,keepaspectratio]{figs/results/%s}'
                             '\\par{\\scriptsize %s%s}\\end{minipage}'
                             % (figfile(f['id'], s['id'], v), ('Other view: ' if s['id'] in point_secs else ''),
                                note or v))
            part.append('\\par\\noindent ' + '\\hfill\n'.join(cells))
        nums = [B.terms(n) for n in s.get('numbers') or [] if not re.search(r'tooltip|[Hh]over', str(n))]
        if nums:
            part.append('\\noindent Key numbers:\\begin{itemize}[leftmargin=1.2em,itemsep=0pt]\\footnotesize\n%s\n\\end{itemize}'
                        % '\n'.join('\\item ' + B.xref(B.tex(n)) for n in nums))
        picks = B.belongs(s, r.get('quotes') or [])
        left = [q for q in picks if q in QB and q not in used_quotes]
        if left:
            chk, qn = r.get('checked') or {}, r.get('qnotes') or {}
            items = [B.fmt_quote(dict(QB[q], text=shown_text(key, q, R, QB)), chk.get(q) == shown_text(key, q, R, QB),
                                 qn.get(q)) for q in left]
            part.append('\\noindent Highlighted quotes not used above:\\begin{quotelist}\n%s\n\\end{quotelist}' % '\n'.join(items))
        if len(part) > 1:
            out.append('\n\n'.join(part))
    if not out:
        return ''
    return '\\begin{options}\n\\optshead{Options for this finding}\n\n' + '\n\n'.join(out) + '\n\\end{options}'


def woven(text, key, picks, R, QB):
    """Highlighted quotes whose (trimmed) words appear in the prose."""
    w = words(text)
    return {q for q in picks if q in QB and words(shown_text(key, q, R, QB))[:60] in w}


def build(paper):
    F, R, over, views = B.load()
    P = yaml.safe_load(PROSE.read_text(encoding='utf-8'))
    QB = B.quote_bank()
    B.QB_ = QB
    notes = {k: {v[0]: v[2] for v in vs} for k, vs in views.items() if not k.startswith('_')}
    for _, order in GROUPS:
        for fid in order:
            f = F[fid]
            if B.pruned(f, R):
                continue
            B.LABELS[fid] = B.lab(fid)
            for s in B.included(f, 'main', R) + B.included(f, 'side', R):
                B.LABELS[fid + '#' + s['id']] = B.lab(fid, s['id'])
    hdr = ('%% GENERATED by scripts/paper/build_prose.py from scripts/paper/prose.yaml (the prose) and the analysis\n'
           '%% register (the options blocks) -- edit the prose there, or here once you stop regenerating.\n\n')
    for name, order in GROUPS:
        out = []
        for fid in order:
            f = F[fid]
            if B.pruned(f, R):
                out.append('%% %s (%s) left out: your verdict this pass was prune.' % (fid, f['title']))
                continue
            p = P.get(fid)
            if not p:
                print('  WARN %s has no prose: left out' % fid)
                continue
            secs = {s['id']: s for s in B.included(f, 'main', R)}
            out.append('%% ======== %s ========' % fid)
            out.append('\\subsection{%s}\\label{%s}' % (p['title'], B.LABELS[fid]))
            out.append(p['intro'].strip())
            used_views, used_quotes, point_secs = set(), set(), set()
            for pt in p['points']:
                sid = pt['sec']
                if sid not in secs:
                    print('  WARN %s#%s: not an included section; point skipped' % (fid, sid))
                    continue
                key = fid + '#' + sid
                point_secs.add(sid)
                point_secs.update(pt.get('also') or [])
                rl = B.role(f, secs[sid], R)
                out.append('%% --- %s%s ---' % (key, (' (pass 5: %s)' % B.ROLE[rl]) if rl in B.ROLE else ''))
                lbls = ''.join('\\label{%s}' % B.LABELS[fid + '#' + x] for x in [sid] + (pt.get('also') or [])
                               if fid + '#' + x in B.LABELS)
                head = ('\\paragraph{%s.}' % pt['heading']) if pt.get('heading') else ''
                figlab = 'fig:' + B.LABELS[key][4:]
                text = pt.get('text', '').strip().replace('\\ref{@', '\\ref{' + figlab)
                out.append('\\phantomsection%s%s\n%s' % (lbls, head, text))
                if pt.get('fig'):
                    out.append(figure(paper, fid, sid, pt['fig'], pt.get('caption', ''), notes.get(key, {})))
                    used_views.update((key, v) for v in pt['fig'])
                if pt.get('after'):
                    out.append(pt['after'].strip().replace('\\ref{@', '\\ref{' + figlab))
                picks = []
                for x in [sid] + (pt.get('also') or []):
                    picks += B.belongs(secs.get(x, {}), (R.get(fid + '#' + x) or {}).get('quotes') or [])
                used_quotes |= woven(pt.get('text', '') + ' ' + pt.get('after', ''), key, picks, R, QB)
                for qid in pt.get('display') or []:
                    if qid not in QB:
                        print('  WARN %s: unknown quote %s' % (key, qid))
                        continue
                    out.append(display(key, qid, R, QB))
                    used_quotes.add(qid)
                    if fid == B.PRACTITIONER:
                        rl_ = B.refs_list(QB[qid], F)
                        if rl_:
                            out.append('\\noindent\\textit{Bears on:}\n' + rl_)
                if secs[sid].get('refs') == 'all':
                    out.append(B.gather_refs(f, R, F))
            ob = options_block(paper, f, R, QB, F, views, used_views, used_quotes, point_secs)
            if ob:
                out.append(ob)
            out.append('\\clearpage')
        (Path(paper) / (name + '.tex')).write_text(hdr + '\n\n'.join(out) + '\n', encoding='utf-8')
        print('wrote %s.tex (%d kB)' % (name, len('\n'.join(out)) / 1024))
    if B.WARN:
        print('unmapped characters/tags:', ' '.join(sorted(B.WARN)))


if __name__ == '__main__':
    build(sys.argv[1])
