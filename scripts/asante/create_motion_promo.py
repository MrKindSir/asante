#!/usr/bin/env python3
"""Render an original vector-style Asante promo with cursor, voice and music."""

from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "documentation/project/assets/media/asante-motion-promo.mp4"
W, H, FPS, DURATION = 1280, 720, 24, 19
INK, MUTED, ORANGE = "#20343b", "#708087", "#df8950"
PALE, LINE, WHITE = "#f7f8f6", "#e2e8e5", "#ffffff"
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(BOLD if bold else FONT, size)


def label(d: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, size: int,
          color: str = INK, bold: bool = False, anchor: str | None = None) -> None:
    d.text(xy, value, font=font(size, bold), fill=color, anchor=anchor)


def ease(v: float) -> float:
    v = max(0.0, min(1.0, v))
    return v * v * (3 - 2 * v)


def fade(t: float, length: float) -> float:
    return min(ease(t / .42), ease((length - t) / .4))


def base(bg: str = WHITE) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (W, H), bg)
    return image, ImageDraw.Draw(image)


def cursor(d: ImageDraw.ImageDraw, x: float, y: float, opacity: float = 1,
           clicked: bool = False) -> None:
    # Cursor is drawn as crisp vector geometry; opacity is handled by its fill color.
    if opacity <= 0.03:
        return
    if clicked:
        d.ellipse((x - 25, y - 25, x + 25, y + 25), fill="#f8e6d8")
    d.polygon([(x, y), (x, y + 34), (x + 9, y + 26), (x + 17, y + 42),
               (x + 24, y + 38), (x + 16, y + 23), (x + 29, y + 22)],
              fill="#263c43", outline=WHITE, width=3)


def map_background(d: ImageDraw.ImageDraw) -> None:
    # Decorative, abstract map lines; no third-party map or footage is used.
    curves = [
        [(0, 105), (195, 20), (290, 178), (435, 110), (640, 32), (835, 138), (1042, 188), (1280, 75)],
        [(0, 220), (165, 280), (260, 180), (420, 264), (645, 351), (815, 240), (1055, 208), (1280, 308)],
        [(0, 415), (190, 350), (290, 510), (450, 429), (684, 357), (852, 452), (1060, 540), (1280, 420)],
        [(0, 595), (167, 512), (300, 646), (442, 558), (680, 505), (824, 594), (1065, 650), (1280, 554)],
        [(212, 0), (167, 158), (280, 245), (220, 370), (188, 528), (275, 720)],
        [(520, 0), (446, 145), (580, 244), (530, 370), (478, 546), (591, 720)],
        [(900, 0), (820, 153), (960, 255), (883, 400), (878, 578), (970, 720)],
    ]
    for curve in curves:
        d.line(curve, fill=LINE, width=3, joint="curve")


def pin(d: ImageDraw.ImageDraw, x: int, y: int) -> None:
    d.ellipse((x - 17, y - 17, x + 17, y + 17), fill="#f8e6d8")
    d.ellipse((x - 10, y - 13, x + 10, y + 8), fill=ORANGE)
    d.polygon([(x - 8, y + 1), (x + 8, y + 1), (x, y + 15)], fill=ORANGE)
    d.ellipse((x - 3, y - 7, x + 3, y - 1), fill=WHITE)


def map_scene(t: float) -> Image.Image:
    im, d = base(PALE)
    map_background(d)
    label(d, (72, 70), "ASANTE  /  LISTEN", 18, ORANGE, True)
    label(d, (72, 113), "Stories belong", 44, INK, True)
    label(d, (72, 164), "to places.", 44, INK, True)
    d.rounded_rectangle((72, 235, 432, 293), radius=14, fill=WHITE, outline="#dce4e1", width=2)
    d.ellipse((92, 252, 110, 270), outline="#829196", width=2)
    d.line((107, 267, 117, 277), fill="#829196", width=2)
    label(d, (132, 252), "Find a story or a place", 17, MUTED)
    d.rounded_rectangle((74, 318, 264, 360), radius=21, fill=WHITE, outline=LINE)
    label(d, (169, 339), "All languages  ▾", 15, INK, True, "mm")
    for px, py in [(680, 210), (848, 390), (1004, 240), (1050, 520), (565, 515)]:
        pin(d, px, py)
    # Story card glides in as the cursor approaches a pin.
    card_x = int(775 + (1 - ease((t - 1.6) / .8)) * 450)
    d.rounded_rectangle((card_x, 388, card_x + 330, 592), radius=18, fill=WHITE, outline=LINE, width=2)
    d.rounded_rectangle((card_x + 18, 406, card_x + 312, 500), radius=12, fill="#e9eee9")
    d.line([(card_x + 20, 482), (card_x + 90, 455), (card_x + 166, 482),
            (card_x + 228, 449), (card_x + 310, 472)], fill="#d5dfda", width=8)
    d.ellipse((card_x + 157, 451, card_x + 177, 471), fill=ORANGE)
    label(d, (card_x + 20, 517), "A place with a story", 19, INK, True)
    label(d, (card_x + 20, 548), "Community voices · 4 min", 14, MUTED)
    d.ellipse((card_x + 261, 526, card_x + 305, 570), fill=ORANGE)
    d.polygon([(card_x + 278, 536), (card_x + 293, 548), (card_x + 278, 560)], fill=WHITE)
    x = 300 + ease((t - .5) / 2.4) * 590
    y = 380 - ease((t - .5) / 2.4) * 115
    cursor(d, x, y, clicked=2.85 < t < 3.25)
    return im


def player_scene(t: float) -> Image.Image:
    im, d = base(WHITE)
    label(d, (84, 53), "ASANTE  /  LISTEN", 18, ORANGE, True)
    label(d, (84, 93), "A story, ready", 42, INK, True)
    label(d, (84, 141), "when you are.", 42, INK, True)
    d.rounded_rectangle((355, 110, 925, 580), radius=24, fill=WHITE, outline=LINE, width=2)
    d.rounded_rectangle((382, 137, 898, 327), radius=16, fill="#f2f5f1")
    d.line([(398, 287), (480, 246), (540, 278), (628, 235), (694, 283), (780, 235), (882, 200)], fill="#cdd9d2", width=4)
    d.ellipse((596, 189, 682, 275), fill=ORANGE)
    d.polygon([(628, 210), (658, 232), (628, 254)], fill=WHITE)
    label(d, (402, 349), "A place with a story", 26, INK, True)
    label(d, (402, 382), "A community voice, connected to place", 16, MUTED)
    for i in range(52):
        h = 9 + int((math.sin(i * 1.7) ** 2) * 34)
        xx = 408 + i * 8.8
        color = ORANGE if i < int(11 + ease((t - 1.6) / 1.4) * 37) else "#e5eae7"
        d.rounded_rectangle((int(xx), 496 - h // 2, int(xx + 4), 496 + h // 2), radius=2, fill=color)
    label(d, (408, 526), "03:18", 13, MUTED)
    label(d, (872, 526), "04:06", 13, MUTED, anchor="ra")
    label(d, (640, 625), "Listen from anywhere. Your location stays optional.", 19, INK, True, "mm")
    cursor(d, 440 + ease((t - .5) / 2.2) * 125, 467, clicked=2.2 < t < 2.65)
    return im


def contributor_scene(t: float) -> Image.Image:
    im, d = base(PALE)
    label(d, (78, 49), "ASANTE  /  CONTRIBUTE", 18, ORANGE, True)
    label(d, (78, 91), "Keep your voice.", 42, INK, True)
    label(d, (78, 140), "Keep your credit.", 42, INK, True)
    d.rounded_rectangle((260, 220, 1030, 590), radius=20, fill=WHITE, outline=LINE, width=2)
    d.line((260, 280, 1030, 280), fill="#e7ece9", width=2)
    for x, color in [(290, "#e88972"), (312, "#e3bd70"), (334, "#75b990")]:
        d.ellipse((x - 7, 243, x + 7, 257), fill=color)
    label(d, (358, 240), "Story workspace", 17, MUTED, True)
    label(d, (304, 301), "A story from my neighborhood", 25, INK, True)
    label(d, (304, 337), "Draft  ·  Your words and attribution stay yours", 15, MUTED)
    d.rounded_rectangle((304, 397, 656, 536), radius=13, fill="#f8f9f7", outline="#edf0ee")
    label(d, (327, 410), "A helpful planning prompt", 15, ORANGE, True)
    label(d, (327, 449), "What would you like listeners", 16)
    label(d, (327, 475), "to remember about this place?", 16)
    d.rounded_rectangle((690, 397, 992, 536), radius=13, fill="#f7f4ef")
    d.ellipse((708, 418, 736, 446), fill="#f0dfcd")
    d.line((715, 432, 721, 438, 731, 425), fill="#9f704b", width=3)
    label(d, (750, 416), "AI can help you plan", 15, INK, True)
    label(d, (716, 458), "You choose what to keep", 15, MUTED)
    label(d, (716, 484), "and what to share.", 15, MUTED)
    d.rounded_rectangle((852, 548, 996, 584), radius=18, fill="#263c43")
    label(d, (924, 557), "Save draft", 14, WHITE, True, "mm")
    cursor(d, 410 + ease((t - .4) / 2) * 365, 482 - ease((t - .4) / 2) * 115,
           clicked=2.2 < t < 2.65)
    return im


def review_scene(t: float) -> Image.Image:
    im, d = base(WHITE)
    label(d, (80, 51), "ASANTE  /  REVIEW", 18, ORANGE, True)
    label(d, (80, 94), "AI assists.", 43, INK, True)
    label(d, (80, 143), "People decide.", 43, INK, True)
    d.rounded_rectangle((345, 240, 935, 540), radius=22, fill=WHITE, outline=LINE, width=2)
    d.ellipse((386, 284, 454, 352), fill="#f1e3d4")
    d.ellipse((409, 296, 431, 318), fill="#c68a5f")
    d.arc((398, 308, 442, 357), 185, 355, fill="#c68a5f", width=9)
    label(d, (478, 286), "A person reviews each story", 24, INK, True)
    label(d, (478, 321), "Consent · credit · context", 16, MUTED)
    d.line((398, 380, 878, 380), fill="#e7ece9", width=2)
    d.ellipse((406, 410, 434, 438), fill="#e6f1e9")
    d.line((413, 423, 419, 429, 428, 416), fill="#4d8e69", width=3)
    label(d, (450, 411), "Publication stays human-led", 17, INK, True)
    d.rounded_rectangle((713, 472, 877, 514), radius=21, fill="#263c43")
    label(d, (795, 480), "Review story", 15, WHITE, True, "mm")
    cursor(d, 860 - ease((t - .25) / 1.4) * 205, 443, clicked=1.65 < t < 2.05)
    return im


def end_scene(t: float) -> Image.Image:
    im, d = base(WHITE)
    d.ellipse((584, 218, 696, 330), fill="#faeee4")
    d.ellipse((600, 234, 680, 314), fill=ORANGE)
    d.ellipse((629, 263, 651, 285), fill=WHITE)
    label(d, (640, 350), "ASANTE", 58, INK, True, "mm")
    label(d, (640, 420), "Every story has a place.", 24, MUTED, anchor="mm")
    label(d, (640, 613), "COMMUNITY STORIES  ·  HUMAN VOICES  ·  SHARED WITH CARE", 12, MUTED, True, "mm")
    cursor(d, 930, 498, opacity=1 - ease((t - 1.2) / .8))
    return im


def first_scene(t: float) -> Image.Image:
    im, d = base(WHITE)
    d.ellipse((586, 192, 694, 300), fill="#faeee4")
    d.ellipse((601, 207, 679, 285), fill=ORANGE)
    d.ellipse((630, 236, 650, 256), fill=WHITE)
    label(d, (640, 335), "ASANTE", 60, INK, True, "mm")
    label(d, (640, 395), "Stories belong to places.", 23, MUTED, anchor="mm")
    cursor(d, 480 + ease(t / 1.7) * 295, 462, clicked=1.55 < t < 1.9)
    return im


def frame_at(t: float) -> Image.Image:
    if t < 2.4:
        im, start, length = first_scene(t), 0.0, 2.4
    elif t < 6.7:
        local = t - 2.4
        im, start, length = map_scene(local), 2.4, 4.3
    elif t < 10.5:
        local = t - 6.7
        im, start, length = player_scene(local), 6.7, 3.8
    elif t < 14.4:
        local = t - 10.5
        im, start, length = contributor_scene(local), 10.5, 3.9
    elif t < 17.2:
        local = t - 14.4
        im, start, length = review_scene(local), 14.4, 2.8
    else:
        local = t - 17.2
        im, start, length = end_scene(local), 17.2, 1.8
    alpha = fade(t - start, length)
    return Image.blend(Image.new("RGB", (W, H), WHITE), im, alpha)


def make_music(path: Path) -> None:
    rate = 48000
    count = rate * DURATION
    chords = [(130.81, 164.81, 196.00, 246.94), (98.00, 123.47, 146.83, 196.00),
              (110.00, 138.59, 164.81, 220.00), (87.31, 110.00, 130.81, 174.61)]
    notes = [261.63, 329.63, 392.00, 329.63, 293.66, 369.99, 440.00, 369.99,
             246.94, 311.13, 392.00, 311.13, 220.00, 293.66, 349.23, 293.66]
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(rate)
        block = bytearray()
        for i in range(count):
            t = i / rate
            pad = sum(math.sin(2 * math.pi * hz * t) + .18 * math.sin(4 * math.pi * hz * t)
                      for hz in chords[int(t // 4.75) % len(chords)]) / 5
            phase = (t * 2) % 1
            pluck = math.sin(2 * math.pi * notes[int(t * 2) % len(notes)] * t) * math.exp(-5.8 * phase)
            swell = min(1.0, t, (DURATION - t) / 1.2)
            sample = int(max(-1.0, min(1.0, (pad * .055 + pluck * .032) * swell)) * 32767)
            block.extend(sample.to_bytes(2, "little", signed=True) * 2)
            if len(block) >= 65536:
                out.writeframesraw(block)
                block.clear()
        if block:
            out.writeframesraw(block)


def main() -> None:
    ffmpeg, say = shutil.which("ffmpeg"), shutil.which("say")
    if not ffmpeg or not say:
        raise SystemExit("This renderer needs ffmpeg and macOS `say` for the voiceover.")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    narration = ("Every story begins somewhere. Asante connects community voices to the places "
                 "they call home. Explore stories on a map, and listen from anywhere. "
                 "Contributors keep their voice and credit. AI can help with planning; "
                 "people review before anything is published. Asante. Every story has a place.")
    with tempfile.TemporaryDirectory(prefix="asante-promo-") as temp_name:
        temp = Path(temp_name)
        silent_video, voice, music = temp / "video.mp4", temp / "voice.aiff", temp / "music.wav"
        generated_voice = subprocess.run([say, "-v", "Tessa", "-r", "175", "-o", str(voice), narration],
                                         capture_output=True, text=True)
        if generated_voice.returncode:
            raise SystemExit(f"Voiceover generation failed: {generated_voice.stderr.strip()}")
        make_music(music)
        encoder = subprocess.Popen([
            ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pixel_format", "rgb24",
            "-video_size", f"{W}x{H}", "-framerate", str(FPS), "-i", "-", "-an",
            "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(silent_video),
        ], stdin=subprocess.PIPE)
        assert encoder.stdin is not None
        for frame in range(FPS * DURATION):
            encoder.stdin.write(frame_at(frame / FPS).tobytes())
        encoder.stdin.close()
        if encoder.wait() != 0:
            raise SystemExit("Video frame encoding failed.")
        subprocess.run([
            ffmpeg, "-y", "-loglevel", "error", "-i", str(silent_video), "-i", str(voice), "-i", str(music),
            "-filter_complex", "[1:a]aresample=48000,volume=1.15,afade=t=out:st=17.5:d=1.4[vo];"
            "[2:a]volume=0.42,afade=t=out:st=17.5:d=1.4[bg];[vo][bg]amix=inputs=2:duration=longest:normalize=0[a]",
            "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-t", str(DURATION), "-movflags", "+faststart", str(OUTPUT),
        ], check=True)
    print(f"Rendered {OUTPUT}")


if __name__ == "__main__":
    main()
