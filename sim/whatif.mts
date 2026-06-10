import { generateSessionPlan, createInitialAssets, HUB, ASSET_SPEED, TASK_PRIMARY, TASK_BASE_TIME } from '../src/utils/missionGen.ts'
import { SeededRNG } from '../src/utils/prng.ts'
import type { Complexity, AssetType, TaskType, MissionBlueprint } from '../src/types/index.ts'

const TYPES: AssetType[] = ['Blue','Red','Green']
const SCEN: Complexity[] = ['balanced','tactical','strategic','full']
const N = 200
const DUR = 480
const dist=(a:any,b:any)=>Math.hypot(a.x-b.x,a.y-b.y)

interface Params { lambdaScale:number; greenBump:number; greenSpeed:number; t4green:number; t5green:number }
function rhoWork(bps:MissionBlueprint[], fleet:Record<AssetType,number>, p:Params){
  const speed = {...ASSET_SPEED, Green:p.greenSpeed}
  const ds:Record<AssetType,number>={Blue:0,Red:0,Green:0}
  for(const bp of bps){
    bp.taskTypes.forEach((type,i)=>{
      const comp={...TASK_PRIMARY[type as TaskType]}
      if(type===4) comp.Green=p.t4green
      if(type===5) comp.Green=p.t5green
      const base=TASK_BASE_TIME[type as TaskType]; const wp=bp.waypoints[i]
      for(const tp of TYPES){const n=(comp as any)[tp]; if(n>0) ds[tp]+=n*(2*dist(HUB,wp)/speed[tp]+base)}
    })
  }
  const f={...fleet, Green:fleet.Green+p.greenBump}
  return TYPES.map(t=>ds[t]/(f[t]*DUR))
}
function fleetOf(c:Complexity){const a=createInitialAssets(c);return{Blue:a.filter(x=>x.type==='Blue').length,Red:a.filter(x=>x.type==='Red').length,Green:a.filter(x=>x.type==='Green').length}}

function evalScenario(c:Complexity,p:Params){
  const fleet=fleetOf(c)
  const agg:number[][]=[]
  let missions=0
  for(let s=0;s<N;s++){
    const seed=(1234567+s*2654435761)>>>0
    let bps=generateSessionPlan(new SeededRNG(seed^1),c,DUR/p.lambdaScale)
    if(p.lambdaScale!==1){bps=bps.map(b=>({...b,arrivalTime:b.arrivalTime*p.lambdaScale})).filter(b=>b.arrivalTime<=DUR)}
    missions+=bps.length
    agg.push(rhoWork(bps,fleet,p))
  }
  const mean=(i:number)=>agg.reduce((s,r)=>s+r[i],0)/agg.length
  return {rho:TYPES.map((_,i)=>mean(i)), missions:missions/N}
}

const base:Params={lambdaScale:1,greenBump:0,greenSpeed:4.2,t4green:2,t5green:1}
const variants:[string,Partial<Params>][]=[
  ['baseline (480s, current params)',{}],
  ['λ×1.5 (slower arrivals)',{lambdaScale:1.5}],
  ['λ×2.0',{lambdaScale:2.0}],
  ['+3 Green fleet',{greenBump:3}],
  ['Green speed 4.2→6.0',{greenSpeed:6.0}],
  ['T4 Green 2→1',{t4green:1}],
  ['COMBO A: λ×1.4 + Green 6.0',{lambdaScale:1.4,greenSpeed:6.0}],
  ['COMBO B: λ×1.3 + Green6.0 + T4g1',{lambdaScale:1.3,greenSpeed:6.0,t4green:1}],
  ['COMBO C: Green6.0 + T4g1 + +2Green',{greenSpeed:6.0,t4green:1,greenBump:2}],
]
for(const c of SCEN){
  console.log(`\n▌ ${c.toUpperCase()}  fleet ${JSON.stringify(fleetOf(c))}`)
  for(const [name,ov] of variants){
    const p={...base,...ov}
    const {rho,missions}=evalScenario(c,p)
    const bnIdx=rho.indexOf(Math.max(...rho)); const bn=TYPES[bnIdx]
    const v=rho[bnIdx]<0.6?'✅':rho[bnIdx]<0.75?'🟡':rho[bnIdx]<1?'🟠':'🔴'
    console.log(`  ${v} ${name.padEnd(34)} ρ B=${rho[0].toFixed(2)} R=${rho[1].toFixed(2)} G=${rho[2].toFixed(2)}  bn=${bn}  missions=${missions.toFixed(1)}`)
  }
}
