"""
haberci.py — YouTube Shorts için Teknoloji Haberi Çekici

Son 24 saatin en popüler 3 teknoloji haberini getirir.

Kaynaklar (hepsi RESMİ API, scraping yok, ban riski sıfır):
    1) HackerNews Firebase API  → gerçek "score" metriği ile popülerlik
    2) Reddit r/technology .json → "ups" metriği ile popülerlik

Çıktı: JSON dosyası ve konsol özeti
    {
      "uretim_zamani": "...",
      "haberler": [
        {"baslik": "...", "url": "...", "kaynak": "HN", "skor": 1234, "yas_saat": 8.2},
        ...
      ]
    }
"""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests


# NİŞ: HAYVAN + DOĞA + İLGİNÇ GERÇEKLER (viral evrensel format)
# Kaynaklar: tek bir konuya değil çoğunlukla görsel/duygusal/şaşırtıcı içeriğe
# odaklı, telif riski sıfır subreddit'ler.
REDDIT_URLS = [
    "https://www.reddit.com/r/NatureIsFuckingLit/top.json?t=day&limit=25",
    "https://www.reddit.com/r/AnimalsBeingBros/top.json?t=day&limit=25",
    "https://www.reddit.com/r/Damnthatsinteresting/top.json?t=day&limit=25",
    "https://www.reddit.com/r/todayilearned/top.json?t=day&limit=25",
]
KULLANICI_AJANI = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"

# Eski HN/r/technology sabitleri (geçici — referans/import kırılmasın diye)
HN_TOP_URL = ""
HN_ITEM_URL = ""
HN_TARANACAK_ADET = 0
REDDIT_URL = REDDIT_URLS[0]

ZAMAN_PENCERESI_SAAT = 48  # niş içerikte gün gün taze değil, "viral son 2 gün"
ISTEK_ZAMAN_ASIMI = 10
ISTEKLER_ARASI_GECIKME = 0.05

CIKTI_DOSYASI = Path(__file__).parent / "haberler.json"
GECMIS_DOSYASI = Path(__file__).parent / "haber_gecmisi.json"
GECMIS_AZAMI_KAYIT = 1000  # eski kayıtlar bu sayının üzerine çıkınca budanır


def _simdi_utc() -> datetime:
    return datetime.now(timezone.utc)


def _yas_saat(unix_zaman: int) -> float:
    fark = _simdi_utc() - datetime.fromtimestamp(unix_zaman, tz=timezone.utc)
    return fark.total_seconds() / 3600


def hackernews_haberleri() -> list[dict]:
    """KAPATILDI — nişten çıkarıldı. Geri uyumluluk için boş döner."""
    return []


def reddit_haberleri() -> list[dict]:
    """4 viral subreddit'ten son 48 saatin top postları (hayvan/doğa/ilginç)."""
    haberler: list[dict] = []
    for url in REDDIT_URLS:
        sub = url.split("/r/")[1].split("/")[0]
        try:
            yanit = requests.get(
                url,
                timeout=ISTEK_ZAMAN_ASIMI,
                headers={"User-Agent": KULLANICI_AJANI},
            )
            yanit.raise_for_status()
            gonderiler = yanit.json().get("data", {}).get("children", [])
        except requests.RequestException as hata:
            print(f"[haberci] r/{sub} alınamadı: {hata}")
            continue

        for g in gonderiler:
            veri = g.get("data", {})
            if veri.get("stickied") or veri.get("over_18"):
                continue
            url_h = veri.get("url_overridden_by_dest") or veri.get("url")
            baslik = veri.get("title")
            olusturma = veri.get("created_utc")
            if not (url_h and baslik and olusturma):
                continue
            yas = _yas_saat(int(olusturma))
            if yas > ZAMAN_PENCERESI_SAAT:
                continue
            haberler.append(
                {
                    "baslik": baslik,
                    "url": url_h,
                    "kaynak": f"r/{sub}",
                    "skor": int(veri.get("ups", 0)),
                    "yas_saat": round(yas, 1),
                    "yorum_sayisi": int(veri.get("num_comments", 0)),
                }
            )
        time.sleep(ISTEKLER_ARASI_GECIKME * 5)  # subreddit'ler arası nezaket

    return haberler


def _tekrarlari_ele(haberler: Iterable[dict]) -> list[dict]:
    gorulen: dict[str, dict] = {}
    for h in haberler:
        anahtar = h["url"].split("?")[0].rstrip("/")
        if anahtar not in gorulen or h["skor"] > gorulen[anahtar]["skor"]:
            gorulen[anahtar] = h
    return list(gorulen.values())


def _normalize_url(url: str) -> str:
    return url.split("?")[0].rstrip("/").lower()


def gunun_trend_seedleri() -> list[str]:
    """
    Google Trends (pytrends) — günün US trending searches'inden seed çek.
    Gemini fallback'e "şu konular şu an viral" ipucu olarak verilir.
    Fail-safe: pytrends hata verirse boş döner, ana akış bozulmaz.
    """
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=0, timeout=(5, 10))
        df = pt.trending_searches(pn="united_states")
        seedler = [str(s) for s in df[0].head(10).tolist()]
        return seedler
    except Exception as hata:
        print(f"[haberci] pytrends trend seed alınamadı: {hata}")
        return []


GEMINI_KONU_SISTEM = """You produce viral YouTube Shorts TOPICS for an
ANIMAL / NATURE / AMAZING-FACTS channel. Output ONLY a JSON array of EXACTLY
3 topic objects.

Each topic = a well-established, factual, surprising fact about an animal,
natural phenomenon, or science wonder that:
- Has clear visual potential (stock footage of the subject exists on Pexels)
- Is broadly known and TRUE (no urban legends, no debunked claims)
- Stops the scroll: emotionally surprising or beautiful

Each object MUST have:
- "baslik": punchy English headline of the fact (e.g. "Octopuses have three hearts and blue blood")
- "url": Wikipedia URL of the main subject (e.g. https://en.wikipedia.org/wiki/Octopus). MUST be a real Wikipedia page.

CRITICAL: avoid any topic whose Wikipedia URL appears in the BLOCKED list
provided in the user prompt — those have been used already.
"""


def gemini_konu_uret(blokli_url: set[str], adet: int = 3) -> list[dict]:
    """Reddit fail olursa fallback — Gemini'den niş konu üretir.
    Bonus: pytrends ile günün US trend aramalarını seed olarak verir."""
    import bridge
    blokli_liste = sorted(list(blokli_url))[-100:]  # son 100 yeter
    bloklar = "\n".join(f"- {u}" for u in blokli_liste) or "(yok)"
    trend_seedleri = gunun_trend_seedleri()
    trend_blok = (
        f"\nTODAY'S GOOGLE TRENDS (top US search trends — gentle inspiration, "
        f"NOT mandatory; pick a related animal/nature angle ONLY if a clean "
        f"connection exists; otherwise ignore):\n"
        + "\n".join(f"  · {s}" for s in trend_seedleri)
        if trend_seedleri else ""
    )
    try:
        yanit = bridge.gemini_metin_uret(
            prompt=(
                f"BLOCKED Wikipedia URLs (do not reuse any of these):\n{bloklar}"
                f"{trend_blok}\n\n"
                f"Produce exactly {adet} fresh viral animal/nature topics now."
            ),
            sistem_promptu=GEMINI_KONU_SISTEM,
            sicaklik=0.9,
            max_token=2048,
        )
        m = re.search(r"\[.*\]", yanit, re.DOTALL)
        if not m:
            return []
        kayitlar = json.loads(m.group(0))
        sonuc = []
        for i, k in enumerate(kayitlar[:adet]):
            if k.get("baslik") and k.get("url"):
                sonuc.append({
                    "baslik": k["baslik"],
                    "url": k["url"],
                    "kaynak": "gemini-fallback",
                    "skor": 1000 - i,
                    "yas_saat": 0,
                    "yorum_sayisi": 0,
                })
        return sonuc
    except Exception as hata:
        print(f"[haberci] Gemini fallback hatası: {hata}")
        return []


def _gecmisi_oku() -> set[str]:
    if not GECMIS_DOSYASI.exists():
        return set()
    try:
        veri = json.loads(GECMIS_DOSYASI.read_text(encoding="utf-8"))
        return {_normalize_url(u) for u in veri.get("islenen_url", [])}
    except (json.JSONDecodeError, OSError):
        return set()


def _gecmise_ekle(yeni_urller: list[str]) -> None:
    mevcut: list[str] = []
    if GECMIS_DOSYASI.exists():
        try:
            mevcut = json.loads(GECMIS_DOSYASI.read_text(encoding="utf-8")).get("islenen_url", [])
        except (json.JSONDecodeError, OSError):
            mevcut = []
    birlesim = mevcut + [u for u in yeni_urller if u not in mevcut]
    if len(birlesim) > GECMIS_AZAMI_KAYIT:
        birlesim = birlesim[-GECMIS_AZAMI_KAYIT:]
    GECMIS_DOSYASI.write_text(
        json.dumps({"islenen_url": birlesim}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def en_populer_3() -> list[dict]:
    havuz = hackernews_haberleri() + reddit_haberleri()
    benzersiz = _tekrarlari_ele(havuz)
    gecmis = _gecmisi_oku()
    yenidenIslenmemis = [
        h for h in benzersiz if _normalize_url(h["url"]) not in gecmis
    ]
    yenidenIslenmemis.sort(key=lambda h: h["skor"], reverse=True)
    print(
        f"[haberci] Reddit havuzu: {len(benzersiz)} benzersiz, "
        f"geçmişte {len(benzersiz) - len(yenidenIslenmemis)}, "
        f"aday {len(yenidenIslenmemis)}",
        flush=True,
    )
    # Reddit yetersiz (engellendi / hepsi geçmişte): Gemini fallback
    if len(yenidenIslenmemis) < 3:
        print("[haberci] Reddit yetersiz → Gemini konu fallback'i devrede.", flush=True)
        fallback = gemini_konu_uret(gecmis, adet=3)
        # mevcut adayların URL'lerini tekrar etmesin
        mevcut_urller = {_normalize_url(h["url"]) for h in yenidenIslenmemis}
        for k in fallback:
            if _normalize_url(k["url"]) not in mevcut_urller:
                yenidenIslenmemis.append(k)
                mevcut_urller.add(_normalize_url(k["url"]))
        print(f"[haberci] Gemini sonrası toplam aday: {len(yenidenIslenmemis)}", flush=True)
    return yenidenIslenmemis[:3]


def main() -> int:
    print("[haberci] Hayvan/doğa nişi — Reddit + Gemini fallback taranıyor...\n")
    secilenler = en_populer_3()

    if not secilenler:
        print("[haberci] Hiç haber bulunamadı.")
        return 1

    cikti = {
        "uretim_zamani": _simdi_utc().isoformat(),
        "haberler": secilenler,
    }
    CIKTI_DOSYASI.write_text(json.dumps(cikti, ensure_ascii=False, indent=2), encoding="utf-8")
    _gecmise_ekle([h["url"] for h in secilenler])

    for sira, h in enumerate(secilenler, 1):
        print(f"{sira}. [{h['kaynak']} · skor {h['skor']} · {h['yas_saat']} sa]")
        print(f"   {h['baslik']}")
        print(f"   {h['url']}\n")

    print(f"[haberci] JSON dosyaya yazıldı: {CIKTI_DOSYASI.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
