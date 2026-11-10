"""The short demo video (about 45 s): full screen, the cards big, only the moments that matter.

A hook (Hermes without GenUI: a wall of text, cut by the purple merge of the real run), then the
three real runs cut down to their big moments, camera close on the card and its pill, cuts with a
short crossfade, a chip naming each scene, and the outro. Music is optional: pass the track with
--music and it is laid under the video, faded out at the end.

    python demo/montage/montage_v3.py                         # -> demo/out/genui_demo_short.mp4 (silent)
    python demo/montage/montage_v3.py --music demo/track.mp3 --music-start 86.2  # with the track

--music-start is where the track starts: 86.2 puts the drop of R-Dug's Galant Captain (88.0 s) on the hook's
cut to the purple merge (1.8 s into the video).
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
from montage_v2 import (ACCENT, BG, DIM, FF, FG, HERE, LINE, ROOT, Reader, card_frame, crop_scale, ease,  # noqa: E402
                        font, lerp_cam, probe)
from scenes_v2 import PR as PR_V2  # noqa: E402  (the PR run's simulated text, for the hook)

OUT_W, OUT_H, FPS = 1920, 1080, 30
XFADE = 6          # frames of crossfade where the source jumps
CAM_EASE = 0.45    # seconds for the camera to settle on a new framing

CARD = (985, 520, 1890)
LEFT = (690, 420, 1300)
RIGHT = (1400, 520, 1100)
REL_LEFT = (690, 400, 1300)
REL_RIGHT = (1400, 450, 1100)
QUIZ = (740, 480, 1400)
SCORE = (600, 380, 1120)

SCENES = [
    {"src": "demo/pr_v2.mp4", "chip": "Pull request  ·  conflicts with main → merged", "cuts": [
        (33.0, 35.0, 1.0, CARD),      # the card builds
        (35.0, 38.2, 1.4, LEFT),      # 4 conflicts: the commits, who changed what
        (40.6, 43.2, 1.0, RIGHT),     # click: Combine both sides
        (44.0, 64.5, 14, CARD),       # resolving, pushing, checks
        (64.5, 66.0, 1.0, LEFT),      # ready: 4 checks passed
        (69.0, 71.4, 1.0, RIGHT),     # click: Merge
        (71.4, 74.6, 1.0, LEFT),      # merged: the graph turns purple
    ]},
    {"src": "demo/push_v2.mp4", "chip": "Release  ·  the migration fails → rolled back", "cuts": [
        (32.4, 34.2, 1.0, CARD),      # waiting for your go
        (35.8, 37.8, 1.0, REL_RIGHT), # click: Deploy 2.4.0 to production
        (38.6, 51.4, 12, CARD),       # deploying
        (51.4, 53.6, 1.0, REL_LEFT),  # migration 0042 fails: red
        (56.4, 58.4, 1.0, REL_RIGHT), # click: Roll back
        (58.6, 64.6, 8, CARD),
        (64.6, 67.6, 1.0, REL_LEFT),  # the rollback branches off the failed step
    ]},
    {"src": "demo/exam_v2.mp4", "chip": "Study session  ·  a quiz inside the card", "cuts": [
        (16.6, 18.6, 1.0, CARD),      # the quiz card builds
        (24.4, 28.6, 1.2, QUIZ),      # first answer: green, red, the why
        (30.4, 58.0, 10, QUIZ),       # the next questions
        (59.0, 61.6, 1.3, QUIZ),      # last answer
        (61.6, 65.0, 1.0, SCORE),     # the score counts up: 3 of 6
    ]},
]


def plan(cuts) -> list[dict]:
    frames = []
    prev_cam, prev_end = cuts[0][3], None
    for a, b, speed, cam in cuts:
        n = max(1, int(round((b - a) / speed * FPS)))
        jump = prev_end is not None and abs(a - prev_end) > 0.05
        for k in range(n):
            u = k / FPS
            m = ease(u / CAM_EASE)
            frames.append({"t": a + u * speed, "cam": lerp_cam(prev_cam, cam, m), "speed": speed,
                           "fade_in": jump and k < XFADE, "k": k})
        prev_cam, prev_end = cam, b
    return frames


def chip(canvas: Image.Image, text: str, u: float) -> Image.Image:
    """A scene's name, low on the left, for its first seconds."""
    shown, fade = 2.4, 0.3
    if u >= shown:
        return canvas
    a = min(1.0, u / fade, (shown - u) / fade)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f = font("seguisb.ttf", 34)
    w = d.textlength(text, font=f)
    x0, y0 = 60, OUT_H - 140 + 16 * (1 - a)
    d.rounded_rectangle((x0, y0, x0 + w + 56, y0 + 72), radius=36, fill=(9, 10, 14, int(235 * a)),
                        outline=ACCENT + (int(200 * a),), width=2)
    d.text((x0 + 28, y0 + 14), text, font=f, fill=FG + (int(255 * a),))
    out = canvas.convert("RGBA")
    out.alpha_composite(layer)
    return out.convert("RGB")


def badge(canvas: Image.Image, speed: float) -> Image.Image:
    if speed <= 1.5:
        return canvas
    d = ImageDraw.Draw(canvas)
    f = font("seguisb.ttf", 26)
    t = f"▶▶ {speed:g}×"
    w = d.textlength(t, font=f)
    d.rounded_rectangle((OUT_W - w - 92, 40, OUT_W - 48, 92), radius=26, fill=(24, 29, 40), outline=LINE, width=2)
    d.text((OUT_W - w - 70, 50), t, font=f, fill=FG)
    return canvas


def headline(canvas: Image.Image, kicker: str, title: str, u: float, kicker_color=DIM) -> Image.Image:
    a = ease(u / 0.25)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle((0, OUT_H - 330, OUT_W, OUT_H), fill=(9, 10, 14, int(210 * a)))
    d.text((80, OUT_H - 290), kicker, font=font("segoeui.ttf", 40), fill=kicker_color + (int(255 * a),))
    d.text((76, OUT_H - 235), title, font=font("seguisb.ttf", 96), fill=FG + (int(255 * a),))
    out = canvas.convert("RGBA")
    out.alpha_composite(layer)
    return out.convert("RGB")


def render(music: str | None, music_start: float = 0.0) -> Path:
    out = ROOT / "demo" / "out" / "genui_demo_short.mp4"
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

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 640, "height": 1024})
        page.goto((HERE / "sim_v2.html").as_uri())
        page.evaluate("d => setData(d)", {"events": PR_V2["sim"]})

        # Hook, part 1: Hermes without GenUI, the reply streaming in as a wall of text.
        for k in range(int(1.8 * FPS)):
            t = 33.4 + 2.6 * k / (1.8 * FPS)
            page.evaluate(f"renderAt({t:.3f})")
            sim = Image.open(io.BytesIO(page.screenshot(type="png"))).convert("RGB").resize((720, 1152), Image.LANCZOS)
            canvas = Image.new("RGB", (OUT_W, OUT_H), BG)
            canvas.paste(sim.crop((0, 40, 720, 40 + OUT_H)), (OUT_W - 720 - 120, 0))
            d = ImageDraw.Draw(canvas)
            d.text((110, 380), "Hermes without GenUI:", font=font("segoeui.ttf", 44), fill=DIM)
            d.text((106, 440), "a wall of text,", font=font("seguisb.ttf", 84), fill=FG)
            d.text((106, 540), "and you type the decision.", font=font("seguisb.ttf", 84), fill=FG)
            write(canvas)
        browser.close()

    # Hook, part 2: the real run's purple merge, under the title.
    pr = SCENES[0]
    w, h = probe(str(ROOT / pr["src"]))
    reader = Reader(str(ROOT / pr["src"]), w, h)
    for k in range(int(1.9 * FPS)):
        t = 71.6 + k / FPS
        canvas = crop_scale(reader.at(t), LEFT, OUT_W, OUT_H)
        write(headline(canvas, "GenUI for Hermes Agent", "Tasks as live cards.", k / FPS, ACCENT))
    reader.close()

    for scene in SCENES:
        src = str(ROOT / scene["src"])
        w, h = probe(src)
        reader = Reader(src, w, h)
        last = None
        for i, f in enumerate(plan(scene["cuts"])):
            canvas = crop_scale(reader.at(f["t"]), f["cam"], OUT_W, OUT_H)
            if f["fade_in"] and last is not None:
                canvas = Image.blend(last, canvas, (f["k"] + 1) / (XFADE + 1))
            elif i < XFADE:  # into each scene from the background
                canvas = Image.blend(Image.new("RGB", canvas.size, BG), canvas, (i + 1) / (XFADE + 1))
            if not f["fade_in"]:
                last = canvas
            write(chip(badge(canvas, f["speed"]), scene["chip"], i / FPS))
        reader.close()

    lines = [
        ("GenUI", font("seguisb.ttf", 120), FG, 250),
        ("live cards for Hermes Agent", font("segoeuil.ttf", 46), ACCENT, 420),
        ("github.com/agenticatech/genui-hermes-hackathon", font("segoeui.ttf", 34), FG, 560),
        ("Hermes Agent Plugin Hackathon · @NousResearch", font("segoeui.ttf", 28), DIM, 860),
    ]
    for k in range(int(3.4 * FPS)):
        write(card_frame(lines, k / FPS, 3.4))
    enc.stdin.close()
    enc.wait()
    seconds = n / FPS
    if music:
        fade_at = max(0.0, seconds - 2.0)
        subprocess.run([FF, "-v", "error", "-y", "-i", str(silent), "-ss", f"{music_start:.2f}", "-i", music, "-map", "0:v", "-map", "1:a",
                        "-af", f"afade=t=in:st=0:d=0.2,loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=out:st={fade_at:.2f}:d=2", "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)], check=True)
        silent.unlink()
    else:
        silent.replace(out)
    print(f"{out} ({seconds:.1f}s, rendered in {time.time() - started:.0f}s)")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--music", help="an audio file to lay under the video")
    ap.add_argument("--music-start", type=float, default=0.0, help="where the track starts, in seconds")
    a = ap.parse_args()
    render(a.music, a.music_start)
