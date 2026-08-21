import { useState } from 'react'
import type { GameState } from '../types'
import type { GameAction } from '../store/actions'

interface Props {
  state: GameState
  dispatch: (a: GameAction) => void
}

// ─── Question schema ────────────────────────────────────────────────────────

// 'info' is a non-input framing paragraph (still occupies a QUESTIONS slot for section-grouping,
// but isAnswered() always treats it as answered — nothing to submit).
type QuestionType = 'number' | 'text' | 'choice' | 'scale' | 'info'

interface Question {
  id: string
  label: string
  help?: string
  type: QuestionType
  section: string
  options?: string[]   // for 'choice'
  min?: number         // for 'number' and 'scale'
  max?: number         // for 'number' and 'scale'
  minLabel?: string    // for 'scale'
  maxLabel?: string    // for 'scale'
}

const FREQUENCY = ['Never', 'Rarely', 'Occasionally', 'Weekly', 'Daily']
const EXPERIENCE = ['None', 'A little', 'Moderate', 'Extensive']
const AGREEMENT = ['Strongly disagree', 'Disagree', 'Neutral', 'Agree', 'Strongly agree']

const SECTION_ABOUT = 'About you'
const SECTION_AIAS = 'Your views on AI'
const SECTION_VERIFICATION = 'Working with AI tools'
const SECTION_DELEGATION = 'AI and decision-making'
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

  // ── Block A — AIAS-4 (Grassini, 2023; validated, verbatim, unidimensional) ──
  // 10-point scale, 1 = Not at all, 10 = Completely agree. Score as mean or sum, no reverse items.
  // Framing paragraph replicates the original administration (a short neutral overview of what
  // "AI" covers) so scores stay comparable to published norms, and doubles as neutral framing that
  // doesn't cue the study's Strategic/Tactical Assistant manipulation.
  {
    id: 'aias_overview', section: SECTION_AIAS, type: 'info',
    label: 'For the next few questions, "AI" refers to artificial intelligence in general — things '
      + 'like virtual assistants (e.g. Siri, Alexa), recommendation algorithms (e.g. what streaming '
      + 'or shopping sites suggest to you), grammar and writing checkers, and chatbots (e.g. ChatGPT).',
  },
  {
    id: 'aias_improve_life', section: SECTION_AIAS, label: 'I believe that AI will improve my life.',
    type: 'scale', min: 1, max: 10, minLabel: 'Not at all', maxLabel: 'Completely agree',
  },
  {
    id: 'aias_improve_work', section: SECTION_AIAS, label: 'I believe that AI will improve my work.',
    type: 'scale', min: 1, max: 10, minLabel: 'Not at all', maxLabel: 'Completely agree',
  },
  {
    id: 'aias_future_use', section: SECTION_AIAS, label: 'I think I will use AI technology in the future.',
    type: 'scale', min: 1, max: 10, minLabel: 'Not at all', maxLabel: 'Completely agree',
  },
  {
    id: 'aias_positive_humanity', section: SECTION_AIAS, label: 'I think AI technology is positive for humanity.',
    type: 'scale', min: 1, max: 10, minLabel: 'Not at all', maxLabel: 'Completely agree',
  },

  // ── Block B — Verification propensity (bespoke) ──
  // 7-point scale, 1 = Strongly disagree, 7 = Strongly agree. Items marked (R) are reverse-keyed
  // (3 of 6, so straight-lining reads as mid-scale rather than a clean sceptic profile) — reverse-
  // score at analysis time, responses are logged raw. `verif_hard_to_detect_errors` is kept out of
  // the composite (it measures perceived error-detectability, not propensity to check) — useful as
  // a moderator.
  {
    id: 'verif_check_before_relying', section: SECTION_VERIFICATION,
    label: "I usually check an AI tool's work before relying on it.",
    type: 'scale', min: 1, max: 7, minLabel: 'Strongly disagree', maxLabel: 'Strongly agree',
  },
  {
    id: 'verif_comfortable_unreviewed', section: SECTION_VERIFICATION,
    label: "I would be comfortable using an AI tool's output without reviewing it.",
    type: 'scale', min: 1, max: 7, minLabel: 'Strongly disagree', maxLabel: 'Strongly agree',
  },
  {
    id: 'verif_want_reasoning', section: SECTION_VERIFICATION,
    label: 'When an AI tool gives me an answer, I want to see the reasoning behind it.',
    type: 'scale', min: 1, max: 7, minLabel: 'Strongly disagree', maxLabel: 'Strongly agree',
  },
  {
    id: 'verif_happy_unsupervised', section: SECTION_VERIFICATION,
    label: 'I am happy to let AI tools work on their own without my involvement.',
    type: 'scale', min: 1, max: 7, minLabel: 'Strongly disagree', maxLabel: 'Strongly agree',
  },
  {
    id: 'verif_overconfident', section: SECTION_VERIFICATION,
    label: 'AI tools tend to be more confident in their answers than they should be.',
    type: 'scale', min: 1, max: 7, minLabel: 'Strongly disagree', maxLabel: 'Strongly agree',
  },
  {
    id: 'verif_reliable_no_check', section: SECTION_VERIFICATION,
    label: 'Most AI tools are reliable enough that checking their work is unnecessary.',
    type: 'scale', min: 1, max: 7, minLabel: 'Strongly disagree', maxLabel: 'Strongly agree',
  },
  {
    id: 'verif_hard_to_detect_errors', section: SECTION_VERIFICATION,
    label: 'I find it difficult to tell when an AI tool has made a mistake.',
    help: 'Optional moderator item — kept separate from the verification-propensity score above.',
    type: 'scale', min: 1, max: 7, minLabel: 'Strongly disagree', maxLabel: 'Strongly agree',
  },

  // ── Block C — Delegation boundary and human authority (bespoke) ──
  // 7-point scale. Item 5 is reverse-keyed (R). Items 1-2 map onto the Strategic (recommend) vs.
  // Tactical (decide) Assistant contrast; items 4-5 are the domain-matched pair on high-stakes use.
  {
    id: 'deleg_human_final_say', section: SECTION_DELEGATION,
    label: 'A human should make the final decision even when an AI recommendation is available.',
    type: 'scale', min: 1, max: 7, minLabel: 'Strongly disagree', maxLabel: 'Strongly agree',
  },
  {
    id: 'deleg_trust_suggest_over_decide', section: SECTION_DELEGATION,
    label: 'I trust AI more for suggesting options than for making decisions.',
    type: 'scale', min: 1, max: 7, minLabel: 'Strongly disagree', maxLabel: 'Strongly agree',
  },
  {
    id: 'deleg_prefer_self_even_if_slower', section: SECTION_DELEGATION,
    label: 'I would rather do a task myself than delegate it to an AI, even if it took me longer.',
    type: 'scale', min: 1, max: 7, minLabel: 'Strongly disagree', maxLabel: 'Strongly agree',
  },
  {
    id: 'deleg_not_when_lives_at_stake', section: SECTION_DELEGATION,
    label: 'AI should not be relied on in situations where lives are at stake.',
    type: 'scale', min: 1, max: 7, minLabel: 'Strongly disagree', maxLabel: 'Strongly agree',
  },
  {
    id: 'deleg_urgent_better_than_nothing', section: SECTION_DELEGATION,
    label: 'In an urgent situation, an AI recommendation is better than no recommendation at all.',
    type: 'scale', min: 1, max: 7, minLabel: 'Strongly disagree', maxLabel: 'Strongly agree',
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
    if (q.type === 'info') return true
    const v = responses[q.id]
    if (q.type === 'number' || q.type === 'scale') return typeof v === 'number' && !Number.isNaN(v)
    return v !== undefined && v !== ''
  }

  const allAnswered = QUESTIONS.every(isAnswered)
  const canSubmit = relaxed || allAnswered

  function submit() {
    if (!canSubmit) return
    dispatch({ type: 'SUBMIT_DEMOGRAPHICS', responses })
  }

  return (
    <div className="min-h-full bg-gray-950 flex items-center justify-center p-6">
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
              {q.type === 'info' ? (
                <p className="text-xs text-gray-400 leading-relaxed bg-gray-800/50 border border-gray-700 rounded-lg px-3 py-2.5">
                  {q.label}
                </p>
              ) : (
                <>
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

                  {q.type === 'scale' && (
                    <div className="space-y-1.5">
                      <div className="flex gap-1">
                        {Array.from({ length: q.max! - q.min! + 1 }, (_, k) => q.min! + k).map(v => (
                          <button
                            key={v}
                            onClick={() => setResponse(q.id, v)}
                            className={`flex-1 py-2.5 rounded text-xs font-semibold transition-colors border ${
                              responses[q.id] === v
                                ? 'bg-blue-600 border-blue-500 text-white'
                                : 'bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-500 hover:text-gray-200'
                            }`}
                          >
                            {v}
                          </button>
                        ))}
                      </div>
                      <div className="flex justify-between text-xs text-gray-600 px-0.5">
                        <span>{q.minLabel}</span>
                        <span>{q.maxLabel}</span>
                      </div>
                    </div>
                  )}
                </>
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
