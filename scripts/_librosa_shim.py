"""
A stand-in for the three `librosa` calls resemblyzer's preprocessing needs, backed by
soundfile/torchaudio instead. Import and call install() BEFORE anything imports `resemblyzer`.

Why this exists: real librosa pulls in numba, and the numba already installed in this machine's
base environment predates the numpy also installed there ("Numba needs NumPy 1.21 or less"), and
because it was installed by conda (distutils), pip can't cleanly upgrade or remove it to fix that.
Rather than touch a shared base environment's numba/llvmlite/numpy stack to chase one optional
accuracy feature, this shim reimplements resemblyzer's exact three call sites --
`librosa.load`, `librosa.resample`, `librosa.feature.melspectrogram` -- on top of soundfile and
torchaudio (already installed, no numba in its dependency chain). See docs/NARRATION.md "Speaker
identification" for the accuracy trade-off this implies.
"""
import sys
import types

import numpy as np
import soundfile as sf
import torch
import torchaudio


def _load(path, sr=None):
    wav, file_sr = sf.read(str(path), dtype='float32', always_2d=False)
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    return wav, file_sr


def _resample(wav, orig_sr, target_sr):
    if orig_sr == target_sr:
        return wav
    t = torch.from_numpy(np.asarray(wav, dtype=np.float32)).unsqueeze(0)
    out = torchaudio.functional.resample(t, orig_sr, target_sr)
    return out.squeeze(0).numpy()


def _melspectrogram(y, sr, n_fft, hop_length, n_mels):
    t = torch.from_numpy(np.asarray(y, dtype=np.float32)).unsqueeze(0)
    mel = torchaudio.transforms.MelSpectrogram(
        sample_rate=sr, n_fft=n_fft, hop_length=hop_length, n_mels=n_mels,
        window_fn=torch.hann_window, power=2.0, center=True,
        norm='slaney', mel_scale='slaney',
    )(t)
    return mel.squeeze(0).numpy()


def install() -> None:
    if 'librosa' in sys.modules and getattr(sys.modules['librosa'], '_is_shim', False):
        return
    if 'librosa' in sys.modules and not getattr(sys.modules['librosa'], '_is_shim', False):
        raise RuntimeError('real librosa is already imported; call shim.install() first')
    mod = types.ModuleType('librosa')
    mod._is_shim = True
    mod.load = _load
    mod.resample = _resample
    feature = types.ModuleType('librosa.feature')
    feature.melspectrogram = _melspectrogram
    mod.feature = feature
    sys.modules['librosa'] = mod
    sys.modules['librosa.feature'] = feature
