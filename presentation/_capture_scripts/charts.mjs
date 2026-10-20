import { chromium } from 'playwright-core';
import fs from 'fs';
const OUT = 'G:/Files/Code/GraphColouringNew/presentation';
const R = 'G:/Files/Code/GraphColouringNew';
const pages = [
  ['01_findings_review_current_pass', 'http://127.0.0.1:8799/findings_review.html', true],
  ['02_findings_combined', 'file:///' + R + '/Results/findings_combined.html'],
  ['03_findings_synthesis', 'file:///' + R + '/Results/findings_synthesis.html'],
  ['04_findings_brief', 'file:///' + R + '/Results/findings_brief.html'],
  ['05_analysis_round1', 'file:///' + R + '/Results/analysis_round1.html'],
  ['06_analysis_round2', 'file:///' + R + '/Results/analysis_round2.html'],
  ['07_report_two_tiers_two_scenarios', 'file:///' + R + '/docs/reports/two-tiers-two-scenarios.html'],
  ['08_report_two_tiers_legacy', 'file:///' + R + '/docs/reports/two-tiers-two-scenarios-legacy.html'],
];
const b = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
const slug = s => (s || '').toLowerCase().replace(/[’']/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 80) || 'chart';
const only = process.argv[2];
async function prep(p) {
  await p.evaluate(() => { document.querySelectorAll('.closed').forEach(e => e.classList.remove('closed')); document.querySelectorAll('details').forEach(d => d.open = true); });
  await p.waitForTimeout(1000);
}
async function grab(p, dir) {
  const n = await p.evaluate(() => {
    const hosts = new Set();
    document.querySelectorAll('svg').forEach(s => {
      const bb = s.getBoundingClientRect(); if (bb.width < 180 || bb.height < 80) return;
      hosts.add(s.closest('.card') || s.closest('figure') || s.closest(".chart")?.parentElement || s.parentElement);
    });
    const arr = [...hosts].filter(h => ![...hosts].some(o => o !== h && o.contains(h)));
    document.querySelectorAll('[data-shot]').forEach(e => e.removeAttribute('data-shot'));
    arr.forEach((h, i) => {
      h.setAttribute('data-shot', i);
      const head = h.querySelector('h3,h4,h2,.card-title,.ttl,b,strong');
      let t = head ? head.textContent.trim() : '';
      const fs_ = h.closest('.fsec'); if (fs_ && !h.classList.contains('card')) t = fs_.querySelector('h3')?.textContent.trim() || t;
      if (!t) { const sec = h.closest('section'); t = sec?.querySelector('h2,h1')?.textContent.trim() || ''; }
      h.setAttribute('data-shot-name', t.slice(0, 120));
    });
    return arr.length;
  });
  if (!n) return 0;
  fs.mkdirSync(dir, { recursive: true });
  for (let i = 0; i < n; i++) {
    const el = p.locator(`[data-shot="${i}"]`);
    const nm = await el.getAttribute('data-shot-name');
    await el.scrollIntoViewIfNeeded().catch(() => {}); await p.waitForTimeout(120);
    await el.screenshot({ path: `${dir}/${String(i + 1).padStart(2, '0')}_${slug(nm)}.png` }).catch(e => console.log('  fail', i, e.message.slice(0, 100)));
  }
  return n;
}
for (const theme of ['light', 'dark']) {
  const ctx = await b.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2, colorScheme: theme });
  const p = await ctx.newPage();
  for (const [name, url, stepper] of pages) {
    if (only && only !== name) continue;
    await p.goto(url, { waitUntil: 'networkidle' }).catch(e => console.log('goto', name, e.message));
    await p.waitForTimeout(2000);
    const base = `${OUT}/02_charts/${theme}/${name}`;
    if (stepper) {
      const seen = new Set(); let k = 0, total = 0;
      while (true) {
        await prep(p);
        const title = await p.evaluate(() => document.querySelector('h2')?.textContent.trim() || '');
        if (seen.has(title)) break; seen.add(title); k++;
        total += await grab(p, `${base}/${String(k).padStart(2, '0')}_${slug(title).slice(0, 60)}`);
        const nx = p.locator('button:has-text("Next →")');
        if (!(await nx.count()) || await nx.isDisabled()) break;
        await nx.click(); await p.waitForTimeout(1000);
      }
      console.log(theme, name, k, 'findings', total);
    } else {
      await prep(p);
      console.log(theme, name, await grab(p, base));
    }
  }
  await ctx.close();
}
// full pages, light, 1x
const ctx = await b.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: 'light' });
const p = await ctx.newPage();
fs.mkdirSync(`${OUT}/03_full_pages`, { recursive: true });
for (const [name, url, stepper] of pages) {
  if (only && only !== name) continue;
  await p.goto(url, { waitUntil: 'networkidle' }).catch(() => {}); await p.waitForTimeout(2000); await prep(p);
  if (stepper) {
    const seen = new Set(); let k = 0;
    while (true) {
      await prep(p);
      const title = await p.evaluate(() => document.querySelector('h2')?.textContent.trim() || '');
      if (seen.has(title)) break; seen.add(title); k++;
      fs.mkdirSync(`${OUT}/03_full_pages/${name}`, { recursive: true });
      await p.screenshot({ path: `${OUT}/03_full_pages/${name}/${String(k).padStart(2, '0')}_${slug(title).slice(0, 60)}.png`, fullPage: true });
      const nx = p.locator('button:has-text("Next →")');
      if (!(await nx.count()) || await nx.isDisabled()) break;
      await nx.click(); await p.waitForTimeout(1000);
    }
  } else await p.screenshot({ path: `${OUT}/03_full_pages/${name}.png`, fullPage: true });
}
await b.close();
console.log('done');
