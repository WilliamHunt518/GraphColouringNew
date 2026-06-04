import { useEffect, useRef, useState, useCallback } from 'react'
import { createPortal } from 'react-dom'
import type { GameState } from '../types'
import type { GameAction } from '../store/actions'
import { TUTORIAL_STEPS, AGENT_INTRO_STEP, FAILURE_DEMO_STEP, ALLOCATION_OVERRIDE_STEP } from '../utils/tutorialSteps'

interface Props {
  state: GameState
  dispatch: (a: GameAction) => void
  step: number
  onStep: (s: number) => void
  onComplete: () => void
}

interface SpotRect { top: number; left: number; right: number; bottom: number }

const CARD_W   = 390
const CARD_H_EST = 290
const MARGIN   = 12
const GAP      = 16

function clamp(min: number, val: number, max: number) {
  return Math.max(min, Math.min(max, val))
}

function computeCardPos(spot: SpotRect | null, side: string, vw: number, vh: number) {
  const centeredTop  = clamp(MARGIN, (vh - CARD_H_EST) / 2, vh - CARD_H_EST - MARGIN)
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
    if (top + CARD_H_EST > vh - MARGIN) top = spot.top - CARD_H_EST - GAP
  } else {
    top = spot.top - CARD_H_EST - GAP; left = spot.left
    if (top < MARGIN) top = spot.bottom + GAP
  }
  return {
    top:  clamp(MARGIN, top,  vh - CARD_H_EST - MARGIN),
    left: clamp(MARGIN, left, vw - CARD_W - MARGIN),
  }
}

export default function Tutorial({ state, dispatch, step, onStep, onComplete }: Props) {
  const [spot, setSpot] = useState<SpotRect | null>(null)
  const [failureHoldExpired, setFailureHoldExpired] = useState(false)
  const autoFiredRef           = useRef(new Set<number>())
  const missionForcedRef       = useRef(false)
  const missionTwoForcedRef    = useRef(false)
  const overrideTeamFiredRef   = useRef(false)
  const failureDemoFiredRef    = useRef(false)
  const failureTryTimerRef     = useRef<ReturnType<typeof setTimeout> | null>(null)

  const current = TUTORIAL_STEPS[step]
  const isLast  = step === TUTORIAL_STEPS.length - 1

  // Spawn first demo mission at tutorial start
  useEffect(() => {
    if (missionForcedRef.current) return
    missionForcedRef.current = true
    if (state.pendingBlueprints.length > 0) {
      dispatch({ type: 'FORCE_MISSION_ARRIVAL' })
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Override the first mission's drone team when the allocation-override step is entered
  useEffect(() => {
    if (overrideTeamFiredRef.current) return
    if (step !== ALLOCATION_OVERRIDE_STEP) return
    overrideTeamFiredRef.current = true
    dispatch({ type: 'TUTORIAL_OVERRIDE_TEAM' })
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
      dispatch({ type: 'FORCE_DRONE_FAILURE' })
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

  // Auto-advance based on game state
  useEffect(() => {
    if (!current?.autoAdvanceWhen) return
    if (autoFiredRef.current.has(step)) return
    if (current.autoAdvanceWhen(state)) {
      autoFiredRef.current.add(step)
      setTimeout(() => onStep(Math.min(step + 1, TUTORIAL_STEPS.length - 1)), current?.autoAdvanceDelay ?? 500)
    }
  }, [state, step, current, onStep])

  // Advance panel-intro step when user clicks "Set manually instead"
  useEffect(() => {
    if (current?.id !== 'panel-intro') return
    const handler = () => onStep(Math.min(step + 1, TUTORIAL_STEPS.length - 1))
    document.addEventListener('tutorial-manual-selected', handler)
    return () => document.removeEventListener('tutorial-manual-selected', handler)
  }, [step, current, onStep])


  // Spacebar advances non-mustInteract steps
  useEffect(() => {
    if (current?.inMapWindow) return
    const handler = (e: KeyboardEvent) => {
      if (e.code !== 'Space') return
      if (current?.mustInteract) return
      // Don't fire when focus is inside an input/button (let normal behaviour run)
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      e.preventDefault()
      if (isLast) onComplete()
      else onStep(step + 1)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [step, current, isLast, onComplete, onStep])

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

  const cardPos = computeCardPos(spot, current?.cardSide ?? 'center', vw, vh)

  // tryIt steps: dim only — whole interface stays interactive
  // mustInteract steps: only the spotlight is interactive (allowClickThrough handles opening it)
  // regular steps: everything blocked
  const isTryIt = !!(current?.tryIt && !current?.mustInteract)
  const dimOnly = isTryIt ? 'none' : 'auto'

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
      <div style={{
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
            {current?.body.map((para, i) => (
              <p key={i} style={{ margin: i < (current.body.length - 1) ? '0 0 8px' : 0 }}>{para}</p>
            ))}
          </div>
          {/* mustInteract hint */}
          {current?.mustInteract && (
            <div style={{ marginTop: 11, padding: '7px 10px', background: 'rgba(251,191,36,0.1)', border: '1px solid rgba(251,191,36,0.25)', borderRadius: 6, fontSize: 12, color: '#fde68a', lineHeight: 1.5 }}>
              {current.mustInteractHint ?? 'Perform the highlighted action above to continue.'}
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
                <button onClick={() => onStep(step - 1)} style={{ fontSize: 13, color: '#94a3b8', background: 'rgba(30,41,59,0.9)', border: '1px solid #334155', borderRadius: 7, padding: '7px 14px', cursor: 'pointer', lineHeight: 1, fontFamily: 'inherit' }}>
                  ← Back
                </button>
              )}
              {/* No Next button for mustInteract steps */}
              {!current?.mustInteract && (
                <button onClick={isLast ? onComplete : () => onStep(step + 1)} style={{ fontSize: 13, color: '#fff', background: 'linear-gradient(135deg,#6366f1,#4f46e5)', border: 'none', borderRadius: 7, padding: '7px 18px', cursor: 'pointer', fontWeight: 600, lineHeight: 1, fontFamily: 'inherit', boxShadow: '0 2px 10px rgba(99,102,241,0.45)' }}>
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
