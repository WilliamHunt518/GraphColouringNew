/* Pass 2 · AREA `style` — "Who the operator is". Data: DATA.pass2.style (scripts/register/pass2/style.py).
   Every chart draws into `host`; missing data -> a short note, never a throw. */
(() => {
  const D = (DATA.pass2 || {}).style;
  const FONT = 11;
  const safe = fn => (host, ...a) => {
    try {
      if (!D) throw new Error('no data');
      fn(host, ...a);
    } catch (e) {
      host.innerHTML = '';
      h('p', { class: 'cap', text: 'Chart unavailable (' + e.message + ') — rerun scripts/register/pass2/style.py and rebuild.' }, host);
    }
  };
  const txt = (s, x, y, t, o = {}) => {
    const n = el('text', Object.assign({ x, y, fill: css(o.ink || '--ink-2'), 'font-size': o.size || FONT,
      'text-anchor': o.anchor || 'start' }, o.mono ? { 'font-family': css('--mono') } : {}, o.weight ? { 'font-weight': o.weight } : {},
      o.rot ? { transform: `rotate(${o.rot} ${x} ${y})` } : {}), s);
    n.textContent = t;
    return n;
  };
  const rhoS = R => R && R.rho != null ? `ρ = ${num(R.rho, 2)}` : '';
  const rho = (R, lab = 'ρ') => R && R.rho != null ? `${lab} = ${num(R.rho, 2)} [${num(R.lo, 2)}, ${num(R.hi, 2)}], ${pval(R.p)}, n = ${R.n}` : '—';
  const cap = (host, html) => h('p', { class: 'cap', html }, host);

  /* scatter panel inside an existing svg. box = {x, y, w, h}; pts = [{x, y, tip, r, ring, fill}] */
  function scatterPanel(s, box, pts, o) {
    const { x: X0, y: Y0, w: W, h: H } = box;
    const xmin = o.xmin, xmax = o.xmax, ymin = o.ymin, ymax = o.ymax;
    const sx = v => X0 + W * (v - xmin) / (xmax - xmin), sy = v => Y0 + H - H * (v - ymin) / (ymax - ymin);
    el('rect', { x: X0, y: Y0, width: W, height: H, fill: 'none', stroke: css('--line') }, s);
    (o.xticks || []).forEach(v => {
      el('line', { x1: sx(v), x2: sx(v), y1: Y0, y2: Y0 + H, stroke: css(v === 0 && o.zeroLines ? '--ink-3' : '--grid'), 'stroke-dasharray': v === 0 && o.zeroLines ? '3 3' : null }, s);
      txt(s, sx(v), Y0 + H + 13, o.fx ? o.fx(v) : num(v, 1), { anchor: 'middle', ink: '--ink-3', mono: true, size: 10 });
    });
    (o.yticks || []).forEach(v => {
      el('line', { x1: X0, x2: X0 + W, y1: sy(v), y2: sy(v), stroke: css(v === 0 && o.zeroLines ? '--ink-3' : '--grid'), 'stroke-dasharray': v === 0 && o.zeroLines ? '3 3' : null }, s);
      txt(s, X0 - 5, sy(v) + 3.5, o.fy ? o.fy(v) : num(v, 1), { anchor: 'end', ink: '--ink-3', mono: true, size: 10 });
    });
    if (o.diag) el('line', { x1: sx(Math.max(xmin, ymin)), y1: sy(Math.max(xmin, ymin)), x2: sx(Math.min(xmax, ymax)), y2: sy(Math.min(xmax, ymax)),
      stroke: css('--ink-3'), 'stroke-dasharray': '4 3' }, s);
    if (o.fit && pts.length > 2) {          // least-squares guide line (visual only; the statistic is Spearman)
      const mx = pts.reduce((a, p) => a + p.x, 0) / pts.length, my = pts.reduce((a, p) => a + p.y, 0) / pts.length;
      const sxy = pts.reduce((a, p) => a + (p.x - mx) * (p.y - my), 0), sxx = pts.reduce((a, p) => a + (p.x - mx) ** 2, 0);
      const b = sxx ? sxy / sxx : 0, f = v => my + b * (v - mx);
      const clip = v => Math.max(ymin, Math.min(ymax, v));
      el('line', { x1: sx(xmin), y1: sy(clip(f(xmin))), x2: sx(xmax), y2: sy(clip(f(xmax))), stroke: css(o.fitColor || '--ink-3'), 'stroke-width': 2, opacity: .7 }, s);
    }
    const cl = (v, a, b) => Math.max(a, Math.min(b, v));
    pts.forEach(p => {
      const c = el('circle', { cx: sx(cl(p.x, xmin, xmax)), cy: sy(cl(p.y, ymin, ymax)), r: p.r || 5, fill: p.fill || css('--mark'),
        'fill-opacity': p.op != null ? p.op : .8, stroke: p.ring ? css('--bad') : css('--surface'), 'stroke-width': p.ring ? 2.5 : 1.5 }, s);
      if (p.tip) hoverable(c, p.tip);
    });
    if (o.title) txt(s, X0, Y0 - 8, o.title, { ink: '--ink', weight: 600, size: 12 });
    if (o.sub) txt(s, X0 + W, Y0 - 8, o.sub, { anchor: 'end', ink: '--ink-3', size: 10.5 });
    if (o.xlab) txt(s, X0 + W / 2, Y0 + H + 28, o.xlab, { anchor: 'middle', ink: '--ink-2', size: 11 });
    if (o.ylab) txt(s, X0 - 34, Y0 + H / 2, o.ylab, { anchor: 'middle', ink: '--ink-2', size: 11, rot: -90 });
    return { sx, sy };
  }

  /* dot + whisker rows on one scale; rows = [{label, est, lo, hi, strong, right, tip, color}] or {head} */
  function ciRows(host, rows, o) {
    const W = 700, rowH = 26, padL = o.padL || 260, padR = o.padR || 80, padT = 8;
    const H = padT + rows.length * rowH + 34, s = svgRoot(host, W, H);
    const tr = o.log ? Math.log : (v => v);
    const x = v => padL + (W - padL - padR) * (tr(v) - tr(o.min)) / (tr(o.max) - tr(o.min));
    const base = padT + rows.length * rowH;
    (o.ticks || []).forEach(v => {
      el('line', { x1: x(v), x2: x(v), y1: padT - 4, y2: base, stroke: css(v === o.ref ? '--ink-3' : '--grid'), 'stroke-dasharray': v === o.ref ? '3 3' : null }, s);
      txt(s, x(v), base + 14, o.fmt(v), { anchor: 'middle', ink: '--ink-3', mono: true, size: 10.5 });
    });
    if (o.xlab) txt(s, padL + (W - padL - padR) / 2, base + 29, o.xlab, { anchor: 'middle', size: 11 });
    rows.forEach((r_, i) => {
      const y = padT + i * rowH + rowH / 2;
      if (r_.head) { txt(s, 8, y + 4, r_.head, { ink: '--ink', weight: 600, size: 12 }); return; }
      const col = r_.color || css(r_.strong ? '--mark' : '--mark-soft');
      txt(s, padL - 10, y + 4, r_.label, { anchor: 'end', size: 12 });
      if (r_.lo != null) el('line', { x1: x(Math.max(o.min, r_.lo)), x2: x(Math.min(o.max, r_.hi)), y1: y, y2: y, stroke: col, 'stroke-width': 2, 'stroke-linecap': 'round' }, s);
      el('circle', { cx: x(Math.max(o.min, Math.min(o.max, r_.est))), cy: y, r: 5, fill: col, stroke: css('--surface'), 'stroke-width': 2 }, s);
      if (r_.right) txt(s, W - padR + 8, y + 4, r_.right, { ink: '--ink-3', mono: true, size: 10.5 });
      hoverable(el('rect', { x: padL, y: y - rowH / 2, width: W - padL - padR, height: rowH, fill: 'transparent' }, s), r_.tip || r_.label);
    });
  }

  const F = () => D.fingerprint;
  const pidsOf = () => F().pids;

  Object.assign(CH, {
    /* 1 · the 33 x 33 similarity-rank matrix: row = a session-1 profile, column = a session-2 profile */
    'style.fingerprintMatrix': safe(host => {
      const FP = F(), n = FP.n, ord = FP.order, P = FP.pids, box = h('div', {}, host);
      const draw = key => {
        const RK = FP[key].rankMatrix, padL = 44, padT = 44, cell = (700 - padL - 12) / n, W = 700, H = padT + n * cell + 34;
        const s = svgRoot(box, W, H);
        txt(s, padL + n * cell / 2, 14, 'Session 2 profile of … (same people, same order) →', { anchor: 'middle', size: 11 });
        txt(s, 12, padT + n * cell / 2, '↓ Session 1 profile of …', { anchor: 'middle', size: 11, rot: -90 });
        ord.forEach((i, a) => {
          txt(s, padL - 4, padT + a * cell + cell * .7, P[i], { anchor: 'end', size: 8, ink: '--ink-3', mono: true });
          txt(s, padL + a * cell + cell * .5, padT - 4, P[i].replace('P', ''), { anchor: 'middle', size: 7.5, ink: '--ink-3', mono: true });
          ord.forEach((j, b) => {
            const k = RK[i][j], op = Math.pow((n - k) / (n - 1), 3);
            const rc = el('rect', { x: padL + b * cell + .5, y: padT + a * cell + .5, width: cell - 1, height: cell - 1,
              fill: css('--mark'), 'fill-opacity': Math.max(op, .03), rx: 1.5 }, s);
            if (i === j) el('rect', { x: padL + b * cell + .5, y: padT + a * cell + .5, width: cell - 1, height: cell - 1, fill: 'none',
              stroke: css('--bad'), 'stroke-width': 2, rx: 1.5 }, s);
            hoverable(rc, `<b>${P[i]} session 1 vs ${P[j]} session 2</b><br>${P[j]} ranks <b>${k}</b> of ${n} for closeness to ${P[i]}’s session-1 habits`
              + (i === j ? '<br><i>same person</i>' : ''));
          });
        });
        // legend strip
        const ly = padT + n * cell + 14;
        [1, 2, 3, 5, 10, 20, 33].forEach((k, q) => {
          el('rect', { x: padL + q * 52, y: ly, width: 14, height: 12, rx: 2, fill: css('--mark'), 'fill-opacity': Math.max(Math.pow((n - k) / (n - 1), 3), .03), stroke: css('--line') }, s);
          txt(s, padL + q * 52 + 18, ly + 10, k === 1 ? '1st' : k === 33 ? '33rd' : '#' + k, { size: 10, ink: '--ink-3' });
        });
        el('rect', { x: padL + 7 * 52 + 10, y: ly, width: 14, height: 12, rx: 2, fill: 'none', stroke: css('--bad'), 'stroke-width': 2 }, s);
        txt(s, padL + 7 * 52 + 28, ly + 10, 'same person (diagonal)', { size: 10, ink: '--ink-3' });
        const R = FP[key];
        cap(box, `Darker = closer. Each row is ranked separately (1st = the closest session-2 profile to that person’s session 1). `
          + `People are ordered by how much they rely on the assistants, so neighbours rely alike and the band near the diagonal is expected; `
          + `the point is that the outlined own-session cells are darker still. Own session ranked 1st: <b>${R.hitsAB} of ${n}</b> rows `
          + `(${R.hitsBA} of ${n} columns), in the top 3: <b>${pct(R.top3, 0)}</b> (chance ${pct(3 / n, 0)}); mean rank <b>${num(R.meanRank, 1)}</b> vs ${num(R.nullRank, 1)} by chance, ${pval(R.pRank)}.`);
      };
      host.insertBefore(btnBar(host, 'Habits', [['all', 'All ten'], ['beyond', 'Reliance axis removed']], 'all', k => { box.innerHTML = ''; draw(k); }), box);
      draw('all');
    }),

    /* 2 · where each person's own other session ranks, against what chance gives */
    'style.fingerprintRanks': safe(host => {
      const FP = F(), n = FP.n, box = h('div', {}, host);
      const bins = [['1st', 1, 1], ['2nd', 2, 2], ['3rd', 3, 3], ['4–5th', 4, 5], ['6–10th', 6, 10], ['11–20th', 11, 20], ['21–33rd', 21, 33]];
      const draw = key => {
        box.innerHTML = '';
        const R = FP[key], rk = R.ranksAB.concat(R.ranksBA), N = rk.length;
        const obs = bins.map(([, a, b]) => rk.filter(v => v >= a && v <= b).length);
        const exp = bins.map(([, a, b]) => N * (b - a + 1) / n);
        const W = 700, H = 230, padL = 46, padB = 44, padT = 16, s = svgRoot(box, W, H);
        const mx = Math.max(...obs, ...exp) * 1.15, bw = (W - padL - 10) / bins.length;
        const y = v => H - padB - (H - padB - padT) * v / mx;
        [0, 5, 10, 15, 20, 25].filter(v => v < mx).forEach(v => {
          el('line', { x1: padL, x2: W - 10, y1: y(v), y2: y(v), stroke: css('--grid') }, s);
          txt(s, padL - 6, y(v) + 4, String(v), { anchor: 'end', ink: '--ink-3', mono: true, size: 10 });
        });
        bins.forEach(([lab], i) => {
          const x0 = padL + i * bw + bw * .2, w = bw * .6;
          const r_ = el('rect', { x: x0, y: y(obs[i]), width: w, height: Math.max(0, y(0) - y(obs[i])), rx: 4, fill: css(i < 3 ? '--s-strat' : '--mark-soft') }, s);
          el('line', { x1: x0 - 6, x2: x0 + w + 6, y1: y(exp[i]), y2: y(exp[i]), stroke: css('--ink'), 'stroke-width': 2, 'stroke-dasharray': '5 3' }, s);
          txt(s, x0 + w / 2, y(obs[i]) - 5, String(obs[i]), { anchor: 'middle', mono: true, size: 11 });
          txt(s, x0 + w / 2, H - padB + 16, lab, { anchor: 'middle', size: 11 });
          hoverable(r_, `<b>Own other session ranked ${lab}</b><br>${obs[i]} of ${N} look-ups (33 people × 2 directions)<br>chance would give ${num(exp[i], 1)}`);
        });
        txt(s, padL + (W - padL) / 2, H - 8, 'Where a person’s own other session ranks among all 33, by closeness of habits', { anchor: 'middle', size: 11 });
        txt(s, 12, padT + (H - padB - padT) / 2, 'number of look-ups (of 66)', { anchor: 'middle', rot: -90, size: 11 });
        cap(box, `Bars: observed (66 look-ups: each person’s session 1 searching the 33 session-2 profiles, and the reverse). Dashed line: what chance gives (every rank equally likely). `
          + `Top-3 share ${pct(R.top3, 0)} vs ${pct(3 / n, 0)} by chance; own session nearest ${R.hitsAB} + ${R.hitsBA} times vs 2 expected (permutation ${pval(R.pHit)}).`);
      };
      host.insertBefore(btnBar(host, 'Habits', [['all', 'All ten'], ['beyond', 'Reliance axis removed'], ['relianceOnly', 'Reliance axis only']], 'all', draw), box);
      draw('all');
    }),

    /* 3 · each person's ten-habit profile, session 1 vs session 2, as small multiples */
    'style.profilePairs': safe(host => {
      const FP = F(), PR = FP.profileR, cols = FP.short, k = cols.length;
      const people = FP.profiles.map((p, i) => Object.assign({ r: PR.own[i], other: PR.otherMean[i] }, p)).sort((a, b) => b.r - a.r);
      const nc = 6, pw = 700 / nc, ph = 78, rows = Math.ceil(people.length / nc), W = 700, H = rows * ph + 30;
      const s = svgRoot(host, W, H), lim = 2.5;
      people.forEach((p, i) => {
        const cx = (i % nc) * pw, cy = Math.floor(i / nc) * ph, ix = cx + 8, iw = pw - 16, iy = cy + 18, ih = ph - 26;
        const xs = j => ix + iw * j / (k - 1), ys = v => iy + ih / 2 - (ih / 2) * Math.max(-lim, Math.min(lim, v)) / lim;
        el('rect', { x: ix, y: iy, width: iw, height: ih, fill: css('--surface-2'), rx: 3 }, s);
        el('line', { x1: ix, x2: ix + iw, y1: ys(0), y2: ys(0), stroke: css('--line') }, s);
        [['s1', '--lad-3'], ['s2', '--lad-1']].forEach(([key, c]) => {
          el('polyline', { points: p[key].map((v, j) => `${xs(j)},${ys(v)}`).join(' '), fill: 'none', stroke: css(c), 'stroke-width': 1.8, 'stroke-linejoin': 'round' }, s);
        });
        txt(s, ix, cy + 13, p.pid, { size: 10.5, ink: '--ink', weight: 600, mono: true });
        txt(s, ix + iw, cy + 13, `r ${num(p.r, 2)} · #${p.rank}`, { anchor: 'end', size: 9.5, ink: '--ink-3', mono: true });
        const hit = el('rect', { x: cx, y: cy, width: pw, height: ph, fill: 'transparent' }, s);
        hoverable(hit, `<b>${p.pid}</b><br>profile correlation with own other session r = ${num(p.r, 2)}; with other people’s, on average r = ${num(p.other, 2)}<br>`
          + `own session-2 ranks ${p.rank} of ${FP.n} (all habits), ${p.rankBeyond} with the reliance axis removed<br>`
          + cols.map((c, j) => `${c}: ${sgn(p.s1[j], 1)} → ${sgn(p.s2[j], 1)}`).join('<br>'));
      });
      legend(host, [{ label: 'Session 1', color: css('--lad-3') }, { label: 'Session 2', color: css('--lad-1') }]);
      cap(host, `Each panel is one person. Left to right, the ten habits (${cols.join(', ')}), each as a z-score against everyone who played the same game (0 = typical; lines clipped at ±2.5). `
        + `Sorted by how closely the two sessions match (r = correlation of the two profiles; #k = rank of own session among 33). Median r with own other session <b>${num(PR.ownMedian, 2)}</b>, with someone else’s <b>${num(PR.otherMedian, 2)}</b>; `
        + `own session closer than the average stranger for <b>${PR.beat} of ${FP.n}</b> people (sign test ${pval(PR.pSign)}).`);
    }),

    /* 4 · habit by habit: session 1 (x) vs session 2 (y), one small scatter per habit */
    'style.retestGrid': safe(host => {
      const FP = F(), RT = FP.retest, order = RT.map((r_, j) => j).sort((a, b) => RT[b].rho - RT[a].rho);
      const nc = 5, pw = 140, ph = 150, W = 700, H = 2 * ph + 34, s = svgRoot(host, W, H);
      order.forEach((j, q) => {
        const r_ = RT[j], cx = (q % nc) * pw, cy = Math.floor(q / nc) * ph;
        const pts = FP.profiles.map(p => ({ x: p.s1[j], y: p.s2[j], r: 3, op: .7,
          fill: css(r_.tier === 'tactical' ? '--s-tac' : '--s-strat'), tip: `<b>${p.pid}</b> · ${r_.label}<br>session 1 ${sgn(p.s1[j], 2)}, session 2 ${sgn(p.s2[j], 2)} (z within game)` }));
        scatterPanel(s, { x: cx + 26, y: cy + 34, w: pw - 34, h: ph - 62 }, pts, { xmin: -3, xmax: 3, ymin: -3, ymax: 3, xticks: [-2, 0, 2], yticks: [-2, 0, 2],
          fx: v => String(v), fy: v => String(v), diag: true });
          txt(s, cx + 4, cy + 12, FP.short[j], { ink: r_.pHolm < .05 ? '--ink' : '--ink-3', weight: 600, size: 11 });
        txt(s, cx + 4, cy + 25, `ρ ${num(r_.rho, 2)} [${num(r_.lo, 2)}, ${num(r_.hi, 2)}]${r_.pHolm < .05 ? '' : ' ns'}`, { size: 9.5, ink: '--ink-3', mono: true });
      });
      txt(s, W / 2, H - 4, 'x = the habit in session 1, y = the same habit in session 2 (each as z within game); dashed = identical', { anchor: 'middle', size: 11 });
      legend(host, [{ label: 'Strategic-tier habit', color: css('--s-strat') }, { label: 'Tactical-tier habit', color: css('--s-tac') }]);
      tableFor(host, ['Habit', 'ρ session 1 vs 2', '95% CI', 'Holm p', 'Distinct levels, 1 session', '2 sessions'],
        order.map(j => { const r_ = RT[j]; return [r_.label, num(r_.rho, 2), `${num(r_.lo, 2)} to ${num(r_.hi, 2)}`, pval(r_.pHolm), num(r_.strata1, 1), num(r_.strata2, 1)]; }));
    }),

    /* 4b · the same ρ's as one ranked dot plot */
    'style.retestDots': safe(host => {
      const RT = F().retest.slice().sort((a, b) => b.rho - a.rho);
      ciRows(host, RT.map(r_ => ({ label: r_.label, est: r_.rho, lo: r_.lo, hi: r_.hi, strong: r_.pHolm < .05,
        color: r_.pHolm < .05 ? css(r_.tier === 'tactical' ? '--s-tac' : '--s-strat') : css('--mark-soft'),
        right: 'ρ ' + num(r_.rho, 2) + (r_.pHolm < .05 ? '' : ' ns'),
        tip: `<b>${r_.label}</b><br>same person, session 1 vs session 2: ρ ${num(r_.rho, 2)} [${num(r_.lo, 2)}, ${num(r_.hi, 2)}]<br>Holm ${pval(r_.pHolm)} · n = 33<br>separates people into ~${num(r_.strata1, 1)} reliable levels from one session, ${num(r_.strata2, 1)} from two` })),
        { min: -0.4, max: 1, ticks: [-0.25, 0, 0.25, 0.5, 0.75, 1], ref: 0, fmt: v => num(v, 2), xlab: 'Spearman ρ, session 1 vs session 2 (0 = no carry-over, 1 = same order of people)' });
      cap(host, 'Coloured = survives Holm correction across the ten habits (strategic blue, tactical orange); grey = does not. Whiskers: 95% bootstrap intervals over people.');
    }),

    /* 5 · pre-empting the cards: session 1 vs session 2 */
    'style.preemptPairs': safe(host => {
      const P = D.preempt, W = 700, H = 330, s = svgRoot(host, W, H);
      const zero = P.points.filter(p => p.a === 0 && p.b === 0), rest = P.points.filter(p => !(p.a === 0 && p.b === 0));
      const mx = Math.max(.6, ...P.points.map(p => Math.max(p.a, p.b))) * 1.05;
      const pts = rest.map(p => ({ x: p.a, y: p.b, r: 4 + Math.sqrt(p.na + p.nb) / 1.6, fill: css('--r-man'),
        tip: `<b>${p.pid}</b><br>session 1: ${p.ka} of ${p.na} decisions pre-empted (${pct(p.a, 0)})<br>session 2: ${p.kb} of ${p.nb} (${pct(p.b, 0)})` }));
      const g = scatterPanel(s, { x: 230, y: 24, w: 300, h: 250 }, pts, { xmin: 0, xmax: mx, ymin: 0, ymax: mx, xticks: [0, .2, .4, .6].filter(v => v <= mx),
        yticks: [0, .2, .4, .6].filter(v => v <= mx), fx: v => pct(v, 0), fy: v => pct(v, 0), diag: true,
        xlab: 'Session 1: share of strategic decisions pre-empted', ylab: 'Session 2: same share' });
      const z = el('circle', { cx: g.sx(0), cy: g.sy(0), r: 4 + zero.length, fill: css('--mark-soft'), 'fill-opacity': .8, stroke: css('--surface'), 'stroke-width': 1.5 }, s);
      hoverable(z, `<b>${zero.length} people never pre-empted in either session</b><br>${zero.map(p => p.pid).join(', ')}`);
      txt(s, g.sx(0) + 8 + zero.length, g.sy(0) - 8, `${zero.length} people: never, either session`, { size: 11, ink: '--ink-3' });
      const R = P.spearman;
      [[`ρ = ${num(R.rho, 2)} [${num(R.lo, 2)}, ${num(R.hi, 2)}]`, true], [`${pval(R.p)}, n = ${R.n}`, true], ['', false],
        [`Pre-empted in session 1 (n = ${P.nDid}):`, false], [`session-2 rate ${pct(P.s2IfDid, 0)}`, true],
        [`Did not (n = ${P.n - P.nDid}):`, false], [`session-2 rate ${pct(P.s2IfNot, 0)}`, true]]
        .forEach(([t, m], q) => t && txt(s, 548, 50 + q * 17, t, { size: 11, mono: m, ink: q < 2 ? '--ink' : '--ink-2' }));
      cap(host, `Each dot is a person (size = decisions). Pre-empting = committing a manual allocation before the strategy cards had loaded. Dashed = same in both sessions. `
        + `${P.preempted} of ${P.decisions} non-residual decisions were pre-empted; ${pct(P.shareOfManual, 0)} of all manual choices.`);
    }),

    /* 6 · what the reliance axis is: loadings in plain terms */
    'style.axisLoadings': safe(host => {
      const L = D.axis.loadings.slice().sort((a, b) => b.v - a.v);
      ciRows(host, L.map(l => ({ label: l.label, est: l.v, lo: null, hi: null, strong: Math.abs(l.v) >= .4,
        color: Math.abs(l.v) >= .4 ? css(l.tier === 'tactical' ? '--s-tac' : '--s-strat') : css('--mark-soft'), right: sgn(l.v, 2),
        tip: `<b>${l.label}</b><br>correlation with the person’s reliance score: ${sgn(l.v, 2)}<br>${l.v > 0 ? 'people high on the axis do more of this' : 'people high on the axis do less of this'}` })),
        { min: -1, max: 1, ticks: [-1, -.5, 0, .5, 1], ref: 0, fmt: v => sgn(v, 1).replace('+0.0', '0'), xlab: 'Correlation between the habit and each person’s score on the reliance axis (n = 33)' });
      cap(host, `The axis is one number per person: a weighted mix of all ten habits, with weights chosen so that this single number captures as much of the spread between people as one number can (here ${pct(D.axis.share, 0)} of it). `
        + `Each bar is the correlation between a habit and that number. +0.92 for “takes the strategy card” means a person’s axis score and their card uptake rise and fall together almost perfectly; −0.48 for decision time means high scorers decide faster. Blue = strategic-tier habit, orange = tactical, grey = weak (|r| < .4).`);
    }),

    /* 7 · the habits that make the axis, as a correlation grid */
    'style.habitCorr': safe(host => {
      const C = D.axis.corr, k = C.cols.length, padL = 130, padT = 92, cell = Math.min(50, (700 - padL - 10) / k), W = 700, H = padT + k * cell + 40;
      const order = D.axis.loadings.map((l, i) => i).sort((a, b) => D.axis.loadings[b].v - D.axis.loadings[a].v);
      const s = svgRoot(host, W, H);
      order.forEach((i, a) => {
        txt(s, padL - 6, padT + a * cell + cell / 2 + 4, C.short[i], { anchor: 'end', size: 11 });
        const tx = padL + a * cell + cell / 2;
        txt(s, tx, padT - 8, C.short[i], { size: 11, rot: -45 });
        order.forEach((j, b) => {
          const v = C.rho[i][j], p = C.p[i][j], diag = i === j;
          const rc = el('rect', { x: padL + b * cell + 1, y: padT + a * cell + 1, width: cell - 2, height: cell - 2, rx: 3,
            fill: diag ? css('--surface-2') : css(v >= 0 ? '--lad-2' : '--warn'), 'fill-opacity': diag ? 1 : Math.min(1, Math.abs(v) * 1.3) }, s);
          if (!diag) {
            txt(s, padL + b * cell + cell / 2, padT + a * cell + cell / 2 + 4, num(v, 2).replace(/^(-?)0\./, '$1.'), { anchor: 'middle', size: 10, mono: true,
              ink: Math.abs(v) > .5 ? '--surface' : '--ink-2', weight: p < .05 ? 600 : null });
            hoverable(rc, `<b>${C.short[i]} × ${C.short[j]}</b><br>Spearman ρ = ${num(v, 2)}, ${pval(p)} (33 people, habits pooled over both sessions)`);
          }
        });
      });
      const ly = padT + k * cell + 18;
      [[-.6, '−.6'], [-.3, '−.3'], [0, '0'], [.3, '+.3'], [.6, '+.6'], [.9, '+.9']].forEach(([v, l], q) => {
        el('rect', { x: padL + q * 60, y: ly, width: 16, height: 12, rx: 2, fill: css(v >= 0 ? '--lad-2' : '--warn'), 'fill-opacity': Math.min(1, Math.abs(v) * 1.3), stroke: css('--line') }, s);
        txt(s, padL + q * 60 + 20, ly + 10, l, { size: 10, ink: '--ink-3', mono: true });
      });
      cap(host, `Rows and columns sorted by loading on the reliance axis, so the habits that make it up sit top-left. Blue = the two habits go together, amber = one goes with less of the other. `
        + `Bold = p < .05 (${D.axis.corrSig.n} of ${D.axis.corrSig.of} pairs, about ${num(.05 * D.axis.corrSig.of, 0)} by chance alone).`);
    }),

    /* 8 · strategic vs tactical reliance per person, coloured by axis score; optional qualitative rings */
    'style.axisScatter': safe(host => {
      const A = D.axis, Q = D.qual || {}, box = h('div', {}, host);
      const bin = v => v >= .8 ? '--lad-1' : v >= 0 ? '--lad-2' : v >= -.8 ? '--lad-3' : '--lad-4';
      const draw = mark => {
        box.innerHTML = '';
        const ring = new Set(mark && Q[mark] ? Q[mark].who : []);
        const s = svgRoot(box, 700, 340);
        const pts = A.people.map(p => ({ x: p.took, y: p.consult, r: 6, fill: css(bin(p.pc1)), op: .95, ring: ring.has(p.pid),
          tip: `<b>${p.pid}</b><br>strategy cards taken ${pct(p.took, 0)} of ${p.n} decisions<br>Suggest pressed on ${pct(p.consult, 0)} of ${p.nT} tactical plans<br>reliance-axis score ${sgn(p.pc1, 2)} SD`
            + (ring.has(p.pid) ? `<br><i>coded ${mark}</i>` : '') }));
        scatterPanel(s, { x: 90, y: 20, w: 420, h: 270 }, pts, { xmin: 0, xmax: 1.02, ymin: 0, ymax: 1.02, xticks: [0, .25, .5, .75, 1], yticks: [0, .25, .5, .75, 1],
          fx: v => pct(v, 0), fy: v => pct(v, 0), xlab: 'Strategic: % of strategic decisions where a card was taken', ylab: 'Tactical: % of plans with Suggest' });
        [['--lad-1', '≥ +0.8 SD'], ['--lad-2', '0 to +0.8'], ['--lad-3', '−0.8 to 0'], ['--lad-4', '< −0.8 SD']].forEach(([c, l], q) => {
          el('circle', { cx: 540, cy: 50 + q * 22, r: 6, fill: css(c), stroke: css('--line') }, s);
          txt(s, 552, 54 + q * 22, l, { size: 11 });
        });
        txt(s, 532, 30, 'Reliance-axis score', { size: 11, weight: 600, ink: '--ink' });
        txt(s, 532, 150, 'Cards vs Suggest:', { size: 10.5, ink: '--ink-3' });
        txt(s, 532, 166, `ρ = ${num(A.tookConsult.rho, 2)} [${num(A.tookConsult.lo, 2)}, ${num(A.tookConsult.hi, 2)}]`, { size: 10, mono: true });
        txt(s, 532, 181, `${pval(A.tookConsult.p)}, n = ${A.tookConsult.n}`, { size: 10, mono: true });
        if (mark && Q[mark]) {
          const g = Q[mark];
          el('circle', { cx: 540, cy: 210, r: 6, fill: 'none', stroke: css('--bad'), 'stroke-width': 2.5 }, s);
          txt(s, 552, 214, `${mark}: ${g.n} of ${g.of}`, { size: 11 });
          txt(s, 532, 236, `cards ${pct(g.took.inMean, 0)} vs ${pct(g.took.restMean, 0)} others`, { size: 10, mono: true });
          txt(s, 532, 252, `Suggest ${pct(g.consult.inMean, 0)} vs ${pct(g.consult.restMean, 0)}`, { size: 10, mono: true });
        }
      };
      host.insertBefore(btnBar(host, 'Ring', [['', 'Nobody'], ['C01', 'Said: my own strategy (C01)'], ['C02', 'Said: wants control (C02)']], '', draw), box);
      draw('');
      cap(host, 'Each dot is a person, both sessions pooled. Strategic and tactical reliance go together only loosely; the axis score (colour) is mostly how many cards a person takes, plus Suggest use and speed.');
    }),

    /* 9 · how much of card-taking is the person vs the mission */
    'style.whoVsWhat': safe(host => {
      const Wv = D.whoVsWhat, PL = Wv.plain;
      const box = h('div', {}, host);
      const r2 = () => {
        h('p', { class: 'cap', html: '<b>Bar length</b> = McFadden pseudo-R², as a % (how much of whether a card is taken each model explains; 0% = no better than the overall rate).' }, box);
        barsH(h('div', {}, box), [{ label: 'Mission, scenario, run, timing', value: Wv.mission, color: css('--mark-soft'), sub: 'drone types, drones, scenario, session, decision number' },
          { label: 'Who the operator is', value: Wv.person, color: css('--s-strat'), sub: 'one term per person' },
          { label: 'Both together', value: Wv.both, color: css('--mark'), sub: `${Wv.n} decisions, ${Wv.people} people` }],
          { max: .4, fmt: v => pct(v, 0), padL: 220 });
        cap(box, `McFadden pseudo-R²: how much better than a coin weighted at the overall rate each model predicts whether a card is taken (0 = no better, 1 = perfect). Descriptive only — person-only models flatter themselves at ~18 decisions each`
          + (PL ? ` (with the person labels shuffled at random, the person-only model still scores ${pct(PL.nullPerson.mean, 0)} on average, so about ${pct(Wv.person - PL.nullPerson.mean, 0)} of its ${pct(Wv.person, 0)} is real)` : '')
          + `. Card uptake per person ranges ${pct(Wv.rates.lo, 0)}–${pct(Wv.rates.hi, 0)} (median ${pct(Wv.rates.median, 0)}).`);
      };
      // The same comparison as a ranking test: bars run from 50% (a coin) towards 100% (perfect), whiskers = 95% interval.
      const plain = () => {
        const M = Object.fromEntries(PL.models.map(m => [m.key, m]));
        const rows = [['mission', 'Mission, scenario, run, timing', '--mark-soft', 'everything about the mission and when it came'],
                      ['person', 'Who the operator is', '--s-strat', 'their rate on all their OTHER decisions'],
                      ['both', 'Both together', '--mark', 'mission + their rate on their other decisions'],
                      ['s1s2', 'Session 2, from session 1 only', '--s-tac', 'each person\'s session-1 rate, applied to their session-2 decisions']];
        const W = 700, rowH = 40, padL = 230, padR = 70, padT = 8, H = padT + rows.length * rowH + 34;
        const s = svgRoot(h('div', {}, box), W, H);
        const x = v => padL + (W - padL - padR) * ((v - .5) / .5);
        [.5, .6, .7, .8, .9, 1].forEach(v => {
          el('line', { x1: x(v), x2: x(v), y1: padT, y2: H - 28, stroke: css(v === .5 ? '--ink-3' : '--grid') }, s);
          el('text', { x: x(v), y: H - 12, 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 11, 'font-family': css('--mono') }, s).textContent = v === .5 ? '50% coin' : pct(v, 0);
        });
        rows.forEach(([k, lab, c, sub], i) => {
          const m = M[k], y = padT + i * rowH + rowH / 2;
          el('text', { x: padL - 10, y: y + 4, 'text-anchor': 'end', fill: css('--ink-2'), 'font-size': 12.5 }, s).textContent = lab;
          el('rect', { x: x(.5), y: y - 8, width: Math.max(0, x(m.auc) - x(.5)), height: 16, rx: 4, fill: css(c) }, s);
          el('line', { x1: x(m.lo), x2: x(m.hi), y1: y, y2: y, stroke: css('--ink'), 'stroke-width': 1.5 }, s);
          [m.lo, m.hi].forEach(v => el('line', { x1: x(v), x2: x(v), y1: y - 5, y2: y + 5, stroke: css('--ink'), 'stroke-width': 1.5 }, s));
          el('text', { x: x(m.hi) + 8, y: y + 4, fill: css('--ink-2'), 'font-size': 12, 'font-family': css('--mono') }, s).textContent = pct(m.auc, 0);
          hoverable(el('rect', { x: padL, y: y - rowH / 2, width: W - padL - padR, height: rowH, fill: 'transparent' }, s),
            `<b>${lab}</b><br>${sub}<br>ranks a taken/not-taken pair right ${pct(m.auc, 0)} of the time [${pct(m.lo, 0)}, ${pct(m.hi, 0)}]<br>`
            + `guesses right ${pct(m.acc, 0)} (always guessing 'card': ${pct(m.base != null ? m.base : PL.baseAcc, 0)}) · ${m.n} decisions`);
        });
        cap(box, `<b>How to read it.</b> Take one decision where a card was taken and one where it was not, and ask each model which is which. `
          + `A coin gets it right 50% of the time, a perfect model 100%. Knowing only the mission: ${pct(M.mission.auc, 0)}. Knowing only who is deciding, from their other decisions: ${pct(M.person.auc, 0)}. `
          + `Both: ${pct(M.both.auc, 0)}. The honest test: each person's session-1 rate alone picks out their session-2 decisions ${pct(M.s1s2.auc, 0)} of the time. `
          + `Whiskers = 95% intervals (people resampled). Plain 'right or wrong' guessing barely moves, because ${pct(PL.rate, 0)} of decisions took a card, so 'always card' is already right ${pct(PL.baseAcc, 0)} of the time.`);
      };
      const draw = k => { box.innerHTML = ''; (k === 'plain' && PL ? plain : r2)(); };
      host.insertBefore(btnBar(host, 'Measure', [['r2', 'Pseudo-R² (as before)'], ['plain', 'In plain terms: telling taken from not taken']], 'r2', draw), box);
      draw('r2');
    }),

    /* 10 · no types: observed against the no-types benchmarks */
    'style.typesNull': safe(host => {
      const T = D.types, A = Object.fromEntries(T.arch.map(a => [a.k, a]));
      const rows = [
        { label: 'Two groups vs one (ΔBIC)', obs: T.dbic, min: 0, max: 15, mark: 10, markLab: 'needed > 10', fmt: v => num(v, 1),
          tip: `How much better two groups fit than one smooth spread. Observed ${num(T.dbic, 1)}; a real two-type split needs > 10. ${pct(T.nullDbicShare, 0)} of simulated no-type samples did at least as well.` },
        { label: 'Same grouping in both sessions (ARI)', obs: T.ari, min: -0.1, max: 1, mark: 0, markLab: '0 = chance', fmt: v => num(v, 2),
          tip: `Agreement between the groups found in session 1 and in session 2 (1 = identical, 0 = chance). Observed ${num(T.ari, 2)}.` },
        { label: 'Spread explained, 3 archetypes', obs: A.expl3.obs, lo: A.expl3.lo, hi: A.expl3.hi, min: .3, max: .7, fmt: v => pct(v, 0),
          tip: `Observed ${pct(A.expl3.obs, 0)}; simulated operators with the same habits but no types: ${pct(A.expl3.lo, 0)}–${pct(A.expl3.hi, 0)} (95%).` },
        { label: 'Same archetype both sessions', obs: A.same.obs, lo: A.same.lo, hi: A.same.hi, min: .2, max: .9, fmt: v => pct(v, 0),
          tip: `Observed ${pct(A.same.obs, 0)}; no-types simulation ${pct(A.same.lo, 0)}–${pct(A.same.hi, 0)} (95%).` }];
      const W = 700, rowH = 46, padL = 250, padR = 70, H = rows.length * rowH + 30, s = svgRoot(host, W, H);
      rows.forEach((q, i) => {
        const y = 20 + i * rowH, x = v => padL + (W - padL - padR) * (v - q.min) / (q.max - q.min);
        txt(s, padL - 12, y + 4, q.label, { anchor: 'end', size: 12 });
        el('line', { x1: x(q.min), x2: x(q.max), y1: y, y2: y, stroke: css('--grid'), 'stroke-width': 6, 'stroke-linecap': 'round' }, s);
        if (q.lo != null) el('line', { x1: x(q.lo), x2: x(q.hi), y1: y, y2: y, stroke: css('--mark-soft'), 'stroke-width': 10, 'stroke-linecap': 'round' }, s);
        if (q.mark != null) { el('line', { x1: x(q.mark), x2: x(q.mark), y1: y - 10, y2: y + 10, stroke: css('--ink-3'), 'stroke-dasharray': '3 2' }, s);
          txt(s, x(q.mark), y - 12, q.markLab, { anchor: 'middle', size: 10, ink: '--ink-3' }); }
        const c = el('circle', { cx: x(q.obs), cy: y, r: 6.5, fill: css('--s-strat'), stroke: css('--surface'), 'stroke-width': 2 }, s);
        txt(s, W - padR + 10, y + 4, q.fmt(q.obs), { mono: true, size: 11 });
        [q.min, q.max].forEach((v, e) => txt(s, x(v), y + 21, q.fmt(v), { anchor: e ? 'end' : 'start', size: 9.5, ink: '--ink-3', mono: true }));
        hoverable(c, `<b>${q.label}</b><br>${q.tip}<br>n = 33 people`);
      });
      legend(host, [{ label: 'observed', color: css('--s-strat') }, { label: 'operators simulated with no types (95% range)', color: css('--mark-soft') }]);
    }),

    /* 11 · disposition against behaviour: all 40 tests at once */
    'style.dispositionGrid': safe(host => {
      const DP = D.disposition, preds = [...new Set(DP.cells.map(c => c.pred))], behs = [...new Set(DP.cells.map(c => c.beh))];
      const lab = Object.fromEntries(DP.cells.map(c => [c.pred, c.predLabel])), blab = Object.fromEntries(DP.cells.map(c => [c.beh, c.behLabel]));
      const padL = 270, padT = 70, cw = (700 - padL - 10) / behs.length, ch = 30, W = 700, H = padT + preds.length * ch + 36;
      const s = svgRoot(host, W, H);
      behs.forEach((b, j) => {
        const words = blab[b].split(' '), mid = Math.ceil(words.length / 2);
        txt(s, padL + j * cw + cw / 2, padT - 26, words.slice(0, mid).join(' '), { anchor: 'middle', size: 10.5 });
        txt(s, padL + j * cw + cw / 2, padT - 12, words.slice(mid).join(' '), { anchor: 'middle', size: 10.5 });
      });
      preds.forEach((p, i) => {
        txt(s, padL - 8, padT + i * ch + ch / 2 + 4, lab[p].length > 42 ? lab[p].slice(0, 41) + '…' : lab[p], { anchor: 'end', size: 11 });
        behs.forEach((b, j) => {
          const c = DP.cells.find(x => x.pred === p && x.beh === b);
          if (!c || c.rho == null) return;
          const rc = el('rect', { x: padL + j * cw + 2, y: padT + i * ch + 2, width: cw - 4, height: ch - 4, rx: 3,
            fill: css(c.rho >= 0 ? '--lad-2' : '--warn'), 'fill-opacity': Math.min(1, Math.abs(c.rho) * 1.4),
            stroke: c.p < .05 ? css('--ink') : 'none', 'stroke-width': 1.5 }, s);
          txt(s, padL + j * cw + cw / 2, padT + i * ch + ch / 2 + 4, num(c.rho, 2).replace(/^(-?)0\./, '$1.'), { anchor: 'middle', size: 10.5, mono: true });
          hoverable(rc, `<b>${c.predLabel}</b> × ${c.behLabel}<br>Spearman ρ = ${num(c.rho, 2)}, ${pval(c.p)} uncorrected, Holm ${pval(c.holm)}<br>n = ${c.n}`);
        });
      });
      txt(s, 8, 14, 'Each cell: Spearman ρ across people, questionnaire score (row) × behaviour (column, mean of both sessions)', { size: 10.5, ink: '--ink-3' });
      txt(s, 8, 28, 'Colour: blue = positive ρ, amber = negative; stronger colour = larger |ρ|', { size: 10.5, ink: '--ink-3' });
      txt(s, 8, H - 10, `Outlined = p < .05 before correction (${DP.nNominal} of ${DP.nTests}); after Holm: ${DP.nHolm}. Detectable at 80% power: |ρ| ≥ ${num(DP.detectable, 2)}.`, { size: 11, ink: '--ink-2' });
    }),

    /* 12 · reliance and trust, between people and within a person */
    'style.trustBW': safe(host => {
      const box = h('div', {}, host);
      const draw = tier => {
        box.innerHTML = '';
        const T = D.trust[tier], s = svgRoot(box, 700, 320), col = css(tier === 'tactical' ? '--s-tac' : '--s-strat');
        const what = tier === 'tactical' ? 'Suggest use' : 'card uptake';
        const lim = (arr, k) => Math.max(.05, ...arr.map(p => Math.abs(p[k]))) * 1.1;
        const bx = lim(T.ptsB, 'x'), by = lim(T.ptsB, 'y'), wx = lim(T.ptsW, 'x'), wy = lim(T.ptsW, 'y');
        const X = Math.max(bx, wx), Y = Math.max(by, wy);
        const tick = v => [-v, 0, v].map(t => +t.toFixed(2));
        const t1 = Math.round(X * 0.6 * 20) / 20 || .05, t2 = Math.round(Y * 0.6 * 2) / 2 || .5;
        scatterPanel(s, { x: 70, y: 30, w: 255, h: 230 }, T.ptsB.map(p => ({ x: p.x, y: p.y, fill: col,
          tip: `<b>${p.pid}</b> (mean of both sessions)<br>${what} ${sgn(100 * p.x, 0)} points vs game average<br>trust ${sgn(p.y, 2)} vs game average (1–7 scale)` })),
          { xmin: -X, xmax: X, ymin: -Y, ymax: Y, xticks: tick(t1), yticks: tick(t2), fx: v => v === 0 ? '0' : sgn(100 * v, 0), fy: v => v === 0 ? '0' : sgn(v, 1), zeroLines: true, fit: true,
            title: 'Between people', sub: rhoS(T.between), xlab: `Person’s ${what} vs game average (points)`, ylab: `Reported ${tier} trust vs average` });
        scatterPanel(s, { x: 420, y: 30, w: 255, h: 230 }, T.ptsW.map(p => ({ x: p.x, y: p.y, fill: col,
          tip: `<b>${p.pid}</b> (session 2 minus session 1, game-adjusted)<br>${what} change ${sgn(100 * p.x, 0)} points<br>trust change ${sgn(p.y, 2)}` })),
          { xmin: -X, xmax: X, ymin: -Y, ymax: Y, xticks: tick(t1), yticks: tick(t2), fx: v => v === 0 ? '0' : sgn(100 * v, 0), fy: v => v === 0 ? '0' : sgn(v, 1), zeroLines: true, fit: true,
            title: 'Within a person', sub: rhoS(T.within), xlab: `Change in ${what}, session 1 → 2 (points)`, ylab: `Change in ${tier} trust` });
        cap(box, `<b>Left:</b> each dot is a person’s average over both sessions — ${rho(T.between)}. <b>Right:</b> each dot is how the same person changed from session 1 to 2 — ${rho(T.within)}. `
          + `Both axes are game-adjusted (each session minus the mean of everyone who played that game). Same scales on both panels; the line is a least-squares guide.`);
      };
      host.insertBefore(btnBar(host, 'Assistant', [['strategic', 'Strategic (cards ↔ strategic trust)'], ['tactical', 'Tactical (Suggest ↔ tactical trust)']], 'strategic', draw), box);
      draw('strategic');
    }),

    /* 13 · payoff: between people vs within a person, on missions completed in full */
    'style.payoffBW': safe(host => {
      const C = D.payoff.completion, s = svgRoot(host, 700, 340);
      scatterPanel(s, { x: 70, y: 30, w: 255, h: 240 }, C.people.map(p => ({ x: p.up, y: p.adj, r: 3 + Math.sqrt(p.n) / 1.5, fill: css('--s-strat'),
        tip: `<b>${p.pid}</b><br>cards taken ${pct(p.up, 0)} of ${p.n} decisions<br>missions completed in full ${pct(p.obs, 0)}; expected from the missions ${pct(p.exp, 0)}<br>difference ${sgn(100 * p.adj, 0)} points` })),
        { xmin: 0, xmax: 1.02, ymin: -.6, ymax: .6, xticks: [0, .5, 1], yticks: [-.5, -.25, 0, .25, .5], fx: v => pct(v, 0), fy: v => v === 0 ? '0' : sgn(100 * v, 0), zeroLines: true, fit: true,
          title: 'Between people', sub: rhoS(C.between), xlab: 'Person’s share of strategy cards taken', ylab: 'Completed in full, vs expected (points)' });
      const pr = C.pairs;
      scatterPanel(s, { x: 420, y: 30, w: 255, h: 240 }, pr.map(p => ({ x: p.man, y: p.card, r: 3 + Math.sqrt(p.nc + p.nm) / 1.5, fill: css('--r-cons'),
        tip: `<b>${p.pid}</b><br>own manual missions completed in full: ${pct(p.man, 0)} (n = ${p.nm})<br>own card missions: ${pct(p.card, 0)} (n = ${p.nc})<br>card minus manual, adjusted for mission size: ${sgn(100 * p.diffAdj, 0)} points` })),
        { xmin: 0, xmax: 1.02, ymin: 0, ymax: 1.02, xticks: [0, .5, 1], yticks: [0, .5, 1], fx: v => pct(v, 0), fy: v => pct(v, 0), diag: true,
          title: 'Within a person', sub: `card better for ${C.within.better} of ${C.within.n}`, xlab: 'Own manual missions completed in full', ylab: 'Own card missions completed in full' });
      cap(host, `<b>Left:</b> people who take more cards complete more of their missions in full than the size of those missions predicts — ${rho(C.between)}. `
        + `<b>Right:</b> but the same person’s card missions do no better than their own manual ones (above the dashed line = card better): better for ${C.within.better}, worse for ${C.within.worse} of ${C.within.n} people with at least two of each; `
        + `median size-adjusted difference ${sgn(100 * C.within.median, 0)} points (Wilcoxon ${pval(C.within.p)}).`);
    }),

    /* 14 · payoff: the model estimates, between vs within */
    'style.payoffForest': safe(host => {
      const P = D.payoff, d = P.decision, sess = P.session, T = P.throughput;
      const g = (y, c) => sess.find(x => x.y === y && x.comp === c) || {};
      h('p', { class: 'cap', html: '<b>Mission completed in full</b> — odds ratio (1 = no difference). Decision-level model, adjusted for mission size, drone types and game.' }, host);
      const a = h('div', {}, host);
      ciRows(a, [
        { label: 'Between: +25 pts card uptake', est: d.between25, lo: Math.pow(d.betweenLo, .25), hi: Math.pow(d.betweenHi, .25), strong: true, color: css('--s-strat'),
          right: '×' + num(d.between25, 2), tip: `Between people, per +25 percentage points of card uptake: OR ${num(d.between25, 2)} (×${num(d.betweenOR, 2)} from 0% to 100%), ${pval(d.betweenP)}; ${d.n} decisions, ${d.people} people` },
        { label: 'Within: own card vs own manual', est: d.withinOR, lo: d.withinLo, hi: d.withinHi, strong: false, color: css('--r-cons'),
          right: '×' + num(d.withinOR, 2), tip: `Within a person, card vs manual: OR ${num(d.withinOR, 2)} [${num(d.withinLo, 2)}, ${num(d.withinHi, 2)}], ${pval(d.withinP)}<br>could have detected ≤ ${num(d.detectLo, 2)} or ≥ ${num(d.detectHi, 2)}` }],
        { min: .4, max: 2.5, log: true, ticks: [.5, .75, 1, 1.5, 2], ref: 1, fmt: v => '×' + v, padL: 290 });
      h('p', { class: 'cap', html: '<b>Session outcomes</b> — change in SD (within game) per +25 percentage points of card uptake. Session-level model, game and run fixed.' }, host);
      const b = h('div', {}, host);
      const row = (y, c, lab) => { const t = g(y, c); return { label: lab, est: t.est, lo: t.lo, hi: t.hi, strong: t.p < .05, color: css(c === 'between' ? '--s-strat' : '--r-cons'),
        right: sgn(t.est, 2), tip: `<b>${t.label}</b>, ${c} person<br>${sgn(t.est, 2)} SD [${sgn(t.lo, 2)}, ${sgn(t.hi, 2)}], ${pval(t.p)}<br>66 sessions, 33 people` }; };
      ciRows(b, [row('z', 'between', 'Score — between people'), row('z', 'within', 'Score — within a person'),
        row('unalloc', 'between', 'Missions never allocated — between'), row('unalloc', 'within', 'Missions never allocated — within')],
        { min: -.9, max: .9, ticks: [-.75, -.5, -.25, 0, .25, .5, .75], ref: 0, fmt: v => sgn(v, 2), padL: 290 });
      cap(host, `Throughput on the wider reliance axis (cards + Suggest + speed): a session one SD higher than the same person’s other session leaves ${num(-T.within.est, 2)} fewer missions never allocated [${num(-T.within.hi, 2)}, ${num(-T.within.lo, 2)}], ${pval(T.within.p)} `
        + `(${num(-T.withinNoSpeed.est, 2)} with decision speed taken out, ${pval(T.withinNoSpeed.p)}; card uptake alone ${pval(T.withinUptake25.p)}). Sessions average ${num(T.meanUnalloc, 1)} never-allocated missions.`);
    }),

    /* 15 · what operators want (counts, unprompted share) */
    'style.wantsBars': safe(host => {
      h('p', { class: 'cap', html: '<b>Bar length</b> = number of the 33 operators who said this in the debrief or interview.' }, host);
      const Q = D.qual, rows = [['C25', 'A human should keep the final say'], ['C27', 'Wants failure data / analytics'], ['C08', 'Wants more options / a middle ground'],
        ['C26', 'Wants the assistant’s reasoning'], ['C28', 'Wants more automation'], ['C23', 'Says the assistant improved results'], ['C24', 'Says they did better by hand']]
        .filter(([c]) => Q[c]);
      barsH(h('div', {}, host), rows.map(([c, l]) => ({ label: `${l} (${c})`, value: Q[c].n, color: css(c === 'C23' || c === 'C24' ? '--mark-soft' : '--mark'),
        sub: `${Q[c].unprompted} unprompted · ${Q[c].who.join(', ') || 'nobody'}<br>cards ${Q[c].took.inMean == null ? '—' : pct(Q[c].took.inMean, 0)} vs ${pct(Q[c].took.restMean, 0)} for everyone else · Suggest ${Q[c].consult.inMean == null ? '—' : pct(Q[c].consult.inMean, 0)} vs ${pct(Q[c].consult.restMean, 0)}` })),
        { max: 12, fmt: v => `${num(v, 0)} of 33`, padL: 300 });
      cap(host, 'People coded from the debrief / interview (one AI coder; see Methods). A person can be in several bars. Hover for who and how the group used the assistants (descriptive only).');
    }),

    /* ───────────── pass 3 ───────────── */

    /* P3 · the ten habits: what each is, and its spread over the 66 sessions (raw units) */
    'style.habits': safe(host => {
      const HB = D.pass3.habits, rows = HB.habits;
      const ONE = { took: 'card taken as offered, % of strategic decisions', preempt: 'made before the cards appeared, % of hand-made decisions',
        edit: 'card edited then committed, % of strategic decisions', previews: 'card previews per strategic decision',
        netSecs: 'seconds per strategic decision, beyond the card wait', dSmall: 'drones vs the Conservative card, single-type missions',
        dLarge: 'drones vs the Conservative card, multi-type missions', consult: 'Suggest pressed, % of tactical plans',
        keep: 'deployed unchanged, % of plans where Suggest was pressed', recSug: 'Suggest pressed, % of recovery episodes' };
      const ORDER = [['Strategic tier (the strategy cards)', ['took', 'previews', 'netSecs', 'preempt', 'edit', 'dLarge', 'dSmall']],
        ['Tactical tier (Suggest)', ['consult', 'keep', 'recSug']]];
      const by = Object.fromEntries(rows.map(r_ => [r_.k, r_]));
      const scale = r_ => {
        if (r_.unit === 'pct') return { min: 0, max: 1, ticks: [0, .5, 1], f: v => pct(v, 0), x: v => v };
        if (r_.unit === 'secs') return { min: 1, max: 50, ticks: [2, 5, 10, 20, 40], f: v => num(v, 0) + ' s', log: true };
        if (r_.unit === 'drones') return { min: -3.5, max: 4.5, ticks: [-3, 0, 3], f: v => sgn(v, 0), zero: true };
        return { min: 0, max: Math.max(1.6, r_.hi || 1), ticks: [0, .5, 1, 1.5], f: v => num(v, 1) };
      };
      const fmtV = (r_, v) => v == null ? '—' : r_.unit === 'pct' ? pct(v, 0) : r_.unit === 'secs' ? num(v, 1) + ' s' : r_.unit === 'drones' ? sgn(v, 1) + ' drones' : num(v, 2);
      const W = 700, rowH = 46, headH = 24, x0 = 300, x1 = 560, nRows = ORDER.reduce((a, g) => a + g[1].length, 0);
      const H = 22 + ORDER.length * headH + nRows * rowH + 20, s = svgRoot(host, W, H);
      txt(s, x0 + (x1 - x0) / 2, 13, 'Each dot = one session (66: 33 people × 2)', { anchor: 'middle', size: 10.5, ink: '--ink-3' });
      txt(s, W - 4, 13, 'carry-over ρ (s1 vs s2)', { anchor: 'end', size: 10.5, ink: '--ink-3' });
      let y = 22;
      ORDER.forEach(([head, keys]) => {
        txt(s, 4, y + 16, head, { ink: '--ink', weight: 600, size: 12 });
        y += headH;
        keys.forEach(k => {
          const r_ = by[k];
          if (!r_) return;
          const sc = scale(r_), tr = sc.log ? Math.log : (v => v);
          const X = v => x0 + (x1 - x0) * (tr(Math.max(sc.min, Math.min(sc.max, v))) - tr(sc.min)) / (tr(sc.max) - tr(sc.min));
          const cy = y + 17, col = css(r_.tier === 'tactical' ? '--s-tac' : '--s-strat');
          txt(s, 4, cy - 2, r_.label, { ink: '--ink', size: 12, weight: 600 });
          txt(s, 4, cy + 13, ONE[k] || '', { size: 10.5, ink: '--ink-3' });
          el('line', { x1: x0, x2: x1, y1: cy, y2: cy, stroke: css('--grid'), 'stroke-width': 1 }, s);
          if (sc.zero) el('line', { x1: X(0), x2: X(0), y1: cy - 12, y2: cy + 12, stroke: css('--ink-3'), 'stroke-dasharray': '2 2' }, s);
          sc.ticks.forEach(t => txt(s, X(t), cy + 24, sc.f(t), { anchor: 'middle', size: 9, ink: '--ink-3', mono: true }));
          if (r_.q1 != null) el('rect', { x: X(r_.q1), y: cy - 10, width: Math.max(2, X(r_.q3) - X(r_.q1)), height: 20, rx: 3, fill: col, 'fill-opacity': .12 }, s);
          r_.pts.forEach((p, i) => {
            if (p[2] == null) return;
            const jit = ((i * 37) % 11 - 5) * 1.5;
            const c = el('circle', { cx: X(p[2]), cy: cy + jit, r: 2.6, fill: col, 'fill-opacity': .55 }, s);
            hoverable(c, `<b>${p[0]} · session ${p[1]}</b><br>${r_.label}: ${fmtV(r_, p[2])}<br>from ${p[3]} ${r_.per}`);
          });
          if (r_.median != null) el('line', { x1: X(r_.median), x2: X(r_.median), y1: cy - 12, y2: cy + 12, stroke: css('--ink'), 'stroke-width': 2.5 }, s);
          const hit = el('rect', { x: 0, y, width: x0 - 6, height: rowH, fill: 'transparent' }, s);
          hoverable(hit, `<b>${r_.label}</b><br>${r_.what}<br>median ${fmtV(r_, r_.median)}, middle half ${fmtV(r_, r_.q1)} to ${fmtV(r_, r_.q3)}`
            + (r_.missing ? `<br>undefined in ${r_.missing} of ${HB.nSessions} sessions (nothing to count)` : '')
            + `<br>same person, session 1 vs 2: ρ ${num(r_.rho, 2)} [${num(r_.rhoLo, 2)}, ${num(r_.rhoHi, 2)}], Holm ${pval(r_.pHolm)}`);
          const strong = r_.pHolm < .05;
          txt(s, W - 4, cy + 4, `ρ ${num(r_.rho, 2)}${strong ? '' : ' ns'}`, { anchor: 'end', size: 11, mono: true, ink: strong ? '--ink' : '--ink-3', weight: strong ? 600 : null });
          y += rowH;
        });
      });
      cap(host, `Dots: every session’s value of the habit in its own units (hover for who and how many decisions it rests on); black tick = median; shaded band = the middle half of sessions. `
        + `Right: how strongly the habit carries over from a person’s first session to their second (Spearman ρ, game-adjusted; “ns” = not significant after correcting for ten tests). `
        + `For the fingerprint every habit is then turned into a z-score within the game played, so the profiles compare people, not games.`);
      tableFor(host, ['Habit', 'What is counted', 'Median', 'Middle half', 'Undefined', 'ρ s1→s2'],
        rows.map(r_ => [r_.label, r_.what, fmtV(r_, r_.median), `${fmtV(r_, r_.q1)} to ${fmtV(r_, r_.q3)}`, `${r_.missing} of ${HB.nSessions}`, num(r_.rho, 2)]), 'What each habit is (definitions)');
    }),

    /* P3 · no types, self-explaining: map, separation vs no-types simulations, recurrence */
    'style.typesSimple': safe(host => {
      const T = D.pass3.types, box = h('div', {}, host);
      const views = {
        map: () => {
          const s = svgRoot(box, 700, 330), M = T.map, gcol = g => css(g ? '--s-tac' : '--s-strat');
          const lim = Math.max(...M.pts.concat(M.sim).map(p => Math.max(Math.abs(p.x), Math.abs(p.y)))) * 1.08;
          const tk = [-Math.floor(lim), 0, Math.floor(lim)];
          scatterPanel(s, { x: 60, y: 34, w: 250, h: 240 }, M.pts.map(p => ({ x: p.x, y: p.y, r: 5.5, fill: gcol(p.g),
            tip: `<b>${p.pid}</b><br>reliance axis ${sgn(p.x, 2)}, second dimension ${sgn(p.y, 2)}<br>put in group ${p.g ? 'B' : 'A'} by the best two-group split` })),
            { xmin: -lim, xmax: lim, ymin: -lim, ymax: lim, xticks: tk, yticks: tk, fx: v => String(v), fy: v => String(v), zeroLines: true,
              title: 'The 33 real operators', xlab: 'Reliance axis: 1st dimension (PCA score)', ylab: '2nd dimension (PCA score)' });
          scatterPanel(s, { x: 420, y: 34, w: 250, h: 240 }, M.sim.map((p, i) => ({ x: p.x, y: p.y, r: 5.5, fill: gcol(p.g), op: .6,
            tip: `Simulated operator ${i + 1} (no types by construction)<br>group ${p.g ? 'B' : 'A'} of the best two-group split` })),
            { xmin: -lim, xmax: lim, ymin: -lim, ymax: lim, xticks: tk, yticks: tk, fx: v => String(v), fy: v => String(v), zeroLines: true,
              title: '33 simulated, no types', xlab: '1st dimension (PCA score)', ylab: '2nd dimension (PCA score)' });
          cap(box, `Each dot is one operator, placed by the two biggest dimensions of their ten habits (together ${pct(M.pc[0] + M.pc[1], 0)} of the differences). Colour = the best split into two groups. `
            + `Left, the real people; right, 33 simulated operators made to have the same habits and the same links between habits, but drawn from one smooth cloud, so they have no types at all (this sample is the typical one, separation ${num(M.simSil, 2)}). `
            + `Both are one continuous cloud: the split just cuts it in half, it does not find two clumps with a gap between them.`);
        },
        sep: () => {
          const S = T.sil, s = svgRoot(box, 700, 280), padL = 60, padB = 50, padT = 22, Hh = 280, top = .45;
          const y = v => Hh - padB - (Hh - padB - padT) * v / top, gw = (700 - padL - 20) / S.length;
          [0, .1, .2, .3, .4].forEach(v => { el('line', { x1: padL, x2: 690, y1: y(v), y2: y(v), stroke: css('--grid') }, s);
            txt(s, padL - 6, y(v) + 4, num(v, 1), { anchor: 'end', size: 10, mono: true, ink: '--ink-3' }); });
          el('line', { x1: padL, x2: 690, y1: y(.25), y2: y(.25), stroke: css('--ink-3'), 'stroke-dasharray': '5 3' }, s);
          txt(s, 688, y(.25) - 5, 'below .25: no real group structure', { anchor: 'end', size: 10, ink: '--ink-3' });
          S.forEach((q, i) => {
            const cx = padL + gw * (i + .5), bw = 46;
            const b1 = el('rect', { x: cx - bw - 4, y: y(q.obs), width: bw, height: y(0) - y(q.obs), rx: 4, fill: css('--s-strat') }, s);
            const b2 = el('rect', { x: cx + 4, y: y(q.nullMean), width: bw, height: y(0) - y(q.nullMean), rx: 4, fill: css('--mark-soft') }, s);
            el('line', { x1: cx + 4 + bw / 2, x2: cx + 4 + bw / 2, y1: y(q.nullLo), y2: y(q.nullHi), stroke: css('--ink-2'), 'stroke-width': 1.5 }, s);
            [q.nullLo, q.nullHi].forEach(v => el('line', { x1: cx + bw / 2 - 2, x2: cx + bw / 2 + 10, y1: y(v), y2: y(v), stroke: css('--ink-2'), 'stroke-width': 1.5 }, s));
            txt(s, cx - bw / 2 - 4, y(q.obs) - 5, num(q.obs, 2), { anchor: 'middle', size: 10.5, mono: true });
            txt(s, cx, Hh - padB + 16, `split into ${q.k} groups`, { anchor: 'middle', size: 11.5, ink: '--ink' });
            txt(s, cx, Hh - padB + 30, `real ≥ simulated in ${pct(1 - q.p, 0)} of draws`, { anchor: 'middle', size: 10, ink: '--ink-3' });
            hoverable(b1, `<b>Real operators, ${q.k} groups</b><br>separation (silhouette) ${num(q.obs, 3)}<br>group sizes ${q.sizes.join(', ')} of 33`);
            hoverable(b2, `<b>No-types simulations, ${q.k} groups</b><br>mean ${num(q.nullMean, 3)}, 95% of ${T.nSims} samples ${num(q.nullLo, 3)}–${num(q.nullHi, 3)}<br>share at least as separated as the real data: ${pct(q.p, 0)}<br>(habits shuffled independently: mean ${num(q.shufMean, 3)})`);
          });
          txt(s, 14, padT + (Hh - padB - padT) / 2, 'separation (silhouette, 0–1)', { anchor: 'middle', size: 11, rot: -90 });
          legend(box, [{ label: 'the 33 real operators', color: css('--s-strat') }, { label: `simulated operators with no types (mean, whisker = 95% of ${T.nSims})`, color: css('--mark-soft') }]);
          cap(box, `Separation (silhouette): for each person, how much closer they sit to their own group than to the nearest other group, averaged; 1 = tight clumps far apart, 0 = the boundaries are arbitrary. `
            + `However the people are split, the real data separate no better than samples that have no types by construction, and all values sit below .25.`);
        },
        recur: () => {
          const A = T.ari, s = svgRoot(box, 700, 250), padL = 60, padB = 40, padT = 22, Hh = 250;
          const top = Math.max(.3, ...A.map(a => a.stableHi)) * 1.1, bot = -.1;
          const y = v => Hh - padB - (Hh - padB - padT) * (v - bot) / (top - bot), gw = (700 - padL - 20) / A.length;
          [-.1, 0, .1, .2, .3].filter(v => v <= top).forEach(v => { el('line', { x1: padL, x2: 690, y1: y(v), y2: y(v), stroke: css(v === 0 ? '--ink-3' : '--grid') }, s);
            txt(s, padL - 6, y(v) + 4, num(v, 1), { anchor: 'end', size: 10, mono: true, ink: '--ink-3' }); });
          A.forEach((a, i) => {
            const cx = padL + gw * (i + .5), bw = 46;
            const b1 = el('rect', { x: cx - bw - 4, y: Math.min(y(a.obs), y(0)), width: bw, height: Math.abs(y(0) - y(a.obs)), rx: 4, fill: css('--s-strat') }, s);
            const b2 = el('rect', { x: cx + 4, y: Math.min(y(a.stableMean), y(0)), width: bw, height: Math.abs(y(0) - y(a.stableMean)), rx: 4, fill: css('--mark-soft') }, s);
            el('line', { x1: cx + 4 + bw / 2, x2: cx + 4 + bw / 2, y1: y(a.stableLo), y2: y(a.stableHi), stroke: css('--ink-2'), 'stroke-width': 1.5 }, s);
            txt(s, cx - bw / 2 - 4, y(a.obs) - 5, num(a.obs, 2), { anchor: 'middle', size: 10.5, mono: true });
            txt(s, cx, Hh - padB + 16, `${a.k} groups`, { anchor: 'middle', size: 11.5, ink: '--ink' });
            hoverable(b1, `<b>Real: session-1 groups vs session-2 groups, ${a.k} groups</b><br>agreement (ARI) ${num(a.obs, 3)}; 1 = the same people grouped together, 0 = chance<br>shuffled labels: 95% ${num(a.nullLo, 3)} to ${num(a.nullHi, 3)} (${pval(a.p)})<br>n = ${a.n} people`);
            hoverable(b2, `<b>Stable no-types simulations</b><br>same habit links and the same session-to-session stability, no types<br>mean ${num(a.stableMean, 3)}, 95% ${num(a.stableLo, 3)} to ${num(a.stableHi, 3)}<br>share at least as high as the real data: ${pct(a.pStable, 0)}`);
          });
          txt(s, 14, padT + (Hh - padB - padT) / 2, 'agreement (ARI; 0 = chance)', { anchor: 'middle', size: 11, rot: -90 });
          legend(box, [{ label: 'real: groups found in session 1 vs session 2', color: css('--s-strat') }, { label: 'no types, but people as stable as the real ones (95% whisker)', color: css('--mark-soft') }]);
          cap(box, `Each session is split into groups on its own, and we ask whether the same people end up together both times (adjusted Rand index: 1 = identical groupings, 0 = what chance gives). `
            + `Agreement is close to zero. It is a shade above pure chance, but no more than a smooth cloud gives when people simply keep their place in it from one session to the next.`);
        }
      };
      host.insertBefore(btnBar(host, 'Show', [['map', 'The people, mapped'], ['sep', 'Do groups separate?'], ['recur', 'Do groups come back?']], 'map', k => views[k]()), box);
      views.map();
    }),

    /* P3 · cards vs Suggest: between people (as before) or within a person (session-to-session change) */
    'style.axisScatter2': safe(host => {
      const A = D.axis, CS = D.pass3.axis.cardsSuggest, box = h('div', {}, host);
      const bin = v => v >= .8 ? '--lad-1' : v >= 0 ? '--lad-2' : v >= -.8 ? '--lad-3' : '--lad-4';
      const views = {
        between: () => {
          const s = svgRoot(box, 700, 340);
          scatterPanel(s, { x: 90, y: 20, w: 420, h: 270 }, A.people.map(p => ({ x: p.took, y: p.consult, r: 6, fill: css(bin(p.pc1)), op: .95,
            tip: `<b>${p.pid}</b><br>strategy cards taken ${pct(p.took, 0)} of ${p.n} decisions<br>Suggest pressed on ${pct(p.consult, 0)} of ${p.nT} tactical plans<br>reliance-axis score ${sgn(p.pc1, 2)} SD` })),
            { xmin: 0, xmax: 1.02, ymin: 0, ymax: 1.02, xticks: [0, .25, .5, .75, 1], yticks: [0, .25, .5, .75, 1], fx: v => pct(v, 0), fy: v => pct(v, 0),
              xlab: 'Strategic: % of strategic decisions where a card was taken', ylab: 'Tactical: % of plans with Suggest' });
          [['--lad-1', '≥ +0.8 SD'], ['--lad-2', '0 to +0.8'], ['--lad-3', '−0.8 to 0'], ['--lad-4', '< −0.8 SD']].forEach(([c, l], q) => {
            el('circle', { cx: 540, cy: 50 + q * 22, r: 6, fill: css(c), stroke: css('--line') }, s);
            txt(s, 552, 54 + q * 22, l, { size: 11 });
          });
          txt(s, 532, 30, 'Reliance-axis score', { size: 11, weight: 600, ink: '--ink' });
          txt(s, 532, 150, 'Cards vs Suggest:', { size: 10.5, ink: '--ink-3' });
          txt(s, 532, 166, `ρ = ${num(CS.raw.rho, 2)} [${num(CS.raw.lo, 2)}, ${num(CS.raw.hi, 2)}]`, { size: 10, mono: true });
          txt(s, 532, 181, `${pval(CS.raw.p)}, n = ${CS.raw.n}`, { size: 10, mono: true });
          txt(s, 532, 200, `game-adjusted: ρ = ${num(CS.between.rho, 2)}, ${pval(CS.between.p)}`, { size: 10, mono: true, ink: '--ink-3' });
          cap(box, `Each dot is a person, both sessions pooled. Between people the two go together only weakly: ${rho(CS.raw)}. Many people press Suggest on almost every plan (median 86% of plans) whatever their card uptake, which caps how strong the link can be.`);
        },
        within: () => {
          const s = svgRoot(box, 700, 340), P = CS.ptsW;
          const lim = Math.max(.3, ...P.map(p => Math.max(Math.abs(p.x), Math.abs(p.y)))) * 1.08;
          scatterPanel(s, { x: 90, y: 20, w: 420, h: 270 }, P.map(p => ({ x: p.x, y: p.y, r: 6, fill: css('--mark'), op: .8,
            tip: `<b>${p.pid}</b> (session 2 minus session 1, each game-adjusted)<br>card uptake ${sgn(100 * p.x, 0)} points<br>Suggest use ${sgn(100 * p.y, 0)} points` })),
            { xmin: -lim, xmax: lim, ymin: -lim, ymax: lim, xticks: [-.4, -.2, 0, .2, .4].filter(v => Math.abs(v) < lim), yticks: [-.4, -.2, 0, .2, .4].filter(v => Math.abs(v) < lim),
              fx: v => v === 0 ? '0' : sgn(100 * v, 0), fy: v => v === 0 ? '0' : sgn(100 * v, 0), zeroLines: true, fit: true,
              xlab: 'Change in % of decisions taking a card, session 1 → 2 (percentage points)', ylab: 'Change in % of plans with Suggest (pp)' });
          txt(s, 532, 40, 'Within a person:', { size: 11, weight: 600, ink: '--ink' });
          txt(s, 532, 58, `ρ = ${num(CS.within.rho, 2)} [${num(CS.within.lo, 2)}, ${num(CS.within.hi, 2)}]`, { size: 10, mono: true });
          txt(s, 532, 73, `${pval(CS.within.p)}, n = ${CS.within.n}`, { size: 10, mono: true });
          cap(box, `Each dot is a person: how much their card uptake (x) and their Suggest use (y) changed from their first session to their second, each measured against everyone who played the same game. `
            + `People who leaned more on the cards in one session also leaned more on Suggest in that session: ${rho(CS.within)}. The line is a least-squares guide.`);
        }
      };
      host.insertBefore(btnBar(host, 'Compare', [['between', 'Between people'], ['within', 'Within a person, session to session']], 'between', k => views[k]()), box);
      views.between();
    }),

    /* P3 · disposition grid plus how many nominal hits chance gives */
    'style.dispositionGrid2': safe(host => {
      CH['style.dispositionGrid'](h('div', {}, host));
      const P = D.pass3.dispPerm, hd = P.hitsDist, N = hd.reduce((a, b) => a + b, 0);
      const box = h('div', {}, host);
      h('p', { class: 'cap', html: `<b>Is three nominal hits out of 40 more than chance?</b> We shuffled which person’s questionnaire goes with which person’s behaviour ${P.nPerm} times and redid all 40 tests each time.` }, box);
      const s = svgRoot(h('div', {}, box), 700, 200), padL = 60, padB = 40, padT = 14, Hh = 200, mx = Math.max(...hd) / N * 1.15;
      const gw = (700 - padL - 20) / hd.length, y = v => Hh - padB - (Hh - padB - padT) * v / mx;
      [0, .1, .2, .3].filter(v => v < mx).forEach(v => { el('line', { x1: padL, x2: 690, y1: y(v), y2: y(v), stroke: css('--grid') }, s);
        txt(s, padL - 6, y(v) + 4, pct(v, 0), { anchor: 'end', size: 10, mono: true, ink: '--ink-3' }); });
      hd.forEach((c, k) => {
        const cx = padL + gw * (k + .5), on = k === P.nominal, more = k >= P.nominal;
        const b = el('rect', { x: cx - gw * .35, y: y(c / N), width: gw * .7, height: y(0) - y(c / N), rx: 3, fill: css(on ? '--s-strat' : more ? '--mark' : '--mark-soft'), 'fill-opacity': on ? 1 : .8 }, s);
        txt(s, cx, Hh - padB + 15, String(k), { anchor: 'middle', size: 10.5, mono: true });
        hoverable(b, `<b>${k} of 40 tests at p < .05</b><br>in ${c} of ${N} shuffles (${pct(c / N, 1)})` + (on ? '<br><i>what the real data gave</i>' : ''));
      });
      txt(s, padL + (700 - padL) / 2, Hh - 8, 'number of the 40 tests reaching p < .05 when the pairing of people is random', { anchor: 'middle', size: 11 });
      cap(box, `Blue = the real result (${P.nominal}); dark bars = as many or more. With no link at all, chance alone gives ${P.nominal} or more such “hits” in <b>${pct(P.pAtLeast, 0)}</b> of shuffles (average ${num(P.meanHits, 1)}). `
        + `And a correlation as strong as the real strongest one (p = ${num(P.minP, 3)}) turns up somewhere in the grid in ${pct(P.pMin, 0)} of shuffles.`);
    }),
    /* P4 · the grid alone; the Holm result and the shuffle check go into one caption */
    'style.dispositionGrid3': safe(host => {
      CH['style.dispositionGrid'](h('div', {}, host));
      const DP = D.disposition, P = (D.pass3 || {}).dispPerm;
      cap(host, `<b>Correcting for 40 tests:</b> ${DP.nNominal} of ${DP.nTests} correlations reach p < .05 before correction and ${DP.nHolm} survive Holm correction. `
        + (P ? `Chance alone gives ${num(P.meanHits, 1)} such nominal hits on average (${P.nominal} or more in ${pct(P.pAtLeast, 0)} of ${P.nPerm} shuffles of which person’s questionnaire goes with which behaviour), so the three outlined cells are about what no link at all would produce.` : ''));
    }),
  });
})();
