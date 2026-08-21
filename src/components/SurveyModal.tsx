import { useState } from 'react'
import type { GameState } from '../types'
import type { GameAction } from '../store/actions'

interface Props {
  state: GameState
  dispatch: (a: GameAction) => void
}

// ─── Survey definitions ────────────────────────────────────────────────────

interface NASAItem { id: string; question: string; leftLabel: string; rightLabel: string }
interface LikertItem { id: string; question: string }
type SurveyType = 'nasa' | 'likert'

interface SurveyDef {
  name: string
  title: string
  subtitle: string
  type: SurveyType
  items: NASAItem[] | LikertItem[]
}

const NASA_ITEMS: NASAItem[] = [
  { id: 'mental_demand',   question: 'How mentally demanding was the task?',                                           leftLabel: 'Low',     rightLabel: 'High'    },
  { id: 'physical_demand', question: 'How physically demanding was the task?',                                         leftLabel: 'Low',     rightLabel: 'High'    },
  { id: 'temporal_demand', question: 'How hurried or rushed was the pace of the task?',                                leftLabel: 'Low',     rightLabel: 'High'    },
  { id: 'performance',     question: 'How successful were you in accomplishing what you were asked to do?',            leftLabel: 'Perfect', rightLabel: 'Failure' },
  { id: 'effort',          question: 'How hard did you have to work to accomplish your level of performance?',         leftLabel: 'Low',     rightLabel: 'High'    },
  { id: 'frustration',     question: 'How insecure, discouraged, irritated, stressed, or annoyed were you?',          leftLabel: 'Low',     rightLabel: 'High'    },
]

const TRUST_STRAT: LikertItem[] = [
  { id: 'strat_reliable',       question: 'The Strategic Assistant is reliable.' },
  { id: 'strat_trust',          question: "I trust the Strategic Assistant's recommendations." },
  { id: 'strat_performs',       question: 'The Strategic Assistant performs well.' },
  { id: 'strat_confident',      question: 'I feel confident using the Strategic Assistant.' },
  { id: 'strat_useful',         question: 'The Strategic Assistant provides useful guidance.' },
  { id: 'strat_follow',         question: "I would follow the Strategic Assistant's suggestions without hesitation." },
]

const TRUST_TACT: LikertItem[] = [
  { id: 'tact_reliable',      question: 'The Tactical Assistant is reliable.' },
  { id: 'tact_trust',         question: "I trust the Tactical Assistant's recommendations." },
  { id: 'tact_performs',      question: 'The Tactical Assistant performs well.' },
  { id: 'tact_confident',     question: 'I feel confident using the Tactical Assistant.' },
  { id: 'tact_useful',        question: 'The Tactical Assistant provides useful guidance.' },
  { id: 'tact_follow',        question: "I would follow the Tactical Assistant's suggestions without hesitation." },
]

const TAM_STRAT: LikertItem[] = [
  { id: 'strat_tam_perf',       question: 'Using the Strategic Assistant improves my task performance.' },
  { id: 'strat_tam_useful',     question: 'Using the Strategic Assistant is useful for this task.' },
  { id: 'strat_tam_easy_learn', question: 'Learning to use the Strategic Assistant was easy.' },
  { id: 'strat_tam_easy_use',   question: 'I find the Strategic Assistant easy to use overall.' },
]

const TAM_TACT: LikertItem[] = [
  { id: 'tact_tam_perf',      question: 'Using the Tactical Assistant improves my task performance.' },
  { id: 'tact_tam_useful',    question: 'Using the Tactical Assistant is useful for this task.' },
  { id: 'tact_tam_easy_learn', question: 'Learning to use the Tactical Assistant was easy.' },
  { id: 'tact_tam_easy_use',  question: 'I find the Tactical Assistant easy to use overall.' },
]

const SURVEY_DEFS: Record<string, SurveyDef> = {
  nasa_tlx: {
    name: 'nasa_tlx',
    title: 'Workload Assessment',
    subtitle: 'NASA Task Load Index — rate the session you just completed (0 = low, 20 = high)',
    type: 'nasa',
    items: NASA_ITEMS,
  },
  trust_strategic: {
    name: 'trust_strategic',
    title: 'Trust in Strategic Assistant',
    subtitle: 'Rate your agreement with each statement (1 = strongly disagree, 7 = strongly agree)',
    type: 'likert',
    items: TRUST_STRAT,
  },
  trust_tactical: {
    name: 'trust_tactical',
    title: 'Trust in Tactical Assistant',
    subtitle: 'Rate your agreement with each statement (1 = strongly disagree, 7 = strongly agree)',
    type: 'likert',
    items: TRUST_TACT,
  },
  tam_strategic: {
    name: 'tam_strategic',
    title: 'Strategic Assistant — Usability',
    subtitle: 'Rate your agreement with each statement (1 = strongly disagree, 7 = strongly agree)',
    type: 'likert',
    items: TAM_STRAT,
  },
  tam_tactical: {
    name: 'tam_tactical',
    title: 'Tactical Assistant — Usability',
    subtitle: 'Rate your agreement with each statement (1 = strongly disagree, 7 = strongly agree)',
    type: 'likert',
    items: TAM_TACT,
  },
}

// Sessions 1 & 2: NASA-TLX + trust scales; session 3: add TAM scales
const SURVEYS_BY_SESSION: Record<number, string[]> = {
  1: ['nasa_tlx', 'trust_strategic', 'trust_tactical'],
  2: ['nasa_tlx', 'trust_strategic', 'trust_tactical'],
  3: ['nasa_tlx', 'trust_strategic', 'trust_tactical', 'tam_strategic', 'tam_tactical'],
}

function initResponses(def: SurveyDef): Record<string, number> {
  if (def.type === 'nasa') {
    const r: Record<string, number> = {}
    ;(def.items as NASAItem[]).forEach(item => { r[item.id] = 10 })
    return r
  }
  return {}
}

// ─── Top-level component ───────────────────────────────────────────────────

export default function SurveyModal({ state, dispatch }: Props) {
  const surveyNames = SURVEYS_BY_SESSION[state.sessionNumber] ?? SURVEYS_BY_SESSION[1]
  const [pageIndex, setPageIndex] = useState(0)
  const [responses, setResponses] = useState<Record<string, number>>(
    () => initResponses(SURVEY_DEFS[surveyNames[0]]),
  )

  const currentName = surveyNames[pageIndex]
  const currentDef = SURVEY_DEFS[currentName]
  const isLast = pageIndex === surveyNames.length - 1
  // Last page of THIS session's surveys is not the end of the study unless this is also the last
  // session — participants were being told "Finish study" after session 1 of 2 and then handed
  // session 2.
  const isFinalSession = state.sessionNumber >= state.config.numSessions

  const allAnswered = currentDef.items.every(item => responses[item.id] !== undefined)

  function setResponse(id: string, value: number) {
    setResponses(r => ({ ...r, [id]: value }))
  }

  function advance() {
    dispatch({ type: 'SUBMIT_SURVEY', surveyName: currentName, responses })
    if (isLast) {
      dispatch({ type: 'FINISH_SURVEYS' })
    } else {
      const nextIdx = pageIndex + 1
      setPageIndex(nextIdx)
      setResponses(initResponses(SURVEY_DEFS[surveyNames[nextIdx]]))
    }
  }

  return (
    <div className="min-h-full bg-gray-950 flex items-center justify-center p-6">
      <div className="w-full max-w-2xl bg-gray-900 rounded-2xl border border-gray-700 shadow-2xl overflow-hidden flex flex-col">

        {/* Header */}
        <div className="px-8 py-5 border-b border-gray-800 flex items-start justify-between gap-4">
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-widest mb-1">
              Session {state.sessionNumber} survey — {pageIndex + 1} / {surveyNames.length}
            </p>
            <h2 className="text-lg font-bold text-white">{currentDef.title}</h2>
            <p className="text-xs text-gray-400 mt-0.5">{currentDef.subtitle}</p>
          </div>
          <div className="flex gap-1.5 shrink-0 mt-1">
            {surveyNames.map((_, i) => (
              <div
                key={i}
                className={`w-2 h-2 rounded-full transition-colors ${
                  i < pageIndex ? 'bg-blue-500' : i === pageIndex ? 'bg-white' : 'bg-gray-700'
                }`}
              />
            ))}
          </div>
        </div>

        {/* Questions */}
        <div className="px-8 py-6 space-y-7 overflow-y-auto max-h-[65vh]">
          {currentDef.type === 'nasa'
            ? (currentDef.items as NASAItem[]).map(item => (
                <NASASlider
                  key={item.id}
                  item={item}
                  value={responses[item.id] ?? 10}
                  onChange={v => setResponse(item.id, v)}
                />
              ))
            : (currentDef.items as LikertItem[]).map(item => (
                <LikertRow
                  key={item.id}
                  item={item}
                  value={responses[item.id] ?? null}
                  onChange={v => setResponse(item.id, v)}
                />
              ))
          }
        </div>

        {/* Footer */}
        <div className="px-8 py-4 border-t border-gray-800 flex items-center justify-between">
          <span className="text-xs text-gray-600">
            {allAnswered ? 'All questions answered' : 'Please answer all questions to continue'}
          </span>
          <button
            onClick={advance}
            disabled={!allAnswered}
            className="px-6 py-2.5 rounded-lg font-semibold text-sm transition-colors bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white"
          >
            {isLast ? (isFinalSession ? 'Finish study' : 'Continue →') : 'Next →'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── NASA-TLX slider ──────────────────────────────────────────────────────

function NASASlider({
  item, value, onChange,
}: {
  item: NASAItem
  value: number
  onChange: (v: number) => void
}) {
  return (
    <div className="space-y-2">
      <p className="text-sm text-gray-200">{item.question}</p>
      <div className="flex items-center gap-3">
        <span className="text-xs text-gray-500 w-14 text-right shrink-0">{item.leftLabel}</span>
        <input
          type="range"
          min={0}
          max={20}
          value={value}
          onChange={e => onChange(Number(e.target.value))}
          className="flex-1 accent-blue-500 h-2 cursor-pointer"
        />
        <span className="text-xs text-gray-500 w-14 shrink-0">{item.rightLabel}</span>
        <span className="font-mono text-white text-sm w-6 text-right shrink-0 tabular-nums">{value}</span>
      </div>
    </div>
  )
}

// ─── 7-point Likert row ───────────────────────────────────────────────────

function LikertRow({
  item, value, onChange,
}: {
  item: LikertItem
  value: number | null
  onChange: (v: number) => void
}) {
  return (
    <div className="space-y-2">
      <p className="text-sm text-gray-200">{item.question}</p>
      <div className="flex gap-1">
        {([1, 2, 3, 4, 5, 6, 7] as const).map(v => (
          <button
            key={v}
            onClick={() => onChange(v)}
            className={`flex-1 py-2.5 rounded text-xs font-semibold transition-colors border ${
              value === v
                ? 'bg-blue-600 border-blue-500 text-white'
                : 'bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-500 hover:text-gray-200'
            }`}
          >
            {v}
          </button>
        ))}
      </div>
      <div className="flex justify-between text-xs text-gray-600 px-0.5">
        <span>Strongly disagree</span>
        <span>Strongly agree</span>
      </div>
    </div>
  )
}
