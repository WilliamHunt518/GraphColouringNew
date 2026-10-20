import { chromium } from 'playwright-core';
import fs from 'fs';
const OUT = 'G:/Files/Code/GraphColouringNew/presentation/01_interface';
const b = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
const ctx = await b.newContext({ viewport: { width: 1920, height: 1080 } });
const p = await ctx.newPage(); const m = await ctx.newPage();
p.on('pageerror', e => console.log('pageerror', e.message));
const W = ms => p.waitForTimeout(ms);
const hide = pg => pg.evaluate(() => {
  document.querySelectorAll('button[title="Spawn next mission immediately"],button[title="Force a drone failure on an active mission"],button[title="End this session now and go to the surveys"],button[title="Skip straight to the end screen"]').forEach(e => { e.style.visibility = 'hidden'; e.dataset.hid = 1; });
  document.querySelectorAll('span').forEach(e => { const t = e.textContent.trim(); if (t === 'TEST' || /failures? fired/.test(t)) { e.style.visibility = 'hidden'; e.dataset.hid = 1; } });
});
const unhide = pg => pg.evaluate(() => document.querySelectorAll('[data-hid]').forEach(e => { e.style.visibility = ''; delete e.dataset.hid; }));
const shot = async (pg, dir, name, sel) => {
  fs.mkdirSync(`${OUT}/${dir}`, { recursive: true }); await hide(pg);
  const path = `${OUT}/${dir}/${name}.png`;
  try { if (sel) await pg.locator(sel).first().screenshot({ path }); else await pg.screenshot({ path }); console.log('ok', dir, name); }
  catch (e) { console.log('FAIL', dir, name, e.message.slice(0, 120)); }
  await unhide(pg);
};
const D2 = '02_strategic_window', D3 = '03_strategic_assistant', D4 = '04_tactical_planner', D5 = '05_failure_recovery', D6 = '06_surveys_and_probes';
const spawn = () => p.click('button[title="Spawn next mission immediately"]');
const deployStrategy = async (which) => {
  await p.locator('button:has-text("Allocate")').first().click(); await W(4500);
  await p.locator(`button:has-text("${which}")`).first().click(); await W(300);
  await p.click('button:has-text("Deploy Selected")'); await W(1200);
};
const openTac = async id => { await m.locator(`[data-tutorial="tac-mission-list"] >> text=${id}`).first().click(); await W(1200); };
const suggestDeploy = async () => { await m.click('[data-tutorial="tac-suggest-btn"]'); await W(7000); await m.click('[data-tutorial="tac-deploy-btn"]'); await W(1200); };
const detailBtn = 'div.absolute ~ button, button.absolute.bottom-2.left-2';

await p.goto('http://localhost:5199/?pid=DEMO&complexity=tactical&seed=42&test=1');
await m.goto('http://localhost:5199/?view=map');
await W(2500);
await shot(p, D2, '01_strategic_window_session_start');
await shot(m, D4, '01_tactical_window_idle');
await W(3000); await spawn(); await W(400); await spawn(); await W(400); await spawn(); await W(1500);
await shot(p, D2, '02_strategic_window_mission_queue');
await shot(p, D2, '03_crop_reserve_strip', '[data-tutorial="reserve-strip"]');
await shot(p, D2, '04_crop_mission_queue', '[data-tutorial="mission-list"]');
await shot(p, D2, '05_crop_strategic_map_with_zones', '[data-tutorial="embedded-map"]');

// ---- Strategic Assistant on M001
await p.locator('button:has-text("Allocate")').first().click(); await W(350);
await shot(p, D3, '01_strategic_assistant_cards_loading');
await W(5000);
await shot(p, D3, '02_strategic_assistant_cards_loaded');
const panel = 'div:has(> div > button:has-text("Deploy Selected"))';
await shot(p, D3, '03_crop_strategy_cards_panel', panel);
await p.locator('button:has-text("Aggressive")').first().click(); await W(500);
await shot(p, D3, '04_aggressive_card_selected');
await shot(p, D3, '05_crop_aggressive_selected', panel);
await p.click('button:has-text("Edit this allocation")'); await W(600);
await shot(p, D3, '06_editing_card_allocation_manually');
await shot(p, D3, '07_crop_manual_allocator', 'div:has(> div > button:text-is("Deploy"))');
await p.click('button:has-text("Back to suggestions")'); await W(300);
await p.locator('button:has-text("Conservative")').first().click(); await W(400);
await shot(p, D3, '08_conservative_card_selected');
await p.click('button:has-text("Deploy Selected")'); await W(1500);
await shot(p, D2, '06_after_strategic_allocation_team_launching');

// ---- Tactical planner on M001 with the Tactical Assistant
await shot(m, D4, '02_tactical_window_pending_mission');
await openTac('M001');
await shot(m, D4, '03_tactical_planner_empty');
await m.click('[data-tutorial="tac-suggest-btn"]'); await W(900);
await shot(m, D4, '04_tactical_assistant_suggesting');
await W(6500);
await shot(m, D4, '05_tactical_assistant_plan_ready');
await shot(m, D4, '06_crop_task_schedule_panel', '[data-tutorial="tac-right-panel"]');
await shot(m, D4, '07_crop_tactical_map', '[data-tutorial="tac-svg-container"]');
await m.click('[data-tutorial="tac-deploy-btn"]'); await W(1200);

// ---- M002 manual strategic + manual tactical
await p.locator('button:has-text("Allocate")').first().click(); await W(300);
await p.click('button:has-text("Set manually instead")'); await W(500);
await shot(p, D3, '09_manual_allocation_before_cards_load');
await p.click('button:has-text("Back to suggestions")'); await W(4500);
await p.locator('button:has-text("Aggressive")').first().click(); await W(300);
await p.click('button:has-text("Deploy Selected")'); await W(1200);
await openTac('M002');
const chips = () => m.locator('[data-tutorial="tac-unassigned"] [draggable="true"]');
const targets = () => m.locator('[data-tutorial="tac-svg-container"] circle[r="11"]');
const nt = await targets().count(); console.log('M002 targets', nt, 'chips', await chips().count());
for (let i = 0; i < Math.min(3, nt); i++) { if (await chips().count()) { await chips().nth(0).dragTo(targets().nth(i)); await W(500); } }
await shot(m, D4, '08_manual_drag_and_drop_partial_plan');
if (nt >= 2 && await chips().count()) {
  await m.keyboard.down('Shift'); await chips().nth(0).dragTo(targets().nth(nt - 1)); await m.keyboard.up('Shift'); await W(600);
}
await shot(m, D4, '09_manual_plan_more_drones');
const droneLabel = m.locator('[data-tutorial="tac-svg-container"] text').filter({ hasText: /^(Fast|Lifter|Camera)-\d+$/ }).first();
if (await droneLabel.count()) { await droneLabel.hover({ force: true }).catch(() => {}); await W(700); await shot(m, D4, '10_hover_drone_full_path'); }
await suggestDeploy();
// ---- M003 straight through the assistants
await deployStrategy('Conservative'); await openTac('M003'); await suggestDeploy();

// ---- in flight
await W(12000);
await shot(p, D2, '07_missions_in_progress');
await shot(m, D4, '11_tactical_window_missions_in_progress');
const act = m.locator('[data-tutorial="tac-mission-list"] >> text=M001').first();
if (await act.count()) { await act.click(); await W(1200); await shot(m, D4, '12_active_mission_view'); }
for (const lvl of ['a', 'b']) {
  await p.locator(detailBtn).first().click().catch(e => console.log('detail', e.message.slice(0, 80)));
  await W(500); await shot(p, D2, `08${lvl}_map_detail_level_${lvl}`);
}
await p.locator(detailBtn).first().click().catch(() => {}); await W(300);

// ---- failure
await W(8000);
await p.evaluate(() => { const b = document.querySelector('button[title="Force a drone failure on an active mission"]'); b.style.visibility = 'visible'; });
await p.click('button[title="Force a drone failure on an active mission"]').catch(e => console.log('no failure', e.message.slice(0, 80))); await W(1500);
await shot(p, D5, '01_strategic_window_drone_failure_alert');
await shot(p, D5, '02_crop_mission_queue_failure', '[data-tutorial="mission-list"]');
await shot(m, D5, '03_tactical_window_failure_flagged');
const fm = await m.evaluate(() => { const el = [...document.querySelectorAll('[data-tutorial="tac-mission-list"] *')].filter(e => /fail|⚠|recover/i.test(e.textContent) && /M\d{3}/.test(e.textContent)).pop(); return el ? el.textContent.slice(0, 120) : null; });
console.log('failed mission entry', fm);
const fmid = fm && fm.match(/M\d{3}/)?.[0];
if (fmid) await openTac(fmid);
await shot(m, D5, '04_recovery_planner');
await shot(m, D5, '05_crop_recovery_panel', '[data-tutorial="tac-right-panel"]');
if (await m.locator('[data-tutorial="tac-suggest-btn"]').count()) {
  await m.click('[data-tutorial="tac-suggest-btn"]'); await W(7000);
  await shot(m, D5, '06_recovery_planner_with_assistant_suggestion');
  await m.locator('[data-tutorial="tac-deploy-btn"]').click().catch(() => {}); await W(1200);
}
await shot(p, D5, '07_strategic_window_after_recovery');

// ---- trust probe (every 90 s)
for (let i = 0; i < 90; i++) { if (await p.locator('button:has-text("Submit")').count()) break; await W(1000); }
await W(600);
await shot(p, D6, '01_in_session_trust_probe');
await shot(p, D6, '02_crop_trust_probe', 'div:has(> button:has-text("Submit"))');
const dismiss = p.locator('button:has-text("Dismiss"), button:has-text("Skip"), button:has-text("×")').first();
await dismiss.click().catch(() => console.log('no dismiss')); await W(800);
await shot(p, D2, '10_later_in_session');
await shot(m, D4, '13_tactical_window_later_in_session');

// ---- end session -> surveys
await p.evaluate(() => { document.querySelector('button[title="End this session now and go to the surveys"]').style.visibility = 'visible'; });
await p.click('button[title="End this session now and go to the surveys"]'); await W(1500);
for (let page = 1; page <= 8; page++) {
  const nm = `${String(page + 2).padStart(2, '0')}_post_session_survey_page_${page}`;
  await shot(p, D6, nm);
  await p.screenshot({ path: `${OUT}/${D6}/${nm}_fullpage.png`, fullPage: true });
  await p.evaluate(() => {
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    document.querySelectorAll('input[type=range]').forEach(r => { set.call(r, String(Math.round((+r.min + +r.max) / 2) + 1)); r.dispatchEvent(new Event('input', { bubbles: true })); r.dispatchEvent(new Event('change', { bubbles: true })); });
  });
  const rows = p.locator('div.flex.gap-1');
  const nr = await rows.count();
  for (let i = 0; i < nr; i++) { const bt = rows.nth(i).locator('button').nth(4); if (await bt.count()) await bt.click().catch(() => {}); }
  await W(400);
  const nx = p.locator('button:has-text("Next →"), button:has-text("Continue →"), button:has-text("Finish study")').first();
  if (!(await nx.count())) { console.log('no next on page', page); break; }
  if (await nx.isDisabled()) { console.log('next disabled on page', page); await shot(p, D6, `debug_page_${page}`); break; }
  await nx.click(); await W(1200);
}
await shot(p, D6, '20_study_complete_screen');
await b.close();
