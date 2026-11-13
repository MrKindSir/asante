#!/usr/bin/env python3
"""Render a refined, original Asante motion promo with a tempo-changing score."""

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
OUTPUT = ROOT / "documentation/project/assets/media/asante-motion-promo-commercial.mp4"
W, H, FPS, DURATION = 1280, 720, 30, 26
INK, GREEN, GREY = "#202e2b", "#3b5b50", "#78817b"
GOLD, COPPER, PAPER = "#b78954", "#c26c43", "#f6f3ed"
PALE, MINT, WHITE = "#e8ede7", "#d7e0d7", "#fffefa"
SANS = "/System/Library/Fonts/Supplemental/Arial.ttf"
SANS_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
SERIF = "/System/Library/Fonts/Supplemental/Georgia.ttf"
SERIF_BOLD = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
SECTIONS = [(0, 4), (4, 10), (10, 16), (16, 21), (21, 26)]


def font(size: int, serif: bool = False, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = SERIF_BOLD if serif and bold else SERIF if serif else SANS_BOLD if bold else SANS
    return ImageFont.truetype(path, size)


def write(d: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, size: int,
          color: str = INK, *, serif: bool = False, bold: bool = False,
          anchor: str | None = None) -> None:
    d.text(xy, value, font=font(size, serif, bold), fill=color, anchor=anchor)


def ease(v: float) -> float:
    v = max(0.0, min(1.0, v))
    return v * v * (3 - 2 * v)


def canvas(bg: str = PAPER) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGB", (W, H), bg)
    return im, ImageDraw.Draw(im)


def card(size: tuple[int, int], fill: str = WHITE) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((2, 2, size[0] - 3, size[1] - 3), radius=21,
                        fill=fill, outline="#deded6", width=2)
    return im, d


def solve(matrix: list[list[float]], vals: list[float]) -> list[float]:
    rows = [r[:] + [v] for r, v in zip(matrix, vals)]
    for c in range(8):
        p = max(range(c, 8), key=lambda i: abs(rows[i][c]))
        rows[c], rows[p] = rows[p], rows[c]
        div = rows[c][c]
        for j in range(c, 9):
            rows[c][j] /= div
        for r in range(8):
            if r != c:
                factor = rows[r][c]
                for j in range(c, 9):
                    rows[r][j] -= factor * rows[c][j]
    return [rows[i][8] for i in range(8)]


def project(canvas_im: Image.Image, artwork: Image.Image,
            quad: list[tuple[float, float]], shadow: bool = True) -> None:
    left, top = int(min(p[0] for p in quad)), int(min(p[1] for p in quad))
    right, bottom = int(max(p[0] for p in quad)), int(max(p[1] for p in quad))
    out_points = [(x - left, y - top) for x, y in quad]
    in_points = [(0, 0), (artwork.width - 1, 0),
                 (artwork.width - 1, artwork.height - 1), (0, artwork.height - 1)]
    matrix: list[list[float]] = []
    vals: list[float] = []
    for (x, y), (u, v) in zip(out_points, in_points):
        matrix.extend([[x, y, 1, 0, 0, 0, -x * u, -y * u],
                       [0, 0, 0, x, y, 1, -x * v, -y * v]])
        vals.extend([u, v])
    coeffs = solve(matrix, vals)
    size = (max(1, right - left), max(1, bottom - top))
    warped = artwork.transform(size, Image.Transform.PERSPECTIVE, coeffs,
                               resample=Image.Resampling.BICUBIC)
    if shadow:
        shadow_art = Image.new("RGBA", artwork.size, (28, 43, 37, 0))
        shadow_art.putalpha(artwork.getchannel("A").point(lambda a: int(a * .18)))
        shadow_warp = shadow_art.transform(size, Image.Transform.PERSPECTIVE, coeffs,
                                           resample=Image.Resampling.BICUBIC)
        shadow_canvas = Image.new("RGBA", canvas_im.size, (0, 0, 0, 0))
        shadow_canvas.alpha_composite(shadow_warp, (left, top + 16))
        shadow_canvas = shadow_canvas.filter(ImageFilter.GaussianBlur(18))
        canvas_im.paste(shadow_canvas, (0, 0), shadow_canvas)
    canvas_im.paste(warped, (left, top), warped)


def brandmark(d: ImageDraw.ImageDraw, x: int, y: int, size: int) -> None:
    d.ellipse((x - size // 2, y - size // 2, x + size // 2, y + size // 2), outline=GOLD, width=2)
    d.ellipse((x - size // 6, y - size // 6, x + size // 6, y + size // 6), fill=COPPER)
    d.line((x, y - size // 2 - 5, x, y - size // 2 + 4), fill=GOLD, width=2)


def pointer(d: ImageDraw.ImageDraw, x: float, y: float, click: bool = False) -> None:
    if click:
        d.ellipse((x - 19, y - 19, x + 19, y + 19), outline=GOLD, width=2)
    d.polygon([(x, y), (x, y + 25), (x + 7, y + 18), (x + 13, y + 31),
               (x + 18, y + 28), (x + 12, y + 16), (x + 23, y + 15)],
              fill=INK, outline=WHITE, width=2)


def header(d: ImageDraw.ImageDraw, section: str, x: int = 72, y: int = 62) -> None:
    brandmark(d, x + 8, y + 8, 22)
    write(d, (x + 30, y), "ASANTE", 13, GREEN, bold=True)
    d.line((x + 106, y + 8, x + 143, y + 8), fill=GOLD, width=1)
    write(d, (x + 156, y), section.upper(), 12, GREY, bold=True)


def map_panel(d: ImageDraw.ImageDraw, t: float) -> None:
    d.rounded_rectangle((0, 0, 660, 390), radius=14, fill="#e9eee7")
    # A restrained isometric neighbourhood with fine roads and landmark pins.
    for row in range(4):
        for col in range(6):
            x = 28 + col * 95 + (row % 2) * 22
            y = 28 + row * 78
            w = 47 + 4 * math.sin(t * 1.2 + row + col)
            h = 13
            d.polygon([(x, y + 22), (x + w, y), (x + w + 25, y + 14), (x + 25, y + 36)], fill="#d1dbd0")
            d.polygon([(x + 25, y + 36), (x + w + 25, y + 14), (x + w + 25, y + 39), (x + 25, y + 61)], fill="#c1d0c3")
    roads = [[(18, 284), (155, 228), (280, 255), (388, 187), (640, 219)],
             [(88, 25), (188, 130), (295, 147), (385, 270), (540, 354)],
             [(320, 12), (300, 98), (410, 141), (463, 255), (606, 337)]]
    for points in roads:
        d.line(points, fill=WHITE, width=11, joint="curve")
        d.line(points, fill="#d7caba", width=2, joint="curve")
    route = [(110, 276), (235, 236), (342, 226), (440, 167), (555, 204)]
    d.line(route, fill=COPPER, width=4, joint="curve")
    for i, (x, y) in enumerate([route[0], route[2], route[4]]):
        r = 9 + int(2 * math.sin(t * 2 + i))
        d.ellipse((x-r, y-r, x+r, y+r), fill=COPPER, outline=WHITE, width=2)


def opener(t: float) -> Image.Image:
    im, d = canvas(PAPER)
    header(d, "COMMUNITY STORIES", 74, 60)
    # Thin architectural contours drift gently in the background.
    for i in range(8):
        d.arc((850 - i * 16, -90 - i * 8, 1430 + i * 16, 760 + i * 20), 65, 288,
              fill="#e7e1d6", width=1)
    write(d, (100, 187), "Every place", 63, INK, serif=True)
    write(d, (100, 264), "holds a story.", 63, INK, serif=True)
    d.line((104, 377, 328 + int(ease(t / 2.5) * 132), 377), fill=GOLD, width=2)
    write(d, (104, 401), "LISTEN  ·  DISCOVER  ·  SHARE", 14, GREEN, bold=True)
    write(d, (104, 595), "A new way to experience the stories connected to place.", 17, GREY)
    # A quiet map tile enters with a slow camera push.
    tile, td = card((365, 390), WHITE)
    map_panel(td, t)
    td.rounded_rectangle((26, 307, 339, 365), radius=9, fill=WHITE, outline="#e5dfd3")
    brandmark(td, 54, 336, 18)
    write(td, (76, 323), "STORIES WITHIN REACH", 12, GREEN, bold=True)
    scale = 1 + .012 * math.sin(t * 1.4)
    q = [(758, 190), (1122, 174), (1141, 570), (778, 587)]
    q = [(950 + (x - 950) * scale, 380 + (y - 380) * scale) for x, y in q]
    project(im, tile, q)
    pointer(d, 446 + ease(t / 3.2) * 228, 510 - ease(t / 3.2) * 64, 3.1 < t < 3.3)
    return im


def discovery(t: float) -> Image.Image:
    im, d = canvas("#f8f7f2")
    header(d, "DISCOVER", 72, 54)
    write(d, (72, 112), "A place is more than a pin.", 39, INK, serif=True)
    write(d, (74, 166), "Explore community stories, wherever you are.", 17, GREY)
    tile, td = card((710, 422), WHITE)
    map_panel(td, t)
    td.rounded_rectangle((22, 22, 285, 70), radius=8, fill=WHITE, outline="#e6e2d9")
    write(td, (42, 37), "Search stories or locations", 14, GREY)
    brandmark(td, 258, 46, 14)
    q = [(90, 229), (786, 166), (820, 585), (124, 639)]
    drift = math.sin(t * .9) * 4
    q = [(x, y + drift) for x, y in q]
    project(im, tile, q)
    # An elegant metadata card settles beside the map at the measured tempo.
    meta, md = card((320, 164), WHITE)
    md.rectangle((3, 3, 316, 13), fill=GOLD)
    write(md, (24, 37), "LISTENING NEAR YOU", 11, GOLD, bold=True)
    write(md, (24, 67), "A story from this place", 19, INK, serif=True)
    write(md, (24, 105), "Community voice  ·  4 min", 13, GREY)
    md.ellipse((255, 97, 290, 132), outline=COPPER, width=2)
    md.polygon([(268, 105), (281, 114), (268, 123)], fill=COPPER)
    project(im, meta, [(835, 459), (1144, 439), (1155, 596), (846, 615)])
    pointer(d, 390 + ease(t / 5.7) * 480, 390 + math.sin(t * 1.1) * 18, t > 5.35)
    return im


def listening(t: float) -> Image.Image:
    im, d = canvas("#f4f1e9")
    header(d, "LISTEN", 76, 58)
    write(d, (76, 151), "Hear the voice.", 49, INK, serif=True)
    write(d, (78, 212), "Feel the place.", 49, INK, serif=True)
    write(d, (80, 309), "One tap opens a story. Listening stays yours.", 17, GREY)
    # Quiet sound-wave engraving gives the left panel a tactile, editorial feel.
    for i in range(4):
        pts = []
        for x in range(84, 620, 5):
            amp = 17 + i * 11
            y = 475 + math.sin(x / 42 + t * 1.15 + i * .5) * amp
            pts.append((x, y))
        d.line(pts, fill=["#d8cdbd", "#c5d2c6", "#dec6ae", "#d7dfd6"][i], width=2)
    d.line((84, 541, 622, 541), fill="#d7d1c7", width=1)
    write(d, (84, 563), "REMOTE DISCOVERY", 11, GREEN, bold=True)
    write(d, (622, 563), "OPTIONAL LOCATION", 11, GREEN, bold=True, anchor="ra")
    player, pd = card((450, 540), WHITE)
    pd.rectangle((3, 3, 446, 250), fill="#e8ede7")
    # No stock footage: abstract relief lines represent a sense of place.
    for i in range(9):
        y = 46 + i * 22
        pd.arc((32 + i * 4, 15 + i * 5, 420 - i * 5, 241 - i * 3), 187, 353,
               fill="#ccd7cc", width=2)
    pd.ellipse((181, 86, 269, 174), fill=WHITE, outline="#d9ded6", width=2)
    pd.polygon([(215, 104), (246, 130), (215, 156)], fill=COPPER)
    write(pd, (30, 284), "A story from this place", 24, INK, serif=True)
    write(pd, (30, 326), "Original voice  ·  Landmark connected", 13, GREY)
    # Animated waveform, fine and restrained.
    for i in range(49):
        h = 7 + int(23 * abs(math.sin(i * .43 + t * 2)))
        x = 31 + i * 8
        pd.rounded_rectangle((x, 410 - h, x + 3, 410 + h), radius=2,
                             fill=COPPER if i < int(9 + 31 * t / 6) else "#e7e7e1")
    write(pd, (31, 453), "02:18", 11, GREY)
    write(pd, (418, 453), "04:06", 11, GREY, anchor="ra")
    q = [(730, 100), (1186, 128), (1161, 648), (708, 611)]
    project(im, player, q)
    pointer(d, 814 + ease(t / 5.5) * 318, 453 - ease(t / 5.5) * 255, 2.4 < t < 2.7)
    return im


def contribute(t: float) -> Image.Image:
    im, d = canvas("#f8f7f2")
    header(d, "CONTRIBUTE", 76, 58)
    write(d, (76, 143), "Your story,", 50, INK, serif=True)
    write(d, (76, 202), "in your own words.", 50, INK, serif=True)
    write(d, (79, 298), "Keep the voice. Keep the credit.", 17, GREY)
    write(d, (79, 544), "AI planning support is optional and bounded.", 13, GREEN, bold=True)
    editor, ed = card((710, 424), WHITE)
    ed.rounded_rectangle((18, 18, 692, 62), radius=7, fill="#f2f3ef")
    brandmark(ed, 43, 40, 16)
    write(ed, (64, 30), "STORY WORKSPACE", 12, GREEN, bold=True)
    write(ed, (40, 100), "A story from my neighborhood", 23, INK, serif=True)
    write(ed, (42, 142), "Draft  ·  saved for review", 13, GREY)
    ed.line((40, 177, 668, 177), fill="#e9e8e1", width=1)
    write(ed, (42, 201), "What would you like people to remember?", 15, GREY)
    for y, width in [(245, 585), (279, 548), (313, 460)]:
        ed.line((42, y, 42 + width, y), fill="#dadbd3", width=2)
    ed.rounded_rectangle((42, 348, 345, 399), radius=7, fill="#f6f4ee")
    brandmark(ed, 66, 373, 15)
    write(ed, (91, 359), "PLANNING SUPPORT", 10, GOLD, bold=True)
    write(ed, (91, 378), "You decide what belongs.", 12, GREEN)
    ed.rounded_rectangle((530, 348, 667, 399), radius=7, fill=GREEN)
    write(ed, (598, 365), "Save draft", 13, WHITE, bold=True, anchor="mm")
    q = [(396, 162), (1094, 132), (1127, 562), (431, 591)]
    project(im, editor, q)
    # A slim credit marker floats at the edge of the editor, with only a small parallax drift.
    d.rounded_rectangle((899, 594, 1121, 638), radius=5, fill=WHITE, outline="#dfd9ce", width=1)
    d.line((915, 616, 936, 616), fill=GOLD, width=2)
    write(d, (947, 604), "CONTRIBUTOR CREDIT", 10, GREEN, bold=True)
    pointer(d, 455 + ease(t / 4.7) * 473, 410 + math.sin(t * 1.2) * 8, t > 4.2)
    return im


def review(t: float) -> Image.Image:
    im, d = canvas(PAPER)
    header(d, "REVIEW", 76, 58)
    write(d, (76, 142), "Stories are shared", 48, INK, serif=True)
    write(d, (76, 198), "with care.", 48, INK, serif=True)
    write(d, (80, 292), "AI can help prepare. People make the call.", 17, GREY)
    write(d, (80, 548), "CONSENT  ·  CREDIT  ·  CONTEXT", 12, GREEN, bold=True)
    sheet, sd = card((610, 400), WHITE)
    brandmark(sd, 52, 55, 20)
    write(sd, (82, 41), "EDITORIAL REVIEW", 12, GOLD, bold=True)
    write(sd, (38, 103), "A story from this place", 23, INK, serif=True)
    write(sd, (40, 139), "Submitted by a community contributor", 13, GREY)
    sd.line((38, 175, 572, 175), fill="#e9e6de", width=1)
    for i, (a, b) in enumerate([("Attribution", "Contributor credit retained"),
                               ("Consent", "Media permission recorded"),
                               ("Context", "Human review required")]):
        y = 199 + i * 56
        sd.ellipse((42, y + 1, 61, y + 20), outline=GOLD, width=1)
        sd.line((47, y + 11, 52, y + 16, 58, y + 7), fill=GREEN, width=2)
        write(sd, (76, y - 2), a.upper(), 10, GREEN, bold=True)
        write(sd, (76, y + 15), b, 13, GREY)
    sd.rounded_rectangle((391, 342, 570, 379), radius=5, fill="#f5f3ed", outline="#e9e5dc")
    write(sd, (480, 352), "HUMAN DECISION", 11, GREEN, bold=True, anchor="mm")
    q = [(633, 170), (1230, 138), (1207, 566), (608, 593)]
    project(im, sheet, q)
    # A restrained foil-like seal settles at the card edge.
    seal = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    sd = ImageDraw.Draw(seal)
    sd.ellipse((4, 4, 124, 124), fill=GREEN, outline=WHITE, width=3)
    sd.ellipse((12, 12, 116, 116), outline="#b9cabc", width=1)
    sd.text((64, 50), "HUMAN", font=font(15, bold=True), fill=WHITE, anchor="mm")
    sd.text((64, 73), "REVIEW", font=font(15, bold=True), fill=WHITE, anchor="mm")
    seal = seal.rotate(int(5 - 5 * ease(t / 1.2)), resample=Image.Resampling.BICUBIC)
    im.paste(seal, (1032, 472), seal)
    pointer(d, 1070 - ease(t / 4.5) * 192, 574, t > 4.55)
    return im


def finale(t: float) -> Image.Image:
    im, d = canvas(PAPER)
    header(d, "ASANTE", 76, 57)
    # Quiet concentric topographic curves replace a loud logo burst.
    for i in range(9):
        pad = i * 18
        d.arc((432 - pad, 116 - pad // 2, 848 + pad, 475 + pad // 2), 192, 348,
              fill="#e4ded2", width=1)
    brandmark(d, 640, 255, int(72 + 3 * math.sin(t * .8)))
    write(d, (640, 382), "ASANTE", 56, INK, serif=True, anchor="mm")
    d.line((552, 423, 728, 423), fill=GOLD, width=1)
    write(d, (640, 462), "Stories, held in place.", 22, GREEN, serif=True, anchor="mm")
    write(d, (640, 579), "DISCOVER  ·  LISTEN  ·  SHARE", 12, GREY, bold=True, anchor="mm")
    pointer(d, 806 + ease(t / 4.8) * 55, 526, t > 4.55)
    return im


SCENES = [opener, discovery, listening, contribute, review, finale]
SCENE_SECTIONS = [(0, 4), (4, 10), (10, 16), (16, 21), (21, 26)]


def frame_at(t: float) -> Image.Image:
    idx = len(SCENES) - 1
    local = t - SCENE_SECTIONS[-1][0]
    for i, (start, end) in enumerate(SCENE_SECTIONS):
        if start <= t < end:
            idx, local = i, t - start
            break
    frame = SCENES[idx](local)
    # Dissolve on a beat: measured 0.3-second overlaps keep the transitions commercial.
    overlap = .30
    start = SCENE_SECTIONS[idx][0]
    if idx and t - start < overlap:
        old_end = SCENE_SECTIONS[idx - 1][1] - SCENE_SECTIONS[idx - 1][0] - .01
        previous = SCENES[idx - 1](old_end)
        frame = Image.blend(previous, frame, ease((t - start) / overlap))
    return frame


def tempo(t: float) -> int:
    if t < 4:
        return 72
    if t < 10:
        return 86
    if t < 16:
        return 100
    if t < 21:
        return 116
    return 72


def make_score(path: Path) -> None:
    rate, total = 48000, 48000 * DURATION
    chord_sets = [(110.0, 138.59, 164.81, 220.0), (98.0, 123.47, 146.83, 196.0),
                  (123.47, 155.56, 185.0, 246.94), (87.31, 110.0, 130.81, 174.61)]
    notes = [329.63, 392.0, 440.0, 392.0, 293.66, 369.99, 440.0, 493.88,
             329.63, 392.0, 493.88, 587.33, 293.66, 369.99, 440.0, 523.25]
    # Timecoded, original interface sound effects: soft taps, a map ping, and transition swells.
    click_times = [3.25, 7.12, 12.42, 19.38]
    ping_times = [6.55]
    whoosh_times = [3.9, 9.9, 15.9, 20.9]
    impact_times = [10.0, 16.0]
    rng = random.Random(42)
    noise = [rng.uniform(-1, 1) for _ in range(rate)]
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(rate)
        block = bytearray()
        for i in range(total):
            t = i / rate
            bpm = tempo(t)
            beat_len = 60 / bpm
            bar_len = beat_len * 4
            section_start = 0 if t < 4 else 4 if t < 10 else 10 if t < 16 else 16 if t < 21 else 21
            beat_phase = (t - section_start) % beat_len
            beat_no = int((t - section_start) / beat_len)
            chord = chord_sets[int(t // 6.5) % len(chord_sets)]
            pad = sum(math.sin(math.tau * f * t) + .20 * math.sin(math.tau * 2 * f * t) for f in chord) / 6
            # A soft, rounded piano-like pluck with a short second harmonic.
            note = notes[(beat_no // 2) % len(notes)]
            pluck_phase = beat_phase / beat_len
            pluck = (math.sin(math.tau * note * t) + .24 * math.sin(math.tau * note * 2 * t)) * math.exp(-5.5 * pluck_phase)
            bass = math.sin(math.tau * chord[0] / 2 * t) * math.exp(-4.0 * beat_phase)
            kick = math.sin(math.tau * (68 - 31 * min(1, beat_phase / .18)) * beat_phase) * math.exp(-22 * beat_phase)
            drums_gain = .10 if t < 4 else .26 if t < 10 else .34 if t < 16 else .40 if t < 21 else .12
            percussion = kick * drums_gain
            # Brushed snaps land on beats 2 and 4 after the score opens up.
            if t >= 4 and beat_no % 4 in (1, 3) and beat_phase < .075:
                percussion += noise[int(beat_phase * rate)] * math.exp(-38 * beat_phase) * .055
            music = pad * .055 + pluck * (.014 if t < 4 else .028) + bass * .065 + percussion
            sfx = 0.0
            for event in click_times:
                dt = t - event
                if 0 <= dt < .10:
                    sfx += (math.sin(math.tau * 1700 * dt) * math.exp(-43 * dt) * .13 +
                            noise[int(dt * rate)] * math.exp(-70 * dt) * .025)
            for event in ping_times:
                dt = t - event
                if 0 <= dt < .8:
                    sfx += (math.sin(math.tau * 1318 * dt) + .45 * math.sin(math.tau * 1976 * dt)) * math.exp(-5.4 * dt) * .075
            for event in whoosh_times:
                dt = t - (event - .32)
                if 0 <= dt < .42:
                    env = math.sin(math.pi * dt / .42) ** 1.5
                    n = noise[int(dt * rate) % len(noise)]
                    sfx += (n * .035 + math.sin(math.tau * (160 + 420 * dt) * dt) * .035) * env
            for event in impact_times:
                dt = t - event
                if 0 <= dt < .24:
                    sfx += (math.sin(math.tau * (78 - 36 * dt) * dt) * math.exp(-14 * dt) * .12)
            # Slow, elegant opening and close; the central build gains rhythmic energy.
            fade_in = min(1.0, t / 1.3)
            fade_out = min(1.0, (DURATION - t) / 1.7)
            master = min(fade_in, fade_out)
            sample = max(-.92, min(.92, (music + sfx) * master))
            value = int(sample * 32767)
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
    narration = ("Every place holds a story. Asante connects community voices to the landmarks they call home. "
                 "Discover a story, tap play, and listen from anywhere. Share your perspective in your own words, "
                 "with your credit intact. AI can help contributors plan. People review each story before publication. "
                 "Asante. Stories, held in place.")
    with tempfile.TemporaryDirectory(prefix="asante-commercial-") as temp_name:
        temp = Path(temp_name)
        silent, voice, score = temp / "visual.mp4", temp / "voice.aiff", temp / "score.wav"
        spoken = subprocess.run([say, "-v", "Tessa", "-r", "166", "-o", str(voice), narration],
                                capture_output=True, text=True)
        if spoken.returncode:
            raise SystemExit(f"Voiceover generation failed: {spoken.stderr.strip()}")
        make_score(score)
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
            ffmpeg, "-y", "-loglevel", "error", "-i", str(silent), "-i", str(voice), "-i", str(score),
            "-filter_complex", "[1:a]aresample=48000,volume=1.16,afade=t=out:st=23:d=1.5[vo];"
            "[2:a]volume=1.0[fx];[vo][fx]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.92[a]",
            "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-t", str(DURATION), "-movflags", "+faststart", str(OUTPUT),
        ], check=True)
    print(f"Rendered {OUTPUT}")


if __name__ == "__main__":
    main()
