import { chromium } from 'playwright-core';
const OUT = 'G:/Files/Code/GraphColouringNew/presentation/02_charts';
const SUB = '01_findings_review_current_pass/06_a-busier-moment-does-not-push-people-onto-the-assistants-eve';
const b = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
for (const theme of ['light', 'dark']) {
  const p = await (await b.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2, colorScheme: theme })).newPage();
  await p.goto('http://127.0.0.1:8799/findings_review.html', { waitUntil: 'networkidle' }); await p.waitForTimeout(1500);
  for (let i = 0; i < 12; i++) { const t = await p.evaluate(() => document.querySelector('h2')?.textContent); if (/busier moment/i.test(t)) break; await p.click('button:has-text("Next →")'); await p.waitForTimeout(800); }
  await p.evaluate(() => document.querySelectorAll('.closed').forEach(e => e.classList.remove('closed')));
  const fs_ = p.locator('.fsec').filter({ has: p.locator('h3', { hasText: 'Queue depth against reliance' }) }).first();
  const box = fs_.locator('.chartbox');
  for (const [tk, tl] of [['both-together', 'Both together'], ['strategic', 'Strategic'], ['tactical', 'Tactical']]) {
    await box.locator('.btnrow').nth(0).locator(`button:text-is("${tl}")`).click();
    for (const [vk, vl] of [['raw', 'Raw'], ['raw-plus-expected', 'Raw + expected'], ['adjusted', 'Adjusted']]) {
      await box.locator('.btnrow').nth(1).locator(`button:text-is("${vl}")`).click(); await p.waitForTimeout(400);
      await p.evaluate(() => document.querySelectorAll('details.tbl').forEach(d => d.open = false));
      await box.scrollIntoViewIfNeeded(); await p.waitForTimeout(200);
      const f = `${OUT}/${theme}/${SUB}/01_1-queue-depth-against-reliance_${tk}_${vk}.png`;
      await box.screenshot({ path: f }); console.log('ok', theme, tk, vk);
    }
  }
}
await b.close();
