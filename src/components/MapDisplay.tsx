import { useState, useEffect, useRef } from 'react'
import type { MapViewState, Asset, Mission, Task, AssetType, TaskStatus } from '../types'
import { HUB, ASSET_CALLSIGNS, CATEGORY_PENALTY_RATE, TASK_WEIGHT } from '../utils/missionGen'
import { DRONE_ICON, TASK_ICON } from '../utils/icons'

// ─── Colour constants ─────────────────────────────────────────────────────

const ASSET_COLOR: Record<AssetType, string> = {
  Blue:  '#60a5fa',
  Red:   '#f87171',
  Green: '#4ade80',
}

const TASK_DOT_COLOR: Record<TaskStatus, string> = {
  pending:   '#4b5563',
  traveling: '#3b82f6',
  executing: '#f59e0b',
  completed: '#10b981',
  failed:    '#ef4444',
}

const ZONE_STROKE: Record<Mission['status'], string> = {
  queued:    '#b45309',
  active:    '#1d4ed8',
  completed: '#374151',
  failed:    '#7f1d1d',
}

const TASK_SHORT_MAP: Record<number, string> = {
  1: 'Rcn', 2: 'Sup', 3: 'Ext', 4: 'Med', 5: 'Rsc',
}

const ZONE_FILL: Record<Mission['status'], string> = {
  queued:    'rgba(120,53,15,0.12)',
  active:    'rgba(29,78,216,0.10)',
  completed: 'rgba(55,65,81,0.06)',
  failed:    'rgba(127,29,29,0.06)',
}

// ─── Main component ───────────────────────────────────────────────────────

interface Props {
  state: MapViewState
  onReprioritiseTop?: (missionId: string, taskId: string) => void
}

export default function MapDisplay({ state, onReprioritiseTop }: Props) {
  const [selectedMissionId, setSelectedMissionId] = useState<string | null>(null)
  const [useCallsigns, setUseCallsigns] = useState(false)
  const channelRef = useRef<BroadcastChannel | null>(null)

  // Pan / zoom state
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 })
  const [grabbing, setGrabbing] = useState(false)
  const svgRef = useRef<SVGSVGElement>(null)
  const isPanning = useRef(false)
  const hasDragged = useRef(false)
  const lastClientPos = useRef({ x: 0, y: 0 })

  // BroadcastChannel for sending actions back to primary window
  useEffect(() => {
    const ch = new BroadcastChannel('sar-study')
    channelRef.current = ch
    return () => ch.close()
  }, [])

  function handleMapAction(action: object) {
    channelRef.current?.postMessage(action)
  }

  // Non-passive wheel listener
  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    function onWheel(e: WheelEvent) {
      e.preventDefault()
      const rect = svg!.getBoundingClientRect()
      const pt = {
        x: (e.clientX - rect.left) / rect.width * 1000,
        y: (e.clientY - rect.top)  / rect.height * 800,
      }
      const factor = e.deltaY < 0 ? 1.2 : 1 / 1.2
      setView(v => {
        const newScale = Math.min(10, Math.max(0.25, v.scale * factor))
        const ratio = newScale / v.scale
        return { x: pt.x - (pt.x - v.x) * ratio, y: pt.y - (pt.y - v.y) * ratio, scale: newScale }
      })
    }
    svg.addEventListener('wheel', onWheel, { passive: false })
    return () => svg.removeEventListener('wheel', onWheel)
  }, [])

  function handlePointerDown(e: React.PointerEvent<SVGSVGElement>) {
    if (e.button !== 0) return
    e.currentTarget.setPointerCapture(e.pointerId)
    isPanning.current = true
    hasDragged.current = false
    lastClientPos.current = { x: e.clientX, y: e.clientY }
    setGrabbing(true)
  }

  function handlePointerMove(e: React.PointerEvent<SVGSVGElement>) {
    if (!isPanning.current) return
    const dx = e.clientX - lastClientPos.current.x
    const dy = e.clientY - lastClientPos.current.y
    lastClientPos.current = { x: e.clientX, y: e.clientY }
    if (Math.abs(dx) > 2 || Math.abs(dy) > 2) hasDragged.current = true
    const svg = svgRef.current
    if (!svg) return
    const rect = svg.getBoundingClientRect()
    setView(v => ({
      ...v,
      x: v.x + dx * 1000 / rect.width,
      y: v.y + dy * 800  / rect.height,
    }))
  }

  function handlePointerUp() {
    isPanning.current = false
    setGrabbing(false)
  }

  function handleClick() {
    if (!hasDragged.current) setSelectedMissionId(null)
    hasDragged.current = false
  }

  const deployedAssets = state.assets.filter(a => a.status !== 'available' && a.status !== 'failed')
  const failedAssets = state.assets.filter(a => a.status === 'failed')
  const groupTransform = `translate(${view.x}, ${view.y}) scale(${view.scale})`
  const isZoomed = view.scale !== 1 || view.x !== 0 || view.y !== 0

  return (
    <div className="flex h-screen bg-gray-950 overflow-hidden">
      {/* Left: SVG map */}
      <div className="flex-1 relative overflow-hidden">
        <svg
          ref={svgRef}
          viewBox="0 0 1000 800"
          className="w-full h-full"
          preserveAspectRatio="xMidYMid meet"
          style={{ cursor: grabbing ? 'grabbing' : 'grab' }}
          onClick={handleClick}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
        >
          <defs>
            <radialGradient id="hubGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
            </radialGradient>
            <filter id="assetGlow">
              <feGaussianBlur stdDeviation="2" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>

          <g transform={groupTransform}>
            {/* Background */}
            <rect width="1000" height="800" fill="#030712" />

            {/* Grid */}
            <MapGrid />

            {/* Range rings from hub */}
            <RangeRings />

            {/* Mission zones */}
            {[...state.missions]
              .sort((a, b) => {
                const order = { completed: 0, failed: 0, queued: 1, active: 2 }
                return order[a.status] - order[b.status]
              })
              .map(m => (
                <MissionZone
                  key={m.id}
                  mission={m}
                  elapsed={state.elapsed}
                  selected={m.id === selectedMissionId}
                  onReprioritiseTop={onReprioritiseTop}
                  onClick={e => { e.stopPropagation(); if (!hasDragged.current) setSelectedMissionId(id => id === m.id ? null : m.id) }}
                />
              ))}

            {/* Asset travel routes */}
            {deployedAssets.map(a => <AssetRoute key={`r-${a.id}`} asset={a} elapsed={state.elapsed} missions={state.missions} />)}

            {/* Asset dots */}
            {deployedAssets.map(a => <AssetDot key={a.id} asset={a} useCallsigns={useCallsigns} />)}

            {/* Failed asset markers */}
            {failedAssets.map(a => <FailedAssetMarker key={`f-${a.id}`} asset={a} useCallsigns={useCallsigns} />)}

            {/* Hub */}
            <HubMarker assets={state.assets} />
          </g>
        </svg>

        {/* Status bar */}
        <div className="absolute bottom-0 left-0 right-0 bg-black/60 backdrop-blur-sm px-4 py-1.5 flex items-center justify-between text-xs text-gray-400 border-t border-gray-800">
          <div className="flex items-center gap-2">
            <span>Session {state.sessionNumber}/3</span>
            <button
              onClick={() => setUseCallsigns(c => !c)}
              className={`px-1.5 py-0.5 rounded border transition-colors ${
                useCallsigns ? 'bg-blue-700 text-blue-100 border-blue-500' : 'bg-gray-800 text-gray-500 border-gray-700 hover:text-gray-300'
              }`}
            >
              {useCallsigns ? 'IDs' : 'Names'}
            </button>
          </div>
          <span className="font-mono text-amber-400 font-bold">{formatCountdown(state.elapsed)}</span>
          <span>
            Score <span className="text-white font-bold">{state.score}</span>
            <span className="text-red-400 ml-1">−{state.penaltyAccrued}</span>
          </span>
          <span>{state.missions.filter(m => m.status === 'active').length} active · {state.missions.filter(m => m.status === 'queued').length} queued</span>
          {isZoomed && (
            <button
              onClick={() => setView({ x: 0, y: 0, scale: 1 })}
              className="px-2 py-0.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700 transition-colors"
            >
              Reset view
            </button>
          )}
          {!isZoomed && <span className="text-gray-600">Scroll to zoom · drag to pan</span>}
        </div>
      </div>

      {/* Right: tactical sidebar */}
      <TacticalSidebar
        state={state}
        selectedMissionId={selectedMissionId}
        onSelectMission={setSelectedMissionId}
        onMapAction={handleMapAction}
      />
    </div>
  )
}

// ─── Tactical sidebar ─────────────────────────────────────────────────────

function TacticalSidebar({ state, selectedMissionId, onSelectMission, onMapAction }: {
  state: MapViewState
  selectedMissionId: string | null
  onSelectMission: (id: string | null) => void
  onMapAction: (action: object) => void
}) {
  const selectedMission = selectedMissionId ? state.missions.find(m => m.id === selectedMissionId) ?? null : null
  const liveMissions = state.missions.filter(m => m.status === 'queued' || m.status === 'active')

  return (
    <div className="w-80 flex-none border-l border-gray-800 bg-gray-900 flex flex-col overflow-hidden">
      {/* Sidebar header */}
      <div className="px-3 py-2 border-b border-gray-800 flex items-center justify-between">
        <span className="text-xs font-bold text-gray-400 uppercase tracking-wider">Tactical Detail</span>
        {selectedMissionId && (
          <button onClick={() => onSelectMission(null)} className="text-xs text-gray-600 hover:text-gray-400">← All</button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {!selectedMission ? (
          // Overview: session stats + mission list
          <>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="bg-gray-800 rounded p-2 space-y-0.5">
                <p className="text-gray-500">Elapsed</p>
                <p className="text-white font-mono font-bold">{formatSeconds(state.elapsed)}</p>
              </div>
              <div className="bg-gray-800 rounded p-2 space-y-0.5">
                <p className="text-gray-500">Score</p>
                <p className="text-white font-mono font-bold">{state.score}</p>
              </div>
              <div className="bg-gray-800 rounded p-2 space-y-0.5">
                <p className="text-gray-500">Reserve B/R/G</p>
                <p className="text-white font-mono">{state.reserve.Blue}/{state.reserve.Red}/{state.reserve.Green}</p>
              </div>
              <div className="bg-gray-800 rounded p-2 space-y-0.5">
                <p className="text-gray-500">Mode</p>
                <p className={`font-mono font-bold ${state.mode === 'agent' ? 'text-purple-400' : 'text-gray-300'}`}>
                  {state.mode === 'agent' ? 'Agent' : 'Manual'}
                </p>
              </div>
            </div>

            {liveMissions.length > 0 && (
              <div className="space-y-1">
                <p className="text-xs text-gray-500 uppercase tracking-wider">Active / Queued</p>
                {liveMissions.map(m => (
                  <button
                    key={m.id}
                    onClick={() => onSelectMission(m.id)}
                    className={`w-full text-left px-2 py-1.5 rounded border text-xs transition-colors ${
                      m.failureRecoveryPending ? 'border-red-700 bg-red-950/20 text-red-300' :
                      m.tacticalPending ? 'border-yellow-700 bg-yellow-950/10 text-yellow-300' :
                      m.status === 'queued' ? 'border-amber-800 bg-amber-950/20 text-amber-300' :
                      'border-gray-700 bg-gray-800 text-gray-300 hover:border-gray-500'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-bold">{m.id}</span>
                      <div className="flex items-center gap-1">
                        {m.failureRecoveryPending && <span className="text-red-400 font-bold">FAILURE</span>}
                        {m.tacticalPending && !m.failureRecoveryPending && <span className="text-yellow-400">PENDING</span>}
                        <span className="text-gray-500">Cat {m.category}</span>
                      </div>
                    </div>
                    <div className="text-gray-500 mt-0.5">
                      {m.tasks.filter(t => t.status === 'completed').length}/{m.tasks.length} tasks
                    </div>
                  </button>
                ))}
              </div>
            )}

            {liveMissions.length === 0 && (
              <p className="text-xs text-gray-600 text-center py-4">No active or queued missions</p>
            )}
          </>
        ) : (
          // Mission detail
          <MissionDetail mission={selectedMission} state={state} onMapAction={onMapAction} />
        )}
      </div>
    </div>
  )
}

function MissionDetail({ mission, state, onMapAction }: {
  mission: Mission
  state: MapViewState
  onMapAction: (action: object) => void
}) {
  const isAgent = state.mode === 'agent'

  return (
    <div className="space-y-3">
      {/* Mission header */}
      <div className="flex items-center gap-2">
        <span className="font-mono font-bold text-white">{mission.id}</span>
        <span className="text-xs px-1.5 py-0.5 rounded bg-gray-700 text-gray-300">Cat {mission.category}</span>
        <span className={`text-xs px-1.5 py-0.5 rounded ${
          mission.status === 'active' ? 'bg-blue-900/60 text-blue-300' :
          mission.status === 'queued' ? 'bg-amber-900/60 text-amber-300' :
          'bg-gray-700 text-gray-400'
        }`}>{mission.status}</span>
      </div>

      {/* Drone failure section */}
      {mission.failureRecoveryPending && mission.pendingRecoveryOptions && (
        <div className="space-y-2">
          <div className="px-2 py-1.5 bg-red-900/40 border border-red-700 rounded text-xs text-red-300">
            <p className="font-bold mb-1">DRONE FAILURE — {mission.failedDroneId}</p>
            <p className="text-red-400">Recovery required</p>
          </div>

          {isAgent && (
            <div className="space-y-1.5">
              <p className="text-xs text-gray-500">Recovery options:</p>
              {mission.pendingRecoveryOptions.map(opt => (
                <button
                  key={opt.type}
                  disabled={!opt.feasible}
                  onClick={() => onMapAction({ _mapAction: 'ACCEPT_RECOVERY', missionId: mission.id, recoveryType: opt.type })}
                  className={`w-full text-left px-2 py-1.5 rounded border text-xs transition-colors ${
                    opt.feasible
                      ? 'border-blue-700 bg-blue-900/30 text-blue-300 hover:bg-blue-800/40'
                      : 'border-gray-700 bg-gray-800 text-gray-600 cursor-not-allowed'
                  }`}
                >
                  <p className="font-bold">{opt.label}</p>
                  <p className="text-gray-400 mt-0.5">{opt.description}</p>
                  {opt.feasible && <p className="text-gray-500 mt-0.5">+{opt.expectedTimeImpact}s est.</p>}
                </button>
              ))}
            </div>
          )}

          {!isAgent && (
            <div className="space-y-1.5">
              <p className="text-xs text-gray-500">Select a replacement drone:</p>
              {state.assets.filter(a => a.status === 'available').slice(0, 8).map(a => (
                <button
                  key={a.id}
                  onClick={() => {
                    const task = mission.tasks.find(t => t.status === 'pending')
                    if (task) onMapAction({ _mapAction: 'APPLY_MANUAL_RECOVERY', missionId: mission.id, taskId: task.id, newAssetId: a.id })
                  }}
                  className="w-full text-left px-2 py-1 rounded border border-gray-700 bg-gray-800 hover:border-gray-500 text-xs text-gray-300 transition-colors"
                >
                  {a.id} ({a.type})
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tactical pending section (agent mode) */}
      {mission.tacticalPending && !mission.failureRecoveryPending && mission.pendingAllocation && (
        <div className="space-y-2">
          <div className="px-2 py-1.5 bg-yellow-900/30 border border-yellow-700 rounded text-xs text-yellow-300">
            <p className="font-bold">Tactical allocation pending</p>
            <p className="text-yellow-500 mt-0.5">
              {mission.pendingAllocation.strategyName} — {mission.tasks.length} tasks
            </p>
          </div>

          {/* Task assignment preview */}
          <div className="space-y-1">
            <p className="text-xs text-gray-500">Planned assignments:</p>
            {mission.tasks.map(task => {
              const assignedIds = mission.pendingAllocation!.taskAssignments[task.id] ?? []
              return (
                <div key={task.id} className="flex items-center gap-2 text-xs">
                  <span className="text-gray-400">{TASK_SHORT_MAP[task.type]}</span>
                  <span className="text-gray-600">{assignedIds.join(', ') || 'unassigned'}</span>
                </div>
              )
            })}
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => onMapAction({ _mapAction: 'CONFIRM_TACTICAL', missionId: mission.id })}
              className="flex-1 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-white text-xs font-semibold transition-colors"
            >
              Confirm Allocation
            </button>
            <button
              onClick={() => onMapAction({ _mapAction: 'OVERRIDE_TACTICAL', missionId: mission.id })}
              className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-gray-300 text-xs transition-colors"
            >
              Override
            </button>
          </div>
        </div>
      )}

      {/* Task status list */}
      {!mission.tacticalPending && !mission.failureRecoveryPending && (
        <div className="space-y-1">
          <p className="text-xs text-gray-500 uppercase tracking-wider">Tasks</p>
          {mission.tasks.map(task => {
            const assigned = state.assets.filter(a => task.assignedAssetIds.includes(a.id))
            const eta = task.completionTime ? Math.max(0, task.completionTime - state.elapsed) : null
            return (
              <div key={task.id} className="flex items-start justify-between text-xs bg-gray-800 rounded px-2 py-1.5">
                <div className="flex items-center gap-1.5">
                  <span
                    className="px-1 h-5 rounded flex items-center justify-center text-white font-bold"
                    style={{ background: TASK_DOT_COLOR[task.status] + '99', fontSize: '9px', minWidth: '22px' }}
                  >
                    {TASK_SHORT_MAP[task.type]}
                  </span>
                  <span className="text-gray-400 capitalize">{task.status}</span>
                  {assigned.length > 0 && (
                    <span className="text-gray-600 font-mono">{assigned.map(a => a.id).join(' ')}</span>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  {eta !== null && task.status !== 'completed' && task.status !== 'failed' && (
                    <span className="text-gray-500 font-mono">{formatSeconds(eta)}</span>
                  )}
                  {task.status === 'completed' && <span className="text-green-400">done</span>}
                  {task.status === 'failed' && <span className="text-red-400">failed</span>}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* ETA */}
      {mission.status === 'active' && (
        <div className="text-xs text-blue-400 font-mono">
          Overall ETA: {formatSeconds(Math.max(0,
            Math.max(...mission.tasks.map(t => t.completionTime ?? 0)) - state.elapsed,
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Grid ─────────────────────────────────────────────────────────────────

function MapGrid() {
  const v = Array.from({ length: 11 }, (_, i) => i * 100)
  const h = Array.from({ length: 9 }, (_, i) => i * 100)
  return (
    <g stroke="#1e293b" strokeWidth={0.5}>
      {v.map(x => <line key={`v${x}`} x1={x} y1={0} x2={x} y2={800} />)}
      {h.map(y => <line key={`h${y}`} x1={0} y1={y} x2={1000} y2={y} />)}
    </g>
  )
}

// ─── Range rings ──────────────────────────────────────────────────────────

function RangeRings() {
  const rings = [150, 300, 450]
  return (
    <g fill="none">
      {rings.map(r => (
        <circle
          key={r}
          cx={HUB.x} cy={HUB.y} r={r}
          stroke="#1e3a5f"
          strokeWidth={0.8}
          strokeDasharray={r === 150 ? '3,5' : '2,8'}
        />
      ))}
      <text x={HUB.x + 152} y={HUB.y - 4} fontSize={8} fill="#1e3a5f">150</text>
      <text x={HUB.x + 302} y={HUB.y - 4} fontSize={8} fill="#1e3a5f">300</text>
    </g>
  )
}

// ─── Hub ──────────────────────────────────────────────────────────────────

function HubMarker({ assets }: { assets: Asset[] }) {
  const byType = (t: AssetType) => assets.filter(a => a.type === t && a.status === 'available').length

  return (
    <g>
      <circle cx={HUB.x} cy={HUB.y} r={40} fill="url(#hubGlow)" />
      <circle cx={HUB.x} cy={HUB.y} r={18} fill="none" stroke="#475569" strokeWidth={1.5} />
      <circle cx={HUB.x} cy={HUB.y} r={8} fill="#1e293b" stroke="#64748b" strokeWidth={1} />
      <line x1={HUB.x - 12} y1={HUB.y} x2={HUB.x + 12} y2={HUB.y} stroke="#64748b" strokeWidth={1} />
      <line x1={HUB.x} y1={HUB.y - 12} x2={HUB.x} y2={HUB.y + 12} stroke="#64748b" strokeWidth={1} />
      <text x={HUB.x} y={HUB.y + 30} textAnchor="middle" fontSize={9} fill="#64748b" letterSpacing="0.05em">HUB</text>
      <text x={HUB.x - 24} y={HUB.y - 24} textAnchor="middle" fontSize={8} fill="#60a5fa">B:{byType('Blue')}</text>
      <text x={HUB.x + 24} y={HUB.y - 24} textAnchor="middle" fontSize={8} fill="#f87171">R:{byType('Red')}</text>
      <text x={HUB.x}      y={HUB.y - 28} textAnchor="middle" fontSize={8} fill="#4ade80">G:{byType('Green')}</text>
    </g>
  )
}

// ─── Mission zone ─────────────────────────────────────────────────────────

function mapPenaltyUrgency(pts: number): 'none' | 'low' | 'med' | 'high' {
  if (pts < 20)  return 'none'
  if (pts < 50)  return 'low'
  if (pts < 100) return 'med'
  return 'high'
}

const URGENCY_STROKE: Record<'none'|'low'|'med'|'high', string | null> = {
  none: null,
  low:  '#ca8a04',
  med:  '#ea580c',
  high: '#dc2626',
}

function MissionZone({
  mission, elapsed, selected, onReprioritiseTop, onClick,
}: {
  mission: Mission
  elapsed: number
  selected: boolean
  onReprioritiseTop?: (missionId: string, taskId: string) => void
  onClick: (e: React.MouseEvent) => void
}) {
  const cx = mission.zoneCenter.x
  const cy = mission.zoneCenter.y
  const r = mission.zoneRadius
  const isDone = mission.status === 'completed' || mission.status === 'failed'
  const isActive = mission.status === 'active'
  const isLive = mission.status === 'queued' || isActive

  const completedTasks = mission.tasks.filter(t => t.status === 'completed').length
  const totalTasks = mission.tasks.length

  const waitSecs = isLive ? Math.max(0, (mission.completionTime ?? elapsed) - mission.arrivalTime) : 0
  const penaltyPts = isLive ? Math.round(CATEGORY_PENALTY_RATE[mission.category] * waitSecs) : 0
  const missionValue = mission.tasks.reduce((sum, t) => sum + TASK_WEIGHT[t.type], 0)
  const urgency = isLive ? mapPenaltyUrgency(penaltyPts) : 'none'
  const urgencyColor = URGENCY_STROKE[urgency]

  const manualPriorityIds: string[] = mission.manualPriorityIds ?? []

  const earnedValue = mission.tasks.filter(t => t.status === 'completed').reduce((sum, t) => sum + TASK_WEIGHT[t.type], 0)
  const progressFrac = missionValue > 0 ? earnedValue / missionValue : 0

  const isAllocating = false  // No longer tracked via MapViewState in new design
  const hasPendingIssue = mission.tacticalPending || mission.failureRecoveryPending

  return (
    <g onClick={onClick} style={{ cursor: isDone ? 'default' : 'pointer' }}>
      {selected && (
        <circle cx={cx} cy={cy} r={r + 6} fill="none" stroke="white" strokeWidth={1} strokeOpacity={0.4} strokeDasharray="4,4" />
      )}
      {hasPendingIssue && (
        <circle cx={cx} cy={cy} r={r + 3} fill="none"
          stroke={mission.failureRecoveryPending ? '#dc2626' : '#ca8a04'}
          strokeWidth={1.5} strokeOpacity={0.7}
          strokeDasharray="3,3"
        />
      )}
      <circle
        cx={cx} cy={cy} r={r}
        fill={ZONE_FILL[mission.status]}
        stroke={isAllocating ? '#3b82f6' : urgencyColor ?? ZONE_STROKE[mission.status]}
        strokeWidth={isAllocating ? 2 : selected ? 2 : urgency !== 'none' ? 1.8 : 1.2}
        strokeDasharray={mission.status === 'queued' ? '5,4' : 'none'}
        strokeOpacity={isDone ? 0.4 : 0.9}
      />
      {isLive && missionValue > 0 && (
        <ProgressArc cx={cx} cy={cy} r={r} fraction={progressFrac} />
      )}
      {mission.tasks.map(t => {
        const postAllocIdx = isActive ? manualPriorityIds.indexOf(t.id) : -1
        const canReprioritise = isActive && !!onReprioritiseTop && (t.status === 'pending' || t.status === 'traveling')
        return (
          <TaskWaypoint
            key={t.id}
            task={t}
            priorityIndex={postAllocIdx}
            onReprioritiseTop={canReprioritise ? () => onReprioritiseTop!(mission.id, t.id) : undefined}
          />
        )
      })}
      <text x={cx} y={cy - r - 6} textAnchor="middle" fontSize={9} fill="#94a3b8" fontFamily="monospace">
        {mission.id}
      </text>
      <text x={cx} y={cy - r - 16} textAnchor="middle" fontSize={8} fill={isDone ? '#4b5563' : '#64748b'}>
        Cat {mission.category} · {completedTasks}/{totalTasks}
      </text>
      {isLive && penaltyPts > 0 && (
        <text
          x={cx} y={cy + r + 14}
          textAnchor="middle" fontSize={8}
          fill={urgencyColor ?? '#6b7280'}
          fontFamily="monospace"
        >
          −{penaltyPts} pts
        </text>
      )}
    </g>
  )
}

function arcPath(cx: number, cy: number, r: number, fraction: number): string {
  const clipped = Math.min(1, Math.max(0, fraction))
  const start = -Math.PI / 2
  const end = start + clipped * 2 * Math.PI
  if (clipped >= 1) return `M ${cx},${cy - r} A ${r},${r} 0 1 1 ${cx - 0.01},${cy - r} Z`
  const x1 = cx + r * Math.cos(start), y1 = cy + r * Math.sin(start)
  const x2 = cx + r * Math.cos(end),   y2 = cy + r * Math.sin(end)
  return `M ${x1},${y1} A ${r},${r} 0 ${clipped > 0.5 ? 1 : 0} 1 ${x2},${y2}`
}

function ProgressArc({ cx, cy, r, fraction }: { cx: number; cy: number; r: number; fraction: number }) {
  if (fraction <= 0) return null
  return <path d={arcPath(cx, cy, r + 4, fraction)} fill="none" stroke="#10b981" strokeWidth={2} strokeLinecap="round" />
}

function TaskWaypoint({ task, priorityIndex = -1, onReprioritiseTop }: {
  task: Task
  priorityIndex?: number
  onReprioritiseTop?: () => void
}) {
  const { x, y } = task.waypoint
  const isExecuting = task.status === 'executing'
  const color = TASK_DOT_COLOR[task.status]
  const canReprioritise = !!onReprioritiseTop
  const isPriority = priorityIndex >= 0

  function handleClick(e: React.MouseEvent) {
    e.stopPropagation()
    if (canReprioritise) onReprioritiseTop!()
  }

  function handlePointerDown(e: React.PointerEvent) {
    e.stopPropagation()
  }

  const interactProps = canReprioritise
    ? { onClick: handleClick, onPointerDown: handlePointerDown, style: { cursor: 'pointer' as const } }
    : {}

  return (
    <g>
      {isExecuting && (
        <circle cx={x} cy={y} r={8} fill="none" stroke={color} strokeWidth={1} strokeOpacity={0.4}>
          <animate attributeName="r" values="5;10;5" dur="2s" repeatCount="indefinite" />
          <animate attributeName="stroke-opacity" values="0.5;0;0.5" dur="2s" repeatCount="indefinite" />
        </circle>
      )}
      {canReprioritise && (
        <circle cx={x} cy={y} r={10} fill="transparent" {...interactProps} />
      )}
      {isPriority && (
        <circle cx={x} cy={y} r={7} fill="none" stroke="#fbbf24"
          strokeWidth={1.3} strokeOpacity={0.9} {...interactProps} />
      )}
      <circle
        cx={x} cy={y} r={8}
        fill="#080f1a"
        stroke={color} strokeWidth={1.4} strokeOpacity={task.status === 'completed' ? 0.35 : 0.85}
        {...interactProps}
      />
      <image
        href={TASK_ICON[task.type]}
        x={x - 7} y={y - 7}
        width={14} height={14}
        opacity={task.status === 'completed' ? 0.25 : 0.88}
        style={{ pointerEvents: 'none' }}
      />
      {isPriority && (
        <text x={x + 6} y={y - 4} fontSize={7} fill="#fbbf24" fontWeight="bold" {...interactProps}>
          {priorityIndex + 1}
        </text>
      )}
    </g>
  )
}

// ─── Asset route line ─────────────────────────────────────────────────────

function AssetRoute({ asset, elapsed, missions }: { asset: Asset; elapsed: number; missions: Mission[] }) {
  const color = ASSET_COLOR[asset.type]
  const { travelFrom, targetPosition, travelStartElapsed, travelEndElapsed } = asset

  if (travelEndElapsed <= travelStartElapsed) return null

  const mx = (travelFrom.x + targetPosition.x) / 2
  const my = (travelFrom.y + targetPosition.y) / 2
  const remaining = Math.max(0, travelEndElapsed - elapsed)
  const showEta = remaining > 0.5

  const mission = missions.find(m => m.id === asset.currentMissionId)
  const futureTasks = mission
    ? mission.tasks.filter(t =>
        t.id !== asset.currentTaskId &&
        t.assignedAssetIds.includes(asset.id) &&
        t.status !== 'completed' && t.status !== 'failed',
      )
    : []

  const pathPoints: Array<{ x: number; y: number }> = [targetPosition, ...futureTasks.map(t => t.waypoint)]
  const showReturn = asset.status === 'deployed' && futureTasks.length === 0

  return (
    <g>
      <line
        x1={travelFrom.x} y1={travelFrom.y}
        x2={targetPosition.x} y2={targetPosition.y}
        stroke={color} strokeWidth={0.8} strokeDasharray="3,6" strokeOpacity={0.35}
      />
      <circle cx={targetPosition.x} cy={targetPosition.y} r={3} fill="none" stroke={color} strokeWidth={1} strokeOpacity={0.5} />
      {showEta && (
        <text x={mx} y={my - 5} textAnchor="middle" fontSize={8} fill={color} fillOpacity={0.7}>
          {formatSeconds(remaining)}
        </text>
      )}
      {pathPoints.length > 1 && (
        <polyline
          points={pathPoints.map(p => `${p.x},${p.y}`).join(' ')}
          fill="none"
          stroke={color}
          strokeWidth={0.7}
          strokeOpacity={0.4}
          strokeLinejoin="round"
        />
      )}
      {(showReturn || futureTasks.length > 0) && (() => {
        const lastPt = pathPoints[pathPoints.length - 1]
        return (
          <line
            x1={lastPt.x} y1={lastPt.y}
            x2={HUB.x} y2={HUB.y}
            stroke={color} strokeWidth={0.5} strokeDasharray="2,8" strokeOpacity={0.2}
          />
        )
      })()}
    </g>
  )
}

// ─── Asset dot ────────────────────────────────────────────────────────────

function AssetDot({ asset, useCallsigns }: { asset: Asset; useCallsigns: boolean }) {
  const { x, y } = asset.position
  const color = ASSET_COLOR[asset.type]
  const isReturning = asset.status === 'returning'
  const label = useCallsigns ? (ASSET_CALLSIGNS[asset.id] ?? asset.id) : asset.id
  const s = 18

  return (
    <g filter="url(#assetGlow)" opacity={isReturning ? 0.55 : 1}>
      <circle cx={x + 1} cy={y + 1} r={s / 2 + 1} fill="black" fillOpacity={0.35} />
      <image href={DRONE_ICON[asset.type]} x={x - s / 2} y={y - s / 2} width={s} height={s} />
      <AssetDirectionPip asset={asset} color={color} />
      <text x={x + s / 2 + 3} y={y + 3} fontSize={8} fill={color} fillOpacity={0.85} fontFamily="monospace">
        {label}
      </text>
    </g>
  )
}

function AssetDirectionPip({ asset, color }: { asset: Asset; color: string }) {
  const { position, targetPosition } = asset
  const dx = targetPosition.x - position.x
  const dy = targetPosition.y - position.y
  const d = Math.hypot(dx, dy)
  if (d < 1) return null
  const norm = 13 / d
  return (
    <line
      x1={position.x} y1={position.y}
      x2={position.x + dx * norm} y2={position.y + dy * norm}
      stroke={color} strokeWidth={1.8} strokeLinecap="round" strokeOpacity={0.9}
    />
  )
}

// ─── Failed asset marker ──────────────────────────────────────────────────

function FailedAssetMarker({ asset, useCallsigns }: { asset: Asset; useCallsigns: boolean }) {
  const { x, y } = asset.position
  const label = useCallsigns ? (ASSET_CALLSIGNS[asset.id] ?? asset.id) : asset.id
  const s = 10

  return (
    <g opacity={0.5}>
      <circle cx={x} cy={y} r={s / 2 + 2} fill="#1f2937" stroke="#6b7280" strokeWidth={1} />
      <line x1={x - s/3} y1={y - s/3} x2={x + s/3} y2={y + s/3} stroke="#6b7280" strokeWidth={2} />
      <line x1={x + s/3} y1={y - s/3} x2={x - s/3} y2={y + s/3} stroke="#6b7280" strokeWidth={2} />
      <text x={x + s / 2 + 3} y={y + 3} fontSize={7} fill="#6b7280" fontFamily="monospace">
        {label}
      </text>
    </g>
  )
}

// ─── Utilities ────────────────────────────────────────────────────────────

function formatCountdown(elapsed: number): string {
  const rem = Math.max(0, 600 - elapsed)
  const m = Math.floor(rem / 60)
  const s = Math.floor(rem % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatSeconds(s: number): string {
  if (s < 60) return `${Math.round(s)}s`
  return `${Math.floor(s / 60)}m${Math.round(s % 60).toString().padStart(2, '0')}s`
}

export type { MapViewState }
