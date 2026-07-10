"""
gorsel_qc.py — Görsel-Konu Eşleşme Kontrolü (Gemini Vision).

Pexels/Wikimedia'dan indirilen bir görselin konuyla GERÇEKTEN ilgili olup
olmadığını Gemini Vision'a sorar. Alakasızsa False döner → montajci başka
klip dener.

Kullanım (modül olarak):
    from gorsel_qc import gorsel_konuyla_eslesir_mi
    if gorsel_konuyla_eslesir_mi(image_path, "ocean sunfish", "Heaviest bony fish"):
        # kullan
"""
import os, sys, base64
from pathlib import Path

PANEL_KOK = Path(__file__).parent

# Vision çağrı kotası — quota dostu, her run max N call
GUNLUK_VISION_LIMITI = int(os.environ.get("VISION_DAILY_LIMIT", "60"))
SAYAÇ_DOSYA = PANEL_KOK / ".vision_sayac.json"


def _sayac_oku() -> dict:
    import json
    from datetime import date
    bugun = date.today().isoformat()
    if SAYAÇ_DOSYA.exists():
        try:
            d = json.loads(SAYAÇ_DOSYA.read_text())
            if d.get("tarih") == bugun: return d
        except Exception:
            pass
    return {"tarih": bugun, "kullanildi": 0}


def _sayac_artir():
    import json
    d = _sayac_oku()
    d["kullanildi"] = d.get("kullanildi", 0) + 1
    SAYAÇ_DOSYA.write_text(json.dumps(d))


def kota_var_mi() -> bool:
    return _sayac_oku().get("kullanildi", 0) < GUNLUK_VISION_LIMITI


def gorsel_konuyla_eslesir_mi(image_path: Path | str, keyword: str,
                              baslik: str = "", esik_skor: int = 6) -> bool:
    """Gemini Vision ile görsel-konu eşleşmesi sorar (0-10 skor).
    True = eşleşir, False = alakasız.

    Kota dolduğunda True döner (kötü filtreleme yerine geç ver)."""
    if not kota_var_mi():
        print(f"  [vision] kota doldu — kontrol atlandı, görsel kabul edildi")
        return True

    if not Path(image_path).exists():
        return False

    try:
        from google import genai
        from google.genai import types as gtypes
    except ImportError:
        return True  # SDK yoksa kontrolsüz geç

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        envf = PANEL_KOK / ".env"
        if envf.exists():
            for line in envf.read_text().splitlines():
                if line.startswith("GEMINI_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break
    if not api_key:
        return True

    image_bytes = Path(image_path).read_bytes()
    mime = "image/jpeg" if str(image_path).lower().endswith((".jpg", ".jpeg")) else "image/png"

    soru = (
        f"This image will be used in a YouTube Shorts video about: '{baslik or keyword}'.\n"
        f"The keyword we searched was: '{keyword}'.\n\n"
        f"Rate how well the image MATCHES the actual subject on a 0-10 scale where:\n"
        f"  0-3 = WRONG subject (different species, unrelated scene)\n"
        f"  4-5 = Vaguely related but not the actual subject\n"
        f"  6-7 = Related (similar category, e.g. 'fish' for 'sunfish')\n"
        f"  8-10 = Direct match (shows the actual subject)\n\n"
        f"Output ONLY a single integer 0-10. No explanation."
    )

    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-3.5-flash",  # 10 Tem: 2.5 emekli
            contents=[gtypes.Content(role="user", parts=[
                gtypes.Part.from_bytes(data=image_bytes, mime_type=mime),
                gtypes.Part.from_text(text=soru),
            ])],
            config=gtypes.GenerateContentConfig(
                temperature=0.1, max_output_tokens=10,
                thinking_config=gtypes.ThinkingConfig(thinking_budget=0),
            ),
        )
        _sayac_artir()
        skor_metin = (resp.text or "").strip()
        # İlk integer'ı çıkar
        import re
        m = re.search(r"\d+", skor_metin)
        if not m:
            return True  # parse edilemezse kabul
        skor = int(m.group())
        eslesir = skor >= esik_skor
        print(f"  [vision] '{keyword[:30]}' eşleşme skoru: {skor}/10 → {'✓ kabul' if eslesir else '✗ red'}")
        return eslesir
    except Exception as h:
        print(f"  [vision] hata: {str(h)[:140]} — kontrolsüz kabul")
        return True


def main():
    """CLI test: python gorsel_qc.py image.jpg 'sunfish'"""
    if len(sys.argv) < 3:
        print("Kullanım: python gorsel_qc.py <image_path> <keyword> [baslik]")
        return 1
    r = gorsel_konuyla_eslesir_mi(
        sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "",
    )
    print(f"Eşleşir mi: {r}")
    return 0 if r else 1


if __name__ == "__main__":
    sys.exit(main())
