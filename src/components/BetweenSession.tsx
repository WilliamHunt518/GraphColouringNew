import { useState, useEffect } from 'react'
import type { GameState } from '../types'
import type { GameAction } from '../store/actions'

const WAIT_SECONDS = 30

interface Props {
  state: GameState
  dispatch: (a: GameAction) => void
}

export default function BetweenSession({ state, dispatch }: Props) {
  const [countdown, setCountdown] = useState(state.config.fastTest ? 3 : WAIT_SECONDS)

  useEffect(() => {
    if (countdown <= 0) return
    const id = setTimeout(() => setCountdown(c => c - 1), 1000)
    return () => clearTimeout(id)
  }, [countdown])

  // During the between phase, sessionNumber is still the session that just ended
  const completedSession = state.sessionNumber
  const nextSession = completedSession + 1
  const prevScore = state.completedSessionScores[completedSession - 1] ?? 0

  const hideScore = state.config.collectDemographics ?? false

  return (
    <div className="min-h-full bg-gray-950 flex items-center justify-center p-6">
      <div className="w-full max-w-md bg-gray-900 rounded-2xl border border-gray-700 p-8 space-y-6 text-center">
        {hideScore ? (
          <div>
            <p className="text-sm text-gray-400 uppercase tracking-widest mb-1">Session {completedSession} complete</p>
            <p className="text-sm text-gray-500 mt-1">Take a short break.</p>
          </div>
        ) : (
          <>
            <div>
              <p className="text-sm text-gray-400 uppercase tracking-widest mb-1">Session {completedSession} complete</p>
              <p className="text-4xl font-bold text-white">{prevScore}</p>
              <p className="text-sm text-gray-500 mt-1">points</p>
            </div>
            <hr className="border-gray-700" />
          </>
        )}

        <div className="space-y-1">
          <p className="text-gray-400 text-sm">Session {nextSession} starts in</p>
          <p className="text-5xl font-mono font-bold text-blue-400">{countdown}</p>
        </div>

        <button
          disabled={countdown > 0}
          onClick={() => dispatch({ type: 'NEXT_SESSION' })}
          className="w-full py-3 rounded-lg font-semibold text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed bg-blue-600 hover:bg-blue-500 disabled:hover:bg-blue-600 text-white"
        >
          {countdown > 0 ? `Continue in ${countdown}s…` : `Start Session ${nextSession}`}
        </button>
      </div>
    </div>
  )
}
