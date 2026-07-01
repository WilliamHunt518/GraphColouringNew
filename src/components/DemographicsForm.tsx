import { useState } from 'react'
import type { GameState } from '../types'
import type { GameAction } from '../store/actions'

interface Props {
  state: GameState
  dispatch: (a: GameAction) => void
}

// ─── Question schema ────────────────────────────────────────────────────────

type QuestionType = 'number' | 'text' | 'choice'

interface Question {
  id: string
  label: string
  help?: string
  type: QuestionType
  section: string
  options?: string[]   // for 'choice'
  min?: number         // for 'number'
  max?: number
}

const FREQUENCY = ['Never', 'Rarely', 'Occasionally', 'Weekly', 'Daily']
const EXPERIENCE = ['None', 'A little', 'Moderate', 'Extensive']
const AGREEMENT = ['Strongly disagree', 'Disagree', 'Neutral', 'Agree', 'Strongly agree']

const SECTION_ABOUT = 'About you'
const SECTION_UNDERSTANDING = 'Before you start'

const QUESTIONS: Question[] = [
  { id: 'age', section: SECTION_ABOUT, label: 'Age', type: 'number', min: 18, max: 100 },
  {
    id: 'gender', section: SECTION_ABOUT, label: 'Gender', type: 'choice',
    options: ['Male', 'Female', 'Non-binary', 'Prefer not to say', 'Other'],
  },
  {
    id: 'education', section: SECTION_ABOUT, label: 'Highest level of education completed', type: 'choice',
    options: ['Secondary / high school', 'Undergraduate degree', 'Postgraduate / master’s', 'Doctorate', 'Other'],
  },
  {
    id: 'field', section: SECTION_ABOUT, label: 'Field of study or occupation', type: 'text',
    help: 'e.g. Computer Science, Nursing, Logistics',
  },
  {
    id: 'gaming_frequency', section: SECTION_ABOUT, label: 'How often do you play video games (any kind)?', type: 'choice',
    options: FREQUENCY,
  },
  {
    id: 'sim_experience', section: SECTION_ABOUT,
    label: 'Experience with simulation software or simulation games',
    help: 'e.g. flight / driving simulators, city-builders, management sims',
    type: 'choice', options: EXPERIENCE,
  },
  {
    id: 'strategy_experience', section: SECTION_ABOUT,
    label: 'Experience with real-time strategy or resource-management games',
    help: 'e.g. StarCraft, Age of Empires, Factorio, Command & Conquer',
    type: 'choice', options: EXPERIENCE,
  },
  {
    id: 'drone_experience', section: SECTION_ABOUT,
    label: 'Experience operating drones or UAVs',
    type: 'choice', options: EXPERIENCE,
  },
  {
    id: 'autonomy_experience', section: SECTION_ABOUT,
    label: 'Experience working with automation, AI assistants, or autonomous systems',
    type: 'choice', options: EXPERIENCE,
  },
  {
    id: 'command_experience', section: SECTION_ABOUT,
    label: 'Experience with emergency management, dispatch, air traffic control, or military command',
    type: 'choice', options: EXPERIENCE,
  },

  // ── Comprehension check ──
  {
    id: 'understand_role', section: SECTION_UNDERSTANDING,
    label: 'I understand my role as the operator in this operation.',
    type: 'choice', options: AGREEMENT,
  },
  {
    id: 'understand_missions', section: SECTION_UNDERSTANDING,
    label: 'I understand how to allocate drones to a mission.',
    type: 'choice', options: AGREEMENT,
  },
  {
    id: 'understand_strategic', section: SECTION_UNDERSTANDING,
    label: 'I understand what the Strategic Assistant is for.',
    type: 'choice', options: AGREEMENT,
  },
  {
    id: 'understand_tactical', section: SECTION_UNDERSTANDING,
    label: 'I understand what the Tactical Assistant is for.',
    type: 'choice', options: AGREEMENT,
  },
  {
    id: 'understand_scoring', section: SECTION_UNDERSTANDING,
    label: 'I understand how my performance is measured.',
    type: 'choice', options: AGREEMENT,
  },
]

// ─── Component ───────────────────────────────────────────────────────────────

export default function DemographicsForm({ state, dispatch }: Props) {
  const relaxed = state.config.fastTest ?? false
  const [responses, setResponses] = useState<Record<string, string | number>>({})

  function setResponse(id: string, value: string | number) {
    setResponses(r => ({ ...r, [id]: value }))
  }

  function isAnswered(q: Question): boolean {
    const v = responses[q.id]
    if (q.type === 'number') return typeof v === 'number' && !Number.isNaN(v)
    return v !== undefined && v !== ''
  }

  const allAnswered = QUESTIONS.every(isAnswered)
  const canSubmit = relaxed || allAnswered

  function submit() {
    if (!canSubmit) return
    dispatch({ type: 'SUBMIT_DEMOGRAPHICS', responses })
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-6">
      <div className="w-full max-w-2xl bg-gray-900 rounded-2xl border border-gray-700 shadow-2xl overflow-hidden flex flex-col">

        {/* Header */}
        <div className="px-8 py-5 border-b border-gray-800">
          <p className="text-xs text-gray-500 uppercase tracking-widest mb-1">Before we begin</p>
          <h2 className="text-lg font-bold text-white">Background questionnaire</h2>
          <p className="text-xs text-gray-400 mt-0.5">
            These questions are about you and your prior experience. There are no right or wrong answers.
          </p>
          {relaxed && (
            <p className="text-xs text-orange-400 mt-2 font-semibold">
              Fast-test mode — validation relaxed; you can submit without answering.
            </p>
          )}
        </div>

        {/* Questions */}
        <div className="px-8 py-6 space-y-7 overflow-y-auto max-h-[70vh]">
          {QUESTIONS.map((q, i) => (
            <div key={q.id} className="space-y-2">
              {(i === 0 || QUESTIONS[i - 1].section !== q.section) && (
                <p className="text-xs font-semibold uppercase tracking-widest text-blue-400 pt-2 first:pt-0">
                  {q.section}
                </p>
              )}
              <p className="text-sm text-gray-200">{q.label}</p>
              {q.help && <p className="text-xs text-gray-500 -mt-1">{q.help}</p>}

              {q.type === 'text' && (
                <input
                  type="text"
                  value={(responses[q.id] as string) ?? ''}
                  onChange={e => setResponse(q.id, e.target.value)}
                  className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              )}

              {q.type === 'number' && (
                <input
                  type="number"
                  min={q.min}
                  max={q.max}
                  value={responses[q.id] === undefined ? '' : String(responses[q.id])}
                  onChange={e => setResponse(q.id, e.target.value === '' ? '' : Number(e.target.value))}
                  className="w-32 bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              )}

              {q.type === 'choice' && (
                <div className="flex flex-wrap gap-1.5">
                  {q.options!.map(opt => (
                    <button
                      key={opt}
                      onClick={() => setResponse(q.id, opt)}
                      className={`px-3 py-2 rounded text-xs font-semibold transition-colors border ${
                        responses[q.id] === opt
                          ? 'bg-blue-600 border-blue-500 text-white'
                          : 'bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-500 hover:text-gray-200'
                      }`}
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="px-8 py-4 border-t border-gray-800 flex items-center justify-between">
          <span className="text-xs text-gray-600">
            {canSubmit ? 'Ready to continue' : 'Please answer all questions to continue'}
          </span>
          <button
            onClick={submit}
            disabled={!canSubmit}
            className="px-6 py-2.5 rounded-lg font-semibold text-sm transition-colors bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white"
          >
            Begin session 1 →
          </button>
        </div>
      </div>
    </div>
  )
}
