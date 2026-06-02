import { useState } from 'react'
import type { Mode, StudyConfig } from '../types'
import { randomSeed } from '../utils/config'

const COMPLEXITIES = [
  { value: 'balanced'  as const, label: 'Balanced',         desc: 'Med Strategic / Med Tactical · 10B 9R 8G' },
  { value: 'tactical'  as const, label: 'Tactical Heavy',   desc: 'Low Strategic / High Tactical · few large missions · 10B 9R 8G' },
  { value: 'strategic' as const, label: 'Strategic Heavy',  desc: 'High Strategic / Low Tactical · many small missions · 9B 8R 7G' },
  { value: 'full'      as const, label: 'Full Spectrum',    desc: 'High Strategic / High Tactical · frequent large missions · 12B 11R 10G' },
  { value: 'quick'     as const, label: 'Quick Test',       desc: 'Dev only · 5B 5R 5G' },
]

const MODES = [
  { value: 'no-agent' as const, label: 'Manual Control', desc: 'All allocations made by operator' },
  { value: 'agent'    as const, label: 'Agent Assist',   desc: 'Agent suggests strategic & tactical options' },
]

const EPSILON_STEP = 0.05
const EPSILON_MIN  = 0.00  // 100% accuracy
const EPSILON_MAX  = 0.95  // 5% accuracy

function epsilonToAccuracy(eps: number): number {
  return Math.round((1 - eps) * 100)
}

function AccuracySpinner({ label, epsilon, onChange }: {
  label: string
  epsilon: number
  onChange: (v: number) => void
}) {
  const accuracy = epsilonToAccuracy(epsilon)
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 space-y-2">
      <span className="block text-xs font-medium text-gray-400">{label}</span>
      <div className="flex items-center justify-between gap-2">
        <button
          onClick={() => onChange(parseFloat(Math.min(EPSILON_MAX, epsilon + EPSILON_STEP).toFixed(2)))}
          disabled={epsilon >= EPSILON_MAX}
          className="w-7 h-7 rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-30 text-white font-bold flex items-center justify-center"
        >−</button>
        <div className="text-center flex-1">
          <span className="text-white font-bold text-xl font-mono tabular-nums">{accuracy}%</span>
          <span className="block text-xs text-gray-500 font-mono">ε = {epsilon.toFixed(2)}</span>
        </div>
        <button
          onClick={() => onChange(parseFloat(Math.max(EPSILON_MIN, epsilon - EPSILON_STEP).toFixed(2)))}
          disabled={epsilon <= EPSILON_MIN}
          className="w-7 h-7 rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-30 text-white font-bold flex items-center justify-center"
        >+</button>
      </div>
    </div>
  )
}

interface Props { onStart: (config: StudyConfig) => void }

export default function StartScreen({ onStart }: Props) {
  const [participantId, setParticipantId] = useState('')
  const [complexity, setComplexity] = useState<StudyConfig['complexity']>('balanced')
  const [mode, setMode] = useState<Mode>('agent')
  const [epsilonStrategic, setEpsilonStrategic] = useState(0.0)
  const [epsilonTactical, setEpsilonTactical]   = useState(0.0)
  const [tacticalMode, setTacticalMode] = useState<StudyConfig['tacticalMode']>('plan-all')
  const [seed, setSeed] = useState(String(randomSeed()))
  const [numSessions, setNumSessions] = useState(1)
  const [testingMode, setTestingMode] = useState(false)
  const [error, setError] = useState('')

  function handleStart() {
    const seedNum = parseInt(seed, 10)
    if (isNaN(seedNum) || seedNum < 1) { setError('Seed must be a positive integer.'); return }
    const finalId = participantId.trim() || `P-${String(randomSeed() % 9000 + 1000)}`
    setError('')
    onStart({
      participantId: finalId,
      condition: 'none',
      mode,
      complexity,
      seed: seedNum,
      agentErrorRate: mode === 'agent' ? epsilonStrategic : 0,
      epsilonTactical: mode === 'agent' ? epsilonTactical : 0,
      tacticalMode: mode === 'agent' ? tacticalMode : 'plan-all',
      testingMode,
      tutorialMode: false,
      numSessions,
    })
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

        {mode === 'agent' && (
          <div className="space-y-3">
            <div className="space-y-1.5">
              <label className="block text-sm font-medium text-gray-300">
                Agent Accuracy
                <span className="ml-2 text-xs text-gray-500 font-normal">how often each agent's suggestion is correct</span>
              </label>
              <div className="grid grid-cols-2 gap-3">
                <AccuracySpinner label="Strategic Agent" epsilon={epsilonStrategic} onChange={setEpsilonStrategic} />
                <AccuracySpinner label="Tactical Agent"  epsilon={epsilonTactical}  onChange={setEpsilonTactical} />
              </div>
            </div>
            <div className="space-y-1.5">
              <label className="block text-sm font-medium text-gray-300">Tactical Agent Style</label>
              <div className="grid grid-cols-2 gap-2">
                {([
                  { value: 'plan-all' as const, label: 'Plan All', desc: 'Full sequence, confirm once' },
                  { value: 'greedy'   as const, label: 'Greedy',   desc: 'Next task only, auto-replans' },
                ] as const).map(opt => (
                  <button key={opt.value} onClick={() => setTacticalMode(opt.value)}
                    className={`text-left px-3 py-2 rounded-lg border text-sm transition-colors ${tacticalMode === opt.value ? 'bg-blue-600 border-blue-500 text-white' : 'bg-gray-800 border-gray-600 text-gray-300 hover:border-gray-400'}`}>
                    <span className="font-medium">{opt.label}</span>
                    <span className="block text-xs mt-0.5 text-gray-400">{opt.desc}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

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

        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-gray-300">Sessions</label>
          <div className="flex gap-2">
            {[1, 2, 3].map(n => (
              <button key={n} onClick={() => setNumSessions(n)}
                className={`flex-1 py-2 rounded-lg border text-sm font-medium transition-colors ${numSessions === n ? 'bg-blue-600 border-blue-500 text-white' : 'bg-gray-800 border-gray-600 text-gray-300 hover:border-gray-400'}`}>
                {n} {n === 1 ? 'session' : 'sessions'}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-3">
          <input id="testing-mode" type="checkbox" checked={testingMode}
            onChange={e => setTestingMode(e.target.checked)}
            className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-orange-500 focus:ring-orange-500" />
          <label htmlFor="testing-mode" className="text-sm text-gray-400 cursor-pointer select-none">
            Testing mode <span className="text-gray-600 text-xs">(infinite time, manual mission/failure triggers)</span>
          </label>
        </div>

        {error && <p className="text-sm text-red-400">{error}</p>}

        <button onClick={handleStart}
          className="w-full py-3 bg-blue-600 hover:bg-blue-500 rounded-lg text-white font-semibold text-sm transition-colors">
          Start Study
        </button>

        <div className="relative">
          <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 border-t border-gray-800" />
          <span className="relative block text-center text-xs text-gray-600 bg-gray-900 px-3 w-fit mx-auto">or</span>
        </div>

        <button
          onClick={() => onStart({
            participantId: 'DEMO',
            condition: 'none',
            mode: 'agent',
            complexity: 'balanced',
            seed: 77777,
            agentErrorRate: 0.10,
            epsilonTactical: 0.10,
            tacticalMode: 'plan-all',
            testingMode: true,
            tutorialMode: true,
            numSessions: 1,
          })}
          className="w-full py-3 bg-indigo-700 hover:bg-indigo-600 rounded-lg text-white font-semibold text-sm transition-colors"
        >
          Run Tutorial
        </button>
        <p className="text-center text-xs text-gray-600">
          Guided walkthrough of every interface element — no configuration needed.
        </p>

        <button
          onClick={() => window.open('/?view=map', 'sar-tactical')}
          className="w-full py-2.5 bg-gray-800 hover:bg-gray-700 border border-gray-600 rounded-lg text-gray-300 font-medium text-sm transition-colors"
        >
          Open Tactical Planner →
        </button>
        <p className="text-center text-xs text-gray-600">
          Open the map window on a second screen before starting.
        </p>
      </div>
    </div>
  )
}
