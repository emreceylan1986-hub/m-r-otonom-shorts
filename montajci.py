"""
montajci.py — Shorts Video Montaj Üreticisi

Akış (her adım terminale yazılır):
    1) En son MP3 + senaryo TXT bulunur (ses_ciktilari/)
    2) MP3 süresi mutagen ile okunur
    3) Senaryo Gemini'ye verilir → 3 görsel arama anahtar kelimesi çıkarılır
    4) Pexels Videos API'den her keyword için 9:16 portrait HD klip indirilir
    5) Her klip MP3 süresinin 1/3'üne ffmpeg ile kırpılır + 1080×1920'a normalize
    6) ffmpeg concat ile birleştirilir
    7) MP3 ses parçası ffmpeg ile mux'lenir → final 1080×1920 MP4

Çıktı: sorts_ciktilari/shorts_<damga>.mp4
"""

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

import imageio_ffmpeg
import requests
from mutagen.mp3 import MP3

import bridge


PANEL_KOK = Path(__file__).parent
SES_KLASORU = PANEL_KOK / "ses_ciktilari"
GECICI_KLASOR = PANEL_KOK / "gecici_video"
CIKTI_KLASOR = PANEL_KOK / "shorts_ciktilari"

PEXELS_ARAMA_URL = "https://api.pexels.com/videos/search"
HEDEF_GENISLIK = 1080
HEDEF_YUKSEKLIK = 1920
KLIP_SAYISI = 3
ISTEK_ZAMAN_ASIMI = 30
INDIRME_ZAMAN_ASIMI = 90

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


KEYWORD_SISTEM_PROMPTU = """You output ONLY a JSON array of exactly 3 short
visual stock-footage search queries (1–3 English words each) that would
visually illustrate the given Shorts script. Pick concrete, photographable
subjects (people, objects, places). Avoid abstract concepts.

Format example: ["office workers typing", "courtroom judge gavel", "robotic arm assembly"]
"""


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
def _adim(numara: int, mesaj: str) -> None:
    print(f"\n[montajcı · adım {numara}] {mesaj}", flush=True)


def _alt(mesaj: str) -> None:
    print(f"   ↳ {mesaj}", flush=True)


def _pexels_anahtarini_oku() -> str:
    if os.environ.get("PEXELS_API_KEY"):
        return os.environ["PEXELS_API_KEY"]
    env = PANEL_KOK / ".env"
    if env.exists():
        for satir in env.read_text(encoding="utf-8").splitlines():
            if satir.startswith("PEXELS_API_KEY="):
                return satir.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(
        "PEXELS_API_KEY .env dosyasında veya environment'ta yok. "
        "https://www.pexels.com/api adresinden ücretsiz al."
    )


def _en_son_dosya(klasor: Path, desen: str) -> Path:
    adaylar = sorted(klasor.glob(desen), key=lambda p: p.stat().st_mtime, reverse=True)
    if not adaylar:
        raise FileNotFoundError(f"Bulunamadı: {klasor}/{desen}")
    return adaylar[0]


def _ffmpeg_calistir(args: list[str]) -> None:
    sonuc = subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True,
        text=True,
    )
    if sonuc.returncode != 0:
        raise RuntimeError(f"ffmpeg hata: {sonuc.stderr.strip()}")


# ---------------------------------------------------------------------------
# Adımlar
# ---------------------------------------------------------------------------
_DAMGA_RE = re.compile(r"_(\d{8}_\d{6})\.")


def _damga(yol: Path) -> str:
    eslesme = _DAMGA_RE.search(yol.name)
    if not eslesme:
        raise RuntimeError(f"Dosya adında zaman damgası yok: {yol.name}")
    return eslesme.group(1)


def en_son_seslendirmeyi_al() -> tuple[Path, Path, float]:
    """En son MP3'ü bulur ve AYNI zaman damgalı senaryo TXT'sini eşleştirir."""
    mp3 = _en_son_dosya(SES_KLASORU, "seslendirme_*.mp3")
    damga = _damga(mp3)
    txt = SES_KLASORU / f"senaryo_{damga}.txt"
    if not txt.exists():
        raise FileNotFoundError(
            f"MP3 ile eşleşen senaryo yok: {txt.name} (damga {damga})"
        )
    sure = MP3(mp3).info.length
    return mp3, txt, sure


def keywordleri_uret(senaryo: str) -> list[str]:
    yanit = bridge.gemini_metin_uret(
        prompt=f"Script:\n{senaryo}",
        sistem_promptu=KEYWORD_SISTEM_PROMPTU,
        sicaklik=0.4,
        max_token=512,
    )
    eslesme = re.search(r"\[.*?\]", yanit, re.DOTALL)
    if not eslesme:
        raise RuntimeError(f"Keyword çıkışı JSON dizi değil:\n{yanit}")
    keywords = json.loads(eslesme.group(0))
    if not isinstance(keywords, list) or len(keywords) != KLIP_SAYISI:
        raise RuntimeError(
            f"Tam {KLIP_SAYISI} keyword bekleniyordu, gelen: {keywords!r}"
        )
    return [str(k).strip() for k in keywords]


def pexels_video_indir(keyword: str, hedef: Path, api_key: str) -> dict:
    yanit = requests.get(
        PEXELS_ARAMA_URL,
        params={"query": keyword, "orientation": "portrait", "size": "medium", "per_page": 8},
        headers={"Authorization": api_key},
        timeout=ISTEK_ZAMAN_ASIMI,
    )
    yanit.raise_for_status()
    veri = yanit.json()
    videolar = veri.get("videos") or []
    if not videolar:
        raise RuntimeError(f"'{keyword}' için Pexels'te portrait video yok.")

    en_iyi_dosya = None
    en_iyi_video = None
    for v in videolar:
        for f in v.get("video_files", []):
            if f.get("width", 0) < f.get("height", 0):  # portrait emniyet
                if en_iyi_dosya is None or (f.get("height", 0) > en_iyi_dosya.get("height", 0)):
                    en_iyi_dosya = f
                    en_iyi_video = v
        if en_iyi_dosya:
            break

    if not en_iyi_dosya:
        raise RuntimeError(f"'{keyword}' için portrait dosyası yok.")

    indirme = requests.get(en_iyi_dosya["link"], stream=True, timeout=INDIRME_ZAMAN_ASIMI)
    indirme.raise_for_status()
    with open(hedef, "wb") as f:
        for parca in indirme.iter_content(chunk_size=1 << 15):
            f.write(parca)

    return {
        "keyword": keyword,
        "url": en_iyi_dosya["link"],
        "boyut": (en_iyi_dosya.get("width"), en_iyi_dosya.get("height")),
        "sure": en_iyi_video.get("duration"),
        "fotograf": en_iyi_video.get("user", {}).get("name", "?"),
    }


def klip_kirp_normalize(kaynak: Path, hedef: Path, sure_sn: float) -> None:
    """
    Kaynağı 1080×1920'a normalize eder ve TAM `sure_sn` saniyeye getirir.
    Kaynak yetmezse `-stream_loop -1` ile döngüye alır → çıktı süresi garanti.
    """
    filtre = (
        f"scale={HEDEF_GENISLIK}:{HEDEF_YUKSEKLIK}:force_original_aspect_ratio=increase,"
        f"crop={HEDEF_GENISLIK}:{HEDEF_YUKSEKLIK},setsar=1"
    )
    _ffmpeg_calistir(
        [
            "-stream_loop", "-1",
            "-i", str(kaynak),
            "-t", f"{sure_sn:.3f}",
            "-vf", filtre,
            "-r", "30",
            "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            str(hedef),
        ]
    )


def klipleri_birlestir(klipler: list[Path], hedef: Path) -> None:
    liste = GECICI_KLASOR / "concat_list.txt"
    liste.write_text("\n".join(f"file '{p.resolve()}'" for p in klipler), encoding="utf-8")
    _ffmpeg_calistir(
        [
            "-f", "concat", "-safe", "0",
            "-i", str(liste),
            "-c", "copy",
            str(hedef),
        ]
    )


def ses_mux(video: Path, mp3: Path, hedef: Path) -> None:
    _ffmpeg_calistir(
        [
            "-i", str(video),
            "-i", str(mp3),
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            str(hedef),
        ]
    )


# ---------------------------------------------------------------------------
# Ana akış
# ---------------------------------------------------------------------------
def main() -> int:
    try:
        GECICI_KLASOR.mkdir(exist_ok=True)
        CIKTI_KLASOR.mkdir(exist_ok=True)

        _adim(1, "En son seslendirme bulunuyor...")
        mp3, txt, sure_sn = en_son_seslendirmeyi_al()
        damga = _damga(mp3)  # final MP4 kaynak MP3 ile aynı damgayı taşısın
        _alt(f"MP3:    {mp3.name}")
        _alt(f"TXT:    {txt.name}")
        _alt(f"Süre:   {sure_sn:.2f} saniye")

        senaryo = txt.read_text(encoding="utf-8").strip()
        klip_basina = sure_sn / KLIP_SAYISI

        _adim(2, "Pexels API anahtarı kontrol ediliyor...")
        api_key = _pexels_anahtarini_oku()
        _alt(f"PEXELS_API_KEY uzunluğu: {len(api_key)} karakter ✓")

        _adim(3, "Senaryo Gemini'ye → 3 görsel arama keyword'ü...")
        keywords = keywordleri_uret(senaryo)
        for k in keywords:
            _alt(k)

        _adim(4, f"Pexels'ten her keyword için 1 portrait klip indiriliyor (klip başına {klip_basina:.2f} sn)...")
        ham_klipler: list[Path] = []
        for sira, kw in enumerate(keywords, 1):
            ham = GECICI_KLASOR / f"ham_{damga}_{sira}.mp4"
            bilgi = pexels_video_indir(kw, ham, api_key)
            ham_klipler.append(ham)
            _alt(
                f"#{sira} '{kw}' → {bilgi['boyut'][0]}×{bilgi['boyut'][1]}, "
                f"kaynak süre {bilgi['sure']}s, Pexels: {bilgi['fotograf']} "
                f"({ham.stat().st_size/1024:.0f} KB)"
            )

        _adim(5, f"Her klip 1080×1920'a kırpılıp normalize ediliyor...")
        normal_klipler: list[Path] = []
        for sira, ham in enumerate(ham_klipler, 1):
            normal = GECICI_KLASOR / f"normal_{damga}_{sira}.mp4"
            klip_kirp_normalize(ham, normal, klip_basina)
            normal_klipler.append(normal)
            _alt(f"#{sira} → {normal.name} ({normal.stat().st_size/1024:.0f} KB)")

        _adim(6, "Klipler ffmpeg concat ile birleştiriliyor...")
        birlesik = GECICI_KLASOR / f"birlesik_{damga}.mp4"
        klipleri_birlestir(normal_klipler, birlesik)
        _alt(f"birlesik → {birlesik.name} ({birlesik.stat().st_size/1024:.0f} KB)")

        _adim(7, "MP3 ses ile mux'lanıyor → final MP4...")
        final = CIKTI_KLASOR / f"shorts_{damga}.mp4"
        ses_mux(birlesik, mp3, final)
        boyut_mb = final.stat().st_size / (1024 * 1024)
        _alt(f"FİNAL: {final.name} ({boyut_mb:.2f} MB)")

        print(f"\n[montajcı] HAZIR ✓  → {final}")
        return 0

    except FileNotFoundError as hata:
        print(f"[montajcı] Veri eksik: {hata}", file=sys.stderr)
        return 2
    except requests.RequestException as hata:
        print(f"[montajcı] Pexels/HTTP hatası: {hata}", file=sys.stderr)
        return 3
    except RuntimeError as hata:
        print(f"[montajcı] Çalışma hatası: {hata}", file=sys.stderr)
        return 4
    except OSError as hata:
        print(f"[montajcı] Dosya/sistem hatası: {hata}", file=sys.stderr)
        return 5
    finally:
        if GECICI_KLASOR.exists():
            shutil.rmtree(GECICI_KLASOR, ignore_errors=True)
            print(f"[montajcı] Geçici klasör temizlendi: {GECICI_KLASOR.name}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
