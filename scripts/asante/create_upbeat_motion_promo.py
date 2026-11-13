#!/usr/bin/env python3
"""Create an original, beat-synced Asante promo using vector-style graphics."""

from __future__ import annotations

import math
import random
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "documentation/project/assets/media/asante-motion-promo-upbeat.mp4"
W, H, FPS, DURATION = 1280, 720, 30, 24
BPM, BEAT = 120, 0.5
INK, MUTED, ORANGE = "#17383d", "#668086", "#e87840"
MINT, CREAM, PALE = "#b6ead5", "#fff5e7", "#f7faf8"
YELLOW, BLUE, WHITE = "#ffd15d", "#5589df", "#ffffff"
FONT_PATH = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
SECTIONS = [(0, 2), (2, 6), (6, 10), (10, 14), (14, 18), (18, 24)]


def fnt(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(BOLD_PATH if bold else FONT_PATH, size)


def txt(d: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, size: int,
        color: str = INK, bold: bool = False, anchor: str | None = None) -> None:
    d.text(xy, value, font=fnt(size, bold), fill=color, anchor=anchor)


def ease(v: float) -> float:
    v = max(0.0, min(1.0, v))
    return v * v * (3 - 2 * v)


def pop(v: float) -> float:
    v = max(0.0, min(1.0, v))
    return 1 + 0.16 * math.sin(v * math.pi) * (1 - v)


def blank(bg: str = PALE) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGB", (W, H), bg)
    return im, ImageDraw.Draw(im)


def rounded_card(size: tuple[int, int], bg: str = WHITE) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    card = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((4, 4, size[0] - 5, size[1] - 5), radius=28,
                        fill=bg, outline="#e5eeea", width=2)
    return card, d


def solve8(matrix: list[list[float]], values: list[float]) -> list[float]:
    rows = [row[:] + [value] for row, value in zip(matrix, values)]
    for col in range(8):
        pivot = max(range(col, 8), key=lambda row: abs(rows[row][col]))
        rows[col], rows[pivot] = rows[pivot], rows[col]
        div = rows[col][col]
        for j in range(col, 9):
            rows[col][j] /= div
        for row in range(8):
            if row == col:
                continue
            factor = rows[row][col]
            for j in range(col, 9):
                rows[row][j] -= factor * rows[col][j]
    return [rows[i][8] for i in range(8)]


def project_card(canvas: Image.Image, card: Image.Image,
                 quad: list[tuple[float, float]], shadow: bool = True) -> None:
    left = int(min(p[0] for p in quad))
    top = int(min(p[1] for p in quad))
    right = int(max(p[0] for p in quad))
    bottom = int(max(p[1] for p in quad))
    dest = [(x - left, y - top) for x, y in quad]
    source = [(0, 0), (card.width - 1, 0), (card.width - 1, card.height - 1), (0, card.height - 1)]
    matrix: list[list[float]] = []
    values: list[float] = []
    for (x, y), (u, v) in zip(dest, source):
        matrix.append([x, y, 1, 0, 0, 0, -x * u, -y * u])
        values.append(u)
        matrix.append([0, 0, 0, x, y, 1, -x * v, -y * v])
        values.append(v)
    coeffs = solve8(matrix, values)
    size = (max(1, right - left), max(1, bottom - top))
    warped = card.transform(size, Image.Transform.PERSPECTIVE, coeffs,
                            resample=Image.Resampling.BICUBIC)
    if shadow:
        offset = 15
        shadow_layer = Image.new("RGBA", card.size, (26, 56, 61, 0))
        shadow_layer.putalpha(card.getchannel("A").point(lambda a: int(a * .22)))
        shadow_warp = shadow_layer.transform(size, Image.Transform.PERSPECTIVE, coeffs,
                                             resample=Image.Resampling.BICUBIC)
        shadow_canvas = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        shadow_canvas.alpha_composite(shadow_warp, (left, top + offset))
        shadow_canvas = shadow_canvas.filter(ImageFilter.GaussianBlur(16))
        canvas.paste(shadow_canvas, (0, 0), shadow_canvas)
    canvas.paste(warped, (left, top), warped)


def cursor(d: ImageDraw.ImageDraw, x: float, y: float, click: bool = False, tint: str = INK) -> None:
    if click:
        d.ellipse((x - 26, y - 26, x + 26, y + 26), fill="#fff0d8", outline=YELLOW, width=4)
    d.polygon([(x, y), (x, y + 37), (x + 10, y + 27), (x + 20, y + 45),
               (x + 28, y + 41), (x + 18, y + 23), (x + 32, y + 21)],
              fill=tint, outline=WHITE, width=3)


def logo(d: ImageDraw.ImageDraw, x: int, y: int, size: int, spin: float = 0) -> None:
    d.ellipse((x - size // 2 - 10, y - size // 2 - 10, x + size // 2 + 10, y + size // 2 + 10), fill=CREAM)
    d.ellipse((x - size // 2, y - size // 2, x + size // 2, y + size // 2), fill=ORANGE)
    d.ellipse((x - size // 9, y - size // 9, x + size // 9, y + size // 9), fill=WHITE)
    # Rotating orbit accent gives the mark a small dimensional flourish.
    angle = math.radians(spin)
    ox = x + int(math.cos(angle) * (size * .75))
    oy = y + int(math.sin(angle) * (size * .45))
    d.ellipse((ox - 7, oy - 7, ox + 7, oy + 7), fill=YELLOW)


def map_art(d: ImageDraw.ImageDraw, rect: tuple[int, int, int, int], t: float) -> None:
    x1, y1, x2, y2 = rect
    d.rounded_rectangle(rect, radius=22, fill="#eaf3ed")
    # Isometric neighborhood blocks.
    for row in range(3):
        for col in range(5):
            x = x1 + 58 + col * 112 + (row % 2) * 25
            y = y1 + 60 + row * 92
            dx = 45 + 4 * math.sin(t * math.pi * 2 + col)
            dy = 16
            d.polygon([(x, y), (x + dx, y - dy), (x + dx + 32, y),
                       (x + 32, y + dy)], fill="#d4e7d8")
            d.polygon([(x + 32, y + dy), (x + dx + 32, y),
                       (x + dx + 32, y + 33), (x + 32, y + 49)], fill="#bedbc9")
            d.polygon([(x, y), (x + 32, y + dy), (x + 32, y + 49), (x, y + 33)], fill="#cbe2d1")
    # Warm route ribbon.
    points = [(x1 + 72, y1 + 211), (x1 + 182, y1 + 172), (x1 + 300, y1 + 213),
              (x1 + 390, y1 + 148), (x1 + 520, y1 + 184)]
    d.line(points, fill=ORANGE, width=8, joint="curve")
    d.line(points, fill="#ffd6ad", width=3, joint="curve")
    for i, (px, py) in enumerate([points[0], points[2], points[4]]):
        radius = 14 + int(4 * math.sin(t * math.pi * 2 + i))
        d.ellipse((px-radius, py-radius, px+radius, py+radius), fill=ORANGE, outline=WHITE, width=4)
        d.ellipse((px-4, py-4, px+4, py+4), fill=WHITE)


def hero_scene(t: float) -> Image.Image:
    im, d = blank("#f9fbfa")
    # Big floating 3D brand tile with a shifting perspective.
    card, cd = rounded_card((760, 360), WHITE)
    cd.rounded_rectangle((28, 28, 160, 160), radius=38, fill=CREAM)
    logo(cd, 94, 94, 68, t * 100)
    txt(cd, (204, 62), "ASANTE", 58, INK, True)
    txt(cd, (207, 139), "STORIES BELONG TO PLACES", 21, MUTED, True)
    cd.rounded_rectangle((205, 210, 551, 272), radius=31, fill=INK)
    txt(cd, (378, 226), "Explore the map", 21, WHITE, True, "mm")
    # Sparkle burst on the first downbeat.
    for i in range(12):
        angle = math.tau * i / 12 + t * 2
        r = 194 + 6 * math.sin(t * math.tau)
        x, y = 640 + math.cos(angle) * r, 350 + math.sin(angle) * r * .58
        d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=[ORANGE, YELLOW, MINT][i % 3])
    pulse = pop((t % BEAT) / BEAT)
    cx, cy = 640, 352
    quad = [(cx - 410 * pulse, cy - 186 * pulse), (cx + 367 * pulse, cy - 208 * pulse),
            (cx + 407 * pulse, cy + 175 * pulse), (cx - 366 * pulse, cy + 195 * pulse)]
    project_card(im, card, quad)
    cursor(d, 498 + ease(t / 1.5) * 222, 535 - ease(t / 1.5) * 130, .8 < t < 1.0)
    return im


def discover_scene(t: float) -> Image.Image:
    im, d = blank("#f6faf7")
    txt(d, (64, 70), "FIND A STORY", 18, ORANGE, True)
    txt(d, (64, 105), "Wherever you are.", 43, INK, True)
    # Large perspective map tile.
    card, cd = rounded_card((760, 440), WHITE)
    map_art(cd, (20, 20, 740, 420), t)
    cd.rounded_rectangle((46, 38, 326, 94), radius=16, fill=WHITE, outline="#deebe4", width=2)
    txt(cd, (70, 53), "Search stories and places", 16, MUTED)
    pulse = pop((t % BEAT) / BEAT)
    q = [(462, 145), (1170, 85), (1193, 516), (489, 581)]
    q = [(462 + (x - 462) * pulse, 330 + (y - 330) * pulse) for x, y in q]
    project_card(im, card, q)
    # Floating story card in a second plane.
    story, sd = rounded_card((338, 178), WHITE)
    sd.rounded_rectangle((16, 16, 322, 82), radius=14, fill=CREAM)
    sd.ellipse((142, 34, 196, 88), fill=ORANGE)
    sd.polygon([(162, 45), (182, 61), (162, 77)], fill=WHITE)
    txt(sd, (20, 101), "A place with a story", 19, INK, True)
    txt(sd, (20, 132), "Community voices · 4 min", 14, MUTED)
    project_card(im, story, [(804, 442), (1131, 418), (1150, 584), (822, 607)])
    # Cursor follows the route and taps a landmark on each bar.
    x = 520 + ease(t / 3.7) * 495
    y = 312 + math.sin(t * math.pi * 2) * 25
    cursor(d, x, y, t > 3.5)
    return im


def listen_scene(t: float) -> Image.Image:
    im, d = blank("#fffaf4")
    # Decorative floating equalizer columns at the edges.
    for i in range(14):
        x = 65 + i * 27
        h = 18 + int(26 * (0.5 + 0.5 * math.sin(t * math.tau + i * .7)))
        d.rounded_rectangle((x, 570 - h, x + 7, 570 + h), radius=4,
                            fill=[MINT, YELLOW, "#ffd4bd"][i % 3])
    card, cd = rounded_card((640, 430), WHITE)
    cd.rounded_rectangle((24, 24, 616, 212), radius=22, fill="#edf5f0")
    # Layered sound-wave ribbons.
    for layer, color, amp in [(0, ORANGE, 58), (1, BLUE, 38), (2, "#63b890", 23)]:
        pts = []
        for x in range(38, 604, 7):
            phase = x / 36 + t * math.tau * (1 + layer * .12)
            pts.append((x, 115 + math.sin(phase) * amp * (0.65 + 0.35 * math.cos(x / 90))))
        cd.line(pts, fill=color, width=4 - layer, joint="curve")
    cd.ellipse((273, 71, 367, 165), fill=ORANGE)
    cd.polygon([(310, 91), (345, 118), (310, 145)], fill=WHITE)
    txt(cd, (40, 252), "A community voice", 27, INK, True)
    txt(cd, (40, 293), "Press play. Listen from anywhere.", 17, MUTED)
    # Beat-reactive waveform scrubber.
    for i in range(48):
        h = 8 + int(27 * abs(math.sin(i * .57 + t * math.tau)))
        col = ORANGE if i < int(8 + 35 * t / 4) else "#e6eeea"
        cd.rounded_rectangle((42 + i * 11, 356 - h // 2, 48 + i * 11, 356 + h // 2), radius=3, fill=col)
    txt(cd, (42, 390), "03:18", 13, MUTED)
    txt(cd, (595, 390), "04:06", 13, MUTED, anchor="ra")
    pulse = pop((t % BEAT) / BEAT)
    cx, cy = 640, 350
    q = [(cx - 325 * pulse, cy - 200 * pulse), (cx + 296 * pulse, cy - 218 * pulse),
         (cx + 328 * pulse, cy + 188 * pulse), (cx - 294 * pulse, cy + 204 * pulse)]
    project_card(im, card, q)
    cursor(d, 495 + ease(t / 2) * 152, 470, .65 < t < .9)
    return im


def contribute_scene(t: float) -> Image.Image:
    im, d = blank("#f5faf8")
    txt(d, (66, 62), "SHARE YOUR STORY", 18, ORANGE, True)
    txt(d, (66, 100), "Your voice. Your credit.", 40, INK, True)
    card, cd = rounded_card((760, 426), WHITE)
    cd.rounded_rectangle((20, 20, 740, 74), radius=18, fill="#f2f6f3")
    for i, c in enumerate(["#f19d85", YELLOW, "#7cc79f"]):
        cd.ellipse((40 + i * 25, 39, 53 + i * 25, 52), fill=c)
    txt(cd, (132, 36), "Story workspace", 16, MUTED, True)
    cd.ellipse((46, 112, 104, 170), fill=CREAM)
    cd.ellipse((65, 121, 85, 141), fill=ORANGE)
    cd.arc((55, 137, 95, 176), 180, 360, fill=ORANGE, width=8)
    txt(cd, (127, 108), "A story from my neighborhood", 23, INK, True)
    txt(cd, (127, 147), "Draft saved · attribution stays yours", 15, MUTED)
    cd.rounded_rectangle((40, 206, 430, 375), radius=17, fill="#f7faf8", outline="#e8efeb", width=2)
    txt(cd, (64, 226), "A planning prompt", 16, ORANGE, True)
    txt(cd, (64, 269), "What should listeners", 18, INK)
    txt(cd, (64, 298), "remember about this place?", 18, INK)
    cd.rounded_rectangle((454, 206, 720, 375), radius=17, fill=CREAM)
    logo(cd, 493, 244, 25, t * 130)
    txt(cd, (523, 232), "AI can help", 16, INK, True)
    txt(cd, (480, 286), "You choose what", 16, MUTED)
    txt(cd, (480, 313), "to keep and share.", 16, MUTED)
    pulse = pop((t % BEAT) / BEAT)
    q = [(248, 176), (1008, 143), (1038, 570), (278, 605)]
    q = [(630 + (x - 630) * pulse, 390 + (y - 390) * pulse) for x, y in q]
    project_card(im, card, q)
    # Small floating credit badge lands with a bounce.
    badge, bd = rounded_card((240, 78), "#fffef8")
    logo(bd, 44, 39, 28, t * 160)
    txt(bd, (79, 26), "YOUR CREDIT", 15, INK, True)
    txt(bd, (79, 48), "stays attached", 13, MUTED)
    bob = math.sin(t * math.tau) * 8
    project_card(im, badge, [(908, 560 + bob), (1150, 548 + bob), (1158, 623 + bob), (916, 635 + bob)])
    cursor(d, 440 + ease(t / 3.2) * 425, 462 - math.sin(t * math.pi * 2) * 18, t > 3.4)
    return im


def review_scene(t: float) -> Image.Image:
    im, d = blank("#fff8f1")
    txt(d, (68, 62), "MADE WITH CARE", 18, ORANGE, True)
    txt(d, (68, 99), "AI assists. People decide.", 40, INK, True)
    card, cd = rounded_card((650, 350), WHITE)
    cd.ellipse((42, 44, 112, 114), fill="#e7f2ec")
    cd.ellipse((65, 54, 89, 79), fill="#559572")
    cd.arc((53, 73, 101, 120), 180, 360, fill="#559572", width=10)
    txt(cd, (138, 50), "A person reviews each story", 24, INK, True)
    txt(cd, (138, 87), "Consent · credit · context", 16, MUTED)
    cd.line((42, 151, 608, 151), fill="#e5eeea", width=2)
    for i, (line, color) in enumerate([("Contributor credit", MINT), ("Story context", CREAM), ("Media consent", "#e9efff")]):
        y = 177 + i * 47
        cd.rounded_rectangle((46, y, 69, y + 23), radius=7, fill=color)
        cd.line((52, y + 12, 58, y + 18, 66, y + 7), fill="#559572", width=3)
        txt(cd, (87, y + 1), line, 17, INK)
    pulse = pop((t % BEAT) / BEAT)
    q = [(338, 190), (956, 158), (982, 494), (360, 525)]
    q = [(660 + (x - 660) * pulse, 358 + (y - 358) * pulse) for x, y in q]
    project_card(im, card, q)
    # A seal rotates in and settles like an editorial approval stamp.
    seal = Image.new("RGBA", (190, 190), (0, 0, 0, 0))
    sd = ImageDraw.Draw(seal)
    sd.ellipse((8, 8, 182, 182), fill=ORANGE, outline=WHITE, width=7)
    sd.ellipse((22, 22, 168, 168), outline=WHITE, width=3)
    sd.text((95, 72), "HUMAN", font=fnt(23, True), fill=WHITE, anchor="mm")
    sd.text((95, 105), "REVIEW", font=fnt(23, True), fill=WHITE, anchor="mm")
    turn = int(-22 + 22 * ease(t / 1.4))
    seal = seal.rotate(turn, resample=Image.Resampling.BICUBIC, expand=True)
    im.paste(seal, (900, 425), seal)
    cursor(d, 1065 - ease(t / 3) * 248, 562, t > 3.45)
    return im


def finale_scene(t: float) -> Image.Image:
    im, d = blank("#f8fbf9")
    # Orbital rings and confetti move on the 120 BPM grid.
    cx, cy = 640, 245
    pulse = pop((t % BEAT) / BEAT)
    for radius, color, width in [(104, "#e8f1ed", 5), (144, "#f3e2d4", 3), (185, "#edf2ef", 2)]:
        rr = radius * pulse
        d.ellipse((cx - rr, cy - rr * .62, cx + rr, cy + rr * .62), outline=color, width=width)
    logo(d, cx, cy, int(104 * pulse), t * 76)
    for i in range(26):
        angle = i * math.tau / 26 + t * .5
        radius = 225 + 16 * math.sin(t * math.tau + i)
        x, y = cx + math.cos(angle) * radius, cy + math.sin(angle) * radius * .68
        color = [ORANGE, YELLOW, MINT, BLUE][i % 4]
        if i % 3:
            d.ellipse((x - 5, y - 5, x + 5, y + 5), fill=color)
        else:
            d.polygon([(x, y - 7), (x + 5, y), (x, y + 7), (x - 5, y)], fill=color)
    txt(d, (640, 435), "ASANTE", 62, INK, True, "mm")
    txt(d, (640, 496), "Every story has a place.", 25, MUTED, anchor="mm")
    d.rounded_rectangle((490, 552, 790, 606), radius=27, fill=INK)
    txt(d, (640, 565), "Explore · Listen · Share", 18, WHITE, True, "mm")
    cursor(d, 451 + ease(t / 4) * 382, 540, t > 4.4)
    return im


SCENES = [hero_scene, discover_scene, listen_scene, contribute_scene, review_scene, finale_scene]


def render_scene(index: int, local: float) -> Image.Image:
    return SCENES[index](local)


def frame_at(t: float) -> Image.Image:
    index = len(SECTIONS) - 1
    local = t - SECTIONS[-1][0]
    for i, (start, end) in enumerate(SECTIONS):
        if start <= t < end:
            index, local = i, t - start
            break
    current = render_scene(index, local)
    # Every editorial cut lands on a downbeat, with a quick swish-like crossfade.
    start = SECTIONS[index][0]
    transition = .16
    if index > 0 and t - start < transition:
        previous = render_scene(index - 1, SECTIONS[index - 1][1] - SECTIONS[index - 1][0] - .01)
        current = Image.blend(previous, current, ease((t - start) / transition))
    # White flash and a warm beat pulse accent key transitions and strong beats.
    beat_phase = t % BEAT
    if beat_phase < .045:
        strength = (1 - beat_phase / .045) * .18
        current = Image.blend(current, Image.new("RGB", (W, H), CREAM), strength)
    return current


def make_music(path: Path) -> None:
    rate, count = 48000, 48000 * DURATION
    chords = [(130.81, 164.81, 196.00, 246.94), (98.00, 123.47, 146.83, 196.00),
              (110.00, 138.59, 164.81, 220.00), (87.31, 110.00, 130.81, 174.61)]
    melody = [523.25, 659.25, 783.99, 659.25, 587.33, 739.99, 880.00, 739.99,
              523.25, 659.25, 783.99, 987.77, 698.46, 880.00, 1046.5, 880.00]
    rng = random.Random(19)
    noise = [rng.uniform(-1, 1) for _ in range(int(rate * .12))]
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(rate)
        block = bytearray()
        for i in range(count):
            t = i / rate
            beat_index = int(t / BEAT)
            beat_time = t - beat_index * BEAT
            chord = chords[int(t // 4) % len(chords)]
            pad = sum(math.sin(math.tau * hz * t) + .14 * math.sin(math.tau * hz * 2 * t)
                      for hz in chord) / 5
            bass_hz = chord[0] / 2
            bass = math.sin(math.tau * bass_hz * t) * math.exp(-3.1 * beat_time)
            note = melody[(beat_index // 2) % len(melody)]
            pluck_phase = (t * 2) % 1
            pluck = math.sin(math.tau * note * t) * math.exp(-5 * pluck_phase)
            kick = math.sin(math.tau * (78 - 36 * min(1, beat_time / .16)) * beat_time) * math.exp(-23 * beat_time)
            clap = 0.0
            beat_in_bar = beat_index % 4
            if beat_in_bar in (1, 3) and beat_time < .11:
                clap = noise[int(beat_time * rate)] * math.exp(-32 * beat_time)
            fade = min(1.0, t / .6, (DURATION - t) / 1.2)
            sample = (pad * .035 + bass * .10 + pluck * .045 + kick * .15 + clap * .045) * fade
            value = int(max(-1, min(1, sample)) * 32767)
            block.extend(value.to_bytes(2, "little", signed=True) * 2)
            if len(block) >= 65536:
                out.writeframesraw(block)
                block.clear()
        if block:
            out.writeframesraw(block)


def main() -> None:
    ffmpeg, say = shutil.which("ffmpeg"), shutil.which("say")
    if not ffmpeg or not say:
        raise SystemExit("This renderer needs ffmpeg and macOS `say` for narration.")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    narration = ("Stories live in the places we share. With Asante, discover community voices on a map. "
                 "Tap a place, press play, and listen from anywhere. Share your story in your own words "
                 "and keep your credit. AI can help you plan. People review every submission before it "
                 "is published. Asante. Every story has a place.")
    with tempfile.TemporaryDirectory(prefix="asante-upbeat-") as temp_name:
        temp = Path(temp_name)
        silent, voice, music = temp / "visual.mp4", temp / "voice.aiff", temp / "music.wav"
        speech = subprocess.run([say, "-v", "Tessa", "-r", "187", "-o", str(voice), narration],
                                capture_output=True, text=True)
        if speech.returncode:
            raise SystemExit(f"Voiceover generation failed: {speech.stderr.strip()}")
        make_music(music)
        encoder = subprocess.Popen([
            ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pixel_format", "rgb24",
            "-video_size", f"{W}x{H}", "-framerate", str(FPS), "-i", "-", "-an",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(silent),
        ], stdin=subprocess.PIPE)
        assert encoder.stdin is not None
        for frame in range(FPS * DURATION):
            encoder.stdin.write(frame_at(frame / FPS).tobytes())
        encoder.stdin.close()
        if encoder.wait() != 0:
            raise SystemExit("Video frame encoding failed.")
        subprocess.run([
            ffmpeg, "-y", "-loglevel", "error", "-i", str(silent), "-i", str(voice), "-i", str(music),
            "-filter_complex", "[1:a]aresample=48000,volume=1.3,afade=t=out:st=21:d=1.4[vo];"
            "[2:a]volume=0.7,afade=t=out:st=22:d=2[bg];[vo][bg]amix=inputs=2:duration=longest:normalize=0[a]",
            "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-t", str(DURATION), "-movflags", "+faststart", str(OUTPUT),
        ], check=True)
    print(f"Rendered {OUTPUT}")


if __name__ == "__main__":
    main()
