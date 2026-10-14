(() => {
  const D = (typeof DATA !== 'undefined' && DATA.pass2) ? DATA.pass2.flaw : null;
  const miss = (host, msg) => { host.innerHTML = ''; h('p', { class: 'note', text: msg || 'Data for this chart is missing — rerun scripts/register/pass2/flaw.py.' }, host); };
  const GC = { said: () => css('--warn'), notSaid: () => css('--s-strat') };
  const GL = { said: 'Said they noticed', notSaid: 'Never said so' };
  const ppts = v => (v >= 0 ? '+' : '') + (100 * v).toFixed(0) + ' pts';
  // every y axis says what it is a share of
  const Y_TOOK = 'card taken, % of decisions';
  function yTitle(s, text, padT, bottom) {
    const yc = (padT + bottom) / 2;
    el('text', { x: 13, y: yc, transform: `rotate(-90 13 ${yc})`, 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 10.5 }, s).textContent = text;
  }

  /* ── generic: categories on x, proportion on y, points with CI bars, optional faint person lines ── */
  function catLines(host, cats, series, o = {}) {
    const W = 700, H = o.height || 300, padL = 64, padR = 130, padT = 18, padB = 46;
    const s = svgRoot(host, W, H);
    yTitle(s, o.yLabel || Y_TOOK, padT, H - padB);
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
    const labs = [];
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
      if (!se.dash) labs.push({ y: y(last.y) + 4 + (o.labelNudge ? o.labelNudge[si] || 0 : 0), color: se.color, label: se.label });
    });
    // end labels: push apart so two lines ending close together never print on top of each other
    labs.sort((a, b) => a.y - b.y);
    for (let i = 1; i < labs.length; i++) if (labs[i].y - labs[i - 1].y < 14) labs[i].y = labs[i - 1].y + 14;
    labs.forEach(l => { el('text', { x: W - padR + 8, y: l.y, fill: l.color, 'font-size': 11.5, 'font-weight': 600 }, s).textContent = l.label; });
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
    diffForest(host, rows, { padL: 280, lim: 0.3, xLabel: 'change after the moment in % of decisions (card taken / Suggest pressed), adjusted, percentage points' });
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
    const W = 700, H = 250, padL = 64, padB = 44, padT = 14;
    const s = svgRoot(h('div', {}, host), W, H);
    yTitle(s, 'chosen, % of three-type decisions', padT, H - padB);
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
    const sv = host.querySelectorAll('svg'); if (sv.length) yTitle(sv[sv.length - 1], 'people', 14, 180);
    legend(host, [{ label: GL.said, color: GC.said() }, { label: GL.notSaid, color: GC.notSaid() }]);
    h('p', { class: 'note', text: `Which of their strategic decisions (in study order, both sessions) was each person’s first illogical card. ${D.odd.timing.firstOrSecond} of 33 met it on their 1st or 2nd decision, so “before the card” is usually one or two decisions at the very start.` }, host);
  }

  /* ═════════════════════ pass 3 ═════════════════════ */
  const P3 = D && D.p3;
  const asRow = a => P3 && Array.isArray(a) ? Object.fromEntries(P3.fields.map((f, i) => [f, a[i]])) : a;
  const SAMPLE_BTN = [['all', 'All missions'], ['three', 'Three-type only'], ['few', 'One- & two-type only']];
  const SAMPLE_TXT = { all: 'all missions', three: 'three-type missions', few: 'one- and two-type missions' };
  const ORDER_BTN = [['all', 'Both game orders'], ['SH', 'Strategic-heavy first'], ['TH', 'Tactical-heavy first']];
  const ORDER_TXT = { all: '', SH: ' · strategic-heavy game first', TH: ' · tactical-heavy game first' };
  const GC3 = { everyone: () => css('--mark'), said: GC.said, notSaid: GC.notSaid };
  const GL3 = { everyone: 'Everyone', said: GL.said, notSaid: GL.notSaid };
  const lead = k => k === 'before' ? -2 : k === 'card' ? -1 : parseInt(k, 10);
  const sortKeys = ks => [...new Set(ks)].sort((a, b) => lead(a) - lead(b));
  const ci = (lo, hi) => lo != null && hi != null ? ` [${pct(lo, 0)}, ${pct(hi, 0)}]` : '';

  /* line + 95% band over ordered categories (decision number, minute); optional rug and an 'after the card' strip.
     Categories may carry `seg`: lines and bands are never joined across a change of seg (separate series, e.g. two
     sessions), and o.segBreaks draws a labelled divider at each break. */
  function bandChart(host, cats, series, o = {}) {
    const nR = (o.nRows || []).length, nH = nR ? 8 + 13 * nR : 0;
    const W = 700, H = (o.height || 290) + (o.strip ? 26 : 0) + (o.segLabels ? 14 : 0) + nH, padL = 64, padR = 130,
      padT = 18 + (o.segLabels ? 14 : 0), padB = 46 + (o.strip ? 26 : 0) + nH;
    const s = svgRoot(host, W, H);
    yTitle(s, o.yLabel || Y_TOOK, padT, H - padB);
    const lo = 0, hi = 1, span = W - padL - padR;
    const x = i => padL + span * ((i + 0.5) / cats.length);
    const y = v => H - padB - (H - padB - padT) * ((Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo));
    [0, .25, .5, .75, 1].forEach(v => {
      el('line', { x1: padL, x2: W - padR, y1: y(v), y2: y(v), stroke: css('--grid') }, s);
      el('text', { x: padL - 8, y: y(v) + 4, 'text-anchor': 'end', fill: css('--ink-3'), 'font-size': 11, 'font-family': css('--mono') }, s).textContent = pct(v, 0);
    });
    cats.forEach((c, i) => el('text', { x: x(i), y: H - padB + 16, 'text-anchor': 'middle', fill: css('--ink-2'), 'font-size': cats.length > 16 ? 10 : 11 }, s).textContent = c.label);
    if (o.xLabel) el('text', { x: (padL + W - padR) / 2, y: H - 8, 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 11 }, s).textContent = o.xLabel;
    const segOf = i => cats[i].seg != null ? cats[i].seg : 0;
    const segs = [...new Set(cats.map((c, i) => segOf(i)))];
    // dividers between segments, and a label over each
    cats.forEach((c, i) => {
      if (i && segOf(i) !== segOf(i - 1)) {
        const xd = (x(i - 1) + x(i)) / 2;
        el('line', { x1: xd, x2: xd, y1: padT - 4, y2: H - padB + 4, stroke: css('--ink-2'), 'stroke-width': 1.5, 'stroke-dasharray': '4 3' }, s);
      }
    });
    if (o.segLabels) segs.forEach(sg => {
      const ii = cats.map((c, i) => i).filter(i => segOf(i) === sg);
      el('text', { x: (x(ii[0]) + x(ii[ii.length - 1])) / 2, y: padT - 8, 'text-anchor': 'middle', fill: css('--ink-2'), 'font-size': 11.5, 'font-weight': 600 }, s)
        .textContent = o.segLabels[sg] || '';
    });
    const idx = Object.fromEntries(cats.map((c, i) => [c.key, i]));
    (o.rug || []).forEach(rg => {
      const xx = padL + span * Math.max(0, Math.min(1, rg.f));
      el('line', { x1: xx, x2: xx, y1: H - padB - 9, y2: H - padB, stroke: rg.color, 'stroke-width': 2, opacity: .85 }, s);
      const hit = el('rect', { x: xx - 3, y: H - padB - 12, width: 6, height: 14, fill: 'transparent' }, s);
      hoverable(hit, rg.tip);
    });
    if (o.rug && o.rug.length) el('text', { x: W - padR + 8, y: H - padB - 1, fill: css('--ink-3'), 'font-size': 10 }, s).textContent = '▮ first illogical card';
    const labs = [];
    series.forEach((se, si) => {
      const off = (si - (series.length - 1) / 2) * 6;
      const pts = se.points.filter(p => p && p.y != null && idx[p.key] != null);
      if (!pts.length) return;
      segs.forEach(sg => {
        const spAll = pts.filter(p => segOf(idx[p.key]) === sg);
        if (!spAll.length) return;
        const sp = spAll.filter(p => !p.thin), thin = spAll.filter(p => p.thin);
        if (thin.length) {
          const tp = (sp.length ? [sp[sp.length - 1]] : []).concat(thin);
          if (tp.length > 1) el('path', { d: tp.map((p, i) => (i ? 'L' : 'M') + (x(idx[p.key]) + off) + ' ' + y(p.y)).join(' '), fill: 'none', stroke: se.color,
                                          'stroke-width': 1.3, 'stroke-dasharray': '2 3', opacity: .6 }, s);
        }
        if (!sp.length) return;
        const withCI = sp.filter(p => p.lo != null && p.hi != null);
        if (withCI.length > 1 && !se.dash) {
          const up = withCI.map(p => `${x(idx[p.key]) + off},${y(p.hi)}`), dn = withCI.slice().reverse().map(p => `${x(idx[p.key]) + off},${y(p.lo)}`);
          el('polygon', { points: up.concat(dn).join(' '), fill: se.color, opacity: se.dash ? .07 : .13 }, s);
        }
        const pa = { d: sp.map((p, i) => (i ? 'L' : 'M') + (x(idx[p.key]) + off) + ' ' + y(p.y)).join(' '), fill: 'none', stroke: se.color,
                     'stroke-width': se.dash ? 1.8 : 2.2, 'stroke-linejoin': 'round' };
        if (se.dash) pa['stroke-dasharray'] = '5 4';
        el('path', pa, s);
      });
      pts.forEach(p => {
        const cx = x(idx[p.key]) + off;
        if (p.lo != null && p.hi != null && !p.thin) el('line', { x1: cx, x2: cx, y1: y(p.lo), y2: y(p.hi), stroke: se.color, 'stroke-width': 1.2, opacity: .55 }, s);
        const hollow = p.thin || p.n < 8, rad = o.sizeByPeople && p.people != null ? 2.2 + 0.28 * Math.min(p.people, 18) : (p.n < 8 ? 3 : 4.5);
        el('circle', { cx, cy: y(p.y), r: rad, fill: hollow ? css('--surface') : se.color, stroke: se.color, 'stroke-width': 1.5, opacity: p.thin ? .6 : 1 }, s);
        const hit = el('circle', { cx, cy: y(p.y), r: 11, fill: 'transparent' }, s);
        hoverable(hit, `<b>${se.label}</b> · ${cats[idx[p.key]].tipLabel || cats[idx[p.key]].label}<br>${pct(p.y, 0)}${ci(p.lo, p.hi)}` + (p.tip ? '<br>' + p.tip : ''));
      });
      const last = pts[pts.length - 1];
      labs.push({ y: y(last.y) + 4, color: se.color, label: se.label });
    });
    labs.sort((a, b) => a.y - b.y);
    for (let i = 1; i < labs.length; i++) if (labs[i].y - labs[i - 1].y < 14) labs[i].y = labs[i - 1].y + 14;
    labs.forEach(l => { el('text', { x: W - padR + 8, y: l.y, fill: l.color, 'font-size': 11.5, 'font-weight': 600 }, s).textContent = l.label; });
    if (o.strip) {
      const sy = H - padB + 26, cw = span / cats.length;
      el('text', { x: padL - 8, y: sy + 9, 'text-anchor': 'end', fill: css('--ink-3'), 'font-size': 10 }, s).textContent = 'after card';
      cats.forEach((c, i) => {
        const v = o.strip[c.key];
        if (v == null) return;
        const rc = el('rect', { x: x(i) - cw / 2 + 2, y: sy, width: cw - 4, height: 11, rx: 2, fill: css('--bad'), opacity: 0.06 + 0.8 * v }, s);
        hoverable(rc, `${c.tipLabel || c.label}: ${pct(v, 0)} of these decisions came at or after the person’s first illogical card`);
      });
    }
    (o.nRows || []).forEach((nr, ri) => {
      const ry = H - padB + (o.strip ? 52 : 32) + ri * 13;
      el('text', { x: padL - 8, y: ry, 'text-anchor': 'end', fill: nr.color, 'font-size': 10 }, s).textContent = nr.label;
      cats.forEach((c, i) => {
        const v = nr.vals[c.key];
        if (v == null) return;
        el('text', { x: x(i), y: ry, 'text-anchor': 'middle', fill: nr.color, 'font-size': 10, 'font-family': css('--mono'),
                     opacity: nr.min && v < nr.min ? .45 : 1 }, s).textContent = v;
      });
    });
  }

  /* grouped vertical bars with 95% whiskers. series: [{label, color, vals: [{v, lo, hi, tip} | null]}] */
  function barsCI(host, cats, series, o = {}) {
    const W = 700, H = o.height || 260, padL = 64, padR = 10, padT = 16, padB = o.padB || 46;
    const s = svgRoot(host, W, H);
    yTitle(s, o.yLabel || Y_TOOK, padT, H - padB);
    const y = v => H - padB - (H - padB - padT) * Math.max(0, Math.min(1, v));
    [0, .25, .5, .75, 1].forEach(v => {
      el('line', { x1: padL, x2: W - padR, y1: y(v), y2: y(v), stroke: css('--grid') }, s);
      el('text', { x: padL - 8, y: y(v) + 4, 'text-anchor': 'end', fill: css('--ink-3'), 'font-size': 11, 'font-family': css('--mono') }, s).textContent = pct(v, 0);
    });
    const band = (W - padL - padR) / cats.length, gap = 3;
    const bw = Math.min(46, (band - 14 - gap * (series.length - 1)) / series.length);
    cats.forEach((c, ci_) => {
      const cx = padL + band * ci_ + band / 2;
      String(c).split('\n').forEach((ln, li) => el('text', { x: cx, y: H - padB + 16 + li * 13, 'text-anchor': 'middle', fill: css(li ? '--ink-3' : '--ink-2'),
                                                             'font-size': li ? 10.5 : 11.5 }, s).textContent = ln);
      const tot = series.length * bw + gap * (series.length - 1);
      series.forEach((se, si) => {
        const d = se.vals[ci_];
        if (!d || d.v == null) return;
        const bx = cx - tot / 2 + si * (bw + gap);
        el('rect', { x: bx, y: y(d.v), width: bw, height: y(0) - y(d.v), rx: 3, fill: se.color, opacity: d.faint ? .45 : 1 }, s);
        if (d.lo != null) el('line', { x1: bx + bw / 2, x2: bx + bw / 2, y1: y(d.lo), y2: y(d.hi), stroke: css('--ink-2'), 'stroke-width': 1.4 }, s);
        if (o.values !== false) el('text', { x: bx + bw / 2, y: (d.hi != null ? y(d.hi) : y(d.v)) - 4, 'text-anchor': 'middle', fill: css('--ink-2'),
                                             'font-size': 10, 'font-family': css('--mono') }, s).textContent = pct(d.v, 0);
        const hit = el('rect', { x: bx, y: padT, width: bw, height: H - padB - padT, fill: 'transparent' }, s);
        hoverable(hit, `<b>${se.label}</b> · ${String(c).replace('\n', ' · ')}<br>${pct(d.v, 0)}${ci(d.lo, d.hi)}${d.tip ? '<br>' + d.tip : ''}`);
      });
    });
    el('line', { x1: padL, x2: W - padR, y1: y(0), y2: y(0), stroke: css('--line') }, s);
    (o.dividers || []).forEach(i => {
      const xd = padL + band * i;
      el('line', { x1: xd, x2: xd, y1: padT, y2: H - 6, stroke: css('--line'), 'stroke-width': 1.2, 'stroke-dasharray': '3 3' }, s);
    });
  }

  const evLabel = k => k === 'before' ? 'before' : k === 'card' ? 'the card' : /^-\d/.test(k) ? (k === '-4' ? '≤ −4' : '−' + k.slice(1)) : '+' + k;
  const P4 = D && D.p4;
  // sort key for event-study positions: steps before the card are negative, the card 0, after-card bins positive
  const leadE = k => k === 'before' ? -10 : k === 'card' ? 0 : parseInt(k, 10);

  /* 1b · the event study, with every step / pairs / threes and all three mission samples */
  function events2(host) {
    if (!P3 || !P3.events) return miss(host);
    host.innerHTML = '';
    let sample = 'all', w = '2', mode = 'plain', pre = 'pooled';
    btnBar(host, 'Missions', SAMPLE_BTN, sample, k => { sample = k; draw(); });
    btnBar(host, 'Grouping', [['1', 'Every step'], ['2', 'Every pair'], ['3', 'Groups of three']], w, k => { w = k; draw(); });
    btnBar(host, 'Before the card', [['pooled', 'One pooled point'], ['steps', 'Steps −3, −2, −1'], ['matched', 'Steps, only people with 3+ before (pairs)']], pre, k => { pre = k; draw(); });
    btnBar(host, 'Show', [['plain', 'Observed'], ['obs', 'Observed + each person'], ['exp', 'Observed + expected'], ['adj', 'Adjusted']], mode, k => { mode = k; draw(); });
    const box = h('div', {}, host), cap = h('p', { class: 'note' }, host);
    function draw() {
      const V = P3.events[sample];
      if (!V || !V.said || !V.said[w]) return miss(box);
      const PR = P4 && P4.pre && P4.pre[sample];
      const preMode = PR ? pre : 'pooled';
      const binsOf = g => {
        if (preMode === 'matched') return PR[g].matched.bins;
        const after = V[g][w].bins;
        return preMode === 'steps' ? PR[g].bins.concat(after.filter(b => b.bin !== 'before')) : after;
      };
      const keys = [...new Set(['said', 'notSaid'].flatMap(g => binsOf(g).map(b => b.bin)))].sort((a, b) => leadE(a) - leadE(b));
      const cats = keys.map(k => ({ key: k, label: evLabel(k) }));
      const series = [], persons = [];
      ['said', 'notSaid'].forEach(g => {
        const B = binsOf(g), col = GC[g]();
        const tipB = b => binTip(b) + (b.n < 8 ? '<br><i>fewer than 8 decisions — read with care</i>' : '');
        if (mode === 'adj') series.push({ label: GL[g], color: col, points: B.map(b => ({ key: b.bin, y: b.adj, lo: b.adjLo, hi: b.adjHi, tip: tipB(b) })) });
        else series.push({ label: GL[g], color: col, points: B.map(b => ({ key: b.bin, y: b.raw, lo: b.rawLo, hi: b.rawHi, tip: tipB(b) })) });
        if (mode === 'exp') series.push({ label: 'expected', color: col, dash: true, points: B.map(b => ({ key: b.bin, y: b.exp, tip: tipB(b) })) });
        if (mode === 'obs' && preMode !== 'matched') V[g][w].persons.forEach(pp => persons.push({ pid: pp.pid, group: GL[g], vals: pp.raw, n: pp.n, color: col }));
      });
      const firstAfter = keys.findIndex(k => leadE(k) >= 0);
      catLines(box, cats, series, { persons, divider: firstAfter, dividerLabel: 'first illogical card',
        yLabel: mode === 'adj' ? 'card taken, % (adjusted)' : Y_TOOK,
        xLabel: `${SAMPLE_TXT[sample]}: ${preMode === 'pooled' ? 'before' : 'steps before'}, the card's own decision, then the person's 1st, 2nd, … such decision after it`,
        labelNudge: mode === 'exp' ? [0, 0, 0, 0] : [-6, 6] });
      const t = g => V[g].test, f = z => `${ppts(z.est)} [${ppts(z.lo)}, ${ppts(z.hi)}], ${pval(z.p)}`;
      const ok = g => t(g) && t(g).adj && t(g).peopleBoth >= 6;
      const old = D.odd && D.odd.views[sample];
      let txt = `Bars are 95% intervals from resampling people; later positions rest on fewer people (hover for n). ${mode === 'obs' && preMode !== 'matched' ? 'Faint lines: each person. ' : ''}`
        + (ok('said') && ok('notSaid')
          ? `Before → after (the card's own decision left out): noticers ${pct(t('said').before, 0)} → ${pct(t('said').after, 0)}, adjusted ${f(t('said').adj)}; `
            + `never said ${pct(t('notSaid').before, 0)} → ${pct(t('notSaid').after, 0)}, adjusted ${f(t('notSaid').adj)}. `
            + (V.interaction && V.interaction.adj ? `Difference ${f(V.interaction.adj)}` : '') + (old && old.perm ? `; label-shuffle ${pval(old.perm.p)}.` : '.')
          : `On ${SAMPLE_TXT[sample]} almost nobody has a decision <i>before</i> their first illogical card (${t('said') ? t('said').peopleBoth : 0} noticers and ${t('notSaid') ? t('notSaid').peopleBoth : 0} others do), because that card only ever appears on these missions — so no before/after change is estimated; read the after-card trend only.`);
      if (!PR && pre !== 'pooled') txt += ' <b>Steps before the card are not available on this mission sample</b> (only 2 people per group have any such decision), so the pooled point is shown.';
      if (preMode === 'steps') {
        const pw = PR.said.peopleWith, pn = PR.notSaid.peopleWith;
        txt += ` <b>Steps before the card:</b> −1 is everyone's last decision before it (${pw['1']} noticers, ${pn['1']} others); −2 and −3 exist only for the ${pw['3']} + ${pn['3']} people with at least three, so each of those points is 8 decisions and its interval spans about ±35 points. “≤ −4” pools everything earlier.`;
      }
      if (preMode === 'matched') {
        txt += ` <b>Matched view:</b> only the ${PR.said.matched.people.length} noticers and ${PR.notSaid.matched.people.length} never-said people with at least three decisions before the card, so every point before and after is the same people. All of them played the tactical-heavy game first; for 9 of the 16 the card (and so everything “after”) came at the start of session 2. Pairs grouping only.`;
      }
      if (mode === 'exp' && P4 && P4.expected && P4.expected[sample === 'few' ? 'all' : sample]) {
        const E = P4.expected[sample === 'few' ? 'all' : sample], a = E.said.after, b = E.notSaid.after;
        txt += ` Dashed lines with hollow dots: the model's <i>expected</i> value for the same decisions, in each group's colour.` + ` <b>Why noticers' expected line is lower:</b> the model's strongest term is each person's own take rate on all their <i>other</i> decisions (${pct(E.said.all.personRate, 0)} for noticers, ${pct(E.notSaid.all.personRate, 0)} for never-said), and most of those decisions come after the card, where noticers take fewer. With that person term set to everyone's average, the expected value after the card is ${pct(a.expMission, 0)} for noticers and ${pct(b.expMission, 0)} for never-said: the missions themselves are alike.`;
      }
      cap.innerHTML = txt;
      tableFor(box, ['Group · position', 'n', 'people', 'raw [95% CI]', 'expected', 'adjusted [95% CI]'],
        ['said', 'notSaid'].flatMap(g => binsOf(g).map(b => [GL[g] + ' · ' + evLabel(b.bin), b.n, b.people, `${pct(b.raw, 0)} [${pct(b.rawLo, 0)}, ${pct(b.rawHi, 0)}]`,
          pct(b.exp, 0), `${pct(b.adj, 0)} [${pct(b.adjLo, 0)}, ${pct(b.adjHi, 0)}]`])));
    }
    draw();
  }

  /* 2b · one dot per person per position, any sample */
  function nth2(host) {
    if (!P3 || !P3.events) return miss(host);
    host.innerHTML = '';
    let sample = 'all';
    btnBar(host, 'Missions', SAMPLE_BTN, sample, k => { sample = k; draw(); });
    const box = h('div', {}, host), cap = h('p', { class: 'note' }, host);
    function draw() {
      const V = P3.events[sample];
      const ks = [...new Set(['said', 'notSaid'].flatMap(g => V[g].k.map(p => p.k)))].sort((a, b) => a - b);
      if (!ks.length) return miss(box);
      const cats = ks.map(k => ({ key: String(k), label: k === 0 ? 'card' : (k > 0 ? '+' : '') + k }));
      const series = ['said', 'notSaid'].map(g => ({ label: GL[g], color: GC[g](),
        points: V[g].k.map(p => ({ key: String(p.k), y: p.raw, lo: p.lo, hi: p.hi,
          tip: `n = ${p.n} decisions from ${p.people} people<br>expected ${pct(p.exp, 0)} · ${num(p.ndrones, 1)} drones · ${num(p.queue, 1)} waiting · minute ${num(p.minute, 1)}` })) }));
      const d0 = ks.findIndex(k => k >= 0);
      catLines(box, cats, series, { height: 290, divider: d0, dividerLabel: 'first illogical card',
        xLabel: `Nth ${SAMPLE_TXT[sample].replace(' missions', '')} decision before (−) / after (+) the first illogical card` });
      cap.textContent = `Each dot is at most one decision per person (n = people at that position), so its 95% interval (Wilson) is wide: at n ≈ 15 a single dot cannot separate 50% from 75%. `
        + (sample === 'all' ? 'On all missions the card’s own decision appears as “card”. ' : '')
        + 'The grouped event-study chart above is the readable version of the same decisions.';
    }
    draw();
  }

  /* 7b · who the two groups are, with the mission toggle */
  function people2(host) {
    if (!D || !D.profile || !P3) return miss(host);
    host.innerHTML = '';
    const C = D.profile.compare;
    tiles(host, [
      { v: `${pct(C.took.said, 0)} vs ${pct(C.took.notSaid, 0)}`, k: 'took a card, all decisions', s: `noticers vs never-said · ${pval(C.took.p)}` },
      { v: `${pct(C.pre3.said, 0)} vs ${pct(C.pre3.notSaid, 0)}`, k: 'three-type, BEFORE the first illogical card', s: `${pval(C.pre3.p)} — they start alike` },
      { v: `${pct(C.suggest.said, 0)} vs ${pct(C.suggest.notSaid, 0)}`, k: 'tactical plans with Suggest pressed', s: pval(C.suggest.p) },
    ]);
    let sample = 'all';
    btnBar(host, 'Missions', SAMPLE_BTN, sample, k => { sample = k; draw(); });
    const box = h('div', { style: 'display:flex;gap:8px;flex-wrap:wrap' }, host), cap = h('p', { class: 'note' }, host);
    function draw() {
      box.innerHTML = '';
      ['said', 'notSaid'].forEach(g => {
        const pairs = P3.events[sample][g]['3'].persons.map(pp => {
          const aft = Object.keys(pp.raw).filter(k => k !== 'before' && k !== 'card');
          const nA = aft.reduce((a, k) => a + pp.n[k], 0);
          if (pp.raw.before == null || !nA) return null;
          return { label: `${pp.pid} (before n ${pp.n.before}, after n ${nA})`, a: pp.raw.before, b: aft.reduce((a, k) => a + pp.raw[k] * pp.n[k], 0) / nA };
        }).filter(Boolean);
        const cell = h('div', { style: 'flex:1 1 320px;min-width:0' }, box);
        h('div', { text: GL[g] + ` — ${pairs.length} people with decisions both sides`, style: 'font-weight:600;font-size:13px;color:' + GC[g]() }, cell);
        const c2 = h('div', {}, cell);
        if (pairs.length) slopes(c2, pairs, { aLabel: 'before the card', bLabel: 'after', height: 240 });
        else h('p', { class: 'note', text: 'Nobody in this group has decisions of this kind on both sides of the card.' }, c2);
      });
      cap.textContent = `${SAMPLE_TXT[sample][0].toUpperCase() + SAMPLE_TXT[sample].slice(1)}, raw; the card's own decision is left out. `
        + `${D.profile.notSaidNarrated} of the ${D.profile.notSaidN} never-said people were recorded narrating during play, so their silence is some evidence they did not remark on it — but not that they did not see it.`;
    }
    draw();
  }

  const PEOPLE_BTN = [['both', 'Each group + everyone'], ['split', 'Noticers vs never-said'], ['everyone', 'Everyone only']];
  const groupsFor = grp => grp === 'everyone' ? ['everyone'] : grp === 'both' ? ['said', 'notSaid', 'everyone'] : ['said', 'notSaid'];
  const seriesFrom = (g, rows, mode) => ({ label: g === 'everyone' ? 'Everyone (pooled)' : GL3[g], color: GC3[g](), dash: g === 'everyone',
    points: rows.map(b => ({ key: b.key || b.bin, n: b.n, y: mode === 'adj' ? b.adj : b.raw, lo: mode === 'adj' ? b.adjLo : b.rawLo, hi: mode === 'adj' ? b.adjHi : b.rawHi,
      tip: `n = ${b.n} decisions from ${b.people} people${b.n < 8 ? ' (few — read with care)' : ''}<br>observed ${pct(b.raw, 0)} · adjusted ${pct(b.adj, 0)}`
        + `<br>${pct(b.aft, 0)} made at/after the person’s first illogical card · ${pct(b.three, 0)} on three-type missions` })) });

  /* use over session time, noticers and never-said and everyone, not aligned to anything */
  function overTime(host) {
    if (!P3 || !P3.time) return miss(host);
    host.innerHTML = '';
    let sess = '1', sample = 'all', order = 'all', grp = 'both', mode = 'raw';
    btnBar(host, 'Session', [['1', 'Session 1'], ['2', 'Session 2'], ['both', 'Both, pooled']], sess, k => { sess = k; draw(); });
    btnBar(host, 'People', PEOPLE_BTN, grp, k => { grp = k; draw(); });
    btnBar(host, 'Missions', SAMPLE_BTN, sample, k => { sample = k; draw(); });
    btnBar(host, 'Game order', ORDER_BTN, order, k => { order = k; draw(); });
    btnBar(host, 'Show', [['raw', 'Observed'], ['adj', 'Adjusted (vs each person’s usual, given the mission)']], mode, k => { mode = k; draw(); });
    const box = h('div', {}, host), cap = h('p', { class: 'note' }, host);
    function draw() {
      const V = P3.time[sample] && P3.time[sample][sess] && P3.time[sample][sess][order];
      if (!V) return miss(box);
      const groups = groupsFor(grp);
      const cats = [...Array(8).keys()].map(m => ({ key: String(m), label: `${m}–${m + 1}` }));
      const series = groups.map(g => seriesFrom(g, (V[g] || []).map(asRow), mode));
      const rug = (P3.anchors || []).filter(a => (sess === 'both' || String(a.run) === sess) && (order === 'all' || (order === 'SH') === (a.order === 'SH-first'))
      ).map(a => ({ f: a.t / 480, color: grp === 'everyone' ? css('--bad') : (a.said ? GC.said() : GC.notSaid()),
          tip: `${a.pid} (${a.said ? 'said they noticed' : 'never said'}): first illogical card at ${Math.round(a.t)} s of session ${a.run}` }));
      bandChart(box, cats, series, { rug, yLabel: mode === 'adj' ? 'card taken, % (adjusted)' : Y_TOOK,
        xLabel: `minutes into session ${sess === 'both' ? '1 and 2 (pooled)' : sess} when the strategy panel opened${ORDER_TXT[order]} · ${SAMPLE_TXT[sample]}` });
      const n = P3.orderPeople[order];
      cap.innerHTML = `<b>What is plotted:</b> every strategic decision is put in the minute of the session when its strategy panel opened (0–1 = the first minute). `
        + `Each point is the share of the decisions in that minute where the person took one of the two strategy cards rather than allocating by hand; the shaded band is a 95% interval from resampling people. `
        + `Nothing is aligned to the illogical card; the small ticks on the axis show when each person first met it. `
        + `${grp === 'everyone' ? `${n.everyone} people` : `${n.said} noticers (amber), ${n.notSaid} never-said (blue)${grp === 'both' ? `, and the dashed line is all ${n.everyone} people pooled` : ''}`}. `
        + `The pooled line is roughly the average of the other two weighted by decisions, so when the groups move in opposite directions it stays flat: that is why the dip is invisible if everyone is lumped together. `
        + `Hollow dots: fewer than 8 decisions. Buttons: session; which lines; mission kind; game order (strategic-heavy-first players met the illogical card at about ${Math.round(P3.dip.anchorWs['SH-first'].medianTS1)} s of session 1; ${P3.dip.anchorWs['TH-first'].inS1} of the ${P3.dip.anchorWs['TH-first'].people} tactical-heavy-first players at about ${Math.round(P3.dip.anchorWs['TH-first'].medianTS1)} s, the rest at the start of session 2); observed or adjusted.`;
    }
    draw();
  }

  /* use by decision number, session 1 then session 2 on one axis (never joined across the break), not aligned to the card.
     Pass 5: later numbers only hold the people who made that many decisions, so by default a point is drawn only if at
     least P5.minPeople people of its group reach it; a toggle shows the thin tail (faded, dotted) and another keeps only
     the people present throughout (a fixed panel through decision K of each session). */
  const P5 = D && D.p5;
  const asRow5 = a => P5 && Array.isArray(a) ? Object.fromEntries(P5.fields.map((f, i) => [f, a[i]])) : a;
  function byIndex(host) {
    if (!P5 || !P5.index) return miss(host);
    host.innerHTML = '';
    const MIN = P5.minPeople;
    let sess = 'both', sample = 'all', order = 'all', grp = 'split', w = '1', mode = 'raw', who = 'all', tail = 'hide';
    btnBar(host, 'Session', [['both', 'Session 1 then session 2'], ['s1', 'Session 1'], ['s2', 'Session 2']], sess, k => { sess = k; draw(); });
    btnBar(host, 'People', PEOPLE_BTN, grp, k => { grp = k; draw(); });
    btnBar(host, 'Who is counted', [['all', 'Everyone who reached each number'], ['panel', 'Only people present throughout (fixed panel)']], who, k => { who = k; draw(); });
    btnBar(host, 'Thin points', [['hide', `Hide points from fewer than ${MIN} people`], ['show', 'Show them, faded']], tail, k => { tail = k; draw(); });
    btnBar(host, 'Missions', SAMPLE_BTN.concat([['clean', 'No illogical card on the mission']]), sample, k => { sample = k; draw(); });
    btnBar(host, 'Game order', ORDER_BTN, order, k => { order = k; draw(); });
    btnBar(host, 'Grouping', [['1', 'Every decision'], ['2', 'Pairs']], w, k => { w = k; draw(); });
    btnBar(host, 'Show', [['raw', 'Observed'], ['adj', 'Adjusted (vs each person’s usual, given the mission)']], mode, k => { mode = k; draw(); });
    const box = h('div', {}, host), cap = h('p', { class: 'note' }, host);
    const STXT = Object.assign({ clean: 'missions with no illogical card' }, SAMPLE_TXT);
    function draw() {
      const ss = sess === 'both' ? ['s1', 's2'] : [sess];
      const groups = groupsFor(grp);
      // the threshold is on the group as a whole (both game orders), so a game-order view keeps exactly the numbers the full view keeps
      const full = (sk, g) => { const V = P5.index[sample][sk].all[who][g]; return Object.fromEntries(((V || {})[w] || []).map(asRow5).map(b => [b.bin, b.people])); };
      const rows = Object.fromEntries(groups.map(g => [g, ss.flatMap((sk, si) => {
        const V = P5.index[sample] && P5.index[sample][sk] && P5.index[sample][sk][order] && P5.index[sample][sk][order][who];
        const fp = full(sk, g);
        return ((V && V[g] || {})[w] || []).map(asRow5).map(b => Object.assign({}, b, { key: sk + ':' + b.bin, seg: si, sk, thin: (fp[b.bin] || 0) < MIN }))
          .filter(b => tail === 'show' || !b.thin);
      })]));
      const keys = [];
      ss.forEach((sk, si) => sortKeys(groups.flatMap(g => rows[g].filter(b => b.seg === si).map(b => b.bin))).forEach(k => keys.push({ key: sk + ':' + k, label: k, seg: si,
        tipLabel: `session ${sk[1]}, decision ${k}` })));
      if (!keys.length) return miss(box, 'No decisions of this kind here.');
      const series = groups.map(g => ({ label: g === 'everyone' ? 'Everyone (pooled)' : GL3[g], color: GC3[g](), dash: g === 'everyone',
        points: rows[g].map(b => ({ key: b.key, n: b.n, people: b.people, thin: b.thin, y: mode === 'adj' ? b.adj : b.raw,
          lo: mode === 'adj' ? b.adjLo : b.rawLo, hi: mode === 'adj' ? b.adjHi : b.rawHi,
          tip: `n = ${b.n} decisions from ${b.people} people${b.thin ? ` — <b>fewer than ${MIN} people reach this number</b>; hidden by default` : ''}`
            + `<br>observed ${pct(b.raw, 0)} · adjusted ${pct(b.adj, 0)}`
            + `<br>${pct(b.three, 0)} three-type missions · ${pct(b.odd, 0)} showed an illogical card · ${pct(b.sg, 0)} in the strategic-heavy game · ${pct(b.end, 0)} in the last 90 s`
            + `<br>${pct(b.aft, 0)} made at/after the person’s first illogical card` })) }));
      const strip = {};
      keys.forEach(c => {
        let n = 0, a = 0;
        groups.filter(g => grp !== 'both' || g !== 'everyone').forEach(g => rows[g].filter(b => b.key === c.key).forEach(b => { n += b.n; a += b.aft * b.n; }));
        if (n) strip[c.key] = a / n;
      });
      const nRows = groups.filter(g => g !== 'everyone' || grp === 'everyone').map(g => ({ label: (g === 'everyone' ? 'people' : g === 'said' ? 'noticers' : 'never said'),
        color: GC3[g](), min: MIN, vals: Object.fromEntries(rows[g].map(b => [b.key, b.people])) }));
      bandChart(box, keys, series, { strip, nRows, sizeByPeople: true, segLabels: sess === 'both' ? ['Session 1', 'Session 2 (the other game)'] : null,
        yLabel: mode === 'adj' ? 'card taken, % of decisions (adjusted)' : Y_TOOK,
        xLabel: `the person's Nth ${sample === 'all' ? '' : STXT[sample].replace(' missions', '').replace('missions with ', '') + ' '}decision of the session${ORDER_TXT[order]}${who === 'panel' ? ' · fixed panel' : ''}` });
      const C = P4 && P4.carry;
      const pan = ss.map(sk => { const q = P5.panel[sample][sk]; return `session ${sk[1]}: ${q.people.said.length} noticers and ${q.people.notSaid.length} never-said people with at least ${q.K} decisions, shown for decisions 1–${q.K}`; }).join('; ');
      cap.innerHTML = `<b>What is plotted:</b> each person's strategic decisions are numbered in the order they made them within each session${sample === 'all' ? '' : ', counting only ' + STXT[sample]}; `
        + `each point is the share of decisions at that number where a strategy card was taken, with a 95% band from resampling people. Dot size and the numbers under the axis give how many people each point rests on. `
        + (sess === 'both' ? 'Session 1 runs left of the dashed line and session 2 right of it; the lines are deliberately not joined across it (session 2 is a different game, after a break and a survey). ' : '')
        + `<b>Later numbers are different people:</b> only those who made that many decisions in the session reach them, and they are mostly players of the strategic-heavy game, which has more missions. `
        + (who === 'panel' ? `<b>Fixed panel</b> (on): ${pan}, so every point is the same people. ` : `So by default a point is drawn only if at least ${MIN} people of its group reach that number (“Thin points” shows the rest, faded and dotted; “Who is counted” switches to a fixed panel of the same people throughout). `)
        + `Not aligned to the card. The red strip shows how many decisions at each number came at or after the person's first illogical card (pale = mostly before it). “No illogical card” leaves out the missions that showed one, which is most of what drives noticers' lows late in session 2.`
        + (C && sess !== 's2' ? ` <b>Does the session-1 recovery carry over?</b> Noticers went from ${pct(C.recovery.said.a, 0)} in decisions 3–5 to ${pct(C.recovery.said.b, 0)} in the rest of session 1 (per person ${ppts(C.recovery.said.diff)} [${ppts(C.recovery.said.ci[0])}, ${ppts(C.recovery.said.ci[1])}]), `
          + `then started session 2 at ${pct(C.endToStart.said.b, 0)} against ${pct(C.endToStart.said.a, 0)} over their last three decisions of session 1 (${ppts(C.endToStart.said.diff)} [${ppts(C.endToStart.said.ci[0])}, ${ppts(C.endToStart.said.ci[1])}]). `
          + `Never-said people also start session 2 a little lower (${pct(C.endToStart.notSaid.a, 0)} → ${pct(C.endToStart.notSaid.b, 0)}), and the difference between the groups at the break is ${ppts(C.endToStart.groupDiff.raw.est)} [${ppts(C.endToStart.groupDiff.raw.lo)}, ${ppts(C.endToStart.groupDiff.raw.hi)}], ${pval(C.endToStart.groupDiff.raw.p)}.` : '');
    }
    draw();
  }

  /* NEW · the dip taken apart */
  function dip(host) {
    if (!P3 || !P3.dip) return miss(host);
    host.innerHTML = '';
    const Q = P3.dip;
    let view = 'effect';
    btnBar(host, 'View', [['effect', 'Dip by game order'], ['did', 'What they did instead'], ['windows', 'Other windows']], view, k => { view = k; draw(); });
    const box = h('div', {}, host), cap = h('p', { class: 'note' }, host);
    const ORD = { 'SH-first': 'Strategic-heavy first (card at decision 2)', 'TH-first': 'Tactical-heavy first (card at decision 5+ or session 2)',
                  'TH-first, window before any illogical card': '  … only window decisions made before any illogical card', both: 'Both orders' };
    function draw() {
      box.innerHTML = '';
      if (view === 'effect') {
        const rows = [];
        ['said', 'notSaid'].forEach(g => {
          rows.push({ head: GL[g] });
          Q.perPerson.filter(x => x.group === g).forEach(x => rows.push({ label: ORD[x.order] || x.order, est: x.mean, lo: x.ci[0], hi: x.ci[1], p: x.p == null ? 1 : x.p, color: GC[g](),
            sub: `${x.people} people · decisions 3–5: ${pct(x.inWin, 0)} (n ${x.nIn}) vs the rest of session 1: ${pct(x.outWin, 0)} (n ${x.nOut})<br>${x.fell} fell, ${x.rose} rose, ${x.same} unchanged · p from a one-sample t-test over people` }));
        });
        rows.push({ head: 'Noticers minus never-said, same window' });
        rows.push({ label: 'Session 1', est: Q.diffS1.raw.est, lo: Q.diffS1.raw.lo, hi: Q.diffS1.raw.hi, p: Q.diffS1.raw.p, color: css('--mark'), sub: 'linear model, game held fixed, people clustered' });
        rows.push({ label: 'Session 2 (does it come back?)', est: Q.diffS2.raw.est, lo: Q.diffS2.raw.lo, hi: Q.diffS2.raw.hi, p: Q.diffS2.raw.p, color: css('--mark'), sub: 'linear model, game held fixed, people clustered' });
        diffForest(box, rows, { padL: 330, lim: 0.7, xLabel: 'card uptake on decisions 3–5 of the session minus the rest of it, percentage points (per person, then averaged)' });
        const m = Q.models.said;
        cap.innerHTML = `Decision numbers count every strategic decision of the session. Noticers: decisions 3–5 are ${ppts(m.win.est)} below the rest of their session 1 `
          + `[${ppts(m.win.lo)}, ${ppts(m.win.hi)}]; allowing for whether the illogical card had already appeared changes it to ${ppts(m.winGivenAfter.est)}, and the card term itself is ${ppts(m.after.est)} (${pval(m.after.p)}). `
          + `Whether the card came early or late (game order) makes no difference to the dip: ${ppts(m.winByOrder.est)}, ${pval(m.winByOrder.p)}. The window was read off the curve, so treat its p-values as descriptive.`;
      } else if (view === 'did') {
        const parts = [['took', 'took a card', '--s-strat'], ['manSeen', 'manual, after looking at the cards', '--r-man'], ['manEarly', 'manual before the cards loaded', '--ink-3']];
        const W = 700, rowH = 30, padL = 220, padR = 20;
        const rows = [];
        ['said', 'notSaid'].forEach(g => { rows.push({ head: GL[g], g }); Q.did.filter(x => x.group === g).forEach(x => rows.push(x)); });
        const s = svgRoot(box, W, 12 + rows.length * rowH + 8);
        const x = v => padL + (W - padL - padR) * v;
        rows.forEach((rw, i) => {
          const y0 = 6 + i * rowH;
          if (rw.head) { el('text', { x: 6, y: y0 + 19, fill: GC[rw.g](), 'font-weight': 600, 'font-size': 12.5 }, s).textContent = rw.head; return; }
          el('text', { x: padL - 10, y: y0 + 19, 'text-anchor': 'end', fill: css('--ink-2'), 'font-size': 12 }, s).textContent = `session 1, decisions ${rw.band} (n ${rw.n}, ${rw.people} people)`;
          let acc = 0;
          parts.forEach(([k, lab, tok]) => {
            const v = rw[k] || 0, c = rw[k + 'CI'];
            const rc = el('rect', { x: x(acc), y: y0 + 6, width: Math.max(0, x(acc + v) - x(acc) - 1.5), height: 18, fill: css(tok), opacity: k === 'manEarly' ? .55 : .9 }, s);
            hoverable(rc, `<b>${GL[rw.group]} · decisions ${rw.band}</b><br>${lab}: ${pct(v, 0)}${c ? ci(c[0], c[1]) + ' (people resampled)' : ''}<br>n = ${rw.n} decisions, ${rw.people} people`
              + `<br>three-type missions: took ${rw.took3 != null ? pct(rw.took3, 0) : '—'} (n ${rw.n3}) · one/two-type: ${rw.tookFew != null ? pct(rw.tookFew, 0) : '—'} (n ${rw.nFew})`
              + `<br>other missions waiting ${num(rw.queue, 1)} · reserve short of a needed type ${pct(rw.short, 0)} · minute ${num(rw.minute, 1)} · ${pct(rw.before, 0)} before their first illogical card`);
            if (v >= 0.09) el('text', { x: x(acc + v / 2), y: y0 + 19, 'text-anchor': 'middle', fill: css('--surface'), 'font-size': 10.5, 'font-family': css('--mono'), 'pointer-events': 'none' }, s).textContent = pct(v, 0);
            acc += v;
          });
        });
        legend(box, parts.map(([, lab, tok]) => ({ label: lab, color: css(tok) })));
        const a = Q.did.find(x => x.group === 'said' && x.band === '3–5'), b = Q.did.find(x => x.group === 'said' && x.band === '1–2');
        cap.innerHTML = `In decisions 3–5 the noticers' extra non-takes are <b>manual allocations made after the cards had loaded</b> (${pct(a.manSeen, 0)}, against ${pct(b.manSeen, 0)} in decisions 1–2), not pre-emptive ones (${pct(a.manEarly, 0)}). `
          + `They looked at the cards and turned them down. It happens on three-type missions too (took ${pct(a.took3, 0)}, n ${a.n3}), where nothing on the card is illogical. Hover a bar for the mission mix and load in that stretch.`;
      } else {
        const rows = [{ head: 'Noticers minus never-said, session 1, by the decisions counted as “the window”' }];
        Q.windows.forEach(x => rows.push({ label: `decisions ${x.window}`, est: x.diff.est, lo: x.diff.lo, hi: x.diff.hi, p: x.diff.p, color: css('--mark'),
          sub: `noticers ${ppts(x.said.est)} (${pval(x.said.p)}) · never-said ${ppts(x.notSaid.est)} (${pval(x.notSaid.p)})` }));
        diffForest(box, rows, { padL: 330, lim: 0.7, xLabel: 'how much more noticers drop in the window than never-said, percentage points' });
        cap.textContent = 'The 3–5 window was picked by eye from the unaligned curve. Every other window that covers decisions 3–4 gives the same direction; it is largest where it was picked (as it must be), so the size is optimistic.';
      }
    }
    draw();
  }

  /* NEW · spoken anchor as bars */
  function spokenBars(host) {
    if (!P3 || !P3.spoken) return miss(host);
    host.innerHTML = '';
    let rem = 'strict', miss3 = 'allFew';
    btnBar(host, 'Remarks', [['strict', 'Strict remarks (7 people)'], ['both', 'Strict and any remark, side by side']], rem, k => { rem = k; draw(); });
    btnBar(host, 'Missions', [['allFew', 'All vs one- & two-type'], ['allThreeFew', 'All, three-type, one- & two-type']], miss3, k => { miss3 = k; draw(); });
    const box = h('div', {}, host), cap = h('p', { class: 'note' }, host);
    const COL = { before: () => css('--ink-3'), after: () => css('--warn') };
    const MS = { all: 'All missions', three: 'Three-type', few: 'One/two-type' };
    function draw() {
      box.innerHTML = '';
      const P = P3.spoken.pooled;
      const sets = rem === 'strict' ? ['strict'] : ['strict', 'broad'];
      const samples = miss3 === 'allFew' ? ['all', 'few'] : ['all', 'three', 'few'];
      const cells = sets.flatMap(st => samples.map(sk => ({ st, sk, bins: (P[st][sk].bins || []).reduce((o, b) => (o[b.bin] = b, o), {}) })));
      const cats = cells.map(c => {
        const nb = c.bins.before, na = c.bins.after;
        return `${MS[c.sk]}\n${sets.length > 1 ? (c.st === 'strict' ? 'strict · ' : 'any · ') : ''}n ${nb ? nb.n : 0} / ${na ? na.n : 0}`;
      });
      const series = ['before', 'after'].map(s_ => ({ label: s_ === 'before' ? 'before saying it' : 'after saying it', color: COL[s_](),
        vals: cells.map(c => { const b = c.bins[s_]; return b ? { v: b.raw, lo: b.rawLo, hi: b.rawHi, faint: b.n < 10,
          tip: `${c.st === 'strict' ? 'Strict remark' : 'Any remark (strict or broad)'} · ${MS[c.sk].toLowerCase()}<br>n = ${b.n} decisions from ${b.people} people · 95% interval from resampling people${b.n < 10 ? '<br><i>fewer than 10 decisions — read with care</i>' : ''}` } : null; }) }));
      const dividers = sets.length > 1 ? [samples.length] : [];
      barsCI(box, cats, series, { height: 260, padB: 52, dividers, yLabel: Y_TOOK });
      legend(box, [{ label: 'before saying it', color: COL.before() }, { label: 'after saying it', color: COL.after() }]);
      const T = (st, sk) => P[st][sk].test;
      const line = (st, sk) => { const t = T(st, sk); return t && t.adj ? `${MS[sk].toLowerCase()}: ${pct(t.before, 0)} → ${pct(t.after, 0)}, adjusted ${ppts(t.adj.est)} [${ppts(t.adj.lo)}, ${ppts(t.adj.hi)}], ${pval(t.adj.p)} (${t.peopleBoth} people with decisions on both sides; ${t.lower} fell, ${t.higher} rose)` : `${MS[sk].toLowerCase()}: not estimable`; };
      cap.innerHTML = `Share of strategic decisions where a strategy card was taken, before and after the moment each person said aloud that a card was wrong; everyone in the set pooled, 95% intervals from resampling people. “n 30 / 75” under a pair = decisions before / after. Pale bars rest on fewer than 10 decisions. `
        + sets.map(st => `<b>${st === 'strict' ? 'Strict remarks' : 'Any remark'}</b> — ` + samples.map(sk => line(st, sk)).join('; ')).join('. ') + '. '
        + `The drop is largest on one- and two-type missions, the ones that carry the illogical card, but their “before” bar is only ${P.strict.few.bins.find(b => b.bin === 'before') ? P.strict.few.bins.find(b => b.bin === 'before').n : 0} decisions from ${P.strict.few.bins.find(b => b.bin === 'before') ? P.strict.few.bins.find(b => b.bin === 'before').people : 0} people for strict remarks, so it is a direction, not a measured size.`;
    }
    draw();
  }

  Object.assign(CH, {
    'flaw.events2': events2, 'flaw.nth2': nth2, 'flaw.people2': people2, 'flaw.overTime': overTime, 'flaw.byIndex': byIndex,
    'flaw.dip': dip, 'flaw.spokenBars': spokenBars,
  });

  Object.assign(CH, {
    'flaw.events': events, 'flaw.nth': nth, 'flaw.oddMissions': oddMissions, 'flaw.strip': strip,
    'flaw.model': model, 'flaw.oldDots': oldDots, 'flaw.people': people, 'flaw.spoken': spoken,
    'flaw.anchors': anchors, 'flaw.dominated': dominated, 'flaw.visibility': visibility, 'flaw.timing': timing,
  });
})();
