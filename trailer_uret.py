#!/usr/bin/env python3
"""
trailer_uret.py — TrendCatcher kanal trailer (~25 sn).

Shorts üretim motorunu yeniden kullan: Pexels video + Wikimedia foto +
ASS altyazı + ses mux. TC shorts'larıyla aynı kalite.

Çıktı: branding/trailer.mp4 (1080x1920)
"""
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import seslendirici
import montajci

PANEL = Path(__file__).parent
BRANDING = PANEL / "branding"
GECICI = PANEL / "trailer_gecici"
GECICI.mkdir(parents=True, exist_ok=True)
BRANDING.mkdir(exist_ok=True)
# montajci'nin GECICI_KLASOR'ü ön-oluştur
Path(montajci.GECICI_KLASOR).mkdir(exist_ok=True)
if hasattr(montajci, "CIKTI_KLASOR"):
    Path(montajci.CIKTI_KLASOR).mkdir(exist_ok=True)

SCRIPT = """Welcome to TrendCatcher.

Wild facts in 30 seconds. Extreme animals, anomaly places, the planet's strangest survivors — four new shorts every day.

Hit subscribe. The wild is waiting."""

# TC nişi — Pexels'ten doğa/vahşi yaşam videoları
KEYWORDS = ["wild eagle flying", "tropical jungle nature", "mountain landscape"]


def log(msg):
    print(f"[trailer] {msg}", flush=True)


def main():
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg yok")

    mp3 = BRANDING / "trailer.mp3"
    ass = BRANDING / "trailer.ass"
    txt = BRANDING / "trailer.txt"
    final = BRANDING / "trailer.mp4"

    txt.write_text(SCRIPT, encoding="utf-8")

    log("1) seslendirici → MP3 + ASS üretiliyor...")
    seslendirici.seslendir(SCRIPT, mp3, ass)
    sure = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(mp3)
    ]).decode().strip())
    log(f"   ✓ ses {sure:.2f}sn")

    log("2) Pexels API anahtarı kontrol...")
    api_key = montajci._pexels_anahtarini_oku()
    log(f"   ✓ key len={len(api_key)}")

    klip_basi = sure / len(KEYWORDS)
    log(f"3) {len(KEYWORDS)} klip indiriliyor (her biri {klip_basi:.1f}sn)...")
    ham_klipler = []
    for i, kw in enumerate(KEYWORDS, 1):
        ham = GECICI / f"ham_{i}.mp4"
        bilgi = montajci.gorsel_kaynak_indir(kw, ham, klip_basi, api_key, baslik="TrendCatcher Trailer")
        log(f"   #{i} '{kw}' → {bilgi.get('fotograf','?')} ({ham.stat().st_size//1024} KB)")
        ham_klipler.append(ham)

    log(f"4) Klipler 1080x1920 normalize ediliyor...")
    normal_klipler = []
    for i, ham in enumerate(ham_klipler, 1):
        normal = GECICI / f"normal_{i}.mp4"
        montajci.klip_kirp_normalize(ham, normal, klip_basi)
        normal_klipler.append(normal)
        log(f"   #{i} → {normal.stat().st_size//1024} KB")

    log("5) Concat birleşik...")
    birlesik = GECICI / "birlesik.mp4"
    montajci.klipleri_birlestir(normal_klipler, birlesik)

    log("6) Altyazı (libass) yakılıyor...")
    altyazili = GECICI / "altyazili.mp4"
    montajci.altyazi_yak(birlesik, ass, altyazili)

    log("7) Ses mux (TTS + opsiyonel müzik)...")
    muzik = None
    try:
        import suno_kutuphane
        suno_yolu = suno_kutuphane.track_sec(KEYWORDS[0])
        if suno_yolu and Path(suno_yolu).exists():
            muzik = GECICI / "bgm.mp3"
            shutil.copy(suno_yolu, muzik)
            log(f"   Müzik (Suno): {Path(suno_yolu).name}")
    except Exception as e:
        log(f"   Müzik atlandı: {e}")

    montajci.ses_mux(altyazili, mp3, final, muzik)

    log("")
    log("=== ÖZET ===")
    log(f"  Video: {final}  ({sure:.1f}sn, {final.stat().st_size//1024} KB)")
    log(f"  Sonraki: python3 trailer_yukle.py")

    shutil.rmtree(GECICI, ignore_errors=True)


if __name__ == "__main__":
    main()
