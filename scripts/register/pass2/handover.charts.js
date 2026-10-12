/* Pass 2 · AREA handover — "When operators hand over". Data: DATA.pass2.handover, written by
   scripts/register/pass2/handover.py. Every chart is defensive: missing data draws a short note. */
(() => {
  const D = (DATA.pass2 || {}).handover;
  const W = 700;
  const C = t => css(t);
  const safe = fn => host => {
    try {
      if (!D) throw new Error('handover.json not embedded');
      fn(host);
    } catch (e) {
      host.innerHTML = '';
      h('p', { class: 'note', text: 'Chart unavailable: ' + e.message }, host);
    }
  };
  const mono = () => C('--mono');
  const txt = (s, a, t) => { const n = el('text', Object.assign({ fill: C('--ink-3'), 'font-size': 11 }, a), s); n.textContent = t; return n; };
  const p0 = v => v == null ? '—' : pct(v, 0);
  const ciTxt = (x, f) => `${f(x.v)} [${f(x.lo)}, ${f(x.hi)}]`;

  /* Points with 95% interval bars, joined by a thin line per series. x is numeric (o.xmin/xmax) or
     categorical (o.cats, series dodged). pts: {x, v, lo, hi, tip}. */
  function ciChart(host, series, o = {}) {
    const H = o.height || 290, padL = 58, padR = o.padR || 150, padT = 18, padB = 50;
    const s = svgRoot(host, W, H);
    const fmt = o.fmt || (v => pct(v, 0));
    const ymin = o.ymin != null ? o.ymin : 0, ymax = o.ymax != null ? o.ymax : 1;
    const y = v => H - padB - (H - padB - padT) * ((v - ymin) / (ymax - ymin));
    let xp, ticks;
    if (o.cats) {
      const bw = (W - padL - padR) / o.cats.length;
      xp = c => padL + bw * (o.cats.indexOf(c) + 0.5);
      ticks = o.cats.map(c => [c, xp(c)]);
    } else {
      xp = v => padL + (W - padL - padR) * ((v - o.xmin) / (o.xmax - o.xmin));
      ticks = (o.xticks || []).map(v => [String(v), xp(v)]);
    }
    (o.yticks || [0, .25, .5, .75, 1]).forEach(v => {
      el('line', { x1: padL, x2: W - padR, y1: y(v), y2: y(v), stroke: C('--grid') }, s);
      txt(s, { x: padL - 8, y: y(v) + 4, 'text-anchor': 'end', 'font-family': mono() }, fmt(v));
    });
    if (o.ref != null) el('line', { x1: padL, x2: W - padR, y1: y(o.ref), y2: y(o.ref), stroke: C('--ink-3'), 'stroke-width': 1.2, 'stroke-dasharray': '4 3' }, s);
    ticks.forEach(([lab, x]) => txt(s, { x, y: H - padB + 17, 'text-anchor': 'middle', 'font-family': mono(), 'font-size': 10.5 }, lab));
    txt(s, { x: (padL + W - padR) / 2, y: H - 8, 'text-anchor': 'middle' }, o.xLabel || '');
    const yl = txt(s, { x: 14, y: (padT + H - padB) / 2, 'text-anchor': 'middle', transform: `rotate(-90 14 ${(padT + H - padB) / 2})` }, o.yLabel || '');
    const labels = [];
    series.forEach((se, si) => {
      const off = o.cats ? (si - (series.length - 1) / 2) * (o.dodge || 12) : 0;
      const pts = (se.pts || []).filter(p => p && p.v != null && (o.cats ? o.cats.includes(p.x) : true));
      if (!pts.length) return;
      const X = p => xp(p.x) + off;
      if (se.line !== false && pts.length > 1) {
        const pa = { d: pts.map((p, i) => (i ? 'L' : 'M') + X(p) + ' ' + y(p.v)).join(' '), fill: 'none', stroke: se.color,
                     'stroke-width': 2, 'stroke-linejoin': 'round', opacity: se.faint ? .55 : .9 };
        if (se.dash) pa['stroke-dasharray'] = '5 4';
        el('path', pa, s);
      }
      pts.forEach(p => {
        if (p.lo != null && p.hi != null)
          el('line', { x1: X(p), x2: X(p), y1: y(Math.max(ymin, p.lo)), y2: y(Math.min(ymax, p.hi)), stroke: se.color, 'stroke-width': 2, 'stroke-linecap': 'round', opacity: .55 }, s);
        el('circle', { cx: X(p), cy: y(p.v), r: se.small ? 3 : 4.5, fill: se.hollow ? C('--surface') : se.color, stroke: se.hollow ? se.color : C('--surface'), 'stroke-width': se.hollow ? 2 : 1.5 }, s);
        const hit = el('circle', { cx: X(p), cy: y(p.v), r: 12, fill: 'transparent' }, s);
        hoverable(hit, `<b>${se.label}</b> · ${p.lab != null ? p.lab : p.x}<br>${ciTxt(p, fmt)}${p.tip ? '<br>' + p.tip : ''}`);
      });
      if (o.direct !== false) {
        const last = pts[pts.length - 1];
        labels.push({ y: y(last.v), x: X(last) + 10, t: se.label, c: se.color });
      }
    });
    // direct labels, nudged apart
    labels.sort((a, b) => a.y - b.y);
    for (let i = 1; i < labels.length; i++) if (labels[i].y - labels[i - 1].y < 14) labels[i].y = labels[i - 1].y + 14;
    labels.forEach(l => { const n = el('text', { x: Math.max(l.x, W - padR + 6), y: l.y + 4, fill: C('--ink-2'), 'font-size': 11.5, 'font-weight': 600 }, s); n.textContent = l.t;
      el('circle', { cx: Math.max(l.x, W - padR + 6) - 6, cy: l.y, r: 3, fill: l.c }, s); n.setAttribute('x', Math.max(l.x, W - padR + 6) + 2); });
    if (series.length >= 2) legend(host, series.map(se => ({ label: se.label, color: se.color })));
    return s;
  }

  /* Estimates with 95% intervals, one row each. log: odds-ratio axis with a line at 1; otherwise a line at 0. */
  function ciStrip(host, rows, o = {}) {
    rows = rows.filter(r => r && r.est != null && r.lo != null && r.hi != null);
    if (!rows.length) { h('p', { class: 'note', text: 'No estimates.' }, host); return; }
    const rowH = 28, padL = o.padL || 300, padR = 92, padT = 22;
    const H = padT + rows.length * rowH + 40;
    const s = svgRoot(host, W, H);
    const log = o.log !== false, ref = log ? 1 : 0;
    const tf = v => log ? Math.log(v) : v;
    let lo = Math.min(tf(ref), ...rows.map(r => tf(r.lo))), hi = Math.max(tf(ref), ...rows.map(r => tf(r.hi)));
    const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
    const x = v => padL + (W - padL - padR) * ((tf(v) - lo) / (hi - lo));
    const base = padT + rows.length * rowH + 4;
    const tks = o.ticks || (log ? [0.25, 0.5, 1, 2, 4, 8].filter(v => tf(v) >= lo && tf(v) <= hi) : null);
    (tks || [lo, (lo + hi) / 2, hi]).forEach(v => {
      el('line', { x1: x(v), x2: x(v), y1: padT - 6, y2: base, stroke: C('--grid') }, s);
      txt(s, { x: x(v), y: base + 15, 'text-anchor': 'middle', 'font-family': mono(), 'font-size': 10.5 }, log ? '×' + v : (o.fmt ? o.fmt(v) : num(v, 2)));
    });
    el('line', { x1: x(ref), x2: x(ref), y1: padT - 10, y2: base, stroke: C('--ink-3'), 'stroke-width': 1.5 }, s);
    txt(s, { x: x(ref), y: padT - 12, 'text-anchor': 'middle', 'font-size': 10.5, 'font-family': mono() }, 'no effect');
    txt(s, { x: (padL + W - padR) / 2, y: H - 6, 'text-anchor': 'middle' }, o.xLabel || (log ? 'odds ratio (95% interval)' : 'estimate (95% interval)'));
    rows.forEach((r, i) => {
      const yy = padT + i * rowH + rowH / 2;
      if (r.head) { el('line', { x1: 8, x2: W - 8, y1: yy - rowH / 2, y2: yy - rowH / 2, stroke: C('--line') }, s); }
      const lt = el('text', { x: padL - 12, y: yy + 4, 'text-anchor': 'end', fill: C('--ink-2'), 'font-size': 12, 'font-weight': r.main ? 600 : 400 }, s);
      lt.textContent = r.label;
      const col = r.color || (r.p < 0.05 ? C('--mark') : C('--mark-soft'));
      el('line', { x1: x(r.lo), x2: x(r.hi), y1: yy, y2: yy, stroke: col, 'stroke-width': 2, 'stroke-linecap': 'round' }, s);
      el('circle', { cx: x(r.est), cy: yy, r: r.main ? 5.5 : 4.5, fill: col, stroke: C('--surface'), 'stroke-width': 2 }, s);
      const pt = el('text', { x: W - padR + 10, y: yy + 4, fill: pColour(r.p), 'font-size': 11, 'font-family': mono() }, s);
      pt.textContent = pval(r.p);
      const hit = el('rect', { x: 0, y: yy - rowH / 2, width: W, height: rowH, fill: 'transparent' }, s);
      const f = log ? (v => '×' + num(v, 2)) : (o.fmt || (v => num(v, 2)));
      hoverable(hit, `<b>${r.label}</b><br>${f(r.est)} [${f(r.lo)}, ${f(r.hi)}] · ${pval(r.p)}`
        + (r.n ? `<br>n = ${r.n} decisions, ${r.k} people` : '') + (r.note ? '<br><i>' + r.note + '</i>' : ''));
    });
    return s;
  }

  /* One row per measure: every person as a faint dot, a named group's members as larger coloured dots,
     with the two group means marked and the permutation p on the right. */
  function groupStrip(host, metrics, people, group, o = {}) {
    const rowH = 38, padL = 250, padR = 150, padT = 10;
    const H = padT + metrics.length * rowH + 20;
    const s = svgRoot(host, W, H);
    const gcol = o.color || C('--mark'), ocol = C('--mark-soft');
    metrics.forEach((m, i) => {
      const yy = padT + i * rowH + rowH / 2;
      const vals = Object.entries(people).map(([pid, v]) => [pid, v[m.key]]).filter(([, v]) => v != null && isFinite(v));
      if (!vals.length) return;
      let lo = Math.min(...vals.map(v => v[1])), hi = Math.max(...vals.map(v => v[1]));
      if (hi === lo) { hi += 1; lo -= 1; }
      const x = v => padL + (W - padL - padR) * ((v - lo) / (hi - lo));
      el('line', { x1: padL, x2: W - padR, y1: yy, y2: yy, stroke: C('--grid') }, s);
      const lt = el('text', { x: padL - 12, y: yy + 4, 'text-anchor': 'end', fill: C('--ink-2'), 'font-size': 12 }, s);
      lt.textContent = m.label;
      txt(s, { x: padL, y: yy + 15, 'font-size': 9.5, 'font-family': mono() }, m.fmt(lo));
      txt(s, { x: W - padR, y: yy + 15, 'font-size': 9.5, 'font-family': mono(), 'text-anchor': 'end' }, m.fmt(hi));
      vals.forEach(([pid, v], j) => {
        const inG = group.includes(pid);
        const jit = ((j * 37) % 9 - 4) * 0.9;
        const c = el('circle', { cx: x(v), cy: yy + (inG ? 0 : jit), r: inG ? 5 : 3, fill: inG ? gcol : ocol, opacity: inG ? 1 : .7,
                                 stroke: inG ? C('--surface') : 'none', 'stroke-width': 1.5 }, s);
        hoverable(c, `<b>${pid}</b>${inG ? ' (' + (o.groupLabel || 'group') + ')' : ''}<br>${m.label}: ${m.fmt(v)}`);
      });
      [[m.inMean, gcol, 'group mean'], [m.restMean, C('--ink-3'), 'everyone else']].forEach(([v, c, lab]) => {
        if (v == null) return;
        el('line', { x1: x(v), x2: x(v), y1: yy - 11, y2: yy + 11, stroke: c, 'stroke-width': 3, 'stroke-linecap': 'round' }, s);
      });
      const pt = el('text', { x: W - padR + 12, y: yy + 4, fill: C('--ink-2'), 'font-size': 11, 'font-family': mono() }, s);
      pt.textContent = `${m.fmt(m.inMean)} vs ${m.fmt(m.restMean)}`;
      const pp = el('text', { x: W - padR + 12, y: yy + 16, fill: pColour(m.p), 'font-size': 10.5, 'font-family': mono() }, s);
      pp.textContent = pval(m.p);
    });
    legend(host, [{ label: (o.groupLabel || 'group') + ' (tall tick = their mean)', color: gcol }, { label: 'everyone else (grey tick = their mean)', color: ocol }]);
  }

  const rateSeries = (rows, xKey) => (rows || []).map(x => ({ x: xKey ? x[xKey] : x.bin, lab: x.bin, v: x.rate, lo: x.lo, hi: x.hi,
    tip: `n = ${x.n} decisions, ${x.k} people` }));
  const medSeries = rows => (rows || []).map(x => ({ x: x.bin, v: x.med, lo: x.lo, hi: x.hi, tip: `n = ${x.n}, ${x.k} people` }));
  const sub = host => h('div', {}, host);
  const head = (host, t) => h('p', { class: 'note', html: t }, host);
  const modelRow = (label, t, extra = {}) => t ? Object.assign({ label, est: t.est, lo: t.lo, hi: t.hi, p: t.p, n: t.n, k: t.k }, extra) : null;

  Object.assign(CH, {
    /* ── A · size ─────────────────────────────────────────────────────────────── */
    'handover.sizeBoth': safe(host => {
      const B = D.size.both;
      ciChart(host, [
        { label: 'Strategic: card taken', color: C('--s-strat'), pts: rateSeries(B.strat, 'x') },
        { label: 'Tactical: Suggest pressed', color: C('--s-tac'), pts: rateSeries(B.tac, 'x') }],
        { xmin: 2, xmax: 18, xticks: [3, 5, 6, 8, 11.5, 16.5].map(v => v), xLabel: 'drones the mission needs (bins: ≤3, 5, 6, 7–9, 10–13, 15–18)',
          yLabel: 'share of decisions handed over', ymin: 0.3, ymax: 1, yticks: [.3, .4, .5, .6, .7, .8, .9, 1] });
      const M = D.size.models;
      head(host, `Within-person odds ratio per doubling of drones needed — strategic ×${num(M.s_doubling.est, 2)} [${num(M.s_doubling.lo, 2)}, ${num(M.s_doubling.hi, 2)}], `
        + `tactical ×${num(M.t_doubling.est, 2)} [${num(M.t_doubling.lo, 2)}, ${num(M.t_doubling.hi, 2)}]; both tiers in one model ×${num(M.both_common.est, 2)} `
        + `(${pval(M.both_common.p)}). Bars are 95% intervals from resampling people.`);
      tableFor(host, ['Drones needed', 'Strategic: card', 'n', 'Tactical: Suggest', 'n'], B.strat.map((x, i) => {
        const t = B.tac[i] || {};
        return [x.bin, `${p0(x.rate)} [${p0(x.lo)}, ${p0(x.hi)}]`, x.n, `${p0(t.rate)} [${p0(t.lo)}, ${p0(t.hi)}]`, t.n];
      }));
    }),
    'handover.sizeStrat': safe(host => {
      const A = D.size.strat;
      ciChart(host, [
        { label: 'one drone type', color: C('--mark-soft'), pts: rateSeries(A.one, 'x') },
        { label: 'three drone types', color: C('--s-strat'), pts: rateSeries(A.three, 'x').filter(p => p.lab !== '1–3') }],
        { xmin: 2, xmax: 19, xticks: [3, 5, 6, 7, 9, 10.5, 12.5, 15, 18], xLabel: 'drones the mission needs',
          yLabel: 'strategy card taken', ymin: 0.2, ymax: 1, yticks: [.2, .4, .6, .8, 1] });
      head(host, 'Strategic tier only, split by how many drone types the mission needs (two-type missions, n = 12, left out). '
        + 'Hover a dot for n. Within one-type missions more drones do not raise uptake; within three-type missions they do, unevenly.');
      tableFor(host, ['Types', 'Drones needed', 'Card taken', 'n', 'people'],
        [...A.one.map(x => ['one', x.bin, `${p0(x.rate)} [${p0(x.lo)}, ${p0(x.hi)}]`, x.n, x.k]),
         ...A.three.map(x => ['three', x.bin, `${p0(x.rate)} [${p0(x.lo)}, ${p0(x.hi)}]`, x.n, x.k])]);
    }),
    'handover.sizeStratSteps': safe(host => {
      const A = D.size.strat;
      ciChart(host, [
        { label: 'decided before the cards loaded', color: C('--r-man'), pts: rateSeries(A.preempt, 'x') },
        { label: 'card taken, cards on screen', color: C('--s-strat'), pts: rateSeries(A.tookSeen, 'x') }],
        { xmin: 2, xmax: 18, xticks: [3, 5, 6, 8, 11.5, 16.5], xLabel: 'drones the mission needs (bins: ≤3, 5, 6, 7–9, 10–13, 15–18)',
          yLabel: 'share of decisions', ymin: 0, ymax: 1 });
      const M = D.size.models;
      head(host, `Two steps of one strategic decision. Before the cards finish loading (~${num(D.speed.revealMean, 1)} s) the operator can already build by hand — `
        + `that falls with size (×${num(M.s_pre.est, 2)} per doubling, ${pval(M.s_pre.p)}). Once the cards are on screen, taking one rises with size only weakly `
        + `(×${num(M.s_seen.est, 2)} [${num(M.s_seen.lo, 2)}, ${num(M.s_seen.hi, 2)}], ${pval(M.s_seen.p)}).`);
    }),
    'handover.sizeTac': safe(host => {
      const A = D.size.tac;
      const cats = A.byPlan.map(x => x.bin);
      ciChart(host, [
        { label: 'all plans', color: C('--s-tac'), pts: rateSeries(A.byPlan) },
        { label: 'mission allocated by hand', color: C('--r-man'), pts: rateSeries(A.byPlanRoute.manual), small: true, hollow: true, faint: true },
        { label: 'mission allocated from a card', color: C('--s-strat'), pts: rateSeries(A.byPlanRoute.card), small: true, hollow: true, faint: true }],
        { cats, dodge: 10, xLabel: 'plan size = drones in the team × tasks', yLabel: 'Suggest pressed', ymin: 0.2, ymax: 1, yticks: [.2, .4, .6, .8, 1] });
      tableFor(host, ['Plan size', 'Suggest pressed', 'n', 'people'], A.byPlan.map(x => [x.bin, `${p0(x.rate)} [${p0(x.lo)}, ${p0(x.hi)}]`, x.n, x.k]));
    }),
    'handover.sizeMeasures': safe(host => {
      const box = sub(host);
      const draw = k => {
        box.innerHTML = '';
        const sA = D.size.strat[k], tA = D.size.tac[k];
        const cats = [...new Set([...(sA || []), ...(tA || [])].map(x => String(x.bin)))];
        const fix = rows => rows.map(x => Object.assign({}, x, { bin: String(x.bin) }));
        ciChart(box, [{ label: 'Strategic: card taken', color: C('--s-strat'), pts: rateSeries(fix(sA)) },
                      { label: 'Tactical: Suggest pressed', color: C('--s-tac'), pts: rateSeries(fix(tA)) }],
          { cats, dodge: 12, xLabel: k === 'byTasks' ? 'tasks in the mission (residual missions left out)' : 'drone types the mission needs',
            yLabel: 'share handed over', ymin: 0.3, ymax: 1, yticks: [.3, .5, .7, .9, 1] });
      };
      btnBar(host, 'Size measured as', [['byTypes', 'drone types'], ['byTasks', 'tasks']], 'byTypes', draw);
      host.appendChild(box);
      draw('byTypes');
    }),
    'handover.sizeModels': safe(host => {
      const M = D.size.models;
      ciStrip(host, [
        modelRow('Strategic · per doubling of drones needed', M.s_doubling, { main: true, color: C('--s-strat') }),
        modelRow('Strategic · per extra drone type', M.s_type, { color: C('--s-strat') }),
        modelRow('Strategic · per extra task', M.s_task, { color: C('--s-strat') }),
        modelRow('Strategic · drones, three-type missions only', M.s_d_in3, { color: C('--s-strat') }),
        modelRow('Strategic · drones, one-type missions only', M.s_d_in1, { color: C('--s-strat') }),
        modelRow('Strategic · cards on screen only, per doubling', M.s_seen, { color: C('--s-strat') }),
        modelRow('Tactical · per doubling of plan size', M.t_doubling_plan, { main: true, color: C('--s-tac'), head: true }),
        modelRow('Tactical · per doubling of drones needed', M.t_doubling, { color: C('--s-tac') }),
        modelRow('Tactical · per extra drone type', M.t_type, { color: C('--s-tac') }),
        modelRow('Tactical · per extra task', M.t_task, { color: C('--s-tac') }),
        modelRow('Tactical · plan size, three-type only', M.t_plan_in3, { color: C('--s-tac') }),
        modelRow('Tactical · plan size, one-type only', M.t_plan_in1, { color: C('--s-tac') }),
        modelRow('Both tiers · per doubling of drones needed', M.both_common, { main: true, head: true }),
        modelRow('Tactical slope ÷ strategic slope', M.both_diff, {})].filter(Boolean),
        { xLabel: 'odds ratio of handing over, comparing each person with themselves (95% interval)' });
    }),
    'handover.sizeRobust': safe(host => {
      const box = sub(host);
      const draw = k => { box.innerHTML = ''; ciStrip(box, (k === 's' ? D.size.robustS : D.size.robustT).map((r, i) => Object.assign({}, r, { main: i === 0,
        color: k === 's' ? C('--s-strat') : C('--s-tac') })), { xLabel: k === 's' ? 'odds ratio of taking a card, per doubling of drones needed' : 'odds ratio of pressing Suggest, per doubling of plan size' }); };
      btnBar(host, 'Tier', [['s', 'Strategic'], ['t', 'Tactical']], 's', draw);
      host.appendChild(box);
      draw('s');
    }),
    'handover.sizePeople': safe(host => {
      const P = D.size.people || [];
      [['sA', 'sB', 'Strategic: card taken', 'one-type missions', 'three-type missions'],
       ['tA', 'tB', 'Tactical: Suggest pressed', `plans ≤ ${num(D.size.tacPlanMedian, 0)} (small)`, `plans > ${num(D.size.tacPlanMedian, 0)} (big)`]].forEach(([a, b, title, al, bl]) => {
        const pairs = P.filter(p => p[a] != null && p[b] != null).map(p => ({ label: p.pid, a: p[a], b: p[b] }));
        h('p', { class: 'note', html: `<b>${title}</b> — each line is one person (at least 3 decisions on each side)` }, host);
        const d = sub(host);
        if (pairs.length) slopes(d, pairs, { aLabel: al, bLabel: bl, height: 230 });
      });
      const c = D.size.peopleCounts;
      head(host, `Strategic: higher on big jobs for ${c.strategic.up} of ${c.strategic.n} people, lower for ${c.strategic.down} (sign test ${pval(c.strategic.p)}). `
        + `Tactical: ${c.tactical.up} of ${c.tactical.n} higher, ${c.tactical.down} lower (${pval(c.tactical.p)}).`);
    }),

    /* ── B · speed ───────────────────────────────────────────────────────────── */
    'handover.speedSize': safe(host => {
      const box = sub(host);
      const draw = k => {
        box.innerHTML = '';
        if (k === 's') {
          const S = D.speed.strat;
          ciChart(box, [
            { label: 'card taken', color: C('--s-strat'), pts: medSeries(S['card']) },
            { label: 'manual, after the cards loaded', color: C('--r-man'), pts: medSeries(S['manual after cards']) },
            { label: 'manual, before the cards loaded', color: C('--mark-soft'), pts: medSeries(S['pre-emptive manual']) }],
            { cats: ['one type', 'three types, 6–9 drones', 'three types, 10–18 drones'], dodge: 16, fmt: v => num(v, 0) + ' s',
              ymin: 0, ymax: 30, yticks: [0, 5, 10, 15, 20, 25, 30], xLabel: 'mission size', yLabel: 'seconds, panel open → choice (median)', line: false });
          head(box, `Raw seconds the operator actually spent (the card's forced ~${num(D.speed.revealMean, 1)} s reveal included). Bars: 95% intervals, people resampled.`);
        } else {
          const T = D.speed.tac, e = D.speed.tacBandEdges || [];
          ciChart(box, [
            { label: 'built by hand', color: C('--r-man'), pts: medSeries(T['hand']) },
            { label: 'Suggest, kept as is', color: C('--s-tac'), pts: medSeries(T['suggest-kept']) },
            { label: 'Suggest, then edited', color: C('--mark-soft'), pts: medSeries(T['suggest-edited']), hollow: true }],
            { cats: ['small', 'mid', 'large'], dodge: 16, fmt: v => num(v, 0) + ' s', ymin: 0, ymax: 90, yticks: [0, 15, 30, 45, 60, 75, 90],
              xLabel: `plan size thirds (drones × tasks: small ≤ ${num(e[0], 0)}, large > ${num(e[1], 0)})`, yLabel: 'seconds, planner open → confirm (median)' });
          head(box, 'Includes the 1-entry-per-second Suggest fill. Edited plans are few (18) — their intervals are wide.');
        }
      };
      btnBar(host, 'Tier', [['s', 'Strategic'], ['t', 'Tactical']], 's', draw);
      host.appendChild(box);
      draw('s');
    }),
    'handover.speedModel': safe(host => {
      const R = D.speed.stratModel;
      const row = (lab, t, c) => ({ label: lab, est: t.est, lo: t.lo, hi: t.hi, p: t.p, color: c });
      ciStrip(host, [row('Card vs manual, one-type · seconds spent', R.raw.one, C('--s-strat')),
                     row('Card vs manual, three-type · seconds spent', R.raw.three, C('--s-strat')),
                     row('Card vs manual, one-type · net of forced reveal', R.net.one, C('--mark-soft')),
                     row('Card vs manual, three-type · net of forced reveal', R.net.three, C('--mark-soft')),
                     { label: 'Tactical: Suggest kept vs hand (plan size held)', est: D.speed.tacKept.pct, lo: D.speed.tacKept.lo, hi: D.speed.tacKept.hi, p: D.speed.tacKept.p, color: C('--s-tac'), head: true }],
        { log: false, fmt: v => sgn(100 * v, 0) + '%', ticks: [-0.6, -0.4, -0.2, 0, 0.2, 0.4, 0.6], xLabel: 'change in decision time with the assistant (negative = faster), within person' });
    }),

    /* ── C · parallel work ───────────────────────────────────────────────────── */
    'handover.parallel': safe(host => {
      const P = D.parallel;
      const cats = ['<15 s', '15–25 s', '25–40 s', '>40 s'];
      ciChart(host, [{ label: 'Suggest pressed', color: C('--s-tac'), pts: rateSeries(P.timeMatched.suggest) },
                     { label: 'built by hand', color: C('--r-man'), pts: rateSeries(P.timeMatched.hand) }],
        { cats, dodge: 16, xLabel: 'how long the tactical planner was open (open → confirm)', yLabel: 'opened another mission\'s strategic panel meanwhile', ymin: 0, ymax: 1 });
      head(host, `Time-matched: plans open for the same length of time, compared. Overall ${p0(P.rateSuggest)} of Suggest plans vs ${p0(P.rateHand)} of hand-built plans; `
        + `${p0(P.rateDuringFill)} of Suggest plans had the other panel opened inside the fill itself (median fill ${num(P.fillSecsMedian, 0)} s).`);
      tableFor(host, ['Open for', 'Suggest', 'n', 'Hand', 'n'], cats.map(c => {
        const a = P.timeMatched.suggest.find(x => x.bin === c) || {}, b = P.timeMatched.hand.find(x => x.bin === c) || {};
        return [c, `${p0(a.rate)} [${p0(a.lo)}, ${p0(a.hi)}]`, a.n, `${p0(b.rate)} [${p0(b.lo)}, ${p0(b.hi)}]`, b.n];
      }));
    }),
    'handover.parallelSpecs': safe(host => {
      ciStrip(host, D.parallel.specs.map((r, i) => Object.assign({}, r, { main: i === 0, color: C('--s-tac') })),
        { xLabel: 'odds ratio: Suggest plan vs hand-built plan, same person (95% interval)' });
    }),

    /* ── D · C06 ─────────────────────────────────────────────────────────────── */
    'handover.c06Profile': safe(host => {
      const C6 = D.c06;
      const F = { pct: v => v == null ? '—' : pct(v, 0), pp: v => v == null ? '—' : sgn(100 * v, 0) + ' pts', s: v => num(v, 1) + ' s', n: v => num(v, 1), z: v => sgn(v, 2) };
      groupStrip(host, C6.rows.map(r => Object.assign({}, r, { fmt: F[r.unit] || (v => num(v, 2)) })), C6.people, C6.who,
        { groupLabel: 'said the assistant is slow (C06: ' + C6.who.join(', ') + ')', color: C('--s-tac') });
      head(host, 'p = two-sided permutation test of the group mean difference (labels reshuffled 20,000 times). Six people — only large differences are detectable; none survives correction.');
    }),

    /* ── E · learning ────────────────────────────────────────────────────────── */
    'handover.learnSpeed': safe(host => {
      const box = sub(host);
      const L = D.learn.curves;
      const draw = k => {
        box.innerHTML = '';
        const col = k === 'strat' ? C('--s-strat') : C('--s-tac');
        const mk = rows => (rows || []).map(x => ({ x: x.bin, v: x.med, lo: x.lo, hi: x.hi, tip: `n = ${x.n}, ${x.k} people` }));
        ciChart(box, [{ label: 'session 1', color: C('--mark-soft'), pts: mk(L[k + '1']) }, { label: 'session 2', color: col, pts: mk(L[k + '2']) }],
          { xmin: 0.5, xmax: 8.5, xticks: [1, 2, 3, 4, 5, 6, 7, 8], fmt: v => num(v, 0) + ' s', ymin: 0, ymax: k === 'strat' ? 20 : 40,
            yticks: k === 'strat' ? [0, 5, 10, 15, 20] : [0, 10, 20, 30, 40], xLabel: 'minute of the 8-minute session',
            yLabel: k === 'strat' ? 'net seconds per strategic decision (median)' : 'net seconds per tactical plan (median)' });
        const M = D.learn.models, a = k === 'strat' ? M.stratOver8 : M.tacOver8, b = k === 'strat' ? M.stratRun2 : M.tacRun2;
        head(box, `Net = forced waits removed. Model (person-clustered): ${sgn(100 * a.pct, 0)}% over the 8 minutes [${sgn(100 * a.lo, 0)}, ${sgn(100 * a.hi, 0)}], ${pval(a.p)}; `
          + `session 2 vs 1 ${sgn(100 * b.pct, 0)}% [${sgn(100 * b.lo, 0)}, ${sgn(100 * b.hi, 0)}], ${pval(b.p)}.`);
      };
      btnBar(host, 'Tier', [['strat', 'Strategic'], ['tac', 'Tactical']], 'strat', draw);
      host.appendChild(box);
      draw('strat');
    }),
    'handover.learnGap': safe(host => {
      const G = D.learn.gap, I = D.learn.inter;
      const rows = [['strat1', 'Strategic · session 1', C('--s-strat')], ['strat2', 'Strategic · session 2', C('--s-strat')],
                    ['tac1', 'Tactical · session 1', C('--s-tac')], ['tac2', 'Tactical · session 2', C('--s-tac')]]
        .filter(([k]) => G[k]).map(([k, lab, c]) => ({ label: lab, est: G[k].gap, lo: G[k].lo, hi: G[k].hi, p: null, color: c,
          note: `big ${p0(G[k].big)} (n=${G[k].nBig}) vs small ${p0(G[k].small)} (n=${G[k].nSmall})` }));
      ciStrip(host, rows, { log: false, padL: 220, fmt: v => sgn(100 * v, 0) + ' pts', ticks: [-0.1, 0, 0.1, 0.2, 0.3, 0.4],
        xLabel: 'hand-over on big jobs minus small jobs, percentage points (95% interval, people resampled)' });
      head(host, `If practice sharpened the rule, session 2 would sit further right. It does not: size × session odds-ratio ratio strategic ×${num(I.strat.est, 2)} (${pval(I.strat.p)}), `
        + `tactical ×${num(I.tac.est, 2)} (${pval(I.tac.p)}). Strategic "big" = three-type, "small" = one-type; tactical split at the median plan size.`);
    }),
    'handover.c22': safe(host => {
      const C2 = D.learn.c22;
      const ppl = C2.people;
      const mk = (key, lab, fmt) => Object.assign({ key, label: lab, fmt }, C2[key]);
      groupStrip(host, [mk('dZ', 'Score within game, change (SD)', v => sgn(v, 2)),
                        mk('dS', 'Strategic decision time, change (log)', v => sgn(v, 2)),
                        mk('dT', 'Tactical plan time, change (log)', v => sgn(v, 2))], ppl, C2.who,
        { groupLabel: 'said they got better (C22)', color: C('--good') });
      head(host, `Session 2 minus session 1, per person (negative time = faster). Score up: C22 ${C2.scoreUp.c22} of ${C2.fasterS.nC22}, others ${C2.scoreUp.others} of ${C2.fasterS.nOthers}. `
        + `Faster strategic decisions: C22 ${C2.fasterS.c22}, others ${C2.fasterS.others}. Faster tactical plans: C22 ${C2.fasterT.c22}, others ${C2.fasterT.others}.`);
    }),

    /* ── F · manual ──────────────────────────────────────────────────────────── */
    'handover.manualDots': safe(host => {
      const M = D.manual;
      const KC = { 'pre-emptive': C('--mark-soft'), 'built after seeing cards': C('--r-man'), 'edited a card': C('--r-cons') };
      const box = sub(host);
      const draw = k => {
        box.innerHTML = '';
        const H = 320, padL = 58, padR = 20, padT = 14, padB = 46;
        const s = svgRoot(box, W, H);
        const vals = M.dots.map(d => d[k]);
        const ymin = Math.min(-5, ...vals) - 0.5, ymax = Math.max(5, ...vals) + 0.5;
        const x = v => padL + (W - padL - padR) * ((v - 1) / 18);
        const y = v => H - padB - (H - padB - padT) * ((v - ymin) / (ymax - ymin));
        for (let v = Math.ceil(ymin); v <= ymax; v += 2) {
          el('line', { x1: padL, x2: W - padR, y1: y(v), y2: y(v), stroke: C('--grid') }, s);
          txt(s, { x: padL - 8, y: y(v) + 4, 'text-anchor': 'end', 'font-family': mono() }, sgn(v, 0));
        }
        el('line', { x1: padL, x2: W - padR, y1: y(0), y2: y(0), stroke: C('--ink-3'), 'stroke-width': 1.5 }, s);
        txt(s, { x: W - padR, y: y(0) - 5, 'text-anchor': 'end', 'font-size': 10.5 }, 'same as the Conservative card');
        [3, 5, 6, 7, 9, 12, 15, 18].forEach(v => txt(s, { x: x(v), y: H - padB + 17, 'text-anchor': 'middle', 'font-family': mono(), 'font-size': 10.5 }, v));
        txt(s, { x: (padL + W - padR) / 2, y: H - 8, 'text-anchor': 'middle' }, 'drones the mission needs');
        txt(s, { x: 14, y: (padT + H - padB) / 2, 'text-anchor': 'middle', transform: `rotate(-90 14 ${(padT + H - padB) / 2})` },
          k === 'd' ? 'manual drones − Conservative card drones' : 'same, needed drone types only');
        M.dots.forEach((d, i) => {
          const jx = (((i * 7919) % 100) / 100 - 0.5) * 0.7, jy = (((i * 104729) % 100) / 100 - 0.5) * 0.5;
          const c = el('circle', { cx: x(d.nd + jx), cy: y(d[k] + jy), r: 4, fill: KC[d.kind] || C('--mark'), opacity: .75, stroke: C('--surface'), 'stroke-width': 1 }, s);
          hoverable(c, `<b>${d.pid}</b> · ${d.kind}<br>mission needs ${d.nd} drones (${d.nc} type${d.nc > 1 ? 's' : ''})<br>committed ${d.got}; cards: Conservative ${d.cons}, Aggressive ${d.aggr}`
            + `<br>vs Conservative ${sgn(d.d, 0)} (needed types ${sgn(d.dn, 0)}, unneeded ${sgn(d.du, 0)})${d.odd ? '<br>Conservative card carried a type the mission did not need' : ''}`);
        });
      };
      btnBar(host, 'Count', [['d', 'all drones'], ['dn', 'needed types only']], 'd', draw);
      host.appendChild(box);
      draw('d');
      legend(host, Object.entries(KC).map(([label, color]) => ({ label: label === 'pre-emptive' ? 'pre-emptive (cards not yet shown)' : label, color })));
      tableFor(host, ['Size', 'Kind', 'n', 'mean vs Conservative', 'needed types', 'unneeded types'],
        M.bands.map(b => [b.band, b.kind, b.n, sgn(b.mean, 2), sgn(b.meanNeeded, 2), sgn(b.meanUnneeded, 2)]));
    }),
    'handover.manualAnchor': safe(host => {
      const T = D.manual.tests;
      const row = (lab, t, c) => t ? { label: lab, est: t.est, lo: t.lo, hi: t.hi, p: t.p, n: t.n, k: t.k, color: c } : null;
      ciStrip(host, [row('Saw the cards · all types', T.seen, C('--r-man')), row('Saw the cards · needed types', T.seenNeeded, C('--r-man')),
                     row('Built own after seeing · needed types', T.seenOwnNeeded, C('--r-man')),
                     row('Edited a card · needed types', T.editedNeeded, C('--r-cons')),
                     row('Pre-emptive (never saw cards) · all types', T.preempt, C('--mark-soft')),
                     row('Pre-emptive · needed types', T.preemptNeeded, C('--mark-soft'))].filter(Boolean),
        { log: false, padL: 280, ticks: [-0.5, 0, 0.5, 1, 1.5, 2], xLabel: 'extra manual drones per extra card drone, mission need held fixed (95% interval)' });
    }),
    'handover.manualPos': safe(host => {
      const M = D.manual;
      const keys = [{ key: 'below both', label: 'below both cards', color: C('--r-cons') }, { key: 'equals a card', label: 'equals a card total', color: C('--mark-soft') },
                    { key: 'strictly between', label: 'strictly between', color: C('--s-strat') }, { key: 'above both', label: 'above both cards', color: C('--r-aggr') }];
      barsStacked(host, M.pos.map(p => ({ label: `${p.kind} (n=${p.n})`, values: Object.fromEntries(keys.map(k => [k.key, p[k.key] / p.n])) })), keys, { padL: 230 });
      legend(host, keys.map(k => ({ label: k.label, color: k.color })));
    }),
  });
})();
