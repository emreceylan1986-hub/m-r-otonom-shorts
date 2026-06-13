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


def _praw_clienti():
    """Reddit OAuth client (PRAW). Eğer credentials yoksa None döner ve
    anonim JSON fallback'e geçer."""
    import os
    cid = os.environ.get("REDDIT_CLIENT_ID")
    csec = os.environ.get("REDDIT_CLIENT_SECRET")
    if not (cid and csec):
        return None
    try:
        import praw
    except ImportError:
        print("[haberci] praw yok — anonim fallback")
        return None
    try:
        r = praw.Reddit(
            client_id=cid,
            client_secret=csec,
            user_agent="TrendCatcher/1.0 by /u/trendcatcher_bot",
            read_only=True,
        )
        # Test
        _ = r.subreddit("test").display_name
        return r
    except Exception as h:
        print(f"[haberci] PRAW client başarısız: {h}")
        return None


def _reddit_praw_fetch(reddit, sub_name: str) -> list[dict]:
    """PRAW ile bir subreddit'in günlük top postlarını çek."""
    out = []
    try:
        for post in reddit.subreddit(sub_name).top(time_filter="day", limit=25):
            if post.stickied or post.over_18: continue
            url = post.url or ""
            if not (url and post.title and post.created_utc): continue
            yas = _yas_saat(int(post.created_utc))
            if yas > ZAMAN_PENCERESI_SAAT: continue
            out.append({
                "baslik": post.title,
                "url": url,
                "kaynak": f"r/{sub_name}",
                "skor": int(post.ups or 0),
                "yas_saat": round(yas, 1),
                "yorum_sayisi": int(post.num_comments or 0),
            })
    except Exception as h:
        print(f"[haberci] PRAW r/{sub_name}: {h}")
    return out


def reddit_haberleri() -> list[dict]:
    """4 viral subreddit'ten son 48 saatin top postları (hayvan/doğa/ilginç).

    Önce PRAW (OAuth) dener — GitHub Actions IP'lerinden 403 alma riskini
    sıfırlar. Credentials yoksa anonim JSON fallback'e döner."""
    reddit = _praw_clienti()
    if reddit is not None:
        print("[haberci] Reddit PRAW (OAuth) modunda")
        haberler = []
        for url in REDDIT_URLS:
            sub = url.split("/r/")[1].split("/")[0]
            haberler.extend(_reddit_praw_fetch(reddit, sub))
            time.sleep(0.5)
        return haberler

    # Anonim JSON fallback
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

CRITICAL — ANTI-DUPLICATE RULES:
1) Avoid any topic whose Wikipedia URL appears in the BLOCKED URLs list.
2) Avoid any topic that is SEMANTICALLY SIMILAR to titles in the BLOCKED TITLES
   list — even if you use a different Wikipedia URL or rephrase the headline.
   Example: if "A group of owls is called a parliament" was used, then
   "Why is a group of owls called a parliament" or anything about owl group
   names is BANNED. Pick a completely different animal/phenomenon.
3) Prefer subjects that do NOT share the main noun (animal/species name) with
   any blocked title.
"""


def _basit_baslik_kelimeleri(b: str) -> set[str]:
    """Başlığın anlamlı kelimelerini set olarak döner (stopword'leri at)."""
    import re as _re
    ATIL = {
        "a","an","the","is","are","was","were","of","in","on","at","to","for",
        "and","or","but","with","as","by","be","has","have","had","do","does",
        "did","this","that","these","those","it","its","i","you","we","they",
        "their","what","why","how","when","known","called","group","fact",
    }
    kelimeler = _re.findall(r"[a-z]{3,}", b.lower())
    return {k for k in kelimeler if k not in ATIL}


def _baslik_benzer_mi(yeni: str, eski_setleri: list[set[str]], esik: float = 0.4) -> bool:
    """Yeni başlık eski setlerden biriyle %esik üstü kelime overlap'ı varsa True."""
    y = _basit_baslik_kelimeleri(yeni)
    if not y:
        return False
    for s in eski_setleri:
        if not s:
            continue
        kesisim = len(y & s)
        oran = kesisim / max(len(y), 1)
        if oran >= esik:
            return True
    return False


def gemini_konu_uret(blokli_url: set[str], adet: int = 3) -> list[dict]:
    """Reddit fail olursa fallback — Gemini'den niş konu üretir.
    URL + konu/başlık benzerliği ile çift katmanlı dedup. pytrends seed eklenir."""
    import bridge
    blokli_liste = sorted(list(blokli_url))[-100:]  # son 100 URL
    bloklar = "\n".join(f"- {u}" for u in blokli_liste) or "(yok)"
    # YUKLEMELER son 50 başlık — semantik benzerlik için Gemini'ye + Python filter'a
    son_basliklar: list[str] = []
    try:
        yuklemeler_yolu = Path(__file__).parent / "yuklemeler.json"
        if yuklemeler_yolu.exists():
            kayitlar = json.loads(yuklemeler_yolu.read_text(encoding="utf-8"))
            son_basliklar = [k.get("title", "") for k in kayitlar[-50:] if k.get("title")]
    except (OSError, json.JSONDecodeError):
        pass
    baslik_bloklari = "\n".join(f"- {b}" for b in son_basliklar) or "(yok)"
    eski_set_listesi = [_basit_baslik_kelimeleri(b) for b in son_basliklar]

    trend_seedleri = gunun_trend_seedleri()
    trend_blok = (
        f"\nTODAY'S GOOGLE TRENDS (top US search trends — gentle inspiration, "
        f"NOT mandatory; pick a related animal/nature angle ONLY if a clean "
        f"connection exists; otherwise ignore):\n"
        + "\n".join(f"  · {s}" for s in trend_seedleri)
        if trend_seedleri else ""
    )

    # FAZ 4: Daily Theme — kanal kimliği için günün haftasının teması
    import datetime
    DAILY_THEMES = {
        # NİŞ DARALTMA (13 Haz 2026): "Extreme/Anomaly Nature" odak.
        # Emre Bey favori: dağ keçisi — haftada en az 1 mountain animal içerik.
        0: "mountain animals — ibex/markhor/bighorn/mountain goats defying gravity on vertical cliffs",
        1: "anomaly lakes/waters — pink lakes, boiling lakes, blood waterfalls, glowing beaches",
        2: "extremophile life — parasites, fungi mind-controlling hosts, surviving in lava/acid",
        3: "tiny extreme creatures — tardigrades, mantis shrimp, jumping spiders with superpowers",
        4: "extreme environments — Antarctic survivors, desert nomads, deep caves, volcanic vents",
        5: "raptors/birds with superpowers — eagles snatching goats, vultures eating bones",
        6: "deep sea anomalies — anglerfish, vampire squid, immortal jellyfish",
    }
    bugun_tema = DAILY_THEMES.get(datetime.datetime.now().weekday(), "any animal/nature")
    tema_blok = (
        f"\nDAILY THEME (today's editorial focus — STRONGLY prefer topics from this theme):\n"
        f"  → {bugun_tema}\n"
    )

    # FAZ 4: Sequel injection — son haftanın top viral'lerinin DEVAMI
    sequel_blok = ""
    try:
        vp = Path(__file__).parent / "viral_patterns.json"
        if vp.exists():
            vp_data = json.loads(vp.read_text())
            ornek = vp_data.get("viral", {}).get("ornek_basliklar", [])[:3]
            if ornek:
                sequel_blok = (
                    f"\nSEQUEL OPPORTUNITY (own channel's recent viral hits — "
                    f"consider a 'next chapter' or related-but-different topic):\n"
                    + "\n".join(f"  · {t}" for t in ornek)
                    + "\n  → If you make a sequel, pick an ADJACENT topic (same category, different example).\n"
                )
    except Exception:
        pass

    # FAZ 9: viral_radar.py'den YouTube'da SON 72h 50K+ izlenmiş trending Shorts
    viral_radar_blok = ""
    try:
        vr = Path(__file__).parent / "viral_targets.json"
        if vr.exists():
            vr_data = json.loads(vr.read_text())
            angles = vr_data.get("angles_for_haberci", [])[:8]
            if angles:
                viral_radar_blok = (
                    f"\n🔥 YOUTUBE TRENDING NOW (last 72h, 50K+ views — these angles are PROVEN VIRAL):\n"
                    + "\n".join(f"  • {a}" for a in angles)
                    + "\n  → ABSOLUTELY adapt one of these angles to a different but related subject. "
                    + "Same hook structure, different species/location. Riding active wave = algorithm push.\n"
                )
    except Exception:
        pass

    # FAZ 8: Real-Time Trending Detector — competitor'lardan VIRAL (10K+ izl) konular
    trending_blok = ""
    try:
        cs = Path(__file__).parent / "competitor_signals.json"
        if cs.exists():
            cs_data = json.loads(cs.read_text())
            # 10K+ izlenmiş "GERÇEK viral" başlıklar
            top = cs_data.get("rakip_top_30_izlenme", [])
            gercek_viral = [t for t in top if t.get("views", 0) >= 10000][:8]
            if gercek_viral:
                lines = [f"  · [{t['views']:,} views] {t['title'][:80]}" for t in gercek_viral]
                trending_blok = (
                    f"\nREAL-TIME TRENDING (10K+ view nature/animal shorts from top channels, last 7d) "
                    f"— THESE ANGLES ARE PROVEN VIRAL RIGHT NOW:\n"
                    + "\n".join(lines)
                    + "\n  → STRONGLY prefer adapting one of these angles to a different subject "
                    + "(same hook structure, different species/place). Trend riding = algorithm boost.\n"
                )
    except Exception:
        pass
    try:
        # 2 turlu üretim: ilk turda red varsa Python filter'la ele, 2. turda
        # daha güçlü uyarıyla yeniden iste.
        sonuc: list[dict] = []
        for tur in range(2):
            ek_uyari = (
                ""
                if tur == 0
                else (
                    "\n\nYOUR PREVIOUS BATCH CONTAINED TOPICS TOO SIMILAR TO BLOCKED "
                    "TITLES. Choose entirely different animals/phenomena. "
                    "Forbidden subjects this round: "
                    + ", ".join(sorted({list(s)[0] for s in eski_set_listesi if s})[:30])
                )
            )
            yanit = bridge.gemini_metin_uret(
                prompt=(
                    f"BLOCKED Wikipedia URLs (do not reuse):\n{bloklar}\n\n"
                    f"BLOCKED TITLES (do not produce semantically similar topics):\n{baslik_bloklari}"
                    f"{viral_radar_blok}{trend_blok}{tema_blok}{sequel_blok}{trending_blok}{ek_uyari}\n\n"
                    f"Produce exactly {adet} fresh viral animal/nature topics now."
                ),
                sistem_promptu=GEMINI_KONU_SISTEM,
                sicaklik=0.95,
                max_token=2048,
            )
            m = re.search(r"\[.*\]", yanit, re.DOTALL)
            if not m:
                continue
            kayitlar = json.loads(m.group(0))
            for i, k in enumerate(kayitlar[:adet]):
                if not (k.get("baslik") and k.get("url")):
                    continue
                # Konu/başlık benzerliği kontrolü
                if _baslik_benzer_mi(k["baslik"], eski_set_listesi):
                    print(f"[haberci] Gemini başlığı '{k['baslik'][:40]}…' eski bir konuya çok benzer → atlandı")
                    continue
                # URL geçmişte var mı
                if _normalize_url(k["url"]) in blokli_url:
                    print(f"[haberci] Gemini URL'si geçmişte → atlandı: {k['url']}")
                    continue
                sonuc.append({
                    "baslik": k["baslik"],
                    "url": k["url"],
                    "kaynak": "gemini-fallback",
                    "skor": 1000 - i,
                    "yas_saat": 0,
                    "yorum_sayisi": 0,
                })
            if len(sonuc) >= 1:
                break
        return sonuc[:adet]
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
