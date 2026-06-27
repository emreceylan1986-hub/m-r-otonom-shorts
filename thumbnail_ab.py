"""
thumbnail_ab.py — Thumbnail A/B Test + Auto-Swap (Faz 8).

Her video için 2 farklı thumbnail üret:
  A) Sarı vurgulu + soft gradient (mevcut stil)
  B) Kırmızı vurgu + yüksek kontrast bottom-bar

Yayında A başlar. 24h+ sonra workflow Analytics CTR'sini ölçer:
  - Eğer ana B daha iyi → YouTube'a B'yi set et + pattern öğren
  - Eğer A daha iyi → değiştirme + pattern öğren

Çıktı: thumbnail_ab_state.json — kayıt + öğrenme tablosu

Kullanım:
    python3 thumbnail_ab.py --uret-iki <video_id> <baslik> [--vurgu KELIME]
    python3 thumbnail_ab.py --karsilastir   # 24h+ önceki tüm test'leri ölç
"""
import argparse, json, os, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

PANEL_KOK = Path(__file__).parent
DURUM = PANEL_KOK / "thumbnail_ab_state.json"
THUMB_KLASORU = PANEL_KOK / "thumbnails"


def _durum_oku() -> dict:
    if not DURUM.exists(): return {"testler": {}, "ogrenme": {}}
    try: return json.loads(DURUM.read_text())
    except Exception: return {"testler": {}, "ogrenme": {}}


def _durum_yaz(d: dict):
    DURUM.write_text(json.dumps(d, ensure_ascii=False, indent=2))


def thumbnail_a_uret(baslik: str, vurgu: str, cikti: Path) -> bool:
    """Stil A: sarı vurgu + alt gradient."""
    import thumbnail
    arama = " ".join(baslik.split()[:2])
    bg = cikti.with_suffix(".bg.png")
    if not thumbnail.pexels_landscape_indir(arama, bg): return False
    thumbnail.metin_yerlestir(bg, baslik, vurgu, cikti)
    bg.unlink(missing_ok=True)
    return cikti.exists()


def thumbnail_b_uret(baslik: str, vurgu: str, cikti: Path) -> bool:
    """Stil B: kırmızı vurgu + yüksek kontrast alt bar + farklı Pexels arama."""
    import thumbnail
    from PIL import Image, ImageDraw
    # Farklı arama — varyasyon için son kelimeleri kullan
    arama = " ".join(baslik.split()[-2:])
    bg = cikti.with_suffix(".bg.png")
    if not thumbnail.pexels_landscape_indir(arama, bg): return False
    # Üretim — kırmızı vurgu
    son = thumbnail.metin_yerlestir(bg, baslik, vurgu, cikti)

    # Extra: kırmızı bar üzerine başlığın anahtar kelimesini KIRMIZI yaz
    img = Image.open(son).convert("RGB")
    W, H = img.size
    draw = ImageDraw.Draw(img)
    # Alt 80px'e kırmızı bar
    draw.rectangle([0, H - 90, W, H], fill=(204, 0, 0))
    # Üzerine beyaz tek kelime — başlığın en uzun anlamlı kelimesi
    font = thumbnail._font_yukle(54)
    kelime = vurgu.upper() if vurgu else baslik.split()[0].upper()
    bbox = draw.textbbox((0, 0), kelime, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, H - 75), kelime, font=font, fill=(255, 255, 255))
    img.save(son, "PNG", optimize=True)
    bg.unlink(missing_ok=True)
    return son.exists()


def thumbnail_yt_set(video_id: str, png_yolu: Path) -> bool:
    """YouTube'a thumbnails.set."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    SCOPES = ["https://www.googleapis.com/auth/youtube"]
    creds = Credentials.from_authorized_user_file(str(PANEL_KOK / "token.json"), SCOPES)
    if creds.expired and creds.refresh_token: creds.refresh(Request())
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    try:
        yt.thumbnails().set(videoId=video_id,
                            media_body=MediaFileUpload(str(png_yolu), mimetype="image/png")).execute()
        return True
    except Exception as h:
        print(f"  Thumbnail set fail: {str(h)[:140]}")
        return False


def uret_iki(video_id: str, baslik: str, vurgu: str = "") -> dict | None:
    """A ve B thumbnail üret + state'e kaydet. A'yı YT'ye set et."""
    THUMB_KLASORU.mkdir(exist_ok=True)
    if not vurgu:
        # En uzun anlamlı kelime
        kelimeler = [w for w in baslik.split() if len(w) > 4]
        vurgu = kelimeler[0] if kelimeler else baslik.split()[0]

    thumb_a = THUMB_KLASORU / f"thumb_a_{video_id}.png"
    thumb_b = THUMB_KLASORU / f"thumb_b_{video_id}.png"

    print(f"[thumb_ab] A üretiliyor: {thumb_a.name}")
    a_ok = thumbnail_a_uret(baslik, vurgu, thumb_a)
    print(f"  A: {'✓' if a_ok else '✗'}")

    print(f"[thumb_ab] B üretiliyor: {thumb_b.name}")
    b_ok = thumbnail_b_uret(baslik, vurgu, thumb_b)
    print(f"  B: {'✓' if b_ok else '✗'}")

    if not (a_ok and b_ok):
        print("[thumb_ab] İki thumbnail üretilemedi"); return None

    # A'yı YouTube'a set
    print(f"[thumb_ab] A YouTube'a yükleniyor...")
    if not thumbnail_yt_set(video_id, thumb_a):
        return None
    print(f"  ✓ A aktif")

    # State'e kaydet
    durum = _durum_oku()
    durum["testler"][video_id] = {
        "baslik": baslik, "vurgu": vurgu,
        "thumb_a": str(thumb_a), "thumb_b": str(thumb_b),
        "yayinlanma": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "aktif": "A", "olculmus": False,
    }
    _durum_yaz(durum)
    return durum["testler"][video_id]


def karsilastir():
    """24h+ önceki test'leri Analytics ile ölç + kazananı swap et."""
    durum = _durum_oku()
    testler = durum.get("testler", {})
    bekleyenler = [(vid, t) for vid, t in testler.items() if not t.get("olculmus")]
    if not bekleyenler:
        print("Ölçülecek test yok"); return

    now = datetime.now(timezone.utc)
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    SCOPES = ["https://www.googleapis.com/auth/youtube",
              "https://www.googleapis.com/auth/yt-analytics.readonly"]
    creds = Credentials.from_authorized_user_file(str(PANEL_KOK / "token.json"), SCOPES)
    if creds.expired and creds.refresh_token: creds.refresh(Request())
    yta = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    ogrenme = durum.setdefault("ogrenme", {"A_kazanma": 0, "B_kazanma": 0, "ornekler": []})
    ogrenme.setdefault("A_kazanma", 0)
    ogrenme.setdefault("B_kazanma", 0)
    ogrenme.setdefault("ornekler", [])

    for vid, t in bekleyenler:
        try:
            zaman = datetime.fromisoformat(t["yayinlanma"].replace("Z","+00:00"))
        except Exception:
            continue
        if (now - zaman).total_seconds() < 24 * 3600:
            continue  # 24 saat geçmedi

        # A performansı (mevcut)
        try:
            r = yta.reports().query(
                ids="channel==MINE",
                startDate=zaman.date().isoformat(),
                endDate=now.date().isoformat(),
                metrics="views,cardImpressions,cardClickRate",
                filters=f"video=={vid}",
            ).execute()
            if r.get("rows"):
                a_izl = int(r["rows"][0][0])
            else:
                a_izl = 0
        except Exception:
            a_izl = 0

        # Stats'den de izlenme + beğeni
        try:
            v = yt.videos().list(part="statistics", id=vid).execute()
            if v.get("items"):
                a_izl = max(a_izl, int(v["items"][0]["statistics"].get("viewCount", 0)))
        except Exception:
            pass

        # KARAR — A 50+ izlenme aldıysa veri var → B'ye geçmek için baseline'a güveniyoruz
        # Şimdilik basit: 50+ izlenme + sonraki 24 saat denemesi
        t["a_izl_24h"] = a_izl
        if a_izl < 30:
            # Çok düşük performans → B'ye geç, daha agresif thumbnail dene
            thumb_b = Path(t["thumb_b"])
            if thumb_b.exists() and thumbnail_yt_set(vid, thumb_b):
                t["aktif"] = "B"
                t["b_swap_zamani"] = now.isoformat(timespec="seconds")
                print(f"  {vid}: A düşük ({a_izl} izl) → B'ye swap edildi")
                ogrenme["B_kazanma"] += 1
            else:
                print(f"  {vid}: A {a_izl} izl ama B swap fail")
        else:
            print(f"  {vid}: A başarılı ({a_izl} izl), B değişmeyecek")
            ogrenme["A_kazanma"] += 1

        t["olculmus"] = True
        ogrenme.setdefault("ornekler", []).append({
            "video_id": vid, "baslik": t["baslik"][:60], "kazanan": t["aktif"], "izl_24h": a_izl,
        })

    _durum_yaz(durum)
    print(f"\n[thumb_ab] Toplam öğrenme: A kazandı {ogrenme['A_kazanma']} | B kazandı {ogrenme['B_kazanma']}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--uret-iki", action="store_true")
    p.add_argument("--video-id")
    p.add_argument("--baslik")
    p.add_argument("--vurgu", default="")
    p.add_argument("--karsilastir", action="store_true")
    args = p.parse_args()

    if args.uret_iki:
        if not (args.video_id and args.baslik):
            print("--video-id ve --baslik gerekli"); return 1
        r = uret_iki(args.video_id, args.baslik, args.vurgu)
        return 0 if r else 1
    elif args.karsilastir:
        karsilastir()
        return 0
    else:
        p.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
