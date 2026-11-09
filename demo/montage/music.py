"""An original electro track for the demo video, synthesized from scratch (no samples, no licence to
clear): 124 BPM, A minor (Am F C G), four-on-the-floor kick, offbeat bass, a side-chained supersaw
pad and a plucked arpeggio. Its sections follow the video's cues: a filtered intro under the title,
a drop at each scene with a riser before it, and the drums falling away under the outro.

    python demo/montage/music.py out.wav 88 --cues 3,31.5,59 --outro 83.5
"""
from __future__ import annotations

import argparse
import wave

import numpy as np

SR = 44100
BPM = 124
BEAT = 60 / BPM
BAR = 4 * BEAT
# Am, F, C, G: bass roots (Hz) and pad chords (MIDI notes)
ROOTS = [55.00, 43.65, 65.41, 49.00]
CHORDS = [[57, 60, 64, 69], [53, 57, 60, 65], [55, 60, 64, 67], [55, 59, 62, 67]]
rng = np.random.default_rng(7)


def midi(n: float) -> float:
    return 440.0 * 2 ** ((n - 69) / 12)


def fftconv(x: np.ndarray, h: np.ndarray) -> np.ndarray:
    n = len(x) + len(h) - 1
    size = 1 << (n - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(h, size), size)[:n]
    return y[len(h) // 2: len(h) // 2 + len(x)]


def lowpass(cut: float, taps: int = 511) -> np.ndarray:
    n = np.arange(taps) - (taps - 1) / 2
    h = np.sinc(2 * cut / SR * n) * np.blackman(taps)
    return h / h.sum()


def highpass(cut: float, taps: int = 511) -> np.ndarray:
    h = -lowpass(cut, taps)
    h[(taps - 1) // 2] += 1
    return h


def saw(freq: float, t: np.ndarray, harmonics: int = 24) -> np.ndarray:
    out = np.zeros_like(t)
    for k in range(1, harmonics + 1):
        if freq * k > SR / 2.2:
            break
        out += np.sin(2 * np.pi * freq * k * t) / k
    return out * (2 / np.pi)


def add(buf: np.ndarray, start: float, sig: np.ndarray, gain: float = 1.0):
    i = int(start * SR)
    if i >= len(buf) or i + len(sig) <= 0:
        return
    j = min(len(buf), i + len(sig))
    buf[max(i, 0):j] += gain * sig[max(0, -i):j - i]


def kick() -> np.ndarray:
    t = np.arange(int(0.42 * SR)) / SR
    f = 46 + 90 * np.exp(-t * 32)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 6.5)
    click = rng.standard_normal(len(t)) * np.exp(-t * 900) * 0.4
    return np.tanh(1.6 * (body + click))


def clap() -> np.ndarray:
    t = np.arange(int(0.22 * SR)) / SR
    noise = fftconv(rng.standard_normal(len(t)), highpass(900, 255))
    env = np.exp(-t * 22)
    for d in (0.0, 0.011, 0.022):
        env += np.where(t >= d, np.exp(-(t - d) * 160), 0) * 0.8
    return noise * env * 0.5


def hat(open_: bool = False) -> np.ndarray:
    t = np.arange(int((0.16 if open_ else 0.05) * SR)) / SR
    noise = fftconv(rng.standard_normal(len(t)), highpass(7500, 255))
    return noise * np.exp(-t * (28 if open_ else 95)) * 0.35


def pluck(freq: float, dur: float) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    return saw(freq, t, 14) * np.exp(-t * 16) * np.minimum(1, t * 400)


def render(path: str, total: float, cues: list[float], outro: float) -> str:
    n = int(total * SR) + SR
    drums, bass, pad_l, pad_r, arp_l, arp_r, fx = (np.zeros(n) for _ in range(7))
    t_all = np.arange(n) / SR
    starts = sorted(cues)
    first = starts[0]

    def section(t: float) -> str:
        if t >= outro:
            return "outro"
        if t < first:
            return "intro"
        return "drop"

    k, cl, hc, ho = kick(), clap(), hat(), hat(True)
    kicks = []
    beat = 0
    while beat * BEAT < total:
        t = beat * BEAT
        sec = section(t)
        # A beat of air right before each later drop, so the drop lands.
        gap = any(0 < c - t <= BEAT * 1.01 for c in starts[1:])
        if sec == "drop" and not gap:
            add(drums, t, k, 0.95)
            kicks.append(t)
            if beat % 4 in (1, 3):
                add(drums, t, cl, 0.55)
            add(drums, t + BEAT / 2, ho, 0.5)
            add(drums, t + BEAT / 4, hc, 0.35)
            add(drums, t + 3 * BEAT / 4, hc, 0.3)
            # Offbeat bass, the chord's root
            root = ROOTS[int(t / BAR) % 4]
            bt = np.arange(int(BEAT / 2 * 0.92 * SR)) / SR
            note = saw(root * 2, bt, 30) * np.minimum(1, bt * 300) * np.exp(-bt * 3.5)
            add(bass, t + BEAT / 2, note, 0.55)
        elif sec == "outro" and t < outro + BAR:
            add(drums, t, k, 0.7 * (1 - (t - outro) / BAR))
        beat += 1

    # Pad: one chord per bar, supersaw, slow attack; brighter once the drops start.
    bar = 0
    while bar * BAR < total:
        t0 = bar * BAR
        tt = np.arange(int(BAR * SR)) / SR
        env = np.minimum(1, tt / 0.35) * np.minimum(1, (BAR - tt) / 0.08)
        chord = CHORDS[bar % 4]
        left = np.zeros_like(tt)
        right = np.zeros_like(tt)
        for note in chord:
            f = midi(note)
            for d, side in ((-0.11, "l"), (-0.04, "r"), (0.0, "lr"), (0.05, "l"), (0.12, "r")):
                wave_ = saw(f * 2 ** (d / 12), tt + rng.random(), 10)
                if "l" in side:
                    left += wave_
                if "r" in side:
                    right += wave_
        level = 0.07 if section(t0) == "intro" else 0.09
        add(pad_l, t0, left * env, level)
        add(pad_r, t0, right * env, level)
        bar += 1

    # Arpeggio: sixteenths over the chord, from the second scene on (soft in the intro).
    step = 0
    while step * BEAT / 4 < total:
        t = step * BEAT / 4
        sec = section(t)
        if sec == "intro" or (sec == "drop" and t >= starts[min(1, len(starts) - 1)]) or sec == "outro":
            chord = CHORDS[int(t / BAR) % 4]
            pattern = [0, 1, 2, 3, 2, 1, 3, 2]
            f = midi(chord[pattern[step % 8]] + 12)
            g = 0.12 if sec == "drop" else 0.07
            if sec == "outro":
                g *= max(0, 1 - (t - outro) / max(0.1, total - outro))
            p = pluck(f, BEAT / 4 * 1.6)
            add(arp_l if step % 2 else arp_r, t, p, g)
            add(arp_r if step % 2 else arp_l, t + BEAT * 0.75, p, g * 0.35)  # a dotted echo across
        step += 1

    # Risers into each drop, and an impact on it.
    for c in starts:
        dur = 2.0 if c > 2.5 else c
        tt = np.arange(int(dur * SR)) / SR
        noise = rng.standard_normal(len(tt))
        blocks = 8
        rise = np.zeros_like(noise)
        for b in range(blocks):
            a, z = b * len(tt) // blocks, (b + 1) * len(tt) // blocks
            rise[a:z] = fftconv(noise[a:z], highpass(400 + 6000 * b / blocks, 255))
        sweep = np.sin(2 * np.pi * np.cumsum(220 + 900 * (tt / dur) ** 2) / SR) * 0.25
        add(fx, c - dur, (rise * 0.5 + sweep) * (tt / dur) ** 2.2, 0.35)
        bt = np.arange(int(1.2 * SR)) / SR
        boom = np.sin(2 * np.pi * np.cumsum(38 + 40 * np.exp(-bt * 9)) / SR) * np.exp(-bt * 3)
        crash = fftconv(rng.standard_normal(len(bt)), highpass(3000, 255)) * np.exp(-bt * 3.2) * 0.25
        add(fx, c, boom + crash, 0.6)
    tt = np.arange(int(2.5 * SR)) / SR
    add(fx, outro, np.sin(2 * np.pi * np.cumsum(36 + 30 * np.exp(-tt * 6)) / SR) * np.exp(-tt * 1.6), 0.5)

    # Side-chain: everything but the drums ducks under each kick.
    duck = np.ones(n)
    for t in kicks:
        i = int(t * SR)
        seg = t_all[i:i + int(0.3 * SR)] - t
        duck[i:i + len(seg)] = np.minimum(duck[i:i + len(seg)], 1 - 0.6 * np.exp(-seg / 0.11))

    bass = fftconv(bass, lowpass(700))
    pad_l = fftconv(pad_l, lowpass(2400))
    pad_r = fftconv(pad_r, lowpass(2400))
    arp_l = fftconv(arp_l, lowpass(4200))
    arp_r = fftconv(arp_r, lowpass(4200))
    # The intro's pad is darker: crossfade a low-passed copy until the first drop.
    for buf in (pad_l, pad_r):
        dark = fftconv(buf, lowpass(700))
        mix = np.clip((t_all - (first - 1.5)) / 1.5, 0, 1)
        buf[:] = dark * (1 - mix) + buf * mix

    left = drums + (bass + pad_l + arp_l) * duck + fx
    right = drums + (bass + pad_r + arp_r) * duck + fx
    stereo = np.stack([left, right], axis=1)[: int(total * SR)]
    fade_in, fade_out = int(0.4 * SR), int(min(2.5, total - outro) * SR)
    stereo[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    stereo[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None] ** 1.5
    stereo = np.tanh(stereo / np.max(np.abs(stereo)) * 1.4) * 0.92
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((stereo * 32767).astype(np.int16).tobytes())
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("total", type=float)
    ap.add_argument("--cues", default="3")
    ap.add_argument("--outro", type=float)
    a = ap.parse_args()
    render(a.out, a.total, [float(c) for c in a.cues.split(",")], a.outro or a.total - 4)
