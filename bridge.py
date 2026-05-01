"""
bridge.py — Gemini Yazılım Denetleme Köprüsü

Bir kod parçasını Gemini 2.5 Flash'a gönderir, JSON formatında
analiz ve karar (ONAY / RED) alır.

Bağımlılık:
    pip install google-genai

Kullanım:
    from bridge import kod_analiz_et
    sonuc = kod_analiz_et(open("script.py").read())
    if sonuc["karar"] == "ONAY":
        ...
"""

import json
import os
import re
import sys
from pathlib import Path

from google import genai
from google.genai import types


def _json_temizle_ve_parse(ham: str) -> dict:
    """
    Gemini bazen JSON spec'ine aykırı escape'ler döndürüyor (örn: \\[ ).
    Üç aşamalı kurtarma:
      1) doğrudan parse
      2) geçersiz escape'leri (\\X → \\\\X) düzeltip parse
      3) regex ile temel alanları çıkar (BELIRSIZ kararı ile fallback)
    """
    try:
        return json.loads(ham)
    except json.JSONDecodeError:
        pass

    onarilmis = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', ham)
    try:
        return json.loads(onarilmis)
    except json.JSONDecodeError:
        pass

    karar_m = re.search(r'"karar"\s*:\s*"(\w+)"', ham)
    ozet_m = re.search(r'"ozet"\s*:\s*"([^"]{0,400})"', ham)
    return {
        "karar": karar_m.group(1) if karar_m else "BELIRSIZ",
        "ozet": (ozet_m.group(1) if ozet_m else "JSON kurtarılamadı, ham yanıt log'da"),
        "hatalar": ["JSON parse başarısız — bridge fallback parser çalıştı"],
        "oneriler": [],
        "duzeltilmis_kod": "",
        "ham_yanit": ham[:2000],
    }


# ---------------------------------------------------------------------------
# API ANAHTARI
# ---------------------------------------------------------------------------
# Üç yoldan biriyle veriyorsun:
#   1) Bu satırı doldur:        GEMINI_API_KEY = "AIza..."
#   2) Terminalde:              export GEMINI_API_KEY="AIza..."
#   3) .env dosyasına yaz:      GEMINI_API_KEY=AIza...
GEMINI_API_KEY = ""  # <-- API anahtarını buraya yapıştır (veya boş bırak, env okunur)
# ---------------------------------------------------------------------------

MODEL = "gemini-2.5-flash"
TIMEOUT_SN = 60

DENETLEME_SISTEM_PROMPTU = """Sen kıdemli bir Python yazılım denetçisisin.
Sana sunulan kodu titizlikle incele:

1. Sözdizimi hatası var mı?
2. Mantık hatası, sonsuz döngü, bellek sızıntısı riski var mı?
3. Güvenlik açığı var mı? (komut enjeksiyonu, hardcoded sır, vs.)
4. Performans veya okunabilirlik açısından kritik sorun var mı?

Yalnızca AŞAĞIDAKİ JSON ŞEMASIYLA cevap ver, başka hiçbir metin ekleme:

{
  "karar": "ONAY" veya "RED",
  "ozet": "tek cümle teşhis",
  "hatalar": ["bulunan kritik sorunların listesi"],
  "oneriler": ["iyileştirme önerileri"],
  "duzeltilmis_kod": "RED ise düzeltilmiş tam kod, ONAY ise boş string"
}

Karar kuralları:
- Kritik hata varsa → RED
- Yalnızca üslup/iyileştirme varsa → ONAY (önerileri yine listele)
"""


def _api_anahtarini_oku() -> str:
    if GEMINI_API_KEY:
        return GEMINI_API_KEY
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    env_yolu = Path(__file__).with_name(".env")
    if env_yolu.exists():
        for satir in env_yolu.read_text(encoding="utf-8").splitlines():
            if satir.startswith("GEMINI_API_KEY="):
                return satir.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(
        "GEMINI_API_KEY bulunamadı. bridge.py içine veya .env dosyasına ekle."
    )


def _client() -> genai.Client:
    return genai.Client(api_key=_api_anahtarini_oku())


# ---------------------------------------------------------------------------
# GENEL AMAÇLI METİN ÜRETİMİ (senaryo, başlık, çeviri vs. için)
# ---------------------------------------------------------------------------
def gemini_metin_uret(
    prompt: str,
    sistem_promptu: str = "",
    sicaklik: float = 0.7,
    max_token: int = 4096,
    dusunme_kapali: bool = True,
) -> str:
    """
    Düz metin üretimi — JSON şart değil. Çıktıyı string olarak döner.

    NOT: Gemini 2.5 Flash'ta 'thinking' tokenları max_output_tokens'ı
    yiyebiliyor. dusunme_kapali=True (varsayılan) bu sebeple thinking_budget=0
    verir; saf çıkış metni için bütün token bütçesi kullanılır.
    """
    client = _client()
    config_kwargs: dict = {
        "system_instruction": sistem_promptu or None,
        "temperature": sicaklik,
        "max_output_tokens": max_token,
    }
    if dusunme_kapali:
        try:
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        except Exception:
            pass  # eski sürümlerde yoksa sessizce geç

    yanit = client.models.generate_content(
        model=MODEL,
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
        config=types.GenerateContentConfig(**config_kwargs),
    )
    return (yanit.text or "").strip()


# ---------------------------------------------------------------------------
# İÇERİK / METİN DENETİMİ (senaryo, başlık, makale vs.)
# kod_analiz_et'in metin sürümü — JSON sözleşmesi farklı
# ---------------------------------------------------------------------------
METIN_DENETIM_SISTEM = """Sen kıdemli bir içerik editörü ve scenarist'sin.
Sana sunulan metni şu kriterlere göre değerlendir:

1. Akıcılık ve doğal konuşma dili
2. Hook gücü (ilk cümle dikkat çekiyor mu?)
3. Olgusal doğruluk (verilen bağlamla tutarlı mı?)
4. Hedef formata uygunluk (Shorts ise ~30-45 sn, ~75-110 kelime)
5. Reklam/spam/abartı dili yokluğu

Yalnızca AŞAĞIDAKİ JSON ŞEMASIYLA cevap ver:

{
  "karar": "ONAY" veya "REVIZE",
  "ozet": "tek cümle değerlendirme",
  "iyilestirmeler": ["yapılan/önerilen değişiklikler"],
  "revize_metin": "REVIZE ise revize edilmiş tam metin; ONAY ise orijinal metin"
}

Kararı sıkı tut: ufak da olsa iyileştirme varsa REVIZE ver.
"""


def metin_onay_iste(metin: str, baglam: str = "") -> dict:
    """
    Bir metni (senaryo, başlık vs.) Gemini'ye denetletir.
    Dönen sözlük: karar, ozet, iyilestirmeler, revize_metin
    """
    if not metin or not metin.strip():
        raise ValueError("Boş metin denetlenemez.")

    client = _client()
    kullanici_promptu = (
        f"Bağlam:\n{baglam}\n\nDenetlenecek metin:\n---\n{metin}\n---"
        if baglam
        else f"Denetlenecek metin:\n---\n{metin}\n---"
    )

    yanit = client.models.generate_content(
        model=MODEL,
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=kullanici_promptu)])],
        config=types.GenerateContentConfig(
            system_instruction=METIN_DENETIM_SISTEM,
            response_mime_type="application/json",
            temperature=0.3,
            max_output_tokens=4096,
        ),
    )

    ham = (yanit.text or "").strip()
    sonuc = _json_temizle_ve_parse(ham)

    for k, v in [
        ("karar", "ONAY"),
        ("ozet", ""),
        ("iyilestirmeler", []),
        ("revize_metin", metin),
    ]:
        sonuc.setdefault(k, v)

    return sonuc


def kod_analiz_et(kod: str) -> dict:
    """
    Kod metnini Gemini'ye gönderir, denetim sonucu sözlüğü döner.

    Dönen sözlük her zaman şu anahtarları içerir:
        karar, ozet, hatalar, oneriler, duzeltilmis_kod
    """
    if not kod or not kod.strip():
        raise ValueError("Boş kod denetlenemez.")

    client = _client()

    yanit = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=f"Denetlenecek kod:\n\n```python\n{kod}\n```")],
            )
        ],
        config=types.GenerateContentConfig(
            system_instruction=DENETLEME_SISTEM_PROMPTU,
            response_mime_type="application/json",
            temperature=0.2,
            max_output_tokens=32768,
        ),
    )

    ham_metin = (yanit.text or "").strip()
    sonuc = _json_temizle_ve_parse(ham_metin)

    for anahtar, varsayilan in [
        ("karar", "RED"),
        ("ozet", ""),
        ("hatalar", []),
        ("oneriler", []),
        ("duzeltilmis_kod", ""),
    ]:
        sonuc.setdefault(anahtar, varsayilan)

    return sonuc


def onay_iste(kod: str, max_deneme: int = 3) -> tuple[bool, str, dict]:
    """
    Kodu denetlet; RED gelirse Gemini'nin önerdiği düzeltilmiş kodla
    yeniden dener. Onay alana kadar veya max_deneme bitene kadar.

    Dönüş: (onaylandi_mi, son_kod, son_rapor)
    """
    mevcut_kod = kod
    son_rapor: dict = {}

    for deneme in range(1, max_deneme + 1):
        rapor = kod_analiz_et(mevcut_kod)
        son_rapor = rapor

        if rapor["karar"] == "ONAY":
            return True, mevcut_kod, rapor

        duzeltilmis = rapor.get("duzeltilmis_kod", "").strip()
        if not duzeltilmis or duzeltilmis == mevcut_kod:
            return False, mevcut_kod, rapor

        print(f"[Deneme {deneme}] RED → düzeltilmiş kodla tekrar denetleniyor...")
        mevcut_kod = duzeltilmis

    return False, mevcut_kod, son_rapor


def _hizli_test() -> int:
    test_kod = (
        "def topla(a, b):\n"
        "    return a + b\n"
        "\n"
        "print(topla(2, 3))\n"
    )
    print("Gemini'ye gönderiliyor...\n")
    rapor = kod_analiz_et(test_kod)
    print(f"Karar    : {rapor['karar']}")
    print(f"Özet     : {rapor['ozet']}")
    print(f"Hatalar  : {rapor['hatalar']}")
    print(f"Öneriler : {rapor['oneriler']}")
    return 0 if rapor["karar"] == "ONAY" else 1


if __name__ == "__main__":
    sys.exit(_hizli_test())
