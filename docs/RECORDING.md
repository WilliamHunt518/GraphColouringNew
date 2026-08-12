# Screen + mic recording (`scripts/record-screens.*`)

Records **all monitors side by side, with the cursor, plus the microphone**, into one MP4 in
`%USERPROFILE%\Videos\sar_demo_<timestamp>.mp4`. Used to capture study sessions alongside the
event log — the log's `wallClock` field on every event is what lets a recording be lined up
against the data afterwards.

```bat
scripts\record-screens.bat                 :: auto-detect everything
scripts\record-screens.bat -Mic "HyperX"   :: force a mic by name or substring
scripts\record-screens.bat -Mic none       :: video only
```

Press **`q`** in the recorder window to stop cleanly. Closing the window, Ctrl-C or killing the
process leaves an **unfinalised, unplayable MP4** — verified: a force-killed run leaves a 44-byte
file with no moov atom, even though it was encoding fine a second earlier. Always stop with `q`.

Nothing about the geometry is hard-coded: monitor count, resolution, DPI scaling and taskbar
height are all detected at launch (`record-screens.ps1:20-34`), so a laptop with one screen works
without changes.

---

## This is machine-specific — read this before debugging

The script was developed on the **desktop**, and the study is run on a **laptop**. Two things are
environment-dependent and are the usual cause of "it worked yesterday":

| | Desktop (developed on) | Laptop (study machine) |
|---|---|---|
| Mic | `Microphone (HyperX Cloud Alpha Wireless)` | *whatever is built in / plugged in* |
| GPU encoder | NVENC (RTX 5070) | **may have no NVIDIA GPU** |

The mic is only a *preference*, not a requirement — see below. The encoder is the one that will
hard-fail.

---

## Diagnostics — run these three first

All three are read-only and safe to run at any time.

**1. Is ffmpeg installed and on PATH?**

```powershell
ffmpeg -version
```

If this fails, nothing else will work. Install with `winget install Gyan.FFmpeg`, then **open a new
terminal** (PATH is only picked up by new processes).

**2. What capture devices exist?**

```powershell
cmd /c "ffmpeg -hide_banner -list_devices true -f dshow -i dummy 2>&1" |
  Select-String '\(audio\)|\(video\)'
```

This is the same call the script makes (`record-screens.ps1:37-46`). It prints device names in
quotes; the audio names are what `-Mic` matches against. Example from the desktop:

```
"HD Pro Webcam C920" (video)
"Microphone (HyperX Cloud Alpha Wireless)" (audio)
"Microphone (HD Pro Webcam C920)" (audio)
"Microphone (Sonic Studio Virtual Mixer)" (audio)
```

**3. Which encoders actually work on this machine?**

```powershell
foreach ($enc in @('h264_nvenc','hevc_nvenc','libx264','h264_qsv','h264_amf')) {
  $null = cmd /c "ffmpeg -hide_banner -loglevel error -f lavfi -i testsrc=size=320x240:rate=30 -frames:v 30 -c:v $enc -f null - 2>&1"
  if ($LASTEXITCODE -eq 0) { "OK    $enc" } else { "FAIL  $enc" }
}
```

**Do not use `ffmpeg -encoders` for this.** That lists what the build was *compiled* with, so
`h264_nvenc` appears even on a machine with no NVIDIA GPU and then fails at runtime. Only the probe
above tells you what will actually encode. (On the desktop it reports OK for nvenc/libx264/amf and
FAIL for `h264_qsv`, which is exactly the distinction that matters.)

---

## Failure modes, in the order they're likely

### 1. No NVIDIA GPU on the laptop → recording dies immediately

**Symptom:** ffmpeg exits within a second with `Cannot load nvcuda.dll`, `No capable devices
found`, or `Cannot init CUDA`. No output file, or a 0-byte one.

**Cause:** the encoder is chosen unconditionally as NVENC at `record-screens.ps1:91`:

```powershell
$venc = if ($canvasW -gt 4096) { 'hevc_nvenc' } else { 'h264_nvenc' }
```

**Fix — apply BOTH edits below. They are one change; applying only the first makes things worse,
because the quality flags at line 101 (`-preset p5 -tune hq -rc vbr -cq 23`) are NVENC-only and
make libx264 exit immediately with `-22 / EINVAL`.**

**Edit 1 — replace line 91** (`$venc = if ($canvasW -gt 4096) {...}`) with:

```powershell
# Pick an encoder this machine can actually run, and the quality flags that go with it.
# NVENC h264 tops out at 4096px wide, so a wide multi-monitor canvas needs an HEVC variant.
function Test-Encoder([string]$enc) {
  $null = cmd /c "ffmpeg -hide_banner -loglevel error -f lavfi -i testsrc=size=320x240:rate=30 -frames:v 30 -c:v $enc -f null - 2>&1"
  return ($LASTEXITCODE -eq 0)
}
$candidates = if ($canvasW -gt 4096) { @('hevc_nvenc','hevc_amf','libx264') }
              else                   { @('h264_nvenc','h264_amf','libx264') }
$venc = $candidates | Where-Object { Test-Encoder $_ } | Select-Object -First 1
if (-not $venc) { throw "No usable encoder found - see docs/RECORDING.md" }

# Quality flags are encoder-specific and NOT interchangeable.
$qArgs = if     ($venc -like '*nvenc*') { @('-preset','p5','-tune','hq','-rc','vbr','-cq','23','-b:v','0') }
         elseif ($venc -like '*amf*')   { @('-quality','balanced','-rc','cqp','-qp_i','23','-qp_p','23') }
         else                           { @('-preset','veryfast','-crf','23') }
```

**Edit 2 — replace lines 101-102** (the `$ffArgs += @('-c:v',$venc,'-preset','p5',...)` block) with:

```powershell
$ffArgs += @('-c:v',$venc) + $qArgs + @('-pix_fmt','yuv420p', $out)
```

All five encoder/flag pairings above (`h264_nvenc`, `hevc_nvenc`, `h264_amf`, `hevc_amf`,
`libx264`) were verified to encode successfully. On the desktop this block selects exactly what the
current hard-coded line selects — `h264_nvenc` for a narrow canvas, `hevc_nvenc` for a wide one —
so it is behaviour-preserving there and only changes what happens when NVENC is unavailable.

`h264_qsv` (Intel Quick Sync) is deliberately left out of the candidate list: it needs a third set
of flags (`-global_quality`) and it fails on this desktop. If the laptop has an Intel iGPU and CPU
encoding proves too slow, add it plus its own `$qArgs` branch — but measure first, `libx264
-preset veryfast` handles screen content on a modern laptop CPU without dropping frames.

### 2. Mic not found, or the wrong one is picked

**Symptom:** console prints `Mic: (none - video only)`, or it records the webcam mic / a virtual
mixer instead of the headset.

**Cause:** the auto-pick at `record-screens.ps1:55-63` prefers anything matching `HyperX|Headset`,
then falls back to the first device that is *not* `Virtual|Mixer|Stereo Mix|What U Hear`, then to
the first device at all. On a machine with no HyperX, whichever real mic enumerates first wins.

**Fix — no code change needed.** Run diagnostic 2, then pass a substring:

```bat
scripts\record-screens.bat -Mic "Realtek"
```

If the laptop's mic should be the permanent default, add it to the preference regex at line 56,
e.g. `-match 'HyperX|Headset|Realtek'`. Keep HyperX in the list so the desktop still works.

### 3. Mic is found but the audio is silent

**Cause:** Windows microphone privacy, not the script. Settings → Privacy & security →
Microphone → *Let desktop apps access your microphone* must be **on**. Also check the device isn't
muted in Sound settings, and isn't held exclusively by another app (Teams, Zoom, OBS).

### 4. Device name contains characters that break the argument

**Symptom:** `Could not find audio device`, or ffmpeg reports an odd truncated name.

**Cause:** the name is interpolated into `audio=$micDevice` at `record-screens.ps1:82`. Names with
non-ASCII characters can survive PowerShell but be mangled by the time dshow sees them.

**Fix:** use the device's *alternative name* instead. Re-run diagnostic 2 with
`-list_options true` for that device, or in Sound settings rename the device to something plain
ASCII.

### 5. It records, but drops frames / falls behind real time

**Symptom:** the ffmpeg status line shows `speed=` below `1x` and a rising `drop=` count.

**This already happens on the desktop.** A 6-second smoke test at 4480x1380 / 30 fps on an
RTX 5070 reported `speed=0.93x` with frames dropping — capture (gdigrab), not encoding, is the
bottleneck. It still produces a usable recording, but a weaker machine will be worse.

**Fix, cheapest first:** drop `-framerate 30` to `20` or `15` at `record-screens.ps1:73` (below
~15 the drone motion on the map gets hard to follow); record one monitor instead of two; or add
`-video_size` downscaling. Do **not** chase this by switching encoder — the encoder is not what's
limiting it.

### 6. Output file is huge, or the disk fills mid-session

Two monitors at full resolution and 30 fps is roughly **1–2 GB per 10 minutes**. Three 8-minute
sessions plus surveys will comfortably exceed 5 GB. Check free space before a run — a disk-full
part way through leaves an unplayable file and the session cannot be re-recorded.

To shrink it, raise `-cq` (NVENC) or `-crf` (libx264) at `record-screens.ps1:101` — 28 is
noticeably smaller and still readable for screen content — or drop `-framerate 30` to `15` at
line 73. The map animates, so below 15 fps drone motion becomes hard to follow.

---

## What not to "fix"

- **The DPI-awareness block (`record-screens.ps1:20-26`).** Without it, `Screen.WorkingArea`
  reports logical pixels while gdigrab captures physical ones, and you silently record a cropped
  region of a scaled display. It looks like unnecessary Win32 interop; it is not.
- **`WorkingArea` rather than `Bounds` (line 30).** That is what crops the taskbar out.
- **The `cmd /c "... 2>&1"` wrapper around device enumeration (line 40).** ffmpeg prints the device
  list to stderr and exits non-zero; calling it directly makes PowerShell throw
  `NativeCommandError` instead of returning the text.

## Verifying a fix without recording a whole session

```bat
scripts\record-screens.bat -Mic none
```

Let it run about five seconds, press `q`, then play the file from `%USERPROFILE%\Videos`. That
exercises geometry detection and the encoder — the two things most likely to be broken — without
depending on audio. Then repeat without `-Mic none` and confirm the console prints the mic you
expect and the playback has sound.
