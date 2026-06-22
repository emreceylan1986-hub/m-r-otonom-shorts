#!/usr/bin/env python3
"""
trailer_uret.py — TrendCatcher kanal trailer (~45 sn) üretir.

Çıktı:
    branding/trailer.mp4    (1080x1920, ~45 sn)
    branding/trailer.mp3
    branding/trailer.txt
"""
import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

import edge_tts

PANEL = Path(__file__).parent
BRANDING = PANEL / "branding"
BRANDING.mkdir(exist_ok=True)

SCRIPT = """Welcome to TrendCatcher.

Wild facts about extreme animals, anomaly places, and the planet's strangest survivors.

Eagles that hunt goats off cliffs. Lakes that boil. Creatures that shouldn't exist.

Four new shorts every day, at 3 PM, 7 PM, 10 PM, and 1 AM.

For the curious. For the explorer. For anyone who still wonders.

Hit subscribe. The wild is waiting."""

SATIRLAR = [
    ("Welcome to", 1.6),
    ("TrendCatcher", 1.8),
    ("Wild facts about", 1.7),
    ("extreme animals", 1.7),
    ("anomaly places", 1.7),
    ("and the planet's", 1.6),
    ("strangest survivors", 2.0),
    ("Eagles that hunt", 1.6),
    ("goats off cliffs", 1.8),
    ("Lakes that boil", 1.5),
    ("Creatures that", 1.4),
    ("shouldn't exist", 1.7),
    ("Four new shorts", 1.6),
    ("every day", 1.4),
    ("at 3 PM, 7 PM", 1.9),
    ("10 PM and 1 AM", 2.0),
    ("For the curious", 1.6),
    ("For the explorer", 1.6),
    ("For anyone who", 1.4),
    ("still wonders", 1.7),
    ("Hit subscribe", 1.8),
    ("The wild is waiting", 2.2),
]

SES = "en-US-AriaNeural"
HIZ = "-10%"
PERDE = "+3Hz"
SES_SEVIYESI = "+0%"


def log(msg):
    print(f"[trailer] {msg}", flush=True)


async def ses_uret(mp3_yol: Path):
    log("1) Edge-TTS ses üretiliyor (Aria, -10%)...")
    iletisim = edge_tts.Communicate(text=SCRIPT, voice=SES, rate=HIZ, pitch=PERDE, volume=SES_SEVIYESI)
    await iletisim.save(str(mp3_yol))
    log(f"   ✓ MP3 yazıldı: {mp3_yol}")


def ses_suresi(mp3_yol: Path) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", str(mp3_yol)]
    return float(subprocess.check_output(cmd).decode().strip())


def ass_dosyasi_yaz(ass_yol: Path, sure: float):
    log("2) ASS altyazı yazılıyor...")
    toplam_ag = sum(a for _, a in SATIRLAR)
    olcek = sure / toplam_ag

    ass_basligi = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,2,5,80,80,200,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def sn_ass(s):
        h = int(s // 3600); s -= h * 3600
        m = int(s // 60); s -= m * 60
        return f"{h}:{m:02d}:{s:05.2f}"

    satir_olaylari = []
    t = 0.0
    for text, ag in SATIRLAR:
        bas = t
        bit = t + ag * olcek
        satir_olaylari.append(f"Dialogue: 0,{sn_ass(bas)},{sn_ass(bit)},Default,,0,0,0,,{text.upper()}")
        t = bit

    ass_yol.write_text(ass_basligi + "\n".join(satir_olaylari) + "\n", encoding="utf-8")
    log(f"   ✓ ASS yazıldı: {len(satir_olaylari)} satır, {sure:.1f}sn")


def banner_dikey(banner_2048: Path, cikti_dikey: Path):
    log("3) Banner dikey arka plana adapte ediliyor (blur + center)...")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(banner_2048),
        "-vf",
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        "boxblur=20:1,setsar=1",
        "-frames:v", "1",
        str(cikti_dikey),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    log(f"   ✓ Dikey BG: {cikti_dikey}")


def video_montaj(bg_dikey: Path, mp3: Path, ass: Path, cikti: Path, sure: float):
    log("4) Final video montajlanıyor (Ken Burns + altyazı + WAV ses)...")
    wav = mp3.with_suffix(".wav")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp3), "-ar", "48000", "-ac", "2", str(wav)],
        check=True, capture_output=True,
    )
    fps = 30
    toplam_frame = int(sure * fps)
    vf = (
        f"loop=loop=-1:size=1,setpts=N/{fps}/TB,"
        f"zoompan=z='min(zoom+0.0006,1.15)':d={toplam_frame}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps={fps},"
        f"format=yuv420p,subtitles={ass}"
    )
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(bg_dikey),
        "-i", str(wav),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-pix_fmt", "yuv420p",
        "-t", f"{sure:.2f}",
        "-shortest",
        str(cikti),
    ]
    sonuc = subprocess.run(cmd, capture_output=True)
    if sonuc.returncode != 0:
        log("FFMPEG HATA:")
        sys.stderr.write(sonuc.stderr.decode()[-2000:])
        raise SystemExit(1)
    log(f"   ✓ Final video: {cikti}")


def main():
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg gerekli (brew install ffmpeg)")

    banner = BRANDING / "banner.png"
    if not banner.exists():
        raise SystemExit(f"banner yok: {banner}")

    mp3 = BRANDING / "trailer.mp3"
    ass = BRANDING / "trailer.ass"
    bg = BRANDING / "trailer_bg.png"
    final = BRANDING / "trailer.mp4"
    script_yol = BRANDING / "trailer.txt"

    script_yol.write_text(SCRIPT, encoding="utf-8")
    log(f"Script kaydedildi: {script_yol}")

    asyncio.run(ses_uret(mp3))
    sure = ses_suresi(mp3)
    log(f"Ses süresi: {sure:.2f}sn")

    ass_dosyasi_yaz(ass, sure)
    banner_dikey(banner, bg)
    video_montaj(bg, mp3, ass, final, sure)

    log("")
    log("=== ÖZET ===")
    log(f"  Video: {final}")
    log(f"  Süre: {sure:.1f}sn")
    log(f"  Sonraki adım: python3 trailer_yukle.py")


if __name__ == "__main__":
    main()
