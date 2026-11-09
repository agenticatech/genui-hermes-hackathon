"""The v2 demo video: three real Hermes Desktop runs with GenUI, each beside a simulation of the
same run without it, between a title and an outro, over an original electro track (music.py).

Each scene opens full width on the prompt, then splits: the real run WITH GenUI on the left
(1280 px), the simulated run WITHOUT it on the right (640 px, sim_v2.html, driven by the
recording's own clock so both sides stay in sync). Waiting is sped up and badged; clicks and the
card's big moments play at 1x, with the camera easing onto the card's pill or graph.

    python demo/montage/montage_v2.py                 # -> demo/out/genui_demo.mp4
    python demo/montage/montage_v2.py --preview 12    # first 12 s, no music
    python demo/montage/montage_v2.py --scene 1       # one scene only, no title, outro or music
"""
from __future__ import annotations

import argparse
import io
import math
import re
import subprocess
import sys
import time
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import music  # noqa: E402
from scenes_v2 import SCENES  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FF = imageio_ffmpeg.get_ffmpeg_exe()
OUT_W, OUT_H, FPS, HEADER = 1920, 1080, 30, 56
SIM_W = 640
SRC_FPS = 30
BG = (13, 14, 19)
HEAD_BG = (9, 10, 14)
LINE = (34, 41, 56)
FG = (236, 239, 243)
DIM = (138, 144, 154)
ACCENT = (143, 180, 255)
FONTS = "C:/Windows/Fonts/"
TITLE_DUR, OUTRO_DUR = 2.8, 4.2


def font(name: str, size: int):
    return ImageFont.truetype(FONTS + name, size)


def probe(src: str) -> tuple[int, int]:
    err = subprocess.run([FF, "-hide_banner", "-i", src], capture_output=True, text=True).stderr
    w, h = re.search(r"Video:.*?(\d{3,5})x(\d{3,5})", err).groups()
    return int(w), int(h)


class Reader:
    """Sequential decoder: at(t) returns the frame shown at t; times only move forward."""

    def __init__(self, src: str, w: int, h: int):
        self.p = subprocess.Popen([FF, "-v", "error", "-i", src, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                  stdout=subprocess.PIPE, bufsize=w * h * 3 * 2)
        self.size, self.shape, self.i, self.frame = w * h * 3, (h, w, 3), -1, None

    def at(self, t: float) -> np.ndarray:
        want = max(0, int(round(t * SRC_FPS)))
        while self.i < want:
            buf = self.p.stdout.read(self.size)
            if len(buf) < self.size:
                break
            self.frame, self.i = np.frombuffer(buf, np.uint8).reshape(self.shape), self.i + 1
        return self.frame

    def close(self):
        self.p.kill()


def ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def lerp_cam(a, b, k):
    return (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, math.exp(math.log(a[2]) + (math.log(b[2]) - math.log(a[2])) * k))


def crop_scale(frame: np.ndarray, cam, out_w: int, out_h: int) -> Image.Image:
    """The camera's view, scaled to the panel; past the recording's edges, the app background."""
    h_src, w_src = frame.shape[:2]
    cx, cy, cw = cam
    ch = cw * out_h / out_w
    x0, y0 = int(round(cx - cw / 2)), int(round(cy - ch / 2))
    x1, y1 = x0 + int(round(cw)), y0 + int(round(ch))
    if x0 >= 0 and y0 >= 0 and x1 <= w_src and y1 <= h_src:
        view = frame[y0:y1, x0:x1]
    else:
        view = np.empty((y1 - y0, x1 - x0, 3), np.uint8)
        view[:] = BG
        sx0, sy0, sx1, sy1 = max(x0, 0), max(y0, 0), min(x1, w_src), min(y1, h_src)
        if sx1 > sx0 and sy1 > sy0:
            view[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = frame[sy0:sy1, sx0:sx1]
    return Image.fromarray(np.ascontiguousarray(view)).resize((out_w, out_h), Image.LANCZOS)


def plan(scene: dict) -> list[dict]:
    """One entry per output frame. A segment keeps the camera and split of the one before unless it
    names its own; a change eases in over `trans` seconds."""
    frames = []
    cam, split = scene["segments"][0]["cam"], 0.0
    settled_cam, settled_split = cam, 0.0
    for seg in scene["segments"]:
        cam = seg.get("cam", cam)
        split = 1.0 if seg.get("split", split == 1.0) else 0.0
        trans = seg.get("trans", 0.8)
        speed = seg.get("speed", 1)
        if "hold_at" in seg:
            dur = seg["dur"]
        else:
            dur = (seg["src"][1] - seg["src"][0]) / speed
        for k in range(max(1, int(round(dur * FPS)))):
            u = k / FPS
            m = ease(u / trans) if trans > 0 else 1.0
            frames.append({
                "cam": lerp_cam(settled_cam, cam, m), "split": settled_split + (split - settled_split) * m, "speed": speed,
                "src_t": seg["hold_at"] if "hold_at" in seg else seg["src"][0] + u * speed,
            })
        settled_cam, settled_split = cam, split
    return frames


def header(canvas: Image.Image, lw: int, s: float, speed: float, scene: dict, f: dict):
    if s <= 0.01:
        return canvas
    hh = int(round(HEADER * s))
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    a = int(255 * s)
    d.rectangle((0, 0, OUT_W, hh), fill=HEAD_BG + (255,))
    d.line((0, hh, OUT_W, hh), fill=LINE + (a,), width=2)
    d.line((lw, hh, lw, OUT_H), fill=LINE + (a,), width=2)
    bold, small = f["bold"], f["small"]
    left = "WITH GENUI"
    d.text((28, hh / 2 - 14), left, font=bold, fill=ACCENT + (a,))
    d.text((28 + d.textlength(left, font=bold) + 18, hh / 2 - 11), scene["title"], font=small, fill=DIM + (a,))
    right = "WITHOUT GENUI · simulated"
    d.text((lw + 22, hh / 2 - 11), right, font=small, fill=DIM + (a,))
    if speed > 1:
        badge = f"▶▶ {speed:g}×"
        w = d.textlength(badge, font=small)
        x1 = lw - 20
        d.rounded_rectangle((x1 - w - 24, hh / 2 - 15, x1, hh / 2 + 15), radius=15, fill=(24, 29, 40, a), outline=LINE + (a,), width=2)
        d.text((x1 - w - 12, hh / 2 - 11), badge, font=small, fill=FG + (a,))
    out = canvas.convert("RGBA")
    out.alpha_composite(layer)
    return out.convert("RGB")


def caption(canvas: Image.Image, scene: dict, index: int, total: int, u: float, f: dict) -> Image.Image:
    """The scene's name and the user's request, over the first seconds of each scene."""
    shown, fade = 2.6, 0.35
    if u >= shown:
        return canvas
    a = min(1.0, u / fade, (shown - u) / fade)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    kicker = f"{index} / {total}  ·  {scene['title'].upper()}"
    line = scene["caption"]
    w = max(d.textlength(kicker, font=f["small"]), d.textlength(line, font=f["caption"])) + 80
    x0, y0 = (OUT_W - w) / 2, 150 - 14 * (1 - a)
    d.rounded_rectangle((x0, y0, x0 + w, y0 + 128), radius=18, fill=(9, 10, 14, int(225 * a)), outline=LINE + (int(255 * a),), width=2)
    d.text((x0 + 40, y0 + 22), kicker, font=f["small"], fill=ACCENT + (int(255 * a),))
    d.text((x0 + 40, y0 + 54), line, font=f["caption"], fill=FG + (int(255 * a),))
    out = canvas.convert("RGBA")
    out.alpha_composite(layer)
    return out.convert("RGB")


def card_frame(lines: list[tuple], u: float, dur: float) -> Image.Image:
    """A title or outro card: lines of (text, font, colour, y), rising and fading in, fading out."""
    img = Image.new("RGB", (OUT_W, OUT_H), BG)
    glow = Image.new("RGB", (OUT_W, OUT_H), BG)
    gd = ImageDraw.Draw(glow)
    gd.ellipse((OUT_W / 2 - 520, OUT_H / 2 - 300, OUT_W / 2 + 520, OUT_H / 2 + 300), fill=(22, 30, 52))
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(160)), 0.9)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i, (text, fnt, color, y, *box) in enumerate(lines):
        k = ease((u - 0.12 * i) / 0.6)
        out = min(1.0, (dur - u) / 0.35)
        a = int(255 * k * max(0.0, out))
        w = d.textlength(text, font=fnt)
        x = (OUT_W - w) / 2
        yy = y + 24 * (1 - k)
        if box:
            d.rounded_rectangle((x - 30, yy - 16, x + w + 30, yy + fnt.size + 22), radius=14, fill=(20, 24, 34, a), outline=(52, 62, 84, a), width=2)
        d.text((x, yy), text, font=fnt, fill=color + (a,))
    out = img.convert("RGBA")
    out.alpha_composite(layer)
    return out.convert("RGB")


def title_lines():
    return [
        ("GenUI", font("seguisb.ttf", 150), FG, 300),
        ("live cards for Hermes Agent", font("segoeuil.ttf", 54), ACCENT, 490),
        ("The agent shows the task as a card, updates it as it works, and asks with a button.", font("segoeui.ttf", 32), DIM, 600),
        ("3 real runs in Hermes Desktop · Claude Opus 5.5 · waits sped up", font("segoeui.ttf", 24), DIM, 900),
    ]


def outro_lines():
    return [
        ("GenUI", font("seguisb.ttf", 120), FG, 250),
        ("hermes plugins install genui", font("consola.ttf", 46), FG, 450, True),
        ("Pull requests · Releases · Machines · Cleanups · Study sessions", font("segoeui.ttf", 32), DIM, 590),
        ("github.com/agenticatech/genui-hermes-hackathon", font("segoeui.ttf", 30), FG, 680),
        ("Hermes Agent Plugin Hackathon · @NousResearch", font("segoeui.ttf", 28), ACCENT, 860),
    ]


def render(preview: float | None = None, only: int | None = None) -> Path:
    fonts = {"bold": font("seguisb.ttf", 24), "small": font("segoeui.ttf", 21), "caption": font("segoeui.ttf", 34)}
    scenes = [SCENES[only - 1]] if only else SCENES
    with_cards = only is None
    plans = [plan(s) for s in scenes]
    cues, t = [], TITLE_DUR if with_cards else 0.0
    for p in plans:
        cues.append(t)
        t += len(p) / FPS
    outro_at = t
    total = t + (OUTRO_DUR if with_cards else 0)
    if preview:
        total = min(total, preview)
    name = "genui_demo" if with_cards else f"genui_scene{only}"
    out = ROOT / "demo" / "out" / f"{name}{'_preview' if preview else ''}.mp4"
    silent = out.with_suffix(".video.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    enc = subprocess.Popen([FF, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OUT_W}x{OUT_H}", "-r", str(FPS),
                            "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
                            "-movflags", "+faststart", str(silent)], stdin=subprocess.PIPE)
    written, limit, started = 0, int(round(total * FPS)), time.time()

    def write(img: Image.Image) -> bool:
        nonlocal written
        if written >= limit:
            return False
        enc.stdin.write(img.tobytes())
        written += 1
        if written % 150 == 0:
            print(f"  {written}/{limit} frames, {time.time() - started:.0f}s", flush=True)
        return True

    if with_cards:
        lines = title_lines()
        for k in range(int(TITLE_DUR * FPS)):
            write(card_frame(lines, k / FPS, TITLE_DUR))
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": SIM_W, "height": OUT_H - HEADER})
        page.goto((HERE / "sim_v2.html").as_uri())
        for index, (scene, frames) in enumerate(zip(scenes, plans), start=1):
            if written >= limit:
                break
            src = str(ROOT / scene["src"])
            w, h = probe(src)
            reader = Reader(src, w, h)
            page.evaluate("d => setData(d)", {"events": scene["sim"]})
            sim_key, sim_img = None, None
            for i, f in enumerate(frames):
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
                canvas = caption(canvas, scene, index, len(scenes), i / FPS, fonts)
                if i < 9:  # a short fade from the background into each scene
                    canvas = Image.blend(Image.new("RGB", canvas.size, BG), canvas, (i + 1) / 10)
                if not write(canvas):
                    break
            reader.close()
        browser.close()
    if with_cards:
        lines = outro_lines()
        for k in range(int(OUTRO_DUR * FPS)):
            if not write(card_frame(lines, k / FPS, OUTRO_DUR)):
                break
    enc.stdin.close()
    enc.wait()
    seconds = written / FPS
    if with_cards and not preview:
        wav = out.with_suffix(".wav")
        music.render(str(wav), seconds, [c for c in cues], outro_at)
        subprocess.run([FF, "-v", "error", "-y", "-i", str(silent), "-i", str(wav), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-shortest", "-movflags", "+faststart", str(out)], check=True)
        silent.unlink()
        wav.unlink()
    else:
        silent.replace(out)
    print(f"{out} ({seconds:.1f}s, rendered in {time.time() - started:.0f}s; scenes start at {', '.join(f'{c:.1f}' for c in cues)}s)")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=float, help="render only the first N seconds, without music")
    ap.add_argument("--scene", type=int, help="render one scene only (1, 2 or 3)")
    a = ap.parse_args()
    render(a.preview, a.scene)
