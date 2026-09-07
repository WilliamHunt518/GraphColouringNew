# Running this study online (Prolific) — feasibility, build plan, and costing

**Status: proposal, not built.** Nothing in `src/` targets an unsupervised online participant yet.
This document is the plan and the budget; it becomes a `study-v2.x` section in
[`STUDY_BUILD.md`](STUDY_BUILD.md) if and when it is actually built.

Costed at **2026-09-07** prices. Every external rate (National Living Wage, Prolific's service fee,
VAT treatment, Cloudflare free-tier limits) is quoted with its source assumption — **re-check them
before committing a budget**, they move.

---

## 1. The short answer

| Question | Answer |
| --- | --- |
| Is it feasible? | Yes. No backend to port — the app is a static SPA that already logs everything client-side. |
| Biggest blocker | The **two-window dual-monitor layout**. Online participants have one screen. Needs a single-window build. |
| Second blocker | Data currently leaves as a **manual file download** with the researcher watching. Needs a POST endpoint. |
| Hosting cost | **£0–£15 for the whole study.** Static site + ~5 small writes per participant sits inside free tiers. |
| Participant cost | **~£25 per completed participant** all-in (£13 base + £5 bonus + Prolific fee + VAT). |
| 30 participants | **~£760**, or **~£870** with a sensible over-recruit buffer. |
| Concurrency ceiling | Technically thousands/day. Practically limited only by your own monitoring — **2–5 at a time over 3–5 days is comfortable** for 20–30 people. |
| Dev effort | **6–8 working days**, plus ethics amendment lead time. |
| What you lose | Screen + mic recording, so **no narration data** (`NARRATION.md`) from the online arm. Online = behavioural log only. |

Gorilla is genuinely not needed. Gorilla buys you a task builder, hosting, randomisation and a
Prolific handshake; you already have the task, hosting is free, and the handshake is three URL
parameters and a redirect. Its per-participant licence buys nothing you cannot do with a 60-line
Cloudflare Worker — and it cannot host a custom React SPA of this complexity as a native task
anyway, so you would be paying Gorilla to iframe your own site.

---

## 2. What has to change in the app

Ordered by how much they matter. Effort figures are dev-days for someone who knows this codebase.

### 2.1 Single-window layout — **must have, 1–2 days**

Today the strategic view (`PrimaryDisplay`) and the tactical view (`MapDisplay`) live in two browser
windows synced over `BroadcastChannel`, opened via `window.open('/?view=map')`
(`PrimaryDisplay.tsx:214`). Two hard problems online:

1. **Width.** `PrimaryDisplay` reserves a 440 px fixed panel plus the map; `MapDisplay` reserves a
   560 px panel plus the map. Side by side that wants ~1900 px. A large share of Prolific
   participants are on 1366×768 laptops.
2. **The clock.** The primary window drives the sim from `requestAnimationFrame`. If a participant
   puts one window on top of the other — which they will, on one screen — the browser suspends rAF
   on the occluded window and `MAX_TICK_GAP_MS` pauses the session. In the lab you fix that by
   telling the operator to keep both visible. Online there is nobody to tell.

**Recommendation: a tabbed single window.** One shell with a Strategic ⇄ Tactical tab bar, rendering
`PrimaryDisplay` or `MapDisplay` into the same window, no `BroadcastChannel` at all. 440 px + map
fits 1280 px; 560 px + map fits 1280 px. Keep the existing two-window path intact behind a flag
(`?layout=single`) so the lab arm is untouched.

Optionally auto-promote to a genuine side-by-side split when `window.innerWidth >= 1800`, so the
participants who *do* have a big monitor get the lab layout.

**Design implication — flag this, do not bury it.** Not being able to see both tiers at once changes
the task. A tab switch costs attention that a glance across two monitors does not, which plausibly
shifts exactly the strategic/tactical division of labour the study measures. So:

- Log `layout: 'dual' | 'tabbed' | 'split'` and `platform: 'lab' | 'online'` in `session_start`.
- Log every tab switch as its own event. It is a real attention datum, arguably a *better* one than
  the lab arm gives you — you cannot see a head turn in the log, but you can see a tab click.
- **Do not pool lab and online sessions** without that flag in the model.

### 2.2 Server-side data capture — **must have, 0.5–1 day**

`DoneScreen` (`GameShell.tsx:331`) builds a JSON blob and triggers a download, and the copy says
"Please ask the researcher to confirm your data has been saved." Online, a participant who closes
the tab at minute 40 takes everything with them.

Full exports run **~3.2 MB** per 3-session participant (the largest in `logs/Pilots/auto/` is
3.5 MB), so roughly 1.1 MB per session.

Write incrementally, never once at the end:

- POST after the demographics/AI-attitude form, after **each** session, and after each survey page.
- `navigator.sendBeacon` on `visibilitychange`/`pagehide` for the partial state.
- Keep the existing `localStorage` autosave (`GameShell.tsx:142`) as the offline fallback, and
  re-POST it on the next load if a send failed.
- Keep the download button, gated behind `?researcher=1`, for the lab arm.

Gzip client-side (`CompressionStream`) before POSTing — 1.1 MB becomes ~100 KB and sidesteps every
serverless body-size limit.

### 2.3 Prolific handshake — **0.5 day**

Prolific appends `?PROLIFIC_PID=…&STUDY_ID=…&SESSION_ID=…`. Parse them in `parseURLConfig`
(`src/utils/config.ts`), use `PROLIFIC_PID` as `participantId`, store all three, and **skip
`StartScreen` entirely** — an online participant must never see the researcher setup form.

Assignment (seed, and the per-session complexity order if you counterbalance) should be a
**deterministic hash of `PROLIFIC_PID`**, not a server counter. The same participant returning gets
the same condition, there is no server state, no race between simultaneous starts, and the
assignment is reproducible from the log alone. (`STUDY_SEED = 42` is currently canonical and shared
by everyone — keep that if you want one fixed scenario, which is the simpler analysis.)

On finish, redirect to the study's Prolific completion URL. Fire and await the final POST **before**
the redirect.

### 2.4 Consent, information sheet, debrief — **0.5 day + ethics text**

Not present at all today. Needed: information sheet, tick-box consent with a data-handling statement
naming where data is stored (see §3.3), right to withdraw, and a debrief page alongside the
completion redirect. Ethics will also want the retention period and the lawful basis.

### 2.5 Comprehension gate and attention checks — **0.5 day**

`DemographicsForm`'s `understand_*` items are **self-rated confidence**, not scored comprehension —
fine with a researcher in the room, useless as an unsupervised gate. Add 3–4 scored items after the
tutorial with a right answer (e.g. "Which drone type is required by T3, T4 and T5?"), allow one
retry with the relevant tutorial step re-shown, and log both attempts. Add one instructed-response
item inside a Likert block per survey.

Do **not** auto-reject on a failed check — Prolific's rules make that risky. Log it and exclude in
analysis.

### 2.6 Environment gating — **0.5 day**

Before consent: refuse phones and tablets, require `innerWidth >= 1280`, warn on unsupported
browsers, offer a fullscreen prompt, and run a 3-second rAF benchmark — this app animates a lot of
SVG, and a weak machine will drop frames and change the task. Screen out at the top, before you owe
anyone money. Set Prolific's own device screener to desktop-only too, but verify client-side: it is
self-reported.

Log `visibilitychange` throughout so you can see who tabbed away mid-session.

### 2.7 Session count and timing — **0.5 day + pilot**

Estimated unsupervised run of the current flow:

| Stage | Minutes |
| --- | --- |
| Information sheet + consent | 2 |
| Demographics + AIAS-4 + verification + delegation scales | 6 |
| Tutorial (48 steps, unsupervised, `tutorialSteps.ts`) | 12 |
| Session 1 (480 s) | 8 |
| Survey (NASA-TLX + trust) | 3 |
| Between-session screen | 0.5 |
| Session 2 (480 s) | 8 |
| Survey (+ TAM on the last) | 4 |
| Debrief + redirect | 1 |
| **Two-session total** | **~45** |
| Three-session total | ~56 |

**Recommendation: run 2 sessions online, not 3.** Prolific return rates climb sharply past ~45
minutes, and a return at minute 50 costs you the whole participant. Two sessions still supports the
within-subject Strategic Heavy → Tactical Heavy contrast via `sessionComplexities`
(`complexityForSession` in `gameReducer.ts`), which is the main reason for multiple sessions anyway.
Advertise 60 minutes and pay for 60 — finishing early is a feature, and Prolific pays the advertised
rate regardless.

The tutorial is the risk: 48 steps written for someone who can ask a question. Watch the pilot
timings on it specifically, and consider an unsupervised trim.

### 2.8 Bonus computation — **0.25 day**

Prolific bonuses upload as a `PID,amount` CSV. Add a script alongside `scripts/study_report.py` that
reads the collected logs, applies the published rule, and emits that CSV.

**The rule must be stated to the participant before they start**, and it must be one they can
influence without being able to game. A threshold on total score across sessions is simplest and
suits the £5 figure: *"a £5 bonus if your total score is above the median of participants so far"*
is defensible; *"the top 20% get £5"* is defensible; a graded £0–£5 is fairer but more to explain.

The budget below assumes flat-£5-on-threshold, with two scenarios: everyone earns it (worst case)
and 70% earn it (a median threshold plus generosity).

### 2.9 Removals and copy — **0.25 day**

- Delete the "ask the researcher" copy from `DoneScreen`.
- Screen/mic recording (`scripts/record-screens.bat`) has no online equivalent. Do not attempt a
  browser-based substitute: `getDisplayMedia` needs a permission prompt most participants will
  refuse, and uploading video blows every free tier.
- Keep session scores hidden on the done screen (already conditional on `collectDemographics`).

---

## 3. Costing

### 3.1 Participant payment

Assumptions, **verify each**:

- **UK National Living Wage (21+) is £12.71/hour** from April 2026. That is what "at or above UK
  minimum wage" means for an adult participant pool.
- **Prolific's service fee is 33.3%** of everything you pay a participant, **including bonuses**, on
  a pay-as-you-go account. Some plans differ — check the account.
- **UK customers are charged 20% VAT on the service fee.** A university generally cannot recover it,
  so it is a real cost. Confirm with your finance office.

| Line | Per participant |
| --- | --- |
| Base payment (60 min @ £13.00/hr — above NLW, round figure) | £13.00 |
| Performance bonus | £5.00 |
| **Participant receives** | **£18.00** |
| Prolific fee @ 33.3% | £6.00 |
| VAT @ 20% on the fee | £1.20 |
| **Total cost to you** | **£25.20** |

If ~70% earn the bonus (average bonus £3.50), the per-participant figure drops to **£23.10**.

Setting the base at exactly NLW (£12.71) saves about £0.40 per participant all-in — not worth the
untidiness. £13.00/hr reads better on the listing and Prolific's fair-pay indicator shows "Great".

### 3.2 Study totals

| N | Everyone bonuses (£25.20 ea.) | 70% bonus (£23.10 ea.) |
| --- | --- | --- |
| 5 (pilot) | £126 | £116 |
| 20 | £504 | £462 |
| 30 | £756 | £693 |
| 30 + 15% buffer | **£870** | **£797** |

The buffer covers **timed-out submissions** (a participant who stalls and lets the clock run out
often still warrants payment) and the occasional part-completion you choose to pay out of fairness.
Straight **returns cost nothing** — Prolific does not charge for them — so the buffer is smaller
than the raw dropout rate suggests.

**Plan for ~£870 to land 30 usable participants, plus ~£126 for a 5-person pilot: ~£1,000 total.**
Load the pilot money separately; you will change something after it.

Note that Prolific requires the account to be pre-funded, so this is cash up front, not invoiced.

### 3.3 Hosting

The app is static and everything is computed in the browser. The server exists only to catch ~5
small JSON writes per participant.

**Recommended: Cloudflare Pages + one Worker + R2.**

| Component | Role | Free tier | This study needs |
| --- | --- | --- | --- |
| Pages | serve the built SPA | unlimited static requests + bandwidth | 30 × ~3 MB ≈ 90 MB |
| Workers | one POST endpoint | 100,000 requests/day | ~150 requests **total** |
| R2 | store the JSON | 10 GB, 1M writes/month | ~100 MB, ~150 writes |

**Cost: £0.** Optional custom domain ~£10/year. `public/map-bg.jpg` is 2.5 MB of the 3 MB initial
load — worth converting to WebP (~400 KB) for participants on slow connections, which is a UX win
rather than a cost one.

Alternatives:

| Option | Cost | When to pick it |
| --- | --- | --- |
| Cloudflare Pages + Worker + R2 | **£0** | Default. |
| Netlify/Vercel + Supabase | £0 | If you prefer Postgres. Watch Vercel's 4.5 MB function body limit — POST per session, gzipped, and you are fine. |
| Hetzner CX22 VPS + Caddy + SQLite | ~£3.30/month, **~£10 for the study** | If ethics insists on a named EU/UK host under your sole control, or wants no US-headquartered processor. |

For ethics: Cloudflare R2 supports an **EU jurisdiction** restriction at bucket creation, which is
usually enough. If it is not, take the VPS — £10 is not worth an argument.

Secure the endpoint minimally but genuinely: a shared token in the build, an origin check, a body
size cap, and a per-PID rate limit. It stores pseudonymous research data, so the risk is junk
writes rather than disclosure — but do not leave it open to the internet unauthenticated.

### 3.4 Grand total

| | Low | High |
| --- | --- | --- |
| Pilot (5) | £116 | £126 |
| Main study (30, buffered) | £797 | £870 |
| Hosting | £0 | £15 |
| Domain (optional) | £0 | £10 |
| **Total** | **~£915** | **~£1,020** |

Dev time (6–8 days) is the real cost and is not in that table.

---

## 4. Concurrency — how many at once?

**Technically, concurrency is a non-issue.** Every participant runs the entire simulation in their
own browser; the server does nothing but accept ~5 writes. The Cloudflare free tier's 100k
requests/day is roughly **20,000 participants/day** of headroom. There is no shared state, no
matchmaking, no session lock. Two hundred simultaneous participants would work as well as two.

The one thing that *would* have needed coordination — assigning conditions without collisions when
two people start at the same instant — is designed away by deriving assignment from a hash of
`PROLIFIC_PID` (§2.3). No counter, no race.

**So the limit is you, not the infrastructure.** Practically:

- **Keep 2–5 in flight.** With 20–30 participants at ~45 min each that is **3–5 days**, which is
  the right pace for a first online run: you can read the first day's logs before the second day's
  participants arrive.
- **Release in waves.** Publish with a small number of places (say 5), verify the data landed and
  looks sane, then use Prolific's "increase places" to top up. Batching is your undo button — a bug
  found after 5 participants costs £126; after 30 it costs £756.
- Prolific has no direct "max concurrent" control; places-available is the throttle.
- Expect clustering. Prolific participants pounce on new studies, so a batch of 5 often starts
  within minutes of each other. Fine here, but it means "5 places" really can mean 5 simultaneous.
- Schedule releases for **UK daytime** if the pool is UK-restricted, which it should be — both for
  the wage argument and for a consistent participant pool.

Per-participant client load is the only genuine resource question, and it is per-machine: the sim
runs `requestAnimationFrame` over a busy SVG scene. That is what the §2.6 benchmark is for.

---

## 5. Build order

1. Single-window tabbed layout behind `?layout=single`; verify at 1280×720. *(§2.1)*
2. Worker + R2 endpoint; incremental POST + beacon + localStorage fallback. *(§2.2)*
3. Prolific entry/exit: URL params in, deterministic assignment, completion redirect out. *(§2.3)*
4. Consent / information sheet / debrief. *(§2.4)*
5. Comprehension gate, attention checks, environment gate. *(§2.5, §2.6)*
6. Cut to 2 sessions; re-time the tutorial. *(§2.7)*
7. Bonus CSV script. *(§2.8)*
8. Copy cleanup and researcher-only gating of the download button. *(§2.9)*
9. **Internal dry run** — someone outside the project, no help given, watching where they stall.
10. **Prolific pilot, 5 people, ~£126.** Read every log. Fix.
11. Release in waves of 5–10.

Steps 1–8 are the 6–8 days. Steps 9–11 are calendar time, not effort. Start the ethics amendment for
online data collection **in parallel with step 1** — it is usually the long pole.

---

## 6. What this arm cannot give you

- **No narration.** The think-aloud pipeline (`docs/NARRATION.md`, `scripts/narration_pipeline.py`)
  depends on screen + mic recording that only exists in the lab. The online arm produces the event
  log and the surveys, nothing else. That is an argument for running **both** arms — lab for depth
  on a handful of participants, online for n — not for replacing one with the other.
- **No researcher clarification**, so anything ambiguous in the tutorial becomes noise rather than a
  question. The pilot exists to find those.
- **A different display condition** (§2.1). Log it, model it, do not pool it silently.
