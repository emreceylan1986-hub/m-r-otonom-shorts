"""
thumbnail.py — Özel YouTube Shorts thumbnail üretici.

Pexels'tan ilgili görsel + Pillow ile metin overlay (gölge + sarı vurgu).
1280x720 (16:9) Shorts thumbnail standardı.

Kullanım:
    python thumbnail.py "Frogs Freeze & Revive" --kelime "freeze" --cikti thumb.png

Workflow entegrasyon:
    Montajcı sonrası çağırılır → output: shorts_ciktilari/thumb_YYYYMMDD_HHMMSS.png
"""
import argparse, json, os, sys, urllib.parse
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

PANEL_KOK = Path(__file__).parent
PEXELS_KEY = None


def _pexels_anahtari() -> str | None:
    global PEXELS_KEY
    if PEXELS_KEY: return PEXELS_KEY
    PEXELS_KEY = os.environ.get("PEXELS_API_KEY")
    if not PEXELS_KEY:
        envf = PANEL_KOK / ".env"
        if envf.exists():
            for line in envf.read_text().splitlines():
                if line.startswith("PEXELS_API_KEY="):
                    PEXELS_KEY = line.split("=", 1)[1].strip()
                    break
    return PEXELS_KEY


def pexels_landscape_indir(arama: str, hedef_png: Path, w: int = 1280, h: int = 720) -> bool:
    """Pexels'tan arama yap, en yüksek çözünürlüklü landscape görsel indir."""
    key = _pexels_anahtari()
    if not key:
        print("[thumb] PEXELS_API_KEY yok"); return False
    try:
        r = requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": arama, "per_page": 10, "orientation": "landscape"},
            headers={"Authorization": key}, timeout=15,
        )
        r.raise_for_status()
        photos = r.json().get("photos", [])
        if not photos: return False
        src = photos[0]["src"]["landscape"] or photos[0]["src"]["large2x"]
        ham = requests.get(src, timeout=20).content
        tmp = hedef_png.with_suffix(".tmp.jpg")
        tmp.write_bytes(ham)
        # Resize to 1280x720 (cover, center-crop)
        img = Image.open(tmp).convert("RGB")
        oran_dst = w / h
        oran_src = img.width / img.height
        if oran_src > oran_dst:
            yeni_w = int(img.height * oran_dst)
            l = (img.width - yeni_w) // 2
            img = img.crop((l, 0, l + yeni_w, img.height))
        else:
            yeni_h = int(img.width / oran_dst)
            t = (img.height - yeni_h) // 2
            img = img.crop((0, t, img.width, t + yeni_h))
        img = img.resize((w, h), Image.LANCZOS)
        img.save(hedef_png, "PNG", optimize=True)
        tmp.unlink()
        return True
    except Exception as h:
        print(f"[thumb] pexels hata: {h}"); return False


def _font_yukle(boyut: int) -> ImageFont.FreeTypeFont:
    """Önce sistem fontunu dene; bulamazsa default'a düş."""
    for yol in [
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/Arial.ttf",
    ]:
        if Path(yol).exists():
            try: return ImageFont.truetype(yol, boyut)
            except Exception: pass
    return ImageFont.load_default()


def metin_yerlestir(img_yolu: Path, metin: str, vurgu_kelime: str = "",
                    cikti: Path | None = None) -> Path:
    """Görselin üzerine büyük, gölgeli, sarı-vurgulu metin ekle."""
    img = Image.open(img_yolu).convert("RGB")
    W, H = img.size

    # Karartma overlay (alttan ortaya)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)
    for i in range(H // 3):
        a = int(180 * (i / (H // 3)))
        draw_ov.rectangle([0, H - i - 1, W, H - i], fill=(0, 0, 0, a))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)
    # Font boyutu: metin uzunluğuna göre adapte
    font_size = max(50, min(130, int(900 / max(len(metin.split()), 3))))
    font = _font_yukle(font_size)

    # Metni satırlara böl (max 3 kelime/satır)
    kelimeler = metin.upper().split()
    satirlar = []
    cur = []
    for k in kelimeler:
        cur.append(k)
        # Genişlik tahminin font_size * 0.6 * uzunluk
        if sum(len(w) for w in cur) > 18:
            satirlar.append(" ".join(cur)); cur = []
    if cur: satirlar.append(" ".join(cur))

    # Çoklu satır metni alt-orta hizala
    line_h = font_size + 12
    toplam_h = line_h * len(satirlar)
    y = H - toplam_h - 60

    for satir in satirlar:
        # Bbox ölç
        bbox = draw.textbbox((0, 0), satir, font=font)
        tw = bbox[2] - bbox[0]
        x = (W - tw) // 2

        # Gölge — 6 yön
        for dx, dy in [(-3,-3),(3,-3),(-3,3),(3,3),(0,-3),(0,3)]:
            draw.text((x + dx, y + dy), satir, font=font, fill=(0, 0, 0))

        # Vurgu kelime sarı, gerisi beyaz
        if vurgu_kelime and vurgu_kelime.upper() in satir:
            # Karakter karakter çiz, vurgu kelime sarı
            parts = []
            kelime_pcs = satir.split(" ")
            for kp in kelime_pcs:
                color = (255, 200, 0) if vurgu_kelime.upper() in kp else (255, 255, 255)
                parts.append((kp, color))
            cx = x
            for i, (kp, c) in enumerate(parts):
                draw.text((cx, y), kp, font=font, fill=c)
                bb = draw.textbbox((0, 0), kp + " ", font=font)
                cx += bb[2] - bb[0]
        else:
            draw.text((x, y), satir, font=font, fill=(255, 255, 255))
        y += line_h

    if cikti is None:
        cikti = img_yolu.with_name(img_yolu.stem + "_thumb.png")
    img.save(cikti, "PNG", optimize=True)
    return cikti


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("baslik", help="Thumbnail'a yazılacak metin (kısa hook)")
    p.add_argument("--arama", default="", help="Pexels arama (boşsa başlıktan)")
    p.add_argument("--kelime", default="", help="Sarı vurgulanacak kelime")
    p.add_argument("--cikti", default=None, help="Çıktı PNG yolu")
    p.add_argument("--mevcut", default=None, help="Mevcut görseli kullan (Pexels'a düşme)")
    args = p.parse_args()

    cikti = Path(args.cikti) if args.cikti else (PANEL_KOK / "thumbnail.png")

    if args.mevcut:
        kaynak = Path(args.mevcut)
        if not kaynak.exists():
            print(f"[thumb] {args.mevcut} yok"); return 1
        # Resize ettir
        img = Image.open(kaynak).convert("RGB").resize((1280, 720), Image.LANCZOS)
        bg_yolu = cikti.with_suffix(".bg.png")
        img.save(bg_yolu, "PNG")
    else:
        arama = args.arama or " ".join(args.baslik.split()[:3])
        bg_yolu = cikti.with_suffix(".bg.png")
        if not pexels_landscape_indir(arama, bg_yolu):
            print("[thumb] Pexels indirilemedi"); return 1

    son = metin_yerlestir(bg_yolu, args.baslik, args.kelime, cikti)
    print(f"[thumb] Üretildi: {son}")
    bg_yolu.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
