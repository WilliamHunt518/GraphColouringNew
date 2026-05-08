import { useState, useEffect } from 'react'
import StartScreen from './components/StartScreen'
import GameShell from './components/GameShell'
import MapWindowClient from './components/MapWindowClient'
import type { StudyConfig } from './types'
import { parseURLConfig } from './utils/config'

const isMapWindow = new URLSearchParams(window.location.search).get('view') === 'map'

export default function App() {
  if (isMapWindow) return <MapWindowClient />

  const [config, setConfig] = useState<StudyConfig | null>(null)

  useEffect(() => {
    const urlConfig = parseURLConfig()
    if (urlConfig) setConfig(urlConfig)
  }, [])

  if (!config) return <StartScreen onStart={setConfig} />
  return <GameShell config={config} />
}
