import { useState } from 'react'
import type { GameState } from '../types'
import type { GameAction } from '../store/actions'

interface Props {
  state: GameState
  dispatch: (a: GameAction) => void
}

export default function TrustProbeModal({ dispatch }: Props) {
  const [trust, setTrust] = useState(5)
  const [workload, setWorkload] = useState(5)

  function submit() {
    dispatch({ type: 'SUBMIT_TRUST_PROBE', trust, workload })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-80 space-y-5 shadow-2xl">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-white">Quick check-in</h3>
          <button
            onClick={() => dispatch({ type: 'DISMISS_TRUST_PROBE' })}
            className="text-gray-500 hover:text-gray-300 text-sm"
          >
            Skip
          </button>
        </div>

        <Slider label="Trust in AI assistants" value={trust} onChange={setTrust} />
        <Slider label="Workload right now" value={workload} onChange={setWorkload} />

        <button
          onClick={submit}
          className="w-full py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium text-white transition-colors"
        >
          Submit
        </button>
      </div>
    </div>
  )
}

function Slider({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-sm">
        <span className="text-gray-300">{label}</span>
        <span className="font-mono text-white font-bold">{value}</span>
      </div>
      <input
        type="range"
        min={1}
        max={10}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="w-full accent-blue-500"
      />
      <div className="flex justify-between text-xs text-gray-500">
        <span>1 — Low</span>
        <span>10 — High</span>
      </div>
    </div>
  )
}
