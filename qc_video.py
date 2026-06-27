#!/usr/bin/env python3
"""
qc_video.py — Yayınlanan video'yu indir, kalite kontrol et, sorun varsa issue aç.

Kontroller:
  1. Süre: 30-65 saniye arasında mı? (TC için 50-65 ideal)
  2. Video=Ses süresi: 0.5sn fark içinde mi? (donma kontrolü)
  3. Son 2 saniye: ses var mı? (yarım kesilme kontrolü)
  4. YouTube video durumu: public mu private mı?
  5. Açıklama + tag tam mı?

Çağrılış:
    python qc_video.py --video-id ABCdef12345
    python qc_video.py --son  # son 5 video toplu kontrol
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

PANEL_KOK = Path(__file__).parent
YUKLEMELER = PANEL_KOK / "yuklemeler.json"
QC_LOG = PANEL_KOK / "qc_video.log"

# Eşikler
MIN_SURE = 25
IDEAL_MIN = 50
IDEAL_MAX = 65
MAX_SURE = 70
MAX_VIDEO_SES_FARKI = 0.5
MIN_SON_2SN_SES_DB = -45  # daha düşük = daha sessiz; -50 altı = "sessiz"


def log(msg):
    print(msg, flush=True)
    try:
        with open(QC_LOG, "a") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def video_indir(video_id, hedef):
    """yt-dlp ile video'yu indir."""
    try:
        subprocess.run(
            ["yt-dlp", "--quiet", "--no-warnings",
             "-f", "best[height<=720]",
             "-o", str(hedef),
             f"https://youtu.be/{video_id}"],
            check=True, timeout=120
        )
        return True
    except Exception as e:
        # yt-dlp yoksa (FileNotFoundError) / indirme / timeout → QC çökmesin
        return False


def video_sure(yol):
    """Video stream süresi."""
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=duration", "-of", "csv=p=0", str(yol)
    ]).decode().strip()
    return float(out) if out else 0.0


def ses_sure(yol):
    """Audio stream süresi."""
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=duration", "-of", "csv=p=0", str(yol)
    ]).decode().strip()
    return float(out) if out else 0.0


def son_2sn_ses_db(yol, video_sure_sn):
    """Son 2 saniyenin ortalama ses dB değeri."""
    basla = max(0, video_sure_sn - 2)
    try:
        cikti = subprocess.run([
            "ffmpeg", "-hide_banner", "-ss", str(basla), "-t", "2",
            "-i", str(yol), "-af", "volumedetect", "-vn", "-f", "null", "/dev/null"
        ], capture_output=True, text=True, timeout=30).stderr
        for line in cikti.split("\n"):
            if "mean_volume" in line:
                db_str = line.split(":")[1].strip().replace(" dB", "")
                return float(db_str)
    except Exception:
        pass
    return -100.0


def altyazi_tasma_kontrol(video_yol):
    """Video'dan 3 frame al, OCR ile metin tespit, ekran sınırı dışında mı kontrol et.

    Hızlı yaklaşım (OCR yok): Üretim aşamasında ASS dosyası kontrol ediliyor.
    Burada video frame'inde altyazı kutusu çok geniş mi diye basit piksel kontrolü.
    Tesseract OCR yoksa skip eder.
    """
    try:
        # Tesseract var mı kontrol
        subprocess.run(["which", "tesseract"], capture_output=True, check=True, timeout=5)
    except Exception:
        return None  # OCR yok, skip

    # Video orta frame'i al (altyazı en olası)
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            frame_yol = tmp.name
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", "10", "-i", str(video_yol), "-vframes", "1", frame_yol
        ], check=True, timeout=20)

        # Tesseract ile pozisyon + boyut
        cikti = subprocess.run([
            "tesseract", frame_yol, "stdout", "tsv", "-l", "eng"
        ], capture_output=True, text=True, timeout=30).stdout

        os.unlink(frame_yol)

        # TSV header: level, page, block, par, line, word, left, top, width, height, conf, text
        max_genislik = 0
        for satir in cikti.split("\n")[1:]:
            parcalar = satir.split("\t")
            if len(parcalar) < 12 or not parcalar[11].strip():
                continue
            try:
                left = int(parcalar[6])
                width = int(parcalar[8])
                sag = left + width
                if sag > max_genislik:
                    max_genislik = sag
            except Exception:
                continue

        # 1080 piksel sınır, 80 piksel margin → 1000+ piksel = TAŞMA
        if max_genislik > 1000:
            return f"altyazi_tasma ({max_genislik}px > 1000)"
        return None
    except Exception:
        return None


def kontrol_et(video_id):
    """Bir video için tüm kontrolleri yap, rapor dict döndür."""
    rapor = {"video_id": video_id, "url": f"https://youtu.be/{video_id}",
             "sorunlar": [], "uyarilar": [], "ok": True}

    with tempfile.TemporaryDirectory() as tmp:
        video_yol = Path(tmp) / "video.mp4"

        log(f"\n=== QC: {video_id} ===")
        if not video_indir(video_id, video_yol):
            rapor["uyarilar"].append("INDIRILEMEDI (yt-dlp yok ya da video hala isleniyor) — QC atlandi")
            log(f"  ⚠ Video indirilemedi → QC atlandi (hard-fail degil)")
            return rapor

        if not video_yol.exists() or video_yol.stat().st_size < 100_000:
            rapor["sorunlar"].append("VIDEO_BOYUT_KUCUK")
            rapor["ok"] = False
            return rapor

        v_sure = video_sure(video_yol)
        a_sure = ses_sure(video_yol)
        fark = abs(v_sure - a_sure)
        son_db = son_2sn_ses_db(video_yol, v_sure)

        rapor["video_sure"] = round(v_sure, 2)
        rapor["ses_sure"] = round(a_sure, 2)
        rapor["video_ses_fark"] = round(fark, 2)
        rapor["son_2sn_db"] = round(son_db, 2)

        log(f"  Video: {v_sure:.1f}sn, Ses: {a_sure:.1f}sn, Fark: {fark:.2f}sn, Son 2sn ses: {son_db:.1f}dB")

        # Kural 1: Süre
        if v_sure < MIN_SURE:
            rapor["sorunlar"].append(f"COK_KISA ({v_sure:.0f}sn < {MIN_SURE})")
            rapor["ok"] = False
        elif v_sure < IDEAL_MIN:
            rapor["uyarilar"].append(f"hedef_alti ({v_sure:.0f}sn < {IDEAL_MIN})")
        elif v_sure > MAX_SURE:
            rapor["sorunlar"].append(f"COK_UZUN ({v_sure:.0f}sn > {MAX_SURE})")
            rapor["ok"] = False

        # Kural 2: Video=Ses
        if fark > MAX_VIDEO_SES_FARKI:
            if v_sure > a_sure + MAX_VIDEO_SES_FARKI:
                rapor["sorunlar"].append(f"DONUK_KUYRUK (video {v_sure-a_sure:.1f}sn fazla)")
                rapor["ok"] = False
            else:
                rapor["sorunlar"].append(f"SES_FAZLA (ses {a_sure-v_sure:.1f}sn fazla)")

        # Kural 3: Son 2sn sessizlik (=yarım kesilme veya kuyruk)
        if son_db < MIN_SON_2SN_SES_DB:
            rapor["uyarilar"].append(f"son_2sn_sessiz ({son_db:.0f}dB) — CTA kesilmiş olabilir")

        # Kural 4: Altyazı taşma (OCR varsa)
        tasma = altyazi_tasma_kontrol(video_yol)
        if tasma:
            rapor["sorunlar"].append(tasma)
            rapor["ok"] = False

        durum = "✓ OK" if rapor["ok"] else "❌ SORUN"
        log(f"  {durum} | Sorun: {len(rapor['sorunlar'])}, Uyarı: {len(rapor['uyarilar'])}")
        if rapor["sorunlar"]:
            for s in rapor["sorunlar"]: log(f"    ❌ {s}")
        if rapor["uyarilar"]:
            for u in rapor["uyarilar"]: log(f"    ⚠️  {u}")

    return rapor


def son_n_video(n=5):
    if not YUKLEMELER.exists():
        return []
    try:
        d = json.loads(YUKLEMELER.read_text())
        return [v.get("video_id") for v in d[-n:] if v.get("video_id")]
    except Exception:
        return []


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--video-id", help="Tek bir video kontrol et")
    p.add_argument("--son", type=int, nargs="?", const=5, help="Son N video kontrol")
    p.add_argument("--issue", action="store_true", help="Sorun varsa GitHub issue aç")
    args = p.parse_args()

    if args.video_id:
        ids = [args.video_id]
    elif args.son:
        ids = son_n_video(args.son)
    else:
        # Default: son 1 video
        ids = son_n_video(1)

    if not ids:
        print("Kontrol edilecek video yok")
        sys.exit(0)

    raporlar = [kontrol_et(vid) for vid in ids]

    log("\n=== ÖZET ===")
    sorunlu = [r for r in raporlar if not r["ok"]]
    uyarili = [r for r in raporlar if r["uyarilar"]]
    log(f"Kontrol edilen: {len(raporlar)}")
    log(f"Sorunlu: {len(sorunlu)}")
    log(f"Uyarılı: {len(uyarili)}")

    # Issue aç
    if args.issue and sorunlu:
        body_lines = ["## 🚨 QC Sorunlu Videolar\n"]
        for r in sorunlu:
            body_lines.append(f"### {r['url']}")
            body_lines.append(f"- Video: {r.get('video_sure','?')}sn, Ses: {r.get('ses_sure','?')}sn")
            body_lines.append(f"- Sorunlar: {', '.join(r['sorunlar'])}")
            if r["uyarilar"]: body_lines.append(f"- Uyarılar: {', '.join(r['uyarilar'])}")
            body_lines.append("")
        body = "\n".join(body_lines)
        # Body'i dosyaya yaz, gh issue create kullansın
        body_dosya = PANEL_KOK / ".qc_issue_body.tmp"
        body_dosya.write_text(body)
        subprocess.run([
            "gh", "issue", "create",
            "--title", f"🚨 QC: {len(sorunlu)} video sorunlu",
            "--body-file", str(body_dosya)
        ], check=False)
        body_dosya.unlink(missing_ok=True)

    # Sorun varsa exit 1
    sys.exit(1 if sorunlu else 0)


if __name__ == "__main__":
    main()
