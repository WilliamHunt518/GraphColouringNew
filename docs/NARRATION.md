# Narration: turning session recordings into data

`scripts\record-screens.bat` captures the screens and the microphone while a participant works
(see [`RECORDING.md`](RECORDING.md)). This document is about what to do with that afterwards:
line the narration up against the event log so you can read **what a participant said while they
were making a specific decision**.

> **Status: skeleton, now run once against a real recording, with a first coding pass and clips.**
> The logic is written and unit-tested; as of 2026-09-10 the full chain has been run end-to-end
> against `Recordings/JackHJ.mp4` / `logs/Study_ver_final/study_JackHJ_none_42.json` session 1 —
> `probe` → `align` → `transcribe` → `join` → hand-coded (`codes.json`) → `clips` — producing 13
> coded decisions, each with a curated quote, reason/trust tags, and a synced video clip, plus an
> aggregate **Findings** section in `logs/narration/decision-cards.html`. The other 4 recordings
> (`AYOMIDE`, `GeorgeH`, `RAMIS`, `SAMHJ`) have not been run yet and may use a different recording
> rig (monitor layout), so **do not assume the ROI below carries over** — re-probe each one.
> Speaker identification (`speakerid`) is built, was run against a *confirmed-correct* reference
> clip, and does not work yet — it mislabelled JackHJ's own clear narration as the researcher. The
> bad output was reverted before anything downstream used it. **Do not run `speakerid` and trust
> its output** until the fix in **Plan: fixing speaker-ID accuracy** (below) is actually done —
> that section exists specifically so this isn't re-discovered the hard way. See the
> [Tuning](#tuning-once-you-have-a-real-recording) section for what changed and what's still a
> guess.

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
pip install pyannote.audio                 # optional: separate speakers, needs an HF token (see below)
pip install resemblyzer soundfile webrtcvad audioread   # optional: `speakerid` — no token needed, see below
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

> **From the `JackHJ.mp4` run:** the default ROI (tuned for a fullscreen kiosk with no browser
> chrome) was wrong on two counts on this rig — the recording shows visible browser chrome (tab
> bar, address bar) above the app, pushing the header down to roughly `y≈0.18` not `y≈0.0`; and
> the timer + score are one right-aligned cluster (`7:58  Score: 429 +540`), so the timer's own
> x-position **drifts left by 100+ px over a session** as the score digit-count grows (measured:
> `x≈1446` at score 0, `x≈1368` at score 1292, out of a 4480px-wide frame). A box wide enough to
> catch the timer at high score will sometimes also catch the leading `:` of "Score:" at low
> score — don't try to out-guess that with a wider box. `parse_clock`'s strict "must look exactly
> like m:ss" check already drops those contaminated reads correctly; a handful of clean samples
> per session is enough for `fit_alignment` (5 samples → `residualMax=0.0, ok=True` here). The ROI
> that worked for this rig: `--roi 0.302,0.178,0.033,0.025`. Re-measure per rig, don't reuse this
> number blindly — see the per-participant note above.
>
> **Also found:** the recorder captures one participant's *entire sitting* — session 1, the
> between-session break, and session 2 — in a single file (confirmed here: the score resets to 0
> exactly where `align`'s stall detector flagged a implausible 638 s gap). `align`/`probe` scan the
> whole file with no way to bound the scan to one session, so aligning session 2 (or a session
> after the first) needs the video trimmed first, e.g. `ffmpeg -i in.mp4 -ss <rough-start>
> -c copy clip.mp4`, or the fit will try to match a later session's countdown against the wrong
> session's log and report bogus stalls. There is no `--start`/`--end` flag for this yet.

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
prompted answers will read as spontaneous thoughts. See **Speaker identification** below for a
no-HuggingFace-token way to do this, since the researcher is the same one person every session.

**7 · Sanity-check the yield.** `join` prints how many decisions ended up with no narration. More
than half silent means either the participant went quiet or the alignment is wrong — and it is
usually the alignment.

---

## Speaker identification (participant vs. researcher)

`--diarize --hf-token` above uses pyannote, which needs a HuggingFace account, accepting the
gated model's terms, and a token — real friction for a two-minute problem. Because the researcher
is **always the same one person** across every session (unlike pyannote's generic unsupervised
clustering, which just gives you "SPEAKER_00"/"SPEAKER_01" with no idea which is which), a single
reference clip of the researcher's voice is reusable across the whole study, and a plain
voice-similarity classifier is enough — no token needed:

```bash
python scripts/narration_pipeline.py --participant P --session N speakerid \
    --ref path/to/researcher-only-clip.wav
python scripts/narration_pipeline.py --participant P --session N join --log ...   # re-attach with speakers labelled
```

This rewrites `transcript.raw.json`'s segments in place with `speaker: "researcher"` or
`"participant"` (voice-similarity, resemblyzer, cosine threshold `--threshold`, default 0.62);
`join` already respects that field, so nothing else changes. Effort-coding tools (the JackHJ
`codes.json`) can then exclude `researcher` segments from being read as the participant's own
reasoning, instead of relying on a human eyeballing content for tone, as was done by hand there.

> **Status: built, tried once with a confirmed-correct reference clip, and it doesn't work yet.**
> Not "no reference clip" — a real one. The researcher (Will) confirmed on 2026-09-10 that
> `logs/narration/JackHJ_s1/candidate_A_setup-chat.mp4` is entirely his own voice. Run against it,
> `speakerid` labelled 80/98 segments "researcher" against only 13 "participant" — including
> JackHJ's own unambiguous first-person narration ("The first one, I'm going to deploy these
> manually...", sim 0.865) as *more* similar to the researcher reference than a genuine
> same-speaker match should be. **The labels were reverted immediately** (segment `speaker`/
> `speakerSim` fields stripped back out of `transcript.raw.json`) before anything downstream —
> `join`'s speaker-based merge boundaries, `codes.json`'s coding — could pick them up and get
> silently corrupted. Do not re-run `speakerid` and trust its output until the accuracy problem
> below is actually fixed; a wrong exclusion is worse than no exclusion. See **Plan** below.

**Why not real `librosa`:** resemblyzer wants it for three calls (`load`, `resample`,
`feature.melspectrogram`), and real librosa pulls in `numba` — which, on this machine's base
Python environment, is already broken against the numpy also installed there ("Numba needs NumPy
1.21 or less"), and was installed by conda (distutils), so pip can't cleanly fix it. Rather than
touch a shared environment's numba/llvmlite/numpy stack for this, `scripts/_librosa_shim.py`
reimplements those three calls on `soundfile` + `torchaudio` (already installed, no numba in its
chain) and registers itself into `sys.modules['librosa']` before resemblyzer is imported. Call
`_librosa_shim.install()` before anything imports `resemblyzer` — `speakerid` already does this.
**This is the prime suspect for the bad result above** — see Plan.

**Getting a reference clip is otherwise straightforward.** A clip guessed from transcript content
alone is not reliable — the first attempt guessed a pre-session "let me explain the demographics
form" stretch was the researcher, and the resulting similarity scores ran backwards from what a
correct reference should produce, meaning that specific guess was wrong. But a *confirmed* clip
(the researcher listens and says "yes that's me") works fine for this part:
`scripts/narration_pipeline.py ... clips` (below) can cut short candidate clips from any
timestamp for a human to check, or the researcher can just record themselves saying a sentence or
two directly. `candidate_A_setup-chat.mp4` proves this half of the problem is solved; the
similarity model itself is what still isn't trustworthy.

## Plan: fixing speaker-ID accuracy (not started)

Not acted on yet — the researcher asked for this to be written down and left for later rather
than pursued further in the same session, given diminishing returns from further guessing at DSP
parameters. Whoever picks this up next:

**Most likely cause:** resemblyzer's pretrained encoder (`voice_encoder.py::VoiceEncoder.forward`)
feeds the mel-spectrogram straight into an LSTM with **no log-compression or normalization step**
— the raw power values go straight in. That makes the model unusually sensitive to the *exact*
numeric scale of the spectrogram, and `_librosa_shim.py`'s `torchaudio`-based
`feature.melspectrogram` almost certainly doesn't reproduce librosa's STFT/mel-filterbank scale
closely enough, even with matching `norm='slaney'`/`mel_scale='slaney'` flags — librosa and
torchaudio differ in window-normalization and other DSP details that a flag-for-flag parameter
match doesn't paper over. A model this sensitive to input scale needs the *actual* library it was
trained against, not a lookalike.

**Option A — isolated venv with real `librosa` (recommended if this is worth fixing properly).**
Create a dedicated virtualenv just for this one step (`python -m venv .venv-speakerid` or similar,
outside the project's tracked files), `pip install librosa resemblyzer` there fresh (a clean venv
has no numba/numpy version conflict to inherit — the conflict here is specific to this machine's
shared conda **base** environment), and either (a) run `speakerid` inside that venv directly, or
(b) keep it invoked from the base env but shell out to the isolated venv's `python` for just the
resemblyzer call. One-time setup, reusable for all 5 recordings and every future one. **Verify
before trusting it**: re-run against `candidate_A_setup-chat.mp4` and check that JackHJ's own
"The first one, I'm going to deploy these manually" segment (session time ~12.4s) comes back
`participant` with a *low* similarity score, not `researcher` with a high one — that's the
concrete regression test this bug leaves behind.

**Option B — keep doing it by hand.** The manual/LLM content-based approach already worked once
(the `tactical:M004:79` researcher-dialogue exclusion in `codes.json`, caught by reading the
transcript, not by a classifier). No new setup, no accuracy risk from a mismatched DSP
implementation, but it costs more reading time per session and depends on the researcher's
speech being contextually distinguishable (questions, second-person address, compliments) —
which won't always be true.

**Not investigated:** whether a *log*-mel spectrogram (rather than raw power) into the shim would
mask the scale-sensitivity problem well enough without a full librosa install — worth a quick try
before committing to Option A, but unverified, so listed here rather than implemented.

## Clips: syncing a quote back to the video

Once a session has run through `align` (so `windows.json` carries a fitted `alignment`), you can
cut a short mp4 (screen + mic) for any decision straight from the source recording:

```bash
python scripts/narration_pipeline.py --participant P --session N clips --video RECORDING.mp4
# or just one:
python scripts/narration_pipeline.py --participant P --session N clips --video RECORDING.mp4 \
    --window-id "strategic:M001:5"
```

Each clip is `[openedAt − pad, closedAt + pad]` (`--pad`, default 2 s), capped at
`--max-duration` (default 25 s) — the decision's own span from the log, not the wider
pre-roll/post-roll window `join` uses for narration capture, so the clip shows the actual UI
action and the speech act around it, not a shared multi-minute ramble. Output lands in
`logs/narration/<pid>_s<n>/clips/<window-id-with-underscores>.mp4` (`:` is illegal in a Windows
filename). `scripts/build_narration_report.py` picks up any clip it finds next to a coded window
and embeds it as a native `<video>` player on that card automatically — re-run it after cutting
clips. Clip generation needs `align`'s alignment to be trustworthy (`ok: true` in
`alignment.json`); a clip cut from a bad alignment will show the wrong moment, so this is a
**"probably not always"** feature, exactly as bad an idea to trust blindly as any other alignment
output — same file, same rule.

---

## What this deliberately does not do yet

- **A coding scheme now exists for one session, single-pass, uncalibrated.** JackHJ session 1 has
  been hand-coded (`logs/narration/JackHJ_s1/codes.json`) against a small bottom-up codebook —
  reason for the choice (`task_load`, `performance_trust`, `mission_criticality`,
  `spare_capacity`, `verification`, `efficiency_anticipation`, `none_stated`) and trust stance
  (`deliberate_manual_control`, `implicit_confidence`, `explicit_trust_increase`) — by a single
  LLM pass (Claude) reading the transcript against each decision's logged outcome, with no second
  coder and no κ. `scripts/build_narration_report.py` aggregates whatever `codes.json` files it
  finds (reason/trust frequency, a reason-vs-actual-choice cross-tab) into a **Findings** section
  at the top of the report; with one participant coded that is a within-session summary, not a
  generalisable finding, and the report says so. Coding a second session, ideally by a different
  coder, to get a real κ is the natural next step before treating any of this as validated. It
  needs a codebook grounded in real transcripts, which is why it waited for one.
- **Report integration exists, but deliberately isn't in `two-tiers-two-scenarios.html`.**
  `scripts/build_narration_report.py` renders every `logs/narration/*/windows.json` into decision
  cards (the event as shown, the choice made, the narration overlapping it) and writes
  `logs/narration/decision-cards.html`. It is **not** merged into the committed, pooled,
  de-identified `docs/reports/` output: a decision card embeds verbatim (redacted) participant
  speech, which is identifiable data under the same ethics terms as the audio and transcripts
  above — so its output path is inside the gitignored `logs/narration/` tree and must never be
  committed, pushed, or pasted into a hosted tool. Re-run it after every new session that goes
  through `join`.
- **No automated video analysis, but manual spot-checking is now one command away.** The `clips`
  step (above) cuts a synced mp4 for any decision on request, and the report embeds one per coded
  card automatically — that covers "let me look at what actually happened here." What's still not
  built: the cursor is recorded and could show which window had attention and whether a card was
  read or clicked through (cross-checking `strategic_card_previewed` latency) *automatically,
  across every window, without a human watching each clip*. That remains a project of its own.

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
| `scripts/narration_pipeline.py` | CLI over ffmpeg / faster-whisper / OpenCV / resemblyzer. Heavy imports are lazy, so `--help`, `probe` and `join` work with nothing installed. Steps: `probe`, `audio`, `transcribe`, `align`, `speakerid`, `join`, `clips`, `all` |
| `scripts/_librosa_shim.py` | reimplements the 3 librosa calls `speakerid` needs, on soundfile/torchaudio, so it doesn't need real librosa's numba dependency. See Speaker identification above |
| `scripts/test_narration.py` | pins the core against synthetic data — runs today, without a video |
| `scripts/build_narration_report.py` + `scripts/narration_report_template.html` | render every `logs/narration/*/windows.json` (+ `codes.json` and `clips/` where present) into `logs/narration/decision-cards.html` (gitignored — see Handling and ethics above) |

```bash
python scripts/test_narration.py
```
