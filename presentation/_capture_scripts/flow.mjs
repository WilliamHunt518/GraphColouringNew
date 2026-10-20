import { chromium } from 'playwright-core';
import fs from 'fs';
const OUT = 'G:/Files/Code/GraphColouringNew/presentation/01_interface';
const b = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
const ctx = await b.newContext({ viewport: { width: 1920, height: 1080 } });
const D1 = '01_setup_and_onboarding', D6 = '06_surveys_and_probes', D7 = '07_tutorial';
const save = async (pg, dir, name, full = false) => {
  fs.mkdirSync(`${OUT}/${dir}`, { recursive: true });
  await pg.evaluate(() => document.querySelectorAll('p, span, div').forEach(e => { if (e.children.length === 0 && /Fast-test mode/.test(e.textContent)) e.style.display = 'none'; }));
  await pg.screenshot({ path: `${OUT}/${dir}/${name}.png`, fullPage: full, timeout: 20000 }).then(() => console.log('ok', name)).catch(e => console.log('FAIL', name, e.message.slice(0, 100)));
};
const which = process.argv[2] || 'all';

if (which === 'all' || which === 'flow') {
  const p = await ctx.newPage();
  await p.goto('http://localhost:5199/'); await p.waitForTimeout(1500);
  await save(p, D1, '01_researcher_start_screen', true);
  await save(p, D1, '01b_researcher_start_screen_top');
  await p.fill('input[placeholder="e.g. P001 (optional)"]', 'P-DEMO');
  await p.check('#study-fast-test');
  await p.click('button:has-text("Begin Participant Study")'); await p.waitForTimeout(1500);
  await save(p, D1, '02_pre_study_questionnaire_top');
  await save(p, D1, '03_pre_study_questionnaire_full', true);
  // scroll through sections for viewport shots
  const h = await p.evaluate(() => { const sc = [...document.querySelectorAll('*')].find(e => e.scrollHeight > e.clientHeight + 50 && getComputedStyle(e).overflowY.match(/auto|scroll/)); window.__sc = sc; return sc ? sc.scrollHeight : 0; });
  for (let y = 1, k = 1; y < h && k < 8; y += 900, k++) {
    await p.evaluate(yy => window.__sc && window.__sc.scrollTo(0, yy), y); await p.waitForTimeout(300);
    await save(p, D1, `03_pre_study_questionnaire_part${k}`);
  }
  await p.locator('button:has-text("Continue"), button:has-text("Begin"), button:has-text("Submit"), button:has-text("Start")').last().click(); await p.waitForTimeout(1500);
  let surveyN = 0, session = 1, seenBetween = false;
  for (let t = 0; t < 200; t++) {
    const txt = await p.evaluate(() => document.body.innerText.slice(0, 300));
    if (/SURVEY/.test(txt)) {
      surveyN++;
      await save(p, D6, `s${session}_survey_page_${surveyN}`);
      await p.evaluate(() => { const sc = [...document.querySelectorAll('*')].find(e => e.scrollHeight > e.clientHeight + 30 && /auto|scroll/.test(getComputedStyle(e).overflowY)); if (sc) sc.scrollTo(0, 1e6); });
      await p.waitForTimeout(250);
      await save(p, D6, `s${session}_survey_page_${surveyN}_scrolled`);
      await p.evaluate(() => {
        const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
        document.querySelectorAll('input[type=range]').forEach(r => { set.call(r, '13'); r.dispatchEvent(new Event('input', { bubbles: true })); r.dispatchEvent(new Event('change', { bubbles: true })); });
      });
      const rows = p.locator('div.flex.gap-1'); const nr = await rows.count();
      for (let i = 0; i < nr; i++) { const bt = rows.nth(i).locator('button').nth(4); if (await bt.count()) await bt.click().catch(() => {}); }
      const nx = p.locator('button:has-text("Next →"), button:has-text("Continue →"), button:has-text("Finish study")').first();
      await nx.click().catch(e => console.log('next', e.message.slice(0, 80))); await p.waitForTimeout(1000);
      continue;
    }
    if (/between|Next session|Session 2|break/i.test(txt) && !/SURVEY/.test(txt) && !seenBetween && surveyN > 0) {
      seenBetween = true; await save(p, D6, 'between_sessions_screen'); session = 2; surveyN = 0;
      const go = p.locator('button').filter({ hasText: /begin|start|continue|ready/i }).first();
      await p.waitForTimeout(1000);
      if (await go.count()) await go.click().catch(() => {});
    }
    if (/download|complete|thank/i.test(txt) && session === 2 && surveyN > 0) { await save(p, D6, 'study_complete_screen'); break; }
    await p.waitForTimeout(1000);
  }
  await p.close();
}

if (which === 'all' || which === 'tutorial') {
  const p = await ctx.newPage(); const m = await ctx.newPage();
  await p.goto('http://localhost:5199/'); await p.waitForTimeout(1200);
  await m.goto('http://localhost:5199/?view=map');
  await p.bringToFront();
  await p.click('button:has-text("Run Tutorial")'); await p.waitForTimeout(2000);
  let lastTitle = '';
  for (let s = 1; s <= 48; s++) {
    const nx = p.locator('button:has-text("Next →")'); const nxm = m.locator('button:has-text("Next →")');
    const title = await p.evaluate(() => document.body.innerText.match(/Step \d+ ?\/ ?\d+|\d+ \/ 48/)?.[0] || '');
    await save(p, D7, `step${String(s).padStart(2, '0')}_strategic_window`);
    await save(m, D7, `step${String(s).padStart(2, '0')}_tactical_window`);
    if (await nx.count() && await nx.isEnabled()) { await nx.click(); }
    else if (await nxm.count() && await nxm.isEnabled()) { await nxm.click(); }
    else { console.log('stuck at step', s, title); break; }
    await p.waitForTimeout(1200);
  }
}
await b.close();
