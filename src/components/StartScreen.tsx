import { useState } from 'react'
import type { Condition, StudyConfig } from '../types'
import { conditionToEpsilons, randomSeed } from '../utils/config'

const CONDITIONS: { value: Condition; label: string; desc: string }[] = [
  { value: 'HH', label: 'HH', desc: 'High accuracy — both assistants' },
  { value: 'LH', label: 'LH', desc: 'Low Co-Pilot / High Meta-Co-Pilot' },
  { value: 'HL', label: 'HL', desc: 'High Co-Pilot / Low Meta-Co-Pilot' },
  { value: 'LL', label: 'LL', desc: 'Low accuracy — both assistants' },
]

const COMPLEXITIES: { value: StudyConfig['complexity']; label: string; desc: string }[] = [
  { value: 'easy',   label: 'Easy',   desc: 'λ=120s, mostly Tier A–B missions' },
  { value: 'medium', label: 'Medium', desc: 'λ=75s, mixed Tier A–D missions' },
  { value: 'hard',   label: 'Hard',   desc: 'λ=45s, Tier C–E heavy' },
]

interface Props {
  onStart: (config: StudyConfig) => void
}

export default function StartScreen({ onStart }: Props) {
  const [participantId, setParticipantId] = useState('')
  const [condition, setCondition] = useState<Condition>('HH')
  const [complexity, setComplexity] = useState<StudyConfig['complexity']>('medium')
  const [seed, setSeed] = useState(String(randomSeed()))
  const [error, setError] = useState('')

  function handleStart() {
    const trimmed = participantId.trim()
    if (!trimmed) { setError('Participant ID is required.'); return }
    const seedNum = parseInt(seed, 10)
    if (isNaN(seedNum) || seedNum < 1) { setError('Seed must be a positive integer.'); return }
    setError('')
    onStart({ participantId: trimmed, condition, complexity, seed: seedNum, ...conditionToEpsilons(condition) })
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-6">
      <div className="w-full max-w-lg bg-gray-900 rounded-2xl border border-gray-700 shadow-2xl p-8 space-y-6">
        {/* Header */}
        <div className="space-y-1">
          <h1 className="text-2xl font-bold text-white tracking-tight">SAR Command Platform</h1>
          <p className="text-sm text-gray-400">Search &amp; Rescue — Human Factors Study</p>
        </div>

        <hr className="border-gray-700" />

        {/* Participant ID */}
        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-gray-300">Participant ID</label>
          <input
            type="text"
            value={participantId}
            onChange={e => setParticipantId(e.target.value)}
            placeholder="e.g. P001"
            className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* Condition */}
        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-gray-300">Condition</label>
          <div className="grid grid-cols-2 gap-2">
            {CONDITIONS.map(c => (
              <button
                key={c.value}
                onClick={() => setCondition(c.value)}
                className={`text-left px-3 py-2 rounded-lg border text-sm transition-colors ${
                  condition === c.value
                    ? 'bg-blue-600 border-blue-500 text-white'
                    : 'bg-gray-800 border-gray-600 text-gray-300 hover:border-gray-400'
                }`}
              >
                <span className="font-mono font-bold">{c.label}</span>
                <span className="block text-xs mt-0.5 text-gray-400">{c.desc}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Complexity */}
        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-gray-300">Complexity</label>
          <div className="grid grid-cols-3 gap-2">
            {COMPLEXITIES.map(cx => (
              <button
                key={cx.value}
                onClick={() => setComplexity(cx.value)}
                className={`text-left px-3 py-2 rounded-lg border text-sm transition-colors ${
                  complexity === cx.value
                    ? 'bg-blue-600 border-blue-500 text-white'
                    : 'bg-gray-800 border-gray-600 text-gray-300 hover:border-gray-400'
                }`}
              >
                <span className="font-medium">{cx.label}</span>
                <span className="block text-xs mt-0.5 text-gray-400">{cx.desc}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Seed */}
        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-gray-300">
            Session Seed
            <span className="ml-2 text-xs text-gray-500 font-normal">determines all randomness</span>
          </label>
          <div className="flex gap-2">
            <input
              type="number"
              value={seed}
              onChange={e => setSeed(e.target.value)}
              className="flex-1 bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={() => setSeed(String(randomSeed()))}
              className="px-3 py-2 bg-gray-700 hover:bg-gray-600 border border-gray-600 rounded-lg text-sm text-gray-300 transition-colors"
            >
              Randomise
            </button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <p className="text-sm text-red-400">{error}</p>
        )}

        {/* Start */}
        <button
          onClick={handleStart}
          className="w-full py-3 bg-blue-600 hover:bg-blue-500 rounded-lg text-white font-semibold text-sm transition-colors"
        >
          Start Study
        </button>
      </div>
    </div>
  )
}
