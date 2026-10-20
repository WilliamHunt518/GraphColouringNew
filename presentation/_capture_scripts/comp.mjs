import { createRequire } from 'module';
import fs from 'fs';
const require = createRequire('G:/Files/Code/GraphColouringNew/package.json');
const sharp = require('sharp');
const P = 'G:/Files/Code/GraphColouringNew/presentation';
const I = P + '/01_interface';
// icons -> png
fs.mkdirSync(P + '/05_assets/icons_png', { recursive: true });
for (const f of fs.readdirSync(P + '/05_assets/icons')) {
  await sharp(P + '/05_assets/icons/' + f, { density: 600 }).resize(512, 512, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } }).png().toFile(P + '/05_assets/icons_png/' + f.replace('.svg', '.png'));
}
// dual monitor composites
const pairs = [
  ['01_queue_and_tactical_idle', '02_strategic_window/02_strategic_window_mission_queue', '04_tactical_planner/01_tactical_window_idle'],
  ['02_strategic_assistant_and_tactical', '03_strategic_assistant/02_strategic_assistant_cards_loaded', '04_tactical_planner/01_tactical_window_idle'],
  ['03_after_allocation_tactical_pending', '02_strategic_window/06_after_strategic_allocation_team_launching', '04_tactical_planner/02_tactical_window_pending_mission'],
  ['04_missions_in_progress', '02_strategic_window/07_missions_in_progress', '04_tactical_planner/11_tactical_window_missions_in_progress'],
  ['05_drone_failure_and_recovery_planner', '05_failure_recovery/01_strategic_window_drone_failure_alert', '05_failure_recovery/04_recovery_planner'],
  ['06_later_in_session', '02_strategic_window/10_later_in_session', '04_tactical_planner/13_tactical_window_later_in_session'],
];
fs.mkdirSync(I + '/08_dual_monitor_side_by_side', { recursive: true });
for (const [name, a, b] of pairs) {
  const gap = 24;
  await sharp({ create: { width: 1920 * 2 + gap, height: 1080, channels: 3, background: '#111111' } })
    .composite([{ input: `${I}/${a}.png`, left: 0, top: 0 }, { input: `${I}/${b}.png`, left: 1920 + gap, top: 0 }])
    .png().toFile(`${I}/08_dual_monitor_side_by_side/${name}.png`);
  console.log('ok', name);
}
