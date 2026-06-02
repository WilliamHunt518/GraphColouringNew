import { useEffect, useRef, useState } from 'react'
import type { FreePlayAchievement } from '../types'

interface Props {
  achievements: FreePlayAchievement[]
  secondsLeft: number
  onSkip: () => void
  readOnly?: boolean  // map window — no skip button
}

function fmt(s: number) {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${String(sec).padStart(2, '0')}`
}

export default function FreePlayOverlay({ achievements, secondsLeft, onSkip, readOnly }: Props) {
  const allDone = achievements.length > 0 && achievements.every(a => a.done)
  const prevAllDone = useRef(false)
  const [flashDone, setFlashDone] = useState(false)

  // Flash "All done!" then auto-close after 2 s
  useEffect(() => {
    if (allDone && !prevAllDone.current) {
      prevAllDone.current = true
      setFlashDone(true)
      if (!readOnly) {
        const t = setTimeout(() => onSkip(), 2200)
        return () => clearTimeout(t)
      }
    }
  }, [allDone, onSkip, readOnly])

  return (
    <div style={{
      position: 'fixed', bottom: 20, right: 20, zIndex: 8000,
      width: 270, fontFamily: 'inherit',
      background: 'linear-gradient(160deg,#1e2d45,#1a2438)',
      border: `1px solid ${flashDone ? 'rgba(34,197,94,0.6)' : 'rgba(99,102,241,0.40)'}`,
      borderRadius: 12, padding: '14px 16px',
      boxShadow: '0 12px 40px rgba(0,0,0,0.70)',
      transition: 'border-color 0.4s',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        <span style={{
          fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em',
          color: flashDone ? '#4ade80' : '#818cf8',
          transition: 'color 0.4s',
        }}>
          {flashDone ? 'All done!' : 'Free Practice'}
        </span>
        <span style={{ fontSize: 11, color: secondsLeft < 60 ? '#f87171' : '#475569', fontVariantNumeric: 'tabular-nums' }}>
          {flashDone ? '' : fmt(secondsLeft)}
        </span>
      </div>

      {/* Achievement list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        {achievements.map(a => (
          <div key={a.id} style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
            {/* Checkbox */}
            <div style={{
              width: 16, height: 16, borderRadius: 4, flexShrink: 0, marginTop: 1,
              border: `1.5px solid ${a.done ? '#4ade80' : '#334155'}`,
              background: a.done ? 'rgba(74,222,128,0.18)' : 'transparent',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.3s',
            }}>
              {a.done && (
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                  <path d="M2 5l2.5 2.5L8 3" stroke="#4ade80" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              )}
            </div>
            <span style={{
              fontSize: 12, lineHeight: 1.4,
              color: a.done ? '#94a3b8' : '#64748b',
              textDecoration: a.done ? 'line-through' : 'none',
              transition: 'color 0.3s',
            }}>{a.label}</span>
          </div>
        ))}
      </div>

      {/* Done button (primary window only) */}
      {!readOnly && (
        <button
          onClick={onSkip}
          style={{
            marginTop: 12, width: '100%', padding: '7px 0',
            background: flashDone ? 'rgba(34,197,94,0.20)' : 'rgba(99,102,241,0.15)',
            border: `1px solid ${flashDone ? 'rgba(34,197,94,0.40)' : 'rgba(99,102,241,0.35)'}`,
            borderRadius: 7, color: flashDone ? '#4ade80' : '#818cf8',
            fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
            transition: 'all 0.3s',
          }}
        >
          {flashDone ? 'Continuing…' : 'Skip free play →'}
        </button>
      )}
    </div>
  )
}
