import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'
import { initWindowZoom } from './utils/windowZoom'

// Per-window UI zoom, independent of the browser's per-origin page zoom.
initWindowZoom()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
