# Narration: turning session recordings into data

`scripts\record-screens.bat` captures the screens and the microphone while a participant works
(see [`RECORDING.md`](RECORDING.md)). This document is about what to do with that afterwards:
line the narration up against the event log so you can read **what a participant said while they
were making a specific decision**.

> **Status: skeleton, now run once against a real recording, with a first coding pass and clips.**
> The logic is written and unit-tested; as of 2026-09-10 the full chain has been run end-to-end
> against `Results/Recordings/P05.mp4` / `Results/Participants/P05.json` session 1 —
> `probe` → `align` → `transcribe` → `join` → hand-coded (`codes.json`) → `clips` — producing 13
> coded decisions, each with a curated quote, reason/trust tags, and a synced video clip, plus an
> aggregate **Findings** section in `Results/Narration/decision-cards.html`. The other 4 recordings
> (`P03`, `P04`, `P01`, `P02`) have not been run yet and may use a different recording
> rig (monitor layout), so **do not assume the ROI below carries over** — re-probe each one.
> Speaker identification (`speakerid`) is built, was run against a *confirmed-correct* reference
> clip, and does not work yet — it mislabelled P05's own clear narration as the researcher. The
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

### The environment that actually works on the study machine (2026-09-28)

Getting faster-whisper onto the GPU here took three dead ends, so the working recipe is written
down rather than rediscovered. It lives in its own venv, **outside the repo**, at
`C:\Users\Work\.venvs\narration`:

```bash
# built from a standalone python.org 3.12 -- NOT the system 3.14 and NOT anaconda's 3.11
"$LOCALAPPDATA/Programs/Python/Python312/python.exe" -m venv ~/.venvs/narration
~/.venvs/narration/Scripts/python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu128
~/.venvs/narration/Scripts/python.exe -m pip install faster-whisper
```

The three things that do not work, and why:

1. **The machine's default Python is 3.14** -- neither torch nor a usable ctranslate2 has wheels
   for it. Anything here has to run on 3.12 or older.
2. **A venv built from anaconda's 3.11 cannot load torch at all** -- `OSError: [WinError 1114] ...
   Error loading "torch\lib\c10.dll"`, regardless of what is on PATH. A venv from a standalone
   python.org install loads the identical wheel fine. Don't try to debug the conda one; rebuild.
3. **CTranslate2 on CUDA segfaults with no message unless torch is imported first.** It finds no
   cuDNN/cuBLAS of its own on Windows, and a missing dependent DLL kills the process outright
   rather than raising. `cmd_transcribe` now does an unconditional best-effort `import torch`
   before `from faster_whisper import WhisperModel` for exactly this reason -- **do not remove
   it**; the failure it prevents is silent. (Installing `nvidia-cudnn-cu12`/`nvidia-cublas-cu12`
   alongside instead does *not* fix it, and conflicts with torch's own copies.)

The card is an **RTX 5070 (Blackwell, sm_120)**, which is why torch has to be a cu128 build --
anything older has no kernels for it. Measured throughput on that card, `large-v3` / `float16` /
`beam_size 5`: **15-50x realtime** (it varies with how much of the sitting is silence, which the
VAD filter skips). The whole corpus of ~33 sittings is well under an hour, not the multi-day job a
CPU run would be.

### Transcribing the whole study

`scripts/transcribe_batch.py` walks every recording, skips anything already done, and is safe to
stop and restart -- a session counts as done only once its `transcript.raw.json` exists:

```bash
python scripts/transcribe_batch.py --list       # what is outstanding
python scripts/transcribe_batch.py --limit 4    # the next four sittings
python scripts/transcribe_batch.py              # the lot
```

It finds the venv above automatically (`--python` overrides). Its unit is the **recording**, not
the session, because one recording is one participant's whole sitting: it extracts audio to
`<pid>_s1/` and transcribes once, rather than transcribing the same speech again for `_s2`. Where
an `_s2/` directory already holds a hand-trimmed `audio.wav`, that clip is picked up as well.

**`Results/Recordings/P02.mp4` cannot be read at all** -- `moov atom not found`: the recorder was
killed before ffmpeg finalised the container, so the file has frames but no index. ffmpeg refuses
it outright and the batch skips it with a FAILED line. P02 has an interview transcript
(`Results/Interviews/P02.docx`), so the sitting is not a total loss, but there is no narration
audio for it and there will not be without an untruncation tool.

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
`Results/Narration/<participant>_s<session>/`:

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

> **From the `P05.mp4` run:** the default ROI (tuned for a fullscreen kiosk with no browser
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
`join` already respects that field, so nothing else changes. Effort-coding tools (the P05
`codes.json`) can then exclude `researcher` segments from being read as the participant's own
reasoning, instead of relying on a human eyeballing content for tone, as was done by hand there.

> **Status: built, tried once with a confirmed-correct reference clip, and it doesn't work yet.**
> Not "no reference clip" — a real one. The researcher (Will) confirmed on 2026-09-10 that
> `Results/Narration/P05_s1/candidate_A_setup-chat.mp4` is entirely his own voice. Run against it,
> `speakerid` labelled 80/98 segments "researcher" against only 13 "participant" — including
> P05's own unambiguous first-person narration ("The first one, I'm going to deploy these
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
before trusting it**: re-run against `candidate_A_setup-chat.mp4` and check that P05's own
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
`Results/Narration/<pid>_s<n>/clips/<window-id-with-underscores>.mp4` (`:` is illegal in a Windows
filename). `scripts/build_narration_report.py` picks up any clip it finds next to a coded window
and embeds it as a native `<video>` player on that card automatically — re-run it after cutting
clips. Clip generation needs `align`'s alignment to be trustworthy (`ok: true` in
`alignment.json`); a clip cut from a bad alignment will show the wrong moment, so this is a
**"probably not always"** feature, exactly as bad an idea to trust blindly as any other alignment
output — same file, same rule.

---

## Segmenting a sitting into its phases

A recording is not one thing. It is the intake forms, two worked sessions, two post-session
surveys, the between screen, and the debrief -- and a sentence means something different in each.
`scripts/narration_segments.py` splits the transcript accordingly:

```bash
python scripts/narration_segments.py --list
python scripts/narration_segments.py --participants P36 P30
python scripts/narration_segments.py                     # everyone with a transcript
```

Output lands beside the transcript in `Results/Narration/<pid>_s1/`: `segments.json` (boundaries,
anchor provenance, per-phase word counts) and `segments/NN_kind.txt` / `.jsonl` (that phase's
speech, timestamped; `.txt` is for reading, `.jsonl` keeps word timings for tooling). Same ethics
rule as everything else in that tree -- gitignored, never committed.

**The boundaries are not estimated.** Every phase change is already in the event log as a
`phase_change` with an exact `wallClock` (`demographics → playing → survey → between → playing →
survey → done`, identical across all 30 sittings), so the only unknown is the wall-clock time of
video frame 0. That comes from an existing `alignment.json` where one exists, otherwise from file
mtime minus duration, corrected by `MTIME_STARTUP_LATENCY` and good to about ±2 s. Fine for
cutting phase blocks; **not** fine for placing an utterance inside a single decision window --
that still needs a proper per-session `align`.

> **An `alignment.json` reading `ok: false` with a huge `residualMax` is usually not a failure.**
> One recording contains both sessions, so the timer-OCR reads form two valid clusters ~631 s
> apart and the single-offset fit rightly refuses to average them; the "stall" it reports is the
> session boundary. The reads themselves are good. `_ocr_anchor` clusters them and takes the
> earliest. This is the same "no `--start`/`--end` flag" limitation noted in the Tuning section,
> seen from the other end.

### Where the debrief actually is

The semi-structured debrief is the richest part of most sittings, and it is **not always in the
`interview` phase**. For four participants (`P03`, `P19`, `P21`, `P27`) the recording stopped at
`done` and the debrief happened while the final survey was still on screen -- so it sits in
`survey2`, which for them runs 6-9 minutes instead of the usual 1-2. For four early participants
(`P05`, `P06`, `P07`, `P12`) it is not in the audio at all and only exists as
`Results/Interviews/<pid>.docx`. Every sitting is accounted for by one of those three routes; a
long `survey2` next to a near-empty `interview` is the signature of the second.

More generally, **people start volunteering opinions during the post-session surveys**, well
before the debrief proper. `survey1` + `survey2` hold ~18k words across the corpus. Do not treat
the survey phases as dead air.

### Corpus shape (30 participants, all phases)

| Phase | Words | What it is good for |
|---|---:|---|
| intake | 6,783 | mostly form-filling; occasional unprompted first impressions |
| session 1 | 21,136 | concurrent think-aloud + researcher exchanges — the decision-level data |
| survey 1 | 10,444 | first reflective opinions, immediately post-task |
| between | 3,481 | short; sometimes a candid aside |
| session 2 | 14,711 | as session 1, other scenario (quieter — people narrate less second time) |
| survey 2 | 7,615 | as survey 1, plus the four debriefs that landed here |
| interview | 24,358 | the debrief: the largest single block in the corpus |

`P05` is the one incomplete case: its `audio.wav` was trimmed to session 1 alone for the original
pilot run, so its later phases read as empty. Do **not** fix that by re-transcribing over
`P05_s1/` -- the hand-coded `codes.json` and `windows.json` there are pinned to that transcript.
Transcribe the full `P05.mp4` into a separate directory instead.

### Name redaction is off by default, on purpose

`--redact` takes names and `redact()` matches them case-insensitively and whole-word. The
researcher's name is "Will", so defaulting it on rewrote "I will say" to "I [name] say" 217 times
across the corpus before it was caught. A redaction that corrupts the sentence is worse than none
in a tree that never leaves the machine and is read by the person whose name it would remove.
Pass `--redact` deliberately; `AMBIGUOUS_NAMES` warns for names that are also ordinary words.

### The consulted expert

`P36`, the final participant, is a serving military officer -- the only one with real domain
expertise in the task the scenario simulates. Their sitting is also the richest in the corpus by a
wide margin (4,307 words of debrief, ~3.5× the next). `CONSULTED_EXPERTS` in
`narration_segments.py` flags this and it is carried into `segments.json` as `consultedExpert`, so
the pooled-versus-separate decision is available to make rather than buried. Nothing in the
analysis acts on it yet.

## Mining the debriefs

`scripts/narration_quotes.py` has two deterministic commands with the judgement deliberately left
visible between them:

```bash
python scripts/narration_quotes.py themes                        # the coding frame
python scripts/narration_quotes.py assemble                      # gather each debrief to read
#   ... a human or an LLM reads debrief.txt and writes quotes.json ...
python scripts/narration_quotes.py render                        # cross-linked quote bank
```

`assemble` writes `Results/Narration/<pid>_s1/debrief.txt`, pulling from `interview` plus `survey2`
where the debrief landed there -- detected by duration and word count, not a hardcoded list, so a
re-segment cannot silently drop one. 26 of 30 sittings have a debrief in audio; the other four are
`Results/Interviews/*.docx` and are reported as such rather than appearing silent.

`render` reads every `quotes.json` and writes `Results/Narration/_quotes/`: one file per theme
(every quote on that topic, across participants) and one per participant (their whole stance,
theme by theme), cross-linked, keyed by a quote id of `<pid>/<theme>/<video seconds>` so any quote
can be found in the video or cut with the `clips` step.

**The extraction in the middle is not automated and should not be.** It is the same shape as the
P05 `codes.json` pass: single-coder, uncalibrated, no κ. `quotes.json` records the coder and an
`attributionNote`, which matters more than usual here because **speaker labels do not exist** --
`speakerid` is still broken (see above), so participant and researcher are separated by content.
Where the researcher offered a formulation and the participant only assented, the participant's own
wording is quoted and the assent recorded in the note; a debrief that happened over the survey is
especially interleaved and needs the surrounding turns checked.

The themes are grounded in the questions actually asked, recovered from the recordings rather than
invented: "how did you find that", "what about the two different agents", "what about the two
scenarios", "did that develop at all", "how do you feel about AI tools generally", plus the topics
participants raised unprompted often enough to need a home.

### What the coding produced

All 26 audio debriefs are coded: **141 quotes, 26 participants, 10 themes**. Four things run
through them, each of which changes how the click logs should be read.

**1 · Tier preference looks like a strategy choice, not a trust disposition.** P10 and P21
independently identify the same structural fact — redundancy can come free from the *shape* of a
plan — and draw opposite conclusions. P10 commits generously at the strategic tier, which collapses
the tactical problem to one sensible plan, then delegates it: *"there is really only one way of
assigning them, which means if I just hit the suggest button, then I can focus on something
else."* P21 commits leanly and hand-chains for failure tolerance: *"I was adding the contingency
plans from the start, which didn't require that intervention."* P03 states the coupling as a
general property: *"if you have a good strategy then it's likely less to fail, because you've
already constrained everything."* Same insight, opposite tier delegated.

**2 · "Manual" is at least four different acts, and the logs cannot tell them apart.**
Interpolating between the only two cards offered (P17: *"I wanted it to be somewhere between those
two levels"*; also P22, P28); avoiding the strategic card's reveal delay on a mission simple enough
to beat it (P29: *"it was faster for me to just click manual"*); deliberately benchmarking the
agent (P29: *"doing a few manual ones myself to see whether it would be better"*); and editing the
card as a first draft (P19: *"you can fix bad, you can't fix nothing — it gives you that seed"*;
also P04, P30, P31). Only the last of these is even visible, and only as its opposite. Two of the
four are *evidence of engagement with the agent*, scored as rejection of it.

**3 · Reliance and believed reliability come apart, repeatedly and explicitly.** P28: *"I think
it's less reliable than before, but I still use its suggestion [...] because at least it saves
time."* P35: *"I will rely more on AI — whether it gave me the right answer or not."* P24: *"Did
you feel you had time to check the plan? No. I don't have time to hesitate. But did you trust it?
Yeah."* P11 puts it as arithmetic: *"even if the tactical agent gave me a dodgy suggestion and the
mission failed, I probably would have gained more points from the time saved running another
mission."* A measure that reads following the recommendation as trust inverts all four.

**4 · Three structural explanations for tier asymmetry, none of which is trust.** Verification cost
(P14 and P22, below); decision type — P30: *"[strategic] needs a bit more of a human element,
because obviously it's unpredictable [...] but when it's already there, it's: okay, this is what
you have, optimise it within your resources"*; and agreement-with-self as the calibration rule —
P32: *"the tactical one seemed to be doing what I was doing, quite reliably, and obviously the
strategic one wasn't."* That last one is corrosive: the strategic tier is *designed* to commit
redundancy no operator would choose, so under P32's rule it cannot pass, whether or not it is
right.

### Verification cost is asymmetric between the tiers, and two participants explain why

P14 gives a purely display-based account of why he scrutinised the tiers differently: *"the way
strategic plans were presented — the quantifiable stats like reserve, resilience, speed — I could
just make a decision in one glance. But in the tactical interface, I had to hover over every drone,
look at the trajectory [...] and then deploy if it was fine."* P22 reaches the identical mechanism
and draws the opposite behavioural conclusion: *"I can't accurately assess and then come up with a
better solution [...] whereas in the strategic view I felt like I could very quickly assess [...]
it's a smaller task space, whereas the tactical view is much more complex."* P14 pays the cost and
checks harder; P22 refuses to pay it and defers.

Two participants converging on the mechanism while diverging on the response is stronger evidence
for it than either alone. **Any tier effect in the reliance data has to be defended against this
explanation**, and it is testable — `strategic_card_previewed` dwell against tactical confirm
latency.

### Two recurring misreadings worth tracking as covariates

- **Failure attribution.** The drone-failure hazard is a flat per-drone-second rate, entirely
  independent of both assistants. P03 and P19 separate it cleanly and explicitly exonerate the
  agent (P19: *"I think those were my failures, though, if I'm being honest with you"*); P25 and
  P18 cannot tell (P25: *"I'm not sure if it's just depends on the tasks, or it just depends on the
  AI assistant"*). Whether an operator can attribute a loss correctly looks like a strong moderator
  of measured trust, and no current instrument captures it.
- **Structure inferred from an i.i.d. process.** P19 and P01 both report failures clustering by
  location or task type, and P19 built a (never-executed) strategy on it: *"the environment is
  particularly hostile to those drones."* There is no such variation.

### Error detection is gated on spare capacity

P15, P17, P33 and P35 all say, independently, that they only noticed the strategic tier's problems
in the session where they had slack. P15: *"in the second round I have more experience [...] now I
can check [...] in the first round, maybe I'm not so familiar, so I haven't checked."* P33: *"in
the first test, I don't have enough time to [notice] it."* P35: *"it's easier to find it out. But
when there are too many tasks in a mission [...] I don't have time to check it."*

Since the agents made **no errors at all**, a declining trust trajectory can be produced entirely
by growing operator competence at noticing what was always there. Any trust-over-time result needs
to contend with this.

## Finding: the Conservative card commits drones the mission does not need

P21, in debrief: *"it was giving me the wrong type of drones. It required only blue drones and kept
giving me red and green ones. So I didn't like that one."* He ran with `agentFailuresEnabled=false`
and both epsilons at 0, so no injected failure was possible, and the first reading was that he had
misread a correct card. **He had not** — and he is one of five.

**Sighting accounting, once all 26 debriefs were coded.** Five participants describe the defect
unprompted and in specific terms — **P13, P17, P20, P21, P35**:

- P13: *"in conservative, you don't need camera or lifters, yet it adds it as reserve — even for
  tasks it doesn't do. That doesn't make sense. It sends redundancy for nothing."*
- P17: *"the type of error is redundant allocation. I have never seen underrepresented"* —
  correctly characterising the direction, which is exactly right: an ungated top-up can only add.
- P20: *"it required all fast drones, and the assistant recommended I add some red and green."*
- P35: *"the mission don't need the blue one, and it suggests me to allocate two or three blue ones."*

A sixth (**P33**) confirms it once the researcher names it, so it is coded as a led confirmation.
Two more (**P01**, **P19**) report over-allocation in terms too ambiguous to code as this defect,
and three (**P28**, **P36**, plus P13 again) complain about strategic over-commitment generally.
It is by a wide margin the most-reported single issue in the corpus.

`copilot.ts:266-268` builds the Conservative pool as

```
consBase[c] + floor((reserve[c] - consBase[c]) * CONSERVATIVE_TOP_UP)
            + (consBase[c] > 0 ? CONSERVATIVE_REDUNDANCY_BUFFER : 0)
```

The `+1` buffer is correctly gated on the colour actually being used by the mission, and the
comment beside it says so. **The 15% top-up is not gated at all.** On an all-Blue mission with 11
Red in reserve, `floor(11 × 0.15) = 1` Red drone is committed to a mission with no use for it.
Aggressive has no equivalent term and never does this.

Reproduce with `scripts/check_conservative_topup.py`.

| | |
|---|---|
| Conservative cards carrying a needless colour | **144 of 725 (19.9%)** |
| Aggressive cards doing the same | 0 of 692 |
| Participants who saw at least one | 33 of 34 |
| Prevalence in **Strategic Heavy** | **29.9%** (131/438) |
| Prevalence in **Tactical Heavy** | **4.5%** (13/287) |

### But it does not measurably change behaviour, and an earlier claim here was wrong

**Correction (2026-09-30).** An earlier version of this section reported that Conservative uptake
fell 35.0% → 24.2% on affected cards, a 14.6 pp within-participant drop at *p* = .008, and that
roughly 40% of the scenario effect on strategic reliance rested on it. **That contrast is
confounded and the conclusion does not survive.**

An odd card requires the mission to leave a colour unused, so it is **structurally impossible on a
three-colour mission** — 0 of 431 in this cohort. "Odd" is nested inside "simple", and simple
missions are exactly where operators build the allocation themselves anyway. The naive odd-versus-
clean contrast is a simple-versus-complex contrast wearing a disguise.

Within the only stratum where it is identified — few-colour missions, *n* = 196 — the effect is
54.7% versus 50.8% uptake, and adjusted for scenario, run and position: **b = −0.29, *p* = .40.**

And it absorbs completely into mission composition (GEE, binomial, clustered on participant;
scenario coefficient is Tactical Heavy vs Strategic Heavy):

| Model | Scenario | Odd card |
|---|---|---|
| unadjusted | b = +0.72, *p* < .001 | — |
| + odd-card flag | b = +0.50, *p* = .009 | b = −0.64, *p* = .009 |
| + mission composition | b = +0.27, *p* = .13 | b = −0.03, *p* = .93 |

The variable doing the work is **how many colours the mission needs** (b = +0.30, *p* = .007):
operators take the card on complex missions and build simple ones themselves. Both the scenario
effect and the odd-card effect are shadows of that.

### No trust carry-over — and the qualitative data says otherwise

Three independent tests, all null:

| Test | Result |
|---|---|
| Already seen one this session → uptake on later decisions | b = +0.29, *p* = .30 |
| Uptake on the very next decision (66.4% → 63.0%) | b = +0.07, *p* = .77 |
| Post-session `trust_strategic` vs odd cards seen | ρ = −0.07, *p* = .57 (66 sessions) |

Operators answer the card in front of them and do not generalise. What the odd card *does* do is
local and large: on that decision Manual jumps from 30.9% to 49.2%, and **both** cards lose roughly
equally (Aggressive 34.1 → 26.5, Conservative 34.9 → 24.2) — it pushes people out of the card
system altogether rather than across to the other card.

**This is a real dissociation, and it is a finding rather than a nuisance.** P20 states plainly
that his trust in the strategic tier dropped after seeing one and that the tactical tier was
unaffected — *"after that point I started [dis]trusting the strategic assistant. But I didn't
notice any similar errors on the tactical."* His behaviour, and the cohort's, shows no such shift:
not on the next decision, not later in the session, not on the trust scale he filled in minutes
afterwards. Self-reported trust damage that leaves no behavioural trace is exactly the kind of
thing a study with both streams is for.

The behaviour was not unknown to the code:  `generateStrategies`' epsilon comment mentions "a lone
Green sitting on an all-Blue mission" as something not worth corrupting. What was never considered
is how that card *reads* to an operator.

> **Ruled 2026-09-30: `copilot.ts` stays as it is.** Recruitment closed at 34 participants with
> this behaviour in place, so changing it would split the cohort on the study's core measure for no
> analytic gain — and it is arguably not a defect at all but the honest consequence of a
> deliberately simple, myopic rule. A `KNOWN BEHAVIOUR` note sits above `CONSERVATIVE_TOP_UP` in
> `copilot.ts` saying what to change, and to re-tag and not pool, **if this build is ever adapted
> or rerun.** Analysis reports it as prevalence and as a local effect on the affected decision; it
> is not used as a covariate, because it is collinear with mission composition and adds nothing
> once that is in the model.

## Finding: the reveal delay is the study's best instrument, not a nuisance

Both tiers carry a deliberate simulated delay, with different cost structures:

| | Delay | Scales with |
|---|---|---|
| Strategic card reveal | flat **4.0–5.0 s** (`CARD_REVEAL_MIN_MS`/`SPAN_MS`, median 4.3 s over 1423 cards) | nothing |
| Tactical Suggest | **2 s per drone**, progressive (`MapDisplay.tsx:966`) | mission size |

Median tactical Suggest is about **14 s**, p90 **22 s**, max **38 s**, and worse in Tactical Heavy
(16 s vs 12 s). The researcher confirms to P27 on the record that this is theatre: *"it solves its
problem instantly, and then it goes through the pretend adding one by one, because it's a fake
tool."* Four participants complain about it (P15, P26, P27, P29).

**Ruled 2026-09-30: this is part of the problem, and it stays.** It also turns out to be the most
useful single instrument in the build.

### What it buys: `manualBeforeCardsLoaded`

Manual entry is available immediately; the cards are not. `strategic_choice` therefore logs whether
the operator committed to building the allocation themselves **before the recommendation existed on
screen** — and reproduced by `scripts/manual_choice_analysis.py`:

| | Manual choices made before the cards loaded |
|---|---|
| Overall | **45.6%** (98/215 where the flag is logged) |
| One-colour missions | **57.3%** |
| Three-colour missions | 35.5% |

**Nearly half of all Manual choices are not rejections of the advice — the advice had not been
given yet.** On the simplest missions it is a clear majority. Any reliance measure that reads
Manual as "declined the recommendation" is measuring something that did not happen in those cases,
and without this delay the two would be indistinguishable.

The delay is also randomly drawn per mission and independent of mission content, which makes it a
natural experiment on latency itself: Manual share is 33.7% on shorter-than-median draws against
35.6% on longer, **z = 0.50**. No detectable effect — though the spread is only ~1 s, so this fails
to confirm the effect rather than ruling it out.

### Manual is slower, not faster — a second belief-versus-behaviour gap

P29's account is that on a simple mission he could beat the card: *"it was faster for me to just
click manual."* Decision time from modal opening to choice says otherwise:

| Mission | Manual (median) | Cards (median) |
|---|---|---|
| One colour | 10.5 s | 9.3–10.6 s |
| Three colours | 17.0 s | 10.9–11.2 s |

Adjusted for mission composition, Manual takes **+4.0 s longer** (*p* = .003). It is never the
faster route, even where the cards cost a 4–5 s wait. What P29 is describing is the moment he
*committed*, which the pre-emption data above shows was genuinely early — not the time the
allocation took. Alongside P20's reported-but-invisible trust drop, this is the second case where a
participant's stated reason is contradicted by their own logged behaviour.

### What Manual commits — and why the first answer here was too simple

**Correction (2026-09-30).** An earlier version of this section said Manual buys reserve: about one
drone per decision held back, matching what P22, P24, P28 and P30 describe. The average is right
and the interpretation was not. Manual is used far more on small, low-criticality missions
(category A 43% Manual, category D 26%), so an average over Manual decisions is an average over a
non-random slice of missions. Broken out, **the saving reverses:**

| Mission size | Drones committed vs the Conservative card |
|---|---|
| small (mean need 4.3) | **−1.25** |
| mid (7.2) | −0.67 |
| large (14.0) | **+1.02** |

Mission size drives it (b = +0.35, *p* < .001); criticality has no independent effect once size is
in the model (b = −0.02, *p* = .94 — the two are correlated, category E needs ~15 drones against
category A's ~5). The comparison itself is sound — `deltaVsConservative` is matched on mission by
construction — but **"Manual preserves reserve" is true of small missions and false of large ones.**

What operators are actually doing is adjusting the card in whichever direction they think it is
wrong, and the direction flips with mission size:

| Where the manual allocation sits | Share |
|---|---|
| **between** the two cards | 47.8% |
| **below both** | 44.5% |
| above both | 7.7% |

On large missions 57.1% land between the cards — the interpolation P17, P22 and P28 describe
(*"I wanted it to be somewhere between those two levels"*). On small missions 52.0% land **below
both**, which is trimming, not interpolating.

### On small missions the Conservative card is often dominated

The small-mission row above is the tell: mean Conservative 4.4 drones against Aggressive 4.0.

**Conservative commits more drones than Aggressive in 17.5% of all card pairs — and 35.4% on small
missions** (29.1% on one-colour missions). Conservative is also the slower card by design. So on
those missions it is dominated on every axis the operator can see: more drones, more time, no
visible compensation. Choosing it would be irrational, and operators largely do not — Conservative
uptake falls from 36.6% to 25.9% and Manual rises from 29.5% to 40.7%.

This is the same ungated top-up as the finding above, seen through a sharper lens: it is not just
that an odd colour appears, it is that the card meant to be the cautious option becomes the
expensive one exactly where the mission is small enough for that to be obvious.

**And it behaves the same way under analysis.** Put the domination flag and the stray-colour flag in
one model with mission composition and neither survives — dominated b = +0.24 (*p* = .20), odd
b = −0.14 (*p* = .66), while colours needed holds at b = +0.26 (*p* = .03). Two independent
operationalisations of "the simple rules produced a visibly bad card", the same answer both times:
real, visible, and not what is driving the behaviour. Mission composition is.

### The limitation that remains

Tactical Suggest latency scales with mission size, which *is* the scenario manipulation, and has no
random component to exploit. It cannot be adjusted away and should be stated as a limitation on the
scenario × tier interaction specifically. P20 is the illustration: he ranked strategic above
tactical on time saved, then caught himself — *"there was like a loading stage when it was doing the
strategic part, so maybe that's not right, actually."* Participants' own cross-tier time
comparisons are not reliable, and time saved is the commonest stated reason for delegating in the
whole corpus.

## Finding: two operator affordances are effectively invisible

Surfaced by P27 asking for a queue sort that already exists.

- **`task_reprioritised` was fired by ZERO of 34 participants.** The reorder control (up/down and
  priority within a mission) is in the event table in `CLAUDE.md` and was never once used. Any
  analysis treating it as a manual-control signal has an empty column.
- **The mission-queue sort toggle emits no event at all.** `sortMode` in `PrimaryDisplay.tsx:106`
  flips the queue between arrival order and score order, and lives entirely in React state. So the
  order missions were *presented* in — which directly shapes which mission gets allocated next — is
  unrecoverable from every log in the study. This is a genuine gap and belongs in
  [`EVENT_LOGGING.md`](EVENT_LOGGING.md).

P27 was one of very few to look for the sort at all, and did not find it: *"I'd prefer to put the
task which cannot be done for now to the end of the list."* His fuller proposal — order by
feasibility first, criticality second, with lookahead to drones about to be freed — is the most
specific design request in the corpus, and it asks for help with **which mission to work on next**,
the one decision neither assistant supports. Both tiers act only after that choice is made.

## What this deliberately does not do yet

- **A coding scheme now exists for one session, single-pass, uncalibrated.** P05 session 1 has
  been hand-coded (`Results/Narration/P05_s1/codes.json`) against a small bottom-up codebook —
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
  `scripts/build_narration_report.py` renders every `Results/Narration/*/windows.json` into decision
  cards (the event as shown, the choice made, the narration overlapping it) and writes
  `Results/Narration/decision-cards.html`. It is **not** merged into the committed, pooled,
  de-identified `docs/reports/` output: a decision card embeds verbatim (redacted) participant
  speech, which is identifiable data under the same ethics terms as the audio and transcripts
  above — so its output path is inside the gitignored `Results/Narration/` tree and must never be
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
- **Nothing generated here is committed.** `Results/Narration/` is in `.gitignore` — audio,
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
| `scripts/build_narration_report.py` + `scripts/narration_report_template.html` | render every `Results/Narration/*/windows.json` (+ `codes.json` and `clips/` where present) into `Results/Narration/decision-cards.html` (gitignored — see Handling and ethics above) |

```bash
python scripts/test_narration.py
```
