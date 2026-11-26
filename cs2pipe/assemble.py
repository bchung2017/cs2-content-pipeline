"""assemble.py: TTS the script, render hook + breakdown to fit the voice, join into one vertical MP4."""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from . import render
from .narrate import spoken_text
from .schema import Timeline


def probe_duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         check=True, capture_output=True, text=True).stdout
    return float(out.strip())


def tts(text: str, out_wav: Path, cfg: dict) -> float:
    t = cfg["tts"]
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    if t["provider"] == "silent":
        seconds = max(1.0, len(text.split()) / t["words_per_second"])
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                        "-t", f"{seconds:.2f}", str(out_wav)], check=True)
    elif t["provider"] == "command":
        text_file = out_wav.with_suffix(".txt")
        text_file.write_text(text)
        cmd = t["command"].format(text_file=shlex.quote(str(text_file)), out_wav=shlex.quote(str(out_wav)))
        subprocess.run(cmd, shell=True, check=True)
    else:
        raise ValueError(f"unknown tts provider {t['provider']!r}")
    return probe_duration(out_wav)


def join(hook: Path, breakdown: Path, voice: Path, out: Path, hook_s: float, breakdown_s: float) -> None:
    fmt = "aformat=sample_rates=44100:channel_layouts=mono"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(hook), "-i", str(breakdown), "-i", str(voice),
        "-f", "lavfi", "-t", f"{hook_s:.3f}", "-i", "anullsrc=r=44100:cl=mono",
        "-filter_complex",
        f"[3:a]{fmt}[ha];[2:a]{fmt},apad,atrim=0:{breakdown_s:.3f}[va];[0:v][ha][1:v][va]concat=n=2:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-movflags", "+faststart", str(out),
    ], check=True)


def assemble(tl: Timeline, play: dict, script: dict, cfg: dict, out_dir: Path,
             hook_source=None) -> tuple[Path, float]:
    out_dir.mkdir(parents=True, exist_ok=True)
    hook_source = hook_source or render.RadarHook()
    voice_s = tts(spoken_text(script), out_dir / "voice.wav", cfg)
    breakdown_s = voice_s + 0.5
    hook = hook_source.render(tl, play, cfg, out_dir / "hook.mp4", script["title"])
    breakdown = render.render_breakdown(tl, play, cfg, out_dir / "breakdown.mp4", breakdown_s, script["title"])
    final = out_dir / "draft.mp4"
    join(hook, breakdown, out_dir / "voice.wav", final, cfg["render"]["hook_seconds"], breakdown_s)
    return final, probe_duration(final)
