# ============================================================================
#  record-screens.ps1 — capture ALL monitors + cursor + microphone into one
#  MP4 (NVENC), at true physical resolution, with the Windows taskbar cropped.
#
#  Geometry and the mic are auto-detected, so it adapts if you change
#  resolution, scaling, monitor arrangement, or audio hardware.
#
#  Mic selection:
#    - default: first real microphone (skips virtual mixers / "stereo mix")
#    - override: pass -Mic with a full name or a substring, e.g.
#        record-screens.bat -Mic "HyperX"
#        record-screens.bat -Mic none        (record video only)
#
#  Stop the recording by clicking this window and pressing  q  (clean finish).
# ============================================================================
param([string]$Mic = '')

$ErrorActionPreference = 'Stop'

# ---- Monitors: make this process per-monitor-DPI-aware so Screen bounds report
#      PHYSICAL pixels (gdigrab captures physical px; otherwise we'd grab a crop).
Add-Type @"
using System; using System.Runtime.InteropServices;
public class U { [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr v); }
"@
[U]::SetProcessDpiAwarenessContext([IntPtr](-4)) | Out-Null   # PER_MONITOR_AWARE_V2
Add-Type -AssemblyName System.Windows.Forms

# WorkingArea = full monitor minus its taskbar. Sort left-to-right by X.
$areas = [System.Windows.Forms.Screen]::AllScreens |
  ForEach-Object { $_.WorkingArea } |
  Sort-Object X

$maxH = ($areas | Measure-Object -Property Height -Maximum).Maximum

# ---- Mic: enumerate DirectShow audio devices and choose one.
function Get-AudioDevices {
  # ffmpeg prints the device list to stderr and exits non-zero; route it through
  # cmd so PowerShell receives plain text (not a terminating NativeCommandError).
  $raw = cmd /c "ffmpeg -hide_banner -list_devices true -f dshow -i dummy 2>&1"
  $names = @()
  foreach ($line in $raw) {
    if ("$line" -match '"([^"]+)"\s+\(audio\)') { $names += $matches[1] }
  }
  ,$names
}

$micDevice = $null
if ($Mic -ne 'none') {
  $audio = Get-AudioDevices
  if ($Mic) {
    $micDevice = $audio | Where-Object { $_ -like "*$Mic*" } | Select-Object -First 1
    if (-not $micDevice) { Write-Host "Mic '$Mic' not found; recording video only." -ForegroundColor Red }
  } else {
    # Prefer the headset mic; else first real mic (skip virtual mixers / loopback).
    $micDevice = $audio | Where-Object { $_ -match 'HyperX|Headset' } | Select-Object -First 1
    if (-not $micDevice) {
      $micDevice = $audio |
        Where-Object { $_ -notmatch 'Virtual|Mixer|Stereo Mix|What U Hear' } |
        Select-Object -First 1
    }
    if (-not $micDevice) { $micDevice = $audio | Select-Object -First 1 }
  }
}

# ---- Build ffmpeg args: one gdigrab input per monitor + optional mic input.
$ffArgs = @()
$pads   = @()
$labels = ''
for ($i = 0; $i -lt $areas.Count; $i++) {
  $a    = $areas[$i]
  $yoff = [int](($maxH - $a.Height) / 2)            # vertically centre shorter screens
  $ffArgs += @('-f','gdigrab','-framerate','30','-draw_mouse','1','-thread_queue_size','1024',
               '-offset_x',"$($a.X)",'-offset_y',"$($a.Y)",
               '-video_size',"$($a.Width)x$($a.Height)",'-i','desktop')
  $pads   += "[$i`:v]pad=$($a.Width):${maxH}:0:${yoff}:black[v$i]"
  $labels += "[v$i]"
}
$filter = ($pads -join ';') + ";${labels}hstack=inputs=$($areas.Count)[v]"

if ($micDevice) {
  $ffArgs += @('-f','dshow','-thread_queue_size','1024','-i',"audio=$micDevice")
}

# ---- Output + encoder. H.264 NVENC tops out at 4096px wide; the side-by-side
#      canvas can exceed that (two monitors = 4480px), so fall back to HEVC NVENC
#      (max 8192px). Both keep native resolution on the GPU.
$ts  = Get-Date -Format 'yyyyMMdd_HHmmss'
$out = Join-Path $env:USERPROFILE "Videos\sar_demo_$ts.mp4"
$canvasW = ($areas | Measure-Object -Property Width -Sum).Sum
$venc = if ($canvasW -gt 4096) { 'hevc_nvenc' } else { 'h264_nvenc' }

$ffArgs += @('-filter_complex', $filter, '-map', '[v]')
if ($micDevice) {
  $ffArgs += @('-map', "$($areas.Count):a", '-c:a','aac','-b:a','192k')
}
$ffArgs += @('-c:v',$venc,'-preset','p5','-tune','hq','-rc','vbr','-cq','23','-b:v','0',
             '-pix_fmt','yuv420p', $out)

Write-Host ""
Write-Host "Recording $($areas.Count) monitor(s) -> ${canvasW}x${maxH} via $venc" -ForegroundColor Cyan
if ($micDevice) { Write-Host "Mic: $micDevice" -ForegroundColor Cyan }
else            { Write-Host "Mic: (none - video only)" -ForegroundColor DarkGray }
Write-Host "  $out"
Write-Host "Press  q  in this window to stop." -ForegroundColor Yellow
Write-Host ""

& ffmpeg -y @ffArgs

Write-Host ""
Write-Host "Saved: $out" -ForegroundColor Green
