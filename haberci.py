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
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests


HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{id}.json"
HN_TARANACAK_ADET = 60  # top listenin ilk N hikayesi taranır

REDDIT_URL = "https://www.reddit.com/r/technology/top.json?t=day&limit=25"
KULLANICI_AJANI = "MR-Studio-Haberci/1.0 (kisisel arastirma)"

ZAMAN_PENCERESI_SAAT = 24
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
    haberler: list[dict] = []
    try:
        ust_yanit = requests.get(HN_TOP_URL, timeout=ISTEK_ZAMAN_ASIMI)
        ust_yanit.raise_for_status()
        kimlikler = ust_yanit.json()[:HN_TARANACAK_ADET]
    except requests.RequestException as hata:
        print(f"[haberci] HN top listesi alınamadı: {hata}")
        return haberler

    for hid in kimlikler:
        try:
            yanit = requests.get(
                HN_ITEM_URL.format(id=hid),
                timeout=ISTEK_ZAMAN_ASIMI,
                headers={"User-Agent": KULLANICI_AJANI},
            )
            yanit.raise_for_status()
            item = yanit.json() or {}
        except requests.RequestException as hata:
            print(f"[haberci] HN item {hid} alınamadı: {hata}")
            continue

        if item.get("type") != "story" or item.get("dead") or item.get("deleted"):
            continue
        if not item.get("url") or not item.get("title"):
            continue

        yas = _yas_saat(item.get("time", 0))
        if yas > ZAMAN_PENCERESI_SAAT:
            continue

        haberler.append(
            {
                "baslik": item["title"],
                "url": item["url"],
                "kaynak": "HN",
                "skor": int(item.get("score", 0)),
                "yas_saat": round(yas, 1),
                "yorum_sayisi": int(item.get("descendants", 0)),
            }
        )
        time.sleep(ISTEKLER_ARASI_GECIKME)

    return haberler


def reddit_haberleri() -> list[dict]:
    haberler: list[dict] = []
    try:
        yanit = requests.get(
            REDDIT_URL,
            timeout=ISTEK_ZAMAN_ASIMI,
            headers={"User-Agent": KULLANICI_AJANI},
        )
        yanit.raise_for_status()
        gonderiler = yanit.json().get("data", {}).get("children", [])
    except requests.RequestException as hata:
        print(f"[haberci] Reddit alınamadı: {hata}")
        return haberler

    for g in gonderiler:
        veri = g.get("data", {})
        if veri.get("stickied") or veri.get("is_self"):
            continue
        url = veri.get("url_overridden_by_dest") or veri.get("url")
        baslik = veri.get("title")
        olusturma = veri.get("created_utc")
        if not (url and baslik and olusturma):
            continue
        yas = _yas_saat(int(olusturma))
        if yas > ZAMAN_PENCERESI_SAAT:
            continue
        haberler.append(
            {
                "baslik": baslik,
                "url": url,
                "kaynak": "Reddit",
                "skor": int(veri.get("ups", 0)),
                "yas_saat": round(yas, 1),
                "yorum_sayisi": int(veri.get("num_comments", 0)),
            }
        )

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
        f"[haberci] Havuz: {len(benzersiz)} benzersiz haber, "
        f"geçmişte işlenmiş {len(benzersiz) - len(yenidenIslenmemis)}, "
        f"aday {len(yenidenIslenmemis)}",
        flush=True,
    )
    return yenidenIslenmemis[:3]


def main() -> int:
    print("[haberci] Son 24 saatin teknoloji haberleri taranıyor...\n")
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
