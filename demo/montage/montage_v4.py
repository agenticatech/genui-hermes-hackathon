"""The v4 demo video (about a minute): the v2 layout, cut tight.

Each scene opens in close-up on the composer as the prompt is typed, then splits as it is sent:
the real run WITH GenUI on the left (1280 px), the simulated run WITHOUT it on the right (640 px,
sim_v2.html on the recording's clock). The wait before the card is one fast-forward; the card
builds, then the clicks and their results play at 1x, everything between them fast.

    python demo/montage/montage_v4.py                                   # -> demo/out/genui_demo_v4.mp4 (silent)
    python demo/montage/montage_v4.py --music track.mp3 --drop 88.0     # the track's drop on the first split
    python demo/montage/montage_v4.py --scene 1                         # one scene only, no title or outro
"""
from __future__ import annotations

import argparse
import io
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from montage_v2 import (ACCENT, BG, DIM, FF, FG, FPS, HEADER, HERE, LINE, OUT_H, OUT_W, ROOT, SIM_W, Reader,  # noqa: E402
                        card_frame, crop_scale, ease, font, header, lerp_cam, probe)
from scenes_v4 import SCENES  # noqa: E402

TITLE_DUR, OUTRO_DUR = 2.0, 3.6
FADE = 6                 # frames of fade from the background into each scene
EMPTY, HOLD = 0.3, 0.3   # seconds on the empty composer before typing, and on the typed prompt


def grab(src: str, t: float, w: int, h: int) -> np.ndarray:
    raw = subprocess.run([FF, "-v", "error", "-ss", f"{t:.3f}", "-i", src, "-frames:v", "1", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(h, w, 3).copy()


class Typing:
    """The prompt typed into the composer, glyph by glyph, rebuilt from a still with the whole prompt:
    what is not typed yet is painted over with the composer's background (the pointer stays)."""

    def __init__(self, src: str, spec: dict, w: int, h: int):
        self.base = grab(src, spec["base"], w, h)
        top = 1290
        rows = self.base[top:1390].astype(int)
        yellow = (rows[..., 0] - rows[..., 2] > 50) & (rows[..., 0] > 120)
        keep = np.zeros_like(yellow)
        for dy in (-2, -1, 0, 1, 2):
            for dx in (-2, -1, 0, 1, 2):
                keep |= np.roll(np.roll(yellow, dy, 0), dx, 1)
        bright = (rows.max(axis=2) > 150) & ~keep
        bright[:, :58] = bright[:, 1900:] = False            # the + button and the model picker
        run = np.zeros(bright.shape[1], int)                 # a caret left in the still: one tall, straight column
        cur = np.zeros(bright.shape[1], int)
        for r in bright:
            cur = np.where(r, cur + 1, 0)
            run = np.maximum(run, cur)
        caret = np.zeros_like(keep)
        for x in np.nonzero(run >= 21)[0]:
            caret[:, max(0, x - 1):x + 2] = True
        bright &= ~caret
        ys = np.nonzero(bright.any(axis=1))[0]
        ink = (rows.max(axis=2) > 60) & ~keep & ~caret
        ink[:ys.min() - 6] = ink[ys.max() + 6:] = False      # the text line only, not the composer's border
        ink[:, :58] = ink[:, 1900:] = False
        runs, start = [], None                               # glyphs: runs of inked columns
        for x, o in enumerate(ink.any(axis=0)):
            if o and start is None:
                start = x
            elif not o and start is not None:
                runs.append((start, x - 1))
                start = None
        self.x0, self.x1 = runs[0][0], runs[-1][1]
        ys = np.nonzero(ink[:, self.x0:self.x1 + 1].any(axis=1))[0]
        self.y0, self.y1 = top + ys.min(), top + ys.max()
        self.r0, self.r1 = self.y0 - 6, self.y1 + 6
        self.keep = keep[self.r0 - top:self.r1 - top + 1]    # the mouse pointer, left in place
        band = rows[self.r0 - top:self.r1 - top + 1]
        self.bg = np.median(band[band.max(axis=2) < 30], axis=0).astype(np.uint8)
        self.stops = [b + 1 for _, b in runs]                # the x after each glyph
        self.dur = spec["dur"]

    def caret_x(self, u: float) -> int:
        """The caret's x, u seconds into the typing (0 to dur)."""
        if u <= 0:
            return self.x0 - 2
        k = min(len(self.stops), int(np.ceil(len(self.stops) * min(1.0, u / self.dur))))
        return self.stops[k - 1]

    def frame(self, u: float, caret: bool) -> np.ndarray:
        f = self.base.copy()
        x = self.caret_x(u)
        a, b = x, self.x1 + 16
        region = f[self.r0:self.r1 + 1, a:b]
        mask = ~self.keep[:, a:b]
        region[mask] = self.bg
        if caret:
            f[self.y0 - 1:self.y1 + 2, x + 1:x + 2] = (226, 230, 236)
        return f


def typing_cam(t: Typing, u: float, cx_prev: float | None) -> tuple:
    """Close on the composer, a slow push-in, the caret kept two thirds across."""
    cw = 1150 + (840 - 1150) * ease(u / 0.9)
    ch = cw * OUT_H / OUT_W
    cy = (t.y0 + t.y1) / 2 - 0.10 * ch
    cx = max(cw / 2 + 20, t.caret_x(u - EMPTY) - 0.20 * cw)
    if cx_prev is not None:
        cx = max(cx, cx_prev)                                 # never pan back
    return (cx, cy, cw)


def plan(scene: dict, typing: Typing) -> list[dict]:
    """One entry per output frame: the typing close-up, then the recording's segments."""
    frames, cx = [], None
    n = int(round((EMPTY + typing.dur + HOLD) * FPS))
    for k in range(n):
        u = k / FPS
        cam = typing_cam(typing, u, cx)
        cx = cam[0]
        blink = u < EMPTY or u > EMPTY + typing.dur
        frames.append({"typing": u - EMPTY, "caret": (not blink) or int(u * 2.2) % 2 == 0,
                       "cam": cam, "split": 0.0, "speed": 1, "src_t": scene["typing"]["base"]})
    settled_cam, settled_split = frames[-1]["cam"], 0.0
    cam, split = settled_cam, 0.0
    for seg in scene["segments"]:
        cam = seg.get("cam", cam)
        split = 1.0 if seg.get("split", split == 1.0) else 0.0
        trans, speed = seg.get("trans", 0.8), seg.get("speed", 1)
        dur = (seg["src"][1] - seg["src"][0]) / speed
        for k in range(max(1, int(round(dur * FPS)))):
            u = k / FPS
            m = ease(u / trans) if trans > 0 else 1.0
            frames.append({"cam": lerp_cam(settled_cam, cam, m), "split": settled_split + (split - settled_split) * m,
                           "speed": speed, "src_t": seg["src"][0] + u * speed})
        settled_cam, settled_split = cam, split
    return frames


def kicker(canvas: Image.Image, text: str, u: float, dur: float) -> Image.Image:
    """The scene's number and name, top left, over the typing."""
    a = max(0.0, min(1.0, u / 0.25, (dur - u) / 0.25))
    if a <= 0:
        return canvas
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f = font("seguisb.ttf", 30)
    w = d.textlength(text, font=f)
    x0, y0 = 60, 56 - 10 * (1 - a)
    d.rounded_rectangle((x0, y0, x0 + w + 52, y0 + 62), radius=31, fill=(9, 10, 14, int(235 * a)),
                        outline=ACCENT + (int(200 * a),), width=2)
    d.text((x0 + 26, y0 + 12), text, font=f, fill=FG + (int(255 * a),))
    out = canvas.convert("RGBA")
    out.alpha_composite(layer)
    return out.convert("RGB")


def title_lines():
    return [
        ("GenUI", font("seguisb.ttf", 150), FG, 330),
        ("live cards for Hermes Agent", font("segoeuil.ttf", 54), ACCENT, 520),
        ("3 real runs in Hermes Desktop, with and without GenUI", font("segoeui.ttf", 30), DIM, 640),
    ]


def outro_lines():
    return [
        ("GenUI", font("seguisb.ttf", 120), FG, 250),
        ("hermes plugins install genui", font("consola.ttf", 46), FG, 450, True),
        ("Pull requests · Releases · Machines · Cleanups · Study sessions", font("segoeui.ttf", 32), DIM, 590),
        ("github.com/agenticatech/genui-hermes-hackathon", font("segoeui.ttf", 30), FG, 680),
        ("Hermes Agent Plugin Hackathon · @NousResearch", font("segoeui.ttf", 28), ACCENT, 860),
    ]


def render(only: int | None, music: str | None, drop: float) -> Path:
    fonts = {"bold": font("seguisb.ttf", 24), "small": font("segoeui.ttf", 21)}
    scenes = [SCENES[only - 1]] if only else SCENES
    with_cards = only is None
    sizes = [probe(str(ROOT / s["src"])) for s in scenes]
    typings = [Typing(str(ROOT / s["src"]), s["typing"], w, h) for s, (w, h) in zip(scenes, sizes)]
    plans = [plan(s, t) for s, t in zip(scenes, typings)]
    first_split = (TITLE_DUR if with_cards else 0.0) + next(i for i, f in enumerate(plans[0]) if f["split"] > 0) / FPS
    name = "genui_demo_v4" if with_cards else f"genui_v4_scene{only}"
    out = ROOT / "demo" / "out" / f"{name}.mp4"
    silent = out.with_suffix(".video.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    enc = subprocess.Popen([FF, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OUT_W}x{OUT_H}", "-r", str(FPS),
                            "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
                            "-movflags", "+faststart", str(silent)], stdin=subprocess.PIPE)
    n, started = 0, time.time()

    def write(img: Image.Image):
        nonlocal n
        enc.stdin.write(img.tobytes())
        n += 1
        if n % 300 == 0:
            print(f"  {n} frames, {time.time() - started:.0f}s", flush=True)

    if with_cards:
        lines = title_lines()
        for k in range(int(TITLE_DUR * FPS)):
            write(card_frame(lines, k / FPS, TITLE_DUR))
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": SIM_W, "height": OUT_H - HEADER})
        page.goto((HERE / "sim_v2.html").as_uri())
        for index, (scene, frames, typing, (w, h)) in enumerate(zip(scenes, plans, typings, sizes), start=1):
            reader = Reader(str(ROOT / scene["src"]), w, h)
            page.evaluate("d => setData(d)", {"events": scene["sim"]})
            sim_key, sim_img = None, None
            n_typing = sum(1 for f in frames if "typing" in f)
            for i, f in enumerate(frames):
                if "typing" in f:
                    frame = typing.frame(f["typing"], f["caret"])
                else:
                    frame = reader.at(f["src_t"])
                s = f["split"]
                hh = int(round(HEADER * s))
                ph, lw = OUT_H - hh, int(round(OUT_W - SIM_W * s))
                canvas = Image.new("RGB", (OUT_W, OUT_H), BG)
                canvas.paste(crop_scale(frame, f["cam"], lw, ph), (0, hh))
                if s > 0.01:
                    key = page.evaluate(f"renderAt({f['src_t']:.3f})")
                    if key != sim_key:
                        sim_key, sim_img = key, Image.open(io.BytesIO(page.screenshot(type="png"))).convert("RGB")
                    canvas.paste(sim_img.crop((0, 0, OUT_W - lw, min(ph, sim_img.height))), (lw, hh))
                canvas = header(canvas, lw, s, f["speed"], scene, fonts)
                canvas = kicker(canvas, f"{index} / {len(scenes)}  ·  {scene['title']}", i / FPS, n_typing / FPS + 0.3)
                if i < FADE:
                    canvas = Image.blend(Image.new("RGB", canvas.size, BG), canvas, (i + 1) / (FADE + 1))
                elif i >= len(frames) - FADE // 2:
                    canvas = Image.blend(Image.new("RGB", canvas.size, BG), canvas, (len(frames) - i) / (FADE // 2 + 1))
                write(canvas)
            reader.close()
        browser.close()
    if with_cards:
        lines = outro_lines()
        for k in range(int(OUTRO_DUR * FPS)):
            write(card_frame(lines, k / FPS, OUTRO_DUR))
    enc.stdin.close()
    enc.wait()
    seconds = n / FPS
    if music:
        start = max(0.0, drop - first_split)
        fade_at = max(0.0, seconds - 2.0)
        subprocess.run([FF, "-v", "error", "-y", "-i", str(silent), "-ss", f"{start:.2f}", "-i", music, "-map", "0:v", "-map", "1:a",
                        "-af", f"afade=t=in:st=0:d=0.2,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,afade=t=out:st={fade_at:.2f}:d=2", "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)], check=True)
        silent.unlink()
    else:
        silent.replace(out)
    print(f"{out} ({seconds:.1f}s, first split at {first_split:.2f}s, rendered in {time.time() - started:.0f}s)")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", type=int, help="render one scene only (1, 2 or 3)")
    ap.add_argument("--music", help="an audio file to lay under the video")
    ap.add_argument("--drop", type=float, default=0.0, help="the time in the track to land on the first split")
    a = ap.parse_args()
    render(a.scene, a.music, a.drop)
