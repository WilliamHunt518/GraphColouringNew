"""
Load all participant data from results/participants/.

Each participant folder contains:
  study_metadata.json   — trial configs
  study_summary.json    — completion + clash stats
  demographics.json     — background questionnaire
  summary_survey.json   — post-session ratings per scenario
  trial_NN_<label>/
    game_events.jsonl   — timestamped event log
    survey.json         — TLX / trust / TAM (absent for tutorial)
"""

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT   = Path(__file__).parent.parent
RESULTS_ROOT = REPO_ROOT / "results" / "participants"


# ── Data classes ────────────────────────────────────────────────────────────

@dataclass
class TrialData:
    label:       str
    index:       int           # 1-based
    folder:      Path
    config:      Dict[str, Any]   # from study_metadata trials list
    events:      List[Dict]       # all lines from game_events.jsonl
    survey:      Optional[Dict]   # survey.json; None for tutorial
    summary:     Dict[str, Any]   # matching entry in study_summary trials list


@dataclass
class ParticipantData:
    participant_id:   str
    folder:           Path
    start_time:       str          # "YYYYMMDD_HHMMSS"
    metadata:         Dict[str, Any]
    summary:          Dict[str, Any]
    demographics:     Dict[str, Any]
    summary_survey:   Dict[str, Any]
    trials:           List[TrialData]
    git_commit:       Optional[str] = None   # full SHA
    git_short:        Optional[str] = None   # 7-char
    git_message:      Optional[str] = None
    git_date:         Optional[str] = None
    pid_label:        str = ""               # "P1", "P2", … assigned after sorting


# ── Helpers ──────────────────────────────────────────────────────────────────

def _read_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> List[Dict]:
    events = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return events


def _git_commit_before(unix_ts: float) -> tuple:
    """Return (full_hash, short_hash, message, date) of the last commit before unix_ts."""
    try:
        dt_str = datetime.utcfromtimestamp(unix_ts).strftime("%Y-%m-%d %H:%M:%S")
        result = subprocess.run(
            ["git", "log", "--pretty=format:%H|%ai|%s", f"--before={dt_str} UTC", "-1"],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split("|", 2)
            h    = parts[0]
            date = parts[1] if len(parts) > 1 else ""
            msg  = parts[2] if len(parts) > 2 else ""
            return h, h[:7], msg, date
    except Exception:
        pass
    return None, None, None, None


def _session_start_ts(trials: List[TrialData]) -> Optional[float]:
    """Unix timestamp of the very first event in the session."""
    for t in trials:
        for e in t.events:
            if "ts" in e:
                return e["ts"]
    return None


# ── Public API ───────────────────────────────────────────────────────────────

def load_participant(folder: Path) -> ParticipantData:
    metadata       = _read_json(folder / "study_metadata.json")
    summary        = _read_json(folder / "study_summary.json")
    demographics   = _read_json(folder / "demographics.json")
    summary_survey = _read_json(folder / "summary_survey.json")

    # Match trial folders to metadata order
    trial_dirs = sorted(
        [d for d in folder.iterdir() if d.is_dir() and d.name.startswith("trial_")],
        key=lambda d: d.name
    )

    trial_cfgs  = metadata.get("trials", [])
    trial_sums  = summary.get("trials", [])

    trials: List[TrialData] = []
    for i, (cfg, summ) in enumerate(zip(trial_cfgs, trial_sums)):
        idx = i + 1
        # Match by prefix "trial_01_", "trial_02_", …
        prefix = f"trial_{idx:02d}_"
        td = next((d for d in trial_dirs if d.name.startswith(prefix)), None)
        if td is None:
            continue

        events = _load_jsonl(td / "game_events.jsonl") if (td / "game_events.jsonl").exists() else []
        # surveys live at participant root as trial_NN_survey.json
        survey_path = folder / f"trial_{idx:02d}_survey.json"
        survey = _read_json(survey_path) if survey_path.exists() else None

        trials.append(TrialData(
            label   = cfg["label"],
            index   = idx,
            folder  = td,
            config  = cfg,
            events  = events,
            survey  = survey,
            summary = summ,
        ))

    # Git version lookup
    first_ts = _session_start_ts(trials)
    git_commit, git_short, git_msg, git_date = (
        _git_commit_before(first_ts) if first_ts else (None, None, None, None)
    )

    return ParticipantData(
        participant_id = metadata["participant_id"],
        folder         = folder,
        start_time     = metadata["start_time"],
        metadata       = metadata,
        summary        = summary,
        demographics   = demographics,
        summary_survey = summary_survey,
        trials         = trials,
        git_commit     = git_commit,
        git_short      = git_short,
        git_message    = git_msg,
        git_date       = git_date,
    )


def load_all_participants() -> List[ParticipantData]:
    """Discover and load every participant folder under results/participants/."""
    if not RESULTS_ROOT.exists():
        print(f"Results directory not found: {RESULTS_ROOT}")
        return []

    participants = []
    for folder in sorted(RESULTS_ROOT.iterdir()):
        if folder.is_dir() and (folder / "study_metadata.json").exists():
            try:
                p = load_participant(folder)
                participants.append(p)
            except Exception as exc:
                print(f"  Warning — failed to load {folder.name}: {exc}")

    # Sort chronologically and assign P1, P2, … labels
    participants.sort(key=lambda p: p.start_time)
    for i, p in enumerate(participants, 1):
        p.pid_label = f"P{i}"
        print(f"  Loaded: {p.pid_label} = {p.participant_id}  ({p.start_time})  git={p.git_short}")

    return participants


def save_participant_map(participants: List[ParticipantData], out_path: Path) -> None:
    """Write a small JSON file mapping P1/P2/… to participant IDs and sessions."""
    mapping = {
        p.pid_label: {
            "participant_id": p.participant_id,
            "session_start":  p.start_time,
            "git_short":      p.git_short or "",
            "git_message":    p.git_message or "",
        }
        for p in participants
    }
    out_path.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
