#!/usr/bin/env python3
"""Build the paper's results LaTeX from the analysis register (docs/analysis/register/findings.yaml).

    python scripts/paper/build_paper.py jobs <jobs.json>          # which charts/views capture_figs.mjs should render
    python scripts/paper/build_paper.py tex  <paperDir>           # results.tex + supplement.tex from the register

Pipeline (see PaperDrafting/v2/README.md): jobs -> node capture_figs.mjs (figures + manifest.json) -> tex.

What goes where:
  * results.tex   — every finding in RESULTS_ORDER; its sections with tier `main` (any role but `archive`).
  * supplement.tex — the same findings' `side` sections that are not `archive` (the sidelined analyses).
Each section becomes: figure (all captured views as panels a, b, ...), the register's text (in \\regtext, i.e. draft
prose to be rewritten), the key numbers, a method paragraph, what participants said (the register's qualitative
summary) and the quotes the researcher highlighted on the review page (responses.json `quotes`, in their order).
Edits that only make sense on the interactive page (toggle/hover instructions, notes addressed to the researcher) are
removed by rule, plus the literal rewrites in scripts/paper/paper_text.json.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parents[2]
REG = BASE / 'docs' / 'analysis' / 'register'
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / 'scripts' / 'register'))

RESULTS_ORDER = ['f-personal-style', 'f-size-decides', 'f-manual-cards', 'f-practice', 'f-workload', 'f-triage',
                 'f-flaw-odd', 'f-tier-trust', 'f-operator-wants']
QUAL_ORDER = ['q-trust-unchecked', 'q-process', 'q-who-decides', 'q-failure', 'q-hierarchy', 'q-real-ops', 'q-new-jobs']
PRACTITIONER = 'q-practitioner'
CONF = {'strong': 'strong', 'moderate': 'moderate', 'suggestive': 'suggestive', 'null': 'a null result',
        'mixed': 'mixed'}


# ─── text conversion ──────────────────────────────────────────────────────────────────────────────

UNI = {
    '×': r'$\times$', '−': r'$-$', '–': '--', '—': '---', '→': r'$\rightarrow$', '←': r'$\leftarrow$',
    '↔': r'$\leftrightarrow$', 'ρ': r'$\rho$', 'κ': r'$\kappa$', 'ε': r'$\varepsilon$', 'Δ': r'$\Delta$',
    'μ': r'$\mu$', 'λ': r'$\lambda$', 'β': r'$\beta$', 'α': r'$\alpha$', '≥': r'$\geq$', '≤': r'$\leq$',
    '≈': r'$\approx$', '±': r'$\pm$', '²': r'$^2$', '·': r'$\cdot$', '…': r'\ldots{}', '‘': '`', '’': "'",
    '“': '``', '”': "''", '÷': r'$\div$', '✓': r'\checkmark{}', '≠': r'$\neq$', '\u00a0': '~', '½': r'$\frac12$',
    '•': r'$\bullet$', '∞': r'$\infty$', '≫': r'$\gg$', '≪': r'$\ll$', '→\u200b': r'$\rightarrow$', '\u200b': '',
    '✕': r'$\times$', '⚠': '(!)', '′': "'", '″': "''", '⁺': r'$^+$',
}
SPECIAL = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#', '_': r'\_', '{': r'\{',
           '}': r'\}', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}'}
TAGS = {'b': ('\\textbf{', '}'), 'strong': ('\\textbf{', '}'), 'i': ('\\emph{', '}'), 'em': ('\\emph{', '}'),
        'code': ('\\texttt{', '}'), 'sup': ('\\textsuperscript{', '}'), 'sub': ('\\textsubscript{', '}')}
WARN: set = set()


def esc(s: str) -> str:
    out = []
    for ch in s:
        if ch in SPECIAL:
            out.append(SPECIAL[ch])
        elif ch in UNI:
            out.append(UNI[ch])
        else:
            if ord(ch) > 127 and ch not in 'éèàüöäçñíóáÉ':
                WARN.add(ch)
            out.append(ch)
    return ''.join(out)


def tex(html: str) -> str:
    """HTML fragment (the register's b/i/code/br) -> LaTeX. ASCII double quotes become `` ''."""
    if not html:
        return ''
    html = str(html)
    parts = re.split(r'(<[^>]+>)', html)
    out, stack, dq = [], [], False
    for part in parts:
        m = re.fullmatch(r'<\s*(/?)\s*([a-zA-Z0-9]+)[^>]*?(/?)>', part)
        if m:
            close, tag = m.group(1) == '/', m.group(2).lower()
            if tag == 'br':
                out.append(' \\par ')
            elif tag in TAGS:
                if close:
                    if stack and stack[-1] == tag:
                        stack.pop(); out.append(TAGS[tag][1])
                else:
                    stack.append(tag); out.append(TAGS[tag][0])
            else:
                WARN.add('<%s>' % tag)
            continue
        seg = []
        for ch in part:
            if ch == '"':
                seg.append("''" if dq else '``'); dq = not dq
            else:
                seg.append(esc(ch))
        out.append(''.join(seg))
    out.extend(TAGS[t][1] for t in reversed(stack))
    return re.sub(r'\s+', ' ', ''.join(out)).strip()


INTERACTIVE = re.compile(r'\b(toggles?|[Bb]uttons?|[Hh]over|tooltips?|Switch the view|switches between|'
                         r'[Ss]how the numbers|open ``|[Cc]lick (?:a|any|the)|the page\'s|[Cc]lips?)\b')
PAREN_INTERACTIVE = re.compile(r'\s*\((?:[^()]|\([^()]*\))*\b(toggle|button|buttons|hover|Hover|tooltip)\b'
                               r'(?:[^()]|\([^()]*\))*\)')


# Sentences that mention a button or toggle but carry content: a participant's words (in quotes), the queue's
# unlogged sort toggle, and definitions that happen to name the page's controls.
KEEP = re.compile(r'"|never logged|not logged|^Each tactical plan split|^The very last numbers|^Rate = ')


def depage(html: str) -> str:
    """Drop what only makes sense on the interactive page: parentheticals about toggles, and whole sentences that
    instruct the reader to click, hover or switch views."""
    if not html:
        return ''
    s = PAREN_INTERACTIVE.sub('', str(html))
    sents = re.split(r'(?<=[.!?])\s+(?=[A-Z<(])', s)
    keep = []
    for x in sents:
        plain = re.sub(r'<[^>]+>', '', x)
        if INTERACTIVE.search(plain) and not KEEP.search(plain):
            # keep the sentence if dropping it would unbalance a tag
            if x.count('<b>') != x.count('</b>') or x.count('<i>') != x.count('</i>'):
                keep.append(x)
            continue
        keep.append(x)
    return ' '.join(keep)


# ─── data ─────────────────────────────────────────────────────────────────────────────────────────

def load():
    F = yaml.safe_load((REG / 'findings.yaml').read_text(encoding='utf-8'))['findings']
    R = json.loads((REG / 'responses.json').read_text(encoding='utf-8'))['cards']
    over = json.loads((HERE / 'paper_text.json').read_text(encoding='utf-8'))
    views = json.loads((HERE / 'figviews.json').read_text(encoding='utf-8'))
    return {f['id']: f for f in F}, R, over, views


def quote_bank():
    from apply_quotes import bank
    B = bank()
    with open(BASE / 'docs' / 'analysis' / 'qual' / 'evidence.csv', encoding='utf-8') as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            B['ev%d' % i] = dict(pid=row['pid'], source=row['source'], at=row['location'], text=row['excerpt'],
                                 led=row.get('led'))
    return B


def role(f, s, R):
    """The section's role this pass: the researcher's pick on the review page, else the register's."""
    return (R.get(f['id'] + '#' + s['id']) or {}).get('role') or s.get('role')


def pruned(f, R):
    return (R.get(f['id']) or {}).get('verdict') == 'prune'


def included(f, tier, R):
    if pruned(f, R):
        return []
    return [s for s in f['sections'] if s.get('tier', 'main') == tier and role(f, s, R) != 'archive']


def lab(fid, sid=None):
    """Section labels: sec:res:<finding> for the quantitative findings (as in v2), sec:qual:<finding> for the
    qualitative ones; sections append :<section>."""
    base = ('sec:qual:' if fid.startswith('q-') else 'sec:res:') + fid[2:]
    return base + (':' + sid if sid else '')


# ─── jobs ─────────────────────────────────────────────────────────────────────────────────────────

def jobs(path):
    F, R, over, views = load()
    out = []
    for fid in RESULTS_ORDER + QUAL_ORDER + [PRACTITIONER, 'f-methods']:
        f = F[fid]
        for s in f['sections']:
            if role(f, s, R) == 'archive' or not s.get('chart'):
                continue
            key = fid + '#' + s['id']
            out.append(dict(finding=fid, findingTitle=f['title'], section=s['id'],
                            views=views.get(key) or [['main', [], '']]))
    Path(path).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding='utf-8')
    print('%d chart jobs, %d views -> %s' % (len(out), sum(len(j['views']) for j in out), path))


# ─── tex ──────────────────────────────────────────────────────────────────────────────────────────

LABELS: dict = {}          # key ('<finding>' or '<finding>#<section>') -> label, for everything the paper contains


def xref(s: str) -> str:
    """Register ids in prose (f-size-decides, q-new-jobs#queue-order) -> cross-references to the paper's sections."""
    def sub(m):
        fid, sid = m.group(1), m.group(2) or m.group(3)
        if sid and fid + '#' + sid in LABELS:
            return r'Section~\ref{%s}' % LABELS[fid + '#' + sid]
        if fid in LABELS:
            return r'Section~\ref{%s}' % LABELS[fid]
        return m.group(0)
    s = re.sub(r'(?<![\w/:])([fq]-[a-z][a-z0-9-]*[a-z0-9])(?:\\#([a-z0-9-]+)|#([a-z0-9-]+))?', sub, s)
    return s.replace('f-who-does-better', "the sidelined ``who does better'' analysis")


def apply_over(key, field, val, over):
    o = over.get(key, {})
    if field in o.get('replace', {}):
        return o['replace'][field]
    for a, b in o.get('sub', {}).get(field, []):
        if isinstance(val, list):
            val = [v.replace(a, b) for v in val]
        elif val:
            if a not in val:
                print('  WARN %s.%s: substitution target not found: %.50s' % (key, field, a))
            val = val.replace(a, b)
    return val


def figure(label, files, title):
    """Placed [H], right after the section's point, so the page reads point -> figure -> numbers -> quotes."""
    # Sized to fit under the point on the same page: one panel up to 0.55 of the text height, two stacked, three or
    # more in a two-column grid (so a four-view figure is not pushed to the next page, leaving the point alone).
    L = ['\\begin{figure}[H]', '\\centering']
    n = len(files)
    if n == 1:
        L.append('\\includegraphics[width=\\linewidth,height=0.55\\textheight,keepaspectratio]{figs/results/%s}'
                 % files[0]['file'])
        note = files[0]['note']
        L.append('\\caption{\\textbf{%s}%s}' % (tex(title), (' ' + note) if note else ''))
    else:
        cols = 1 if n == 2 else 2
        rows = -(-n // cols)
        h_ = 0.56 / rows - 0.05
        for i, v in enumerate(files):
            L += ['\\begin{subfigure}[t]{%s}' % ('\\linewidth' if cols == 1 else '0.495\\linewidth'), '\\centering',
                  '\\includegraphics[width=\\linewidth,height=%.2f\\textheight,keepaspectratio]{figs/results/%s}'
                  % (h_, v['file']),
                  '\\caption{%s}' % (v['note'] or v['suffix']), '\\label{%s:%s}' % (label, v['suffix']),
                  '\\end{subfigure}']
            if cols == 1 or i % 2 == 1:
                L.append('\\par\\smallskip')
            else:
                L.append('\\hfill')
        L.append('\\caption{\\textbf{%s}}' % tex(title))
    L += ['\\label{%s}' % label, '\\end{figure}']
    return '\n'.join(L)


SRC = {'think-aloud': 'think-aloud', 'debrief': 'debrief', 'interview': 'written interview',
       'questionnaire talk': 'talk during the questionnaire'}
ROLE = {'paper': 'for the paper', 'extra': 'extra: may make it in', 'numbers': 'numbers only'}


def fmt_quote(q, checked, comment):
    src = SRC.get(q.get('source'), q.get('source', ''))
    at = (' ' + str(q['at'])) if q.get('at') and q.get('source') != 'interview' else ''
    led = ', after a leading question' if str(q.get('led')) in ('1', 'True', 'true') else ''
    para = ' (paraphrase)' if q.get('paraphrase') else ''
    mixed = ', includes the researcher\'s words' if q.get('mixed') else ''
    mark = '' if checked else '\\unchecked{}'
    out = ''
    if q.get('prompt'):
        out += '{\\upshape\\footnotesize Researcher: %s}\\par ' % tex(q['prompt'])
    out += "``%s''%s\\,---\\,%s (%s%s%s%s)%s" % (tex(q['text']).strip("`'"), mark, q['pid'], src, at, led, mixed, para)
    if comment:
        out += '\\par\\usernote{Your comment: %s}' % tex(comment)
    return '\\item ' + out


KIND = {'agrees': 'Agrees with', 'qualifies': 'Qualifies', 'beyond': 'Goes beyond'}


_RETARGET = None


def link(to, F):
    """(\\ref text, target title) for a link to register section `to`, after scripts/paper/retarget.json (sections
    the researcher's edit of the results removed, pointed at the closest one that remains)."""
    global _RETARGET
    if _RETARGET is None:
        p = HERE / 'retarget.json'
        _RETARGET = json.loads(p.read_text(encoding='utf-8'))['map'] if p.exists() else {}
    to = _RETARGET.get(to, to)
    if to.startswith('@'):                                    # a label in main.tex, given as @label|title
        lab_, _, title = to[1:].partition('|')
        return 'Section~\\ref{%s}' % lab_, title
    fid, _, sid = to.partition('#')
    s = next((x for x in (F.get(fid) or {}).get('sections') or [] if x['id'] == sid), None)
    title = terms(s['title']) if s else to
    return (('Section~\\ref{%s}' % LABELS[to]) if to in LABELS else None), title


def refs_list(q, F):
    """A passage's links back to the results (passages/<PID>.yaml `refs`), as cross-references."""
    L = []
    for r in q.get('refs') or []:
        where, title = link(r['to'], F)
        name = tex(title)
        where = where or '(not in the paper)'
        L.append('\\item \\textit{%s} %s, \\emph{%s}: %s' % (KIND.get(r['kind'], r['kind']), where, name, tex(terms(r['point']))))
    if not L:
        return ''
    return '\n'.join(['\\begin{itemize}[leftmargin=1.2em,itemsep=1pt]\\small'] + L + ['\\end{itemize}'])


def belongs(s, picks):
    """The highlights the review page still shows for this section: quotes in its featured / more lists, or coded
    excerpts (ev<N>) when the section draws on codes. A highlight left over from an earlier layout of the section
    (the page hides it) is dropped here too."""
    q = s.get('qual') or {}
    pool = set(q.get('featured') or []) | set(q.get('more') or [])
    return [x for x in picks if x in pool or (x.startswith('ev') and s.get('codes'))]


_TERMS = None


def terms(s):
    """The paper's terms (scripts/paper/terms.json: strategy card chosen, tactical suggestion requested, ...) applied
    to register prose, never to quotes."""
    global _TERMS
    if _TERMS is None:
        _TERMS = [(re.compile(a), b) for a, b in json.loads((HERE / 'terms.json').read_text(encoding='utf-8'))['rules']]
    if not s:
        return s
    s = str(s)
    for rx, b in _TERMS:
        s = rx.sub(lambda m, b=b: b, s)
    return s


def section(f, s, R, over, man, QB, F, level='subsubsection'):
    key = f['id'] + '#' + s['id']
    r = R.get(key) or {}
    title = apply_over(key, 'title', s['title'], over)
    out = ['\\%s{%s}\\label{%s}' % (level, tex(title), LABELS[key])]
    rl = role(f, s, R)
    if rl in ROLE or (r.get('note') or '').strip():
        tag = ('\\passtag{%s}' % ROLE[rl]) if rl in ROLE else ''
        note = ('\\usernote{Your note: %s}' % tex(r['note'].strip())) if (r.get('note') or '').strip() else ''
        out.append('\\noindent ' + ' '.join(x for x in (tag, note) if x))
    # 1 · the point
    text = terms(apply_over(key, 'text', depage(s.get('text', '')), over))
    files = man.get(key) or []
    if text:
        out.append('\\noindent \\regtext{%s}%s' % (xref(tex(text)), (' (Figure~\\ref{fig:%s})' % LABELS[key][4:]) if files else ''))
    # 2 · the graph
    if files:
        out.append(figure('fig:' + LABELS[key][4:], files, title))
    # 3 · the numbers (and how they were worked out)
    nums = [terms(n) for n in apply_over(key, 'numbers', s.get('numbers') or [], over)
            if not re.search(r'tooltip|[Hh]over', str(n))]
    if nums:
        out += ['\\paragraph*{Key numbers.}', '\\begin{itemize}[leftmargin=1.2em,itemsep=1pt]']
        out += ['\\item %s' % xref(tex(n)) for n in nums]
        out.append('\\end{itemize}')
    how = terms(apply_over(key, 'how', depage(s.get('how', '')), over))
    if how:
        out.append('\\paragraph*{Method.} {\\small %s}' % xref(tex(how)))
    # 4 · the quotes
    qual = s.get('qual') or {}
    summ = terms(apply_over(key, 'qual', qual.get('summary', ''), over))
    if summ:
        out.append('\\paragraph*{What participants said.} \\regtext{%s}' % xref(tex(summ)))
    picked = belongs(s, r.get('quotes') or [])
    trims, chk, notes = r.get('trims') or {}, r.get('checked') or {}, r.get('qnotes') or {}
    qs = []
    for q in picked:
        if q not in QB:
            continue
        shown = trims.get(q) or QB[q]['text']
        qs.append((q, dict(QB[q], text=shown), chk.get(q) == shown, notes.get(q)))
    if qs:
        out += ['\\paragraph*{Quotes selected for this section.}', '\\begin{quotelist}']
        out += [fmt_quote(q, c, n) for _, q, c, n in qs]
        out.append('\\end{quotelist}')
        for qid, q, _, _ in qs:
            rl_ = refs_list(q, F)
            if rl_:
                out += ['\\paragraph*{Links back to the results.}', rl_]
    if s.get('refs') == 'all':
        out.append(gather_refs(f, R, F))
    out.append('\\clearpage')
    return '\n\n'.join(out)


def gather_refs(f, R, F):
    """`refs: all`: every link on the finding's highlighted passages, grouped by kind."""
    seen, rows = set(), []
    for s in f['sections']:
        if s.get('tier', 'main') == 'side' or s.get('refs') == 'all':
            continue
        for q in belongs(s, (R.get(f['id'] + '#' + s['id']) or {}).get('quotes') or []):
            if q in seen:
                continue
            seen.add(q)
            rows += [(r, s) for r in (QB_.get(q) or {}).get('refs') or []]
    L = []
    for k, lab_ in KIND.items():
        part = [(r, s) for r, s in rows if r['kind'] == k]
        if not part:
            continue
        L += ['\\paragraph*{%s the results (%d).}' % (lab_, len(part)), '\\begin{itemize}[leftmargin=1.2em,itemsep=1pt]\\small']
        for r, s in part:
            where, title = link(r['to'], F)
            where = where or "(``%s'', not in the paper)" % tex(title)
            L.append('\\item %s, from the point in Section~\\ref{%s}: %s' % (where, LABELS[f['id'] + '#' + s['id']], tex(terms(r['point']))))
        L.append('\\end{itemize}')
    return '\n'.join(L)


QB_: dict = {}


def finding_head(f, R, over, level='subsection'):
    fid = f['id']
    head = apply_over(fid, 'headline', f.get('headline', ''), over)
    ftitle = apply_over(fid, 'title', f['title'], over)
    out = ['\\%s{%s}\\label{%s}' % (level, tex(ftitle), LABELS[fid])]
    r = R.get(fid) or {}
    verdict = r.get('verdict')
    line = '\\regtext{\\textbf{Summary.} %s} \\par\\noindent{\\small\\textit{Strength of evidence (register rating): %s.%s}}' % (
        xref(tex(head)), CONF.get(f.get('confidence'), f.get('confidence') or 'not rated'),
        (' Your verdict: %s.' % verdict) if verdict else '')
    out.append(line)
    if (r.get('note') or '').strip():
        out.append('\\noindent\\usernote{Your note on the finding: %s}' % tex(r['note'].strip()))
    return out


def build_tex(paper):
    global QB_
    F, R, over, _ = load()
    figdir = Path(paper) / 'figs' / 'results'
    man = {}
    for j in json.loads((figdir / 'jobs.json').read_text(encoding='utf-8')):
        fs = [dict(file='%s__%s__%s.png' % (j['finding'], j['section'], v[0]), suffix=v[0], note=v[2]) for v in j['views']]
        fs = [x for x in fs if (figdir / x['file']).exists()]
        if fs:
            man[j['finding'] + '#' + j['section']] = fs
    QB_ = QB = quote_bank()
    groups = [('results', RESULTS_ORDER, 'main'), ('qual', QUAL_ORDER, 'main'), ('practitioner', [PRACTITIONER], 'main')]
    for _, order, _t in groups:                       # every label first, so cross-references can be checked
        for fid in order:
            f = F[fid]
            if pruned(f, R):
                continue
            LABELS[fid] = lab(fid)
            for s in included(f, 'main', R) + included(f, 'side', R):
                LABELS[fid + '#' + s['id']] = lab(fid, s['id'])
    files, sup = {}, []
    for name, order, _t in groups:
        out = []
        for fid in order:
            f = F[fid]
            if pruned(f, R):
                out.append('%% %s (%s) left out: your verdict this pass was prune.' % (fid, f['title']))
                continue
            single = name == 'practitioner'
            out += finding_head(f, R, over, level='subsection' if not single else 'subsection')
            for s in included(f, 'main', R):
                out.append(section(f, s, R, over, man, QB, F))
            side = included(f, 'side', R)
            if side:
                ftitle = apply_over(fid, 'title', f['title'], over)
                sup.append('\\subsection{%s (supplementary analyses)}\\label{%s}' % (tex(ftitle), lab(fid).replace('sec:', 'sec:sup:')))
                sup.append('\\noindent Supplement to Section~\\ref{%s}.' % LABELS[fid])
                for s in side:
                    sup.append(section(f, s, R, over, man, QB, F))
        files[name] = out
    hdr = '%% GENERATED by scripts/paper/build_paper.py from docs/analysis/register/findings.yaml -- do not edit by hand;\n' \
          '%% rewrite the prose in main.tex or change the register / scripts/paper/paper_text.json and rebuild.\n\n'
    for name, out in files.items():
        (Path(paper) / (name + '.tex')).write_text(hdr + '\n\n'.join(out) + '\n', encoding='utf-8')
    (Path(paper) / 'supplement.tex').write_text(hdr + '\n\n'.join(sup) + '\n', encoding='utf-8')
    body = '\n'.join(sum(files.values(), []) + sup)
    print('wrote %s, supplement.tex' % ', '.join('%s.tex (%d kB)' % (n, len('\n'.join(o)) / 1024) for n, o in files.items()))
    print('sections: %d; figures: %d' % (body.count('\\subsubsection{'), body.count('\\begin{figure}')))
    if WARN:
        print('unmapped characters/tags:', ' '.join(sorted(WARN)))
    leftovers = sorted(set(re.findall(r'[^.]{0,60}\b(?:[Yy]ou|[Yy]our|researcher|toggle|[Bb]utton)\b[^.]{0,40}',
                                      re.sub(r'\\begin\{quotelist\}.*?\\end\{quotelist\}|\\(usernote|passtag)\{[^}]*\}',
                                             '', body, flags=re.S))))
    if leftovers:
        print('page-only wording left (%d):' % len(leftovers))
        for x in leftovers:
            print('   ...' + x.strip())


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'jobs':
        jobs(sys.argv[2])
    elif cmd == 'tex':
        build_tex(sys.argv[2])
