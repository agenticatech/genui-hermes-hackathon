"""Turn a raw Hermes Desktop recording into a 1920x1080 post for X.

1. A close-up on the prompt box: the prompt is typed fast, rebuilt from the sent message's own pixels
   (same font, same colours), since the recordings paste it.
2. A zoom out to the whole app as the message is sent.
3. A split screen: the real run WITH GenUI on the left, a simulated run WITHOUT it on the right
   (sim.html, driven by the recording's own clock so both sides stay in sync). Waiting is sped up,
   interactions play at 1x, and nothing below the chat (status bar, server address) is ever shown.

    python demo/montage/montage.py push_to_prod        # -> demo/out/push_to_prod.mp4
    python demo/montage/montage.py push_to_prod --preview 12   # first 12 s only
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
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scenes import SCENES  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FF = imageio_ffmpeg.get_ffmpeg_exe()
OUT_W, OUT_H, FPS, HEADER = 1920, 1080, 30, 56
PANEL_W = OUT_W // 2
SRC_FPS = 30
FONT = "C:/Windows/Fonts/courbd.ttf"
COL = {"bg": (3, 10, 3), "header": (1, 6, 1), "line": (24, 71, 31), "fg": (18, 255, 64), "dim": (47, 138, 69)}

# Measured on the recordings (Hermes Desktop, Cyberpunk theme, 2558 px wide).
INPUT_BG = np.array([12, 19, 12], float)
BUBBLE_BG_G = 22
TEXT_RGB = np.array([18, 255, 64], float)
INPUT_TEXT_X = 382          # left ink of the first character in the prompt box
INPUT_CLEAR = (376, 1320, 1900, 1364)   # the box's text area (placeholder, mouse I-beam)
EMPTY_CHAT = (330, 640, 2262, 1310)     # the empty chat above the box (welcome text)
CHAT_BG = np.array([3, 10, 3], np.uint8)
BUBBLE_TEXT_X = 364         # left ink of the first character in the sent message
BUBBLE_ROWS = (60, 90)      # rows holding the sent message's text
BUBBLE_TO_INPUT_DY = 1266   # same line, moved from the message box to the prompt box
ADVANCE = 10.27             # px per character (Courier New at the app's size)


def probe(src: str) -> tuple[int, int]:
    err = subprocess.run([FF, "-hide_banner", "-i", src], capture_output=True, text=True).stderr
    w, h = re.search(r"Video:.*?(\d{3,5})x(\d{3,5})", err).groups()
    return int(w), int(h)


def grab(src: str, t: float, w: int, h: int) -> np.ndarray:
    raw = subprocess.run([FF, "-v", "error", "-ss", f"{t:.3f}", "-i", src, "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(h, w, 3).copy()


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


class Typist:
    """The prompt box with the prompt typed up to n characters, in the app's own glyphs."""

    def __init__(self, base: np.ndarray, bubble: np.ndarray, prompt: str):
        x0, x1, y0, y1 = INPUT_CLEAR[0], INPUT_CLEAR[2], INPUT_CLEAR[1], INPUT_CLEAR[3]
        self.base = base.copy()
        self.base[y0:y1, x0:x1] = INPUT_BG.astype(np.uint8)
        # The empty chat's welcome lines sit just above the box: keep the close-up on the box alone.
        self.base[EMPTY_CHAT[1]:EMPTY_CHAT[3], EMPTY_CHAT[0]:EMPTY_CHAT[2]] = CHAT_BG
        width = int(math.ceil(len(prompt) * ADVANCE)) + 4
        strip = bubble[BUBBLE_ROWS[0]:BUBBLE_ROWS[1], BUBBLE_TEXT_X - 2:BUBBLE_TEXT_X - 2 + width, 1].astype(float)
        self.alpha = np.clip((strip - BUBBLE_BG_G) / (255 - BUBBLE_BG_G), 0, 1)[:, :, None]
        self.y = BUBBLE_ROWS[0] + BUBBLE_TO_INPUT_DY
        self.x = INPUT_TEXT_X - 2
        self.n = len(prompt)

    def frame(self, chars: int, caret: bool) -> np.ndarray:
        f = self.base.copy()
        w = min(self.alpha.shape[1], int(round(chars * ADVANCE)) + 2)
        if w > 0:
            region = f[self.y:self.y + self.alpha.shape[0], self.x:self.x + w].astype(float)
            a = self.alpha[:, :w]
            f[self.y:self.y + a.shape[0], self.x:self.x + w] = (region * (1 - a) + TEXT_RGB * a).astype(np.uint8)
        if caret:
            cx = self.x + 2 + int(round(chars * ADVANCE)) + 1
            f[self.y + 5:self.y + 25, cx:cx + 2] = TEXT_RGB.astype(np.uint8)
        return f


def ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def lerp_cam(a, b, k):
    return (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, math.exp(math.log(a[2]) + (math.log(b[2]) - math.log(a[2])) * k))


def crop_scale(frame: np.ndarray, cam, out_w: int, out_h: int) -> Image.Image:
    h_src, w_src = frame.shape[:2]
    cx, cy, cw = cam
    ch = cw * out_h / out_w
    if ch > h_src:  # never taller than the recording
        ch, cw = h_src, h_src * out_w / out_h
    x0 = min(max(cx - cw / 2, 0), w_src - cw)
    y0 = min(max(cy - ch / 2, 0), h_src - ch)
    return Image.fromarray(frame).resize((out_w, out_h), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))


def plan(scene: dict) -> list[dict]:
    """One entry per output frame: what to show and how. A segment inherits the camera and the
    split of the one before unless it names its own; a change eases in over `trans` seconds."""
    frames = []
    cam_name, split = "input", 0.0
    settled_cam, settled_split = None, 0.0
    n_chars = len(scene["prompt"])
    for seg in scene["segments"]:
        cam_name = seg.get("cam", cam_name)
        split = 1.0 if seg.get("split", split == 1.0) else 0.0
        cam = scene["cams"][cam_name]
        start_cam = settled_cam or cam
        trans = seg.get("trans", 0.8)
        speed = seg.get("speed", 1)
        if "typing" in seg:
            kind, dur = "typing", seg["typing"] + seg.get("hold", 0.4)
        elif "hold_at" in seg:
            kind, dur = "hold", seg["dur"]
        else:
            kind, dur = "play", (seg["src"][1] - seg["src"][0]) / speed
        for k in range(max(1, int(round(dur * FPS)))):
            u = k / FPS
            m = ease(u / trans) if trans > 0 else 1.0
            entry = {"kind": kind, "cam": lerp_cam(start_cam, cam, m), "split": settled_split + (split - settled_split) * m,
                     "speed": speed, "src_t": 0.0}
            if kind == "typing":
                entry["chars"] = min(n_chars, int(math.ceil(n_chars * u / seg["typing"])))
                entry["caret"] = u < seg["typing"] or int((u - seg["typing"]) * 2.5) % 2 == 0
            elif kind == "hold":
                entry["src_t"] = seg["hold_at"]
            else:
                entry["src_t"] = seg["src"][0] + u * speed
            frames.append(entry)
        settled_cam, settled_split = cam, split
    return frames


def overlay(canvas: Image.Image, lw: int, s: float, speed: float, font, small):
    """Header with the two labels, the speed badge, the divider and the fade on the cut text."""
    if s <= 0.01:
        return canvas
    hh = int(round(HEADER * s))
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    a = int(255 * s)
    d.rectangle((0, 0, OUT_W, hh), fill=COL["header"] + (255,))
    d.line((0, hh, OUT_W, hh), fill=COL["line"] + (a,), width=2)
    d.line((lw, hh, lw, OUT_H), fill=COL["line"] + (a,), width=2)
    for text, x_mid, color in (("WITH GENUI", lw / 2, COL["fg"]), ("WITHOUT GENUI  (simulated)", lw + (OUT_W - lw) / 2, COL["dim"])):
        w = d.textlength(text, font=font)
        d.text((x_mid - w / 2, hh / 2 - 13), text, font=font, fill=color + (a,))
    if speed > 1:
        badge = f">> x{speed:g}"
        w = d.textlength(badge, font=small)
        d.rounded_rectangle((lw - w / 2 - 12, hh / 2 - 15, lw + w / 2 + 12, hh / 2 + 15), radius=8, fill=COL["header"] + (a,),
                            outline=COL["line"] + (a,), width=2)
        d.text((lw - w / 2, hh / 2 - 10), badge, font=small, fill=COL["fg"] + (a,))
    out = canvas.convert("RGBA")
    out.alpha_composite(layer)
    return out.convert("RGB")


def fade_right(img: Image.Image, s: float, width: int = 90) -> Image.Image:
    """The real chat's long lines run past the left panel: fade them into the background."""
    if s <= 0.01:
        return img
    arr = np.asarray(img).astype(float)
    w = min(width, arr.shape[1])
    ramp = (np.linspace(0, 1, w) ** 1.5 * s)[None, :, None]
    arr[:, -w:] = arr[:, -w:] * (1 - ramp) + np.array(COL["bg"], float) * ramp
    return Image.fromarray(arr.astype(np.uint8))


def render(name: str, preview: float | None = None) -> Path:
    scene = SCENES[name]
    src = str(ROOT / scene["src"])
    w, h = probe(src)
    frames = plan(scene)
    if preview:
        frames = frames[: int(preview * FPS)]
    typist = Typist(grab(src, scene["base_t"], w, h), grab(src, scene["bubble_t"], w, h), scene["prompt"])
    out = ROOT / "demo" / "out" / f"{name}{'_preview' if preview else ''}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    enc = subprocess.Popen([FF, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OUT_W}x{OUT_H}", "-r", str(FPS),
                            "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                            "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)
    reader = Reader(src, w, h)
    font, small = ImageFont.truetype(FONT, 26), ImageFont.truetype(FONT, 20)
    started = time.time()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": PANEL_W, "height": OUT_H - HEADER})
        page.goto((HERE / "sim.html").as_uri())
        page.evaluate("d => setData(d)", {"events": scene["sim"]})
        sim_key, sim_img = None, None
        for i, f in enumerate(frames):
            if f["kind"] == "typing":
                src_frame = typist.frame(f["chars"], f["caret"])
            else:
                src_frame = reader.at(f["src_t"])
            s = f["split"]
            hh = int(round(HEADER * s))
            ph, lw = OUT_H - hh, int(round(OUT_W - PANEL_W * s))
            canvas = Image.new("RGB", (OUT_W, OUT_H), COL["header"])
            canvas.paste(fade_right(crop_scale(src_frame, f["cam"], lw, ph), s), (0, hh))
            if s > 0.01:
                key = page.evaluate(f"renderAt({f['src_t']:.3f})")
                if key != sim_key:
                    sim_key, sim_img = key, Image.open(io.BytesIO(page.screenshot(type="png"))).convert("RGB")
                rw = OUT_W - lw
                canvas.paste(sim_img.crop((0, 0, rw, min(ph, sim_img.height))), (lw, hh))
            canvas = overlay(canvas, lw, s, f["speed"], font, small)
            enc.stdin.write(canvas.tobytes())
            if i % 90 == 0:
                print(f"  {i}/{len(frames)} frames, {time.time() - started:.0f}s", flush=True)
        browser.close()
    reader.close()
    enc.stdin.close()
    enc.wait()
    print(f"{out} ({len(frames) / FPS:.1f}s, rendered in {time.time() - started:.0f}s)")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("scene", choices=sorted(SCENES))
    ap.add_argument("--preview", type=float, help="render only the first N seconds")
    args = ap.parse_args()
    render(args.scene, args.preview)
