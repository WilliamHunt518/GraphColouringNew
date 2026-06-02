import { useState, useEffect, useCallback, useRef } from 'react'
import { createPortal } from 'react-dom'
import type { MapViewState } from '../types'
import { TUTORIAL_STEPS, TACTICAL_STEP_FIRST, TACTICAL_STEP_LAST } from '../utils/tutorialSteps'

interface Props {
  state: MapViewState
  step: number
  onNext: () => void
  onBack: () => void
  onComplete: () => void
}

interface SpotRect { top: number; left: number; right: number; bottom: number }

const CARD_W     = 370
const CARD_H_EST = 280
const MARGIN     = 12
const GAP        = 14

function clamp(min: number, val: number, max: number) {
  return Math.max(min, Math.min(max, val))
}

function computeCardPos(spot: SpotRect | null, side: string, vw: number, vh: number) {
  if (!spot || side === 'center') {
    return {
      top:  clamp(MARGIN, (vh - CARD_H_EST) / 2, vh - CARD_H_EST - MARGIN),
      left: clamp(MARGIN, (vw - CARD_W) / 2, vw - CARD_W - MARGIN),
    }
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

export default function TacticalTutorial({ state, step, onNext, onBack, onComplete }: Props) {
  const [spot, setSpot] = useState<SpotRect | null>(null)
  const chainCountRef        = useRef(0)
  const sawFailurePendingRef = useRef(false)

  const current = TUTORIAL_STEPS[step]

  // Only render for map-window steps
  if (!current?.inMapWindow) return null

  const isFirstTacStep = step === TACTICAL_STEP_FIRST
  const isLastTacStep  = step === TACTICAL_STEP_LAST

  // Auto-advance tac-select when user clicks a mission in the sidebar
  useEffect(() => {
    if (current?.id !== 'tac-select') return
    const handler = () => onNext()
    document.addEventListener('tutorial-mission-selected', handler)
    return () => document.removeEventListener('tutorial-mission-selected', handler)
  }, [step, current, onNext])

  // tac-chain: count Shift+drags, advance after 2
  useEffect(() => {
    if (current?.id !== 'tac-chain') { chainCountRef.current = 0; return }
    const handler = () => {
      chainCountRef.current++
      if (chainCountRef.current >= 2) setTimeout(() => onNext(), 400)
    }
    document.addEventListener('tutorial-drone-chained', handler)
    return () => document.removeEventListener('tutorial-drone-chained', handler)
  }, [step, current, onNext])

  // tac-suggest: advance when Suggest is clicked
  useEffect(() => {
    if (current?.id !== 'tac-suggest') return
    const handler = () => onNext()
    document.addEventListener('tutorial-suggest-clicked', handler)
    return () => document.removeEventListener('tutorial-suggest-clicked', handler)
  }, [step, current, onNext])

  // failure-recovery-do: advance when failureRecoveryPending transitions true → false
  useEffect(() => {
    if (current?.id !== 'failure-recovery-do') { sawFailurePendingRef.current = false; return }
    const hasPending = state.missions.some(m => m.failureRecoveryPending)
    if (hasPending) {
      sawFailurePendingRef.current = true
    } else if (sawFailurePendingRef.current) {
      setTimeout(() => onNext(), 600)
    }
  }, [state, step, current, onNext])

  // Spacebar advances non-mustInteract steps
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.code !== 'Space') return
      if (current?.mustInteract) return
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      e.preventDefault()
      if (isLastTacStep) onComplete()
      else onNext()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [step, current, isLastTacStep, onNext, onComplete])

  // Track highlighted element rect
  const refreshSpot = useCallback(() => {
    if (!current.highlight) { setSpot(null); return }
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
  }, [current.highlight, current.spotlightPadding])

  useEffect(() => {
    refreshSpot()
    const el = current.highlight
      ? document.querySelector(`[data-tutorial="${current.highlight}"]`) : null
    const ro = new ResizeObserver(refreshSpot)
    if (el) ro.observe(el)
    window.addEventListener('resize', refreshSpot)
    return () => { ro.disconnect(); window.removeEventListener('resize', refreshSpot) }
  }, [refreshSpot])

  const vw  = window.innerWidth
  const vh  = window.innerHeight
  const pct = ((step + 1) / TUTORIAL_STEPS.length) * 100
  const cardPos = computeCardPos(spot, current.cardSide ?? 'center', vw, vh)

  const isTryIt = !!(current.tryIt && !current.mustInteract)
  const dimOnly = isTryIt ? 'none' : 'auto'

  const portal = (
    <div style={{ position: 'fixed', inset: 0, zIndex: 9000, pointerEvents: 'none' }}>

      {/* Spotlight */}
      {spot ? (
        <>
          <div style={{ position: 'fixed', top: 0, left: 0, right: 0, height: spot.top, background: 'rgba(2,6,23,0.80)', pointerEvents: dimOnly }} />
          <div style={{ position: 'fixed', top: spot.bottom, left: 0, right: 0, bottom: 0, background: 'rgba(2,6,23,0.80)', pointerEvents: dimOnly }} />
          <div style={{ position: 'fixed', top: spot.top, left: 0, width: spot.left, height: spot.bottom - spot.top, background: 'rgba(2,6,23,0.80)', pointerEvents: dimOnly }} />
          <div style={{ position: 'fixed', top: spot.top, left: spot.right, right: 0, height: spot.bottom - spot.top, background: 'rgba(2,6,23,0.80)', pointerEvents: dimOnly }} />
          <div style={{
            position: 'fixed', top: spot.top, left: spot.left,
            width: spot.right - spot.left, height: spot.bottom - spot.top,
            border: '2px solid rgba(99,102,241,0.9)', borderRadius: 6,
            boxShadow: '0 0 0 1px rgba(99,102,241,0.2), 0 0 16px rgba(99,102,241,0.18)',
            pointerEvents: 'none',
          }} />
          {!current.allowClickThrough && !isTryIt && (
            <div style={{ position: 'fixed', top: spot.top, left: spot.left, width: spot.right - spot.left, height: spot.bottom - spot.top, pointerEvents: 'auto' }} />
          )}
        </>
      ) : (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(2,6,23,0.80)', pointerEvents: dimOnly }} />
      )}

      {/* Card */}
      <div style={{
        position: 'fixed', top: cardPos.top, left: cardPos.left, width: CARD_W,
        zIndex: 9001, pointerEvents: 'auto', fontFamily: 'inherit',
      }}>
        <div style={{
          background: 'linear-gradient(160deg,#1e2d45,#1a2438)',
          border: '1px solid rgba(99,102,241,0.50)', borderRadius: 12,
          padding: '18px 20px 16px',
          boxShadow: '0 16px 48px rgba(0,0,0,0.75)',
          color: '#f1f5f9',
        }}>
          {/* meta */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span style={{ fontSize: 10, color: '#818cf8', textTransform: 'uppercase', letterSpacing: '0.09em', fontWeight: 700 }}>Tutorial — Tactical Planner</span>
            <span style={{ fontSize: 11, color: '#475569' }}>{step + 1} / {TUTORIAL_STEPS.length}</span>
          </div>
          {/* progress */}
          <div style={{ height: 3, background: 'rgba(71,85,105,0.5)', borderRadius: 2, marginBottom: 14 }}>
            <div style={{ height: 3, background: 'linear-gradient(90deg,#6366f1,#818cf8)', borderRadius: 2, width: `${pct}%`, transition: 'width 0.3s ease' }} />
          </div>
          {/* title */}
          <h3 style={{ fontSize: 15, fontWeight: 700, color: '#f8fafc', margin: '0 0 10px', lineHeight: 1.3 }}>{current.title}</h3>
          {/* body */}
          <div style={{ fontSize: 13, color: '#94a3b8', lineHeight: 1.65 }}>
            {current.body.map((para, i) => (
              <p key={i} style={{ margin: i < current.body.length - 1 ? '0 0 8px' : 0 }}>{para}</p>
            ))}
          </div>
          {/* mustInteract hint */}
          {current.mustInteract && (
            <div style={{ marginTop: 11, padding: '7px 10px', background: 'rgba(251,191,36,0.1)', border: '1px solid rgba(251,191,36,0.25)', borderRadius: 6, fontSize: 12, color: '#fde68a', lineHeight: 1.5 }}>
              Perform the highlighted action to continue.
            </div>
          )}
          {/* tryIt hint */}
          {current.tryIt && !current.mustInteract && (
            <div style={{ marginTop: 11, padding: '7px 10px', background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.25)', borderRadius: 6, fontSize: 12, color: '#a5b4fc', lineHeight: 1.5 }}>
              {current.tryItHint ?? 'Try the highlighted element, then click Next.'}
            </div>
          )}
          {/* navigation */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 15 }}>
            <button onClick={onComplete} style={{ fontSize: 12, color: '#475569', background: 'none', border: 'none', cursor: 'pointer', padding: '4px 0', lineHeight: 1, fontFamily: 'inherit' }}>
              Skip tutorial
            </button>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {!isFirstTacStep && (
                <button onClick={onBack} style={{ fontSize: 13, color: '#94a3b8', background: 'rgba(30,41,59,0.9)', border: '1px solid #334155', borderRadius: 7, padding: '7px 14px', cursor: 'pointer', lineHeight: 1, fontFamily: 'inherit' }}>
                  ← Back
                </button>
              )}
              {!current.mustInteract && (
                <button onClick={isLastTacStep ? onComplete : onNext} style={{ fontSize: 13, color: '#fff', background: 'linear-gradient(135deg,#6366f1,#4f46e5)', border: 'none', borderRadius: 7, padding: '7px 18px', cursor: 'pointer', fontWeight: 600, lineHeight: 1, fontFamily: 'inherit', boxShadow: '0 2px 10px rgba(99,102,241,0.45)' }}>
                  {isLastTacStep ? 'Finish' : 'Next →'}
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
