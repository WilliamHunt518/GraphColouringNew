import TutorialText from './TutorialText'

interface Props {
  /** Called when the operator dismisses the summary (ends the tutorial). */
  onFinish: () => void
}

interface Recap {
  title: string
  body: string
}

const RECAP: Recap[] = [
  {
    title: 'Missions & your reserve',
    body: 'Distress calls arrive in the mission queue. You respond by committing drones from your reserve of {blue}, {red}, and {green} assets — each type has different speeds and capabilities.',
  },
  {
    title: 'Strategic allocation — how many to send',
    body: 'When you start a mission the Strategic Agent offers an Aggressive and a Conservative strategy: bundles of drone counts with projected ETA, speed, and reserve scores. Pick one, or set the counts yourself.',
  },
  {
    title: 'Tactical planning — which drone does what',
    body: 'Once allocated, the Tactical Agent fills in a drone→task plan in the map planner. Accept it as-is, or drag any drone to a different task to override individual assignments.',
  },
  {
    title: 'Failures & recovery',
    body: 'Drones can fail mid-mission. Reassign a spare to recover, or abort if the mission can no longer be completed — keeping some redundancy makes recovery easier.',
  },
  {
    title: 'Scoring',
    body: 'Complete tasks quickly to keep your penalty low, and watch your reserve so you can respond to the next call.',
  },
]

export default function TutorialSummary({ onFinish }: Props) {
  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-6 overflow-y-auto">
      <div className="bg-gray-900 rounded-2xl border border-gray-700 p-8 max-w-2xl w-full space-y-6 my-6">
        <div className="text-center">
          <p className="text-xs text-indigo-400 uppercase tracking-widest mb-2">Tutorial complete</p>
          <h2 className="text-2xl font-bold text-white">A quick recap</h2>
          <p className="text-gray-400 text-sm mt-1">Here are the key things you've learned so far.</p>
        </div>

        <div className="space-y-3">
          {RECAP.map(r => (
            <div key={r.title} className="bg-gray-800/60 rounded-xl border border-gray-700/60 p-4">
              <h3 className="text-sm font-semibold text-white mb-1">{r.title}</h3>
              <p className="text-sm text-gray-300 leading-relaxed">
                <TutorialText text={r.body} />
              </p>
            </div>
          ))}
        </div>

        {/* Key message — freedom to mix strategies */}
        <div className="bg-indigo-900/30 border border-indigo-700/50 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-indigo-200 mb-1">You're in control</h3>
          <p className="text-sm text-indigo-100/90 leading-relaxed">
            You are free to use any combination of strategies — automated and manual — exactly as you
            prefer. Accept an agent's suggestion, tweak it, or plan a mission entirely by hand. There is
            no single right approach: do whatever helps you respond most effectively.
          </p>
        </div>

        <button
          onClick={onFinish}
          className="w-full py-3 bg-indigo-600 hover:bg-indigo-500 rounded-lg font-semibold text-white text-sm transition-colors"
        >
          Finish
        </button>
      </div>
    </div>
  )
}
