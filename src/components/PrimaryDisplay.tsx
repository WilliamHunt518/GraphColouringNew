import type { GameState, Mission, Task, AssetType, MissionCategory, Posture, AssetChip } from '../types'
import type { GameAction } from '../store/actions'
import { reserveCount } from '../store/gameReducer'
import CopilotModal from './CopilotModal'
import TrustProbeModal from './TrustProbeModal'

interface Props {
  state: GameState
  dispatch: (a: GameAction) => void
}

// ─── Colour helpers ───────────────────────────────────────────────────────

const CAT_BADGE: Record<MissionCategory, string> = {
  A: 'bg-gray-700 text-gray-200',
  B: 'bg-blue-900/80 text-blue-200',
  C: 'bg-amber-900/80 text-amber-200',
  D: 'bg-orange-900/80 text-orange-200',
  E: 'bg-red-900/80 text-red-200',
}

const TASK_STATUS_STYLE: Record<Task['status'], string> = {
  pending:   'bg-gray-700 text-gray-400',
  traveling: 'bg-blue-800 text-blue-100 animate-pulse',
  executing: 'bg-amber-700 text-amber-100 animate-pulse',
  completed: 'bg-green-800 text-green-100',
  failed:    'bg-red-900 text-red-300',
}

const TASK_LABEL: Record<number, string> = { 1: 'T1', 2: 'T2', 3: 'T3', 4: 'T4', 5: 'T5' }

const POSTURE_COLOR: Record<Posture, string> = {
  Aggressive:   'bg-red-700 text-white',
  Conservative: 'bg-blue-700 text-white',
  Hold:         'bg-gray-600 text-white',
}

const CHIP_COLOR: Record<AssetChip, string> = {
  'commit freely':    'bg-green-900/60 text-green-300 border-green-700',
  'commit cautiously':'bg-amber-900/60 text-amber-300 border-amber-700',
  'hold':             'bg-red-900/60 text-red-300 border-red-700',
}

const ASSET_BAR_COLOR: Record<AssetType, string> = {
  Blue:  'bg-blue-500',
  Red:   'bg-red-500',
  Green: 'bg-green-500',
}

const ASSET_TOTAL: Record<AssetType, number> = { Blue: 18, Red: 9, Green: 3 }

// ─── Top-level ────────────────────────────────────────────────────────────

export default function PrimaryDisplay({ state, dispatch }: Props) {
  const queued  = state.missions.filter(m => m.status === 'queued')
  const active  = state.missions.filter(m => m.status === 'active')
  const done    = state.missions.filter(m => m.status === 'completed' || m.status === 'failed')
  const reserve = reserveCount(state.assets)

  return (
    <div className="h-screen flex flex-col bg-gray-950 text-white overflow-hidden">
      {/* Header */}
      <header className="flex items-center justify-between px-5 py-2.5 bg-gray-900 border-b border-gray-800 flex-none">
        <div className="flex items-center gap-4">
          <span className="font-bold text-white">SAR Command</span>
          <span className="text-xs text-gray-400 uppercase tracking-wide">
            Session {state.sessionNumber} / 3
          </span>
        </div>
        <div className="flex items-center gap-6 text-sm">
          <span className="font-mono text-amber-400 font-bold">{formatCountdown(state.elapsed)}</span>
          <span className="text-gray-400">Score: <span className="text-white font-bold">{state.score}</span></span>
          <span className="text-gray-600 text-xs">
            {state.pendingBlueprints.length} upcoming
          </span>
          <button
            onClick={() => window.open('/?view=map', '_blank', 'noopener')}
            className="text-xs px-2.5 py-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700 transition-colors"
          >
            Open Map
          </button>
        </div>
      </header>

      {/* Body */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: mission queue */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2 min-w-0">
          {/* Incoming missions (queued, not yet allocated) */}
          {queued.length > 0 && (
            <section>
              <SectionLabel text="Incoming — awaiting allocation" dot="bg-amber-400" />
              {queued.map(m => (
                <MissionCard key={m.id} mission={m} state={state} dispatch={dispatch} />
              ))}
            </section>
          )}

          {/* Active missions */}
          {active.length > 0 && (
            <section className={queued.length > 0 ? 'mt-4' : ''}>
              <SectionLabel text="Active missions" dot="bg-blue-400" />
              {active.map(m => (
                <MissionCard key={m.id} mission={m} state={state} dispatch={dispatch} />
              ))}
            </section>
          )}

          {/* Completed / failed */}
          {done.length > 0 && (
            <section className="mt-4 opacity-60">
              <SectionLabel text="Completed" dot="bg-gray-500" />
              {done.slice(-6).map(m => (
                <MissionCard key={m.id} mission={m} state={state} dispatch={dispatch} />
              ))}
            </section>
          )}

          {queued.length === 0 && active.length === 0 && done.length === 0 && (
            <div className="flex flex-col items-center justify-center h-48 text-gray-600">
              <p className="text-sm">No missions yet</p>
              <p className="text-xs mt-1">Missions will appear here as they arrive</p>
            </div>
          )}
        </div>

        {/* Right: reserve + Meta-Co-Pilot */}
        <aside className="w-72 flex-none border-l border-gray-800 flex flex-col overflow-hidden">
          <div className="overflow-y-auto flex-1 p-4 space-y-4">
            <ReservePanel state={state} reserve={reserve} />
            <ForecastPanel state={state} />
            <MetaCopilotWidget state={state} dispatch={dispatch} />
          </div>
        </aside>
      </div>

      {/* Overlays */}
      {state.copilotModal && <CopilotModal state={state} dispatch={dispatch} />}
      {state.trustProbeActive && <TrustProbeModal state={state} dispatch={dispatch} />}
    </div>
  )
}

// ─── Section label ────────────────────────────────────────────────────────

function SectionLabel({ text, dot }: { text: string; dot: string }) {
  return (
    <div className="flex items-center gap-2 mb-2 px-1">
      <span className={`w-1.5 h-1.5 rounded-full ${dot} flex-none`} />
      <span className="text-xs text-gray-500 uppercase tracking-wider">{text}</span>
    </div>
  )
}

// ─── Mission card ─────────────────────────────────────────────────────────

function MissionCard({ mission, state, dispatch }: { mission: Mission; state: GameState; dispatch: (a: GameAction) => void }) {
  const isQueued    = mission.status === 'queued'
  const isActive    = mission.status === 'active'
  const isCompleted = mission.status === 'completed'
  const isFailed    = mission.status === 'failed'

  const completedTasks = mission.tasks.filter(t => t.status === 'completed').length
  const totalTasks = mission.tasks.length

  const borderColor = isQueued ? 'border-amber-700' : isActive ? 'border-blue-800' : 'border-gray-800'
  const bgColor = isQueued ? 'bg-amber-950/20' : isActive ? 'bg-blue-950/10' : 'bg-gray-900/40'

  // Expected completion = latest completionTime among all tasks
  const eta = isActive
    ? Math.max(0, Math.max(...mission.tasks.map(t => t.completionTime ?? 0)) - state.elapsed)
    : null

  return (
    <div className={`rounded-lg border ${borderColor} ${bgColor} p-3 mb-2`}>
      {/* Card header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-mono text-xs font-bold text-white">{mission.id}</span>
          <span className={`text-xs px-1.5 py-0.5 rounded font-bold ${CAT_BADGE[mission.category]}`}>
            {mission.category}
          </span>
          {isActive && (
            <span className="text-xs text-gray-400">{completedTasks}/{totalTasks}</span>
          )}
          {isCompleted && <span className="text-xs text-green-400">✓ complete</span>}
          {isFailed && <span className="text-xs text-red-400">✗ failed</span>}
        </div>

        <div className="flex items-center gap-2 flex-none">
          {isActive && eta !== null && (
            <span className="text-xs text-gray-400 font-mono">ETA {formatSeconds(eta)}</span>
          )}
          {isQueued && (
            <button
              onClick={() => dispatch({ type: 'OPEN_ALLOCATE', missionId: mission.id })}
              className="px-3 py-1 bg-amber-600 hover:bg-amber-500 rounded text-xs font-semibold text-white transition-colors"
            >
              Allocate
            </button>
          )}
        </div>
      </div>

      {/* Task strip */}
      <div className="flex flex-wrap gap-1">
        {mission.tasks.map(t => (
          <TaskBadge key={t.id} task={t} state={state} dispatch={dispatch} />
        ))}
      </div>
    </div>
  )
}

// ─── Task badge ───────────────────────────────────────────────────────────

function TaskBadge({ task, state, dispatch }: {
  task: Task
  state: GameState
  dispatch: (a: GameAction) => void
}) {
  const deployed = state.assets.filter(a => task.assignedAssetIds.includes(a.id) && a.status === 'deployed')

  return (
    <div className="relative group">
      <span
        className={`inline-flex items-center justify-center w-7 h-7 rounded text-xs font-bold cursor-default select-none ${TASK_STATUS_STYLE[task.status]}`}
        title={`Task ${task.type} — ${task.status}`}
      >
        {TASK_LABEL[task.type]}
      </span>

      {/* Recall button appears on hover for executing/traveling tasks */}
      {deployed.length > 0 && (task.status === 'executing' || task.status === 'traveling') && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:flex gap-1 flex-col z-10">
          {deployed.map(a => (
            <button
              key={a.id}
              onClick={() => dispatch({ type: 'RECALL_ASSET', assetId: a.id })}
              className="text-xs bg-red-700 hover:bg-red-600 text-white px-2 py-0.5 rounded whitespace-nowrap"
            >
              Recall {a.id}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Reserve panel ────────────────────────────────────────────────────────

function ReservePanel({ state, reserve }: { state: GameState; reserve: { Blue: number; Red: number; Green: number } }) {
  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-3 space-y-3">
      <p className="text-xs text-gray-500 uppercase tracking-wider">Reserve</p>
      {(['Blue', 'Red', 'Green'] as AssetType[]).map(type => {
        const total   = ASSET_TOTAL[type]
        const avail   = reserve[type]
        const deployed = state.assets.filter(a => a.type === type && a.status === 'deployed').length
        const returning = state.assets.filter(a => a.type === type && a.status === 'returning').length

        return (
          <div key={type} className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className={type === 'Blue' ? 'text-blue-400' : type === 'Red' ? 'text-red-400' : 'text-green-400'}>
                {type}
              </span>
              <span className="text-gray-400 font-mono">
                {avail} avail · {deployed} out · {returning} rtng
              </span>
            </div>
            <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden flex">
              <div
                className={`h-full ${ASSET_BAR_COLOR[type]} transition-all`}
                style={{ width: `${(avail / total) * 100}%` }}
              />
              <div
                className="h-full bg-gray-500 transition-all"
                style={{ width: `${(returning / total) * 100}%` }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ─── Forecast panel ───────────────────────────────────────────────────────

function ForecastPanel({ state }: { state: GameState }) {
  const f = state.categoryForecast
  const cats = ['A', 'B', 'C', 'D', 'E'] as MissionCategory[]
  const next = state.pendingBlueprints[0]

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-3 space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-500 uppercase tracking-wider">Next mission forecast</p>
        {next && (
          <span className="text-xs text-gray-600 font-mono">
            in {formatSeconds(Math.max(0, next.arrivalTime - state.elapsed))}
          </span>
        )}
      </div>
      <div className="flex gap-1 items-end h-12">
        {cats.map(c => (
          <div key={c} className="flex-1 flex flex-col items-center gap-0.5">
            <div
              className={`w-full rounded-t transition-all ${CAT_BADGE[c].split(' ')[0]}`}
              style={{ height: `${Math.round(f[c] * 100)}%`, minHeight: f[c] > 0 ? 2 : 0 }}
            />
            <span className="text-xs text-gray-500">{c}</span>
          </div>
        ))}
      </div>
      <div className="flex gap-1 items-center justify-end">
        {cats.filter(c => f[c] > 0.05).map(c => (
          <span key={c} className={`text-xs px-1 rounded ${CAT_BADGE[c]}`}>
            {c} {Math.round(f[c] * 100)}%
          </span>
        ))}
      </div>
    </div>
  )
}

// ─── Meta-Co-Pilot widget ─────────────────────────────────────────────────

function MetaCopilotWidget({ state, dispatch }: { state: GameState; dispatch: (a: GameAction) => void }) {
  const rec = state.metaRec
  const postures: Posture[] = ['Aggressive', 'Conservative', 'Hold']

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-3 space-y-3">
      <p className="text-xs text-gray-500 uppercase tracking-wider">Meta-Co-Pilot</p>

      {rec ? (
        <>
          {/* Recommended posture */}
          <div className={`rounded-lg px-3 py-2 text-sm font-bold ${POSTURE_COLOR[rec.posture]}`}>
            {rec.posture}
          </div>

          {/* Rationale */}
          <p className="text-xs text-gray-400 leading-snug">{rec.rationale}</p>

          {/* Asset chips */}
          <div className="space-y-1.5">
            {(['Blue', 'Red', 'Green'] as AssetType[]).map(t => (
              <div key={t} className="flex items-center justify-between">
                <span className={`text-xs ${t === 'Blue' ? 'text-blue-400' : t === 'Red' ? 'text-red-400' : 'text-green-400'}`}>
                  {t}
                </span>
                <span className={`text-xs px-2 py-0.5 rounded border font-medium ${CHIP_COLOR[rec.chips[t]]}`}>
                  {rec.chips[t]}
                </span>
              </div>
            ))}
          </div>

          {/* Posture override buttons */}
          <div className="flex gap-1 pt-1">
            {postures.map(p => (
              <button
                key={p}
                onClick={() => dispatch({ type: 'SET_META_POSTURE', posture: p })}
                className={`flex-1 py-1 rounded text-xs font-medium transition-colors ${
                  (state.metaPostureOverride ?? rec.posture) === p
                    ? POSTURE_COLOR[p]
                    : 'bg-gray-800 text-gray-400 hover:text-gray-200'
                }`}
              >
                {p.slice(0, 4)}
              </button>
            ))}
          </div>
        </>
      ) : (
        <p className="text-xs text-gray-600 py-2">Waiting for first analysis…</p>
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
