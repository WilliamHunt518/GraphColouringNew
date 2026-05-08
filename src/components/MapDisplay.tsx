import { useState } from 'react'
import type { MapViewState, Asset, Mission, Task, AssetType, TaskStatus } from '../types'
import { HUB } from '../utils/missionGen'

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

const ZONE_FILL: Record<Mission['status'], string> = {
  queued:    'rgba(120,53,15,0.12)',
  active:    'rgba(29,78,216,0.10)',
  completed: 'rgba(55,65,81,0.06)',
  failed:    'rgba(127,29,29,0.06)',
}

// ─── Main component ───────────────────────────────────────────────────────

interface Props {
  state: MapViewState
}

export default function MapDisplay({ state }: Props) {
  const [selectedMissionId, setSelectedMissionId] = useState<string | null>(null)
  const selectedMission = state.missions.find(m => m.id === selectedMissionId) ?? null

  const deployedAssets = state.assets.filter(a => a.status !== 'available')

  return (
    <div className="relative w-full h-full bg-slate-950 overflow-hidden select-none">
      <svg
        viewBox="0 0 1000 800"
        className="w-full h-full"
        preserveAspectRatio="xMidYMid meet"
        onClick={() => setSelectedMissionId(null)}
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

        {/* Background */}
        <rect width="1000" height="800" fill="#030712" />

        {/* Grid */}
        <MapGrid />

        {/* Range rings from hub */}
        <RangeRings />

        {/* Mission zones (rendered back-to-front) */}
        {[...state.missions]
          .sort((a, b) => {
            const order = { completed: 0, failed: 0, queued: 1, active: 2 }
            return order[a.status] - order[b.status]
          })
          .map(m => (
            <MissionZone
              key={m.id}
              mission={m}
              selected={m.id === selectedMissionId}
              onClick={e => { e.stopPropagation(); setSelectedMissionId(m.id) }}
            />
          ))}

        {/* Asset travel routes (rendered below dots) */}
        {deployedAssets.map(a => <AssetRoute key={`r-${a.id}`} asset={a} elapsed={state.elapsed} />)}

        {/* Asset dots */}
        {deployedAssets.map(a => <AssetDot key={a.id} asset={a} />)}

        {/* Hub */}
        <HubMarker assets={state.assets} />
      </svg>

      {/* Info overlay */}
      {selectedMission && (
        <MissionInfoOverlay
          mission={selectedMission}
          assets={state.assets}
          elapsed={state.elapsed}
          onClose={() => setSelectedMissionId(null)}
        />
      )}

      {/* Status bar */}
      <div className="absolute bottom-0 left-0 right-0 bg-black/60 backdrop-blur-sm px-4 py-1.5 flex items-center justify-between text-xs text-gray-400 border-t border-gray-800">
        <span>Session {state.sessionNumber}/3</span>
        <span className="font-mono text-amber-400 font-bold">{formatCountdown(state.elapsed)}</span>
        <span>Score <span className="text-white font-bold">{state.score}</span></span>
        <span>{state.missions.filter(m => m.status === 'active').length} active · {state.missions.filter(m => m.status === 'queued').length} queued</span>
      </div>
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
      {/* Glow */}
      <circle cx={HUB.x} cy={HUB.y} r={40} fill="url(#hubGlow)" />
      {/* Outer ring */}
      <circle cx={HUB.x} cy={HUB.y} r={18} fill="none" stroke="#475569" strokeWidth={1.5} />
      {/* Inner circle */}
      <circle cx={HUB.x} cy={HUB.y} r={8} fill="#1e293b" stroke="#64748b" strokeWidth={1} />
      {/* Cross */}
      <line x1={HUB.x - 12} y1={HUB.y} x2={HUB.x + 12} y2={HUB.y} stroke="#64748b" strokeWidth={1} />
      <line x1={HUB.x} y1={HUB.y - 12} x2={HUB.x} y2={HUB.y + 12} stroke="#64748b" strokeWidth={1} />
      {/* Label */}
      <text x={HUB.x} y={HUB.y + 30} textAnchor="middle" fontSize={9} fill="#64748b" letterSpacing="0.05em">HUB</text>
      {/* Available counts */}
      <text x={HUB.x - 24} y={HUB.y - 24} textAnchor="middle" fontSize={8} fill="#60a5fa">B:{byType('Blue')}</text>
      <text x={HUB.x + 24} y={HUB.y - 24} textAnchor="middle" fontSize={8} fill="#f87171">R:{byType('Red')}</text>
      <text x={HUB.x}      y={HUB.y - 28} textAnchor="middle" fontSize={8} fill="#4ade80">G:{byType('Green')}</text>
    </g>
  )
}

// ─── Mission zone ─────────────────────────────────────────────────────────

function MissionZone({
  mission, selected, onClick,
}: {
  mission: Mission
  selected: boolean
  onClick: (e: React.MouseEvent) => void
}) {
  const cx = mission.zoneCenter.x
  const cy = mission.zoneCenter.y
  const r = mission.zoneRadius
  const isDone = mission.status === 'completed' || mission.status === 'failed'

  const completedTasks = mission.tasks.filter(t => t.status === 'completed').length
  const totalTasks = mission.tasks.length

  return (
    <g onClick={onClick} style={{ cursor: isDone ? 'default' : 'pointer' }}>
      {/* Selected highlight ring */}
      {selected && (
        <circle cx={cx} cy={cy} r={r + 6} fill="none" stroke="white" strokeWidth={1} strokeOpacity={0.4} strokeDasharray="4,4" />
      )}

      {/* Zone circle */}
      <circle
        cx={cx} cy={cy} r={r}
        fill={ZONE_FILL[mission.status]}
        stroke={ZONE_STROKE[mission.status]}
        strokeWidth={selected ? 2 : 1.2}
        strokeDasharray={mission.status === 'queued' ? '5,4' : 'none'}
        strokeOpacity={isDone ? 0.4 : 0.9}
      />

      {/* Progress arc for active missions */}
      {mission.status === 'active' && totalTasks > 0 && (
        <ProgressArc cx={cx} cy={cy} r={r} fraction={completedTasks / totalTasks} />
      )}

      {/* Waypoint dots for each task */}
      {mission.tasks.map(t => (
        <TaskWaypoint key={t.id} task={t} />
      ))}

      {/* Zone label */}
      <text x={cx} y={cy - r - 6} textAnchor="middle" fontSize={9} fill="#94a3b8" fontFamily="monospace">
        {mission.id}
      </text>
      <text x={cx} y={cy - r - 16} textAnchor="middle" fontSize={8} fill={isDone ? '#4b5563' : '#64748b'}>
        Cat {mission.category} · {completedTasks}/{totalTasks}
      </text>
    </g>
  )
}

function ProgressArc({ cx, cy, r, fraction }: { cx: number; cy: number; r: number; fraction: number }) {
  if (fraction <= 0) return null
  const clipped = Math.min(1, fraction)
  // Draw arc around the outside of the zone circle
  const outerR = r + 4
  const start = -Math.PI / 2
  const end = start + clipped * 2 * Math.PI
  const x1 = cx + outerR * Math.cos(start)
  const y1 = cy + outerR * Math.sin(start)
  const x2 = cx + outerR * Math.cos(end)
  const y2 = cy + outerR * Math.sin(end)
  const large = clipped > 0.5 ? 1 : 0
  const d = clipped >= 1
    ? `M ${cx},${cy - outerR} A ${outerR},${outerR} 0 1 1 ${cx - 0.01},${cy - outerR} Z`
    : `M ${x1},${y1} A ${outerR},${outerR} 0 ${large} 1 ${x2},${y2}`
  return <path d={d} fill="none" stroke="#10b981" strokeWidth={2} strokeLinecap="round" />
}

function TaskWaypoint({ task }: { task: Task }) {
  const { x, y } = task.waypoint
  const isExecuting = task.status === 'executing'
  const color = TASK_DOT_COLOR[task.status]

  return (
    <g>
      {/* Pulse ring for executing tasks */}
      {isExecuting && (
        <circle cx={x} cy={y} r={8} fill="none" stroke={color} strokeWidth={1} strokeOpacity={0.4}>
          <animate attributeName="r" values="5;10;5" dur="2s" repeatCount="indefinite" />
          <animate attributeName="stroke-opacity" values="0.5;0;0.5" dur="2s" repeatCount="indefinite" />
        </circle>
      )}
      <circle cx={x} cy={y} r={4} fill={color} />
      <text x={x} y={y - 7} textAnchor="middle" fontSize={7} fill={color} fontFamily="monospace">
        T{task.type}
      </text>
    </g>
  )
}

// ─── Asset route line ─────────────────────────────────────────────────────

function AssetRoute({ asset, elapsed }: { asset: Asset; elapsed: number }) {
  const color = ASSET_COLOR[asset.type]
  const { travelFrom, targetPosition, travelStartElapsed, travelEndElapsed } = asset

  // Skip if journey is very short or already completed
  if (travelEndElapsed <= travelStartElapsed) return null

  const mx = (travelFrom.x + targetPosition.x) / 2
  const my = (travelFrom.y + targetPosition.y) / 2

  // Travel time remaining
  const remaining = Math.max(0, travelEndElapsed - elapsed)
  const showEta = remaining > 0.5

  return (
    <g>
      {/* Route line */}
      <line
        x1={travelFrom.x} y1={travelFrom.y}
        x2={targetPosition.x} y2={targetPosition.y}
        stroke={color}
        strokeWidth={0.8}
        strokeDasharray="3,6"
        strokeOpacity={0.35}
      />
      {/* Destination marker */}
      <circle
        cx={targetPosition.x} cy={targetPosition.y}
        r={3} fill="none"
        stroke={color} strokeWidth={1} strokeOpacity={0.5}
      />
      {/* Travel time annotation */}
      {showEta && (
        <text x={mx} y={my - 5} textAnchor="middle" fontSize={8} fill={color} fillOpacity={0.7}>
          {formatSeconds(remaining)}
        </text>
      )}
    </g>
  )
}

// ─── Asset dot ────────────────────────────────────────────────────────────

function AssetDot({ asset }: { asset: Asset }) {
  const { x, y } = asset.position
  const color = ASSET_COLOR[asset.type]
  const isReturning = asset.status === 'returning'

  return (
    <g filter="url(#assetGlow)">
      {/* Shadow */}
      <circle cx={x + 1} cy={y + 1} r={5} fill="black" fillOpacity={0.4} />
      {/* Body */}
      <circle
        cx={x} cy={y} r={5}
        fill={color}
        fillOpacity={isReturning ? 0.5 : 0.95}
        stroke={isReturning ? color : 'white'}
        strokeWidth={isReturning ? 0 : 0.8}
        strokeOpacity={0.6}
      />
      {/* Direction pip — shows a small line in direction of travel */}
      <AssetDirectionPip asset={asset} color={color} />
      {/* Label */}
      <text x={x + 8} y={y + 3} fontSize={8} fill={color} fillOpacity={0.85} fontFamily="monospace">
        {asset.id}
      </text>
    </g>
  )
}

function AssetDirectionPip({ asset, color }: { asset: Asset; color: string }) {
  const { position, targetPosition } = asset
  const dx = targetPosition.x - position.x
  const dy = targetPosition.y - position.y
  const dist = Math.hypot(dx, dy)
  if (dist < 1) return null
  const norm = 7 / dist
  return (
    <line
      x1={position.x} y1={position.y}
      x2={position.x + dx * norm} y2={position.y + dy * norm}
      stroke={color} strokeWidth={1.5} strokeLinecap="round"
    />
  )
}

// ─── Mission info overlay ─────────────────────────────────────────────────

function MissionInfoOverlay({
  mission, assets, elapsed, onClose,
}: {
  mission: Mission
  assets: Asset[]
  elapsed: number
  onClose: () => void
}) {
  const taskStatusLabel: Record<TaskStatus, string> = {
    pending: 'Pending',
    traveling: 'En route',
    executing: 'Executing',
    completed: 'Complete',
    failed: 'Failed',
  }

  return (
    <div
      className="absolute top-2 right-2 w-64 bg-gray-900/95 border border-gray-700 rounded-xl p-4 space-y-3 shadow-2xl z-10"
      onClick={e => e.stopPropagation()}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-mono font-bold text-white text-sm">{mission.id}</span>
          <span className="text-xs text-gray-400">Cat {mission.category}</span>
        </div>
        <button onClick={onClose} className="text-gray-500 hover:text-gray-200 text-lg leading-none">×</button>
      </div>

      <div className="text-xs text-gray-400">
        Zone center: ({Math.round(mission.zoneCenter.x)}, {Math.round(mission.zoneCenter.y)})
      </div>

      <div className="space-y-1.5">
        {mission.tasks.map(task => {
          const assigned = assets.filter(a => task.assignedAssetIds.includes(a.id))
          const eta = task.completionTime ? Math.max(0, task.completionTime - elapsed) : null
          return (
            <div key={task.id} className="flex items-start justify-between text-xs">
              <div className="flex items-center gap-1.5">
                <span
                  className="w-5 h-5 rounded flex items-center justify-center text-white font-bold text-xs"
                  style={{ background: TASK_DOT_COLOR[task.status] + '99' }}
                >
                  {task.type}
                </span>
                <span className="text-gray-300">{taskStatusLabel[task.status]}</span>
                {assigned.length > 0 && (
                  <span className="text-gray-500 font-mono">{assigned.map(a => a.id).join(' ')}</span>
                )}
              </div>
              {eta !== null && task.status !== 'completed' && task.status !== 'failed' && (
                <span className="text-gray-500 font-mono">{formatSeconds(eta)}</span>
              )}
              {task.status === 'completed' && <span className="text-green-400">✓</span>}
              {task.status === 'failed' && <span className="text-red-400">✗</span>}
            </div>
          )
        })}
      </div>

      {mission.status === 'active' && (
        <div className="text-xs text-blue-400 font-mono">
          ETA: {formatSeconds(Math.max(0,
            Math.max(...mission.tasks.map(t => t.completionTime ?? 0)) - elapsed,
          ))}
        </div>
      )}
    </div>
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

// Re-export for GameShell
export type { MapViewState }
