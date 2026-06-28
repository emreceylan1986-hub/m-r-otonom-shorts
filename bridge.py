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


def _generate_retry(model: str, contents, config, _denemeler: int = 9):
    """
    Gemini generate_content + exponential backoff (cap 90s).
    503/429/500 (geçici aşırı yük) → 9 deneme, ~6 dk toplam bekleme.
    Gemini spike'ları uzun sürebilir; workflow 25 dk timeout içinde rahat.
    """
    import time
    from google.genai import errors as _genai_errors

    son_hata = None
    for deneme in range(_denemeler):
        try:
            client = _client()
            return client.models.generate_content(
                model=model, contents=contents, config=config
            )
        except _genai_errors.ServerError as hata:  # 5xx
            son_hata = hata
            bekle = min(2 ** (deneme + 1), 90)
            print(f"[bridge] Gemini {getattr(hata,'code','5xx')} — {bekle}s sonra "
                  f"yeniden ({deneme+1}/{_denemeler})", flush=True)
            time.sleep(bekle)
        except _genai_errors.ClientError as hata:  # 429 rate limit dahil
            if getattr(hata, "code", None) == 429:
                if ("PerDay" in str(hata)) or ("GenerateRequestsPerDay" in str(hata)):
                    print("[bridge] Gemini GUNLUK kota (PerDay) doldu — retry YOK, fail-fast", flush=True)
                    raise
                son_hata = hata
                bekle = min(2 ** (deneme + 1), 90)
                print(f"[bridge] Gemini 429 rate limit — {bekle}s sonra "
                      f"yeniden ({deneme+1}/{_denemeler})", flush=True)
                time.sleep(bekle)
            else:
                raise
    raise RuntimeError(f"Gemini {_denemeler} denemede de yanıt vermedi: {son_hata}")


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

    yanit = _generate_retry(
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
4. Hedef formata uygunluk (Shorts: ~25-30 sn, KESİN 55-70 kelime —
   metni ASLA 70 kelimenin üstüne uzatma; gerekiyorsa KISALT)
5. Reklam/spam/abartı dili yokluğu

KRİTİK DİL KURALI: revize_metin'i HER ZAMAN orijinal metnin diliyle aynı
dilde yaz. Orijinal İngilizce ise revize de %100 İngilizce olmalı —
asla Türkçe'ye çevirme. Bu kanal global İngilizce kitleye yayın yapıyor.

Yalnızca AŞAĞIDAKİ JSON ŞEMASIYLA cevap ver:

{
  "karar": "ONAY" veya "REVIZE",
  "ozet": "tek cümle değerlendirme",
  "iyilestirmeler": ["yapılan/önerilen değişiklikler"],
  "revize_metin": "REVIZE ise revize edilmiş tam metin; ONAY ise orijinal metin"
}

Kararı sıkı tut: ufak da olsa iyileştirme varsa REVIZE ver.
"""


UYGUNLUK_DENETIM_SISTEM = """Sen YouTube Shorts yayın editörüsün. Sana bir video
paketi (KAYNAK HABER + senaryo + başlık + açıklama + etiketler) sunulacak.
Beş net kritere göre uygunluk değerlendir:

1. TELİF: marka adı, lisanslı karakter, şirket logosu, yapıt referansı içeriyor mu?
2. CLICKBAIT/YANILTICI: başlık ile içerik uyumsuz mu, abartı vaat mi var mı?
3. OLGUSAL SADAKAT: senaryo, VERİLEN KAYNAK HABERE sadık mı? Senaryo kaynaktaki
   bilgiyi çarpıtıyor mu, abartıyor mu, kaynakta OLMAYAN bir iddia ekliyor mu?
   ⚠️ KRİTİK: Kaynak haberin KENDİ doğruluğunu SORGULAMA. Kaynak güncel bir
   teknoloji haberidir ve senin bilgi kesim tarihinden SONRA olabilir — bir
   ürün/olay/şirketi "tanımıyorsan" bu onun var olmadığı anlamına GELMEZ.
   "Böyle bir şey yok / duymadım" gerekçesiyle ASLA REDDED verme. Yalnızca
   senaryonun kaynağı ÇARPITIP çarpıtmadığına bak.
4. TOPLULUK POLİTİKASI: küfür, siyasi tahrik, sağlık iddiası, kumar/finans tavsiyesi,
   nefret söylemi, kişisel saldırı, şiddet?
5. MARKA TUTARLILIĞI: TrendCatcher tonuna (haber + bilgilendirme) uygun mu?

KARAR ÜRETME KURALI (dengeli ol — amaç çöp içeriği engellemek, iyi içeriği
yayınlatmak; aşırı katılık tüm kanalı durdurur):

- REDDED → SADECE şu ağır ihlallerde: senaryonun kaynağı ÇARPITMASI
  (olay/sonuç/aktör kaynaktan farklı), kaynakta olmayan iddia uydurma,
  telif ihlali, ciddi topluluk politikası ihlali (nefret, şiddet,
  tehlikeli sağlık iddiası). NOT: kaynağı tanımamak REDDED sebebi DEĞİL.
- SUPHELI → SADECE gerçek ve ciddi bir belirsizlik/risk sezdiğinde, net ihlal
  diyemediğin ama yayınlanması markaya zarar verebilecek durumlarda.
- UYGUN → olgusal olarak doğruysa ve ağır ihlal yoksa. ÖNEMLİ: başlıktaki
  hafif bir üslup/clickbait kelimesi, küçük abartı tonu veya stil kusuru
  TEK BAŞINA SUPHELI sebebi DEĞİLDİR — içerik olgusal doğruysa UYGUN ver.
  "Hafif clickbait taşıyor AMA içerik doğru" → UYGUN.

YALNIZCA bu JSON ile cevap ver:
{
  "karar": "UYGUN" | "SUPHELI" | "REDDED",
  "sebep": "tek cümle gerekçe",
  "risk_alanlari": ["telif" | "clickbait" | "olgusal" | "politika" | "marka"]
}
"""


def icerik_uygunluk_denetimi(
    senaryo: str,
    baslik: str,
    aciklama: str,
    etiketler: list,
    kaynak_baslik: str = "",
    kaynak_url: str = "",
) -> dict:
    """
    Yükleme öncesi son denetim. Şüpheli/redded sonuç → yukleyici otomatik
    PRIVATE'a düşürür ve uyarı flag oluşturur.

    kaynak_baslik/kaynak_url: orijinal haber — olgusal denetim 'senaryo
    kaynağa sadık mı' diye yapılır, 'haber gerçek mi' diye DEĞİL.
    """
    import os as _os
    if _os.environ.get("GEMINI_TASARRUF") == "1":
        return {"karar": "UYGUN", "sebep": "tasarruf modu — denetim atlandı", "risk_alanlari": []}
    kaynak_blok = (
        f"KAYNAK HABER (senaryo buna sadık olmalı; bu kaynağın kendi "
        f"doğruluğunu sorgulama):\n  Başlık: {kaynak_baslik}\n  URL: {kaynak_url}\n\n"
        if kaynak_baslik
        else ""
    )
    paket = (
        f"{kaynak_blok}"
        f"BAŞLIK: {baslik}\n\n"
        f"AÇIKLAMA:\n{aciklama}\n\n"
        f"ETİKETLER: {', '.join(etiketler)}\n\n"
        f"SENARYO:\n{senaryo}"
    )
    yanit = _generate_retry(
        model=MODEL,
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=paket)])],
        config=types.GenerateContentConfig(
            system_instruction=UYGUNLUK_DENETIM_SISTEM,
            response_mime_type="application/json",
            temperature=0.2,
            max_output_tokens=4096,
            # thinking KAPALI — yoksa thinking token'ları bütçeyi yer,
            # JSON yarıda kesilir, karar/sebep boş gelir (private tıkanması)
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    sonuc = _json_temizle_ve_parse((yanit.text or "").strip())
    sonuc.setdefault("karar", "SUPHELI")  # parse hatası → güvenli taraf
    sonuc.setdefault("sebep", "")
    sonuc.setdefault("risk_alanlari", [])
    if sonuc["karar"] not in {"UYGUN", "SUPHELI", "REDDED"}:
        sonuc["karar"] = "SUPHELI"
    return sonuc


def metin_onay_iste(metin: str, baglam: str = "") -> dict:
    """
    Bir metni (senaryo, başlık vs.) Gemini'ye denetletir.
    Dönen sözlük: karar, ozet, iyilestirmeler, revize_metin
    """
    if not metin or not metin.strip():
        raise ValueError("Boş metin denetlenemez.")

    import os as _os
    if _os.environ.get("GEMINI_TASARRUF") == "1":
        return {"karar": "ONAY", "ozet": "tasarruf modu — denetim atlandı", "iyilestirmeler": [], "revize_metin": metin}

    kullanici_promptu = (
        f"Bağlam:\n{baglam}\n\nDenetlenecek metin:\n---\n{metin}\n---"
        if baglam
        else f"Denetlenecek metin:\n---\n{metin}\n---"
    )

    yanit = _generate_retry(
        model=MODEL,
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=kullanici_promptu)])],
        config=types.GenerateContentConfig(
            system_instruction=METIN_DENETIM_SISTEM,
            response_mime_type="application/json",
            temperature=0.3,
            max_output_tokens=4096,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
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

    yanit = _generate_retry(
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
            thinking_config=types.ThinkingConfig(thinking_budget=0),
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
