import type { ReactNode } from 'react'
import { DRONE_ICON, TASK_ICON, CAT_ICON } from '../utils/icons'
import { ASSET_TYPE_LABEL } from '../utils/missionGen'
import type { AssetType, MissionCategory } from '../types'

// Inline symbol tokens usable inside tutorial step body text.
//   {blue} {red} {green}          → drone icon + coloured functional label (Fast/Lifter/Camera)
//   {T1}..{T5}                    → task icon + "T1" label
//   {catA}..{catE}                → category icon + "Cat A" label
//
// Using the symbol alongside the word is clearer than the word alone, so each
// token renders the icon together with its short label.

const DRONE_LABEL: Record<string, AssetType> = { blue: 'Blue', red: 'Red', green: 'Green' }
const DRONE_TEXT_COLOR: Record<AssetType, string> = {
  Blue: '#93c5fd', Red: '#fca5a5', Green: '#86efac',
}

const TOKEN_RE = /\{(blue|red|green|t[1-5]|cat[a-e])\}/gi

function DroneChip({ type }: { type: AssetType }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, verticalAlign: 'middle', whiteSpace: 'nowrap' }}>
      <img src={DRONE_ICON[type]} alt="" style={{ width: 16, height: 16, flex: 'none' }} />
      <span style={{ color: DRONE_TEXT_COLOR[type], fontWeight: 700 }}>{ASSET_TYPE_LABEL[type]}</span>
    </span>
  )
}

function TaskChip({ n }: { n: number }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, verticalAlign: 'middle', whiteSpace: 'nowrap' }}>
      <img src={TASK_ICON[n]} alt="" style={{ width: 16, height: 16, flex: 'none' }} />
      <span style={{ color: '#cbd5e1', fontWeight: 700 }}>{`T${n}`}</span>
    </span>
  )
}

function CatChip({ cat }: { cat: MissionCategory }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, verticalAlign: 'middle', whiteSpace: 'nowrap' }}>
      <img src={CAT_ICON[cat]} alt="" style={{ width: 16, height: 16, flex: 'none' }} />
      <span style={{ color: '#e2e8f0', fontWeight: 700 }}>{`Cat ${cat}`}</span>
    </span>
  )
}

function renderToken(token: string, key: number): ReactNode {
  const t = token.toLowerCase()
  if (t in DRONE_LABEL) return <DroneChip key={key} type={DRONE_LABEL[t]} />
  if (t[0] === 't')      return <TaskChip key={key} n={Number(t[1])} />
  if (t.startsWith('cat')) return <CatChip key={key} cat={t[3].toUpperCase() as MissionCategory} />
  return token
}

export default function TutorialText({ text }: { text: string }) {
  const parts: ReactNode[] = []
  let last = 0
  let key = 0
  let m: RegExpExecArray | null
  TOKEN_RE.lastIndex = 0
  while ((m = TOKEN_RE.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    parts.push(renderToken(m[1], key++))
    last = m.index + m[0].length
  }
  if (last < text.length) parts.push(text.slice(last))
  return <>{parts}</>
}
