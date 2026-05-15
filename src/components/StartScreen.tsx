import { useState } from 'react'
import type { Mode, StudyConfig } from '../types'
import { randomSeed } from '../utils/config'

const COMPLEXITIES = [
  { value: 'standard'  as const, label: 'Standard',      desc: '18/9/3 drones · balanced mix' },
  { value: 'surge'     as const, label: 'Fleet Surge',   desc: '24/12/4 drones · lighter missions' },
  { value: 'precision' as const, label: 'Precision Ops', desc: '12/6/2 drones · heavy missions' },
  { value: 'campaign'  as const, label: 'Campaign',      desc: '24/12/4 drones · heavy+volume' },
]

const MODES = [
  { value: 'no-agent' as const, label: 'Manual Control', desc: 'All allocations made by operator' },
  { value: 'agent'    as const, label: 'Agent Assist',   desc: 'Agent suggests strategic & tactical options' },
]

interface Props { onStart: (config: StudyConfig) => void }

export default function StartScreen({ onStart }: Props) {
  const [participantId, setParticipantId] = useState('')
  const [complexity, setComplexity] = useState<StudyConfig['complexity']>('standard')
  const [mode, setMode] = useState<Mode>('no-agent')
  const [seed, setSeed] = useState(String(randomSeed()))
  const [error, setError] = useState('')

  function handleStart() {
    const seedNum = parseInt(seed, 10)
    if (isNaN(seedNum) || seedNum < 1) { setError('Seed must be a positive integer.'); return }
    const finalId = participantId.trim() || `P-${String(randomSeed() % 9000 + 1000)}`
    setError('')
    onStart({ participantId: finalId, mode, complexity, seed: seedNum, agentErrorRate: 0.20 })
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-6">
      <div className="w-full max-w-lg bg-gray-900 rounded-2xl border border-gray-700 shadow-2xl p-8 space-y-6">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold text-white tracking-tight">SAR Command Platform</h1>
          <p className="text-sm text-gray-400">Search &amp; Rescue — Human Factors Study</p>
        </div>
        <hr className="border-gray-700" />

        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-gray-300">
            Participant ID <span className="ml-2 text-xs text-gray-500 font-normal">leave blank to auto-assign</span>
          </label>
          <input type="text" value={participantId} onChange={e => setParticipantId(e.target.value)}
            placeholder="e.g. P001 (optional)"
            className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
        </div>

        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-gray-300">Mode</label>
          <div className="grid grid-cols-2 gap-2">
            {MODES.map(m => (
              <button key={m.value} onClick={() => setMode(m.value)}
                className={`text-left px-3 py-2 rounded-lg border text-sm transition-colors ${mode === m.value ? 'bg-blue-600 border-blue-500 text-white' : 'bg-gray-800 border-gray-600 text-gray-300 hover:border-gray-400'}`}>
                <span className="font-medium">{m.label}</span>
                <span className="block text-xs mt-0.5 text-gray-400">{m.desc}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-gray-300">Complexity</label>
          <div className="grid grid-cols-2 gap-2">
            {COMPLEXITIES.map(cx => (
              <button key={cx.value} onClick={() => setComplexity(cx.value)}
                className={`text-left px-3 py-2 rounded-lg border text-sm transition-colors ${complexity === cx.value ? 'bg-blue-600 border-blue-500 text-white' : 'bg-gray-800 border-gray-600 text-gray-300 hover:border-gray-400'}`}>
                <span className="font-medium">{cx.label}</span>
                <span className="block text-xs mt-0.5 text-gray-400">{cx.desc}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-gray-300">
            Session Seed <span className="ml-2 text-xs text-gray-500 font-normal">determines all randomness</span>
          </label>
          <div className="flex gap-2">
            <input type="number" value={seed} onChange={e => setSeed(e.target.value)}
              className="flex-1 bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500" />
            <button onClick={() => setSeed(String(randomSeed()))}
              className="px-3 py-2 bg-gray-700 hover:bg-gray-600 border border-gray-600 rounded-lg text-sm text-gray-300 transition-colors">
              Randomise
            </button>
          </div>
        </div>

        {error && <p className="text-sm text-red-400">{error}</p>}

        <button onClick={handleStart}
          className="w-full py-3 bg-blue-600 hover:bg-blue-500 rounded-lg text-white font-semibold text-sm transition-colors">
          Start Study
        </button>
      </div>
    </div>
  )
}
