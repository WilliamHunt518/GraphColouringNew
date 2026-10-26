// Render the review page's charts as paper figures (PNG, light theme, 3x).
//
//   node scripts/paper/capture_figs.mjs <jobs.json> <outDir> [baseUrl]
//
// jobs.json (written by build_paper.py): [{finding, findingTitle, section, views: [[suffix, clicks, note]]}].
// The review page must be served (scripts/register/review.bat, or `python -m http.server` in Results/).
// For each view: click the listed toggles inside that section's chart box, then screenshot the chart with its
// toggle rows, data tables and trailing explanatory paragraphs hidden (the text goes into the LaTeX caption).
// Writes <outDir>/<finding>__<section>__<suffix>.png and <outDir>/manifest.json.
import { chromium } from 'playwright-core';
import fs from 'fs';
import path from 'path';

const [jobsPath, outDir, base = 'http://127.0.0.1:8766/findings_review.html'] = process.argv.slice(2);
const jobs = JSON.parse(fs.readFileSync(jobsPath, 'utf8'));
// The paper's terms (scripts/paper/terms.json), applied to every text node of a chart before it is captured.
const termsPath = process.env.TERMS || path.join(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), 'terms.json');
const TERMS = fs.existsSync(termsPath) ? JSON.parse(fs.readFileSync(termsPath, 'utf8')).rules : [];
if (!TERMS.length) console.log('WARNING: no terms file at', termsPath, '- labels left as on the review page');
fs.mkdirSync(outDir, { recursive: true });
const chrome = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const b = await chromium.launch({ executablePath: chrome });
const p = await (await b.newContext({ viewport: { width: 1100, height: 1000 }, deviceScaleFactor: 3, colorScheme: 'light' })).newPage();
const errors = [];
p.on('pageerror', e => errors.push(e.message));
await p.goto(base, { waitUntil: 'networkidle' });
await p.waitForTimeout(1500);

const title = () => p.evaluate(() => (document.querySelector('h2') || {}).textContent || '');
// headings and register titles differ in quote characters and spacing, so compare a normalised prefix
const norm = s => s.replace(/[‘’'"“”]/g, '').replace(/\s+/g, ' ').trim().toLowerCase();
// The page remembers the last finding viewed (even across reloads), so search forwards, then backwards.
async function openFinding(t, id) {
  // the page exposes go(<finding id>); fall back to paging when it does not
  if (id && await p.evaluate(i => typeof go === 'function' && (go(i), true), id)) { await p.waitForTimeout(500); return true; }
  for (const label of ['Next →', '← Previous']) {
    let prev = null;
    for (let i = 0; i < 20; i++) {
      const cur = await title();
      if (norm(cur).startsWith(norm(t).slice(0, 50))) return true;
      if (cur === prev) break;                       // at the end in this direction
      prev = cur;
      const btn = p.locator(`button:has-text("${label}")`);
      if (!(await btn.count()) || await btn.isDisabled()) break;
      await btn.click(); await p.waitForTimeout(600);
    }
  }
  return false;
}

const manifest = {};
for (const job of jobs) {
  if (!(await openFinding(job.findingTitle, job.finding))) { console.log('MISSING finding', job.finding); continue; }
  await p.evaluate(() => { document.querySelectorAll('.closed').forEach(e => e.classList.remove('closed'));
    document.querySelectorAll('details.sidepanel').forEach(d => { d.open = true; }); });
  const sec = p.locator(`#sec-${job.section}`);
  if (!(await sec.count()) || !(await sec.locator('.chartbox svg').count())) { console.log('no chart', job.finding, job.section); continue; }
  const box = sec.locator('.chartbox').first();
  const out = [];
  for (const [suffix, clicks, note, opts = {}] of job.views) {
    const file = `${job.finding}__${job.section}__${suffix}.png`;
    if (process.env.SKIP_EXISTING && fs.existsSync(path.join(outDir, file))) { out.push({ file, suffix, note }); continue; }
    // Re-open the finding fresh for every view so toggles from the previous view do not carry over.
    await p.reload({ waitUntil: 'networkidle' }); await p.waitForTimeout(700);
    await openFinding(job.findingTitle, job.finding);
    await p.evaluate(() => { document.querySelectorAll('.closed').forEach(e => e.classList.remove('closed'));
      document.querySelectorAll('details.sidepanel').forEach(d => { d.open = true; }); });
    let ok = true;
    for (const [lab, opt] of clicks) {
      const row = box.locator('.btnrow').filter({ has: p.locator('.btnlab', { hasText: lab }) }).first();
      const btn = row.locator('button').filter({ hasText: opt }).first();
      if (!(await btn.count())) { console.log('  no button', job.section, lab, '->', opt); ok = false; break; }
      await btn.click(); await p.waitForTimeout(350);
    }
    if (!ok) continue;
    await p.evaluate(sel => {
      const ch = document.querySelector(sel);
      ch.querySelectorAll('.btnrow, details.tbl, details').forEach(e => { e.style.display = 'none'; });
      // hide paragraphs that come after the last chart graphic (explanations, read-outs); keep headings above graphics
      const svgs = [...ch.querySelectorAll('svg')];
      const last = svgs[svgs.length - 1];
      ch.querySelectorAll('p').forEach(par => {
        if (last && (last.compareDocumentPosition(par) & Node.DOCUMENT_POSITION_FOLLOWING)) par.style.display = 'none';
      });
    }, `#sec-${job.section} .chartbox .chart`);
    // opts.only === 'first': keep only the chart's first graphic and its legend (e.g. drop a forest plot underneath):
    // at every level from that graphic up to the chart, hide later siblings that hold another graphic or a paragraph
    if (opts.only === 'first') await p.evaluate(sel => {
      const ch = document.querySelector(sel), first = ch.querySelector('svg');
      for (let n = first; n && n !== ch; n = n.parentElement) {
        for (let s = n.nextElementSibling; s; s = s.nextElementSibling)
          if (s.tagName === 'svg' || s.tagName === 'P' || s.querySelector('svg')) s.style.display = 'none';
      }
    }, `#sec-${job.section} .chartbox .chart`);
    await p.evaluate(([sel, rules]) => {
      const ch = document.querySelector(sel), rx = rules.map(([a, b]) => [new RegExp(a, 'g'), b]);
      const w = document.createTreeWalker(ch, NodeFilter.SHOW_TEXT);
      let n; while ((n = w.nextNode())) { let s = n.textContent; rx.forEach(([r, b]) => { s = s.replace(r, b); }); if (s !== n.textContent) n.textContent = s; }
    }, [`#sec-${job.section} .chartbox .chart`, TERMS]);
    await p.waitForTimeout(200);
    try {
      await sec.locator('.chartbox .chart').first().screenshot({ path: path.join(outDir, file), timeout: 15000 });
      out.push({ file, suffix, note });
      console.log('ok', file);
    } catch (e) { console.log('FAIL', file, e.message.split(String.fromCharCode(10))[0]); }
  }
  manifest[`${job.finding}#${job.section}`] = out;
}
fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify(manifest, null, 1));
console.log('page errors:', errors.length ? errors : 'none');
await b.close();
