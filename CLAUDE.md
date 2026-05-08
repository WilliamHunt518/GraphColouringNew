# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

A **web-based human-subjects study platform** for research on trust in hierarchical autonomous AI systems. Operators manage a reserve of heterogeneous drone assets and allocate them to incoming search-and-rescue missions. Two AI assistants operate at different decision tiers:

- **Co-Pilot** — tactical tier; triggered when allocating a mission; proposes three strategies
- **Meta-Co-Pilot** — strategic tier; always-visible widget; recommends reserve posture

Study uses a **2×2 between-subjects design** manipulating the accuracy of each assistant independently (conditions HH / LH / HL / LL).

## Tech Stack

- **React 18 + Vite 5 + TypeScript** — SPA, no backend
- **Tailwind CSS v3** — layout and styling
- **SVG** — operational map (asset animation, mission zones, routes)
- **BroadcastChannel API** — two-window state sync for dual-monitor setup
- All randomness seeded via Mulberry32 PRNG (`src/utils/prng.ts`) — same seed → same session

## Running the App

```bash
npm install       # once
npm run dev       # dev server at http://localhost:5173
```

**URL parameters** pre-fill the start screen (useful for researcher setup):
```
http://localhost:5173/?pid=P001&condition=HH&complexity=medium&seed=42
```

**Two-monitor setup:**
- Primary window: `http://localhost:5173/` (default view)
- Map window: `http://localhost:5173/?view=map` — receives state via BroadcastChannel

## Architecture

### Study Design

Three 10-minute sessions separated by 30-second between-session screens. Asset pool: 18 Blue, 9 Red, 3 Green (30 total).

| Condition | ε_Co-Pilot | ε_Meta-Co-Pilot |
|-----------|-----------|----------------|
| HH        | 0.10      | 0.10           |
| LH        | 0.40      | 0.10           |
| HL        | 0.10      | 0.40           |
| LL        | 0.40      | 0.40           |

### Key Files

```
index.html               # Vite entry
src/
  main.tsx               # React root mount
  App.tsx                # Top-level: StartScreen → GameShell
  index.css              # Tailwind directives + base styles
  types/
    index.ts             # All TypeScript types (Asset, Task, Mission, GameState, events)
  utils/
    prng.ts              # SeededRNG class (Mulberry32)
    config.ts            # URL param parsing, condition → epsilon mapping
    missionGen.ts        # Seeded mission generator (Poisson arrivals, zone placement)
    copilot.ts           # Co-Pilot strategy generator with ε noise
    metacopilot.ts       # Meta-Co-Pilot posture evaluator with ε noise
    scoring.ts           # Score, green efficiency, follow-rate calculation
  store/
    gameReducer.ts       # useReducer state machine
    actions.ts           # Action type union
  components/
    StartScreen.tsx      # Researcher setup: participantId, condition, complexity, seed
    GameShell.tsx        # Session wrapper, clock, broadcast sync
    PrimaryDisplay.tsx   # Reserve panel + mission queue + Co-Pilot modal + MCP widget
    MapDisplay.tsx       # SVG operational map
    SurveyModal.tsx      # NASA-TLX, trust, TAM surveys
    TrustProbe.tsx       # Periodic 2-question trust/workload probe (every 90s)
    BetweenSession.tsx   # 30s inter-session screen
```

### Data Output

All events logged in-memory. At session end, "Download Data" button exports:
```json
{
  "participantId": "P001",
  "condition": "HH",
  "seed": 42,
  "sessions": [{ ...events }]
}
```

### Mission Generation

Poisson inter-arrivals: Easy λ=120s, Medium λ=75s, Hard λ=45s.
Zone: circle r=80, ≥150 units from hub (500,400), ≥200 units from other active zones.
Tasks execute greedily (T5 first → most constrained).

### Asset Speeds (units/second)

| Type  | Speed | Notes |
|-------|-------|-------|
| Blue  | 3.0   | Fast, recce-only |
| Red   | 2.0   | Standard, supply + extract |
| Green | 1.4   | Slow, required for T4/T5 |

### Trust Probe

A 2-question modal (trust 1–10, workload 1–10) appears every 90 seconds during play. Non-blocking — operator can dismiss immediately.

## Development Guidelines

### Adding task types or asset types
Edit `src/types/index.ts` first, then update `missionGen.ts` and `copilot.ts`.

### Changing accuracy
Edit `conditionToEpsilons()` in `src/utils/config.ts`.

### Modifying Co-Pilot strategies
`src/utils/copilot.ts` — `generateStrategies()`. Noise is applied to objective weights before ranking.

### Modifying Meta-Co-Pilot
`src/utils/metacopilot.ts` — `evaluatePosture()`. Noise perturbs the category forecast before EV calculation.

## Critical Constraints

1. **All randomness seeded** — pass `SeededRNG` instances everywhere, never call `Math.random()` in game logic
2. **No backend** — all state in-memory; export is a client-side JSON download
3. **UI language** — use "assistant" or "Co-Pilot" / "Meta-Co-Pilot", never "AI" or "algorithm"
4. **Events logged immediately** — every operator action and agent recommendation must be logged with ms timestamp
5. **BroadcastChannel host/client** — primary window is host; map window subscribes only; never let client mutate state
