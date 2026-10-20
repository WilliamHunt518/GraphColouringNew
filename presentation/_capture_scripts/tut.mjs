import { chromium } from 'playwright-core';
import fs from 'fs';
const OUT = 'G:/Files/Code/GraphColouringNew/presentation/01_interface/07_tutorial';
fs.rmSync(OUT, { recursive: true, force: true }); fs.mkdirSync(OUT, { recursive: true });
const b = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
const ctx = await b.newContext({ viewport: { width: 1920, height: 1080 } });
const p = await ctx.newPage(); const m = await ctx.newPage();
const W = ms => p.waitForTimeout(ms);
const slug = s => s.toLowerCase().replace(/[’']/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 50);
const hideTest = pg => pg.evaluate(() => {
  document.querySelectorAll('button[title="Spawn next mission immediately"],button[title="Force a drone failure on an active mission"],button[title="End this session now and go to the surveys"],button[title="Skip straight to the end screen"]').forEach(e => { e.style.visibility = 'hidden'; e.dataset.hid = 1; });
  document.querySelectorAll('span').forEach(e => { const t = e.textContent.trim(); if (t === 'TEST' || /failures? fired/.test(t)) { e.style.visibility = 'hidden'; e.dataset.hid = 1; } });
});
const unhide = pg => pg.evaluate(() => document.querySelectorAll('[data-hid]').forEach(e => { e.style.visibility = ''; delete e.dataset.hid; }));
const save = async (pg, name) => { await hideTest(pg); await pg.screenshot({ path: `${OUT}/${name}.png`, timeout: 20000 }).catch(e => console.log('FAIL', name, e.message.slice(0, 80))); await unhide(pg); };
const TITLES = ['Welcome to SAR Command','Sessions & Scoring','The Header Bar','Session Timer','Your Score','Your Drone Reserve','Three Drone Types','The Mission Queue','Reading a Mission Card','Task Progress Bar','Penalty Histogram','Allocating a Mission','Manual Allocation','Set Your Allocation & Deploy','Tactical Planning Pending','The Strategic Map','The Tactical Planner','Mission Queue','Select Your Mission','Planner Header','The Mission Zone','Check Task Requirements','Your Available Drones','Assigning Drones to Tasks','Chaining One Drone Through Multiple Tasks','Complete the Plan','Task Schedule','Deploy the Mission','Watch the Deployment','Mission Failure Alert','Recovery Planner','Reassign Now','Why Redundancy Matters','When You Cannot Recover','Reopen the Failed Mission','Abort the Mission','Now Try the Assistants','Allocate the Second Mission','The Strategic Assistant','Reading a Strategy Card','Strategy Score Bars','Select a Strategy & Deploy','The Tactical Assistant','Select the New Mission','Let the Tactical Assistant Fill the Plan','Review and Override','Deploy Mission 2',"You're Ready — Good Luck!"];
const curTitle = async () => {
  for (const [pg, w] of [[p, 'strategic'], [m, 'tactical']]) {
    const k = await pg.evaluate(() => { const mm = document.body.innerText.match(/(\d{1,2}) \/ 48/); return mm ? +mm[1] : 0; });
    if (k) return [TITLES[k - 1], pg, w];
  }
  return [null, null, null];
};
const chips = () => m.locator('[data-tutorial="tac-unassigned"] [draggable="true"]');
const targets = () => m.locator('[data-tutorial="tac-svg-container"] circle[r="11"]');

const synthDrag = (chipIdx, tgtIdx, shift = false) => m.evaluate(([ci, ti, sh]) => {
  const chip = document.querySelectorAll('[data-tutorial="tac-unassigned"] [draggable="true"]')[ci];
  const circles = document.querySelectorAll('[data-tutorial="tac-svg-container"] circle[r="11"]');
  const tgt = circles[ti % circles.length];
  if (!chip || !tgt) return false;
  const dt = new DataTransfer();
  chip.dispatchEvent(new DragEvent('dragstart', { bubbles: true, dataTransfer: dt }));
  tgt.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: dt }));
  tgt.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt, shiftKey: sh }));
  chip.dispatchEvent(new DragEvent('dragend', { bubbles: true, dataTransfer: dt }));
  return dt.getData('droneId') || true;
}, [chipIdx, tgtIdx, shift]);

let firstDrone = null;
const pointerDrag = async (droneId, tgtIdx, shift) => {
  const d = m.locator(`[data-drone="${droneId}"]`).first();
  const bb = await d.boundingBox(); const tb = await targets().nth(tgtIdx).boundingBox();
  if (!bb || !tb) { console.log('no boxes', droneId, tgtIdx); return; }
  if (shift) await m.keyboard.down('Shift');
  await m.mouse.move(bb.x + bb.width / 2, bb.y + bb.height / 2); await m.mouse.down();
  await m.mouse.move(tb.x + tb.width / 2, tb.y + tb.height / 2, { steps: 12 }); await W(150); await m.mouse.up();
  if (shift) await m.keyboard.up('Shift');
};
const plus = async (row, times) => { for (let i = 0; i < times; i++) { await p.locator('button:text-is("+")').nth(row).click(); await W(300); } };
const actions = {
  'Allocating a Mission': async () => p.click('[data-tutorial="first-allocate-btn"]'),
  'Manual Allocation': async () => p.click('[data-tutorial="first-manual-toggle"]'),
  'Set Your Allocation & Deploy': async () => { await plus(0, 1); await plus(1, 2); await plus(2, 1); await save(p, 'step14b_manual_allocation_filled'); await p.click('[data-tutorial="first-deploy-btn"]'); },
  'Select Your Mission': async () => m.locator('[data-tutorial="tac-mission-list"]').getByText(/^[A-Z]\d{3}$/).last().click({ force: true }),
  'Select the New Mission': async () => m.locator('[data-tutorial="tac-mission-list"]').getByText(/^[A-Z]\d{3}$/).last().click({ force: true }),
  'Assigning Drones to Tasks': async () => { firstDrone = await synthDrag(0, 0); console.log('assigned', firstDrone); },
  'Chaining One Drone Through Multiple Tasks': async () => { await pointerDrag(firstDrone, 1, true); await W(700); await pointerDrag(firstDrone, 2, true); },
  'Complete the Plan': async () => { let k = 0; const nt = await targets().count(); while (await chips().count() && k < 8) { const id = await synthDrag(0, 0); await W(500); for (let t = 1; t < nt; t++) { await pointerDrag(id, t, true); await W(500); } k++; } },
  'Mission Failure Alert': async () => m.locator('[data-tutorial="tac-mission-list"]').getByText(/^[A-Z]\d{3}$/).last().click({ force: true }),
  'Reopen the Failed Mission': async () => m.locator('[data-tutorial="tac-mission-list"]').getByText(/^[A-Z]\d{3}$/).last().click({ force: true }),
  'Reassign Now': async () => { const ids = await m.evaluate(() => [...new Set([...document.querySelectorAll('[data-tutorial="tac-svg-container"] [data-drone]')].map(e => e.getAttribute('data-drone')))]); const nt = await targets().count(); console.log('recovery drones', ids, nt); for (const id of ids) for (let t = 0; t < nt; t++) { await pointerDrag(id, t, true).catch(() => {}); await W(400); } await save(m, 'step32b_recovery_plan_filled_tactical_window'); await m.click('[data-tutorial="tac-deploy-btn"]', { timeout: 5000 }); },
  'Abort the Mission': async () => m.click('[data-tutorial="tac-abandon-btn"]'),
  'Deploy the Mission': async () => m.click('[data-tutorial="tac-deploy-btn"]'),
  'Deploy Mission 2': async () => m.click('[data-tutorial="tac-deploy-btn"]'),
  'Let the Tactical Assistant Fill the Plan': async () => m.click('[data-tutorial="tac-suggest-btn"]'),
  'Allocate the Second Mission': async () => p.click('[data-tutorial="first-allocate-btn"]', { timeout: 8000 }),
  'Select a Strategy & Deploy': async () => { await p.locator('[data-tutorial="first-strategy-card"]').click({ timeout: 8000 }); await W(500); await p.click('[data-tutorial="first-deploy-btn"]', { timeout: 8000 }); },
};
await p.goto('http://localhost:5199/'); await W(1200);
await m.goto('http://localhost:5199/?view=map');
await p.click('button:has-text("Run Tutorial")'); await W(2500);
let prev = null, stuck = 0, n = 0;
for (let it = 0; it < 120 && stuck < 10; it++) {
  const [t, pg, w] = await curTitle();
  if (!t) { stuck++; await W(1500); continue; }
  if (t !== prev) {
    n++; const idx = TITLES.indexOf(t) + 1;
    const base = `step${String(idx).padStart(2, '0')}_${slug(t)}`;
    await save(pg, `${base}_${w}_window`);
    if (w === 'strategic' && idx >= 15) await save(m, `${base}_tactical_window`);
    if (w === 'tactical') await save(p, `${base}_strategic_window`);
    console.log('step', idx, t, w); prev = t; stuck = 0;
  }
  let clicked = false;
  for (const g of [pg, pg === p ? m : p]) { const nx = g.locator('button:has-text("Next →"), button:has-text("Finish")').first(); if (await nx.count() && await nx.isVisible() && await nx.isEnabled()) { await nx.click(); clicked = true; break; } }
  if (clicked) { await W(1300); continue; }
  if (actions[t] && (actions[t].tries || 0) < 4) { actions[t].tries = (actions[t].tries || 0) + 1; try { await actions[t](); } catch (e) { console.log('action fail', t, e.message.slice(0, 100)); } await W(2000); continue; }
  // auto-advancing steps (e.g. watching the deployment): wait
  await W(3000); stuck++;
  if (stuck >= 10) console.log('stuck at', t);
}
await b.close();
