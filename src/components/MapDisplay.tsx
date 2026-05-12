import { useState, useEffect, useRef } from 'react'
import type { MapViewState, Asset, Mission, Task, AssetType, TaskStatus } from '../types'
import { HUB, ASSET_CALLSIGNS } from '../utils/missionGen'

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
  onToggleTaskPriority?: (taskId: string) => void
  onReprioritiseTop?: (missionId: string, taskId: string) => void
}

export default function MapDisplay({ state, onToggleTaskPriority, onReprioritiseTop }: Props) {
  const [selectedMissionId, setSelectedMissionId] = useState<string | null>(null)
  const [useCallsigns, setUseCallsigns] = useState(false)
  const selectedMission = state.missions.find(m => m.id === selectedMissionId) ?? null

  // Pan / zoom state
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 })
  const [grabbing, setGrabbing] = useState(false)
  const svgRef = useRef<SVGSVGElement>(null)
  const isPanning = useRef(false)
  const hasDragged = useRef(false)
  const lastClientPos = useRef({ x: 0, y: 0 })

  // Non-passive wheel listener (React synthetic events can't preventDefault reliably)
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

  const deployedAssets = state.assets.filter(a => a.status !== 'available')
  const groupTransform = `translate(${view.x}, ${view.y}) scale(${view.scale})`
  const isZoomed = view.scale !== 1 || view.x !== 0 || view.y !== 0

  return (
    <div className="relative w-full h-full bg-slate-950 overflow-hidden select-none">
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
                copilotMissionId={state.copilotMissionId}
                priorityTaskIds={state.priorityTaskIds}
                onToggleTaskPriority={onToggleTaskPriority}
                onReprioritiseTop={onReprioritiseTop}
                onClick={e => { e.stopPropagation(); if (!hasDragged.current) setSelectedMissionId(m.id) }}
              />
            ))}

          {/* Asset travel routes (rendered below dots) */}
          {deployedAssets.map(a => <AssetRoute key={`r-${a.id}`} asset={a} elapsed={state.elapsed} missions={state.missions} />)}

          {/* Asset dots */}
          {deployedAssets.map(a => <AssetDot key={a.id} asset={a} useCallsigns={useCallsigns} />)}

          {/* Hub */}
          <HubMarker assets={state.assets} />
        </g>
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
        <span>Score <span className="text-white font-bold">{state.score}</span></span>
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

function MissionZone({
  mission, selected, copilotMissionId, priorityTaskIds, onToggleTaskPriority, onReprioritiseTop, onClick,
}: {
  mission: Mission
  selected: boolean
  copilotMissionId: string | null
  priorityTaskIds: string[]
  onToggleTaskPriority?: (taskId: string) => void
  onReprioritiseTop?: (missionId: string, taskId: string) => void
  onClick: (e: React.MouseEvent) => void
}) {
  const cx = mission.zoneCenter.x
  const cy = mission.zoneCenter.y
  const r = mission.zoneRadius
  const isDone = mission.status === 'completed' || mission.status === 'failed'
  const isAllocating = mission.id === copilotMissionId
  const isActive = mission.status === 'active'

  const completedTasks = mission.tasks.filter(t => t.status === 'completed').length
  const totalTasks = mission.tasks.length

  const movableTasks = isActive
    ? mission.tasks.filter(t => t.status === 'pending' || t.status === 'traveling')
    : []
  const manualPriorityIds: string[] = mission.manualPriorityIds ?? []

  return (
    <g onClick={onClick} style={{ cursor: isDone ? 'default' : 'pointer' }}>
      {selected && (
        <circle cx={cx} cy={cy} r={r + 6} fill="none" stroke="white" strokeWidth={1} strokeOpacity={0.4} strokeDasharray="4,4" />
      )}
      <circle
        cx={cx} cy={cy} r={r}
        fill={ZONE_FILL[mission.status]}
        stroke={isAllocating ? '#3b82f6' : ZONE_STROKE[mission.status]}
        strokeWidth={isAllocating ? 2 : selected ? 2 : 1.2}
        strokeDasharray={mission.status === 'queued' ? '5,4' : 'none'}
        strokeOpacity={isDone ? 0.4 : 0.9}
      />
      {mission.status === 'active' && totalTasks > 0 && (
        <ProgressArc cx={cx} cy={cy} r={r} fraction={completedTasks / totalTasks} />
      )}
      {mission.tasks.map(t => {
        const isMovable = movableTasks.some(m => m.id === t.id)
        const canReprioritise = isActive && isMovable && !!onReprioritiseTop
        // Badge only for explicitly clicked tasks (post-alloc) or selected tasks (pre-alloc)
        const postAllocIdx = isActive ? manualPriorityIds.indexOf(t.id) : -1
        return (
          <TaskWaypoint
            key={t.id}
            task={t}
            priorityIndex={isAllocating ? priorityTaskIds.indexOf(t.id) : postAllocIdx}
            onToggle={isAllocating ? () => onToggleTaskPriority?.(t.id) : undefined}
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
    </g>
  )
}

function ProgressArc({ cx, cy, r, fraction }: { cx: number; cy: number; r: number; fraction: number }) {
  if (fraction <= 0) return null
  const clipped = Math.min(1, fraction)
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

function TaskWaypoint({ task, priorityIndex = -1, onToggle, onReprioritiseTop }: {
  task: Task
  priorityIndex?: number   // -1 = not in allocation; ≥0 = priority position (0-based)
  onToggle?: () => void         // during allocation: toggle priority
  onReprioritiseTop?: () => void // post-allocation: bump pending task to front
}) {
  const { x, y } = task.waypoint
  const isExecuting = task.status === 'executing'
  const color = TASK_DOT_COLOR[task.status]
  const canPrioritise = !!onToggle
  const canReprioritise = !!onReprioritiseTop
  const isClickable = canPrioritise || canReprioritise
  const isPriority = priorityIndex >= 0

  // Put onClick and onPointerDown on individual elements so SVG pointer-capture
  // (set by handlePointerDown on the root SVG) cannot steal the click.
  function handleClick(e: React.MouseEvent) {
    e.stopPropagation()
    if (canPrioritise) onToggle!()
    else if (canReprioritise) onReprioritiseTop!()
  }

  function handlePointerDown(e: React.PointerEvent) {
    // Stop propagation so the root SVG never calls setPointerCapture for this hit.
    e.stopPropagation()
  }

  const interactProps = isClickable
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
      {/* Transparent hit-area — carries the click/pointerdown handlers */}
      {isClickable && (
        <circle cx={x} cy={y} r={10} fill="transparent" {...interactProps} />
      )}
      {/* Dashed ring: clickable during allocation, not yet in priority queue */}
      {canPrioritise && !isPriority && (
        <circle cx={x} cy={y} r={7} fill="none" stroke="white"
          strokeWidth={0.8} strokeOpacity={0.28} strokeDasharray="2,3" {...interactProps} />
      )}
      {/* Solid amber ring: priority position (both during allocation and post-allocation) */}
      {isPriority && (
        <circle cx={x} cy={y} r={7} fill="none" stroke="#fbbf24"
          strokeWidth={1.3} strokeOpacity={0.9} {...interactProps} />
      )}
      <circle cx={x} cy={y} r={4} fill={color} {...interactProps} />
      <text x={x} y={y - 7} textAnchor="middle" fontSize={7} fill={color} fontFamily="monospace" {...interactProps}>
        {TASK_SHORT_MAP[task.type]}
      </text>
      {/* Priority number badge */}
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

  // Collect future task waypoints for this asset (sequential plan)
  const mission = missions.find(m => m.id === asset.currentMissionId)
  // Filter preserves mission.tasks array order, which reflects any reprioritisation.
  const futureTasks = mission
    ? mission.tasks.filter(t =>
        t.id !== asset.currentTaskId &&
        t.assignedAssetIds.includes(asset.id) &&
        t.status !== 'completed' && t.status !== 'failed',
      )
    : []

  // Build predicted path: targetPosition → future waypoints → hub (if returning after last task)
  const pathPoints: Array<{ x: number; y: number }> = [targetPosition, ...futureTasks.map(t => t.waypoint)]
  const showReturn = asset.status === 'deployed' && futureTasks.length === 0

  return (
    <g>
      {/* Current travel segment — dashed */}
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

      {/* Future task chain — thin solid line */}
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

      {/* Return-to-hub leg — dotted */}
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

  const fo = isReturning ? 0.5 : 0.95
  const stroke = isReturning ? 'none' : 'white'
  const sw = isReturning ? 0 : 0.8
  const label = useCallsigns ? (ASSET_CALLSIGNS[asset.id] ?? asset.id) : asset.id

  return (
    <g filter="url(#assetGlow)">
      <circle cx={x + 1} cy={y + 1} r={5} fill="black" fillOpacity={0.4} />
      {asset.type === 'Blue' && (
        <circle cx={x} cy={y} r={5} fill={color} fillOpacity={fo}
          stroke={stroke} strokeWidth={sw} strokeOpacity={0.6} />
      )}
      {asset.type === 'Red' && (
        <polygon points={`${x},${y-5.5} ${x+5.5},${y} ${x},${y+5.5} ${x-5.5},${y}`}
          fill={color} fillOpacity={fo} stroke={stroke} strokeWidth={sw} strokeOpacity={0.6} />
      )}
      {asset.type === 'Green' && (
        <polygon points={`${x},${y-5.5} ${x+5},${y+4.5} ${x-5},${y+4.5}`}
          fill={color} fillOpacity={fo} stroke={stroke} strokeWidth={sw} strokeOpacity={0.6} />
      )}
      <AssetDirectionPip asset={asset} color={color} />
      <text x={x + 8} y={y + 3} fontSize={8} fill={color} fillOpacity={0.85} fontFamily="monospace">
        {label}
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
    pending: 'Pending', traveling: 'En route', executing: 'Executing',
    completed: 'Complete', failed: 'Failed',
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
                  className="px-1 h-5 rounded flex items-center justify-center text-white font-bold"
                  style={{ background: TASK_DOT_COLOR[task.status] + '99', fontSize: '9px', minWidth: '22px' }}
                >
                  {TASK_SHORT_MAP[task.type]}
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

export type { MapViewState }
