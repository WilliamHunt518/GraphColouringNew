/* Shared by findings_synthesis_template.html and findings_brief_template.html; the builder
   inlines it at the COMMON_JS marker, straight after `const DATA`. Chart forms, content helpers,
   the data shorthands (C, S, N, SR, DP) and the hover glossary all live here so the two pages
   draw the same charts and define every term the same way. */
/* ───────────────────────── tiny DOM + SVG helpers ───────────────────────── */
const NS = 'http://www.w3.org/2000/svg';
const $ = id => document.getElementById(id);
function el(tag, attrs = {}, host) {
  const n = document.createElementNS(NS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  if (host) host.appendChild(n);
  return n;
}
function h(tag, attrs = {}, host) {
  const n = document.createElement(tag);
  for (const k in attrs) {
    if (k === 'html') n.innerHTML = attrs[k];
    else if (k === 'text') n.textContent = attrs[k];
    else n.setAttribute(k, attrs[k]);
  }
  if (host) host.appendChild(n);
  return n;
}
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const pct = (v, d = 1) => (100 * v).toFixed(d) + '%';
const num = (v, d = 1) => v == null || isNaN(v) ? '—' : (+v).toFixed(d);
const sgn = (v, d = 2) => (v >= 0 ? '+' : '') + (+v).toFixed(d);
function pval(p) {
  if (p == null || isNaN(p)) return '—';
  if (p < 0.001) return 'p < .001';
  return 'p = ' + p.toFixed(3).replace(/^0/, '');
}
/* p-value tiers, by the conventional thresholds: < .001, < .01, < .05, < .10 (marginal), ≥ .10. */
function pTier(p) {
  if (p == null || isNaN(p)) return '';
  return p < 0.001 ? 'p1' : p < 0.01 ? 'p2' : p < 0.05 ? 'p3' : p < 0.10 ? 'p4' : 'pns';
}
const P_TIER_LABEL = { p1: 'p < .001', p2: 'p < .01', p3: 'p < .05', p4: 'p < .10 (marginal)', pns: 'p ≥ .10 (not significant)' };
const pColour = p => { const t = pTier(p); return t === 'pns' || !t ? css('--ink-3') : css('--' + t); };
function pClass(p) { return (p != null && p < 0.05 ? 'sig' : 'ns') + ' pv ' + pTier(p); }
/* HTML for a p-value, already coloured. */
const pv = (p, label = 'p') => p == null || isNaN(p) ? '—'
  : `<span class="pv ${pTier(p)}" title="${P_TIER_LABEL[pTier(p)]}">${pval(p).replace(/^p/, label).replace("<", "&lt;")}</span>`;

/* Every p- or q-value written anywhere on a page ("p = .004", "p < .001", "q = .04", "p .07") is wrapped and
   coloured by tier, so no template has to remember to. SVG <text> gets a fill instead. Runs once the page has
   rendered and again on anything added later (tooltips, the model explorer). */
const P_RX = /(^|[\s(\[,;·:—–-])((?:adj(?:usted)?\.?\s+|Holm[- ]adjusted\s+|calibrated\s+|one-sided\s+|exact\s+)?(?:p|q))(\s*(?:=|<|≤|≈)\s*|\s+)(0?\.\d+|0|1(?:\.0+)?)(?![\d.])/g;
function tierFromMatch(op, v) {
  let x = parseFloat(v);
  if (/[<≤]/.test(op)) x -= 1e-9;
  return pTier(x);
}
function colourTextNode(n) {
  const t = n.nodeValue;
  P_RX.lastIndex = 0;
  if (!P_RX.test(t)) return;
  P_RX.lastIndex = 0;
  const frag = document.createDocumentFragment();
  let last = 0, m;
  while ((m = P_RX.exec(t))) {
    const start = m.index + m[1].length;
    // a bare space separator ("p .07") only counts when the number starts with a point
    if (!/[=<≤≈]/.test(m[3]) && !/^\./.test(m[4])) continue;
    frag.appendChild(document.createTextNode(t.slice(last, start)));
    const tier = tierFromMatch(m[3], m[4]);
    const sp = document.createElement('span');
    sp.className = 'pv ' + tier;
    sp.title = P_TIER_LABEL[tier] || '';
    sp.textContent = t.slice(start, m.index + m[0].length);
    frag.appendChild(sp);
    last = m.index + m[0].length;
  }
  if (!last) return;
  frag.appendChild(document.createTextNode(t.slice(last)));
  n.parentNode.replaceChild(frag, n);
}
function colourPValues(root) {
  if (!root || !root.ownerDocument && root !== document) return;
  const svgText = root.querySelectorAll ? root.querySelectorAll('svg text') : [];
  svgText.forEach(tx => {
    const m = /^\s*(?:p|q)\s*(=|<|≤)\s*(0?\.\d+|0|1)\s*$/.exec(tx.textContent);
    if (m) { const tier = tierFromMatch(m[1], m[2]); tx.setAttribute('fill', tier === 'pns' ? css('--ink-3') : css('--' + tier));
             tx.setAttribute('font-weight', tier === 'pns' ? 400 : 600); }
  });
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: n => {
      const pa = n.parentNode;
      if (!pa || pa.closest && pa.closest('script,style,svg,.pv,textarea,code')) return NodeFilter.FILTER_REJECT;
      return /[pq]/.test(n.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    } });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach(colourTextNode);
}
function pKey(host, before) {
  const d = document.createElement('div');
  d.className = 'pkey';
  d.innerHTML = 'p-values coloured by threshold: ' + ['p1', 'p2', 'p3', 'p4', 'pns']
    .map(t => `<span class="pv ${t}">${P_TIER_LABEL[t]}</span>`).join(' ');
  if (before) host.insertBefore(d, before); else host.appendChild(d);
  return d;
}
window.addEventListener('DOMContentLoaded', () => {
  const mainEl = document.getElementById('main');
  if (!mainEl) return;
  colourPValues(mainEl);
  const meta = mainEl.querySelector('p.meta');
  if (meta && mainEl.querySelector('.pv')) pKey(mainEl, meta.nextSibling);
  let queued = false;
  const pending = new Set();
  new MutationObserver(muts => {
    muts.forEach(mu => mu.addedNodes.forEach(n => { if (n.nodeType === 1 && !n.classList.contains('pv')) pending.add(n); }));
    if (!queued && pending.size) {
      queued = true;
      requestAnimationFrame(() => { queued = false; const xs = [...pending]; pending.clear(); xs.forEach(colourPValues); });
    }
  }).observe(document.body, { childList: true, subtree: true });
});

/* tooltip */
const tip = $('tip');
function showTip(e, html, wide) {
  tip.innerHTML = html;
  tip.classList.toggle('wide', !!wide);
  tip.style.opacity = 1;
  const r = tip.getBoundingClientRect();
  let x = e.clientX + 14, y = e.clientY - r.height - 10;
  if (x + r.width > innerWidth - 8) x = e.clientX - r.width - 14;
  if (y < 8) y = e.clientY + 16;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}
function hideTip() { tip.style.opacity = 0; }
function hoverable(node, html) {
  node.addEventListener('mousemove', e => showTip(e, html));
  node.addEventListener('mouseleave', hideTip);
}

function svgRoot(host, w, hgt) {
  host.innerHTML = '';
  const s = el('svg', { viewBox: `0 0 ${w} ${hgt}`, role: 'img' }, host);
  return s;
}
function legend(host, items) {
  const l = h('div', { class: 'legend' }, host);
  items.forEach(it => {
    const s = h('span', {}, l);
    h('i', { style: `background:${it.color}` }, s);
    h('span', { text: it.label }, s);
  });
  return l;
}
function tableFor(host, cols, rows, label) {
  const d = h('details', { class: 'tbl' }, host);
  h('summary', { text: label || 'Show the numbers' }, d);
  const t = h('table', {}, d);
  const thead = h('thead', {}, t), tr = h('tr', {}, thead);
  cols.forEach((c, i) => h('th', { text: c, class: i ? 'num' : '' }, tr));
  const tb = h('tbody', {}, t);
  rows.forEach(r => {
    const x = h('tr', {}, tb);
    r.forEach((v, i) => {
      const td = h('td', { text: v && v.g ? v.text : v, class: i ? 'num' : '' }, x);
      if (v && v.g) glNode(td, v.g);
    });
  });
}

/* ───────────────────────── chart forms ───────────────────────── */

/* Horizontal bars: one series, magnitude by category. Direct-labelled, no legend needed. */
function barsH(host, rows, o = {}) {
  const W = 700, rowH = o.rowH || 30, padL = o.padL || 150, padR = 66, padT = 6;
  const H = padT + rows.length * rowH + 8;
  const s = svgRoot(host, W, H);
  const max = o.max != null ? o.max : Math.max(...rows.map(r => r.value)) * 1.06 || 1;
  const x = v => padL + (W - padL - padR) * (v / max);
  rows.forEach((r, i) => {
    const y = padT + i * rowH, bh = Math.min(15, rowH - 12);
    el('text', { x: padL - 10, y: y + rowH / 2 + 4, 'text-anchor': 'end',
                 fill: css('--ink-2'), 'font-size': 12.5 }, s).textContent = r.label;
    el('rect', { x: padL, y: y + (rowH - bh) / 2, width: Math.max(0, x(r.value) - padL), height: bh,
                 rx: 4, fill: r.color || css('--mark') }, s);
    const t = el('text', { x: x(r.value) + 8, y: y + rowH / 2 + 4, fill: css('--ink-2'),
                           'font-size': 12, 'font-family': css('--mono') }, s);
    t.textContent = o.fmt ? o.fmt(r.value) : pct(r.value);
    const hit = el('rect', { x: padL, y, width: W - padL - padR, height: rowH, fill: 'transparent' }, s);
    hoverable(hit, `<b>${r.label}</b><br>${o.fmt ? o.fmt(r.value) : pct(r.value)}${r.sub ? '<br>' + r.sub : ''}`);
  });
  el('line', { x1: padL, y1: padT, x2: padL, y2: H - 8, stroke: css('--line'), 'stroke-width': 1 }, s);
}

/* Grouped vertical bars: a few series across a few categories. */
function barsGrouped(host, cats, series, o = {}) {
  const W = 700, H = o.height || 250, padL = 52, padB = 40, padT = 14, padR = 10;
  const s = svgRoot(host, W, H);
  const all = series.flatMap(se => se.values.filter(v => v != null));
  const max = o.max != null ? o.max : Math.max(...all) * 1.12;
  const y = v => H - padB - (H - padB - padT) * (v / max);
  const bandW = (W - padL - padR) / cats.length;
  const gap = 2, bw = Math.min(42, (bandW - 26 - gap * (series.length - 1)) / series.length);
  // `o.ticks` is the number of INTERVALS, so n+1 gridlines are drawn and the top one lands on the
  // maximum. (Written as `Array(o.ticks || 4 + 1)` it parsed as `o.ticks || 5`, which made a
  // caller-supplied count both the divisor and one short of its own gridline count; the default of
  // 4 is unchanged by the fix.)
  const nTicks = o.ticks == null ? 4 : o.ticks;
  nTicks && [...Array(nTicks + 1).keys()].forEach(i => {
    const v = max * i / nTicks;
    el('line', { x1: padL, x2: W - padR, y1: y(v), y2: y(v), stroke: css('--grid'), 'stroke-width': 1 }, s);
    el('text', { x: padL - 8, y: y(v) + 4, 'text-anchor': 'end', fill: css('--ink-3'),
                 'font-size': 11, 'font-family': css('--mono') }, s).textContent = o.fmt ? o.fmt(v) : num(v, 0);
  });
  cats.forEach((c, ci) => {
    const cx = padL + bandW * ci + bandW / 2;
    el('text', { x: cx, y: H - padB + 17, 'text-anchor': 'middle', fill: css('--ink-2'),
                 'font-size': 12 }, s).textContent = c;
    const total = series.length * bw + gap * (series.length - 1);
    series.forEach((se, si) => {
      const v = se.values[ci];
      if (v == null) return;
      const bx = cx - total / 2 + si * (bw + gap);
      el('rect', { x: bx, y: y(v), width: bw, height: Math.max(0, H - padB - y(v)), rx: 4,
                   fill: se.color }, s);
      const t = el('text', { x: bx + bw / 2, y: y(v) - 5, 'text-anchor': 'middle',
                             fill: css('--ink-2'), 'font-size': 11, 'font-family': css('--mono') }, s);
      t.textContent = o.fmt ? o.fmt(v) : num(v, 1);
      const hit = el('rect', { x: bx, y: padT, width: bw, height: H - padB - padT, fill: 'transparent' }, s);
      hoverable(hit, `<b>${se.label}</b><br>${c}: ${o.fmt ? o.fmt(v) : num(v, 1)}${se.subs && se.subs[ci] ? '<br>' + se.subs[ci] : ''}`);
    });
  });
  el('line', { x1: padL, x2: W - padR, y1: H - padB, y2: H - padB, stroke: css('--line') }, s);
}

/* 100% stacked bars, one row per category. 2px surface gap between segments. */
function barsStacked(host, rows, keys, o = {}) {
  const W = 700, rowH = 40, padL = o.padL || 120, padR = 12, padT = 4;
  const H = padT + rows.length * rowH + 6;
  const s = svgRoot(host, W, H);
  const span = W - padL - padR;
  rows.forEach((r, i) => {
    const y = padT + i * rowH, bh = 20;
    el('text', { x: padL - 10, y: y + rowH / 2 + 4, 'text-anchor': 'end', fill: css('--ink-2'),
                 'font-size': 12.5 }, s).textContent = r.label;
    let acc = 0;
    keys.forEach(k => {
      const v = r.values[k.key] || 0;
      if (v <= 0) return;
      const x0 = padL + span * acc, w = span * v;
      el('rect', { x: x0, y: y + (rowH - bh) / 2, width: Math.max(0, w - 2), height: bh, rx: 3,
                   fill: k.color }, s);
      if (w > 44) {
        el('text', { x: x0 + w / 2 - 1, y: y + rowH / 2 + 4, 'text-anchor': 'middle',
                     fill: k.ink || '#fff', 'font-size': 11, 'font-family': css('--mono') }, s)
          .textContent = pct(v, 0);
      }
      const hit = el('rect', { x: x0, y: y + (rowH - bh) / 2, width: Math.max(0, w - 2), height: bh,
                               fill: 'transparent' }, s);
      hoverable(hit, `<b>${k.label}</b><br>${r.label}: ${pct(v)}${r.sub ? '<br>' + r.sub : ''}`);
      acc += v;
    });
  });
}

/* Diverging bars around a zero baseline. One series; polarity carried by position, so no
   second hue is introduced -- the sign is unambiguous and a legend would add nothing. */
function barsDiverging(host, rows, o = {}) {
  const W = 700, rowH = o.rowH || 36, padL = o.padL || 132, padR = 74, padT = 8;
  const H = padT + rows.length * rowH + 22;
  const s = svgRoot(host, W, H);
  const mx = Math.max(...rows.map(r => Math.abs(r.value))) * 1.25 || 1;
  const mid = padL + (W - padL - padR) / 2;
  const x = v => mid + ((W - padL - padR) / 2) * (v / mx);
  el('line', { x1: mid, y1: padT, x2: mid, y2: H - 22, stroke: css('--line'), 'stroke-width': 1.5 }, s);
  el('text', { x: mid, y: H - 6, 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 11,
               'font-family': css('--mono') }, s).textContent = o.zeroLabel || 'same as the card';
  rows.forEach((r, i) => {
    const y = padT + i * rowH, bh = 16;
    el('text', { x: padL - 10, y: y + rowH / 2 + 4, 'text-anchor': 'end', fill: css('--ink-2'),
                 'font-size': 12.5 }, s).textContent = r.label;
    const x0 = Math.min(mid, x(r.value)), w = Math.abs(x(r.value) - mid);
    // A row can opt out of the ink: a correlation that does not survive correction is drawn in the
    // soft tone so the eye is not pulled to it. Magnitude still reads; emphasis does not.
    el('rect', { x: x0, y: y + (rowH - bh) / 2, width: w, height: bh, rx: 4,
                 fill: css(r.faint ? '--mark-soft' : '--mark') }, s);
    const right = r.value >= 0;
    const lab = o.fmt ? o.fmt(r.value) : sgn(r.value);
    el('text', { x: right ? x(r.value) + 8 : x(r.value) - 8, y: y + rowH / 2 + 4,
                 'text-anchor': right ? 'start' : 'end', fill: css('--ink-2'), 'font-size': 12,
                 'font-family': css('--mono') }, s).textContent = lab;
    const hit = el('rect', { x: padL, y, width: W - padL - padR, height: rowH, fill: 'transparent' }, s);
    hoverable(hit, `<b>${r.label}</b><br>${lab}${o.unit != null ? o.unit : ' drones'}`
      + `${r.sub ? '<br>' + r.sub : ''}`);
  });
}

/* Coefficient plot with confidence intervals -- for the three nested models. */
function forest(host, rows, o = {}) {
  const W = 700, rowH = 34, padL = o.padL || 210, padR = 90, padT = 12;
  const H = padT + rows.length * rowH + 48;
  const s = svgRoot(host, W, H);
  const lim = o.lim || Math.max(...rows.flatMap(r => [Math.abs(r.lo), Math.abs(r.hi)])) * 1.15 || 1;
  const mid = padL + (W - padL - padR) / 2;
  const half = (W - padL - padR) / 2;
  const x = v => mid + half * (v / lim);
  const base = padT + rows.length * rowH + 2;
  // A real axis: ticks in log-odds with the odds-ratio equivalent underneath, because "b = +0.30"
  // means nothing on its own. OR = e^b, so 0 -> 1.0 (no change in the odds).
  [-lim * 0.75, -lim * 0.375, 0, lim * 0.375, lim * 0.75].forEach(v => {
    el('line', { x1: x(v), x2: x(v), y1: padT - 4, y2: base, stroke: css('--grid'), 'stroke-width': 1 }, s);
    el('text', { x: x(v), y: base + 14, 'text-anchor': 'middle', fill: css('--ink-3'),
                 'font-size': 10.5, 'font-family': css('--mono') }, s).textContent = v.toFixed(1);
    el('text', { x: x(v), y: base + 27, 'text-anchor': 'middle', fill: css('--ink-3'),
                 'font-size': 10, 'font-family': css('--mono') }, s)
      .textContent = '×' + Math.exp(v).toFixed(2);
  });
  el('line', { x1: padL, x2: W - padR, y1: base, y2: base, stroke: css('--line') }, s);
  el('line', { x1: mid, y1: padT - 4, x2: mid, y2: base, stroke: css('--ink-3'), 'stroke-width': 1.5 }, s);
  el('text', { x: mid, y: padT - 8, 'text-anchor': 'middle', fill: css('--ink-3'), 'font-size': 10.5,
               'font-family': css('--mono') }, s).textContent = 'no effect';
  el('text', { x: padL, y: base + 27, 'text-anchor': 'start', fill: css('--ink-3'), 'font-size': 10,
               'font-family': css('--mono') }, s).textContent = '← less likely';
  el('text', { x: W - padR, y: base + 27, 'text-anchor': 'end', fill: css('--ink-3'), 'font-size': 10,
               'font-family': css('--mono') }, s).textContent = 'more likely →';
  rows.forEach((r, i) => {
    const y = padT + i * rowH + rowH / 2;
    const lt = el('text', { x: padL - 12, y: y + 4, 'text-anchor': 'end', fill: css('--ink-2'),
                            'font-size': 12.5 }, s);
    lt.textContent = r.label;
    if (r.g) lt.setAttribute('data-g', r.g);
    const sig = r.p < 0.05;
    const col = sig ? css('--mark') : css('--mark-soft');
    el('line', { x1: x(r.lo), x2: x(r.hi), y1: y, y2: y, stroke: col, 'stroke-width': 2,
                 'stroke-linecap': 'round' }, s);
    el('circle', { cx: x(r.b), cy: y, r: 5, fill: col, stroke: css('--surface'), 'stroke-width': 2 }, s);
    el('text', { x: W - padR + 10, y: y + 4, fill: pColour(r.p), 'font-weight': r.p < 0.10 ? 600 : 400,
                 'font-size': 11.5, 'font-family': css('--mono') }, s).textContent = pval(r.p);
    const hit = el('rect', { x: padL, y: y - rowH / 2, width: W - padL - padR, height: rowH,
                             fill: 'transparent' }, s);
    hoverable(hit, `<b>${r.label}</b><br>odds ×${Math.exp(r.b).toFixed(2)} `
      + `[${Math.exp(r.lo).toFixed(2)}, ${Math.exp(r.hi).toFixed(2)}]<br>b = ${sgn(r.b, 3)} · ${pval(r.p)}`);
  });
}


/* Lines over an ordered x, with a marked event at x = 0. Crosshair + tooltip on hover. */
function linesAt(host, series, o = {}) {
  const W = 700, H = o.height || 270, padL = 48, padR = o.padR || 156, padT = 16, padB = 42;
  const s = svgRoot(host, W, H);
  const xs = [...new Set(series.flatMap(se => se.points.map(pt => pt.x)))].sort((a, b) => a - b);
  const x = v => padL + (W - padL - padR) * ((v - xs[0]) / Math.max(1, xs[xs.length - 1] - xs[0]));
  const y = v => H - padB - (H - padB - padT) * v;
  [0, .25, .5, .75, 1].forEach(v => {
    el('line', { x1: padL, x2: W - padR, y1: y(v), y2: y(v), stroke: css('--grid') }, s);
    el('text', { x: padL - 8, y: y(v) + 4, 'text-anchor': 'end', fill: css('--ink-3'),
                 'font-size': 11, 'font-family': css('--mono') }, s).textContent = pct(v, 0);
  });
  if (o.markZero !== false && xs[0] <= 0 && xs[xs.length - 1] >= 0) {
    el('line', { x1: x(0), x2: x(0), y1: padT - 6, y2: H - padB, stroke: css('--bad'),
                 'stroke-width': 1.5, 'stroke-dasharray': '4 3' }, s);
    el('text', { x: x(0), y: padT - 10, 'text-anchor': 'middle', fill: css('--bad'),
                 'font-size': 10.5, 'font-family': css('--mono') }, s)
      .textContent = o.zeroLabel || 'first illogical card';
  }
  xs.forEach(v => el('text', { x: x(v), y: H - padB + 17, 'text-anchor': 'middle',
                               fill: css('--ink-3'), 'font-size': 10.5,
                               'font-family': css('--mono') }, s)
    .textContent = (v > 0 ? '+' : '') + v);
  el('text', { x: (padL + W - padR) / 2, y: H - 6, 'text-anchor': 'middle', fill: css('--ink-3'),
               'font-size': 11 }, s).textContent = o.xLabel || 'decisions relative to that card';
  series.forEach(se => {
    const pts = se.points.slice().sort((a, b) => a.x - b.x);
    const d = pts.map((pt, i) => (i ? 'L' : 'M') + x(pt.x) + ' ' + y(pt.y)).join(' ');
    el('path', { d, fill: 'none', stroke: se.color, 'stroke-width': 2, 'stroke-linejoin': 'round',
                 'stroke-linecap': 'round', opacity: se.faint ? .5 : 1 }, s);
    pts.forEach(pt => {
      el('circle', { cx: x(pt.x), cy: y(pt.y), r: 4, fill: se.color, stroke: css('--surface'),
                     'stroke-width': 1.5 }, s);
      const hit = el('circle', { cx: x(pt.x), cy: y(pt.y), r: 12, fill: 'transparent' }, s);
      hoverable(hit, '<b>' + se.label + '</b><br>' + (pt.x > 0 ? '+' : '') + pt.x + ': '
        + pct(pt.y) + (pt.n ? '<br>n = ' + pt.n : ''));
    });
    const last = pts[pts.length - 1];
    el('text', { x: x(last.x) + 10, y: y(last.y) + 4, fill: se.color, 'font-size': 11.5,
                 'font-weight': 600 }, s).textContent = se.label;
  });
}

/* Paired slope chart: one line per participant between two conditions.
   Defaults to a 0-1 proportion axis labelled as percentages; `o.lo`/`o.hi`/`o.fmt`/`o.ticks` carry
   a scale that is not a proportion (the 1-7 trust scales) without touching the proportion callers. */
function slopes(host, pairs, o = {}) {
  const W = 700, H = o.height || 260, padT = 18, padB = 34, padL = 150, padR = 150;
  const s = svgRoot(host, W, H);
  const lo = o.lo != null ? o.lo : 0, hi = o.hi != null ? o.hi : 1;
  const fmt = o.fmt || (v => pct(v, 0));
  const y = v => H - padB - (H - padB - padT) * ((v - lo) / (hi - lo));
  const xa = padL, xb = W - padR;
  (o.ticks || [lo, (lo + hi) / 2, hi]).forEach(v => {
    el('line', { x1: xa - 30, x2: xb + 30, y1: y(v), y2: y(v), stroke: css('--grid') }, s);
    el('text', { x: xa - 40, y: y(v) + 4, 'text-anchor': 'end', fill: css('--ink-3'),
                 'font-size': 11, 'font-family': css('--mono') }, s).textContent = fmt(v);
  });
  pairs.forEach(pr => {
    const up = pr.b >= pr.a;
    el('line', { x1: xa, y1: y(pr.a), x2: xb, y2: y(pr.b), stroke: css('--mark-soft'),
                 'stroke-width': 1.5, opacity: .75 }, s);
    [[xa, pr.a], [xb, pr.b]].forEach(([cx, v]) =>
      el('circle', { cx, cy: y(v), r: 3.5, fill: css('--mark-soft') }, s));
    const hit = el('line', { x1: xa, y1: y(pr.a), x2: xb, y2: y(pr.b), stroke: 'transparent',
                             'stroke-width': 12 }, s);
    hoverable(hit, '<b>' + pr.label + '</b><br>' + o.aLabel + ': ' + fmt(pr.a) + '<br>'
      + o.bLabel + ': ' + fmt(pr.b));
  });
  const ma = pairs.reduce((s2, p) => s2 + p.a, 0) / pairs.length;
  const mb = pairs.reduce((s2, p) => s2 + p.b, 0) / pairs.length;
  el('line', { x1: xa, y1: y(ma), x2: xb, y2: y(mb), stroke: css('--s-strat'), 'stroke-width': 3,
               'stroke-linecap': 'round' }, s);
  [[xa, ma], [xb, mb]].forEach(([cx, v]) =>
    el('circle', { cx, cy: y(v), r: 6, fill: css('--s-strat'), stroke: css('--surface'),
                   'stroke-width': 2 }, s));
  el('text', { x: xa - 40, y: y(ma) - 12, 'text-anchor': 'end', fill: css('--s-strat'),
               'font-size': 11.5, 'font-weight': 600 }, s).textContent = 'mean ' + fmt(ma);
  el('text', { x: xb + 40, y: y(mb) - 12, 'text-anchor': 'start', fill: css('--s-strat'),
               'font-size': 11.5, 'font-weight': 600 }, s).textContent = 'mean ' + fmt(mb);
  [[xa, o.aLabel], [xb, o.bLabel]].forEach(([cx, lab]) =>
    el('text', { x: cx, y: H - 10, 'text-anchor': 'middle', fill: css('--ink-2'),
                 'font-size': 12 }, s).textContent = lab);
}

/* ───────────────────────── content helpers ───────────────────────── */
const Q = {};
DATA.narration.quotes.forEach(q => { Q[q.id] = q; });

/* What the participant was being asked when they said it. The theme is the CODER's label for the
   topic, not a record of what the operator was doing at that moment -- every quote on this page
   comes from the post-session debrief, after the task was over. See the standing note in the
   Reading section. */
const THEME_CONTEXT = {
  overall_experience: 'asked how they found the task',
  agent_comparison: 'asked to compare the two assistants',
  scenario_comparison: 'asked to compare the two scenarios',
  trust_trajectory: 'asked whether their reliance changed over time',
  verification: 'asked whether and how they checked the advice',
  manual_override: 'asked why they built allocations by hand',
  interface_legibility: 'on what they could not read or find',
  general_ai_disposition: 'asked about AI tools in general',
  real_world_transfer: 'asked whether this would work in practice',
  design_suggestions: 'asked what they would change',
};
const mmss = t => `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`;

function quote(host, id, opts = {}) {
  const q = Q[id];
  if (!q) { h('p', { class: 'note', text: 'missing quote: ' + id }, host); return; }
  const b = h('blockquote', q.expert ? { class: 'expert' } : {}, host);
  h('p', { text: '“' + (opts.trim || q.text) + '”' }, b);
  const a = h('span', { class: 'attr' }, b);
  a.innerHTML = `<span class="pid">${q.pid}</span> · post-session debrief, ${mmss(q.at)} into the `
    + `recording · ${THEME_CONTEXT[q.theme] || q.theme.replace(/_/g, ' ')}`;
  if (q.expert) h('span', { class: 'badge', text: 'CONSULTED EXPERT' }, a);
  return b;
}
function para(host, html) { h('p', { html }, host); }
function note(host, html) { h('div', { class: 'note', html }, host); }
let FINDING_N = 0;
function section(id, kicker, title) {
  const s = h('section', { id }, $('main'));
  const hd = h('div', { class: 'sec-head' }, s);
  // 'Finding' auto-numbers in document order; anything else is used verbatim. Hand-numbering
  // these desynced the moment a section moved, so the number is derived, never written down.
  h('div', { class: 'kicker', text: kicker === 'Finding' ? 'Finding ' + (++FINDING_N) : kicker }, hd);
  h('h2', { text: title }, hd);
  return s;
}
function card(host, title) {
  const c = h('div', { class: 'card' }, host);
  if (title) h('h4', { text: title }, c);
  return c;
}
function tiles(host, items) {
  const t = h('div', { class: 'tiles' }, host);
  items.forEach(i => {
    const d = h('div', { class: 'tile' }, t);
    h('span', { class: 'v', text: i.v }, d);
    h('span', { class: 'k', text: i.k }, d);
    if (i.s) h('span', { class: 's', text: i.s }, d);
  });
}

/* ───────────────────────── the page ───────────────────────── */
const C = DATA.computed, S = DATA.study, N = DATA.narration;
const SR = DATA.selfreport, DP = DATA.disposition;
const main = $('main');

/* ───────────────────────── glossary ─────────────────────────
   One entry per term the page uses. `what` says what it measures, `read` says how to read the
   number shown for it, and `here` (where the builder supplies a spread) says what this sample
   actually scored, because "4.2 on a 1–7 scale" means little without that. Any element carrying
   data-g="<key>" shows the entry on hover, and the Glossary section at the end lists them all. */
const spreadOf = (key, fmt) => {
  const d = (DP.dist || {})[key];
  return d ? `In this sample (n = ${d.n} operators): average ${fmt(d.mean)}, `
    + `lowest ${fmt(d.lo)}, highest ${fmt(d.hi)}.` : '';
};
const alphaOf = i => DP.batteries && DP.batteries[i] ? num(DP.batteries[i].alpha, 2) : '—';
const f1 = v => num(v, 1), f2 = v => num(v, 2), fp = v => pct(v, 0);
const EXP_READ = 'Each answer is coded None = 0, A little = 1, Moderate = 2, Extensive = 3.';
const SPLIT_READ = 'Operators are split at the median answer; the “more experienced half” '
  + 'is everyone above it.';
const PER_PERSON = ' In the disposition grid each operator’s value is the average of their two sessions.';
const GLOSS = {
  // — what operators brought with them —
  aias: { term: 'AIAS-4 attitude to AI', group: 'Disposition (pre-study questionnaire)',
    what: 'A published, validated four-item questionnaire on general attitude to AI (Grassini, '
      + '2023): “AI will improve my life”, “AI will improve my work”, “I will use AI technology in '
      + 'the future”, “AI technology is positive for humanity”.',
    read: 'The average of the four answers, each on a 1–10 scale. 1 = entirely negative about AI, '
      + '10 = entirely positive.', here: () => spreadOf('aias', f1) },
  verification: { term: 'Verification propensity', group: 'Disposition (pre-study questionnaire)',
    what: 'How much someone habitually checks an AI’s output before relying on it. Six statements '
      + 'written for this study, e.g. “I usually check an AI tool’s work before relying on it” and, '
      + 'worded the other way round, “Most AI tools are reliable enough that checking their work '
      + 'is unnecessary”.',
    read: () => 'The average on a 1–7 scale, after flipping the three statements worded the other '
      + 'way. 1 = happy to use AI output unchecked, 7 = always wants to check it. The six items '
      + `do not hang together well (α = ${alphaOf(1)}), so this score is noisy.`,
    here: () => spreadOf('verification', f2) },
  delegation: { term: 'Delegation boundary', group: 'Disposition (pre-study questionnaire)',
    what: 'Where someone draws the line on handing decisions to an AI: how much authority they '
      + 'think should stay with a human. Five statements written for this study: a human should '
      + 'make the final decision; I trust AI more for suggesting options than for making decisions; '
      + 'I would rather do a task myself even if slower; AI should not be relied on when lives are '
      + 'at stake; and, worded the other way round, in an urgent situation an AI recommendation is '
      + 'better than none.',
    read: () => 'The average on a 1–7 scale, after flipping the reversed statement. 1 = happy to '
      + 'hand decisions to AI, 7 = humans should keep the authority. The five items do not hang '
      + `together well (α = ${alphaOf(2)}), so this score is noisy.`,
    here: () => spreadOf('delegation', f2) },
  delegTrustSuggestOverDecide: { term: '“Trust AI more for suggesting than deciding”',
    group: 'Disposition (pre-study questionnaire)',
    what: 'One delegation statement on its own: “I trust AI more for suggesting options than for '
      + 'making decisions.” Written to mirror this study’s two tiers: the Strategic Assistant '
      + 'suggests, the Tactical Assistant plans what actually happens.',
    read: 'A single answer, 1 = strongly disagree to 7 = strongly agree.',
    here: () => spreadOf('delegTrustSuggestOverDecide', f1) },
  delegHumanFinalSay: { term: '“A human should make the final decision”',
    group: 'Disposition (pre-study questionnaire)',
    what: 'One delegation statement on its own: “A human should make the final decision even when '
      + 'an AI recommendation is available.”',
    read: 'A single answer, 1 = strongly disagree to 7 = strongly agree.',
    here: () => spreadOf('delegHumanFinalSay', f1) },
  errorDetectability: { term: '“Hard to tell when AI has erred”',
    group: 'Disposition (pre-study questionnaire)',
    what: '“I find it difficult to tell when an AI tool has made a mistake.” Asked alongside the '
      + 'verification items but kept out of that score: it is about how hard errors are to spot, '
      + 'not about a habit of checking.',
    read: 'A single answer, 1 = strongly disagree (errors are easy to spot) to 7 = strongly agree '
      + '(errors are hard to spot).', here: () => spreadOf('errorDetectability', f1) },
  experienceMean: { term: 'Prior experience (mean of five items)',
    group: 'Disposition (pre-study questionnaire)',
    what: 'Five questions on prior experience: simulation software; real-time strategy games; '
      + 'operating drones; automation / AI assistants; emergency dispatch, air traffic control or '
      + 'military command.',
    read: EXP_READ + ' The five are averaged, so 0 = no experience of any of them and 3 = '
      + 'extensive experience of all of them.', here: () => spreadOf('experienceMean', f2) },
  autonomyExperience: { term: 'Experience with automation / AI',
    group: 'Disposition (pre-study questionnaire)',
    what: 'One question: “Experience working with automation, AI assistants, or autonomous systems.”',
    read: EXP_READ, here: () => spreadOf('autonomyExperience', f1) },

  // — prior-experience axes used in the median split —
  autonomy_experience: { term: 'Automation / AI assistants', group: 'Prior experience',
    what: '“Experience working with automation, AI assistants, or autonomous systems.”',
    read: EXP_READ + ' ' + SPLIT_READ },
  strategy_experience: { term: 'Real-time strategy games', group: 'Prior experience',
    what: '“Experience with real-time strategy or resource-management games.”',
    read: EXP_READ + ' ' + SPLIT_READ },
  sim_experience: { term: 'Simulation software', group: 'Prior experience',
    what: '“Experience with simulation software or simulation games.”',
    read: EXP_READ + ' ' + SPLIT_READ },
  command_experience: { term: 'Dispatch / command / ATC', group: 'Prior experience',
    what: '“Experience with emergency management, dispatch, air traffic control, or military command.”',
    read: EXP_READ + ' ' + SPLIT_READ + ' Most operators answered None, so here the “more '
      + 'experienced half” just means anyone with any experience.' },
  drone_experience: { term: 'Operating drones', group: 'Prior experience',
    what: '“Experience operating drones or UAVs.”',
    read: EXP_READ + ' ' + SPLIT_READ + ' Most operators answered None, so here the “more '
      + 'experienced half” just means anyone with any experience.' },
  gaming_frequency: { term: 'Plays video games', group: 'Prior experience',
    what: 'How often they play video games.',
    read: 'Coded Never = 0, Rarely = 1, Occasionally = 2, Weekly = 3, Daily = 4. ' + SPLIT_READ },

  // — what operators did —
  took: { term: 'Took a strategy card', group: 'Behaviour (from the event logs)',
    what: 'Each mission the operator allocates is one strategic decision: take the Aggressive card, '
      + 'take the Conservative card, or allocate drones by hand (Manual). This is the share of '
      + 'those decisions that went to one of the two cards.',
    read: 'A proportion. 60% means 6 in every 10 missions were allocated by accepting a card as '
      + 'offered; the other 4 were Manual.' + PER_PERSON, here: () => spreadOf('took', fp) },
  consult: { term: 'Consulted the tactical plan', group: 'Behaviour (from the event logs)',
    what: 'After allocating, the operator assigns drones to tasks in the tactical planner, which '
      + 'starts empty. This is the share of deployed plans where they pressed Suggest at least '
      + 'once to see the Tactical Assistant’s plan. Pressing it is a deliberate choice.',
    read: 'A proportion. 40% means they looked at the assistant’s plan for 4 in every 10 '
      + 'plans they deployed.' + PER_PERSON, here: () => spreadOf('consult', fp) },
  accept: { term: 'Took the tactical plan unmodified', group: 'Behaviour (from the event logs)',
    what: 'The share of deployed tactical plans where the operator pressed Suggest and then '
      + 'deployed the assistant’s plan exactly as given, without changing a single assignment.',
    read: 'A proportion of all deployed plans, not just the consulted ones. 20% means 2 in '
      + 'every 10 plans were the assistant’s, untouched.' + PER_PERSON,
    here: () => spreadOf('accept', fp) },
  secs: { term: 'Strategic decision time', group: 'Behaviour (from the event logs)',
    what: 'Seconds from the strategic panel opening to the operator’s choice (a card or Manual). '
      + 'The cards stay unreadable for the first 4–5 seconds, so taking a card can never be '
      + 'quicker than that.',
    read: 'The median over that session’s decisions, in seconds. Higher = slower.' + PER_PERSON,
    here: () => spreadOf('secs', v => num(v, 1) + 's') },
  score: { term: 'Session score', group: 'Behaviour (from the event logs)',
    what: 'Points for every task completed (20 to 100 depending on task type, bigger tasks worth '
      + 'more), minus a penalty that builds up every second a mission’s tasks are left unfinished. '
      + 'Higher-category missions build penalty faster. It never goes below 0.',
    read: 'Points for one 8-minute session. Higher = better.' + PER_PERSON,
    here: () => spreadOf('score', v => num(v, 0)) },

  // — what operators reported after each session —
  trust_s: { term: 'Reported trust in the Strategic Assistant', group: 'Self-report (after each session)',
    what: 'Six statements answered after each session: it is reliable; I trust its recommendations; '
      + 'it performs well; I feel confident using it; it provides useful guidance; I would follow '
      + 'its suggestions without hesitation.',
    read: 'The average of the six, each 1 = strongly disagree to 7 = strongly agree. 4 is neutral.',
    here: () => spreadOf('trust_s', f2) },
  trust_t: { term: 'Reported trust in the Tactical Assistant', group: 'Self-report (after each session)',
    what: 'The same six statements as the strategic trust scale, asked about the Tactical Assistant.',
    read: 'The average of the six, each 1 = strongly disagree to 7 = strongly agree. 4 is neutral.',
    here: () => spreadOf('trust_t', f2) },
  rtlx: { term: 'Reported workload (raw NASA-TLX)', group: 'Self-report (after each session)',
    what: 'The NASA Task Load Index: six sliders on mental demand, physical demand, time pressure, '
      + 'own performance (high = felt they failed), effort and frustration.',
    read: 'The plain average of the six sliders, 0–20. Higher = more demanding.',
    here: () => spreadOf('rtlx', f1) },

  // — model terms —
  scenario: { term: 'Scenario (Tactical Heavy vs Strategic Heavy)', group: 'Model terms',
    what: 'Each operator played both scenarios. Strategic Heavy sends many small missions (one '
      + 'every ~37 s on average); Tactical Heavy sends fewer, larger ones (~75 s apart). Same '
      + 'fleet, same task types.',
    read: 'How the odds of taking a card change for a decision made in Tactical Heavy compared '
      + 'with one made in Strategic Heavy.' },
  odd: { term: 'Illogical card', group: 'Model terms',
    what: 'The Conservative card on that mission committed a drone type the mission had no use '
      + 'for, e.g. a Camera drone on a mission with no camera task. It comes from the simple rules '
      + 'the cards are built with, not from a deliberate fault.',
    read: 'Yes or no. How the odds of taking a card change when the Conservative card was illogical.' },
  ncolours: { term: 'Colours needed', group: 'Model terms',
    what: 'How many of the three drone types (Fast, Lifter, Camera) the mission’s tasks call for: '
      + '1, 2 or 3.',
    read: 'How the odds of taking a card change for each extra drone type the mission needs.' },
  ndrones: { term: 'Drones needed', group: 'Model terms',
    what: 'The total number of drones the mission’s task badges ask for, added up across its '
      + 'tasks. It is not the minimum needed to finish, because drones can do tasks one after '
      + 'another.',
    read: 'How the odds of taking a card change for each extra drone the mission needs.' },
  category: { term: 'Mission category A–E', group: 'Model terms',
    what: 'The mission’s designed size and urgency rating. On a genuine mission it is exactly the '
      + 'task count (A = 2 tasks … E = 6) and it sets how fast the penalty builds. A residual '
      + 'mission keeps its parent’s category with fewer tasks, which is why the category term '
      + 'should be read on genuine missions only.',
    read: 'Coded A = 1 to E = 5. How the odds of taking a card change for each step up.' },
  time: { term: 'Run + time in session', group: 'Model terms',
    what: 'Two control terms added together: which of their two sessions it was, and how far '
      + 'into that session the decision fell. Together they soak up learning and fatigue.',
    read: 'See the two entries below.' },
  run: { term: 'Second run (vs first)', group: 'Model terms',
    what: 'Whether the decision was made in the operator’s second 8-minute session, whichever '
      + 'scenario that was.',
    read: 'How the odds of taking a card change in the second session compared with the first.' },
  idx: { term: 'Each further decision into the session', group: 'Model terms',
    what: 'How many strategic decisions the operator had already made earlier in the same session.',
    read: 'How the odds of taking a card change with each earlier decision. A small multiplier '
      + 'adds up: ×1.03 per decision is about ×1.34 after ten.' },
  residual: { term: 'Residual mission', group: 'Model terms',
    what: 'When an operator abandons a mission in flight, its unfinished tasks come back as a new '
      + 'mission (its id ends in -R). It keeps the parent’s category but holds only the leftover '
      + 'tasks, so a residual E mission averages under 3 tasks where a genuine E has 6. “Genuine '
      + 'missions only” drops these decisions.',
    read: '' },

  // — statistics —
  rho: { term: 'Spearman ρ (rho)', group: 'Statistics',
    what: 'A rank correlation: do operators who rank high on one measure also rank high on the other?',
    read: '−1 = exactly opposite order, 0 = unrelated, +1 = exactly the same order. As a rough '
      + 'guide, about .1 is small, .3 moderate and .5 large.' },
  holm: { term: 'Holm correction', group: 'Statistics',
    what: 'An adjustment for running many tests at once. With 40 tests, about 2 will pass '
      + 'p < .05 by chance alone even when nothing is going on.',
    read: 'Each p-value is raised so the whole family of tests has only a 5% chance of producing '
      + 'any false alarm. A Holm-adjusted p under .05 is a result that survives that.' },
  odds: { term: 'Odds multiplier (odds ratio)', group: 'Statistics',
    what: 'How a term changes the odds of taking a card, holding the other terms in the model fixed.',
    read: '×1.00 = no change, ×2.00 = odds doubled, ×0.50 = odds halved. Odds are not '
      + 'probability: going from a 50% to a 67% chance is ×2 in odds.' },
  gee: { term: 'GEE, clustered on participant', group: 'Statistics',
    what: 'A regression (generalised estimating equations) that allows for each operator '
      + 'contributing many decisions, so the uncertainty is not understated and one prolific '
      + 'operator cannot dominate.',
    read: '' },
  ci: { term: '95% interval', group: 'Statistics',
    what: 'The range of effect sizes the data are consistent with.',
    read: 'If the interval includes ×1.00 (crosses the centre line), the term cannot be told '
      + 'apart from no effect.' },
  alpha: { term: 'Cronbach’s α (alpha)', group: 'Statistics',
    what: 'Whether the statements in a questionnaire hang together as measuring one thing.',
    read: '0 to 1. 0.7 or above is the usual bar for an acceptable scale; below it the averaged '
      + 'score is noisy and a null result from it is weak evidence.' },
  welch: { term: 'Welch test', group: 'Statistics',
    what: 'Compares the averages of two groups without assuming they are equally spread out.',
    read: 'The p is the chance of seeing a gap at least this big if the two groups were really '
      + 'the same.' },
};
const gv = x => typeof x === 'function' ? x() : (x || '');
function glossHtml(key) {
  const g = GLOSS[key];
  if (!g) return '';
  const read = gv(g.read), here = gv(g.here);
  return `<span class="g-term">${g.term}</span>${gv(g.what)}`
    + (read ? `<span class="g-read">${read}</span>` : '')
    + (here ? `<span class="g-here">${here}</span>` : '');
}
// `gl` is for HTML strings, `glNode` for an element already built.
const gl = (key, text) => `<span class="gl" data-g="${key}">${text || GLOSS[key].term}</span>`;
function glNode(n, key) {
  if (!GLOSS[key]) return n;
  n.setAttribute('data-g', key);
  if (n.classList) n.classList.add('gl');
  return n;
}
// One listener for every glossary hover, including ones re-rendered later. It runs in the
// capture phase so that leaving a glossary term hides its box BEFORE a chart's own hover handler
// shows the next one.
let glossOn = false;
document.addEventListener('mousemove', e => {
  const n = e.target.closest ? e.target.closest('[data-g]') : null;
  if (n && GLOSS[n.getAttribute('data-g')]) {
    showTip(e, glossHtml(n.getAttribute('data-g')), true);
    glossOn = true;
  } else if (glossOn) { hideTip(); glossOn = false; }
}, true);

