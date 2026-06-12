"""
post_upload.py — Yayın sonrası enrichment pipeline.

yukleyici.py'nin başarıyla bıraktığı .basarili_yayin JSON'unu okur ve
sırasıyla:
    1) Thumbnail üret + YouTube'a set (youtube.upload scope)
    2) Pinterest'e pin oluştur (varsa PINTEREST_TOKEN)
    3) Multilang caption yükle (TR/ES/PT)

Hepsi continue-on-error mantığıyla — biri fail ederse diğerleri akar.

Kullanım:
    python post_upload.py  # .basarili_yayin'i okur, hepsini çağırır
"""
import json, os, sys, subprocess
from pathlib import Path

PANEL_KOK = Path(__file__).parent
BASARILI = PANEL_KOK / ".basarili_yayin"


def _veri_oku() -> dict:
    if not BASARILI.exists():
        print("[post_upload] .basarili_yayin yok — yayın olmamış veya zaten işlenmiş")
        sys.exit(0)
    return json.loads(BASARILI.read_text())


def thumbnail_uret_ve_yukle(veri: dict) -> bool:
    """Thumbnail üret + YouTube'a set."""
    try:
        from thumbnail import pexels_landscape_indir, metin_yerlestir
    except ImportError as h:
        print(f"  thumbnail modül yok: {h}"); return False

    video_id = veri["video_id"]
    baslik = veri["title"]
    tmp_bg = PANEL_KOK / f"_thumb_bg_{video_id}.png"
    tmp_thumb = PANEL_KOK / f"_thumb_{video_id}.png"

    # Arama — başlığın ilk 2 kelimesi
    arama = " ".join(baslik.split()[:2])
    if not pexels_landscape_indir(arama, tmp_bg):
        print(f"  Pexels indirilemedi: {arama}")
        return False

    # Vurgulanacak kelime — başlığın ilk anlamlı uzun kelimesi
    vurgu = next((w for w in baslik.split() if len(w) > 5), "")
    metin_yerlestir(tmp_bg, baslik, vurgu, tmp_thumb)
    tmp_bg.unlink(missing_ok=True)

    if not tmp_thumb.exists():
        print(f"  Thumbnail üretilemedi"); return False

    # YouTube'a set
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        creds = Credentials.from_authorized_user_file(str(PANEL_KOK / "token.json"),
            ["https://www.googleapis.com/auth/youtube"])
        if creds.expired and creds.refresh_token: creds.refresh(Request())
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        media = MediaFileUpload(str(tmp_thumb), mimetype="image/png")
        yt.thumbnails().set(videoId=video_id, media_body=media).execute()
        print(f"  ✓ Thumbnail yüklendi → video {video_id}")
        # Pinterest için tut, sonra temizlenir
        return True
    except Exception as h:
        msg = str(h)[:200]
        if "forbidden" in msg.lower() or "permission" in msg.lower():
            print(f"  ⚠️  Thumbnail upload izni yok (kanal verified değil olabilir): {msg}")
        else:
            print(f"  ✗ Thumbnail upload fail: {msg}")
        return False
    finally:
        # Pinterest sonrası temizlenecek, şimdilik bırak
        pass


def pinterest_pin_olustur(veri: dict, thumb_yolu: Path | None) -> bool:
    """Pinterest'e pin oluştur."""
    try:
        from pinterest_pin import pin_olustur
    except ImportError as h:
        print(f"  pinterest_pin modül yok: {h}"); return False
    sonuc = pin_olustur(
        veri["video_id"], veri["title"],
        veri.get("aciklama", "") or veri["title"],
        thumb_yolu,
    )
    return sonuc is not None


def multilang_caption(veri: dict) -> bool:
    """Senaryodan TR/ES/PT altyazı yükle. Senaryo dosyası ses_ciktilari/'da."""
    # Senaryo dosyasını bul (seslendirici çıktısı)
    ses_klasor = PANEL_KOK / "ses_ciktilari"
    if not ses_klasor.exists():
        print("  ses_ciktilari klasörü yok"); return False
    txt_dosyalar = sorted(ses_klasor.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not txt_dosyalar:
        print("  Senaryo .txt bulunamadı"); return False
    senaryo_yolu = txt_dosyalar[0]

    try:
        r = subprocess.run(
            ["python3", str(PANEL_KOK / "multilang_caption.py"),
             veri["video_id"], str(senaryo_yolu),
             "--diller", "tr,es,pt"],
            timeout=120, capture_output=True, text=True,
        )
        print(r.stdout[-500:])
        if r.stderr: print(r.stderr[-300:])
        return r.returncode == 0
    except Exception as h:
        print(f"  multilang fail: {h}"); return False


def main() -> int:
    veri = _veri_oku()
    print(f"[post_upload] Video: {veri['video_id']} | {veri['title'][:50]}")

    sonuclar = {}

    # 1) Thumbnail
    print("\n[1/3] Thumbnail üretim + upload...")
    thumb_yolu = PANEL_KOK / f"_thumb_{veri['video_id']}.png"
    sonuclar["thumbnail"] = thumbnail_uret_ve_yukle(veri)

    # 2) Pinterest pin
    print("\n[2/3] Pinterest pin...")
    sonuclar["pinterest"] = pinterest_pin_olustur(veri, thumb_yolu if thumb_yolu.exists() else None)

    # 3) Multilang caption
    print("\n[3/3] Multilang caption upload (tr,es,pt)...")
    sonuclar["multilang"] = multilang_caption(veri)

    # Temizle
    thumb_yolu.unlink(missing_ok=True)

    print(f"\n[post_upload] Özet:")
    for k, v in sonuclar.items():
        icon = "✓" if v else "✗"
        print(f"  {icon} {k}")

    # Hiç biri başarılı olmadıysa fail (workflow continue-on-error'lı zaten)
    return 0 if any(sonuclar.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
