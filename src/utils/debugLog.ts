// Module-level debug log — accumulated in memory, downloadable via header button

const entries: string[] = []

export function debugLog(msg: string, data?: unknown): void {
  const ts = new Date().toISOString()
  const line = data !== undefined
    ? `[${ts}] ${msg} ${JSON.stringify(data, null, 0)}`
    : `[${ts}] ${msg}`
  entries.push(line)
  // Also echo to console for live inspection
  console.debug('[DBG]', msg, data ?? '')
}

export function downloadDebugLog(): void {
  const blob = new Blob([entries.join('\n') + '\n'], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `sar-debug-${Date.now()}.log`
  a.click()
  URL.revokeObjectURL(url)
}

export function clearDebugLog(): void {
  entries.length = 0
}

export function logCount(): number {
  return entries.length
}
