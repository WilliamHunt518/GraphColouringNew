// build-map-bg.mjs — generate the static operational-map background.
//
// Downloads OpenTopoMap raster tiles for an area and stitches them into a single
// JPEG at public/map-bg.jpg (5:4 to match the 1000x800 world). One-off / build-time
// only — the resulting image is committed and served statically; the app makes no
// network calls at runtime.
//
//   node scripts/build-map-bg.mjs
//
// To redraft a different area, edit AREA below (center lat/lon) and rerun.
//
// Tiles: © OpenTopoMap (CC-BY-SA), © OpenStreetMap contributors.

import sharp from 'sharp'
import { mkdir } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const OUT = resolve(__dirname, '../public/map-bg.jpg')

// --- Area selection -------------------------------------------------------
// Buttermere / Crummock Water, Lake District: lakes, fells, the small village
// of Buttermere (building cluster), sparse labels on OpenTopoMap.
const AREA = {
  lat: 54.5417,
  lon: -3.2772,
  zoom: 14,
  cols: 14, // 14*256 = 3584 px wide
  rows: 8,  //  8*256 = 2048 px tall  -> 1.75 (~16:9)
}

const TILE = 256
const SERVERS = ['a', 'b', 'c']

// Fractional slippy-tile coords for a lat/lon at a zoom.
function tileXY(lat, lon, z) {
  const n = 2 ** z
  const x = ((lon + 180) / 360) * n
  const latRad = (lat * Math.PI) / 180
  const y = ((1 - Math.asinh(Math.tan(latRad)) / Math.PI) / 2) * n
  return { x, y }
}

async function fetchTile(z, x, y, attempt = 0) {
  const s = SERVERS[(x + y) % SERVERS.length]
  const url = `https://${s}.tile.opentopomap.org/${z}/${x}/${y}.png`
  try {
    const res = await fetch(url, {
      headers: {
        // OpenTopoMap asks for a descriptive UA identifying the application.
        'User-Agent': 'SAR-Study-MapBuilder/1.0 (research; contact william.hunt518@gmail.com)',
      },
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return Buffer.from(await res.arrayBuffer())
  } catch (err) {
    if (attempt < 4) {
      await new Promise(r => setTimeout(r, 500 * (attempt + 1)))
      return fetchTile(z, x, y, attempt + 1)
    }
    throw new Error(`Failed tile ${z}/${x}/${y}: ${err.message}`)
  }
}

async function main() {
  const { lat, lon, zoom, cols, rows } = AREA
  const c = tileXY(lat, lon, zoom)
  const x0 = Math.round(c.x - cols / 2)
  const y0 = Math.round(c.y - rows / 2)
  const n = 2 ** zoom

  console.log(`Area: ${lat},${lon} z${zoom} — tiles x[${x0}..${x0 + cols - 1}] y[${y0}..${y0 + rows - 1}]`)

  const composites = []
  let done = 0
  for (let dy = 0; dy < rows; dy++) {
    for (let dx = 0; dx < cols; dx++) {
      const tx = ((x0 + dx) % n + n) % n
      const ty = y0 + dy
      const buf = await fetchTile(zoom, tx, ty)
      composites.push({ input: buf, left: dx * TILE, top: dy * TILE })
      done++
      process.stdout.write(`\r  tiles: ${done}/${cols * rows}`)
      await new Promise(r => setTimeout(r, 120)) // be polite
    }
  }
  process.stdout.write('\n')

  await mkdir(dirname(OUT), { recursive: true })
  await sharp({
    create: {
      width: cols * TILE,
      height: rows * TILE,
      channels: 3,
      background: { r: 11, g: 18, b: 32 },
    },
  })
    .composite(composites)
    .jpeg({ quality: 82 })
    .toFile(OUT)

  console.log(`Wrote ${OUT} (${cols * TILE}x${rows * TILE})`)
}

main().catch(e => {
  console.error(e)
  process.exit(1)
})
