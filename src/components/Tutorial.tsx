import { useEffect, useRef, useState, useCallback } from 'react'
import { createPortal } from 'react-dom'
import type { GameState } from '../types'
import type { GameAction } from '../store/actions'
import { TUTORIAL_STEPS, AGENT_INTRO_STEP, FAILURE_DEMO_STEP, ALLOCATION_OVERRIDE_STEP, ABORT_EXPLAIN_STEP } from '../utils/tutorialSteps'
import TutorialText from './TutorialText'

interface Props {
  state: GameState
  dispatch: (a: GameAction) => void
  step: number
  onStep: (s: number) => void
  onComplete: () => void
  /** Has the operator switched the allocation panel to manual mode? Latched in GameShell. */
  manualSelected: boolean
}

interface SpotRect { top: number; left: number; right: number; bottom: number }

const CARD_W   = 390
const CARD_H_EST = 290
const MARGIN   = 12
const GAP      = 16

function clamp(min: number, val: number, max: number) {
  return Math.max(min, Math.min(max, val))
}

function computeCardPos(spot: SpotRect | null, side: string, vw: number, vh: number, cardH: number) {
  const centeredTop  = clamp(MARGIN, (vh - cardH) / 2, vh - cardH - MARGIN)
  const centeredLeft = clamp(MARGIN, (vw - CARD_W)    / 2, vw - CARD_W    - MARGIN)
  if (side === 'center') return { top: centeredTop, left: centeredLeft }
  if (!spot) {
    // No spotlight — anchor card to the named screen edge
    if (side === 'right')  return { top: centeredTop, left: vw - CARD_W - MARGIN }
    if (side === 'left')   return { top: centeredTop, left: MARGIN }
    return { top: centeredTop, left: centeredLeft }
  }
  let top: number, left: number
  if (side === 'right') {
    left = spot.right + GAP; top = spot.top
    if (left + CARD_W > vw - MARGIN) left = spot.left - CARD_W - GAP
  } else if (side === 'left') {
    left = spot.left - CARD_W - GAP; top = spot.top
    if (left < MARGIN) left = spot.right + GAP
  } else if (side === 'bottom') {
    top = spot.bottom + GAP; left = spot.left
    if (top + cardH > vh - MARGIN) top = spot.top - cardH - GAP
  } else {
    top = spot.top - cardH - GAP; left = spot.left
    if (top < MARGIN) top = spot.bottom + GAP
  }
  return {
    top:  clamp(MARGIN, top,  vh - cardH - MARGIN),
    left: clamp(MARGIN, left, vw - CARD_W - MARGIN),
  }
}

export default function Tutorial({ state, dispatch, step, onStep, onComplete, manualSelected }: Props) {
  const [spot, setSpot] = useState<SpotRect | null>(null)
  // Measured card height. CARD_H_EST alone under-estimated the taller cards, so they were
  // positioned as if short and ran off the bottom of the viewport with Back/Skip unreachable.
  const [cardH, setCardH] = useState(CARD_H_EST)
  const cardRef = useRef<HTMLDivElement | null>(null)
  const [failureHoldExpired, setFailureHoldExpired] = useState(false)
  const autoFiredRef           = useRef(new Set<number>())
  const missionForcedRef       = useRef(false)
  const missionTwoForcedRef    = useRef(false)
  const overrideTeamFiredRef   = useRef(false)
  const failureDemoFiredRef    = useRef(false)
  const abandonScenarioFiredRef = useRef(false)
  const failureTryTimerRef     = useRef<ReturnType<typeof setTimeout> | null>(null)

  const current = TUTORIAL_STEPS[step]
  const isLast  = step === TUTORIAL_STEPS.length - 1

  // A mustInteract step whose action has become impossible (mission gone, recovery pool empty…)
  // is downgraded to a normal step so the operator always has a way forward.
  const stuck = !!current?.mustInteract && !!current.unsatisfiableWhen && current.unsatisfiableWhen(state)
  const gated = !!current?.mustInteract && !stuck

  const advanceStep = (from: number, dir: 1 | -1) => {
    let idx = from + dir
    // Going back, step over any mustInteract step whose action is ALREADY done (its
    // autoAdvanceWhen is satisfied). Landing on one showed a "do this now" card for something
    // that cannot be done again — e.g. "click Allocate" with the panel already open — and the
    // spotlight target no longer existed, which blanked the screen behind a blocking overlay.
    while (dir === -1 && idx > 0) {
      const s = TUTORIAL_STEPS[idx]
      if (!s?.mustInteract || !s.autoAdvanceWhen?.(state)) break
      idx -= 1
    }
    return Math.max(0, Math.min(TUTORIAL_STEPS.length - 1, idx))
  }

  // Spawn first demo mission at tutorial start
  useEffect(() => {
    if (missionForcedRef.current) return
    missionForcedRef.current = true
    if (state.pendingBlueprints.length > 0) {
      dispatch({ type: 'FORCE_MISSION_ARRIVAL' })
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Override the first mission's drone team when the tactical-pending step is entered
  useEffect(() => {
    if (overrideTeamFiredRef.current) return
    if (step !== ALLOCATION_OVERRIDE_STEP) return
    overrideTeamFiredRef.current = true
    dispatch({ type: 'TUTORIAL_OVERRIDE_TEAM' })
  }, [step, dispatch])

  // Dispatch TUTORIAL_FORCE_ABANDON_SCENARIO when the abort-explain step is entered
  useEffect(() => {
    if (abandonScenarioFiredRef.current) return
    if (step !== ABORT_EXPLAIN_STEP) return
    abandonScenarioFiredRef.current = true
    dispatch({ type: 'TUTORIAL_FORCE_ABANDON_SCENARIO' })
  }, [step, dispatch])

  // Spawn second mission when agent-intro phase begins
  useEffect(() => {
    if (missionTwoForcedRef.current) return
    if (step < AGENT_INTRO_STEP) return
    missionTwoForcedRef.current = true
    if (state.pendingBlueprints.length > 0) {
      dispatch({ type: 'FORCE_MISSION_ARRIVAL' })
    }
  }, [step, state.pendingBlueprints.length, dispatch])

  // Start the 5-second hold when the failure-demo step is first reached
  useEffect(() => {
    if (step < FAILURE_DEMO_STEP || failureHoldExpired) return
    const t = setTimeout(() => setFailureHoldExpired(true), 5000)
    return () => clearTimeout(t)
  }, [step, failureHoldExpired])

  // Force a drone failure after the hold expires
  useEffect(() => {
    if (!failureHoldExpired) return
    if (failureDemoFiredRef.current) return
    if (state.missions.some(m => m.failureRecoveryPending)) {
      failureDemoFiredRef.current = true
      return
    }
    // Any deployed drone with a task assignment is enough — reducer now accepts traveling drones too
    const hasDeployed = state.missions.some(
      m => m.status === 'active' && state.assets.some(
        a => a.currentMissionId === m.id && a.status === 'deployed' && a.currentTaskId
      )
    )
    if (hasDeployed) {
      failureDemoFiredRef.current = true
      // Not FORCE_DRONE_FAILURE: that picks the first executing drone, which may be the team's
      // only Red — stranding a supply drop and leaving the recovery lesson with nothing to do
      // but abandon. TUTORIAL_FORCE_FAILURE picks one the operator can actually recover from.
      dispatch({ type: 'TUTORIAL_FORCE_FAILURE' })
    } else if (!failureTryTimerRef.current) {
      // Drones may not have departed yet — retry in 1 s
      failureTryTimerRef.current = setTimeout(() => {
        failureTryTimerRef.current = null
        failureDemoFiredRef.current = false
      }, 1000)
    }
  }, [state, step, failureHoldExpired, dispatch])

  // Track highlighted element rect
  const refreshSpot = useCallback(() => {
    if (!current?.highlight || current.inMapWindow) { setSpot(null); return }
    const el = document.querySelector(`[data-tutorial="${current.highlight}"]`)
    if (!el) { setSpot(null); return }
    const r   = el.getBoundingClientRect()
    const pad = current.spotlightPadding ?? 8
    setSpot({
      top:    Math.max(0, r.top - pad),
      left:   Math.max(0, r.left - pad),
      right:  Math.min(window.innerWidth,  r.right  + pad),
      bottom: Math.min(window.innerHeight, r.bottom + pad),
    })
  }, [current?.highlight, current?.spotlightPadding, current?.inMapWindow])

  useEffect(() => {
    refreshSpot()
    const el = (current?.highlight && !current.inMapWindow)
      ? document.querySelector(`[data-tutorial="${current.highlight}"]`) : null
    const ro = new ResizeObserver(refreshSpot)
    if (el) ro.observe(el)
    window.addEventListener('resize', refreshSpot)
    // MutationObserver: re-check spotlight when DOM changes (e.g. dynamic panels appearing)
    const mo = new MutationObserver(refreshSpot)
    mo.observe(document.body, { childList: true, subtree: true })
    return () => { ro.disconnect(); mo.disconnect(); window.removeEventListener('resize', refreshSpot) }
  }, [refreshSpot])

  // Re-arm auto-advance whenever a step is (re-)entered. Without this the guard below was
  // permanent for the whole session: stepping Back onto an already-fired step left it unable to
  // advance again, with no Next button (mustInteract) — a dead end escapable only via Skip.
  const prevStepRef = useRef(step)
  useEffect(() => {
    if (prevStepRef.current === step) return
    prevStepRef.current = step
    autoFiredRef.current.delete(step)
  }, [step])

  // Auto-advance based on game state
  useEffect(() => {
    if (!current?.autoAdvanceWhen) return
    if (autoFiredRef.current.has(step)) return
    if (current.autoAdvanceWhen(state)) {
      autoFiredRef.current.add(step)
      setTimeout(() => onStep(advanceStep(step, 1)), current?.autoAdvanceDelay ?? 500)
    }
  }, [state, step, current, onStep])

  // Advance panel-intro once the panel is in manual mode. Reads GameShell's latched flag rather
  // than listening for the click itself: the click can land while 'allocate' is still the current
  // step (it auto-advances the moment the panel opens), and a missed event left the operator on
  // "click Set manually instead" with manual mode already on, the toggle gone, and no Next.
  useEffect(() => {
    if (current?.id !== 'panel-intro') return
    if (!manualSelected) return
    onStep(advanceStep(step, 1))
  }, [manualSelected, step, current, onStep])   // eslint-disable-line react-hooks/exhaustive-deps


  // Spacebar advances non-mustInteract steps
  useEffect(() => {
    if (current?.inMapWindow) return
    const handler = (e: KeyboardEvent) => {
      if (e.code !== 'Space') return
      if (gated) return
      // Don't fire when focus is inside an input/button (let normal behaviour run)
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      e.preventDefault()
      if (isLast) onComplete()
      else onStep(advanceStep(step, 1))
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [step, current, isLast, gated, onComplete, onStep])

  // Re-measure whenever the card content changes.
  useEffect(() => {
    const el = cardRef.current
    if (!el) return
    const measure = () => setCardH(el.offsetHeight)
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [step, current?.id])

  const vw = window.innerWidth
  const vh = window.innerHeight
  const pct = ((step + 1) / TUTORIAL_STEPS.length) * 100

  // When tutorial is active but the current step is in the tactical window,
  // grey out the primary window — unless noOverlayOnPrimary lets it stay visible.
  if (current?.inMapWindow) {
    if (current.noOverlayOnPrimary) return null
    return createPortal(
      <div style={{
        position: 'fixed', inset: 0, zIndex: 9000, pointerEvents: 'auto',
        background: 'rgba(2,6,23,0.88)',
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10,
      }}>
        <span style={{ fontSize: 10, color: '#818cf8', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.09em', fontFamily: 'inherit' }}>Tutorial</span>
        <span style={{ fontSize: 14, color: '#94a3b8', fontFamily: 'inherit' }}>See the Tactical Planner window →</span>
        <span style={{ fontSize: 11, color: '#475569', fontFamily: 'inherit' }}>{step + 1} / {TUTORIAL_STEPS.length}</span>
      </div>,
      document.body,
    )
  }

  const cardPos = computeCardPos(spot, current?.cardSide ?? 'center', vw, vh, cardH)

  // tryIt steps: dim only — whole interface stays interactive
  // mustInteract steps: only the spotlight is interactive (allowClickThrough handles opening it)
  // regular steps: everything blocked
  const isTryIt = !!(current?.tryIt && !current?.mustInteract)
  // A step that asks for a spotlight whose element isn't on screen would otherwise fall through to
  // a FULL-SCREEN blocking dim — the entire app becomes unclickable with nothing highlighted.
  // Never block in that case: dim for focus, but let every control through.
  const spotMissing = !!current?.highlight && !current.inMapWindow && !spot
  const dimOnly = (isTryIt || spotMissing) ? 'none' : 'auto'

  const portal = (
    <div style={{ position: 'fixed', inset: 0, zIndex: 9000, pointerEvents: 'none' }}>

      {/* Spotlight overlay — omitted entirely for noOverlay steps */}
      {!current?.noOverlay && (spot ? (
        <>
          <div style={{ position: 'fixed', top: 0, left: 0, right: 0, height: spot.top, background: 'rgba(2,6,23,0.80)', pointerEvents: dimOnly }} />
          <div style={{ position: 'fixed', top: spot.bottom, left: 0, right: 0, bottom: 0, background: 'rgba(2,6,23,0.80)', pointerEvents: dimOnly }} />
          <div style={{ position: 'fixed', top: spot.top, left: 0, width: spot.left, height: spot.bottom - spot.top, background: 'rgba(2,6,23,0.80)', pointerEvents: dimOnly }} />
          <div style={{ position: 'fixed', top: spot.top, left: spot.right, right: 0, height: spot.bottom - spot.top, background: 'rgba(2,6,23,0.80)', pointerEvents: dimOnly }} />
          {/* ring */}
          <div style={{
            position: 'fixed', top: spot.top, left: spot.left,
            width: spot.right - spot.left, height: spot.bottom - spot.top,
            border: '2px solid rgba(99,102,241,0.9)', borderRadius: 6,
            boxShadow: '0 0 0 1px rgba(99,102,241,0.2), 0 0 16px rgba(99,102,241,0.18)',
            pointerEvents: 'none',
          }} />
          {!current?.allowClickThrough && !isTryIt && (
            <div style={{ position: 'fixed', top: spot.top, left: spot.left, width: spot.right - spot.left, height: spot.bottom - spot.top, pointerEvents: 'auto' }} />
          )}
        </>
      ) : (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(2,6,23,0.80)', pointerEvents: dimOnly }} />
      ))}

      {/* Tutorial card */}
      <div ref={cardRef} style={{
        position: 'fixed', top: cardPos.top, left: cardPos.left, width: CARD_W,
        zIndex: 9001, pointerEvents: 'auto', fontFamily: 'inherit',
      }}>
        <div style={{
          background: 'linear-gradient(160deg, #1e2d45 0%, #1a2438 100%)',
          border: '1px solid rgba(99,102,241,0.50)', borderRadius: 12,
          padding: '18px 20px 16px',
          boxShadow: '0 16px 48px rgba(0,0,0,0.75), 0 0 0 1px rgba(99,102,241,0.08)',
          color: '#f1f5f9',
        }}>
          {/* meta row */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span style={{ fontSize: 10, color: '#818cf8', textTransform: 'uppercase', letterSpacing: '0.09em', fontWeight: 700 }}>Tutorial</span>
            <span style={{ fontSize: 11, color: '#475569' }}>{step + 1} / {TUTORIAL_STEPS.length}</span>
          </div>
          {/* progress */}
          <div style={{ height: 3, background: 'rgba(71,85,105,0.5)', borderRadius: 2, marginBottom: 14 }}>
            <div style={{ height: 3, background: 'linear-gradient(90deg,#6366f1,#818cf8)', borderRadius: 2, width: `${pct}%`, transition: 'width 0.3s ease' }} />
          </div>
          {/* title */}
          <h3 style={{ fontSize: 15, fontWeight: 700, color: '#f8fafc', margin: '0 0 10px', lineHeight: 1.3 }}>{current?.title}</h3>
          {/* body */}
          <div style={{ fontSize: 13, color: '#94a3b8', lineHeight: 1.65 }}>
            {current && (current.body.length === 1 ? (
              <p style={{ margin: 0 }}><TutorialText text={current.body[0]} /></p>
            ) : (
              <ul style={{ margin: 0, paddingLeft: 18, listStyle: 'disc' }}>
                {current.body.map((para, i) => (
                  <li key={i} style={{ marginBottom: i < current.body.length - 1 ? 8 : 0 }}><TutorialText text={para} /></li>
                ))}
              </ul>
            ))}
          </div>
          {/* mustInteract hint — or, once the action has become impossible, why we're moving on */}
          {current?.mustInteract && (
            <div style={{ marginTop: 11, padding: '7px 10px', background: stuck ? 'rgba(148,163,184,0.10)' : 'rgba(251,191,36,0.1)', border: stuck ? '1px solid rgba(148,163,184,0.25)' : '1px solid rgba(251,191,36,0.25)', borderRadius: 6, fontSize: 12, color: stuck ? '#cbd5e1' : '#fde68a', lineHeight: 1.5 }}>
              {stuck
                ? (current.unsatisfiableHint ?? 'This step can no longer be completed — click Next to carry on.')
                : (current.mustInteractHint ?? 'Perform the highlighted action above to continue.')}
            </div>
          )}
          {/* tryIt hint */}
          {current?.tryIt && !current?.mustInteract && (
            <div style={{ marginTop: 11, padding: '7px 10px', background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.25)', borderRadius: 6, fontSize: 12, color: '#a5b4fc', lineHeight: 1.5 }}>
              {current.tryItHint ?? 'Try the highlighted element, then click Next to continue.'}
            </div>
          )}
          {/* navigation */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 15 }}>
            <button onClick={onComplete} style={{ fontSize: 12, color: '#475569', background: 'none', border: 'none', cursor: 'pointer', padding: '4px 0', lineHeight: 1, fontFamily: 'inherit' }}>
              Skip tutorial
            </button>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {step > 0 && (
                <button onClick={() => onStep(advanceStep(step, -1))} style={{ fontSize: 13, color: '#94a3b8', background: 'rgba(30,41,59,0.9)', border: '1px solid #334155', borderRadius: 7, padding: '7px 14px', cursor: 'pointer', lineHeight: 1, fontFamily: 'inherit' }}>
                  ← Back
                </button>
              )}
              {/* No Next button for mustInteract steps — unless the action is unsatisfiable */}
              {!gated && (
                <button onClick={isLast ? onComplete : () => onStep(advanceStep(step, 1))} style={{ fontSize: 13, color: '#fff', background: 'linear-gradient(135deg,#6366f1,#4f46e5)', border: 'none', borderRadius: 7, padding: '7px 18px', cursor: 'pointer', fontWeight: 600, lineHeight: 1, fontFamily: 'inherit', boxShadow: '0 2px 10px rgba(99,102,241,0.45)' }}>
                  {isLast ? 'Finish' : 'Next →'}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )

  return createPortal(portal, document.body)
}
