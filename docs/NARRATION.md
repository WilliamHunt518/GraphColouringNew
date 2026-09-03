# Narration: turning session recordings into data

`scripts\record-screens.bat` captures the screens and the microphone while a participant works
(see [`RECORDING.md`](RECORDING.md)). This document is about what to do with that afterwards:
line the narration up against the event log so you can read **what a participant said while they
were making a specific decision**.

> **Status: skeleton.** The logic is written and unit-tested; the parts that touch a real video
> have never seen one. Every default here — the timer box above all — is a considered guess.
> Expect to tune. The [Tuning](#tuning-once-you-have-a-real-recording) section is the checklist.

---

## Why bother

The build runs both assistants at ε = 0 permanently ([`STUDY_BUILD.md`](STUDY_BUILD.md) § 15), so
the study cannot ask "do operators notice bad advice". What it can ask is **on what grounds do
operators accept or refuse correct advice, and does that differ between the two tiers** — and that
question is answered by what people say, not by what they click.

There is also a specific hole the logs cannot fill. `STUDY_BUILD.md` § 14 says it outright: the
Manual-versus-card split is "unidentifiable between low reliance and a rational response to an
incoherent display". A sentence of narration identifies it.

And the arithmetic favours it. A correlation between AI attitude and tier preference needs roughly
85 participants to be worth reading; *what one participant says while refusing a strategy card* is
informative at n = 1.

---

## The three clocks

Everything in the pipeline is a conversion between these. Getting them confused is the single
biggest risk to the analysis, so they have distinct names in the code.

| Clock | Symbol | Where it comes from | Used by |
|---|---|---|---|
| **Video time** | `v` | seconds from the recording's first frame | Whisper timestamps, OpenCV frame seeks |
| **Session time** | `e` | seconds since the session started | every event's `elapsed`; `timestamp` is the same thing in ms |
| **Wall clock** | — | ISO-8601 UTC | every event's `wallClock`; the recorder's filename (local time) |

The pipeline works in **session time**, because that is the axis the logs already use and the axis
a reader thinks in — *"what did they say four seconds before they clicked Aggressive?"*

### Why alignment reads the on-screen timer

The obvious anchor is the recorder's filename, `sar_demo_20260622_123050.mp4`
(`record-screens.ps1:96`). It is the weaker choice for three reasons, in increasing order of
importance:

1. It is written when the PowerShell script starts, not when ffmpeg's first frame lands.
2. One-second granularity, in local time, against UTC event stamps.
3. **It cannot see a stall.** `MAX_TICK_GAP_MS` in `gameReducer.ts` deliberately *pauses*
   simulated time when the primary window loses visibility — a genuine pause, not a catch-up. The
   video keeps rolling through it. So a wall-clock alignment drifts by exactly the length of the
   stall, in exactly the sessions where something unusual happened.

The session countdown in the header (`8:00` → `0:00`) is ground truth for the axis the logs use.
It is large, monospace, fixed in place and high contrast, which makes it about the friendliest OCR
target available. So: sample frames, read the clock, fit `e = v − offset`.

The fit **fixes the slope at 1** and takes the median offset. Both clocks are real time, so a
fitted slope away from 1 could only be OCR error or a stall smeared across the whole session — a
two-parameter fit would hide the one failure we most want to see. `find_stalls()` reports plateaus
separately, and `Alignment.ok` goes false when the residuals say the single-offset model does not
hold.

---

## Install

Nothing is needed to run `probe`, `join`, or the tests. The rest:

```bash
pip install faster-whisper                 # transcription with word timestamps
pip install opencv-python pytesseract      # timer OCR
winget install UB-Mannheim.TesseractOCR    # the OCR engine itself, + a NEW terminal for PATH
pip install pyannote.audio                 # optional: separate participant from researcher
```

`ffmpeg` must be on PATH already (it is, for the recorder). A CUDA build of torch makes
transcription roughly an order of magnitude faster; without one, use `--model distil-large-v3`.

---

## Run it

```bash
# 0. once per recording rig: find the timer box
python scripts/narration_pipeline.py --participant P-1234 --session 1 \
    probe --video "C:\Users\Work\Videos\sar_demo_20260903_141530.mp4"

# 1..4. the whole thing
python scripts/narration_pipeline.py --participant P-1234 --session 1 all \
    --video "C:\Users\Work\Videos\sar_demo_20260903_141530.mp4" \
    --log   "logs/Study_v1.8/study_P-1234_none_42.json" \
    --roi 0.35,0.0,0.10,0.045 \
    --diarize --hf-token hf_xxx \
    --redact "Firstname" "Surname" "Will"
```

Steps also run individually (`audio`, `transcribe`, `align`, `join`) — during tuning you will
mostly re-run `align` and `join`, which are the cheap ones. Output lands in
`logs/narration/<participant>_s<session>/`:

| File | What it is |
|---|---|
| `audio.wav` | 16 kHz mono, ~100× smaller than the MP4 |
| `transcript.raw.json` | Whisper segments and words, in **video** time |
| `alignment.json` | the fitted offset, every OCR read, and any stalls found |
| `utterances.jsonl` | merged utterances in **session** time, redacted |
| `windows.json` | one entry per operator decision, with its narration attached |

### What a decision window is

`decision_windows()` pairs each opener with its closer, per mission:

| Kind | Opens | Closes |
|---|---|---|
| `strategic` | `strategic_modal_opened` | `strategic_choice` · `strategic_dismissed` |
| `tactical` | `tactical_opened` | `tactical_confirmed` |
| `recovery` | `recovery_opened` | `failure_recovery` · `mission_abandoned` |

Each window carries the fields that make the narration interpretable — for a strategic window,
the two cards as shown and the `choiceType`; for a tactical one, `suggestUsedCount` and
`modifiedFromAgentPlan`; for a recovery, which drone died and whether the agent's fix was used.

A window that never closed (session ended mid-decision) is **kept and clipped**, flagged
`closed: false`. Those are often the most interesting ones, and dropping them would bias the
sample toward decisions people found easy.

Windows can overlap — a recovery opens while a tactical plan is being built — so one utterance can
belong to two. That is a real property of the task, not double counting; `windowIds` on each
utterance records it.

---

## Tuning, once you have a real recording

Work down this list. Each step has something specific to look at.

**1 · The timer ROI is the first thing that will be wrong.** The recording is *all monitors side
by side*, so where the header lands depends on monitor count, order and resolution. `probe` writes
frames; open one, measure the box around `7:59`, divide by frame size, pass as `--roi X,Y,W,H`.
The `align` step prints how many frames gave a usable clock — if that is 0 it also prints the raw
OCR strings, which usually makes the problem obvious (a slice of the map, or the score).

**2 · Check `alignment.json` before believing any transcript.** Look at `residualMax` (should be
well under a second) and `stalls` (should be empty). If `ok` is false, watch a few seconds of
video at a known event time before going further.

**3 · Sanity-check the alignment against something visible.** Take a `strategic_modal_opened`
event, convert with `Alignment.to_video()`, and scrub there. The panel should be appearing. This
one check is worth more than any amount of residual arithmetic.

**4 · Then tune the windows.** `--pre-roll` (default 5 s) catches the reaction to the panel
appearing; `--post-roll` (default 3 s) catches the far more common case of someone explaining a
choice just *after* clicking. Both are guesses. Listen to a few decisions and adjust — and once
set, keep them fixed across participants.

**5 · Check the vocabulary.** `glossary()` in `narration_core.py` primes Whisper with drone ids
and UI terms. Drone ids are exactly what links an utterance to a task, and Whisper mangles
`Lifter-7` into "lift a seven" without help. If the transcripts still garble them, extend the
glossary — and mirror any change to the display names in `missionGen.ts`.

**6 · Diarize if you spoke.** You are in the room, and a researcher prompt can *cause* an
utterance. Keep both speakers: code only the participant, but keep your prompts as context, or
prompted answers will read as spontaneous thoughts.

**7 · Sanity-check the yield.** `join` prints how many decisions ended up with no narration. More
than half silent means either the participant went quiet or the alignment is wrong — and it is
usually the alignment.

---

## What this deliberately does not do yet

- **No coding scheme.** The obvious next step is deductive coding — trust expression,
  verification, workload, confusion, strategy rationale — with an LLM first pass and human
  adjudication on a sample, reporting κ. That turns narration into variables that join to the
  behavioural measures in `agent_scenario_aggregate.py`. It needs a codebook grounded in real
  transcripts, so it waits for real transcripts.
- **No report integration.** `windows.json` is shaped to become a "decision cards" section in
  `docs/reports/two-tiers-two-scenarios.html` — each card being the event, the two strategy cards
  as shown, and what they said. One rendering pass once the data exists.
- **No video analysis.** The cursor is recorded and could show which window had attention and
  whether a card was read or clicked through (cross-checking `strategic_card_previewed` latency).
  Automating that is a project of its own; use the video for targeted spot-checks first.

## Speech measures

`speech_measures()` returns words/min, pause share and disfluencies per 100 words per window,
because they cost nothing once word timings exist and you have a per-session NASA-TLX to validate
them against. Treat them as proxies: **a pause is concentration or overload, and timing alone
cannot tell you which.** `disfluencyPer100` is `null` when there are no word timings to judge from
— that means "not measurable", not "none found".

## Handling and ethics

Ethics approval is in place for recording. Two practical consequences the pipeline assumes:

- **Everything runs locally.** faster-whisper and pyannote are on-device; nothing is uploaded. If
  you ever swap in a hosted API, that is a change of data-handling, not an implementation detail.
- **Nothing generated here is committed.** `logs/narration/` is in `.gitignore` — audio,
  transcripts and per-decision narration are identifiable (a voice, a screen, a named person).
  Regenerate them; never commit them. `--redact` takes names to strip (pass the participant's, and
  your own — they will say it), and also removes emails and phone numbers. It is a crude first
  pass over a transcript a human still reads, not a guarantee.

## Reactivity

Thinking aloud changes behaviour. Concurrent verbalisation of what someone is already attending to
is broadly non-reactive; asking for *explanations* is not, and shifts both strategy and time on
task. Standardise the instruction across participants, record what it was, and if some participants
narrated and others did not, do not pool them.

## Files

| File | Role |
|---|---|
| `scripts/narration_core.py` | clocks, alignment, windows, utterances, redaction. **Standard library only** |
| `scripts/narration_pipeline.py` | CLI over ffmpeg / faster-whisper / OpenCV. Heavy imports are lazy, so `--help`, `probe` and `join` work with nothing installed |
| `scripts/test_narration.py` | pins the core against synthetic data — runs today, without a video |

```bash
python scripts/test_narration.py
```
