"""Synthesizes the original music bed for the Kumaun showcase (no samples, no licensing).

Usage: python3 bgm.py app-showcase/assets/bgm.wav   (needs numpy)
"""
import sys
import wave

import numpy as np

SR = 44100
DUR = 42.5
BPM = 120
BEAT = 60 / BPM
BAR = 4 * BEAT
APP_IN = 3.9  # beat drops in when the app first appears
N = int(SR * DUR)
t = np.arange(N) / SR
out = np.zeros(N)
rng = np.random.default_rng(7)

CHORDS = [[48, 55, 60, 64], [45, 52, 57, 60], [41, 48, 53, 57], [43, 50, 55, 59]]  # C Am F G


def mid(n):
    return 440 * 2 ** ((n - 69) / 12)


def env_ad(length, attack, decay):
    x = np.arange(length) / SR
    return np.minimum(x / attack, 1) * np.exp(-x / decay)


def add(sig, start):
    i = int(start * SR)
    j = min(N, i + len(sig))
    if i < N:
        out[i:j] += sig[: j - i]


bars = int(DUR / BAR)

for b in range(bars):  # warm pad
    length = int(BAR * SR) + int(0.4 * SR)
    x = np.arange(length) / SR
    sig = np.zeros(length)
    for n in CHORDS[b % 4]:
        f = mid(n)
        for det in (-0.004, 0, 0.004):
            sig += np.sin(2 * np.pi * f * (1 + det) * x) + 0.3 * np.sin(2 * np.pi * 2 * f * (1 + det) * x)
    env = np.minimum(x / 0.5, 1) * np.minimum((length / SR - x) / 0.4, 1)
    add(0.05 * sig * env, b * BAR)

for b in range(bars):  # plucked arpeggio
    ch = CHORDS[b % 4]
    pattern = [ch[0], ch[1], ch[2], ch[3], ch[2], ch[1], ch[2], ch[1]]
    for k, n in enumerate(pattern):
        start = b * BAR + k * BEAT / 2
        if start < APP_IN:
            continue
        length = int(0.5 * SR)
        x = np.arange(length) / SR
        f = mid(n + 24 if k % 4 == 0 else n + 12)
        sig = (np.sin(2 * np.pi * f * x) + 0.4 * np.sin(2 * np.pi * 2 * f * x)) * env_ad(length, 0.004, 0.12)
        add(0.07 * sig, start)

for b in range(bars):  # bass
    n = CHORDS[b % 4][0] - 12
    for k in (0, 1.5, 2, 3):
        start = b * BAR + k * BEAT
        if start < APP_IN:
            continue
        length = int(0.5 * SR)
        x = np.arange(length) / SR
        add(0.16 * np.sin(2 * np.pi * mid(n) * x) * env_ad(length, 0.01, 0.25), start)

for k in range(int(DUR / BEAT)):  # kick on the beat, hat on the off-beat
    start = k * BEAT
    if start < APP_IN:
        continue
    length = int(0.3 * SR)
    x = np.arange(length) / SR
    phase = 2 * np.pi * np.cumsum(45 + 90 * np.exp(-x * 30)) / SR
    add(0.34 * np.sin(phase) * np.exp(-x * 12), start)
    length = int(0.08 * SR)
    x = np.arange(length) / SR
    hat = np.diff(rng.standard_normal(length), prepend=0)
    add(0.05 * hat * np.exp(-x * 55), start + BEAT / 2)

out *= np.minimum(t / 1.0, 1) * np.minimum((DUR - t) / 1.8, 1)  # fade in and out
out = np.tanh(out * 1.4)
out *= 0.8 / np.max(np.abs(out))

with wave.open(sys.argv[1], "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((out * 32767).astype(np.int16).tobytes())
