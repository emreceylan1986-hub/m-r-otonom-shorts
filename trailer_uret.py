#!/usr/bin/env python3
"""
trailer_uret.py — TrendCatcher kanal trailer (~24 sn).

STRATEJİ: Pillow ile telifsiz vahşi-doğa temalı sahneler. Her sahne için
gradient + parıltı noktaları + büyük doğa sembolü.

Çıktı:
    branding/trailer.mp4    1080x1920
"""
import asyncio
import random
import shutil
import subprocess
import sys
from pathlib import Path

import edge_tts
from PIL import Image, ImageDraw, ImageFilter

PANEL = Path(__file__).parent
BRANDING = PANEL / "branding"
SAHNE_DIR = BRANDING / "trailer_sahneler"
SAHNE_DIR.mkdir(parents=True, exist_ok=True)

W, H = 1080, 1920

# 7 sahne (TC vahşi-doğa teması)
SAHNE = [
    {"ust": "WELCOME TO",     "alt": "TRENDCATCHER",    "palet": [(180, 120, 30), (40, 25, 5)],  "yildiz": 100, "sembol": "🌍"},
    {"ust": "WILD FACTS",     "alt": "IN 30 SECONDS",   "palet": [(40, 120, 60), (5, 25, 10)],   "yildiz": 80,  "sembol": "🦅"},
    {"ust": "EAGLES HUNT",    "alt": "GOATS OFF CLIFFS","palet": [(140, 80, 30), (25, 15, 5)],   "yildiz": 90,  "sembol": "🏔️"},
    {"ust": "LAKES",          "alt": "THAT BOIL",       "palet": [(180, 50, 40), (30, 5, 5)],    "yildiz": 70,  "sembol": "🌋"},
    {"ust": "TINY CREATURES", "alt": "BIG SURVIVAL",    "palet": [(60, 100, 140), (5, 15, 30)],  "yildiz": 120, "sembol": "🦎"},
    {"ust": "4 NEW SHORTS",   "alt": "EVERY DAY",       "palet": [(80, 140, 50), (10, 25, 10)],  "yildiz": 90,  "sembol": "🐆"},
    {"ust": "HIT",            "alt": "SUBSCRIBE",       "palet": [(200, 60, 80), (30, 10, 15)],  "yildiz": 100, "sembol": "🔔"},
]

SCRIPT = """Welcome to TrendCatcher.

Wild facts in 30 seconds — extreme animals, anomaly places, and the planet's strangest survivors.

Eagles that hunt goats off cliffs. Lakes that boil. Creatures that shouldn't exist.

Four new shorts every day.

Hit subscribe. The wild is waiting."""

SES = "en-US-AriaNeural"
HIZ = "-10%"
PERDE = "+3Hz"


def log(msg):
    print(f"[trailer] {msg}", flush=True)


def sahne_png_uret(i: int, cfg: dict) -> Path:
    cikti = SAHNE_DIR / f"sahne_{i:02d}.png"
    merkez, kenar = cfg["palet"]
    img = Image.new("RGB", (W, H), kenar)
    px = img.load()

    cx, cy = W // 2, int(H * 0.45)
    max_r = ((W // 2) ** 2 + (H // 2) ** 2) ** 0.5
    for y in range(H):
        for x in range(0, W, 4):
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            t = min(d / max_r, 1.0)
            r = int(merkez[0] * (1 - t) + kenar[0] * t)
            g = int(merkez[1] * (1 - t) + kenar[1] * t)
            b = int(merkez[2] * (1 - t) + kenar[2] * t)
            for dx in range(4):
                if x + dx < W:
                    px[x + dx, y] = (r, g, b)

    # Parıltı noktaları (TC için ateş kıvılcımı / yaprak gibi)
    draw = ImageDraw.Draw(img)
    rng = random.Random(i * 1337)
    for _ in range(cfg["yildiz"]):
        x = rng.randint(0, W - 1)
        y = rng.randint(0, H - 1)
        boy = rng.choices([1, 2, 3], weights=[60, 30, 10])[0]
        parlaklik = rng.randint(180, 255)
        draw.ellipse([x - boy, y - boy, x + boy, y + boy],
                     fill=(parlaklik, parlaklik - 30, max(0, parlaklik - 80)))

    img = img.filter(ImageFilter.GaussianBlur(radius=0.5))

    # Sembol BÜYÜK
    try:
        from PIL import ImageFont
        font_emoji = ImageFont.truetype("/System/Library/Fonts/Apple Color Emoji.ttc", size=160)
        draw2 = ImageDraw.Draw(img)
        sembol = cfg["sembol"]
        bbox = draw2.textbbox((0, 0), sembol, font=font_emoji, embedded_color=True)
        tw = bbox[2] - bbox[0]
        draw2.text(((W - tw) // 2, int(H * 0.20)), sembol, font=font_emoji, embedded_color=True)
    except Exception as e:
        log(f"   ⚠ emoji: {e}")

    img.save(cikti, "PNG", optimize=True)
    return cikti


def sahne_video_yap(i: int, png: Path, ust_text: str, alt_text: str, sure: float, cikti: Path):
    fps = 30
    toplam_frame = int(sure * fps)
    safe_ust = ust_text.replace("'", "\\'")
    safe_alt = alt_text.replace("'", "\\'")

    vf = (
        f"scale=1080:1920,setsar=1,"
        f"zoompan=z='min(zoom+0.0008,1.10)':d={toplam_frame}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps={fps},"
        f"drawtext=fontfile=/System/Library/Fonts/Helvetica.ttc:"
        f"text='{safe_ust}':fontcolor=white:fontsize=100:borderw=4:bordercolor=black@0.8:"
        f"x=(w-text_w)/2:y=h*0.50:"
        f"alpha='if(lt(t,0.3),t/0.3,if(gt(t,{sure-0.3}),({sure}-t)/0.3,1))',"
        f"drawtext=fontfile=/System/Library/Fonts/Helvetica.ttc:"
        f"text='{safe_alt}':fontcolor=white:fontsize=140:borderw=5:bordercolor=black@0.85:"
        f"x=(w-text_w)/2:y=h*0.62:"
        f"alpha='if(lt(t,0.5),(t-0.2)/0.3,if(gt(t,{sure-0.3}),({sure}-t)/0.3,1))',"
        "format=yuv420p"
    )
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(png),
        "-vf", vf,
        "-t", f"{sure:.2f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        str(cikti),
    ]
    sonuc = subprocess.run(cmd, capture_output=True)
    if sonuc.returncode != 0:
        sys.stderr.write(sonuc.stderr.decode()[-2000:])
        raise SystemExit(f"sahne {i} hata")


async def ses_uret(mp3_yol: Path):
    iletisim = edge_tts.Communicate(text=SCRIPT, voice=SES, rate=HIZ, pitch=PERDE)
    await iletisim.save(str(mp3_yol))


def ses_suresi(mp3: Path) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", str(mp3)]
    return float(subprocess.check_output(cmd).decode().strip())


def sahneleri_birlestir(sahne_mp4: list, ses_mp3: Path, cikti: Path):
    liste = BRANDING / "trailer_concat.txt"
    liste.write_text("\n".join(f"file '{p.resolve()}'" for p in sahne_mp4))
    silent_v = BRANDING / "trailer_silent.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(liste),
         "-c", "copy", str(silent_v)],
        check=True, capture_output=True,
    )
    wav = ses_mp3.with_suffix(".wav")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(ses_mp3), "-ar", "48000", "-ac", "2", str(wav)],
        check=True, capture_output=True,
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(silent_v),
        "-i", str(wav),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-shortest",
        str(cikti),
    ]
    sonuc = subprocess.run(cmd, capture_output=True)
    if sonuc.returncode != 0:
        sys.stderr.write(sonuc.stderr.decode()[-1500:])
        raise SystemExit(1)


def main():
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg yok")

    (BRANDING / "trailer.txt").write_text(SCRIPT, encoding="utf-8")

    log("1) Sahne PNG'leri üretiliyor...")
    png_yollari = []
    for i, cfg in enumerate(SAHNE):
        png = sahne_png_uret(i, cfg)
        log(f"   ✓ sahne {i+1}/{len(SAHNE)}: {cfg['ust']} {cfg['alt']}")
        png_yollari.append(png)

    log("2) Edge-TTS ses üretiliyor...")
    mp3 = BRANDING / "trailer.mp3"
    asyncio.run(ses_uret(mp3))
    toplam_ses = ses_suresi(mp3)
    log(f"   Ses süresi: {toplam_ses:.2f}sn")

    log("3) Sahne videoları üretiliyor...")
    pay = toplam_ses / len(SAHNE)
    sahne_mp4 = []
    for i, (cfg, png) in enumerate(zip(SAHNE, png_yollari)):
        cikti = SAHNE_DIR / f"sahne_{i:02d}.mp4"
        sahne_video_yap(i, png, cfg["ust"], cfg["alt"], pay, cikti)
        sahne_mp4.append(cikti)

    log("4) Birleştirme + ses mux...")
    final = BRANDING / "trailer.mp4"
    sahneleri_birlestir(sahne_mp4, mp3, final)

    for p in png_yollari + sahne_mp4:
        p.unlink(missing_ok=True)
    (BRANDING / "trailer_silent.mp4").unlink(missing_ok=True)
    (BRANDING / "trailer_concat.txt").unlink(missing_ok=True)

    log("")
    log("=== ÖZET ===")
    log(f"  Video: {final}  ({toplam_ses:.1f}sn)")
    log(f"  Sonraki: python3 trailer_yukle.py")


if __name__ == "__main__":
    main()
