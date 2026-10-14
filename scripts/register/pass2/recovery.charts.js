/* Pass 2 · area `recovery` — "Trust, tiers and recovery". Data: DATA.pass2.recovery
   (written by scripts/register/pass2/recovery.py). Every chart draws into `host` (a div), uses a
   700-wide viewBox, colours from CSS tokens only, and degrades to a short note when data is missing. */
(() => {
  const D = (DATA.pass2 || {}).recovery;
  const W = 700;
  const missing = (host, what) => { h('p', { class: 'cap', text: `No data for ${what} — run scripts/register/pass2/recovery.py.` }, host); };
  const safe = (name, fn) => host => { try { if (!D) return missing(host, name); fn(host); } catch (e) { host.innerHTML = ''; missing(host, name + ' (' + e.message + ')'); } };
  const T = (s, x, y, txt, o = {}) => { const t = el('text', Object.assign({ x, y, fill: css('--ink-2'), 'font-size': 12 }, o), s); t.textContent = txt; return t; };
  const mono = () => css('--mono');
  const fmtS = v => v == null ? '—' : num(v, 1) + ' s';

  /* horizontal rate bars with a 95% CI whisker and the n on the right */
  function rateCI(host, rows, o = {}) {
    const rowH = o.rowH || 34, padL = o.padL || 230, padR = 110, padT = 8, padB = 30;
    const H = padT + rows.length * rowH + padB;
    const s = svgRoot(host, W, H);
    const max = o.max != null ? o.max : 1;
    const x = v => padL + (W - padL - padR) * (v / max);
    [0, .25, .5, .75, 1].map(f => f * max).forEach(v => {
      el('line', { x1: x(v), x2: x(v), y1: padT, y2: H - padB, stroke: css('--grid') }, s);
      T(s, x(v), H - padB + 15, o.tick ? o.tick(v) : pct(v, 0), { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 10.5, 'font-family': mono() });
    });
    if (o.xLabel) T(s, padL + (W - padL - padR) / 2, H - 3, o.xLabel, { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 11 });
    rows.forEach((r, i) => {
      const y = padT + i * rowH, cy = y + rowH / 2;
      T(s, padL - 10, cy + 4, r.label, { 'text-anchor': 'end', 'font-size': 12.5 });
      if (r.value == null) { T(s, padL + 6, cy + 4, 'no cases', { fill: css('--ink-3'), 'font-size': 11 }); return; }
      el('rect', { x: padL, y: cy - 7, width: Math.max(1, x(r.value) - padL), height: 14, rx: 4, fill: r.color || css('--mark') }, s);
      if (r.lo != null && r.hi != null) {
        el('line', { x1: x(r.lo), x2: x(r.hi), y1: cy, y2: cy, stroke: css('--ink-2'), 'stroke-width': 1.5 }, s);
        [r.lo, r.hi].forEach(v => el('line', { x1: x(v), x2: x(v), y1: cy - 5, y2: cy + 5, stroke: css('--ink-2'), 'stroke-width': 1.5 }, s));
      }
      T(s, W - padR + 8, cy + 4, (o.fmt || (v => pct(v, 0)))(r.value) + (r.n != null ? `  n=${r.n}` : ''), { 'font-size': 11.5, 'font-family': mono() });
      const hit = el('rect', { x: 0, y, width: W, height: rowH, fill: 'transparent' }, s);
      hoverable(hit, `<b>${r.label}</b><br>${(o.fmt || (v => pct(v, 0)))(r.value)}` + (r.lo != null ? ` [${(o.fmt || (v => pct(v, 0)))(r.lo)}, ${(o.fmt || (v => pct(v, 0)))(r.hi)}] 95% CI` : '') + (r.sub ? '<br>' + r.sub : ''));
    });
  }

  /* estimate ± CI rows on a linear scale with a zero line (differences on the 1–7 trust scale) */
  function ciRows(host, rows, o = {}) {
    const rowH = 30, padL = o.padL || 210, padR = 120, padT = 10, padB = 34;
    const H = padT + rows.length * rowH + padB;
    const s = svgRoot(host, W, H);
    const lo = o.lo != null ? o.lo : Math.min(0, ...rows.map(r => r.lo)) - .2, hi = o.hi != null ? o.hi : Math.max(...rows.map(r => r.hi)) + .2;
    const x = v => padL + (W - padL - padR) * ((v - lo) / (hi - lo));
    const ticks = []; for (let v = Math.ceil(lo * 2) / 2; v <= hi + 1e-9; v += .5) ticks.push(v);
    ticks.forEach(v => { el('line', { x1: x(v), x2: x(v), y1: padT, y2: H - padB, stroke: v === 0 ? css('--ink-3') : css('--grid'), 'stroke-width': v === 0 ? 1.5 : 1 }, s);
      T(s, x(v), H - padB + 15, sgn(v, 1), { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 10.5, 'font-family': mono() }); });
    T(s, padL + (W - padL - padR) / 2, H - 4, o.xLabel || 'tactical minus strategic (points on the 1–7 scale)', { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 11 });
    rows.forEach((r, i) => {
      const cy = padT + i * rowH + rowH / 2;
      T(s, padL - 10, cy + 4, r.label, { 'text-anchor': 'end', 'font-size': 12.5 });
      if (r.est == null) return;
      const col = r.lo > 0 || r.hi < 0 ? css('--s-tac') : css('--mark-soft');
      if (r.lo != null) el('line', { x1: x(r.lo), x2: x(r.hi), y1: cy, y2: cy, stroke: col, 'stroke-width': 2, 'stroke-linecap': 'round' }, s);
      el('circle', { cx: x(r.est), cy, r: 5.5, fill: col, stroke: css('--surface'), 'stroke-width': 2 }, s);
      T(s, W - padR + 10, cy + 4, `${sgn(r.est, 2)}  n=${r.n}`, { 'font-size': 11.5, 'font-family': mono() });
      const hit = el('rect', { x: 0, y: cy - rowH / 2, width: W, height: rowH, fill: 'transparent' }, s);
      hoverable(hit, `<b>${r.label}</b><br>${sgn(r.est, 2)} [${sgn(r.lo, 2)}, ${sgn(r.hi, 2)}] 95% CI<br>n = ${r.n}${r.sub ? '<br>' + r.sub : ''}`);
    });
  }

  /* generic scatter */
  function scatter(host, pts, o) {
    const H = o.height || 380, padL = 62, padR = 24, padT = 18, padB = 46;
    const s = svgRoot(host, W, H);
    const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
    const [x0, x1] = o.xr || [Math.min(...xs), Math.max(...xs)], [y0, y1] = o.yr || [Math.min(...ys), Math.max(...ys)];
    const X = v => padL + (W - padL - padR) * ((v - x0) / (x1 - x0)), Y = v => H - padB - (H - padB - padT) * ((v - y0) / (y1 - y0));
    (o.xt || []).forEach(v => { el('line', { x1: X(v), x2: X(v), y1: padT, y2: H - padB, stroke: v === 0 && o.zero ? css('--ink-3') : css('--grid') }, s);
      T(s, X(v), H - padB + 15, (o.xf || (v => num(v, 1)))(v), { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 10.5, 'font-family': mono() }); });
    (o.yt || []).forEach(v => { el('line', { x1: padL, x2: W - padR, y1: Y(v), y2: Y(v), stroke: v === 0 && o.zero ? css('--ink-3') : css('--grid') }, s);
      T(s, padL - 8, Y(v) + 4, (o.yf || (v => num(v, 1)))(v), { 'text-anchor': 'end', fill: css('--ink-3'), 'font-size': 10.5, 'font-family': mono() }); });
    T(s, padL + (W - padL - padR) / 2, H - 6, o.xLabel, { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 11.5 });
    const yl = T(s, 14, padT + (H - padT - padB) / 2, o.yLabel, { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 11.5 });
    yl.setAttribute('transform', `rotate(-90 14 ${padT + (H - padT - padB) / 2})`);
    (o.notes || []).forEach(n => T(s, X(n.x), Y(n.y), n.text, { 'text-anchor': n.anchor || 'middle', fill: css('--ink-3'), 'font-size': 11, 'font-style': 'italic' }));
    pts.forEach(p => {
      const c = el('circle', { cx: X(p.x), cy: Y(p.y), r: p.r || 6, fill: p.color || css('--mark'), 'fill-opacity': .85, stroke: css('--surface'), 'stroke-width': 2 }, s);
      if (p.ring) c.setAttribute('stroke', p.ring);
      hoverable(c, p.tip);
    });
    return { s, X, Y };
  }

  const PREF_COL = k => k === 'tactical' ? css('--s-tac') : k === 'strategic' ? css('--s-strat') : css('--mark-soft');

  Object.assign(CH, {
    /* ───────────── f-tier-trust ───────────── */
    'recovery.trustPairs': safe('trust per person', host => {
      const P = D.trust.people.slice().sort((a, b) => (a.t - a.s) - (b.t - b.s)), G = D.trust.gap;
      const H = 330, padL = 52, padR = 150, padT = 16, padB = 40, s = svgRoot(host, W, H);
      const step = (W - padL - padR) / P.length, Y = v => H - padB - (H - padB - padT) * ((v - 1) / 6);
      [1, 2, 3, 4, 5, 6, 7].forEach(v => { el('line', { x1: padL, x2: W - 20, y1: Y(v), y2: Y(v), stroke: css('--grid') }, s);
        T(s, padL - 8, Y(v) + 4, v, { 'text-anchor': 'end', fill: css('--ink-3'), 'font-size': 10.5, 'font-family': mono() }); });
      P.forEach((p, i) => {
        const cx = padL + step * (i + .5), up = p.t > p.s;
        el('line', { x1: cx, x2: cx, y1: Y(p.s), y2: Y(p.t), stroke: up ? css('--s-tac') : css('--s-strat'), 'stroke-width': 2, opacity: .7 }, s);
        el('circle', { cx, cy: Y(p.s), r: 4, fill: css('--s-strat'), stroke: css('--surface'), 'stroke-width': 1.5 }, s);
        el('circle', { cx, cy: Y(p.t), r: 4, fill: css('--s-tac'), stroke: css('--surface'), 'stroke-width': 1.5 }, s);
        const hit = el('rect', { x: cx - step / 2, y: padT, width: step, height: H - padT - padB, fill: 'transparent' }, s);
        hoverable(hit, `<b>${p.pid}</b><br>Strategic ${num(p.s, 2)} · Tactical ${num(p.t, 2)}<br>gap ${sgn(p.t - p.s, 2)} (mean of their 2 sessions)`);
      });
      const yt = T(s, 12, padT + (H - padT - padB) / 2, 'trust in the assistant (1–7)', { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 11 });
      yt.setAttribute('transform', `rotate(-90 12 ${padT + (H - padT - padB) / 2})`);
      T(s, padL + (W - padL - padR) / 2, H - 10, `${P.length} operators, sorted by their gap (tactical − strategic)`, { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 11.5 });
      // group means with CI on the right
      const mx = W - padR + 50;
      [['Strategic', G.strategic, css('--s-strat'), -16], ['Tactical', G.tactical, css('--s-tac'), 16]].forEach(([lab, m, c, dx]) => {
        el('line', { x1: mx + dx, x2: mx + dx, y1: Y(m.lo), y2: Y(m.hi), stroke: c, 'stroke-width': 2 }, s);
        el('circle', { cx: mx + dx, cy: Y(m.mean), r: 6.5, fill: c, stroke: css('--surface'), 'stroke-width': 2 }, s);
        T(s, mx + dx + (dx > 0 ? 10 : -10), Y(m.mean) + 4, `${lab} ${num(m.mean, 2)}`, { 'text-anchor': dx > 0 ? 'start' : 'end', 'font-size': 11, fill: css('--ink-2') });
      });
      T(s, mx, padT + 4, 'mean ± 95% CI', { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 10.5 });
      legend(host, [{ label: 'Strategic Assistant', color: css('--s-strat') }, { label: 'Tactical Assistant', color: css('--s-tac') }]);
      h('p', { class: 'cap', text: `Trust, 1–7 (mean of six items, averaged over each person's two sessions). ${G.higherTac} of ${G.n} higher for tactical, ${G.higherStrat} higher for strategic, ${G.tied} tied. Gap ${sgn(G.diff, 2)} [${sgn(G.lo, 2)}, ${sgn(G.hi, 2)}], ${pval(G.p)}.` }, host);
    }),
    'recovery.trustSplits': safe('trust splits', host => {
      const box = h('div', {}, host), TR = D.trust;
      const views = {
        items: () => ciRows(box, TR.items.map(i => ({ label: i.label, est: i.diff, lo: i.lo, hi: i.hi, n: i.n, sub: `Strategic ${num(i.s, 2)} · Tactical ${num(i.t, 2)} · ${pval(i.p)}` }))),
        game: () => ciRows(box, TR.byGame.map(g => ({ label: g.game.replace('strategic|', 'Strategic Heavy game ').replace('tactical|', 'Tactical Heavy game '), est: g.gapmean, lo: g.gaplo, hi: g.gaphi, n: g.gapn, sub: `Strategic ${num(g.s, 2)} · Tactical ${num(g.t, 2)} (sessions)` }))),
        run: () => ciRows(box, TR.byRun.map(g => ({ label: 'Session ' + g.run, est: g.gapmean, lo: g.gaplo, hi: g.gaphi, n: g.gapn, sub: `Strategic ${num(g.s, 2)} · Tactical ${num(g.t, 2)}` }))),
      };
      host.insertBefore(btnBar(host, 'Split by', [['items', 'Questionnaire item'], ['game', 'Game played'], ['run', 'First / second session']], 'items', k => views[k]()), box);
      views.items();
    }),
    /* pass 3: the four games merged into the two scenarios */
    'recovery.trustSplits2': safe('trust splits by scenario', host => {
      const box = h('div', {}, host), TR = D.trust, BS = TR.byScenario;
      const SCN = { strategic: 'Strategic Heavy sessions', tactical: 'Tactical Heavy sessions' };
      const views = {
        items: () => ciRows(box, TR.items.map(i => ({ label: i.label, est: i.diff, lo: i.lo, hi: i.hi, n: i.n, sub: `Strategic ${num(i.s, 2)} · Tactical ${num(i.t, 2)} · ${pval(i.p)}` }))),
        scenario: () => {
          ciRows(box, BS.rows.map(g => ({ label: SCN[g.scen], est: g.gapmean, lo: g.gaplo, hi: g.gaphi, n: g.gapn,
            sub: `Strategic ${num(g.s.mean, 2)} [${num(g.s.lo, 2)}, ${num(g.s.hi, 2)}] · Tactical ${num(g.t.mean, 2)} [${num(g.t.lo, 2)}, ${num(g.t.hi, 2)}]<br>both games of this scenario pooled; n = sessions, one per person` })), { lo: -0.5, hi: 2.5 });
          const P = BS.paired, M = BS.model;
          h('p', { class: 'cap', html: `Every person played one session of each scenario, so the two rows are the same ${P.n} people. Their gap is larger in Strategic Heavy by ${sgn(P.gapDiff.mean, 2)} points [${sgn(P.gapDiff.lo, 2)}, ${sgn(P.gapDiff.hi, 2)}] (paired t ${pval(P.gapP)}, Wilcoxon ${pval(P.gapWil)}), `
            + `mostly because strategic trust is lower there (${sgn(P.sDiff.mean, 2)}, ${pval(P.sP)}) rather than tactical trust higher (${sgn(P.tDiff.mean, 2)}, ${pval(P.tP)}). `
            + `With scenario and session in one model: Strategic Heavy ${sgn(M.sh.est, 2)} [${sgn(M.sh.lo, 2)}, ${sgn(M.sh.hi, 2)}] (${pval(M.sh.p)}), second session ${sgn(M.run2.est, 2)} [${sgn(M.run2.lo, 2)}, ${sgn(M.run2.hi, 2)}] (${pval(M.run2.p)}).` }, box);
        },
        run: () => ciRows(box, TR.byRun.map(g => ({ label: 'Session ' + g.run, est: g.gapmean, lo: g.gaplo, hi: g.gaphi, n: g.gapn, sub: `Strategic ${num(g.s, 2)} · Tactical ${num(g.t, 2)}` })), { lo: -0.5, hi: 2.5 }),
      };
      host.insertBefore(btnBar(host, 'Split by', [['items', 'Questionnaire item'], ['scenario', 'Scenario played'], ['run', 'First / second session']], 'items', k => views[k]()), box);
      views.items();
    }),

    /* pass 3: checking cost, with a toggle to keep only the well-filled plan sizes */
    'recovery.checkCost2': safe('checking cost', host => {
      const C = D.checking, SUB = C.subset, WELL = ['3', '6–7', '8+'], box = h('div', {}, host);
      const draw = which => {
        box.innerHTML = '';
        const B = which === 'well' ? C.bins.filter(b => WELL.includes(b.label)) : C.bins;
        const H = 300, padT = 18, padB = 52, gap = 50, pw = (W - 60 - gap - 20) / 2, s = svgRoot(h('div', {}, box), W, H);
        const xL = 60, xR = 60 + pw + gap, n = B.length, bx = (x0, i) => x0 + pw * (i + .5) / n;
        const yR = v => H - padB - (H - padB - padT) * v, maxS = Math.max(10, ...B.map(b => b.netQ3 || 0)), yS = v => H - padB - (H - padB - padT) * (v / maxS);
        [0, .25, .5, .75, 1].forEach(v => { el('line', { x1: xL, x2: xL + pw, y1: yR(v), y2: yR(v), stroke: css('--grid') }, s);
          T(s, xL - 6, yR(v) + 4, pct(v, 0), { 'text-anchor': 'end', fill: css('--ink-3'), 'font-size': 10.5, 'font-family': mono() }); });
        for (let v = 0; v <= maxS; v += 2) { el('line', { x1: xR, x2: xR + pw, y1: yS(v), y2: yS(v), stroke: css('--grid') }, s);
          T(s, xR - 6, yS(v) + 4, v + ' s', { 'text-anchor': 'end', fill: css('--ink-3'), 'font-size': 10.5, 'font-family': mono() }); }
        T(s, xL + pw / 2, 12, 'Share of plans', { 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 600 });
        T(s, xR + pw / 2, 12, 'Checking time after the reveal (consulted plans)', { 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 600 });
        [['consulted', 'cLo', 'cHi', css('--mark-soft'), -7], ['kept', 'kLo', 'kHi', css('--s-tac'), 7]].forEach(([k, l, u, c, dx]) => {
          const pts = B.map((b, i) => [bx(xL, i) + dx, yR(b[k])]);
          el('polyline', { points: pts.map(p => p.join(',')).join(' '), fill: 'none', stroke: c, 'stroke-width': 1.5, opacity: .6 }, s);
          B.forEach((b, i) => { const cx = bx(xL, i) + dx;
            el('line', { x1: cx, x2: cx, y1: yR(b[l]), y2: yR(b[u]), stroke: c, 'stroke-width': 1.5 }, s);
            const d = el('circle', { cx, cy: yR(b[k]), r: 5, fill: c, stroke: css('--surface'), 'stroke-width': 1.5 }, s);
            hoverable(d, `<b>${b.label} drones</b><br>${k === 'kept' ? 'kept unmodified' : 'pressed Suggest'} ${pct(b[k], 0)} [${pct(b[l], 0)}, ${pct(b[u], 0)}]<br>n = ${b.n} plans, ${b.people} people`); });
        });
        B.forEach((b, i) => { const cx = bx(xR, i);
          el('rect', { x: cx - 10, y: yS(b.netQ3), width: 20, height: Math.max(1, yS(b.netQ1) - yS(b.netQ3)), rx: 4, fill: css('--s-tac'), 'fill-opacity': .25 }, s);
          el('line', { x1: cx - 10, x2: cx + 10, y1: yS(b.netMed), y2: yS(b.netMed), stroke: css('--s-tac'), 'stroke-width': 3 }, s);
          const hit = el('rect', { x: cx - 18, y: padT, width: 36, height: H - padT - padB, fill: 'transparent' }, s);
          hoverable(hit, `<b>${b.label} drones</b><br>median ${fmtS(b.netMed)} (IQR ${fmtS(b.netQ1)}–${fmtS(b.netQ3)})<br>≈ ${fmtS(b.perDrone)} per drone · forced reveal ≈ ${fmtS(b.reveal)} (excluded)<br>n = ${b.nCons} consulted plans`); });
        [[xL], [xR]].forEach(([x0]) => B.forEach((b, i) => {
          T(s, bx(x0, i), H - padB + 15, b.label, { 'text-anchor': 'middle', fill: css('--ink-2'), 'font-size': 10.5, 'font-family': mono() });
          T(s, bx(x0, i), H - padB + 28, `n=${x0 === xL ? b.n : b.nCons}`, { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 9.5, 'font-family': mono() });
        }));
        T(s, xL + pw / 2, H - 6, 'drones in the plan', { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 11 });
        T(s, xR + pw / 2, H - 6, 'drones in the plan', { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 11 });
        legend(box, [{ label: 'Pressed Suggest (consulted)', color: css('--mark-soft') }, { label: 'Kept the plan unmodified', color: css('--s-tac') }, { label: 'Checking time: median (bar) and middle half (box)', color: css('--s-tac') }]);
        tableFor(box, ['Drones', 'Plans', 'People', 'Consulted', 'Kept unmodified', 'Kept | consulted', 'Median check (s)', 'Per drone (s)'],
          B.map(b => [b.label, b.n, b.people, pct(b.consulted, 0), pct(b.kept, 0), b.keptGivenCons == null ? '—' : pct(b.keptGivenCons, 0), num(b.netMed, 1), num(b.perDrone, 2)]));
        const M = which === 'well' && SUB ? SUB : C, nP = which === 'well' && SUB ? SUB.nPlans : C.nPlans;
        const or = t => `OR ${num(t.est, 2)} [${num(t.lo, 2)}, ${num(t.hi, 2)}], ${pval(t.p)}`;
        h('p', { class: 'cap', html: (which === 'well' ? `Only the plan sizes with plenty of plans (3, 6–7 and 8+ drones: ${nP} of ${C.nPlans} plans; the ${SUB ? SUB.dropped : '—'} plans of 1–2, 4 or 5 drones are left out). ` : `All ${C.nPlans} confirmed tactical plans. `)
          + `Whiskers are 95% CIs; n under each size. Per SD of plan size, on these plans: kept unmodified ${or(M.keepOR)}; consulted ${or(M.consultOR)}; kept once consulted ${or(M.keepGivenConsOR)}; checking time ${sgn(M.netB.est, 2)} s [${sgn(M.netB.lo, 2)}, ${sgn(M.netB.hi, 2)}], ${pval(M.netB.p)}.`
          + (which === 'well' && SUB ? ` 8+ drones vs 3 drones directly: consulted ${or(SUB.consulted3v8)}, kept ${or(SUB.keep3v8)}.` : '')
          + ` Person medians: ${num(C.tacMedian, 1)} s on a tactical plan vs ${num(C.stratMedian, 1)} s on a strategy card.` }, box);
      };
      host.insertBefore(btnBar(host, 'Plan sizes', [['well', 'Well-filled sizes only (3, 6–7, 8+)'], ['all', 'All sizes']], 'well', draw), box);
      draw('well');
    }),

    /* pass 4: the two views the researcher kept (questionnaire item, scenario); session order stays behind a third button */
    'recovery.trustSplits3': safe('trust splits', host => {
      const box = h('div', {}, host), TR = D.trust, BS = TR.byScenario;
      const SCN = { strategic: 'Strategic Heavy sessions', tactical: 'Tactical Heavy sessions' };
      const XL = 'trust gap: tactical minus strategic (points on the 1–7 scale)';
      const views = {
        items: () => { box.innerHTML = '';
          ciRows(box, TR.items.map(i => ({ label: i.label, est: i.diff, lo: i.lo, hi: i.hi, n: i.n, sub: `Strategic ${num(i.s, 2)} · Tactical ${num(i.t, 2)} · ${pval(i.p)}<br>n = people (each person's two sessions averaged)` })), { xLabel: XL });
          h('p', { class: 'cap', text: 'One row per questionnaire item: each person’s tactical answer minus their strategic answer, averaged over their two sessions; 95% CI. Orange = CI clear of zero.' }, box); },
        scenario: () => { box.innerHTML = '';
          ciRows(box, BS.rows.map(g => ({ label: SCN[g.scen], est: g.gapmean, lo: g.gaplo, hi: g.gaphi, n: g.gapn,
            sub: `Strategic ${num(g.s.mean, 2)} [${num(g.s.lo, 2)}, ${num(g.s.hi, 2)}] · Tactical ${num(g.t.mean, 2)} [${num(g.t.lo, 2)}, ${num(g.t.hi, 2)}]<br>both games of this scenario pooled; n = sessions, one per person` })), { lo: -0.5, hi: 2.5, xLabel: XL });
          const P = BS.paired, M = BS.model;
          h('p', { class: 'cap', html: `Every person played one session of each scenario, so the two rows are the same ${P.n} people. Their gap is larger in Strategic Heavy by ${sgn(P.gapDiff.mean, 2)} points [${sgn(P.gapDiff.lo, 2)}, ${sgn(P.gapDiff.hi, 2)}] (paired t ${pval(P.gapP)}, Wilcoxon ${pval(P.gapWil)}), `
            + `mostly because strategic trust is lower there (${sgn(P.sDiff.mean, 2)}, ${pval(P.sP)}) rather than tactical trust higher (${sgn(P.tDiff.mean, 2)}, ${pval(P.tP)}). `
            + `With scenario and session in one model: Strategic Heavy ${sgn(M.sh.est, 2)} [${sgn(M.sh.lo, 2)}, ${sgn(M.sh.hi, 2)}] (${pval(M.sh.p)}), second session ${sgn(M.run2.est, 2)} [${sgn(M.run2.lo, 2)}, ${sgn(M.run2.hi, 2)}] (${pval(M.run2.p)}).` }, box); },
        run: () => { box.innerHTML = '';
          ciRows(box, TR.byRun.map(g => ({ label: 'Session ' + g.run, est: g.gapmean, lo: g.gaplo, hi: g.gaphi, n: g.gapn, sub: `Strategic ${num(g.s, 2)} · Tactical ${num(g.t, 2)}` })), { lo: -0.5, hi: 2.5, xLabel: XL }); },
      };
      host.insertBefore(btnBar(host, 'Split by', [['items', 'Questionnaire item'], ['scenario', 'Scenario played'], ['run', 'Also: first / second session']], 'items', k => views[k]()), box);
      views.items();
    }),

    /* pass 4: is the tactical plan given less attention in Strategic Heavy sessions? */
    'recovery.attention': safe('attention to the tactical plan', host => {
      const A = D.trust && D.trust.attention;
      if (!A) return missing(host, 'attention (rerun recovery.py)');
      const box = h('div', {}, host);
      const draw = which => {
        box.innerHTML = '';
        const rows = A.rows, rowH = 42, padL = 330, padR = 110, padT = 26, padB = 42, H = padT + rows.length * rowH + padB, s = svgRoot(box, W, H);
        const lim = Math.log(3), X = v => padL + (W - padL - padR) * ((Math.log(Math.min(3, Math.max(1 / 3, v))) + lim) / (2 * lim));
        [[1 / 3, '⅓'], [.5, '½'], [1, '1'], [2, '2'], [3, '3']].forEach(([v, lab]) => { el('line', { x1: X(v), x2: X(v), y1: padT - 6, y2: H - padB, stroke: v === 1 ? css('--ink-3') : css('--grid'), 'stroke-width': v === 1 ? 1.5 : 1 }, s);
          T(s, X(v), H - padB + 14, '×' + lab, { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 10.5, 'font-family': mono() }); });
        T(s, X(1), padT - 10, 'same in both scenarios', { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 10.5 });
        T(s, (padL + W - padR) / 2, H - 4, 'Strategic Heavy ÷ Tactical Heavy (time ratio or odds ratio, log scale)', { 'text-anchor': 'middle', fill: css('--ink-2'), 'font-size': 11 });
        rows.forEach((r_, i) => {
          const cy = padT + i * rowH + rowH / 2 - 4, m = r_[which], f = v => r_.kind === 'time' ? num(v, 1) + ' s' : pct(v, 0);
          T(s, padL - 10, cy, r_.label, { 'text-anchor': 'end', 'font-size': 11.5 });
          T(s, padL - 10, cy + 14, `${r_.kind === 'time' ? 'median' : 'rate'}: Strategic Heavy ${f(r_.sh)} · Tactical Heavy ${f(r_.th)}`, { 'text-anchor': 'end', 'font-size': 10, fill: css('--ink-3'), 'font-family': mono() });
          const col = m.p < .05 ? css('--s-tac') : css('--mark-soft');
          el('line', { x1: X(m.lo), x2: X(m.hi), y1: cy + 4, y2: cy + 4, stroke: col, 'stroke-width': 2.5, 'stroke-linecap': 'round' }, s);
          el('circle', { cx: X(m.est), cy: cy + 4, r: 5.5, fill: col, stroke: css('--surface'), 'stroke-width': 2 }, s);
          T(s, W - padR + 8, cy + 8, `×${num(m.est, 2)} ${pval(m.p)}`, { 'font-size': 11, 'font-family': mono() });
          const hit = el('rect', { x: 0, y: cy - rowH / 2 + 4, width: W, height: rowH, fill: 'transparent' }, s);
          hoverable(hit, `<b>${r_.label}</b><br>${r_.kind === 'time' ? 'ratio of typical (geometric-mean) times' : 'odds ratio'}, Strategic Heavy vs Tactical Heavy: ×${num(m.est, 2)} [${num(m.lo, 2)}, ${num(m.hi, 2)}], ${pval(m.p)}<br>${which === 'adj' ? 'same plan size and session order' : 'raw, no adjustment'}<br>n = ${r_.nSH} plans in Strategic Heavy, ${r_.nTH} in Tactical Heavy`);
        });
        const R = A.attnVsTrust;
        h('p', { class: 'cap', html: `${A.nPlans} tactical plans (${A.nSH} in Strategic Heavy sessions, averaging ${num(A.drSH, 1)} drones; ${A.nTH} in Tactical Heavy, ${num(A.drTH, 1)} drones). Times are compared as ratios of typical (geometric-mean) seconds, rates as odds ratios; GEE clustered by person, 95% CIs; orange = CI clear of ×1. `
          + (which === 'adj' ? 'Adjusted = compared at the same plan size (drones × tasks) and session order. ' : 'Raw = no adjustment, and Strategic Heavy plans are much smaller. ')
          + `Does less attention go with more trust? Person by person, the change in size-adjusted planner time (Strategic Heavy minus Tactical Heavy) against the change in tactical trust: ρ = ${num(R.rho, 2)} [${num(R.lo, 2)}, ${num(R.hi, 2)}], ${pval(R.p)}, n = ${R.n}.` }, box);
      };
      host.insertBefore(btnBar(host, 'Compare', [['adj', 'Like-for-like plans (size and session adjusted)'], ['raw', 'Raw']], 'adj', draw), box);
      draw('adj');
    }),

    /* pass 4: checking cost with contiguous plan-size bins, each with enough plans (no toggle) */
    'recovery.checkCost3': safe('checking cost', host => {
      const C = D.checking, B4 = C.bins4;
      if (!B4) return missing(host, 'checking bins (rerun recovery.py)');
      const B = B4.bins, H = 320, padT = 24, padB = 58, gap = 76, xL = 70, pw = (W - xL - gap - 16) / 2, xR = xL + pw + gap;
      const s = svgRoot(h('div', {}, host), W, H), n = B.length, bx = (x0, i) => x0 + pw * (i + .5) / n;
      const yR = v => H - padB - (H - padB - padT) * v, maxS = 12, yS = v => H - padB - (H - padB - padT) * (Math.min(v, maxS) / maxS);
      [0, .25, .5, .75, 1].forEach(v => { el('line', { x1: xL, x2: xL + pw, y1: yR(v), y2: yR(v), stroke: css('--grid') }, s);
        T(s, xL - 6, yR(v) + 4, pct(v, 0), { 'text-anchor': 'end', fill: css('--ink-3'), 'font-size': 10.5, 'font-family': mono() }); });
      for (let v = 0; v <= maxS; v += 3) { el('line', { x1: xR, x2: xR + pw, y1: yS(v), y2: yS(v), stroke: css('--grid') }, s);
        T(s, xR - 6, yS(v) + 4, v + ' s', { 'text-anchor': 'end', fill: css('--ink-3'), 'font-size': 10.5, 'font-family': mono() }); }
      const yt = (x, lab) => { const t = T(s, x, padT + (H - padT - padB) / 2, lab, { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 11 }); t.setAttribute('transform', `rotate(-90 ${x} ${padT + (H - padT - padB) / 2})`); };
      yt(18, '% of tactical plans');
      yt(xR - 44, 'seconds checking after the reveal');
      T(s, xL + pw / 2, 13, 'Suggest pressed / plan kept unmodified', { 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 600 });
      T(s, xR + pw / 2, 13, 'Checking time (plans where Suggest was pressed)', { 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 600 });
      [['consulted', 'cLo', 'cHi', css('--mark-soft'), -7], ['kept', 'kLo', 'kHi', css('--s-tac'), 7]].forEach(([k, l, u, c, dx]) => {
        el('polyline', { points: B.map((b, i) => [bx(xL, i) + dx, yR(b[k])].join(',')).join(' '), fill: 'none', stroke: c, 'stroke-width': 1.5, opacity: .6 }, s);
        B.forEach((b, i) => { const cx = bx(xL, i) + dx;
          el('line', { x1: cx, x2: cx, y1: yR(b[l]), y2: yR(b[u]), stroke: c, 'stroke-width': 1.5 }, s);
          const d = el('circle', { cx, cy: yR(b[k]), r: 5, fill: c, stroke: css('--surface'), 'stroke-width': 1.5 }, s);
          hoverable(d, `<b>${b.label} drones</b><br>${k === 'kept' ? 'kept unmodified' : 'pressed Suggest'} ${pct(b[k], 0)} [${pct(b[l], 0)}, ${pct(b[u], 0)}] 95% CI<br>n = ${b.n} plans, ${b.people} people (${b.nSH} in Strategic Heavy)`); });
      });
      B.forEach((b, i) => { const cx = bx(xR, i);
        el('rect', { x: cx - 10, y: yS(b.netQ3), width: 20, height: Math.max(1, yS(b.netQ1) - yS(b.netQ3)), rx: 4, fill: css('--s-tac'), 'fill-opacity': .25 }, s);
        el('line', { x1: cx - 10, x2: cx + 10, y1: yS(b.netMed), y2: yS(b.netMed), stroke: css('--s-tac'), 'stroke-width': 3 }, s);
        const hit = el('rect', { x: cx - 18, y: padT, width: 36, height: H - padT - padB, fill: 'transparent' }, s);
        hoverable(hit, `<b>${b.label} drones</b><br>median ${fmtS(b.netMed)} (middle half ${fmtS(b.netQ1)}–${fmtS(b.netQ3)})<br>≈ ${fmtS(b.perDrone)} per drone · forced reveal ≈ ${fmtS(b.reveal)} (excluded)<br>n = ${b.nCons} plans with Suggest pressed`); });
      [xL, xR].forEach(x0 => B.forEach((b, i) => {
        T(s, bx(x0, i), H - padB + 15, b.label, { 'text-anchor': 'middle', fill: css('--ink-2'), 'font-size': 10.5, 'font-family': mono() });
        T(s, bx(x0, i), H - padB + 28, `n=${x0 === xL ? b.n : b.nCons}`, { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 9.5, 'font-family': mono() });
      }));
      T(s, xL + pw / 2, H - 6, 'drones in the Tactical Assistant’s plan', { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 11 });
      T(s, xR + pw / 2, H - 6, 'drones in the Tactical Assistant’s plan', { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 11 });
      legend(host, [{ label: 'Pressed Suggest (95% CI)', color: css('--mark-soft') }, { label: 'Kept the plan unmodified (95% CI)', color: css('--s-tac') }, { label: 'Checking time: median (bar) and middle half of plans (box)', color: css('--s-tac') }]);
      tableFor(host, ['Drones', 'Plans', 'People', 'In Strategic Heavy', 'Suggest pressed', 'Kept unmodified', 'Kept | Suggest', 'Median check (s)', 'Per drone (s)'],
        B.map(b => [b.label, b.n, b.people, b.nSH, pct(b.consulted, 0), pct(b.kept, 0), b.keptGivenCons == null ? '—' : pct(b.keptGivenCons, 0), num(b.netMed, 1), num(b.perDrone, 2)]));
      const or = t => `OR ${num(t.est, 2)} [${num(t.lo, 2)}, ${num(t.hi, 2)}], ${pval(t.p)}`;
      h('p', { class: 'cap', html: `All ${C.nPlans} confirmed tactical plans, in six contiguous size bins chosen so every bin has at least ${B4.minPlans} plans (and at least ${B4.minCons} with a checking time). Whiskers are 95% CIs; n under each bin. `
        + `Per SD of plan size (all plans, adjusted for scenario and session): kept unmodified ${or(C.keepOR)}; Suggest pressed ${or(C.consultOR)}; kept once Suggest was pressed ${or(C.keepGivenConsOR)}; checking time ${sgn(C.netB.est, 2)} s [${sgn(C.netB.lo, 2)}, ${sgn(C.netB.hi, 2)}], ${pval(C.netB.p)}. `
        + `10+ drones vs ≤3: Suggest pressed ${or(B4.ends.consulted)}, kept ${or(B4.ends.keep)}. Person medians: ${num(C.tacMedian, 1)} s on a tactical plan vs ${num(C.stratMedian, 1)} s on a strategy card.` }, host);
    }),


    'recovery.prefGap': safe('stated preference', host => {
      const G = D.preference.groups.slice().sort((a, b) => ['tactical', 'strategic', 'conditional', 'both', 'none'].indexOf(a.pref) - ['tactical', 'strategic', 'conditional', 'both', 'none'].indexOf(b.pref));
      const rowH = 44, padL = 170, padR = 120, padT = 10, padB = 36, H = padT + G.length * rowH + padB, s = svgRoot(host, W, H);
      const lo = -3, hi = 4, X = v => padL + (W - padL - padR) * ((v - lo) / (hi - lo));
      for (let v = lo; v <= hi; v++) { el('line', { x1: X(v), x2: X(v), y1: padT, y2: H - padB, stroke: v === 0 ? css('--ink-3') : css('--grid'), 'stroke-width': v === 0 ? 1.5 : 1 }, s);
        T(s, X(v), H - padB + 15, sgn(v, 0), { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 10.5, 'font-family': mono() }); }
      T(s, padL + (W - padL - padR) / 2, H - 4, 'questionnaire trust gap, tactical − strategic (1–7 points)', { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 11 });
      G.forEach((g, i) => {
        const cy = padT + i * rowH + rowH / 2, c = PREF_COL(g.pref);
        T(s, padL - 10, cy + 4, `said ${g.pref} (${g.nSaid})`, { 'text-anchor': 'end', 'font-size': 12.5 });
        g.who.forEach((pid, j) => { const v = g.gaps[j]; if (v == null) return;
          const d = el('circle', { cx: X(Math.max(lo, Math.min(hi, v))), cy: cy + ((j % 3) - 1) * 6, r: 4.5, fill: c, 'fill-opacity': .8, stroke: css('--surface'), 'stroke-width': 1.5 }, s);
          hoverable(d, `<b>${pid}</b> said ${g.pref}<br>questionnaire gap ${sgn(v, 2)}`); });
        if (g.mean != null) {
          el('line', { x1: X(g.mean), x2: X(g.mean), y1: cy - 14, y2: cy + 14, stroke: css('--ink-2'), 'stroke-width': 2.5 }, s);
          T(s, W - padR + 10, cy + 4, `mean ${sgn(g.mean, 2)}`, { 'font-size': 11.5, 'font-family': mono() });
        }
      });
      const P = D.preference;
      h('p', { class: 'cap', text: `Stated preference from the debrief/interview coding (round 2; one coder, not yet second-coded). Of those naming one assistant, ${P.signK} of ${P.signN} named the tactical one (sign test ${pval(P.signP)}). Their questionnaire answer points the same way for ${P.agree} of ${P.agreeOf}. Black tick = group mean.` }, host);
    }),
    'recovery.checkCost': safe('checking cost', host => {
      const B = D.checking.bins, H = 300, padT = 18, padB = 52, gap = 50, pw = (W - 60 - gap - 20) / 2, s = svgRoot(host, W, H);
      const xL = 60, xR = 60 + pw + gap, n = B.length, bx = (x0, i) => x0 + pw * (i + .5) / n;
      const yR = v => H - padB - (H - padB - padT) * v, maxS = Math.max(10, ...B.map(b => b.netQ3 || 0)), yS = v => H - padB - (H - padB - padT) * (v / maxS);
      [0, .25, .5, .75, 1].forEach(v => { el('line', { x1: xL, x2: xL + pw, y1: yR(v), y2: yR(v), stroke: css('--grid') }, s);
        T(s, xL - 6, yR(v) + 4, pct(v, 0), { 'text-anchor': 'end', fill: css('--ink-3'), 'font-size': 10.5, 'font-family': mono() }); });
      for (let v = 0; v <= maxS; v += 2) { el('line', { x1: xR, x2: xR + pw, y1: yS(v), y2: yS(v), stroke: css('--grid') }, s);
        T(s, xR - 6, yS(v) + 4, v + ' s', { 'text-anchor': 'end', fill: css('--ink-3'), 'font-size': 10.5, 'font-family': mono() }); }
      T(s, xL + pw / 2, 12, 'Share of plans', { 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 600 });
      T(s, xR + pw / 2, 12, 'Checking time after the reveal (consulted plans)', { 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 600 });
      [['consulted', 'cLo', 'cHi', css('--mark-soft'), -6], ['kept', 'kLo', 'kHi', css('--s-tac'), 6]].forEach(([k, l, u, c, dx]) => {
        const pts = B.map((b, i) => [bx(xL, i) + dx, yR(b[k])]);
        el('polyline', { points: pts.map(p => p.join(',')).join(' '), fill: 'none', stroke: c, 'stroke-width': 2 }, s);
        B.forEach((b, i) => { const cx = bx(xL, i) + dx;
          el('line', { x1: cx, x2: cx, y1: yR(b[l]), y2: yR(b[u]), stroke: c, 'stroke-width': 1.5 }, s);
          const d = el('circle', { cx, cy: yR(b[k]), r: 4.5, fill: c, stroke: css('--surface'), 'stroke-width': 1.5 }, s);
          hoverable(d, `<b>${b.label} drones</b><br>${k === 'kept' ? 'kept unmodified' : 'pressed Suggest'} ${pct(b[k], 0)} [${pct(b[l], 0)}, ${pct(b[u], 0)}]<br>n = ${b.n} plans, ${b.people} people`); });
      });
      B.forEach((b, i) => { const cx = bx(xR, i);
        el('rect', { x: cx - 9, y: yS(b.netQ3), width: 18, height: Math.max(1, yS(b.netQ1) - yS(b.netQ3)), rx: 4, fill: css('--s-tac'), 'fill-opacity': .25 }, s);
        el('line', { x1: cx - 9, x2: cx + 9, y1: yS(b.netMed), y2: yS(b.netMed), stroke: css('--s-tac'), 'stroke-width': 3 }, s);
        const hit = el('rect', { x: cx - 16, y: padT, width: 32, height: H - padT - padB, fill: 'transparent' }, s);
        hoverable(hit, `<b>${b.label} drones</b><br>median ${fmtS(b.netMed)} (IQR ${fmtS(b.netQ1)}–${fmtS(b.netQ3)})<br>≈ ${fmtS(b.perDrone)} per drone · forced reveal ≈ ${fmtS(b.reveal)} (excluded)<br>n = ${b.nCons} consulted plans`); });
      [[xL], [xR]].forEach(([x0]) => B.forEach((b, i) => T(s, bx(x0, i), H - padB + 15, b.label, { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 10.5, 'font-family': mono() })));
      T(s, xL + pw / 2, H - 14, 'drones in the plan', { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 11 });
      T(s, xR + pw / 2, H - 14, 'drones in the plan', { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 11 });
      legend(host, [{ label: 'Pressed Suggest (consulted)', color: css('--mark-soft') }, { label: 'Kept the plan unmodified', color: css('--s-tac') }, { label: 'Checking time: median (bar) and middle half (box)', color: css('--s-tac') }]);
      const C = D.checking;
      tableFor(host, ['Drones', 'Plans', 'Consulted', 'Kept unmodified', 'Kept | consulted', 'Median check (s)', 'Per drone (s)'],
        B.map(b => [b.label, b.n, pct(b.consulted, 0), pct(b.kept, 0), b.keptGivenCons == null ? '—' : pct(b.keptGivenCons, 0), num(b.netMed, 1), num(b.perDrone, 2)]));
      h('p', { class: 'cap', text: `${C.nPlans} confirmed tactical plans, ${C.nPeople} people. Bars are 95% CIs. Once Deploy unlocks, people spend a median ${num(C.tacMedian, 1)} s on a tactical plan against ${num(C.stratMedian, 1)} s on a strategy card (person medians).` }, host);
    }),
    'recovery.statedRevealed': safe('stated vs revealed', host => {
      const box = h('div', {}, host), SR = D.statedRevealed;
      const draw = k => {
        const P = SR.people.filter(p => p.tgap != null && p[k] != null), R = k === 'ugapA' ? SR.rhoA : SR.rhoC;
        const q = { tt: 0, ss: 0, ts: 0, st: 0 }; P.forEach(p => { if (p.tgap > 0 && p[k] > 0) q.tt++; else if (p.tgap < 0 && p[k] < 0) q.ss++; else if (p.tgap > 0 && p[k] < 0) q.ts++; else if (p.tgap < 0 && p[k] > 0) q.st++; });
        scatter(box, P.map(p => ({ x: p.tgap, y: p[k], color: PREF_COL(p.pref), r: 6.5,
          tip: `<b>${p.pid}</b>${p.pref ? ' · said ' + p.pref : ''}<br>Trust: strategic ${num(p.ts, 2)}, tactical ${num(p.tt, 2)} (gap ${sgn(p.tgap, 2)})<br>Took a card ${pct(p.took, 0)} · consulted plan ${pct(p.consult, 0)} · kept it ${pct(p.accept, 0)}` })),
          { xr: [-3, 4], yr: [-1, 1], xt: [-3, -2, -1, 0, 1, 2, 3, 4], yt: [-1, -.5, 0, .5, 1], zero: true, xf: v => sgn(v, 0), yf: v => sgn(100 * v, 0) + ' pt',
            xLabel: 'STATED: trust gap, tactical − strategic (questionnaire, 1–7)',
            yLabel: k === 'ugapA' ? 'REVEALED: % plans kept − % cards taken (pp)' : 'REVEALED: % plans with Suggest − % cards taken (pp)',
            notes: [{ x: 3.9, y: .92, anchor: 'end', text: `trust & use favour tactical: ${q.tt}` }, { x: -2.9, y: -.92, anchor: 'start', text: `both favour strategic: ${q.ss}` },
                    { x: 3.9, y: -.92, anchor: 'end', text: `trust tactical, use strategic: ${q.ts}` }, { x: -2.9, y: .92, anchor: 'start', text: `trust strategic, use tactical: ${q.st}` }] });
        h('p', { class: 'cap', text: `Each dot is one operator (both sessions pooled). Spearman ρ = ${num(R.rho, 2)} [${num(R.lo, 2)}, ${num(R.hi, 2)}], ${pval(R.p)}, n = ${R.n}. Colour = what they said in the debrief.` }, box);
      };
      host.insertBefore(btnBar(host, 'Use measure', [['ugapA', 'Kept the plan unmodified'], ['ugapC', 'Pressed Suggest at all']], 'ugapA', draw), box);
      draw('ugapA');
      legend(host, [{ label: 'said tactical', color: css('--s-tac') }, { label: 'said strategic', color: css('--s-strat') }, { label: 'conditional / both / none / not coded', color: css('--mark-soft') }]);
    }),
    'recovery.trustLead': safe('trust vs use, levels and changes', host => {
      const SR = D.statedRevealed, rows = [
        ['Between people: strategic trust ~ took a card', SR.levels.strat],
        ['Between people: tactical trust ~ kept the plan', SR.levels.tacA],
        ['Between people: trust gap ~ use gap', SR.rhoA],
        ['Within person: change in strategic trust ~ change in card use', SR.change.strat],
        ['Within person: change in tactical trust ~ change in keeping', SR.change.tacA],
        ['Leads? session-1 strategic trust ~ later change in card use', SR.lead.strat],
        ['Leads? session-1 tactical trust ~ later change in keeping', SR.lead.tacA]];
      const rowH = 32, padL = 380, padR = 100, padT = 10, padB = 34, H = padT + rows.length * rowH + padB, s = svgRoot(host, W, H);
      const X = v => padL + (W - padL - padR) * ((v + 1) / 2);
      [-1, -.5, 0, .5, 1].forEach(v => { el('line', { x1: X(v), x2: X(v), y1: padT, y2: H - padB, stroke: v === 0 ? css('--ink-3') : css('--grid'), 'stroke-width': v === 0 ? 1.5 : 1 }, s);
        T(s, X(v), H - padB + 15, num(v, 1), { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 10.5, 'font-family': mono() }); });
      T(s, padL + (W - padL - padR) / 2, H - 4, 'Spearman ρ with 95% bootstrap CI', { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 11 });
      rows.forEach(([lab, R], i) => {
        const cy = padT + i * rowH + rowH / 2;
        T(s, padL - 10, cy + 4, lab, { 'text-anchor': 'end', 'font-size': 12 });
        if (!R || R.rho == null) return;
        const col = R.p < .05 ? css('--mark') : css('--mark-soft');
        if (R.lo != null) el('line', { x1: X(R.lo), x2: X(R.hi), y1: cy, y2: cy, stroke: col, 'stroke-width': 2, 'stroke-linecap': 'round' }, s);
        el('circle', { cx: X(R.rho), cy, r: 5.5, fill: col, stroke: css('--surface'), 'stroke-width': 2 }, s);
        T(s, W - padR + 8, cy + 4, `${num(R.rho, 2)} ${pval(R.p)}`, { 'font-size': 11, 'font-family': mono() });
        const hit = el('rect', { x: 0, y: cy - rowH / 2, width: W, height: rowH, fill: 'transparent' }, s);
        hoverable(hit, `<b>${lab}</b><br>ρ = ${num(R.rho, 2)} [${num(R.lo, 2)}, ${num(R.hi, 2)}] · ${pval(R.p)} · n = ${R.n} people`);
      });
    }),

    /* ───────────── f-recovery ───────────── */
    'recovery.abandonByType': safe('abandonment by refusal type', host => {
      const C = D.refusal.byClass, col = { wrong: css('--bad'), correct: css('--mark-soft'), solved: css('--s-tac'), hand: css('--s-tac'), none: css('--mark-soft') };
      rateCI(host, C.map(c => ({ label: c.label, value: c.rate, lo: c.lo, hi: c.hi, n: c.n, color: col[c.cls],
        sub: `${c.abandoned} of ${c.n} resolved episodes abandoned · ${c.people} people · ${c.fixable} fixable with drones on the mission${c.unresolved ? ` · ${c.unresolved} more left open at the buzzer` : ''}` })),
        { padL: 250, xLabel: 'share of recovery episodes abandoned (95% CI)' });
      const F = D.refusal.fisher;
      h('p', { class: 'cap', text: `One row per recovery episode (a drone failure that needed the operator), grouped by what Suggest said. Wrong refusal vs every other attempted fixable failure: ${F.table[0][0]} of ${F.table[0][0] + F.table[0][1]} vs ${F.table[1][0]} of ${F.table[1][0] + F.table[1][1]} abandoned (odds ×${num(F.OR, 1)}, Fisher ${pval(F.p)}).` }, host);
    }),
    'recovery.refusalTimeline': safe('refusal timeline', host => {
      const order = [['wrong', 'abandoned', 'Wrong refusal → abandoned'], ['wrong', 'recovered', 'Wrong refusal → fixed'], ['correct', 'abandoned', 'Correct refusal → abandoned']];
      const E = D.refusal.episodes, rows = [];
      order.forEach(([c, o, lab]) => { const g = E.filter(e => e.cls === c && e.outcome === o).sort((a, b) => a.refusalToClose - b.refusalToClose);
        if (g.length) { rows.push({ head: `${lab} (${g.length})` }); g.forEach(e => rows.push(e)); } });
      const rowH = 15, padL = 120, padR = 20, padT = 8, padB = 40, H = padT + rows.length * rowH + padB, s = svgRoot(host, W, H);
      const lo = -20, hi = 45, X = v => padL + (W - padL - padR) * ((Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo));
      [-20, -10, 0, 10, 20, 30, 40].forEach(v => { el('line', { x1: X(v), x2: X(v), y1: padT, y2: H - padB, stroke: v === 0 ? css('--ink-3') : css('--grid'), 'stroke-width': v === 0 ? 1.5 : 1 }, s);
        T(s, X(v), H - padB + 14, (v > 0 ? '+' : '') + v + ' s', { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 10.5, 'font-family': mono() }); });
      T(s, X(0), H - 6, 'seconds from the first “No workable plan” (0) — before it: the failure and any hand edits; after it: everything until the mission was closed', { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 10.5 });
      rows.forEach((e, i) => {
        const cy = padT + i * rowH + rowH / 2;
        if (e.head) { T(s, 6, cy + 4, e.head, { 'font-size': 11.5, 'font-weight': 600 }); return; }
        T(s, padL - 8, cy + 4, `${e.pid} s${e.run} ${e.mission}`, { 'text-anchor': 'end', 'font-size': 10.5, fill: e.verified ? css('--bad') : css('--ink-2'), 'font-family': mono() });
        el('line', { x1: X(-e.failToRefusal), x2: X(0), y1: cy, y2: cy, stroke: css('--grid'), 'stroke-width': 2 }, s);
        el('line', { x1: X(0), x2: X(e.refusalToClose), y1: cy, y2: cy, stroke: css('--ink-3'), 'stroke-width': 2 }, s);
        el('circle', { cx: X(-e.failToRefusal), cy, r: 3, fill: css('--ink-3') }, s);
        (e.dragsPre || []).concat(e.drags || []).forEach(t => el('line', { x1: X(t), x2: X(t), y1: cy - 5, y2: cy + 5, stroke: css('--s-tac'), 'stroke-width': 2 }, s));
        (e.presses || []).forEach(p => { const fail = p.res === 'failed' || p.res === 'partial';
          el('circle', { cx: X(p.t), cy, r: 4, fill: fail ? css('--surface') : css('--s-tac'), stroke: fail ? css('--bad') : css('--s-tac'), 'stroke-width': 2 }, s); });
        const end = X(e.refusalToClose), ab = e.outcome === 'abandoned';
        el('rect', { x: end - 4.5, y: cy - 4.5, width: 9, height: 9, rx: ab ? 1 : 4.5, fill: ab ? css('--bad') : css('--good'), stroke: css('--surface'), 'stroke-width': 1.5 }, s);
        const hit = el('rect', { x: 0, y: cy - rowH / 2, width: W, height: rowH, fill: 'transparent' }, s);
        hoverable(hit, `<b>${e.pid} session ${e.run}, ${e.mission}</b>${e.verified ? ' (verified on video)' : ''}<br>failure → first refusal ${fmtS(e.failToRefusal)}<br>first refusal → ${e.outcome} ${fmtS(e.refusalToClose)} (last refusal → close ${fmtS(e.lastToClose)})<br>`
          + `Suggest presses refused: ${e.nRefusals} · drags before / after: ${e.dragsBefore} / ${e.dragsAfter} · actions on other missions meanwhile: ${e.othersAfter}<br>${num(e.timeLeft, 0)} s left in the session`);
      });
      legend(host, [{ label: '“No workable plan” (Suggest press)', color: css('--bad') }, { label: 'Drone dragged in the planner', color: css('--s-tac') }, { label: 'Abandoned (square)', color: css('--bad') }, { label: 'Fixed and deployed', color: css('--good') }, { label: 'Failure (grey dot, left)', color: css('--ink-3') }]);
      h('p', { class: 'cap', text: 'Times beyond +45 s or before −20 s are drawn at the edge (hover for the real value). Red label: P19 s1 M003, checked frame by frame on the recording.' }, host);
    }),
    'recovery.secondsToAbandon': safe('seconds to abandon', host => {
      const kinds = [['wrong', 'after a WRONG refusal', css('--bad'), 'last refusal'], ['correct', 'after a correct refusal', css('--mark-soft'), 'last refusal'],
        ['own', 'after own hand edits (no refusal)', css('--s-tac'), 'last own action'], ['untried', 'nothing tried at all', css('--mark-soft'), 'the failure']];
      const P = D.refusal.strip, rowH = 46, padL = 230, padR = 80, padT = 10, padB = 38, H = padT + kinds.length * rowH + padB, s = svgRoot(host, W, H);
      const mx = 120, X = v => padL + (W - padL - padR) * Math.sqrt(Math.min(v, mx) / mx);
      [0, 5, 10, 20, 40, 80, 120].forEach(v => { el('line', { x1: X(v), x2: X(v), y1: padT, y2: H - padB, stroke: css('--grid') }, s);
        T(s, X(v), H - padB + 14, v + ' s', { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 10.5, 'font-family': mono() }); });
      T(s, padL + (W - padL - padR) / 2, H - 4, 'seconds from the trigger to abandoning (square-root scale; ≥120 s drawn at the edge)', { 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 11 });
      kinds.forEach(([k, lab, c, trig], i) => {
        const cy = padT + i * rowH + rowH / 2, g = P.filter(p => p.kind === k).sort((a, b) => a.s - b.s);
        T(s, padL - 10, cy, lab, { 'text-anchor': 'end', 'font-size': 12 });
        T(s, padL - 10, cy + 14, `from ${trig} · n=${g.length}`, { 'text-anchor': 'end', 'font-size': 10.5, fill: css('--ink-3') });
        g.forEach((p, j) => { const d = el('circle', { cx: X(p.s), cy: cy + ((j % 3) - 1) * 7, r: 4.5, fill: c, 'fill-opacity': .85, stroke: css('--surface'), 'stroke-width': 1.5 }, s);
          hoverable(d, `<b>${p.label}</b><br>${fmtS(p.s)} from ${trig} to abandon`); });
        if (g.length) { const med = g[Math.floor((g.length - 1) / 2)].s / 2 + g[Math.ceil((g.length - 1) / 2)].s / 2;
          el('line', { x1: X(med), x2: X(med), y1: cy - 15, y2: cy + 15, stroke: css('--ink-2'), 'stroke-width': 2.5 }, s);
          T(s, W - padR + 8, cy + 4, 'median ' + num(med, 1) + ' s', { 'font-size': 11, 'font-family': mono() }); }
      });
    }),
    'recovery.afterRefusal': safe('attempts after a refusal', host => {
      const A = D.afterRefusal, rows = [];
      [['any', 'first refusal of any kind'], ['wrong', 'first WRONG refusal']].forEach(([k, lab]) => { const x = A[k]; if (!x) return;
        const wb = wl(x.before, x.nBefore), wa = wl(x.after, x.nAfter);
        rows.push({ label: `before ${lab}`, value: x.before, lo: wb[0], hi: wb[1], n: x.nBefore, color: css('--mark-soft'), sub: `${x.people} people exposed` });
        rows.push({ label: `after ${lab}`, value: x.after, lo: wa[0], hi: wa[1], n: x.nAfter, color: css('--s-tac'),
          sub: `odds ratio after vs before, adjusted for session: ×${num((x.model || {}).est, 2)} [${num((x.model || {}).lo, 2)}, ${num((x.model || {}).hi, 2)}], ${pval((x.model || {}).p)}` }); });
      rateCI(host, rows, { padL: 250, xLabel: 'share of LATER fixable failures where a fix was attempted (95% CI)' });
      h('p', { class: 'cap', text: `Only people who ever got a refusal; their own fixable failures before vs after it (the refusal episode itself left out). Raw rates go up; once the second session's general rise is taken out the odds point down (×${num((A.any.model || {}).est, 2)}), and neither is distinguishable from no change. Only ${A.any.peopleBoth} people have failures on both sides.` }, host);
      function wl(p, n) { if (!n || p == null) return [null, null]; const z = 1.96, d = 1 + z * z / n, c = (p + z * z / (2 * n)) / d, w = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d; return [c - w, c + w]; }
    }),
    'recovery.relianceAttempt': safe('reliance vs attempting', host => {
      const box = h('div', {}, host), R = D.reliance.rows;
      const draw = k => {
        const row = R.find(x => String(x.minLeft) === k) || R[0], never = new Set(row.never);
        const P = row.people.filter(p => p.pc1 != null), xs = P.map(p => p.pc1), xmin = Math.floor(Math.min(...xs)), xmax = Math.ceil(Math.max(...xs));
        const xt = []; for (let v = xmin; v <= xmax; v++) xt.push(v);
        scatter(box, P.map(p => ({ x: p.pc1, y: p.rate, r: 3.5 + Math.sqrt(p.n) * 1.6, color: never.has(p.pid) ? css('--bad') : css('--mark'),
          tip: `<b>${p.pid}</b><br>attempted ${p.k} of ${p.n} fixable failures (${pct(p.rate, 0)})<br>reliance score ${num(p.pc1, 2)}` })),
          { xr: [xmin, xmax], yr: [-0.05, 1.05], xt, yt: [0, .25, .5, .75, 1], yf: v => pct(v, 0), xf: v => num(v, 0),
            xLabel: 'reliance axis (PC1 of ten usage habits; higher = leans on both assistants more)', yLabel: 'share of own fixable failures attempted' });
        const a = row.all, b = row.noNever, c = row.noRec;
        h('p', { class: 'cap', text: `${row.nPeople} people, ${row.nEps} fixable failures${row.minLeft ? ` with ≥ ${row.minLeft} s left` : ''}. Dot size = number of failures. Red = never attempted one (${row.never.join(', ')}). ρ = ${num(a.rho, 2)} [${num(a.lo, 2)}, ${num(a.hi, 2)}] ${pval(a.p)}; axis without its recovery-Suggest item ρ = ${num(c.rho, 2)}; without the never-attempters ρ = ${num(b.rho, 2)} [${num(b.lo, 2)}, ${num(b.hi, 2)}] ${pval(b.p)}. ${row.always} of ${row.nPeople} attempted every one.` }, box);
      };
      host.insertBefore(btnBar(host, 'Failures', [['31', 'With ≥ 31 s left (main)'], ['0', 'All, including the last 30 s']], '31', draw), box);
      draw('31');
    }),
    'recovery.timeLeft': safe('time left', host => {
      const T_ = D.timeLeft;
      rateCI(host, T_.bins.map(b => ({ label: `${b.label} left`, value: b.rate, lo: b.lo, hi: b.hi, n: b.n, color: css('--mark'),
        sub: `${b.k} of ${b.n} fixable failures attempted${b.unresolved ? ` · ${b.unresolved} still open at the buzzer` : ''}` })), { padL: 150, xLabel: 'share of fixable failures where a fix was attempted (95% CI)' });
      h('p', { class: 'cap', text: `Time left in the 8-minute session when the drone failed. Operators take a median ${fmtS(T_.firstMoveMed)} to make a first move (IQR ${fmtS(T_.firstMoveQ1)}–${fmtS(T_.firstMoveQ3)}); ${T_.leftOpenLe12} of the ${T_.leftOpen} failures still open at the buzzer began with 12 s or less on the clock.` }, host);
    }),
  });
})();
