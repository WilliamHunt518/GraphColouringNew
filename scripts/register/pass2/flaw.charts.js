(() => {
  const D = (typeof DATA !== 'undefined' && DATA.pass2) ? DATA.pass2.flaw : null;
  const miss = (host, msg) => { host.innerHTML = ''; h('p', { class: 'note', text: msg || 'Data for this chart is missing — rerun scripts/register/pass2/flaw.py.' }, host); };
  const GC = { said: () => css('--warn'), notSaid: () => css('--s-strat') };
  const GL = { said: 'Said they noticed', notSaid: 'Never said so' };
  const ppts = v => (v >= 0 ? '+' : '') + (100 * v).toFixed(0) + ' pts';

  /* ── generic: categories on x, proportion on y, points with CI bars, optional faint person lines ── */
  function catLines(host, cats, series, o = {}) {
    const W = 700, H = o.height || 300, padL = 50, padR = 130, padT = 18, padB = 46;
    const s = svgRoot(host, W, H);
    const lo = o.lo != null ? o.lo : 0, hi = o.hi != null ? o.hi : 1;
    const x = i => padL + (W - padL - padR) * ((i + 0.5) / cats.length);
    const y = v => H - padB - (H - padB - padT) * ((Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo));
    const ticks = o.ticks || [0, .25, .5, .75, 1];
    ticks.forEach(v => {
      el('line', { x1: padL, x2: W - padR, y1: y(v), y2: y(v), stroke: css('--grid') }, s);
      el('text', { x: padL - 8, y: y(v) + 4, 'text-anchor': 'end', fill: css('--ink-3'), 'font-size': 11,
                   'font-family': css('--mono') }, s).textContent = o.tickFmt ? o.tickFmt(v) : pct(v, 0);
    });
    cats.forEach((c, i) => el('text', { x: x(i), y: H - padB + 17, 'text-anchor': 'middle', fill: css('--ink-2'),
                                        'font-size': 11.5 }, s).textContent = c.label);
    if (o.xLabel) el('text', { x: (padL + W - padR) / 2, y: H - 8, 'text-anchor': 'middle', fill: css('--ink-3'),
                               'font-size': 11 }, s).textContent = o.xLabel;
    if (o.divider != null) {
      const xd = (x(o.divider - 1) + x(o.divider)) / 2;
      el('line', { x1: xd, x2: xd, y1: padT - 6, y2: H - padB, stroke: css('--bad'), 'stroke-width': 1.5, 'stroke-dasharray': '4 3' }, s);
      el('text', { x: xd, y: padT - 8, 'text-anchor': 'middle', fill: css('--bad'), 'font-size': 10.5,
                   'font-family': css('--mono') }, s).textContent = o.dividerLabel || '';
    }
    const idx = Object.fromEntries(cats.map((c, i) => [c.key, i]));
    (o.persons || []).forEach(pp => {
      const pts = cats.map((c, i) => pp.vals[c.key] != null ? [x(i), y(pp.vals[c.key])] : null).filter(Boolean);
      if (pts.length < 2) return;
      const pth = el('path', { d: pts.map((p, i) => (i ? 'L' : 'M') + p[0] + ' ' + p[1]).join(' '), fill: 'none',
                               stroke: pp.color, 'stroke-width': 1, opacity: .18 }, s);
      const hit = el('path', { d: pth.getAttribute('d'), fill: 'none', stroke: 'transparent', 'stroke-width': 6 }, s);
      hoverable(hit, `<b>${pp.pid}</b> (${pp.group})<br>` + cats.filter(c => pp.vals[c.key] != null)
        .map(c => `${c.label}: ${pct(pp.vals[c.key], 0)} (n ${pp.n[c.key]})`).join('<br>'));
    });
    series.forEach((se, si) => {
      const off = (si - (series.length - 1) / 2) * 7;
      const pts = se.points.filter(p => p.y != null && idx[p.key] != null);
      if (!pts.length) return;
      const d = pts.map((p, i) => (i ? 'L' : 'M') + (x(idx[p.key]) + off) + ' ' + y(p.y)).join(' ');
      const pa = { d, fill: 'none', stroke: se.color, 'stroke-width': 2.2, 'stroke-linejoin': 'round' };
      if (se.dash) pa['stroke-dasharray'] = '5 4';
      el('path', pa, s);
      pts.forEach(p => {
        const cx = x(idx[p.key]) + off;
        if (p.lo != null && p.hi != null)
          el('line', { x1: cx, x2: cx, y1: y(p.lo), y2: y(p.hi), stroke: se.color, 'stroke-width': 1.6, opacity: .75 }, s);
        el('circle', { cx, cy: y(p.y), r: se.dash ? 3 : 4.5, fill: se.dash ? css('--surface') : se.color,
                       stroke: se.dash ? se.color : css('--surface'), 'stroke-width': 1.5 }, s);
        const hit = el('circle', { cx, cy: y(p.y), r: 11, fill: 'transparent' }, s);
        hoverable(hit, `<b>${se.label}</b> · ${cats[idx[p.key]].label}<br>${o.valFmt ? o.valFmt(p.y) : pct(p.y)}`
          + (p.lo != null ? ` [${pct(p.lo, 0)}, ${pct(p.hi, 0)}]` : '') + (p.tip ? '<br>' + p.tip : ''));
      });
      const last = pts[pts.length - 1];
      el('text', { x: W - padR + 8, y: y(last.y) + 4 + (o.labelNudge ? o.labelNudge[si] || 0 : 0), fill: se.color, 'font-size': 11.5,
                   'font-weight': 600 }, s).textContent = se.label;
    });
  }

  const binTip = b => `n = ${b.n} decisions from ${b.people} people<br>missions averaging ${num(b.ndrones, 1)} drones, `
    + `${num(b.ntasks, 1)} tasks · ${num(b.queue, 1)} others waiting · minute ${num(b.minute, 1)} · ${pct(b.session2, 0)} session 2`
    + `<br>raw ${pct(b.raw, 0)} · expected ${pct(b.exp, 0)} · adjusted ${pct(b.adj, 0)}`;
  const BIN_LABEL = { before: 'before', card: 'the card', '1–3': '1st–3rd', '4–6': '4th–6th', '7–9': '7th–9th', '10+': '10th+' };

  /* 1 · the rebuilt event study */
  function events(host) {
    if (!D || !D.odd) return miss(host);
    host.innerHTML = '';
    let sample = 'three', mode = 'obs';
    btnBar(host, 'Missions', [['three', 'Three-type (never carry the flaw)'], ['all', 'All missions']], sample, k => { sample = k; draw(); });
    btnBar(host, 'Show', [['obs', 'Observed + each person'], ['exp', 'Observed + expected'], ['adj', 'Adjusted']], mode, k => { mode = k; draw(); });
    const box = h('div', {}, host), cap = h('p', { class: 'note' }, host);
    function draw() {
      const V = D.odd.views[sample];
      if (!V) return miss(box);
      const keys = D.binKeys.filter(k => sample === 'all' || k !== 'card');
      const cats = keys.map(k => ({ key: k, label: BIN_LABEL[k] || k }));
      const series = [], persons = [];
      ['said', 'notSaid'].forEach(g => {
        const B = V[g].bins.bins;
        const col = GC[g]();
        if (mode === 'adj') series.push({ label: GL[g], color: col, points: B.map(b => ({ key: b.bin, y: b.adj, lo: b.adjLo, hi: b.adjHi, tip: binTip(b) })) });
        else series.push({ label: GL[g], color: col, points: B.map(b => ({ key: b.bin, y: b.raw, lo: b.rawLo, hi: b.rawHi, tip: binTip(b) })) });
        if (mode === 'exp') series.push({ label: 'expected', color: col, dash: true, points: B.map(b => ({ key: b.bin, y: b.exp, tip: binTip(b) })) });
        if (mode === 'obs') V[g].bins.persons.forEach(pp => persons.push({ pid: pp.pid, group: GL[g], vals: pp.raw, n: pp.n, color: col }));
      });
      catLines(box, cats, series, { persons, divider: keys.indexOf(sample === 'all' ? 'card' : '1–3') + (sample === 'all' ? 0 : 0),
        dividerLabel: 'first illogical card', xLabel: (sample === 'three' ? 'three-type' : '') + ' decisions after the first illogical card (each person counted in order)',
        labelNudge: mode === 'exp' ? [0, 0, 0, 0] : [-6, 6] });
      const t = g => V[g].test;
      cap.innerHTML = `Bars are 95% intervals from resampling people. ${mode === 'obs' ? 'Faint lines: each person’s own rate in each bin. ' : ''}`
        + `Before → after (anchor decision excluded): noticers ${pct(t('said').before, 0)} → ${pct(t('said').after, 0)}, adjusted change ${ppts(t('said').adj.est)} `
        + `[${ppts(t('said').adj.lo)}, ${ppts(t('said').adj.hi)}], ${pval(t('said').adj.p)}; never said ${pct(t('notSaid').before, 0)} → ${pct(t('notSaid').after, 0)}, `
        + `${ppts(t('notSaid').adj.est)} [${ppts(t('notSaid').adj.lo)}, ${ppts(t('notSaid').adj.hi)}], ${pval(t('notSaid').adj.p)}. `
        + `Difference ${ppts(V.interaction.adj.est)}, ${pval(V.interaction.adj.p)}; label-shuffle ${pval(V.perm.p)}.`;
      tableFor(box, ['Group · bin', 'n', 'people', 'raw', 'expected', 'adjusted [95% CI]'],
        ['said', 'notSaid'].flatMap(g => V[g].bins.bins.map(b => [GL[g] + ' · ' + (BIN_LABEL[b.bin] || b.bin), b.n, b.people, pct(b.raw, 0), pct(b.exp, 0),
          `${pct(b.adj, 0)} [${pct(b.adjLo, 0)}, ${pct(b.adjHi, 0)}]`])));
    }
    draw();
  }

  /* 2 · Nth three-type decision after the card, one dot each */
  function nth(host) {
    if (!D || !D.odd) return miss(host);
    const V = D.odd.views.three;
    const ks = [...new Set(['said', 'notSaid'].flatMap(g => V[g].k.map(p => p.k)))].sort((a, b) => a - b);
    const cats = ks.map(k => ({ key: String(k), label: (k > 0 ? '+' : '') + k }));
    const series = ['said', 'notSaid'].map(g => ({ label: GL[g], color: GC[g](),
      points: V[g].k.map(p => ({ key: String(p.k), y: p.raw, lo: p.lo, hi: p.hi,
        tip: `n = ${p.n} people (one decision each)<br>expected ${pct(p.exp, 0)} · ${num(p.ndrones, 1)} drones · ${num(p.queue, 1)} waiting · minute ${num(p.minute, 1)}` })) }));
    catLines(host, cats, series, { height: 290, divider: ks.indexOf(1), dividerLabel: 'first illogical card',
      xLabel: 'Nth three-type decision before (−) / after (+) the first illogical card — every person has a +1, +2, … until their decisions run out' });
    h('p', { class: 'note', text: 'Each dot is one decision per person, so its 95% interval (Wilson) is wide: at n ≈ 15 a single dot cannot separate 50% from 75%. Read the binned chart above for the trend.' }, host);
  }

  /* 3 · the illogical-card missions themselves */
  function oddMissions(host) {
    if (!D || !D.odd || !D.odd.oddMissions) return miss(host);
    host.innerHTML = '';
    const O = D.odd.oddMissions;
    const parts = [['cons', 'took the illogical Conservative card', '--r-cons'], ['aggr', 'took Aggressive', '--r-aggr'],
                   ['manSeen', 'manual, after seeing the cards', '--r-man'], ['manEarly', 'manual before the cards loaded', '--ink-3']];
    const W = 700, rowH = 30, padL = 190, padR = 20;
    const rows = [];
    ['said', 'notSaid'].forEach(g => { rows.push({ head: GL[g] }); O[g].rows.forEach(rw => rows.push(Object.assign({ g }, rw))); });
    const H = 10 + rows.length * rowH + 20;
    const s = svgRoot(host, W, H);
    const x = v => padL + (W - padL - padR) * v;
    rows.forEach((rw, i) => {
      const y0 = 8 + i * rowH;
      if (rw.head) { el('text', { x: 6, y: y0 + 19, fill: GC[rows[i + 1] ? rows[i + 1].g : 'said'](), 'font-weight': 600, 'font-size': 12.5 }, s).textContent = rw.head; return; }
      el('text', { x: padL - 10, y: y0 + 19, 'text-anchor': 'end', fill: css('--ink-2'), 'font-size': 12 }, s)
        .textContent = `${rw.bin} illogical card (n ${rw.n}, ${rw.people} people)`;
      let acc = 0;
      parts.forEach(([k, lab, tok]) => {
        const v = rw[k] || 0;
        const r_ = el('rect', { x: x(acc), y: y0 + 6, width: Math.max(0, x(acc + v) - x(acc)), height: 18, fill: css(tok), opacity: k === 'manEarly' ? .55 : .9 }, s);
        const ci = rw[k + 'CI'];
        hoverable(r_, `<b>${GL[rw.g]} · ${rw.bin} illogical card</b><br>${lab}: ${pct(v, 0)}` + (ci ? ` [${pct(ci[0], 0)}, ${pct(ci[1], 0)}] (people resampled)` : '') + `<br>n = ${rw.n} decisions, ${rw.people} people`);
        if (v >= 0.09) el('text', { x: x(acc + v / 2), y: y0 + 19, 'text-anchor': 'middle', fill: css('--surface'), 'font-size': 10.5, 'font-family': css('--mono'), 'pointer-events': 'none' }, s).textContent = pct(v, 0);
        acc += v;
      });
    });
    legend(host, parts.map(([k, lab, tok]) => ({ label: lab, color: css(tok) })));
    const tr = O.tests;
    const f = z => z && z.est != null ? `${ppts(z.est)} per card [${ppts(z.lo)}, ${ppts(z.hi)}]` : '—';
    h('p', { class: 'note', html: `Trend per extra illogical card met (linear, people clustered, game held fixed): `
      + `<b>took any card</b> — noticers ${f(tr.took.trend.said)}, never-said ${f(tr.took.trend.notSaid)}, difference ${pval(tr.took.trend.interaction.p)}; `
      + `<b>took the illogical Conservative card</b> — ${f(tr.cons.trend.said)} vs ${f(tr.cons.trend.notSaid)}, ${pval(tr.cons.trend.interaction.p)}; `
      + `<b>went manual before the cards loaded</b> — ${f(tr.manEarly.trend.said)} vs ${f(tr.manEarly.trend.notSaid)}, ${pval(tr.manEarly.trend.interaction.p)}.` }, host);
  }

  /* 4 · robustness strip */
  function strip(host) {
    if (!D || !D.strip) return miss(host);
    host.innerHTML = '';
    let which = 'diff', kind = 'adj';
    btnBar(host, 'Estimate', [['diff', 'Noticers minus never-said'], ['said', 'Noticers'], ['notSaid', 'Never said']], which, k => { which = k; draw(); });
    btnBar(host, 'Scale', [['adj', 'Adjusted'], ['raw', 'Raw (practice + game held fixed)']], kind, k => { kind = k; draw(); });
    const box = h('div', {}, host);
    function draw() {
      const rows = [];
      let fam = null;
      D.strip.forEach(sp => {
        if (sp.family !== fam) { fam = sp.family; rows.push({ head: fam }); }
        const z = which === 'diff' ? sp.diff && sp.diff[kind] : sp[which] && sp[which][kind];
        if (!z) return;
        rows.push({ label: sp.label.replace('Main: ', '') + (sp.thin ? ' (too few before — not estimable)' : ''), est: z.est, lo: z.lo, hi: z.hi, p: z.p,
                    color: which === 'diff' ? css('--mark') : GC[which](),
                    sub: which === 'diff' ? '' : `${sp[which].people} people · ${pct(sp[which].before, 0)} → ${pct(sp[which].after, 0)} raw` });
      });
      diffForest(box, rows, { padL: 360, lim: 0.6, xLabel: which === 'diff' ? 'how much more noticers changed than non-noticers, percentage points' : 'change after the first illogical card, percentage points' });
    }
    draw();
  }

  /* 5 · what the expected-value model uses */
  function model(host) {
    if (!D || !D.model) return miss(host);
    forest(host, D.model.terms.map(t => ({ label: t.label.replace(' (per logit unit)', ''), b: t.b, lo: t.lo, hi: t.hi, p: t.p })), { padL: 300 });
    const w = D.model.worked;
    h('p', { class: 'note', html: `Each row: how the odds of taking a card change with that feature, the others held fixed (×1.00 = no change). The person term dominates: the model separates take from not-take with AUC ${num(D.model.auc, 2)} (0.5 = guessing), mostly by knowing who is deciding. Worked example (${w.pid}, session ${w.run}): a ${w.ncolours}-type mission needing ${w.ndrones} drones, minute ${num(w.minute, 1)}, ${w.queued} waiting, by someone who takes cards ${pct(w.personRate, 0)} of the time elsewhere → expected ${pct(w.expected, 0)}; they ${w.took ? 'took' : 'did not take'} one, so the residual is ${sgn(w.res, 2)}.` }, host);
  }

  /* 6 · old chart dots as surprise scores */
  function oldDots(host) {
    if (!D || !D.oldDots) return miss(host);
    const Z = D.oldDots.z;
    const W = 700, H = 280, padL = 48, padR = 20, padT = 16, padB = 44;
    const s = svgRoot(host, W, H);
    const rels = [...new Set(Z.map(z => z.rel))].sort((a, b) => a - b);
    const x = v => padL + (W - padL - padR) * ((rels.indexOf(v) + 0.5) / rels.length);
    const y = v => H - padB - (H - padB - padT) * ((Math.max(-3, Math.min(3, v)) + 3) / 6);
    el('rect', { x: padL, y: y(1.96), width: W - padL - padR, height: y(-1.96) - y(1.96), fill: css('--mark-soft'), opacity: .25 }, s);
    [-3, -1.96, 0, 1.96, 3].forEach(v => el('text', { x: padL - 6, y: y(v) + 4, 'text-anchor': 'end', fill: css('--ink-3'), 'font-size': 10.5, 'font-family': css('--mono') }, s).textContent = v);
    el('line', { x1: padL, x2: W - padR, y1: y(0), y2: y(0), stroke: css('--line') }, s);
    rels.forEach(rv => el('text', { x: x(rv), y: H - padB + 16, 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 10.5, 'font-family': css('--mono') }, s).textContent = (rv > 0 ? '+' : '') + rv);
    el('text', { x: (padL + W) / 2, y: H - 8, 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 11 }, s).textContent = 'old chart position (counting every decision); y = how surprising the dot is given its missions and people (z)';
    Z.forEach(z => {
      const off = z.group === 'said' ? -4 : 4;
      const c = el('circle', { cx: x(z.rel) + off, cy: y(z.z), r: 3 + Math.sqrt(z.n), fill: GC[z.group](), opacity: .8, stroke: css('--surface') }, s);
      hoverable(c, `<b>${GL[z.group]} · ${z.rel > 0 ? '+' : ''}${z.rel}</b><br>n = ${z.n} · observed ${pct(z.raw, 0)} vs expected ${pct(z.exp, 0)}<br>z = ${z.z}`);
    });
    legend(host, [{ label: GL.said, color: GC.said() }, { label: GL.notSaid, color: GC.notSaid() }, { label: 'band: |z| < 1.96, where 95% of dots fall by chance', color: css('--mark-soft') }]);
    const d8 = D.oldDots.dip8, pl = D.oldDots.plateau;
    h('p', { class: 'note', html: `${Z.filter(z => Math.abs(z.z) > 1.96).length} of ${Z.length} dots fall outside the band; about ${(0.05 * Z.length).toFixed(1)} would by chance. `
      + `<b>+8</b>: ${d8.n} decisions (one per person), ${pct(d8.took, 0)} took a card vs ${pct(d8.exp, 0)} expected; the ${d8.declined} who declined are ${d8.declinedPeople.length} different people; the same people took ${pct(d8.samePeopleElsewhere, 0)} on their other later three-type missions. `
      + `<b>Never-said +2/+3</b>: ${pl.n} decisions from ${pl.people.length} people, all took a card where ${pct(pl.exp, 0)} was expected, during busy moments (${num(pl.queue, 1)} missions waiting).` }, host);
  }

  /* 7 · who the two groups are */
  function people(host) {
    if (!D || !D.profile) return miss(host);
    host.innerHTML = '';
    const C = D.profile.compare;
    tiles(host, [
      { v: `${pct(C.took.said, 0)} vs ${pct(C.took.notSaid, 0)}`, k: 'took a card, all decisions', s: `noticers vs never-said · ${pval(C.took.p)}` },
      { v: `${pct(C.pre3.said, 0)} vs ${pct(C.pre3.notSaid, 0)}`, k: 'three-type, BEFORE the first illogical card', s: `${pval(C.pre3.p)} — they start alike` },
      { v: `${pct(C.suggest.said, 0)} vs ${pct(C.suggest.notSaid, 0)}`, k: 'tactical plans with Suggest pressed', s: pval(C.suggest.p) },
    ]);
    const box = h('div', { style: 'display:flex;gap:8px;flex-wrap:wrap' }, host);
    const V = D.odd.views.three;
    ['said', 'notSaid'].forEach(g => {
      const pairs = V[g].bins.persons.map(pp => {
        const aft = Object.keys(pp.raw).filter(k => k !== 'before' && k !== 'card');
        const nA = aft.reduce((a, k) => a + pp.n[k], 0);
        if (pp.raw.before == null || !nA) return null;
        return { label: `${pp.pid} (before n ${pp.n.before}, after n ${nA})`, a: pp.raw.before, b: aft.reduce((a, k) => a + pp.raw[k] * pp.n[k], 0) / nA };
      }).filter(Boolean);
      const cell = h('div', { style: 'flex:1 1 320px;min-width:0' }, box);
      h('div', { text: GL[g] + ` — ${pairs.length} people with three-type missions both sides`, style: 'font-weight:600;font-size:13px;color:' + GC[g]() }, cell);
      const c2 = h('div', {}, cell);
      if (pairs.length) slopes(c2, pairs, { aLabel: 'before the card', bLabel: 'after', height: 240 });
    });
    h('p', { class: 'note', text: `Three-type missions, raw. ${D.profile.notSaidNarrated} of the ${D.profile.notSaidN} never-said people were recorded narrating during play, so their silence is some evidence they did not remark on it — but not that they did not see it.` }, host);
  }

  /* 8 · spoken anchor */
  function spoken(host) {
    if (!D || !D.spoken) return miss(host);
    host.innerHTML = '';
    let sample = 'All';
    btnBar(host, 'Missions', [['All', 'All missions'], ['3', 'Three-type']], sample, k => { sample = k; draw(); });
    const box = h('div', {}, host), cap = h('p', { class: 'note' }, host);
    function draw() {
      const pairs = D.spoken.people.filter(p => p['before' + sample] != null && p['after' + sample] != null)
        .map(p => ({ label: `${p.pid} — ${p.strict ? 'strict' : 'broad'}: ${p.gist} (s${p.run} ${Math.round(p.t)} s; before n ${p['nBefore' + sample]}, after n ${p['nAfter' + sample]})`,
                     a: p['before' + sample], b: p['after' + sample] }));
      slopes(box, pairs, { aLabel: 'before saying it', bLabel: 'after', height: 260 });
      const st = D.spoken.strict[sample === 'All' ? 'all' : 'three'].test;
      cap.innerHTML = st ? `Strict remarks (${st.people} people): ${pct(st.before, 0)} → ${pct(st.after, 0)}; adjusted ${ppts(st.adj.est)} [${ppts(st.adj.lo)}, ${ppts(st.adj.hi)}], ${pval(st.adj.p)}; ${st.lower} fell, ${st.higher} rose. `
        + `Timing-matched placebo ${pval(D.spoken.strict[sample === 'All' ? 'all' : 'three'].placebo.p)}. Hover a line for the remark.` : '';
    }
    draw();
  }

  /* 9 · refusal and failure anchors */
  function anchors(host) {
    if (!D || !D.refusal) return miss(host);
    const rows = [];
    const OUT = [['strategicAll', 'Strategy cards taken, all missions'], ['strategic3', 'Strategy cards taken, three-type'], ['tactical', 'Tactical Suggest pressed']];
    [['refusal', 'After the first “No workable plan” from Suggest'], ['blind', 'After the first WRONG “No workable plan”'], ['failure', 'After the first drone failure on a task']].forEach(([k, lab]) => {
      const A = D.refusal[k];
      if (!A) return;
      rows.push({ head: `${lab} (${A.people} people)` });
      OUT.forEach(([o, ol]) => {
        const t = A[o] && A[o].test;
        if (!t || !t.adj) return;
        rows.push({ label: ol, est: t.adj.est, lo: t.adj.lo, hi: t.adj.hi, p: t.adj.p, color: o === 'tactical' ? css('--s-tac') : css('--s-strat'),
                    sub: `raw ${pct(t.before, 0)} → ${pct(t.after, 0)} · expected ${pct(t.expBefore, 0)} → ${pct(t.expAfter, 0)} · ${t.lower} fell, ${t.higher} rose · placebo ${pval(A[o].placebo.p)}` });
      });
    });
    const T = D.odd.tacticalAfterOdd.test;
    rows.push({ head: 'After the first illogical strategy card (33 people)' });
    rows.push({ label: 'Tactical Suggest pressed', est: T.adj.est, lo: T.adj.lo, hi: T.adj.hi, p: T.adj.p, color: css('--s-tac'),
                sub: `raw ${pct(T.before, 0)} → ${pct(T.after, 0)}` });
    diffForest(host, rows, { padL: 280, lim: 0.3, xLabel: 'adjusted change after the moment, percentage points' });
  }

  /* 10 · dominated cards and previews */
  function dominated(host) {
    if (!D || !D.dominated) return miss(host);
    host.innerHTML = '';
    const R = D.dominated.three, P = D.dominated.previews;
    tiles(host, [
      { v: pct(D.dominated.rate, 0), k: 'of all decisions had a dominated Conservative card', s: `${pct(D.dominated.byTypes['3'].dom, 0)} of three-type, ${pct(D.dominated.byTypes['1'].dom, 0)} of one-type` },
      { v: `${P.both} of ${P.n}`, k: 'decisions where both cards were highlighted', s: `${P.bothPeople} people` },
      { v: `${P.all['0']}`, k: 'decisions where no card was highlighted', s: 'manual without clicking a card' },
    ]);
    const cats = [['cons', 'Conservative', '--r-cons'], ['aggr', 'Aggressive', '--r-aggr'], ['man', 'Manual', '--r-man']];
    const W = 700, H = 250, padL = 50, padB = 44, padT = 14;
    const s = svgRoot(h('div', {}, host), W, H);
    const y = v => H - padB - (H - padB - padT) * (v / 0.6);
    [0, .2, .4, .6].forEach(v => { el('line', { x1: padL, x2: W - 10, y1: y(v), y2: y(v), stroke: css('--grid') }, s);
      el('text', { x: padL - 6, y: y(v) + 4, 'text-anchor': 'end', fill: css('--ink-3'), 'font-size': 11, 'font-family': css('--mono') }, s).textContent = pct(v, 0); });
    const gw = (W - padL - 10) / 2;
    R.forEach((rw, gi) => {
      const gx = padL + gi * gw;
      el('text', { x: gx + gw / 2, y: H - padB + 18, 'text-anchor': 'middle', fill: css('--ink-2'), 'font-size': 12 }, s)
        .textContent = rw.dom ? `Conservative dominated (n ${rw.n})` : `a real trade-off (n ${rw.n})`;
      el('text', { x: gx + gw / 2, y: H - padB + 33, 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 10.5 }, s)
        .textContent = `Cons ${num(rw.consN, 1)} drones, ${num(rw.consEta, 0)} s · Aggr ${num(rw.aggrN, 1)} drones, ${num(rw.aggrEta, 0)} s`;
      cats.forEach(([k, lab, tok], ci) => {
        const bx = gx + gw * 0.18 + ci * gw * 0.22, bw = gw * 0.17;
        const r_ = el('rect', { x: bx, y: y(rw[k]), width: bw, height: y(0) - y(rw[k]), rx: 3, fill: css(tok) }, s);
        const c = rw[k + 'CI'];
        if (c) el('line', { x1: bx + bw / 2, x2: bx + bw / 2, y1: y(c[0]), y2: y(c[1]), stroke: css('--ink-2'), 'stroke-width': 1.5 }, s);
        hoverable(r_, `<b>${lab}</b>, ${rw.dom ? 'dominated' : 'trade-off'} cards<br>${pct(rw[k], 0)}` + (c ? ` [${pct(c[0], 0)}, ${pct(c[1], 0)}]` : '') + `<br>n = ${rw.n} decisions, ${rw.people} people`);
      });
    });
    legend(host, cats.map(([k, lab, tok]) => ({ label: lab, color: css(tok) })));
    const m = D.dominated.model;
    if (m) h('p', { class: 'note', text: `Three-type, non-residual missions. Allowing for mission size, tasks and game, a dominated Conservative card is chosen with odds ×${num(m.est, 2)} [${num(m.lo, 2)}, ${num(m.hi, 2)}], ${pval(m.p)} — no sign of avoidance, though the interval cannot rule out a moderate one. Bars: 95% intervals from resampling people.` }, host);
  }

  /* 11 · visible vs hidden flaws */
  function visibility(host) {
    if (!D || !D.visibility) return miss(host);
    host.innerHTML = '';
    const V = D.visibility, n = V.strategic.people;
    const sp = V.tactical.spokenTac || [];
    barsH(host, [
      { label: 'Saw an illogical strategy card', value: V.strategic.exposed / n, color: css('--s-strat'), sub: `${V.strategic.oddDecisions} of ${V.strategic.decisions} decisions (${pct(V.strategic.oddShare, 0)})` },
      { label: 'Said the cards over-allocate (C12)', value: V.strategic.c12 / n, color: css('--s-strat'), sub: `${V.strategic.c12} people; ${V.strategic.saidMain} including in-play remarks` },
      { label: 'Got a WRONG “No workable plan”', value: V.tactical.blindPeople / n, color: css('--s-tac'), sub: `${V.tactical.blindPresses} wrong refusals of ${V.tactical.refusals}` },
      { label: 'Said a tactical plan was flawed (C13)', value: V.tactical.c13 / n, color: css('--s-tac'), sub: `${V.tactical.c13} people; ${V.tactical.c13AmongBlind} of them among those wrongly refused` },
      { label: 'Said why Suggest refused, in play', value: 1 / n, color: css('--s-tac'), sub: `${sp.filter(x => x.blind).length} reacted aloud to a wrong refusal; 1 named the cause` },
    ], { padL: 250, fmt: v => `${Math.round(v * n)} of ${n}` , max: 1 });
  }

  /* 12 · when the first illogical card arrives */
  function timing(host) {
    if (!D || !D.odd || !D.odd.timing.perPerson) return miss(host);
    const P = D.odd.timing.perPerson;
    const bins = [['1st', p => p.seq === 1], ['2nd', p => p.seq === 2], ['3rd', p => p.seq === 3], ['4th–6th', p => p.seq >= 4 && p.seq <= 6],
                  ['7th–10th', p => p.seq >= 7 && p.seq <= 10], ['11th+', p => p.seq > 10]];
    barsGrouped(host, bins.map(b => b[0]), ['said', 'notSaid'].map(g => ({ label: GL[g], color: GC[g](),
      values: bins.map(([, f]) => P.filter(p => (g === 'said') === !!p.said).filter(f).length) })), { height: 220, fmt: v => num(v, 0) });
    legend(host, [{ label: GL.said, color: GC.said() }, { label: GL.notSaid, color: GC.notSaid() }]);
    h('p', { class: 'note', text: `Which of their strategic decisions (in study order, both sessions) was each person’s first illogical card. ${D.odd.timing.firstOrSecond} of 33 met it on their 1st or 2nd decision, so “before the card” is usually one or two decisions at the very start.` }, host);
  }

  Object.assign(CH, {
    'flaw.events': events, 'flaw.nth': nth, 'flaw.oddMissions': oddMissions, 'flaw.strip': strip,
    'flaw.model': model, 'flaw.oldDots': oldDots, 'flaw.people': people, 'flaw.spoken': spoken,
    'flaw.anchors': anchors, 'flaw.dominated': dominated, 'flaw.visibility': visibility, 'flaw.timing': timing,
  });
})();
