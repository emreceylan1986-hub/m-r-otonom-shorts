"""
pinterest_pin.py — Pinterest API v5 Pin Otomatik Üretici (Faz 4).

Her yeni YouTube video için Pinterest'e pin oluşturur — Pinterest
PinSEO uzun süreli, "evergreen" trafik kaynağıdır (TikTok aksine
YouTube'a TIKLAMA verir, çünkü Pinterest "websiteye gönderme" mantığıyla
tasarlanmıştır).

OAuth: önce manuel Pinterest Developer'da app oluştur + access_token al
(developers.pinterest.com → My Apps). Token GitHub secret'a `PINTEREST_TOKEN`
olarak ekle.

Kullanım:
    python pinterest_pin.py <video_id> <baslik> <aciklama> [--board BOARD_ID]
"""
import argparse, json, os, sys
from pathlib import Path

import requests

PANEL_KOK = Path(__file__).parent
API_BASE = "https://api.pinterest.com/v5"

# Pinterest board ID'lerini env'den oku — Emre Bey kendi board'unu kurar
DEFAULT_BOARD = os.environ.get("PINTEREST_BOARD_ID", "")


def _token() -> str | None:
    token = os.environ.get("PINTEREST_TOKEN")
    if token: return token
    envf = PANEL_KOK / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            if line.startswith("PINTEREST_TOKEN="):
                return line.split("=", 1)[1].strip()
    return None


def board_listele() -> list[dict]:
    """Mevcut board'ları listele — ilk kurulumda Emre Bey'in board_id'sini
    bulması için."""
    token = _token()
    if not token: return []
    r = requests.get(f"{API_BASE}/boards", headers={"Authorization": f"Bearer {token}"}, timeout=15)
    if r.status_code != 200:
        print(f"  HATA {r.status_code}: {r.text[:200]}"); return []
    return r.json().get("items", [])


def pin_olustur(video_id: str, baslik: str, aciklama: str,
                thumbnail_yolu: Path | None = None,
                board_id: str | None = None) -> dict | None:
    """Pinterest'e pin oluştur. Thumbnail varsa upload, yoksa Pexels URL."""
    token = _token()
    if not token:
        print("[pinterest] PINTEREST_TOKEN env yok — atlandı")
        return None

    board_id = board_id or DEFAULT_BOARD
    if not board_id:
        print("[pinterest] PINTEREST_BOARD_ID env yok — board listele:")
        for b in board_listele():
            print(f"  - {b.get('id')}  {b.get('name')}")
        return None

    # Thumbnail varsa upload, yoksa varsayılan
    if thumbnail_yolu and thumbnail_yolu.exists():
        # Pinterest media_source: image_url (URL) veya image_base64
        import base64
        b64 = base64.b64encode(thumbnail_yolu.read_bytes()).decode()
        media = {"source_type": "image_base64", "content_type": "image/png", "data": b64}
    else:
        # Pexels'tan landscape fetch
        from thumbnail import pexels_landscape_indir
        tmp = PANEL_KOK / f"_pin_tmp_{video_id}.png"
        if not pexels_landscape_indir(baslik.split()[0] if baslik else "nature", tmp, 1000, 1500):
            print("[pinterest] Thumbnail kaynak yok"); return None
        import base64
        b64 = base64.b64encode(tmp.read_bytes()).decode()
        media = {"source_type": "image_base64", "content_type": "image/png", "data": b64}
        tmp.unlink(missing_ok=True)

    body = {
        "board_id": board_id,
        "title": baslik[:100],
        "description": (aciklama + f"\n\n▶ Watch full on YouTube: https://youtu.be/{video_id}")[:500],
        "link": f"https://youtu.be/{video_id}",
        "media_source": media,
    }

    r = requests.post(
        f"{API_BASE}/pins",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body, timeout=30,
    )
    if r.status_code in (200, 201):
        data = r.json()
        print(f"  ✓ Pin oluşturuldu: {data.get('id')}")
        return data
    else:
        print(f"  ✗ HATA {r.status_code}: {r.text[:300]}"); return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("video_id", nargs="?")
    p.add_argument("baslik", nargs="?")
    p.add_argument("aciklama", nargs="?")
    p.add_argument("--thumbnail", default=None)
    p.add_argument("--board", default=None)
    p.add_argument("--list-boards", action="store_true")
    args = p.parse_args()

    if args.list_boards:
        for b in board_listele():
            print(f"{b.get('id')}\t{b.get('name')}")
        return 0

    if not (args.video_id and args.baslik):
        print("Kullanım: pinterest_pin.py <video_id> <baslik> <aciklama>"); return 2

    thumb = Path(args.thumbnail) if args.thumbnail else None
    sonuc = pin_olustur(args.video_id, args.baslik, args.aciklama or "", thumb, args.board)
    return 0 if sonuc else 1


if __name__ == "__main__":
    sys.exit(main())
