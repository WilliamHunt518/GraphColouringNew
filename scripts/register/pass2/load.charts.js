(() => {
  const D = (DATA.pass2 || {}).load;
  const W = 700;
  const say = (host, msg) => h('p', { class: 'cap', text: msg }, host);
  const ok = (host, v, what) => { if (v == null) { say(host, 'No data for ' + what + ' (load.json missing this block).'); return false; } return true; };
  const mono = () => css('--mono');
  const txt = (s, x, y, t, a = {}) => { const n = el('text', Object.assign({ x, y, fill: css('--ink-3'), 'font-size': 11, 'font-family': mono() }, a), s); n.textContent = t; return n; };
  const TIER = { strategic: ['--s-strat', 'Strategic: strategy card taken'], tactical: ['--s-tac', 'Tactical: Suggest pressed'] };

  /* ── generic: values over an ordered set of x labels, with CI whiskers; several series side by side.
     series: {label, color, pts:[{x(label), y, lo, hi, n, tip}], dash, hollow}
     o: {lo, hi, fmt, ticks, yLabel, xLabel, vline (x index position, may be fractional), vlabel, ref:{y,label}} */
  function ciChart(host, xs, series, o = {}) {
    const H = o.height || 280, padL = 56, padR = o.padR || 20, padT = 26, padB = 46;
    const s = svgRoot(host, W, H);
    const lo = o.lo != null ? o.lo : 0, hi = o.hi != null ? o.hi : 1, fmt = o.fmt || (v => pct(v, 0));
    const y = v => H - padB - (H - padB - padT) * ((v - lo) / (hi - lo));
    const step = (W - padL - padR) / xs.length;
    const nS = series.length, off = k => (k - (nS - 1) / 2) * Math.min(14, step / (nS + 1));
    const xc = i => padL + step * (i + 0.5);
    (o.ticks || [lo, lo + (hi - lo) / 4, lo + (hi - lo) / 2, lo + 3 * (hi - lo) / 4, hi]).forEach(v => {
      el('line', { x1: padL, x2: W - padR, y1: y(v), y2: y(v), stroke: css('--grid') }, s);
      txt(s, padL - 8, y(v) + 4, fmt(v), { 'text-anchor': 'end' });
    });
    xs.forEach((lab, i) => txt(s, xc(i), H - padB + 17, lab, { 'text-anchor': 'middle' }));
    txt(s, (padL + W - padR) / 2, H - 8, o.xLabel || '', { 'text-anchor': 'middle', 'font-family': 'inherit', 'font-size': 11.5 });
    if (o.yLabel) txt(s, 14, (padT + H - padB) / 2, o.yLabel, { transform: `rotate(-90 14 ${(padT + H - padB) / 2})`, 'text-anchor': 'middle', 'font-family': 'inherit', 'font-size': 11.5 });
    if (o.ref) {
      el('line', { x1: padL, x2: W - padR, y1: y(o.ref.y), y2: y(o.ref.y), stroke: css('--ink-3'), 'stroke-dasharray': '2 3' }, s);
      txt(s, W - padR - 4, y(o.ref.y) - 5, o.ref.label, { 'text-anchor': 'end' });
    }
    if (o.vline != null) {
      const xv = padL + step * o.vline;
      el('line', { x1: xv, x2: xv, y1: padT - 10, y2: H - padB, stroke: css('--ink-2'), 'stroke-width': 1.3, 'stroke-dasharray': '2 4' }, s);
      txt(s, xv + 5, padT - 12, o.vlabel || '', { fill: css('--ink-2') });
    }
    series.forEach((se, k) => {
      const pts = se.pts.filter(p => p.y != null);
      const X = p => xc(xs.indexOf(p.x)) + off(k);
      if (se.line !== false && pts.length > 1) {
        const pa = { d: pts.map((p, i) => (i ? 'L' : 'M') + X(p) + ' ' + y(p.y)).join(' '), fill: 'none', stroke: se.color, 'stroke-width': se.dash ? 1.4 : 2, opacity: se.faint ? .55 : 1 };
        if (se.dash) pa['stroke-dasharray'] = '5 4';
        el('path', pa, s);
      }
      pts.forEach(p => {
        if (p.lo != null && p.hi != null)
          el('line', { x1: X(p), x2: X(p), y1: y(Math.max(lo, p.lo)), y2: y(Math.min(hi, p.hi)), stroke: se.color, 'stroke-width': 1.6, opacity: se.faint ? .55 : .9 }, s);
        el('circle', { cx: X(p), cy: y(p.y), r: se.dash ? 3.2 : 4.5, fill: se.hollow || se.dash ? css('--surface') : se.color, stroke: se.color, 'stroke-width': 1.6, opacity: se.faint ? .7 : 1 }, s);
        const hit = el('circle', { cx: X(p), cy: y(p.y), r: 11, fill: 'transparent' }, s);
        hoverable(hit, `<b>${se.label}</b><br>${o.xName || 'x'} ${p.x}: ${fmt(p.y)}` + (p.lo != null ? ` [${fmt(p.lo)}, ${fmt(p.hi)}]` : '') + (p.n != null ? `<br>n = ${p.n}` : '') + (p.tip ? '<br>' + p.tip : ''));
      });
    });
    return s;
  }

  /* odds-ratio forest on a log axis; rows {label, est, lo, hi, p, n, people, sub} */
  function orForest(host, rows, o = {}) {
    const rowH = 26, padL = o.padL || 250, padR = 96, padT = 20;
    const H = padT + rows.length * rowH + 40 + (o.xTitle ? 18 : 0);
    const s = svgRoot(host, W, H);
    const lim = Math.log(o.lim || 3);
    const x = v => padL + (W - padL - padR) * ((Math.log(v) + lim) / (2 * lim));
    const base = padT + rows.length * rowH;
    (o.ticks || [0.33, 0.5, 0.75, 1, 1.33, 2, 3]).forEach(v => {
      el('line', { x1: x(v), x2: x(v), y1: padT - 4, y2: base, stroke: v === 1 ? css('--ink-3') : css('--grid'), 'stroke-width': v === 1 ? 1.5 : 1 }, s);
      txt(s, x(v), base + 14, '×' + v, { 'text-anchor': 'middle' });
    });
    txt(s, x(1), padT - 8, o.zero || 'no change', { 'text-anchor': 'middle' });
    txt(s, padL, base + 30, o.left || '← less likely', {});
    txt(s, W - padR, base + 30, o.right || 'more likely →', { 'text-anchor': 'end' });
    if (o.xTitle) txt(s, (padL + W - padR) / 2, base + 48, o.xTitle, { 'text-anchor': 'middle', fill: css('--ink-2'), 'font-family': 'inherit', 'font-size': 11.5 });
    const clip = v => Math.min(Math.exp(lim), Math.max(Math.exp(-lim), v));
    rows.forEach((r_, i) => {
      const yy = padT + i * rowH + rowH / 2;
      if (r_.head) { txt(s, 8, yy + 4, r_.label, { fill: css('--ink-2'), 'font-weight': 600, 'font-family': 'inherit', 'font-size': 12 }); return; }
      txt(s, padL - 10, yy + 4, r_.label, { 'text-anchor': 'end', fill: css('--ink-2'), 'font-family': 'inherit', 'font-size': 12 });
      if (r_.est == null) return;
      const col = r_.color || (r_.main ? css('--mark') : css('--mark-soft'));
      el('line', { x1: x(clip(r_.lo)), x2: x(clip(r_.hi)), y1: yy, y2: yy, stroke: col, 'stroke-width': r_.main ? 3 : 2, 'stroke-linecap': 'round' }, s);
      el('circle', { cx: x(clip(r_.est)), cy: yy, r: r_.main ? 6 : 4.5, fill: col, stroke: css('--surface'), 'stroke-width': 1.5 }, s);
      txt(s, W - padR + 8, yy + 4, r_.right != null ? r_.right : (r_.p != null ? pval(r_.p) : ''), { fill: r_.p != null ? pColour(r_.p) : css('--ink-3') });
      const hit = el('rect', { x: padL, y: yy - rowH / 2, width: W - padL - padR, height: rowH, fill: 'transparent' }, s);
      hoverable(hit, `<b>${r_.label}</b><br>×${num(r_.est, 2)} [${num(r_.lo, 2)}, ${num(r_.hi, 2)}]` + (r_.p != null ? ' · ' + pval(r_.p) : '') + (r_.n != null ? `<br>n = ${r_.n}` : '') + (r_.people != null ? ` · ${r_.people} people` : '') + (r_.sub ? '<br>' + r_.sub : ''));
    });
  }

  /* null histogram with the observed value marked */
  function nullHist(host, nul, o = {}) {
    const H = 150, padL = 20, padR = 20, padT = 28, padB = 36;
    const s = svgRoot(host, W, H);
    const ed = nul.edges, hs = nul.hist;
    const lo = Math.min(ed[0], nul.obs), hi = Math.max(ed[ed.length - 1], nul.obs);
    const span = (hi - lo) || 1, L = lo - span * .08, R = hi + span * .08;
    const x = v => padL + (W - padL - padR) * ((v - L) / (R - L));
    const mx = Math.max(...hs) || 1, y = v => H - padB - (H - padB - padT) * v / mx;
    hs.forEach((c, i) => el('rect', { x: x(ed[i]), y: y(c), width: Math.max(1, x(ed[i + 1]) - x(ed[i]) - 1), height: H - padB - y(c), fill: css('--mark-soft'), opacity: .7 }, s));
    el('line', { x1: padL, x2: W - padR, y1: H - padB, y2: H - padB, stroke: css('--line') }, s);
    [ed[0], (ed[0] + ed[ed.length - 1]) / 2, ed[ed.length - 1]].forEach(v => txt(s, x(v), H - padB + 15, (o.fmt || (z => num(z, 2)))(v), { 'text-anchor': 'middle' }));
    el('line', { x1: x(nul.obs), x2: x(nul.obs), y1: padT - 8, y2: H - padB, stroke: css('--bad'), 'stroke-width': 2.5 }, s);
    txt(s, x(nul.obs), padT - 12, 'observed ' + (o.fmt || (z => num(z, 2)))(nul.obs), { 'text-anchor': x(nul.obs) > W - 120 ? 'end' : 'middle', fill: css('--bad'), 'font-weight': 600 });
    txt(s, (padL + W - padR) / 2, H - 6, o.xLabel || '', { 'text-anchor': 'middle', 'font-family': 'inherit', 'font-size': 11.5 });
    const hit = el('rect', { x: padL, y: padT, width: W - padL - padR, height: H - padT - padB, fill: 'transparent' }, s);
    hoverable(hit, `<b>${o.title || ''}</b><br>observed ${num(nul.obs, 3)}<br>random utterances: mean ${num(nul.mean, 3)}, 95% of draws ${num(nul.lo, 3)}–${num(nul.hi, 3)}<br>${pval(nul.p)}`);
  }

  /* one row of dots per group on a shared x; group mean ± CI drawn as a bar */
  function dotRows(host, groups, o = {}) {
    const rowH = 64, padL = 190, padR = 40, padT = 18;
    const H = padT + groups.length * rowH + 40;
    const s = svgRoot(host, W, H);
    const all = groups.flatMap(g => g.pts.map(p => p.v)).concat(groups.flatMap(g => [g.lo, g.hi].filter(v => v != null)));
    const m = o.lim || Math.max(0.05, ...all.map(Math.abs)) * 1.08;
    const x = v => padL + (W - padL - padR) * ((v + m) / (2 * m));
    const base = padT + groups.length * rowH;
    [-m, -m / 2, 0, m / 2, m].forEach(v => {
      el('line', { x1: x(v), x2: x(v), y1: padT - 6, y2: base, stroke: v === 0 ? css('--ink-3') : css('--grid'), 'stroke-width': v === 0 ? 1.5 : 1 }, s);
      txt(s, x(v), base + 15, (o.fmt || (z => sgn(z, 2)))(v), { 'text-anchor': 'middle' });
    });
    txt(s, (padL + W - padR) / 2, H - 6, o.xLabel || '', { 'text-anchor': 'middle', 'font-family': 'inherit', 'font-size': 11.5 });
    groups.forEach((g, i) => {
      const yy = padT + i * rowH + rowH / 2;
      txt(s, padL - 12, yy - 2, g.label, { 'text-anchor': 'end', fill: g.color, 'font-weight': 600, 'font-family': 'inherit', 'font-size': 12.5 });
      if (g.sub) txt(s, padL - 12, yy + 13, g.sub, { 'text-anchor': 'end' });
      g.pts.forEach((p, j) => {
        const jy = yy + ((j * 37) % 23 - 11);
        const c = el('circle', { cx: x(Math.max(-m, Math.min(m, p.v))), cy: jy, r: 4, fill: g.color, opacity: .45 }, s);
        hoverable(c, `<b>${p.label}</b><br>${(o.fmt || (z => sgn(z, 3)))(p.v)}${p.tip ? '<br>' + p.tip : ''}`);
      });
      if (g.mean != null) {
        if (g.lo != null) el('line', { x1: x(Math.max(-m, g.lo)), x2: x(Math.min(m, g.hi)), y1: yy, y2: yy, stroke: g.color, 'stroke-width': 3.5, 'stroke-linecap': 'round' }, s);
        el('rect', { x: x(g.mean) - 2, y: yy - 14, width: 4, height: 28, fill: g.color }, s);
        const hit = el('rect', { x: x(g.mean) - 8, y: yy - 16, width: 16, height: 32, fill: 'transparent' }, s);
        hoverable(hit, `<b>${g.label}: mean</b><br>${(o.fmt || (z => sgn(z, 3)))(g.mean)}` + (g.lo != null ? ` [${(o.fmt || (z => sgn(z, 3)))(g.lo)}, ${(o.fmt || (z => sgn(z, 3)))(g.hi)}]` : '') + `<br>n = ${g.pts.length} people`);
      }
    });
  }

  const pp = v => sgn(100 * v, 1) + ' pp';
  const QX = ['0', '1', '2', '3', '4', '5', '6+'];
  // The queue list shows ~3.5 cards at rest (3 full + part of a 4th). On an axis of OTHER missions
  // waiting (the one being opened is also a card), the list overflows past 2.5 others; on an axis of
  // ALL missions waiting (minute start) past 3.5. vAt(v, x0) turns a data value into the chart's
  // slot position when the first x label is x0.
  const vAt = (v, x0) => v - x0 + 0.5;
  const VL = vAt(2.5, 0);
  const VLAB = 'list full beyond here (~3.5 cards incl. this one)';

  Object.assign(CH, {
    /* A — queue depth vs reliance, raw / raw+expected / adjusted, with person-bootstrap CIs */
    'load.nullBins': host => {
      if (!ok(host, D && D.null, 'the queue bins')) return;
      let tier = 'strategic', mode = 'adj';
      const box = h('div', {}, host);
      const draw = () => {
        const YL = { strategic: '% of strategic decisions where a card was taken', tactical: '% of tactical plans where Suggest was pressed', both: '% of decisions using the assistant' };
        const seriesFor = (tr, both) => {
          const B = D.null[tr].bins, [cv, lab] = TIER[tr], col = css(cv), pre = both ? lab + ' — ' : '';
          const raw = { label: pre + 'Raw rate', color: col, faint: mode === 'adj' && !both, hollow: mode === 'adj' && !both, pts: B.map(b => ({ x: b.label, y: b.raw, lo: b.rawLo, hi: b.rawHi, n: b.n, tip: `${b.people} people · missions avg ${num(b.ndrones, 1)} drones · minute ${num(b.minute, 1)} · their own usual rate ${pct(b.person, 0)}` })) };
          const exp = { label: pre + 'Expected from mission, minute, game, person', color: both ? col : css('--ink-3'), dash: true, pts: B.map(b => ({ x: b.label, y: b.exp, n: b.n })) };
          const adj = { label: pre + 'Adjusted', color: col, pts: B.map(b => ({ x: b.label, y: b.adj, lo: b.adjLo, hi: b.adjHi, n: b.n, tip: 'overall rate + (observed − expected) in this bin' })) };
          // raw as a dotted line without whiskers, under the adjusted line (the paper's view, 2026-10-21)
          const rawDot = Object.assign({}, raw, { label: pre + 'Raw rate (dotted)', dash: true, hollow: true, faint: false,
            pts: raw.pts.map(p => Object.assign({}, p, { lo: null, hi: null })) });
          if (mode === 'rawadj') return [rawDot, adj];
          if (both) return mode === 'raw' ? [raw] : mode === 'exp' ? [raw, exp] : [adj];
          return mode === 'raw' ? [raw] : mode === 'exp' ? [raw, exp] : [raw, adj];
        };
        const ser = tier === 'both' ? seriesFor('strategic', true).concat(seriesFor('tactical', true)) : seriesFor(tier, false);
        const B = D.null[tier === 'both' ? 'strategic' : tier].bins;
        box.innerHTML = '';
        ciChart(box, QX, ser, { lo: 0.3, hi: 1, ticks: [.3, .4, .5, .6, .7, .8, .9, 1], xName: 'waiting', xLabel: 'number of OTHER missions waiting for a strategic decision at that moment',
          yLabel: YL[tier], vline: VL, vlabel: VLAB, ref: tier === 'both' ? null : { y: D.null[tier].overall, label: 'overall ' + pct(D.null[tier].overall, 0) } });
        legend(box, ser.map(se => ({ label: se.label + (se.pts[0] && se.pts[0].lo != null ? ' (95% CI, people resampled)' : ''), color: se.color })));
        if (tier === 'both') { say(box, `Both assistants on one axis (${mode === 'adj' ? 'both adjusted' : mode === 'raw' ? 'both raw' : 'both raw, each with its expected line dashed'}). Blue = strategic decisions (card taken), orange = tactical plans (Suggest pressed). Hover a point for its n.`); return; }
        tableFor(box, ['Waiting', 'n', 'People', 'Raw', 'Raw 95% CI', 'Expected', 'Adjusted', 'Adj. 95% CI', 'Mission drones', 'Their usual rate', 'In Strategic Heavy games'],
          B.map(b => [b.label, b.n, b.people, pct(b.raw, 0), `${pct(b.rawLo, 0)}–${pct(b.rawHi, 0)}`, pct(b.exp, 0), pct(b.adj, 0), `${pct(b.adjLo, 0)}–${pct(b.adjHi, 0)}`, num(b.ndrones, 1), pct(b.person, 0), pct(b.stratGame, 0)]));
      };
      host.insertBefore(btnBar(host, 'Assistant', [['strategic', 'Strategic'], ['tactical', 'Tactical'], ['both', 'Both together']], tier, k => { tier = k; draw(); }), box);
      host.insertBefore(btnBar(host, 'View', [['raw', 'Raw'], ['exp', 'Raw + expected'], ['adj', 'Adjusted'], ['rawadj', 'Raw (dotted) + adjusted']], mode, k => { mode = k; draw(); }), box);
      draw();
    },

    /* G — how long the mission had been left waiting vs handing it over (pass 5: "do they automate a card left hanging?") */
    'load.waits': host => {
      if (!ok(host, D && D.waits, 'the waiting-time bins')) return;
      let tier = 'strategic', mode = 'adj';
      const box = h('div', {}, host);
      const draw = () => {
        const Wt = D.waits[tier], B = Wt.bins, [cv] = TIER[tier], col = css(cv), m = Wt.models.main;
        const raw = { label: 'Raw rate', color: col, faint: mode === 'adj', hollow: mode === 'adj', pts: B.map(b => ({ x: b.label, y: b.raw, lo: b.rawLo, hi: b.rawHi, n: b.n, tip: `${b.people} people · missions avg ${num(b.ndrones, 1)} drones · minute ${num(b.minute, 1)} · their own usual rate ${pct(b.person, 0)}` })) };
        const exp = { label: 'Expected from mission, minute, game, person', color: css('--ink-3'), dash: true, pts: B.map(b => ({ x: b.label, y: b.exp, n: b.n })) };
        const adj = { label: 'Adjusted', color: col, pts: B.map(b => ({ x: b.label, y: b.adj, lo: b.adjLo, hi: b.adjHi, n: b.n, tip: 'overall rate + (observed − expected) in this bin' })) };
        const ser = mode === 'raw' ? [raw] : mode === 'exp' ? [raw, exp] : [raw, adj];
        box.innerHTML = '';
        ciChart(box, B.map(b => b.label), ser, { lo: 0.3, hi: 1, ticks: [.3, .4, .5, .6, .7, .8, .9, 1], xName: 'waited',
          xLabel: tier === 'strategic' ? 'how long the mission had been in the queue when the operator first opened it' : 'how long the tactical planner sat open before the operator’s first action on it',
          yLabel: tier === 'strategic' ? '% of strategic decisions where a card was taken' : '% of tactical plans where Suggest was pressed',
          ref: { y: Wt.overall, label: 'overall ' + pct(Wt.overall, 0) } });
        legend(box, ser.map(se => ({ label: se.label + (se.pts[0] && se.pts[0].lo != null ? ' (95% CI, people resampled)' : ''), color: se.color })));
        say(box, `${Wt.n} ${tier === 'strategic' ? 'decisions' : 'plans'} from ${Wt.people} people (median wait ${num(Wt.median, 0)} s). Comparing each person with themselves, every doubling of the wait multiplies the odds of ${tier === 'strategic' ? 'taking the card' : 'pressing Suggest'} by ${num(m.est, 2)} [${num(m.lo, 2)}, ${num(m.hi, 2)}], ${pval(m.p)}; also holding the queue fixed, ${num(Wt.models['plus queue'].est, 2)}, ${pval(Wt.models['plus queue'].p)}.`);
        tableFor(box, ['Waited', 'n', 'People', 'Raw', 'Raw 95% CI', 'Expected', 'Adjusted', 'Adj. 95% CI', 'Mission drones', 'Minute', 'Their usual rate'],
          B.map(b => [b.label, b.n, b.people, pct(b.raw, 0), `${pct(b.rawLo, 0)}–${pct(b.rawHi, 0)}`, pct(b.exp, 0), pct(b.adj, 0), `${pct(b.adjLo, 0)}–${pct(b.adjHi, 0)}`, num(b.ndrones, 1), num(b.minute, 1), pct(b.person, 0)]));
      };
      host.insertBefore(btnBar(host, 'Assistant', [['strategic', 'Strategic (mission left in the queue)'], ['tactical', 'Tactical (plan left open)']], tier, k => { tier = k; draw(); }), box);
      host.insertBefore(btnBar(host, 'View', [['raw', 'Raw'], ['exp', 'Raw + expected'], ['adj', 'Adjusted']], mode, k => { mode = k; draw(); }), box);
      draw();
    },

    /* B — every specification of the within-person queue effect */
    'load.robust': host => {
      if (!ok(host, D && D.null, 'the robustness strip')) return;
      let tier = 'strategic';
      const box = h('div', {}, host);
      const draw = () => {
        box.innerHTML = '';
        const R = D.null[tier].robust.map(x => Object.assign({}, x, { main: /main/.test(x.label), sub: x.label.startsWith('Game') || /games only/.test(x.label) ? 'within one game / pair of games: the comparison is between moments of the same person in the same game' : '' }));
        orForest(box, R, { lim: 3, padL: 260, left: '← less reliance when busier', right: 'more reliance when busier →' });
        const d = D.null[tier].detect;
        say(box, `Each row: the change in the odds of ${tier === 'strategic' ? 'taking a strategy card' : 'pressing Suggest'} per extra mission waiting, comparing each person with themselves. Main model (thick): if the true effect sat at the ends of its CI, going from 0 to 5 waiting would move the rate from ${pct(d.base, 0)} to between ${pct(d.lo, 0)} and ${pct(d.hi, 0)}.`);
      };
      host.insertBefore(btnBar(host, 'Assistant', [['strategic', 'Strategic'], ['tactical', 'Tactical']], tier, k => { tier = k; draw(); }), box);
      draw();
    },

    /* C1 — said vs did, per person */
    'load.saidDid': host => {
      if (!ok(host, D && D.saidDid, 'said vs did')) return;
      let tier = 'strategic', view = 'slope';
      const box = h('div', {}, host);
      const draw = () => {
        box.innerHTML = '';
        if (view === 'slope') {
          const P = D.saidDid.slopes[tier];
          const g = (k, lab, col) => ({ label: lab, color: col, sub: `${P[k].positive} of ${P[k].n} lean upward`, mean: P[k].mean, lo: P[k].lo, hi: P[k].hi,
            pts: P.points.filter(p => p.said === (k === 'said' ? 1 : 0)).map(p => ({ label: p.pid, v: p.slope, tip: `${p.n} decisions · queue avg ${num(p.meanQ, 1)}, max ${p.maxQ} · raw slope ${pp(p.slopeRaw)}` })) });
          dotRows(box, [g('said', 'Said they hand over when busy (C11)', css('--bad')), g('notSaid', 'Did not say so', css('--mark-soft'))],
            { lim: 0.25, fmt: pp, xLabel: `each person's own change in ${tier === 'strategic' ? 'card-taking' : 'Suggest use'} per extra mission waiting (adjusted, percentage points)` });
          say(box, `Groups differ: ${pval(P.pDiff)} (Mann–Whitney). "Said" group's slopes vs zero: ${pval(P.pSaidVsZero)}. Bar = group mean with 95% CI; dots = people.`);
        } else {
          const P = D.saidDid.busier[tier];
          const g = (k, lab, col) => ({ label: lab, color: col, sub: `${P[k].adjDiff.higher} of ${P[k].adjDiff.n} higher in the heavier game`, mean: P[k].adjDiff.mean, lo: P[k].adjDiff.lo, hi: P[k].adjDiff.hi,
            pts: P.points.filter(p => p.said === (k === 'said' ? 1 : 0)).map(p => ({ label: p.pid, v: p.adjDiff, tip: `heavier ${p.heavy}: ${pct(p.rawHeavy, 0)} raw · lighter ${p.light}: ${pct(p.rawLight, 0)} raw` })) });
          dotRows(box, [g('said', 'Said they hand over when busy (C11)', css('--bad')), g('notSaid', 'Did not say so', css('--mark-soft'))],
            { lim: 0.5, fmt: pp, xLabel: `${tier === 'strategic' ? 'card-taking' : 'Suggest use'}: heavier game minus lighter game (adjusted, percentage points)` });
        }
      };
      host.insertBefore(btnBar(host, 'Assistant', [['strategic', 'Strategic'], ['tactical', 'Tactical']], tier, k => { tier = k; draw(); }), box);
      host.insertBefore(btnBar(host, 'Compare', [['slope', 'Moment to moment (queue)'], ['busier', 'Busier vs lighter game']], view, k => { view = k; draw(); }), box);
      draw();
    },

    /* C2 — spoken overload during play vs random utterances */
    'load.spoken': host => {
      const N = D && D.saidDid && D.saidDid.narration;
      if (!ok(host, N, 'the narration moments')) return;
      h('p', { class: 'cap', html: `<b>${N.moments}</b> spoken-overload moments from <b>${N.momentPeople}</b> people (${N.sessions} narrated sessions, ${N.people} people, ${N.utterances} utterances). Red line = the observed average; grey = 5,000 draws of the same number of random utterances from the same sessions.` }, host);
      [['queue', 'Missions waiting at the moment they said it', v => num(v, 2)],
       ['took', 'Strategy cards taken within ±60 s (adjusted: observed − expected)', v => sgn(v, 3)],
       ['consulted', 'Suggest pressed within ±60 s (adjusted: observed − expected)', v => sgn(v, 3)]].forEach(([k, t, f]) => {
        const d = h('div', {}, host);
        h('p', { class: 'cap', html: `<b>${t}</b> — ${pval(N[k].p)}` }, d);
        nullHist(d, N[k], { fmt: f, title: t, xLabel: k === 'queue' ? 'mean missions waiting' : 'mean (observed − expected)' });
      });
    },

    /* D — backlog vs practice */
    'load.backlog': host => {
      const B = D && D.backlog;
      if (!ok(host, B, 'backlog vs practice')) return;
      let mode = 'both';
      const box = h('div', {}, host);
      const draw = () => {
        box.innerHTML = '';
        const xs = B.bins.map(b => b.label);
        const raw = { label: 'Raw', color: css('--s-tac'), faint: mode !== 'raw', hollow: mode !== 'raw', pts: B.bins.map(b => ({ x: b.label, y: b.raw, lo: b.rawLo, hi: b.rawHi, n: b.n, tip: `${b.people} people · average minute ${num(b.minute, 1)}` })) };
        const noMin = { label: 'Adjusted for plan, game, person — NOT minute', color: css('--ink-3'), dash: true, pts: B.bins.map(b => ({ x: b.label, y: b.adjNoMin, lo: b.adjNoMinLo, hi: b.adjNoMinHi, n: b.n })) };
        const adj = { label: '… and minute of the session', color: css('--s-tac'), pts: B.bins.map(b => ({ x: b.label, y: b.adj, lo: b.adjLo, hi: b.adjHi, n: b.n })) };
        const ser = mode === 'raw' ? [raw] : [raw, noMin, adj];
        ciChart(box, xs, ser, { lo: .5, hi: 1, ticks: [.5, .6, .7, .8, .9, 1], xName: 'backlog', xLabel: 'missions waiting for a strategic decision when the operator starts on the plan', yLabel: 'plans with Suggest pressed' });
        legend(box, ser.map(se => ({ label: se.label, color: se.color })));
      };
      host.insertBefore(btnBar(host, 'View', [['raw', 'Raw'], ['both', 'Raw and adjusted']], mode, k => { mode = k; draw(); }), box);
      draw();
      // both rise with the minute
      const d2 = h('div', {}, host);
      h('p', { class: 'cap', html: '<b>Why minute matters:</b> both the backlog and Suggest use climb over the session (first minutes vs later).' }, d2);
      const M = B.byMinute, xs = M.map(m => String(m.minute + 1));
      const mxB = Math.max(...M.map(m => m.backlog)) * 1.15;
      ciChart(d2, xs, [{ label: 'Suggest pressed', color: css('--s-tac'), pts: M.map(m => ({ x: String(m.minute + 1), y: m.suggest, n: m.n })) },
        { label: 'Backlog (scaled: top of axis = ' + num(mxB, 1) + ' missions)', color: css('--ink-3'), dash: true, pts: M.map(m => ({ x: String(m.minute + 1), y: m.backlog / mxB, n: m.n, tip: `backlog ${num(m.backlog, 2)} missions` })) }],
        { lo: 0, hi: 1, height: 220, xName: 'minute', xLabel: 'minute of the 8-minute session', yLabel: 'rate / scaled backlog' });
      legend(d2, [{ label: 'Suggest pressed (share of plans)', color: css('--s-tac') }, { label: 'Missions waiting (scaled)', color: css('--ink-3') }]);
    },

    /* E — deep queues: between people vs within */
    'load.deep': host => {
      const E = D && D.deep;
      if (!ok(host, E, 'deep queues')) return;
      let tier = 'strategic';
      const box = h('div', {}, host);
      const draw = () => {
        box.innerHTML = '';
        const X = E[tier], col = css(TIER[tier][0]);
        const H = 300, padL = 56, padR = 20, padT = 16, padB = 46, s = svgRoot(box, W, H);
        const mx = Math.max(0.1, ...X.persons.map(p => p.share)) * 1.08;
        const x = v => padL + (W - padL - padR) * v / mx, y = v => H - padB - (H - padB - padT) * v;
        [0, .25, .5, .75, 1].forEach(v => { el('line', { x1: padL, x2: W - padR, y1: y(v), y2: y(v), stroke: css('--grid') }, s); txt(s, padL - 8, y(v) + 4, pct(v, 0), { 'text-anchor': 'end' }); });
        [0, mx / 2, mx].forEach(v => txt(s, x(v), H - padB + 16, pct(v, 0), { 'text-anchor': 'middle' }));
        txt(s, (padL + W - padR) / 2, H - 8, 'share of this person\'s decisions made with 4+ others waiting', { 'text-anchor': 'middle', 'font-family': 'inherit', 'font-size': 11.5 });
        txt(s, 14, (padT + H - padB) / 2, tier === 'strategic' ? 'cards taken (all their decisions)' : 'Suggest pressed (all their plans)', { transform: `rotate(-90 14 ${(padT + H - padB) / 2})`, 'text-anchor': 'middle', 'font-family': 'inherit', 'font-size': 11.5 });
        X.persons.forEach(p => { const c = el('circle', { cx: x(p.share), cy: y(p.rate), r: 4 + Math.sqrt(p.n) / 2, fill: col, opacity: .55 }, s); hoverable(c, `<b>${p.pid}</b><br>${pct(p.share, 0)} of ${p.n} decisions with 4+ waiting<br>rate ${pct(p.rate, 0)}`); });
        say(box, `Between people (dots): those who often face deep queues rely LESS (Spearman ρ = ${num(X.rho, 2)}, ${pval(X.rhoP)}) — and they are the people working bigger missions by hand (ρ with mission size ${num(X.rhoSize, 2)}). Within a person (same model, own deep vs own shallow moments): odds ×${num(X.within.est, 2)} [${num(X.within.lo, 2)}, ${num(X.within.hi, 2)}], ${pval(X.within.p)} — no change. Of ${X.pairedN} people who met both, ${X.pairedHigher} relied more (adjusted) when deep, ${X.pairedLower} less.`);
      };
      host.insertBefore(btnBar(host, 'Assistant', [['strategic', 'Strategic'], ['tactical', 'Tactical']], tier, k => { tier = k; draw(); }), box);
      draw();
    },

    /* F1 — which mission is picked: oldest / top-3 vs chance */
    'load.pickOrder': host => {
      const T_ = D && D.triage;
      if (!ok(host, T_, 'triage')) return;
      let k = 'oldest';
      const box = h('div', {}, host);
      const draw = () => {
        box.innerHTML = '';
        const B = T_.bins, xs = B.map(b => b.label);
        const ch = k === 'oldest' ? 'chOld' : k === 'top3' ? 'chTop3' : 'chSmall';
        const lab = k === 'oldest' ? 'Opened the OLDEST waiting mission' : k === 'top3' ? 'Opened one of the top 3 in the list' : 'Opened the SMALLEST waiting mission';
        ciChart(box, xs, [{ label: lab, color: css('--s-strat'), pts: B.map(b => ({ x: b.label, y: b[k], lo: b[k + 'Lo'], hi: b[k + 'Hi'], n: b.n, tip: `${b.people} people` })) },
          { label: 'If they picked at random from what was waiting', color: css('--ink-3'), dash: true, pts: B.map(b => ({ x: b.label, y: b[ch] })) }],
          { lo: 0, hi: 1, xName: 'others waiting', xLabel: 'number of OTHER missions waiting when the operator opened one (decisions with a choice to make)', yLabel: '% of decisions that opened this mission', vline: vAt(2.5, 1), vlabel: VLAB });
        legend(box, [{ label: lab + ' (95% CI)', color: css('--s-strat') }, { label: 'chance: picking at random from what was waiting', color: css('--ink-3') }]);
      };
      host.insertBefore(btnBar(host, 'Picked', [['oldest', 'Oldest'], ['top3', 'Top 3 of list'], ['smallest', 'Smallest']], k, v => { k = v; draw(); }), box);
      draw();
    },

    /* F2 — size of what is picked vs what is waiting */
    'load.pickSize': host => {
      const T_ = D && D.triage;
      if (!ok(host, T_, 'triage')) return;
      const B = T_.bins, xs = B.map(b => b.label);
      ciChart(h('div', {}, host), xs, [
        { label: 'Opened mission', color: css('--s-strat'), pts: B.map(b => ({ x: b.label, y: b.picked, lo: b.pickedLo, hi: b.pickedHi, n: b.n })) },
        { label: 'Average of the others waiting', color: css('--ink-3'), dash: true, pts: B.map(b => ({ x: b.label, y: b.waiting, lo: b.waitingLo, hi: b.waitingHi, n: b.n })) }],
        { lo: 0, hi: 12, ticks: [0, 3, 6, 9, 12], fmt: v => num(v, 0), xName: 'others waiting', xLabel: 'other missions waiting', yLabel: 'drones the mission needs', vline: vAt(2.5, 1), vlabel: VLAB, height: 240 });
      legend(host, [{ label: 'Opened mission (95% CI)', color: css('--s-strat') }, { label: 'Others waiting at that moment', color: css('--ink-3') }]);
      ciChart(h('div', {}, host), xs, [{ label: 'Size rank of the opened mission', color: css('--s-strat'), pts: B.map(b => ({ x: b.label, y: b.rank, lo: b.rankLo, hi: b.rankHi, n: b.n })) }],
        { lo: 0, hi: 1, ticks: [0, .25, .5, .75, 1], fmt: v => v === 0 ? 'smallest' : v === 1 ? 'largest' : num(v, 2), xName: 'others waiting', xLabel: 'other missions waiting', yLabel: 'rank among waiting', ref: { y: .5, label: 'random pick' }, vline: vAt(2.5, 1), height: 220 });
      const L = T_.choice && T_.choice.longByGame;
      if (L) say(host, 'Decisions made with 4+ others waiting, by game: ' + Object.entries(L).map(([g, n]) => `${g.replace('|', ' game ')} ${n}`).join(', ') + '. Long queues are almost all in the Strategic Heavy games, where every mission is smaller.');
    },

    /* F3 — what makes a waiting mission get picked (conditional logit), short vs long queue */
    'load.choice': host => {
      const C = D && D.triage && D.triage.choice;
      if (!ok(host, C, 'the choice model')) return;
      let scope = 'strategicGames';
      const box = h('div', {}, host);
      const NAMES = { oldest: 'It is the oldest waiting', newest: 'It is the newest arrival', size: 'Per 3 more drones than the others', resid: 'It is a left-over (residual) mission' };
      const draw = () => {
        box.innerHTML = '';
        const rows = [];
        [['short', '1–3 others waiting', css('--mark-soft')], ['long', '4+ others waiting', css('--s-strat')]].forEach(([k, lab, col]) => {
          const c = C[scope + '.' + k];
          if (!c) return;
          rows.push({ head: true, label: `${lab} (${c.decisions} decisions, ${c.people} people)` });
          Object.entries(c.terms).forEach(([f, v]) => rows.push({ label: NAMES[f], est: v.est, lo: v.lo, hi: v.hi, color: col, right: '×' + num(v.est, 2), sub: '95% CI from resampling people' }));
        });
        orForest(box, rows, { lim: 8, ticks: [0.25, 0.5, 1, 2, 4, 8], padL: 250, left: '← less likely to be opened', right: 'more likely →', zero: 'no pull' });
      };
      host.insertBefore(btnBar(host, 'Games', [['strategicGames', 'Strategic Heavy games only'], ['all', 'All four games']], scope, k => { scope = k; draw(); }), box);
      draw();
    },

    /* pass 3 — the choice model with p-values, and a direct test of short vs long queues */
    'load.choiceSig': host => {
      const C = D && D.triage && D.triage.choiceSig;
      if (!ok(host, C, 'the choice model significance (rerun load.py)')) return;
      let scope = 'strategicGames';
      const box = h('div', {}, host);
      const NAMES = { oldest: 'It is the oldest waiting', newest: 'It is the newest arrival', size: 'Per 3 more drones than the others', resid: 'It is a left-over (residual) mission' };
      const draw = () => {
        box.innerHTML = '';
        const c = C[scope];
        if (!c) { say(box, 'No data for this scope.'); return; }
        const rows = [];
        [['short', '1–3 others waiting', css('--mark-soft')], ['long', '4+ others waiting', css('--s-strat')]].forEach(([k, lab, col]) => {
          const q = c[k];
          rows.push({ head: true, label: `${lab} (${q.decisions} decisions, ${q.people} people)` });
          Object.entries(q.terms).forEach(([f, v]) => rows.push({ label: NAMES[f], est: v.est, lo: v.lo, hi: v.hi, p: v.p, color: col,
            sub: `bootstrap ${pval(v.p)} (people resampled ${C.nBoot}×); model-based Wald ${pval(v.pWald)}` }));
        });
        rows.push({ head: true, label: 'Does the pull change when the queue is long? (long ÷ short)' });
        Object.entries(c.ratio).forEach(([f, v]) => rows.push({ label: NAMES[f], est: v.est, lo: v.lo, hi: v.hi, p: v.p, color: css('--mark'),
          sub: 'ratio of the two odds ratios; 1 = the same pull at both queue lengths' }));
        orForest(box, rows, { lim: 8, ticks: [0.25, 0.5, 1, 2, 4, 8], padL: 250, left: '← less likely', right: 'more likely →', zero: 'no pull (×1)', xTitle: 'odds ratio of being opened, log scale (bottom block: long ÷ short)' });
        const sig = Object.entries(c.ratio).filter(([, v]) => v.p < .05).map(([f]) => NAMES[f].toLowerCase());
        say(box, `Right-hand column: p-value for each estimate (bootstrap over people; coloured when below .10). Short vs long: ${sig.length ? 'differs for ' + sig.join(', ') : 'no feature’s pull differs significantly between short and long queues'}. `
          + 'Intervals and p-values come from resampling whole people, so they allow for each person making many decisions.');
      };
      host.insertBefore(btnBar(host, 'Games', [['strategicGames', 'Strategic Heavy games only'], ['all', 'All four games']], scope, k => { scope = k; draw(); }), box);
      draw();
    },

    /* F4 — pace: decisions per minute and seconds per decision against the queue */
    'load.pace': host => {
      const P = D && D.pace;
      if (!ok(host, P, 'pace')) return;
      const R = P.rateBins;
      ciChart(h('div', {}, host), R.map(b => b.label), [{ label: 'Strategic decisions in the minute', color: css('--s-strat'), pts: R.map(b => ({ x: b.label, y: b.perMin, lo: b.lo, hi: b.hi, n: b.n, tip: 'n = person-minutes' })) }],
        { lo: 0, hi: 2.5, ticks: [0, .5, 1, 1.5, 2, 2.5], fmt: v => num(v, 1), xName: 'waiting at minute start', xLabel: 'missions waiting at the start of the minute', yLabel: 'decisions per minute', vline: vAt(3.5, 0), vlabel: 'list full beyond here (~3.5 cards)', height: 230 });
      const B = P.bins;
      ciChart(h('div', {}, host), B.map(b => b.label), [{ label: 'Seconds to decide (median, IQR)', color: css('--s-strat'), pts: B.map(b => ({ x: b.label, y: b.secs, lo: b.secsQ1, hi: b.secsQ3, n: b.n, tip: `beyond the forced card reveal: ${num(b.net, 1)} s · decided before the cards loaded ${pct(b.early, 0)}` })) }],
        { lo: 0, hi: 30, ticks: [0, 10, 20, 30], fmt: v => num(v, 0) + ' s', xName: 'waiting', xLabel: 'other missions waiting', yLabel: 'seconds per strategic decision', vline: VL, height: 220 });
      say(host, `Within person: each extra mission waiting → decisions per minute ×${num(P.rate.est, 2)} [${num(P.rate.lo, 2)}, ${num(P.rate.hi, 2)}] (${pval(P.rate.p)}); seconds per decision ${sgn(P.secs.pct, 1)}% [${sgn(P.secs.pctLo, 1)}, ${sgn(P.secs.pctHi, 1)}] (${pval(P.secs.p)}); deciding before the cards load ×${num(P.early.est, 2)} (${pval(P.early.p)}).`);
    },

    /* games: how heavy each is */
    'load.games': host => {
      if (!ok(host, D && D.games, 'games')) return;
      barsH(host, D.games.map(g => ({ label: g.game.replace('|', ' game '), value: g.drones, sub: `${g.arrivals} missions · ${g.tasks} tasks · mean queue ${num(g.meanQ, 2)} · ${g.sessions} sessions` })), { fmt: v => num(v, 0) + ' drones', padL: 150 });
    },
  });
})();
