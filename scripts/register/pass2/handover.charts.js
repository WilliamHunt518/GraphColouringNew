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
  /* Rotated y-axis title; a newline splits it into two lines so long titles never clip. */
  const yTitle = (s, label, cy) => {
    const lines = String(label || '').split('\n');
    lines.forEach((ln, i) => {
      const x = lines.length > 1 ? 11 + i * 13 : 14;
      txt(s, { x, y: cy, 'text-anchor': 'middle', transform: `rotate(-90 ${x} ${cy})`, 'font-size': lines.length > 1 && i ? 10 : 11 }, ln);
    });
  };

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
        { xLabel: 'odds ratio of handing over, each person compared with themselves (95% interval, log scale)' });
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
        yTitle(s, k === 'd' ? 'drones committed by hand minus\ndrones on the Conservative card' : 'same difference (drones),\nneeded drone types only', (padT + H - padB) / 2);
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
      head(host, 'Each bar is 100% of that kind of manual allocation (n = decisions); each segment is the % whose total drone count was below both cards\' totals, '
        + 'equal to one card\'s total, strictly between the two, or above both.');
    }),
  });

  /* ── pass 3 helpers (bars for categories, per the researcher's pass-2 notes) ─────────────── */
  const P3 = () => { if (!D.p3) throw new Error('pass-3 numbers missing: rerun handover.py'); return D.p3; };
  const sec = v => v == null ? '—' : num(v, 1) + ' s';

  /* Grouped vertical bars with 95% interval whiskers. cats: category keys; series: [{label, color,
     pts: [{cat, v, lo, hi, tip, color?}]}]. Bars start at zero; every bar has a hover with n. */
  function ciBars(host, cats, series, o = {}) {
    const H = o.height || 280, padL = 62, padR = 14, padT = 20, padB = o.padB || 56;
    const s = svgRoot(host, W, H);
    const fmt = o.fmt || (v => pct(v, 0));
    const ymin = o.ymin != null ? o.ymin : 0, ymax = o.ymax != null ? o.ymax : 1;
    const y = v => H - padB - (H - padB - padT) * ((Math.max(ymin, Math.min(ymax, v)) - ymin) / (ymax - ymin));
    (o.yticks || [0, .25, .5, .75, 1]).forEach(v => {
      el('line', { x1: padL, x2: W - padR, y1: y(v), y2: y(v), stroke: C('--grid') }, s);
      txt(s, { x: padL - 8, y: y(v) + 4, 'text-anchor': 'end', 'font-family': mono() }, (o.tickFmt || fmt)(v));
    });
    const bandW = (W - padL - padR) / cats.length;
    const ns = series.length, gap = 3;
    const bw = Math.max(6, Math.min(o.maxBar || 42, (bandW - 14 - gap * (ns - 1)) / ns));
    cats.forEach((c, ci) => {
      const cx = padL + bandW * (ci + 0.5);
      const lines = String(o.catLabel ? o.catLabel(c) : c).split('\n');
      lines.forEach((ln, li) => txt(s, { x: cx, y: H - padB + 16 + li * 12, 'text-anchor': 'middle', 'font-size': li ? 9.5 : 10.5,
        'font-family': mono() }, ln));
      const total = ns * bw + gap * (ns - 1);
      series.forEach((se, si) => {
        const p = (se.pts || []).find(q => q && String(q.cat) === String(c));
        if (!p || p.v == null) return;
        const bx = cx - total / 2 + si * (bw + gap);
        const col = p.color || se.color;
        const y0 = y(Math.max(ymin, 0));
        el('rect', { x: bx, y: Math.min(y(p.v), y0), width: bw, height: Math.max(0.5, Math.abs(y0 - y(p.v))), rx: 3, fill: col,
                     opacity: se.faint ? .5 : .88 }, s);
        const xm = bx + bw / 2;
        if (p.lo != null && p.hi != null) {
          el('line', { x1: xm, x2: xm, y1: y(p.lo), y2: y(p.hi), stroke: C('--ink-2'), 'stroke-width': 1.4 }, s);
          [p.lo, p.hi].forEach(v => el('line', { x1: xm - 4, x2: xm + 4, y1: y(v), y2: y(v), stroke: C('--ink-2'), 'stroke-width': 1.4 }, s));
        }
        if (o.values !== false && bw >= 20) {
          const top = Math.min(y(p.v), p.hi != null ? y(p.hi) : y(p.v));
          txt(s, { x: xm, y: top - 5, 'text-anchor': 'middle', 'font-size': 9.5, 'font-family': mono(), fill: C('--ink-2') }, fmt(p.v));
        }
        const hit = el('rect', { x: bx, y: padT, width: bw, height: H - padB - padT, fill: 'transparent' }, s);
        hoverable(hit, `<b>${se.label}</b> · ${lines.join(' ')}<br>${fmt(p.v)}${p.lo != null && p.hi != null ? ` [${fmt(p.lo)}, ${fmt(p.hi)}]` : ''}`
          + (p.tip ? '<br>' + p.tip : ''));
      });
    });
    el('line', { x1: padL, x2: W - padR, y1: H - padB, y2: H - padB, stroke: C('--line') }, s);
    txt(s, { x: (padL + W - padR) / 2, y: H - 6, 'text-anchor': 'middle' }, o.xLabel || '');
    yTitle(s, o.yLabel, (padT + H - padB) / 2);
    if (ns >= 2 && o.legend !== false) legend(host, series.map(se => ({ label: se.label, color: se.color })));
    return s;
  }

  /* Horizontal stacked bars in absolute units (seconds). rows: [{label, sub, vals: {key: {mean, lo, hi}}}];
     keys: [{key, label, color}]. Each segment's hover gives its mean and interval. */
  function stackAbs(host, rows, keys, o = {}) {
    const rowH = 46, padL = o.padL || 170, padR = 70, padT = 8, padB = 36;
    const H = padT + rows.length * rowH + padB;
    const s = svgRoot(host, W, H);
    const tot = r_ => keys.reduce((a, k) => a + Math.max(0, (r_.vals[k.key] || {}).mean || 0), 0);
    const max = o.max || Math.max(...rows.map(tot)) * 1.05 || 1;
    const x = v => padL + (W - padL - padR) * (v / max);
    const step = o.step || 20;
    for (let v = 0; v <= max; v += step) {
      el('line', { x1: x(v), x2: x(v), y1: padT, y2: H - padB + 4, stroke: C('--grid') }, s);
      txt(s, { x: x(v), y: H - padB + 17, 'text-anchor': 'middle', 'font-family': mono(), 'font-size': 10 }, num(v, 0));
    }
    txt(s, { x: (padL + W - padR) / 2, y: H - 4, 'text-anchor': 'middle' }, o.xLabel || 'seconds');
    rows.forEach((r_, i) => {
      const yy = padT + i * rowH, bh = 22;
      const lt = el('text', { x: padL - 10, y: yy + rowH / 2, 'text-anchor': 'end', fill: C('--ink-2'), 'font-size': 12.5 }, s);
      lt.textContent = r_.label;
      if (r_.sub) txt(s, { x: padL - 10, y: yy + rowH / 2 + 13, 'text-anchor': 'end', 'font-size': 10 }, r_.sub);
      let acc = 0;
      keys.forEach(k => {
        const v = (r_.vals[k.key] || {});
        const m = Math.max(0, v.mean || 0);
        if (m <= 0) return;
        const x0 = x(acc), w = x(acc + m) - x0;
        el('rect', { x: x0, y: yy + (rowH - bh) / 2 - 4, width: Math.max(0, w - 1.5), height: bh, rx: 3, fill: k.color }, s);
        if (w > 30) txt(s, { x: x0 + w / 2, y: yy + rowH / 2 + 4 - 4, 'text-anchor': 'middle', 'font-size': 10.5, 'font-family': mono(), fill: '#fff' }, num(m, 0));
        const hit = el('rect', { x: x0, y: yy + (rowH - bh) / 2 - 4, width: Math.max(1, w), height: bh, fill: 'transparent' }, s);
        hoverable(hit, `<b>${k.label}</b><br>${r_.label}: ${sec(v.mean)} [${sec(v.lo)}, ${sec(v.hi)}]${r_.tip ? '<br>' + r_.tip : ''}`);
        acc += m;
      });
      txt(s, { x: x(acc) + 6, y: yy + rowH / 2, 'font-family': mono(), 'font-size': 11, fill: C('--ink-2') }, num(acc, 0) + ' s');
    });
    legend(host, keys.map(k => ({ label: k.label, color: k.color })));
  }

  /* One row per measure, two bars (group vs everyone else) with 95% intervals; each row has its own scale. */
  function pairBars(host, rows, o = {}) {
    const rowH = 46, padL = 270, padR = 150, padT = 8;
    const H = padT + rows.length * rowH + 10;
    const s = svgRoot(host, W, H);
    const gcol = o.color || C('--mark'), ocol = C('--mark-soft');
    rows.forEach((m, i) => {
      const yy = padT + i * rowH;
      const vals = [m.inMean, m.inLo, m.inHi, m.restMean, m.restLo, m.restHi].filter(v => v != null && isFinite(v));
      if (!vals.length) return;
      let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
      if (hi === lo) hi = lo + 1;
      const x = v => padL + (W - padL - padR) * ((v - lo) / (hi - lo));
      const lt = el('text', { x: padL - 12, y: yy + rowH / 2 + 4, 'text-anchor': 'end', fill: C('--ink-2'), 'font-size': 12 }, s);
      lt.textContent = m.label;
      el('line', { x1: x(0), x2: x(0), y1: yy + 4, y2: yy + rowH - 6, stroke: C('--ink-3') }, s);
      [[m.inMean, m.inLo, m.inHi, gcol, o.groupLabel || 'group', m.nIn, 0], [m.restMean, m.restLo, m.restHi, ocol, 'everyone else', m.nRest, 1]]
        .forEach(([v, a, b, col, lab, n, j]) => {
          if (v == null) return;
          const by = yy + 6 + j * 16, bh = 12;
          el('rect', { x: Math.min(x(0), x(v)), y: by, width: Math.max(1, Math.abs(x(v) - x(0))), height: bh, rx: 2, fill: col }, s);
          if (a != null && b != null) {
            el('line', { x1: x(a), x2: x(b), y1: by + bh / 2, y2: by + bh / 2, stroke: C('--ink-2'), 'stroke-width': 1.4 }, s);
            [a, b].forEach(w => el('line', { x1: x(w), x2: x(w), y1: by + 2, y2: by + bh - 2, stroke: C('--ink-2'), 'stroke-width': 1.4 }, s));
          }
          const hit = el('rect', { x: padL, y: by, width: W - padL - padR, height: bh, fill: 'transparent' }, s);
          hoverable(hit, `<b>${lab}</b> · ${m.label}<br>mean ${m.fmt(v)}${a != null ? ` [${m.fmt(a)}, ${m.fmt(b)}]` : ''}<br>n = ${n} people`);
        });
      const pt = el('text', { x: W - padR + 12, y: yy + rowH / 2 - 2, fill: C('--ink-2'), 'font-size': 11, 'font-family': mono() }, s);
      pt.textContent = `${m.fmt(m.inMean)} vs ${m.fmt(m.restMean)}`;
      const pp = el('text', { x: W - padR + 12, y: yy + rowH / 2 + 12, fill: pColour(m.p), 'font-size': 10.5, 'font-family': mono() }, s);
      pp.textContent = pval(m.p);
    });
    legend(host, [{ label: (o.groupLabel || 'group') + ' (top bar)', color: gcol }, { label: 'everyone else (lower bar)', color: ocol }]);
  }

  const rateBars = (rows, tipX) => (rows || []).map(x => ({ cat: String(x.bin), v: x.rate, lo: x.lo, hi: x.hi,
    tip: `n = ${x.n} decisions, ${x.k} people${tipX ? '<br>' + tipX : ''}` }));
  const orTxt = t => t ? `×${num(t.est, 2)} [${num(t.lo, 2)}, ${num(t.hi, 2)}], ${pval(t.p)}` : 'not estimable';

  Object.assign(CH, {
    /* f-size-decides#both, as side-by-side bars */
    'handover.sizeBothBars': safe(host => {
      const B = D.size.both, M = D.size.models;
      const cats = B.strat.map(x => String(x.bin));
      ciBars(host, cats, [
        { label: 'Strategic: card taken', color: C('--s-strat'), pts: rateBars(B.strat) },
        { label: 'Tactical: Suggest pressed', color: C('--s-tac'), pts: rateBars(B.tac) }],
        { xLabel: 'drones the mission needs (binned so each bar has ≥ 59 decisions)', yLabel: '% of decisions handed over\n(card taken / Suggest pressed)' });
      head(host, `Within-person odds ratio per doubling of drones needed: strategic ${orTxt(M.s_doubling)}; tactical ${orTxt(M.t_doubling)}; `
        + `both tiers in one model ${orTxt(M.both_common)}. Whiskers are 95% intervals from resampling people. The 5-drone dip on the strategic tier is seven `
        + 'particular missions, not a size effect (see "Why the 5-drone missions dip").');
      tableFor(host, ['Drones needed', 'Strategic: card', 'n', 'Tactical: Suggest', 'n'], B.strat.map((x, i) => {
        const t = B.tac[i] || {};
        return [x.bin, `${p0(x.rate)} [${p0(x.lo)}, ${p0(x.hi)}]`, x.n, `${p0(t.rate)} [${p0(t.lo)}, ${p0(t.hi)}]`, t.n];
      }));
    }),

    /* f-size-decides#strategic-steps, as bars */
    'handover.sizeStratStepsBars': safe(host => {
      const A = D.size.strat, M = D.size.models;
      ciBars(host, A.preempt.map(x => String(x.bin)), [
        { label: 'decided before the cards loaded (all decisions)', color: C('--r-man'), pts: rateBars(A.preempt) },
        { label: 'card taken, once the cards were on screen', color: C('--s-strat'), pts: rateBars(A.tookSeen) }],
        { xLabel: 'drones the mission needs', yLabel: 'share of strategic decisions' });
      head(host, `Two steps of one strategic decision. Before the cards finish loading (~${num(D.speed.revealMean, 1)} s) the operator can already build by hand: `
        + `that falls with size (${orTxt(M.s_pre)} per doubling). Once the cards are on screen, taking one rises with size only weakly (${orTxt(M.s_seen)}). `
        + 'The 5-drone bar is seven particular missions; see the next section.');
    }),

    /* f-size-decides#strategic-steps: what is different about the 5-drone missions */
    'handover.fiveDrone': safe(host => {
      const F = P3().five;
      const box = sub(host);
      const SC = { 3: C('--mark-soft'), 5: C('--r-man'), 6: C('--s-strat') };
      const cats = F.per.map(x => `${x.nd}|${x.game}|${x.mission}`);
      const lab = c => { const x = F.per.find(z => `${z.nd}|${z.game}|${z.mission}` === c); return `${x.mission}\nmin ${num(x.minute, 0)}`; };
      const draw = k => {
        box.innerHTML = '';
        const pts = F.per.map(x => ({ cat: `${x.nd}|${x.game}|${x.mission}`, color: SC[x.nd],
          v: k === 'took' ? x.took : x.early, lo: k === 'took' ? x.lo : x.elo, hi: k === 'took' ? x.hi : x.ehi,
          tip: `${x.comp} · ${x.game.replace('strategic', 'Strategic Heavy').replace('tactical', 'Tactical Heavy')} game<br>n = ${x.n} decisions (one per person)`
            + `<br>arrived around minute ${num(x.minute, 1)}, ${num(x.queue, 1)} other missions waiting on average<br>median decision ${sec(x.secs)}` }));
        ciBars(box, cats, [{ label: k === 'took' ? 'card taken' : 'decided before the cards loaded', color: C('--mark'), pts }],
          { catLabel: lab, maxBar: 30, xLabel: 'each bar is one mission (all-Fast recce missions only), ordered by size then by arrival minute',
            yLabel: k === 'took' ? '% of decisions where\na strategy card was taken' : '% of decisions made\nbefore the cards loaded', padB: 64 });
      };
      btnBar(host, 'Show', [['took', 'card taken'], ['early', 'decided before cards loaded']], 'took', draw);
      host.appendChild(box);
      draw('took');
      legend(host, [{ label: '3 drones (T1+T2)', color: SC[3] }, { label: '5 drones (T1+T2+T2)', color: SC[5] }, { label: '6 drones (T1+T1+T2+T2)', color: SC[6] }]);
      const G = Object.fromEntries(F.groups.map(g => [g.nd, g])), Mo = F.models;
      head(host, `Each size is one composition and only a handful of missions (3 drones: ${G[3].missions}, 5: ${G[5].missions}, 6: ${G[6].missions}). `
        + `Missions of the same size range widely. Within person, with game and session held fixed, 5-drone missions are not distinguishable from 3-drone ones `
        + `(card ${orTxt(Mo.took.five_w)}) and 6-drone from 3-drone (${orTxt(Mo.took.six_w)}). Whiskers: 95% Wilson intervals.`);
      tableFor(host, ['Drones', 'Mission', 'Game', 'n', 'Card taken', 'Before cards', 'Minute', 'Waiting', 'Median s'],
        F.per.map(x => [x.nd, x.mission, x.game, x.n, `${p0(x.took)} [${p0(x.lo)}, ${p0(x.hi)}]`, p0(x.early), num(x.minute, 1), num(x.queue, 1), num(x.secs, 1)]));
    }),

    /* f-size-decides#models, with artefact checks folded in */
    'handover.sizeModels2': safe(host => {
      const M = D.size.models, X = P3().missionChecks;
      const find = (lst, lab) => (lst || []).find(r_ => r_.label === lab);
      const feNote = (t, n) => t ? `same model as the row it checks; interval clustered on person and on the ${t.missions} shared missions; ${n}` : '';
      ciStrip(host, [
        modelRow('Strategic · per doubling of drones needed', M.s_doubling, { main: true, color: C('--s-strat') }),
        modelRow('Strategic · per extra drone type', M.s_type, { color: C('--s-strat') }),
        modelRow('Strategic · per extra task', M.s_task, { color: C('--s-strat') }),
        modelRow('Strategic · cards on screen only, per doubling', M.s_seen, { color: C('--s-strat') }),
        modelRow('Tactical · per doubling of drones needed', M.t_doubling, { main: true, color: C('--s-tac'), head: true }),
        modelRow('Tactical · per doubling of plan size', M.t_doubling_plan, { color: C('--s-tac') }),
        modelRow('Tactical · per extra drone type', M.t_type, { color: C('--s-tac') }),
        modelRow('Tactical · per extra task', M.t_task, { color: C('--s-tac') }),
        modelRow('Both tiers · per doubling of drones needed', M.both_common, { main: true, head: true }),
        modelRow('Check · strategic, illogical card excluded', find(D.size.robustS, 'Illogical Conservative card excluded'), { color: C('--s-strat'), head: true,
          note: 'every decision whose Conservative card carried a type the mission did not need removed' }),
        modelRow('Check · strategic, missions shared across people', X.fe.s, { color: C('--s-strat'), note: feNote(X.fe.s, 'per doubling of drones needed') }),
        modelRow('Check · tactical, illogical-card missions excluded', find(D.size.robustT, 'Mission had an illogical Conservative card excluded'), { color: C('--s-tac'),
          note: 'per doubling of plan size' }),
        modelRow('Check · tactical, missions shared across people', X.fe.t, { color: C('--s-tac'), note: feNote(X.fe.t, 'per doubling of drones needed') })].filter(Boolean),
        { xLabel: 'odds ratio of handing over, each person compared with themselves (95% interval, log scale)' });
      const ml = X.missionLevel;
      head(host, `Checks (bottom block). "Missions shared across people": everyone played the same fixed missions, so a few odd missions could carry the effect; these rows `
        + `let the interval reflect that (clustered on mission as well as person); the estimate is unchanged and the interval stays clear of 1. With each mission as one point (missions with ≥ 5 decisions), `
        + `the share handed over rises with size: strategic ρ = ${num(ml.s.rho, 2)} over ${ml.s.missions} missions (${pval(ml.s.p)}), tactical ρ = ${num(ml.t.rho, 2)} over ${ml.t.missions} (${pval(ml.t.p)}).`);
    }),

    /* f-size-decides#tactical: five size measures, split by the strategic route */
    'handover.sizeTacMeasures': safe(host => {
      const TM = P3().tacMeasures;
      const box = sub(host);
      const XL = { needed: 'drones the mission needs', team: 'drones committed to the mission (the team)', tasks: 'tasks in the mission (residual missions left out)',
                   types: 'drone types the mission needs (two-type: 12 plans)', plan: 'plan size = drones committed × tasks' };
      const draw = k => {
        box.innerHTML = '';
        const R = TM[k];
        ciBars(box, R.bins, [
          { label: 'mission allocated from a strategy card', color: C('--s-strat'), pts: rateBars(R.card) },
          { label: 'mission allocated by hand', color: C('--r-man'), pts: rateBars(R.manual) }],
          { xLabel: XL[k], yLabel: '% of tactical plans\nwith Suggest pressed' });
        const sm_ = R.sameMissionDiff;
        head(box, `Size, within person: ${orTxt(R.size)} ${R.unit}. Card-allocated vs hand-allocated, size held: ${orTxt(R.route)}. `
          + `Does the gap narrow as size grows (route × size; below 1 = narrows)? ${orTxt(R.inter)}. `
          + (k === 'team' || k === 'plan'
            ? `This measure depends on the operator's own strategic choice: for the same mission, card allocations score ×${num(Math.pow(2, sm_.b), 2)} higher on it than hand allocations.`
            : 'This measure is fixed by the mission, the same whichever route the operator took.'));
      };
      btnBar(host, 'Size measured as', [['needed', 'drones needed'], ['team', 'drones committed'], ['tasks', 'tasks'], ['types', 'drone types'], ['plan', 'plan size']], 'needed', draw);
      host.appendChild(box);
      draw('needed');
      const L = TM.personLink;
      head(host, `Person level: people who take more strategy cards also press Suggest more (Spearman ρ = ${num(L.rho, 2)}, ${pval(L.p)}, ${L.k} people).`);
    }),

    /* f-size-decides#people, as bars with intervals */
    'handover.sizePeopleBars': safe(host => {
      const PB = P3().peopleBars;
      const box = sub(host);
      const draw = k => {
        box.innerHTML = '';
        const mk = rows => rows.map(x => ({ cat: x.bin, v: x[k].mean, lo: x[k].lo, hi: x[k].hi, tip: `${x.k} people with ≥ 2 decisions here (${x.n} decisions)` }));
        ciBars(box, PB.strat.rows.map(x => x.bin), [
          { label: 'Strategic: card taken', color: C('--s-strat'), pts: mk(PB.strat.rows) },
          { label: 'Tactical: Suggest pressed', color: C('--s-tac'), pts: mk(PB.tac.rows) }],
          { xLabel: 'drones the mission needs', yLabel: k === 'rel' ? '% handed over (mean of people),\neach person\'s own average removed' : '% handed over\n(mean of people\'s own rates)' });
      };
      btnBar(host, 'Each person', [['rel', 'compared with their own average'], ['raw', 'plain average of people']], 'rel', draw);
      host.appendChild(box);
      draw('rel');
      head(host, `Each person counts once per bar (people with at least 2 decisions in that band); whiskers resample people. `
        + `Biggest band above smallest: strategic ${PB.strat.up} people, below ${PB.strat.down}, equal ${PB.strat.same} (sign test ${pval(PB.strat.p)}); `
        + `tactical ${PB.tac.up}, ${PB.tac.down}, ${PB.tac.same} (${pval(PB.tac.p)}).`);
    }),

    /* f-size-decides#speed, as bars */
    'handover.speedSizeBars': safe(host => {
      const box = sub(host);
      const mb = rows => (rows || []).map(x => ({ cat: x.bin, v: x.med, lo: x.lo, hi: x.hi, tip: `n = ${x.n} decisions, ${x.k} people` }));
      const fs = v => num(v, 0) + ' s';
      const draw = k => {
        box.innerHTML = '';
        if (k === 's') {
          const S = D.speed.strat;
          ciBars(box, ['one type', 'three types, 6–9 drones', 'three types, 10–18 drones'], [
            { label: 'card taken', color: C('--s-strat'), pts: mb(S['card']) },
            { label: 'manual, after the cards loaded', color: C('--r-man'), pts: mb(S['manual after cards']) },
            { label: 'manual, before the cards loaded', color: C('--mark-soft'), pts: mb(S['pre-emptive manual']) }],
            { fmt: fs, ymin: 0, ymax: 30, yticks: [0, 5, 10, 15, 20, 25, 30], xLabel: 'mission size', yLabel: 'seconds, panel open → choice (median)' });
          const sp = P3().speedSpread['pre-emptive manual'];
          head(box, `Raw seconds the operator actually spent (the card's forced ~${num(D.speed.revealMean, 1)} s reveal included). Whiskers: 95% intervals of the median, people resampled. `
            + `The short whisker on "manual, before the cards loaded" for one-type missions is real: ${sp.n} decisions from ${sp.k} people, the middle half between ${num(sp.q1, 1)} and ${num(sp.q3, 1)} s.`);
        } else {
          const T = D.speed.tac, e = D.speed.tacBandEdges || [];
          ciBars(box, ['small', 'mid', 'large'], [
            { label: 'built by hand', color: C('--r-man'), pts: mb(T['hand']) },
            { label: 'Suggest, kept as is', color: C('--s-tac'), pts: mb(T['suggest-kept']) },
            { label: 'Suggest, then edited (few)', color: C('--mark-soft'), pts: mb(T['suggest-edited']), faint: true }],
            { fmt: fs, ymin: 0, ymax: 90, yticks: [0, 15, 30, 45, 60, 75, 90], yLabel: 'seconds, planner open → confirm (median)',
              xLabel: `plan size thirds (drones × tasks: small ≤ ${num(e[0], 0)}, large > ${num(e[1], 0)})` });
          head(box, 'Includes the 1-entry-per-second Suggest fill. Edited plans are few (18), so their whiskers are wide.');
        }
      };
      btnBar(host, 'Tier', [['s', 'Strategic'], ['t', 'Tactical']], 's', draw);
      host.appendChild(box);
      draw('s');
    }),

    /* f-size-decides#parallel: where a tactical plan's time goes */
    'handover.phases': safe(host => {
      const PH = P3().phases;
      const keys = [{ key: 'pre', label: 'before the first action', color: C('--mark-soft') },
                    { key: 'build', label: 'building the plan (drags, or the Suggest fill)', color: C('--s-tac') },
                    { key: 'hold', label: 'plan ready → confirmed', color: C('--warn') },
                    { key: 'carry', label: 'carrying out (confirm → mission complete)', color: C('--good') }];
      const box = sub(host);
      const RL = { hand: 'built by hand', 'suggest-kept': 'Suggest, kept as is' };
      const draw = band => {
        box.innerHTML = '';
        const rec = PH.phases[band] || {};
        const rows = ['hand', 'suggest-kept'].filter(k => rec[k]).map(k => ({ label: RL[k], sub: `n = ${rec[k].n} plans, ${rec[k].k} people`,
          vals: rec[k], tip: `n = ${rec[k].n} plans, ${rec[k].k} people` }));
        if (!rows.length) { h('p', { class: 'note', text: 'No plans in this band.' }, box); return; }
        stackAbs(box, rows, keys, { xLabel: 'seconds (mean), from the planner opening to the mission completing' });
        tableFor(box, ['Route', 'n', 'Before first action', 'Building', 'Ready → confirm', 'Carrying out', 'Total'],
          ['hand', 'suggest-kept', 'suggest-edited'].filter(k => rec[k]).map(k => [k, rec[k].n,
            ...['pre', 'build', 'hold', 'carry', 'total'].map(s_ => `${num(rec[k][s_].mean, 1)} [${num(rec[k][s_].lo, 1)}, ${num(rec[k][s_].hi, 1)}]`)]));
      };
      btnBar(host, 'Missions', [['all', 'all'], ['small', 'small (≤ 6 drones)'], ['mid', 'mid (7–9)'], ['large', 'large (10+)']], 'all', draw);
      host.appendChild(box);
      draw('all');
      const M = PH.models;
      h('p', { class: 'note', html: '<b>Suggest plan minus the same person\'s hand-built plans</b>, seconds per phase, drones needed held fixed (negative = Suggest quicker):' }, host);
      const d2 = sub(host);
      ciStrip(d2, [['pre', 'Before the first action'], ['build', 'Building the plan'], ['hold', 'Plan ready → confirmed'], ['carry', 'Carrying out'], ['total', 'Whole thing']]
        .map(([k, lab], i) => M[k] ? { label: lab, est: M[k].est, lo: M[k].lo, hi: M[k].hi, p: M[k].p, n: M[k].n, k: M[k].k, main: k === 'total',
          color: (keys.find(z => z.key === k) || {}).color || C('--mark'), head: k === 'total' } : null).filter(Boolean),
        { log: false, padL: 220, fmt: v => sgn(v, 0) + ' s', ticks: [-20, -10, 0], xLabel: 'seconds, Suggest minus hand-built (95% interval)' });
      const pj = PH.proj;
      head(host, `Only missions that finished in full with no drone failure can show "carrying out" (${PH.nClean} of ${PH.nPlans} plans; few edited Suggest plans survive, so they are left out). `
        + `A check that needs no finished mission: the scheduler's projected completion of the confirmed plan, minus the Tactical Assistant's own plan at the moment the planner opened — `
        + `median +${num(pj.hand.med, 1)} s for hand-built plans (${pj.hand.n}), +${num(pj['suggest-kept'].med, 1)} s for kept Suggest plans (${pj['suggest-kept'].n}).`);
    }),

    /* f-size-decides#slow, means with intervals only */
    'handover.c06Bars': safe(host => {
      const C6 = D.c06, CI = P3().c06ci;
      const F = { pct: v => v == null ? '—' : pct(v, 0), pp: v => v == null ? '—' : sgn(100 * v, 0) + ' pts', s: v => num(v, 1) + ' s', n: v => num(v, 1), z: v => v == null ? '—' : sgn(v, 2) };
      const rows = C6.rows.map(r_ => Object.assign({}, r_, CI.find(c => c.key === r_.key) || {}, { fmt: F[r_.unit] || (v => num(v, 2)) }));
      pairBars(host, rows, { groupLabel: 'said the assistant is slow (C06, 6 people)', color: C('--s-tac') });
      head(host, 'Bars are group means; whiskers are 95% intervals from resampling people within each group. p = two-sided permutation test. '
        + 'With six people, none of the ten differences is reliable (lowest p = .055, and about one p below .10 is expected by chance among ten).');
    }),

    /* f-practice#speed: speed-up within a session vs carry-over */
    'handover.learnCarry': safe(host => {
      const CA = P3().carry;
      const box = sub(host);
      const draw = k => {
        box.innerHTML = '';
        const B = CA[k].bars;
        const pts = part => B.filter(b => b.part === part).map(b => ({ cat: 'session ' + b.run, v: b.med, lo: b.lo, hi: b.hi, tip: `n = ${b.n} decisions, ${b.k} people` }));
        const ymax = k === 'strat' ? 16 : 35;
        ciBars(box, ['session 1', 'session 2'], [
          { label: 'minutes 1–2 of the session', color: C('--mark-soft'), pts: pts('start') },
          { label: 'minutes 7–8', color: k === 'strat' ? C('--s-strat') : C('--s-tac'), pts: pts('end') }],
          { fmt: v => num(v, 1) + ' s', tickFmt: v => num(v, 0) + ' s', ymin: 0, ymax, yticks: k === 'strat' ? [0, 4, 8, 12, 16] : [0, 5, 10, 15, 20, 25, 30, 35], maxBar: 70,
            xLabel: 'session (each bar: decisions made in those minutes of that session)',
            yLabel: k === 'strat' ? 'seconds per strategic decision (median),\nforced card load removed' : 'seconds per tactical plan (median),\nforced Suggest fill removed' });
        const M = CA[k].model;
        const pc = t => `${sgn(100 * t.pct, 0)}% [${sgn(100 * t.lo, 0)}, ${sgn(100 * t.hi, 0)}], ${pval(t.p)}`;
        head(box, `Model (person-clustered, game held fixed), relative to the start of session 1: end of session 1 ${pc(M.s1end)}; start of session 2 ${pc(M.s2start)}; `
          + `start of session 2 relative to the end of session 1 ${pc(M.s2start_vs_s1end)}. Within-session slope with the queue held fixed: ${pc(M.slopeQueueHeld)} per minute.`);
      };
      btnBar(host, 'Tier', [['strat', 'Strategic'], ['tac', 'Tactical']], 'strat', draw);
      host.appendChild(box);
      draw('strat');
    }),

    /* f-practice#c22, with each assistant's use added */
    'handover.c22b': safe(host => {
      const C2 = D.learn.c22, U = P3().c22use;
      const ppl = {};
      Object.entries(C2.people).forEach(([pid, v]) => { ppl[pid] = Object.assign({}, v, (U.people || {})[pid] || {}); });
      const mk = (key, lab, fmt, src) => Object.assign({ key, label: lab, fmt }, src);
      groupStrip(host, [mk('dZ', 'Score (SD within game)', v => sgn(v, 2), C2.dZ),
                        mk('dS', 'Strategic time (log seconds)', v => sgn(v, 2), C2.dS),
                        mk('dT', 'Tactical time (log seconds)', v => sgn(v, 2), C2.dT),
                        mk('dTook', 'Cards taken (% points)', v => sgn(100 * v, 0), U.took),
                        mk('dSug', 'Suggest pressed (% points)', v => sgn(100 * v, 0), U.sug)], ppl, C2.who,
        { groupLabel: 'said they got better (C22)', color: C('--good') });
      head(host, `Every row is a change from session 1 to session 2 (session 2 minus session 1); each dot is one person, each row has its own scale (ends labelled). `
        + `Times are medians of net seconds on a log scale: −0.1 ≈ 10% faster. Assistant use is each session's rate minus that game's average rate, so a change of game does not count as a change of habit. `
        + `Used more cards in session 2: C22 ${U.upTook.c22} of ${U.upTook.nC22}, others ${U.upTook.others} of ${U.upTook.nOthers}; pressed Suggest more: C22 ${U.upSug.c22}, others ${U.upSug.others}. `
        + `Across everyone, a bigger score gain does not go with a bigger rise in use (cards ρ = ${num(U.rho_took.rho, 2)}, ${pval(U.rho_took.p)}; Suggest ρ = ${num(U.rho_sug.rho, 2)}, ${pval(U.rho_sug.p)}).`);
    }),
  });
  /* ── pass 4 (the researcher's pass-3 notes) ─────────────────────────────────────────────── */
  const P4 = () => { if (!D.p4) throw new Error('pass-4 numbers missing: rerun handover.py'); return D.p4; };

  /* Grouped, vertically stacked columns in seconds. groups: [{id, label}] ('\n' = second line);
     bars: [{id, label}] drawn side by side inside each group; rec(g, b) -> {seg: {mean, lo, hi}, n, k} or null;
     keys: the segments to stack [{key, label, color}]; o.total: the key whose interval is the whisker on the
     whole bar (must equal the sum of the shown segments). Every segment has a hover with its mean, interval and n. */
  function stackCols(host, groups, bars, rec, keys, o = {}) {
    const H = o.height || 330, padL = 62, padR = 10, padT = 22, padB = 70;
    const s = svgRoot(host, W, H);
    const ymax = o.ymax || 100;
    const y = v => H - padB - (H - padB - padT) * (Math.max(0, Math.min(ymax, v)) / ymax);
    (o.yticks || [0, ymax / 2, ymax]).forEach(v => {
      el('line', { x1: padL, x2: W - padR, y1: y(v), y2: y(v), stroke: C('--grid') }, s);
      txt(s, { x: padL - 8, y: y(v) + 4, 'text-anchor': 'end', 'font-family': mono() }, num(v, 0));
    });
    const bandW = (W - padL - padR) / groups.length, nb = bars.length, gap = 5;
    const bw = Math.min(o.maxBar || 40, (bandW - 18 - gap * (nb - 1)) / nb);
    groups.forEach((g, gi) => {
      const cx = padL + bandW * (gi + 0.5), total = nb * bw + gap * (nb - 1);
      if (gi) el('line', { x1: padL + bandW * gi, x2: padL + bandW * gi, y1: padT, y2: H - padB + 52, stroke: C('--grid'), 'stroke-dasharray': '2 3' }, s);
      String(g.label).split('\n').forEach((ln, li) => txt(s, { x: cx, y: H - padB + 34 + li * 12, 'text-anchor': 'middle', 'font-size': li ? 9.5 : 11,
        fill: C('--ink-2'), 'font-weight': li ? 400 : 600 }, ln));
      bars.forEach((b, bi) => {
        const bx = cx - total / 2 + bi * (bw + gap), xm = bx + bw / 2;
        txt(s, { x: xm, y: H - padB + 14, 'text-anchor': 'middle', 'font-size': 9.5 }, b.label);
        const r_ = rec(g.id, b.id);
        if (!r_) { txt(s, { x: xm, y: H - padB - 6, 'text-anchor': 'middle', 'font-size': 9 }, 'n < 3'); return; }
        let acc = 0;
        keys.forEach(k => {
          const v = r_[k.key] || {}, m = Math.max(0, v.mean || 0);
          if (m <= 0) return;
          const y0 = y(acc), y1 = y(acc + m);
          el('rect', { x: bx, y: y1, width: bw, height: Math.max(0.5, y0 - y1 - 1), fill: k.color, rx: 2 }, s);
          if (y0 - y1 > 14 && bw >= 22) txt(s, { x: xm, y: (y0 + y1) / 2 + 4, 'text-anchor': 'middle', 'font-size': 9.5, 'font-family': mono(), fill: '#fff' }, num(m, 0));
          const hit = el('rect', { x: bx, y: y1, width: bw, height: Math.max(1, y0 - y1), fill: 'transparent' }, s);
          hoverable(hit, `<b>${k.label}</b><br>${g.label.replace('\n', ' ')} · ${b.label}: ${sec(v.mean)} [${sec(v.lo)}, ${sec(v.hi)}] (mean, 95% interval)`
            + `<br>n = ${r_.n} ${o.unit || 'plans'}, ${r_.k} people`);
          acc += m;
        });
        const T_ = o.total ? r_[o.total] : null;
        if (T_ && T_.lo != null && T_.hi != null) {
          el('line', { x1: xm, x2: xm, y1: y(T_.lo), y2: y(T_.hi), stroke: C('--ink-2'), 'stroke-width': 1.3 }, s);
          [T_.lo, T_.hi].forEach(v => el('line', { x1: xm - 3.5, x2: xm + 3.5, y1: y(v), y2: y(v), stroke: C('--ink-2'), 'stroke-width': 1.3 }, s));
        }
        const top = Math.min(y(acc), T_ && T_.hi != null ? y(T_.hi) : y(acc));
        txt(s, { x: xm, y: Math.max(padT - 6, top - 5), 'text-anchor': 'middle', 'font-size': 9.5, 'font-family': mono(), fill: C('--ink-2') }, num(acc, 0));
      });
    });
    el('line', { x1: padL, x2: W - padR, y1: H - padB, y2: H - padB, stroke: C('--line') }, s);
    txt(s, { x: (padL + W - padR) / 2, y: H - 4, 'text-anchor': 'middle' }, o.xLabel || '');
    yTitle(s, o.yLabel, (padT + H - padB) / 2);
    legend(host, keys.map(k => ({ label: k.label, color: k.color })));
  }
  /* Candidate ticks kept only where the strip's estimates reach (ciStrip draws every tick it is given). */
  const fitTicks = (rows, cands) => {
    const lo = Math.min(0, ...rows.map(x => x.lo)), hi = Math.max(0, ...rows.map(x => x.hi));
    return cands.filter(v => v >= lo && v <= hi);
  };
  const pctRow = (label, t, extra = {}) => t ? Object.assign({ label, est: t.est, lo: t.lo, hi: t.hi, p: t.p }, extra) : null;
  const secRow = (label, t, extra = {}) => t ? Object.assign({ label, est: t.est, lo: t.lo, hi: t.hi, p: t.p, n: t.n, k: t.k }, extra) : null;

  Object.assign(CH, {
    /* f-size-decides#speed (pass 4): stacked by size, with the time before the first action separated out */
    'handover.speedPhases': safe(host => {
      const SP = P4().stratPhases, TP = P4().tacPhases;
      const bar = h('div', {}, host);
      const box = sub(host);
      let tier = 's', show = 'all';
      const draw = () => {
        box.innerHTML = '';
        if (tier === 's') {
          const all = [{ key: 'load', label: 'no action yet: cards still loading (≈ 4.7 s forced wait)', color: C('--ink-3') },
                       { key: 'idle', label: 'no action yet: cards on screen', color: C('--mark-soft') },
                       { key: 'act', label: 'first click → choice', color: C('--s-strat') }];
          const keys = show === 'all' ? all : show === 'noidle' ? [all[0], all[2]] : [all[2]];
          const tot = show === 'all' ? 'tot' : show === 'noidle' ? 'noidle' : 'act';
          stackCols(box, [{ id: 'one type', label: 'one drone type\n3–6 drones' }, { id: 'three types, 6–9 drones', label: 'three types\n6–9 drones' },
                          { id: 'three types, 10–18 drones', label: 'three types\n10–18 drones' }],
            [{ id: 'card', label: 'card' }, { id: 'manual after cards', label: 'by hand' }, { id: 'pre-emptive manual', label: 'hand, early' }],
            (g, b) => (SP.phases[g] || {})[b] || null, keys,
            { total: tot, ymax: 35, yticks: [0, 10, 20, 30], unit: 'decisions', yLabel: 'seconds per strategic decision (mean),\npanel opened → choice',
              xLabel: '"card" = strategy card taken; "by hand" = built by hand after the cards loaded; "hand, early" = before they loaded' });
          const M = SP.models, f = v => sgn(100 * v, 0) + '%';
          h('p', { class: 'note', html: '<b>Card minus the same person\'s manual decisions</b>, % change in time (negative = card quicker), under each way of counting:' }, box);
          const rows = [
            pctRow('One type · everything', M.all.one, { color: C('--ink-3') }), pctRow('One type · without idle time', M.noIdle.one, { color: C('--mark-soft') }),
            pctRow('One type · from first click only', M.active.one, { color: C('--s-strat') }),
            pctRow('Three types · everything', M.all.three, { color: C('--ink-3'), head: true }), pctRow('Three types · without idle time', M.noIdle.three, { color: C('--mark-soft') }),
            pctRow('Three types · from first click only', M.active.three, { color: C('--s-strat') })].filter(Boolean);
          ciStrip(sub(box), rows, { log: false, padL: 250, fmt: f, ticks: fitTicks(rows, [-0.75, -0.5, -0.25, 0, 0.25, 0.5]),
            xLabel: '% change in seconds, card vs manual, same person (95% interval)' });
        } else {
          const all = [{ key: 'pre', label: 'no action yet (planner open, nothing pressed or dragged)', color: C('--mark-soft') },
                       { key: 'build', label: 'building the plan (drags, or the Suggest fill)', color: C('--s-tac') },
                       { key: 'hold', label: 'plan ready → confirmed', color: C('--warn') }];
          const keys = show === 'all' ? all : all.slice(1);
          stackCols(box, [{ id: 'small', label: 'small\n≤ 6 drones needed' }, { id: 'mid', label: 'mid\n7–9 drones' }, { id: 'large', label: 'large\n10+ drones' },
                          { id: 'all', label: 'all plans\n(raw mix)' }],
            [{ id: 'hand', label: 'by hand' }, { id: 'suggest-kept', label: 'Suggest' }],
            (g, b) => (TP.phases[g] || {})[b] || null, keys,
            { total: show === 'all' ? 'tot' : 'plan', ymax: 70, yticks: [0, 20, 40, 60], yLabel: 'seconds per tactical plan (mean),\nplanner opened → confirmed',
              xLabel: '"Suggest" = Suggest pressed and the plan kept as filled (18 edited Suggest plans left out)' });
          const M = TP.models;
          h('p', { class: 'note', html: '<b>Suggest minus the same person\'s hand-built plans</b>, seconds, drones needed held fixed:' }, box);
          const rows = [secRow('Everything (open → confirm)', M.tot, { color: C('--ink-3') }),
                        secRow('Without time before the first action', M.plan, { color: C('--s-tac') })].filter(Boolean);
          ciStrip(sub(box), rows, { log: false, padL: 250, fmt: v => sgn(v, 0) + ' s', ticks: fitTicks(rows, [-10, -5, 0, 5]),
            xLabel: 'seconds, Suggest minus by hand, same person (95% interval)' });
        }
      };
      btnBar(bar, 'Tier', [['s', 'Strategic'], ['t', 'Tactical']], 's', k => { tier = k; draw(); });
      btnBar(bar, 'Time counted:', [['all', 'everything'], ['noidle', 'without idle time'], ['active', 'from the first click only']], 'all', k => { show = k; draw(); });
      draw();
      const po = TP.preOther.all;
      head(host, `<b>First action</b> = the operator's first click on this decision: a card highlighted or a manual count changed (strategic), Suggest pressed or a drone dragged (tactical). `
        + `<b>Idle time</b> = panel open but no action yet, once the cards are on screen (strategic) or from the planner opening (tactical). "From the first click only" also drops the strategic 4.7 s card load; `
        + `on the tactical tier the two are the same view. Idle time mixes reading the cards or plan with being busy elsewhere; the log cannot separate them, but for tactical plans idle for over 10 s, `
        + `${pct(po.shareLong, 0)} had another mission's strategic panel opened in the meantime (${po.nLong} plans). Whiskers: 95% intervals of the total, people resampled.`);
    }),

    /* f-size-decides#parallel (pass 4): every size group's stacked bars in one chart, plus a size-standardised 'all' */
    'handover.phases2': safe(host => {
      const PH = P3().phases, SM = P4().simpson;
      const keys0 = [{ key: 'pre', label: 'no action yet (planner open, nothing pressed or dragged)', color: C('--mark-soft') },
                     { key: 'build', label: 'building the plan (drags, or the Suggest fill)', color: C('--s-tac') },
                     { key: 'hold', label: 'plan ready → confirmed', color: C('--warn') },
                     { key: 'carry', label: 'carrying out (confirm → mission complete)', color: C('--good') }];
      const rec = (g, b) => {
        let r_;
        if (g === 'std') r_ = SM.std[b];
        else {
          r_ = (PH.phases[g] || {})[b];
          if (!r_) return null;
          const np = g === 'all' ? (SM.raw[b] || {}).noPre : (SM.bandNoPre[g] || {})[b];
          r_ = Object.assign({}, r_, { noPre: np || null });
        }
        return r_;
      };
      const bar = h('div', {}, host);
      const box = sub(host);
      const draw = show => {
        box.innerHTML = '';
        stackCols(box, [{ id: 'small', label: 'small\n≤ 6 drones needed' }, { id: 'mid', label: 'mid\n7–9 drones' }, { id: 'large', label: 'large\n10+ drones' },
                        { id: 'all', label: 'all missions\nraw mix' }, { id: 'std', label: 'all missions\nsize-standardised' }],
          [{ id: 'hand', label: 'by hand' }, { id: 'suggest-kept', label: 'Suggest' }], rec, show === 'all' ? keys0 : keys0.slice(1),
          { total: show === 'all' ? 'total' : 'noPre', ymax: 200, yticks: [0, 50, 100, 150, 200], height: 350,
            yLabel: 'seconds per plan (mean),\nplanner opened → mission complete', xLabel: 'finished missions only (no drone failure); "Suggest" = Suggest pressed, plan kept as filled' });
      };
      btnBar(bar, 'Time counted:', [['all', 'all four phases'], ['nopre', 'without time before the first action (grey)']], 'all', draw);
      draw('all');
      const M = PH.models;
      h('p', { class: 'note', html: '<b>Suggest plan minus the same person\'s hand-built plans</b>, seconds per phase (negative = Suggest quicker). All rows but the last hold drones needed fixed:' }, host);
      const rows = [['pre', 'Before the first action'], ['build', 'Building the plan'], ['hold', 'Plan ready → confirmed'], ['carry', 'Carrying out']]
        .map(([k, lab]) => M[k] ? secRow(lab, M[k], { color: (keys0.find(z => z.key === k) || {}).color }) : null)
        .concat([secRow('Whole thing', M.total, { main: true, head: true, color: C('--ink-2') }),
                 secRow('Whole thing, without before the first action', SM.noPre, { main: true, color: C('--s-tac') }),
                 secRow('Whole thing, size NOT held (the raw-mix comparison)', SM.noSize, { color: C('--mark-soft'), head: true })]).filter(Boolean);
      ciStrip(sub(host), rows, { log: false, padL: 300, fmt: v => sgn(v, 0) + ' s', ticks: fitTicks(rows, [-20, -10, 0, 10]),
        xLabel: 'seconds, Suggest minus by hand, same person (95% interval)' });
      const mx = SM.mix, w = SM.weights;
      head(host, `<b>Why "all missions" reverses the order.</b> Suggest is quicker within every size group, yet slower in the raw "all" bars, because the two routes are used on different missions: `
        + `${pct(mx.hand.small.share, 0)} of the finished hand-built plans are small, against ${pct(mx['suggest-kept'].small.share, 0)} of Suggest plans `
        + `(${pct(mx['suggest-kept'].large.share, 0)} of Suggest plans are large, ${pct(mx.hand.large.share, 0)} of hand-built). Small missions are quick whichever way, so the hand-built average is pulled down by its mix. `
        + `The size-standardised bars give both routes the same mix (small ${pct(w.small, 0)}, mid ${pct(w.mid, 0)}, large ${pct(w.large, 0)}, the pooled shares): `
        + `${num(SM.std.hand.total.mean, 0)} s by hand vs ${num(SM.std['suggest-kept'].total.mean, 0)} s with Suggest. Only ${SM.largeHand.n} large hand-built plans finished cleanly (${SM.largeHand.k} people), so the hand-built large and standardised bars are the least certain. `
        + `"Without time before the first action" removes the grey segment; the within-person saving shrinks a little (${sgn(M.total.est, 0)} s → ${sgn(SM.noPre.est, 0)} s) and stays clear of zero.`);
    }),
  });
})();
