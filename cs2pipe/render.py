"""render.py: 2D radar breakdown (our own asset) and the 3-second hook.

Frames are drawn with Pillow and piped to ffmpeg as raw RGB. With maps/<map>.png and the
game's overview file maps/<map>.txt (pos_x, pos_y, scale) the radar image is used; without
them the view fits the round's positions on a plain background.

The hook here is a zoomed radar clip ending just after the key kill. POV footage from CS2
demo playback is next-step 5 in the roadmap (unknown whether it can be scripted); plug it in
as another `HookSource` once that test passes.
"""
from __future__ import annotations

import re
import subprocess
from bisect import bisect_right
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .schema import Timeline

COLORS = {"CT": (93, 160, 230), "T": (232, 163, 61), "bg": (14, 17, 22), "ink": (225, 230, 236),
          "dim": (130, 140, 150), "key": (255, 215, 94), "line": (240, 80, 70)}


def font(size: int):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def load_overview(maps_dir: Path, map_name: str) -> tuple[Image.Image, dict] | None:
    png, txt = maps_dir / f"{map_name}.png", maps_dir / f"{map_name}.txt"
    if not (png.exists() and txt.exists()):
        return None
    text = txt.read_text(errors="ignore")
    vals = {k: float(re.search(rf'"{k}"\s+"(-?[\d.]+)"', text).group(1)) for k in ("pos_x", "pos_y", "scale")}
    return Image.open(png).convert("RGB"), vals


class Track:
    """Interpolated positions for one round."""

    def __init__(self, tl: Timeline, round_number: int):
        self.samples = [s for s in tl.positions if s.round == round_number]
        self.ticks = [s.tick for s in self.samples]

    def at(self, tick: float) -> dict[str, tuple[float, float, bool]]:
        if not self.samples:
            return {}
        i = bisect_right(self.ticks, tick)
        if i == 0:
            return {k: (v[0], v[1], bool(v[2])) for k, v in self.samples[0].players.items()}
        if i >= len(self.samples):
            return {k: (v[0], v[1], bool(v[2])) for k, v in self.samples[-1].players.items()}
        a, b = self.samples[i - 1], self.samples[i]
        f = (tick - a.tick) / max(1, b.tick - a.tick)
        out = {}
        for k, va in a.players.items():
            vb = b.players.get(k, va)
            out[k] = (va[0] + (vb[0] - va[0]) * f, va[1] + (vb[1] - va[1]) * f, bool(vb[2] if f > 0.5 else va[2]))
        return out

    def bounds(self) -> tuple[float, float, float, float]:
        xs = [v[0] for s in self.samples for v in s.players.values()]
        ys = [v[1] for s in self.samples for v in s.players.values()]
        return min(xs), min(ys), max(xs), max(ys)


class View:
    """World (x, y) -> pixel in a square of `size` px, optionally zoomed on a centre."""

    def __init__(self, size: int, overview: tuple | None, track: Track, zoom: float = 1.0,
                 centre: tuple[float, float] | None = None):
        self.size, self.zoom = size, zoom
        if overview:
            img, o = overview
            self.radar = img
            self.world = (o["pos_x"], o["pos_y"] - o["scale"] * img.height, o["pos_x"] + o["scale"] * img.width, o["pos_y"])
        else:
            self.radar = None
            x0, y0, x1, y1 = track.bounds()
            span = max(x1 - x0, y1 - y0) * 1.15 or 1.0
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            self.world = (cx - span / 2, cy - span / 2, cx + span / 2, cy + span / 2)
        x0, y0, x1, y1 = self.world
        self.centre = centre or ((x0 + x1) / 2, (y0 + y1) / 2)
        self.span = (x1 - x0) / zoom

    def px(self, x: float, y: float) -> tuple[float, float]:
        cx, cy = self.centre
        return ((x - cx) / self.span + 0.5) * self.size, (0.5 - (y - cy) / self.span) * self.size

    def background(self) -> Image.Image:
        if self.radar is None:
            return Image.new("RGB", (self.size, self.size), (24, 28, 34))
        x0, y0, x1, y1 = self.world
        w = self.radar.width
        cx, cy = self.centre
        left = (cx - self.span / 2 - x0) / (x1 - x0) * w
        top = (y1 - (cy + self.span / 2)) / (y1 - y0) * w
        side = self.span / (x1 - x0) * w
        return self.radar.crop((int(left), int(top), int(left + side), int(top + side))).resize((self.size, self.size))


def _draw_frame(canvas: Image.Image, view: View, bg: Image.Image, tl: Timeline, play: dict, track: Track,
                tick: float, title: str, top: int) -> None:
    rnd = tl.rounds[play["round"] - 1]
    w = canvas.width
    canvas.paste(COLORS["bg"], (0, 0, w, canvas.height))
    canvas.paste(bg, (0, top))
    d = ImageDraw.Draw(canvas)
    s = w / 1080
    d.text((w / 2, top / 2), title, fill=COLORS["ink"], font=font(int(54 * s)), anchor="mm")

    kills = [e for e in tl.events_in_round(rnd.number) if e.type == "kill" and e.tick <= tick]
    for k in kills:
        if tick - k.tick < tl.tickrate * 1.0:
            pos = track.at(k.tick)
            if k.actor in pos and k.target in pos:
                a, b = view.px(*pos[k.actor][:2]), view.px(*pos[k.target][:2])
                d.line([(a[0], a[1] + top), (b[0], b[1] + top)], fill=COLORS["line"], width=max(1, int(5 * s)))
    r = 16 * s
    for sid, (x, y, alive) in track.at(tick).items():
        side = rnd.sides.get(sid)
        if not side:
            continue
        px, py = view.px(x, y)
        py += top
        if alive:
            d.ellipse((px - r, py - r, px + r, py + r), fill=COLORS[side])
            if sid == play["actor"]:
                d.ellipse((px - r * 1.7, py - r * 1.7, px + r * 1.7, py + r * 1.7), outline=COLORS["key"], width=max(1, int(5 * s)))
        else:
            d.line((px - r, py - r, px + r, py + r), fill=COLORS["dim"], width=max(1, int(4 * s)))
            d.line((px - r, py + r, px + r, py - r), fill=COLORS["dim"], width=max(1, int(4 * s)))

    alive = {sd: 0 for sd in ("CT", "T")}
    for sid, (_, _, a) in track.at(tick).items():
        if a and rnd.sides.get(sid):
            alive[rnd.sides[sid]] += 1
    y = top + view.size + 40 * s
    sb = rnd.score_before
    d.text((w / 2, y), f"Round {rnd.number}   {tl.teams['A']} {sb['A']} - {sb['B']} {tl.teams['B']}",
           fill=COLORS["ink"], font=font(int(40 * s)), anchor="mt")
    d.text((w / 2, y + 60 * s), f"CT {alive['CT']}  v  {alive['T']} T", fill=COLORS["dim"], font=font(int(40 * s)), anchor="mt")
    fy = y + 140 * s
    for k in kills[-6:]:
        colour = COLORS["key"] if k.id in play["event_ids"] else COLORS["ink"]
        line = f"{tl.player_name(k.actor)}  [{k.weapon}]  {tl.player_name(k.target)}"
        if k.flags:
            line += "  " + " ".join(k.flags)
        d.text((60 * s, fy), line, fill=colour, font=font(int(34 * s)))
        fy += 48 * s


def _encode(frames, out: Path, w: int, h: int, fps: int) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
         "-r", str(fps), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", str(out)],
        stdin=subprocess.PIPE)
    for frame in frames:
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed writing {out}")


def _clip(tl: Timeline, play: dict, cfg: dict, out: Path, t_start: float, t_end: float, seconds: float,
          zoom: float, title: str) -> Path:
    rc = cfg["render"]
    w, h, fps = rc["width"], rc["height"], rc["fps"]
    track = Track(tl, play["round"])
    overview = load_overview(Path(cfg["paths"]["maps_dir"]), tl.map)
    top = int(h * 0.14)
    centre = None
    if zoom > 1:
        p = track.at(play["key_tick"]).get(play["actor"])
        centre = (p[0], p[1]) if p else None
    view = View(w, overview, track, zoom, centre)
    bg = view.background()
    n = max(2, int(seconds * fps))
    canvas = Image.new("RGB", (w, h))

    def frames():
        for i in range(n):
            _draw_frame(canvas, view, bg, tl, play, track, t_start + (t_end - t_start) * i / (n - 1), title, top)
            yield canvas

    _encode(frames(), out, w, h, fps)
    return out


class RadarHook:
    def render(self, tl: Timeline, play: dict, cfg: dict, out: Path, title: str) -> Path:
        secs = cfg["render"]["hook_seconds"]
        end = min(play["end_tick"], play["key_tick"] + tl.tickrate * 0.5)
        return _clip(tl, play, cfg, out, end - secs * tl.tickrate, end, secs, 2.2, title)


class CS2ClientHook:
    """POV hook from CS2 demo playback. Blocked on roadmap next-step 5."""

    def render(self, tl: Timeline, play: dict, cfg: dict, out: Path, title: str) -> Path:
        raise NotImplementedError("CS2 client POV capture not built; see docs/roadmap.md next step 5")


def render_breakdown(tl: Timeline, play: dict, cfg: dict, out: Path, seconds: float, title: str) -> Path:
    return _clip(tl, play, cfg, out, play["start_tick"], play["end_tick"], seconds, 1.0, title)
