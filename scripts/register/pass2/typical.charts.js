/* Pass 5 · how typical is P36? Data: DATA.pass2.typical (written by scripts/register/pass2/typical.py).
   One row per measure: everyone as a grey dot on that measure's own range, the middle half shaded, the median
   ticked, P36 as the large dot, and a plain verdict on the right (typical / leans high or low / unusual). */
(() => {
  const D = (DATA.pass2 || {}).typical;
  const W = 760;
  const say = (host, msg) => h('p', { class: 'cap', text: msg }, host);
  const mono = () => css('--mono');
  const T = (s, x, y, t, a = {}) => { const n = el('text', Object.assign({ x, y, fill: css('--ink-2'), 'font-size': 12 }, a), s); n.textContent = t; return n; };
  const EXP = ['none', 'a little', 'moderate', 'extensive'];
  const fmt = (f, v) => v == null ? '—' : f === 'pct' ? pct(v, 0) : f === 'pp' ? sgn(100 * v, 0) + ' pts' : f === 's' ? num(v, 1) + ' s'
    : f === 'z' ? sgn(v, 2) : f === 'exp' ? EXP[Math.round(v)] || num(v, 0) : num(v, f.startsWith('scale') ? 1 : 1);
  const VERDICT = r => r.band === 'typical' ? 'typical' : (r.band === 'leans' ? 'leans ' : 'unusual · ') + r.side;
  const COL = { typical: '--ink-3', leans: '--warn', unusual: '--bad' };

  Object.assign(CH, {
    'typical.p36': host => {
      if (!D) return say(host, 'No data — run scripts/register/pass2/typical.py.');
      const rows = D.rows, groups = [...new Set(rows.map(r => r.group))];
      const rowH = 24, gapH = 26, padL = 300, padR = 190, padT = 6;
      const H = padT + rows.length * rowH + groups.length * gapH + 22;
      const s = svgRoot(h('div', {}, host), W, H);
      const x0 = padL, x1 = W - padR;
      let y = padT;
      groups.forEach(g => {
        y += gapH;
        T(s, 8, y - 8, g, { 'font-weight': 600, fill: css('--ink'), 'font-size': 12.5 });
        rows.filter(r => r.group === g).forEach(r => {
          const vals = r.people.map(p => p[1]);
          let lo = Math.min(...vals), hi = Math.max(...vals);
          if (r.fmt.startsWith('scale:')) [lo, hi] = r.fmt.slice(6).split('-').map(Number);
          if (r.fmt === 'exp') [lo, hi] = [0, 3];
          if (r.fmt === 'pct') [lo, hi] = [Math.min(0, lo), Math.max(1, hi)];
          const X = v => x0 + (x1 - x0) * (hi === lo ? .5 : (v - lo) / (hi - lo));
          const cy = y + rowH / 2;
          T(s, padL - 12, cy + 4, r.label, { 'text-anchor': 'end', 'font-size': 12 });
          el('line', { x1: x0, x2: x1, y1: cy, y2: cy, stroke: css('--grid') }, s);
          el('rect', { x: X(r.q1), y: cy - 8, width: Math.max(2, X(r.q3) - X(r.q1)), height: 16, rx: 3, fill: css('--grid'), opacity: .9 }, s);
          el('line', { x1: X(r.median), x2: X(r.median), y1: cy - 9, y2: cy + 9, stroke: css('--ink-3'), 'stroke-width': 2 }, s);
          // everyone else, stacked a little where values coincide
          const seen = {};
          r.people.forEach(([pid, v]) => {
            if (pid === D.who) return;
            const k = Math.round(X(v) / 4); seen[k] = (seen[k] || 0) + 1;
            const dy = ((seen[k] % 3) - 1) * 4;
            const c = el('circle', { cx: X(v), cy: cy + dy, r: 2.6, fill: css('--ink-3'), opacity: .55 }, s);
            hoverable(c, `${pid}: ${fmt(r.fmt, v)}`);
          });
          const col = css(COL[r.band]);
          const me = el('circle', { cx: X(r.me), cy, r: 6.5, fill: col, stroke: css('--surface'), 'stroke-width': 2 }, s);
          hoverable(me, `<b>${D.who}: ${fmt(r.fmt, r.me)}</b><br>median ${fmt(r.fmt, r.median)}, middle half ${fmt(r.fmt, r.q1)} to ${fmt(r.fmt, r.q3)}<br>percentile rank ${num(r.pctRank, 0)} of ${r.n} people`);
          T(s, x1 + 12, cy + 4, fmt(r.fmt, r.me), { 'font-family': mono(), 'font-size': 11.5 });
          T(s, x1 + 88, cy + 4, VERDICT(r), { 'font-size': 11.5, fill: col, 'font-weight': r.band === 'typical' ? 400 : 600 });
          const hit = el('rect', { x: 0, y, width: padL, height: rowH, fill: 'transparent' }, s);
          hoverable(hit, `<b>${r.label}</b><br>${D.who} ${fmt(r.fmt, r.me)} · median ${fmt(r.fmt, r.median)} · percentile rank ${num(r.pctRank, 0)}`);
          y += rowH;
        });
      });
      T(s, x0, H - 4, 'each row on its own scale · grey band = middle half of the 33 · tick = median', { fill: css('--ink-3'), 'font-size': 10.5 });
      const names = k => rows.filter(r => D[k].includes(r.key)).map(r => r.label);
      say(host, `Typical (middle half): ${names('typical').join('; ')}. Leaning (10th–25th or 75th–90th percentile): ${names('leans').join('; ')}. Unusual (beyond the 10th or 90th): ${names('unusual').join('; ')}.`);
    },
  });
})();
