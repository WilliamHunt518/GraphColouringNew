import { useState } from 'react'
import type { GameState, Strategy, AssetRequirement, AssetType } from '../types'
import type { GameAction } from '../store/actions'
import { reserveCount } from '../store/gameReducer'

interface Props {
  state: GameState
  dispatch: (a: GameAction) => void
}

const ASSET_COLORS: Record<AssetType, string> = {
  Blue: 'text-blue-400',
  Red: 'text-red-400',
  Green: 'text-green-400',
}

function fmtTime(seconds: number) {
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}m ${s.toString().padStart(2, '0')}s`
}

export default function CopilotModal({ state, dispatch }: Props) {
  const modal = state.copilotModal!
  const mission = state.missions.find(m => m.id === modal.missionId)!
  const reserve = reserveCount(state.assets)
  const [manualMode, setManualMode] = useState(false)
  const [manualAlloc, setManualAlloc] = useState<AssetRequirement>({ Blue: 0, Red: 0, Green: 0 })

  const selectedStrat = modal.selectedIndex !== null ? modal.strategies[modal.selectedIndex] : null
  const editedAlloc = modal.editedAllocation
  // Allocation to apply: edited > selected strategy > manual
  const toApply: AssetRequirement = manualMode
    ? manualAlloc
    : editedAlloc ?? selectedStrat?.assets ?? { Blue: 0, Red: 0, Green: 0 }

  const isFeasible = (a: AssetRequirement) =>
    a.Blue <= reserve.Blue && a.Red <= reserve.Red && a.Green <= reserve.Green
  const canApply = manualMode
    ? (toApply.Blue + toApply.Red + toApply.Green > 0) && isFeasible(toApply)
    : selectedStrat != null && isFeasible(toApply)

  function applySource(): 'copilot_as_proposed' | 'copilot_modified' | 'manual' {
    if (manualMode) return 'manual'
    if (editedAlloc) return 'copilot_modified'
    return 'copilot_as_proposed'
  }

  function handleApply() {
    if (!canApply) return
    dispatch({
      type: 'APPLY_ALLOCATION',
      missionId: modal.missionId,
      allocation: toApply,
      source: applySource(),
      strategies: modal.strategies,
      selectedIndex: modal.selectedIndex,
    })
  }

  function handleDismiss() {
    dispatch({ type: 'DISMISS_COPILOT', missionId: modal.missionId })
  }

  const catColors: Record<string, string> = {
    A: 'bg-gray-700 text-gray-200',
    B: 'bg-blue-900 text-blue-200',
    C: 'bg-amber-900 text-amber-200',
    D: 'bg-orange-900 text-orange-200',
    E: 'bg-red-900 text-red-200',
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/70 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl w-full max-w-4xl flex flex-col max-h-[90vh]">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700 flex-none">
          <div className="flex items-center gap-3">
            <span className="text-lg font-bold text-white">Co-Pilot</span>
            <span className="text-gray-400">—</span>
            <span className="text-gray-300 font-mono">{mission.id}</span>
            <span className={`text-xs px-2 py-0.5 rounded font-bold ${catColors[mission.category]}`}>
              Cat {mission.category}
            </span>
            <span className="text-xs text-gray-500">{mission.tasks.length} tasks</span>
          </div>
          <button onClick={handleDismiss} className="text-gray-500 hover:text-gray-200 text-xl leading-none">×</button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-700 flex-none">
          <button
            onClick={() => setManualMode(false)}
            className={`px-6 py-2.5 text-sm font-medium transition-colors ${!manualMode ? 'text-white border-b-2 border-blue-500' : 'text-gray-400 hover:text-gray-200'}`}
          >
            Co-Pilot Strategies
          </button>
          <button
            onClick={() => setManualMode(true)}
            className={`px-6 py-2.5 text-sm font-medium transition-colors ${manualMode ? 'text-white border-b-2 border-blue-500' : 'text-gray-400 hover:text-gray-200'}`}
          >
            Manual Allocation
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          {!manualMode ? (
            <StrategyCards
              strategies={modal.strategies}
              selectedIndex={modal.selectedIndex}
              editedAlloc={editedAlloc}
              reserve={reserve}
              onSelect={i => dispatch({ type: 'SELECT_STRATEGY', strategyIndex: i })}
              onEdit={a => dispatch({ type: 'EDIT_ALLOCATION', allocation: a })}
            />
          ) : (
            <ManualAllocation
              reserve={reserve}
              allocation={manualAlloc}
              onChange={setManualAlloc}
            />
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-700 flex-none bg-gray-950 rounded-b-2xl">
          <div className="text-sm text-gray-400">
            {canApply && !manualMode && selectedStrat && (
              <span>
                Applying <span className="text-white font-medium">{selectedStrat.name}</span>
                {' — '}
                <AssetSummary a={toApply} />
              </span>
            )}
            {canApply && manualMode && (
              <span>Manual: <AssetSummary a={toApply} /></span>
            )}
            {!canApply && !manualMode && (
              <span className="text-gray-600">Select a strategy to continue</span>
            )}
          </div>
          <div className="flex gap-3">
            <button onClick={handleDismiss} className="px-4 py-2 text-sm text-gray-400 hover:text-gray-200 transition-colors">
              Dismiss
            </button>
            <button
              onClick={handleApply}
              disabled={!canApply}
              className="px-5 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg text-sm font-semibold text-white transition-colors"
            >
              Apply Allocation
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Strategy cards ───────────────────────────────────────────────────────

function StrategyCards({
  strategies, selectedIndex, editedAlloc, reserve, onSelect, onEdit,
}: {
  strategies: Strategy[]
  selectedIndex: number | null
  editedAlloc: AssetRequirement | null
  reserve: AssetRequirement
  onSelect: (i: number) => void
  onEdit: (a: AssetRequirement) => void
}) {
  const [editingIndex, setEditingIndex] = useState<number | null>(null)

  if (strategies.length === 0) {
    return (
      <div className="text-center py-10 text-gray-500">
        No feasible strategies available with current reserve. Use Manual Allocation.
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {strategies.map((s, i) => {
        const selected = selectedIndex === i
        const editing = editingIndex === i && selected
        return (
          <div
            key={s.name}
            onClick={() => { onSelect(i); setEditingIndex(null) }}
            className={`rounded-xl border-2 p-4 cursor-pointer transition-all space-y-3 ${
              selected
                ? 'border-blue-500 bg-blue-950/40'
                : 'border-gray-700 bg-gray-800 hover:border-gray-500'
            }`}
          >
            <div>
              <div className="flex items-center gap-2 mb-1">
                {selected && <span className="text-blue-400 text-xs">✓</span>}
                <span className="font-bold text-white text-sm">{s.name}</span>
              </div>
              <p className="text-xs text-gray-400 leading-snug">{s.description}</p>
            </div>

            <div className="text-center">
              <span className="text-2xl font-mono font-bold text-white">{fmtTime(s.expectedCompletionTime)}</span>
              <p className="text-xs text-gray-500">expected completion</p>
            </div>

            <div className="space-y-1 text-xs">
              <p className="text-gray-500 uppercase tracking-wider">Assets needed</p>
              {(['Blue', 'Red', 'Green'] as AssetType[]).map(t => s.assets[t] > 0 && (
                <div key={t} className="flex justify-between">
                  <span className={ASSET_COLORS[t]}>{t}</span>
                  <span className="text-white font-mono">{s.assets[t]}</span>
                </div>
              ))}
            </div>

            <div className="space-y-1 text-xs">
              <p className="text-gray-500 uppercase tracking-wider">Reserve after</p>
              {(['Blue', 'Red', 'Green'] as AssetType[]).map(t => (
                <div key={t} className="flex justify-between">
                  <span className={ASSET_COLORS[t]}>{t}</span>
                  <span className={`font-mono ${s.reserveAfter[t] === 0 ? 'text-red-400' : 'text-gray-300'}`}>
                    {s.reserveAfter[t]}
                  </span>
                </div>
              ))}
            </div>

            {/* Speed vs reserve bars */}
            <div className="space-y-1.5 text-xs">
              <ScoreBar label="Speed" value={s.speedScore} color="bg-blue-500" />
              <ScoreBar label="Reserve" value={s.reserveScore} color="bg-green-500" />
            </div>

            {/* Edit allocation toggle */}
            {selected && (
              <button
                onClick={e => { e.stopPropagation(); setEditingIndex(editing ? null : i) }}
                className="w-full text-xs text-blue-400 hover:text-blue-200 py-1 border border-blue-700 rounded-lg transition-colors"
              >
                {editing ? 'Cancel edit' : 'Modify assets'}
              </button>
            )}

            {/* Inline asset editor */}
            {editing && (
              <div
                onClick={e => e.stopPropagation()}
                className="space-y-2 border-t border-gray-700 pt-3"
              >
                {(['Blue', 'Red', 'Green'] as AssetType[]).map(t => (
                  <AssetStepper
                    key={t}
                    type={t}
                    value={(editedAlloc ?? s.assets)[t]}
                    max={reserve[t]}
                    onChange={v => onEdit({ ...(editedAlloc ?? s.assets), [t]: v })}
                  />
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function ScoreBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-gray-500 w-12">{label}</span>
      <div className="flex-1 bg-gray-700 rounded-full h-1.5">
        <div className={`${color} h-1.5 rounded-full`} style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      <span className="text-gray-400 w-7 text-right">{Math.round(value * 100)}%</span>
    </div>
  )
}

// ─── Manual allocation ────────────────────────────────────────────────────

function ManualAllocation({
  reserve, allocation, onChange,
}: {
  reserve: AssetRequirement
  allocation: AssetRequirement
  onChange: (a: AssetRequirement) => void
}) {
  return (
    <div className="max-w-xs mx-auto space-y-4">
      <p className="text-sm text-gray-400 text-center mb-6">
        Directly specify how many of each asset type to commit to this mission.
      </p>
      {(['Blue', 'Red', 'Green'] as AssetType[]).map(t => (
        <AssetStepper
          key={t}
          type={t}
          value={allocation[t]}
          max={reserve[t]}
          onChange={v => onChange({ ...allocation, [t]: v })}
        />
      ))}
    </div>
  )
}

// ─── Shared sub-components ────────────────────────────────────────────────

function AssetStepper({
  type, value, max, onChange,
}: {
  type: AssetType
  value: number
  max: number
  onChange: (v: number) => void
}) {
  return (
    <div className="flex items-center gap-3">
      <span className={`w-16 text-sm font-medium ${ASSET_COLORS[type]}`}>{type}</span>
      <button
        onClick={() => onChange(Math.max(0, value - 1))}
        className="w-7 h-7 rounded bg-gray-700 hover:bg-gray-600 text-white font-bold text-sm flex items-center justify-center"
      >−</button>
      <span className="w-6 text-center font-mono text-white font-bold">{value}</span>
      <button
        onClick={() => onChange(Math.min(max, value + 1))}
        className="w-7 h-7 rounded bg-gray-700 hover:bg-gray-600 text-white font-bold text-sm flex items-center justify-center"
      >+</button>
      <span className="text-xs text-gray-500">/ {max} available</span>
    </div>
  )
}

function AssetSummary({ a }: { a: AssetRequirement }) {
  const parts: string[] = []
  if (a.Blue > 0) parts.push(`B:${a.Blue}`)
  if (a.Red > 0) parts.push(`R:${a.Red}`)
  if (a.Green > 0) parts.push(`G:${a.Green}`)
  return <span className="font-mono text-gray-200">{parts.join(' ')}</span>
}
