import { generateSessionPlan, createInitialAssets, HUB, TASK_PRIMARY, TASK_BASE_TIME } from '../src/utils/missionGen.ts'
import { SeededRNG } from '../src/utils/prng.ts'
import type { Complexity, AssetType, TaskType, MissionBlueprint } from '../src/types/index.ts'

const TYPES: AssetType[] = ['Blue','Red','Green']
const SCEN: Complexity[] = ['balanced','tactical','strategic','full']
const N = 300, DUR = 480
const dist=(a:any,b:any)=>Math.hypot(a.x-b.x,a.y-b.y)

// Candidate global speeds (modest buffs, keep Blue>Red>Green distinct)
const SPEED: Record<AssetType,number> = { Blue: 9.0, Red: 7.0, Green: 5.2 }
// failure overhead multiplier on work demand (each mission redoes ~some tasks)
const FAIL_MULT = 1.25
const TARGET_RHO = 0.58

function demandPerSession(c:Complexity){
  const ds:Record<AssetType,number>={Blue:0,Red:0,Green:0}
  let tasks=0, missions=0
  for(let s=0;s<N;s++){
    const seed=(1234567+s*2654435761)>>>0
    const bps=generateSessionPlan(new SeededRNG(seed^1),c,DUR)
    missions+=bps.length
    for(const bp of bps){
      tasks+=bp.taskTypes.length
      bp.taskTypes.forEach((type,i)=>{
        const comp=TASK_PRIMARY[type as TaskType]; const base=TASK_BASE_TIME[type as TaskType]; const wp=bp.waypoints[i]
        for(const tp of TYPES){const n=comp[tp]; if(n>0) ds[tp]+= n*(2*dist(HUB,wp)/SPEED[tp]+base)}
      })
    }
  }
  for(const tp of TYPES) ds[tp]=ds[tp]/N*FAIL_MULT
  return {ds, tasks:tasks/N, missions:missions/N}
}
function curFleet(c:Complexity){const a=createInitialAssets(c);return{Blue:a.filter(x=>x.type==='Blue').length,Red:a.filter(x=>x.type==='Red').length,Green:a.filter(x=>x.type==='Green').length}}

console.log(`Speeds B=${SPEED.Blue} R=${SPEED.Red} G=${SPEED.Green}  failMult=${FAIL_MULT}  targetρ=${TARGET_RHO}  dur=${DUR}s\n`)
for(const c of SCEN){
  const {ds,tasks,missions}=demandPerSession(c)
  const need:Record<string,number>={}
  for(const tp of TYPES) need[tp]=Math.ceil(ds[tp]/(TARGET_RHO*DUR))
  const cur=curFleet(c)
  const rhoCur:Record<string,number>={}; for(const tp of TYPES) rhoCur[tp]=ds[tp]/(cur[tp]*DUR)
  console.log(`▌ ${c.toUpperCase()}  missions=${missions.toFixed(1)} tasks=${tasks.toFixed(0)}`)
  console.log(`   current fleet ${cur.Blue}B/${cur.Red}R/${cur.Green}G  → ρ(withfail) B=${rhoCur.Blue.toFixed(2)} R=${rhoCur.Red.toFixed(2)} G=${rhoCur.Green.toFixed(2)}`)
  console.log(`   fleet needed for ρ=${TARGET_RHO}:  ${need.Blue}B / ${need.Red}R / ${need.Green}G   (≤15 each: ${TYPES.every(t=>need[t]<=15)?'yes':'NO — reduce arrivals/size'})`)
}
