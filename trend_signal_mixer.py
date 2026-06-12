"""
trend_signal_mixer.py — Çok kaynaklı trend sinyal birleştirici.

Reddit (PRAW), Google Trends (pytrends), YouTube autocomplete, ve
competitor_signals.json'ı tek bir "sıcak" konu listesinde birleştirir.

Çıktı: trend_signals.json — haberci.py'nin Gemini prompt'una seed olur.

Kullanım:
    python trend_signal_mixer.py
"""
import json, time, urllib.parse
from datetime import datetime
from pathlib import Path
import requests

PANEL_KOK = Path(__file__).parent
CIKTI = PANEL_KOK / "trend_signals.json"

# Niş seed kelimeleri — autocomplete sorgu temeli
SEED_TERIMLERI = [
    "amazing animal", "rare nature", "extreme weather",
    "deep sea creature", "world record animal", "natural phenomenon",
    "weird animal facts", "ocean mystery", "wildlife shocking",
]


def google_trends_yukselen() -> list[str]:
    try:
        from pytrends.request import TrendReq
        py = TrendReq(hl="en-US", tz=360)
        out = []
        for seed in SEED_TERIMLERI[:5]:
            try:
                py.build_payload([seed], cat=0, timeframe="now 1-d", geo="")
                rel = py.related_queries()
                rising = rel.get(seed, {}).get("rising")
                if rising is not None:
                    for row in rising.head(5).itertuples():
                        out.append(str(row.query))
                time.sleep(1)
            except Exception as h:
                print(f"  pytrends {seed}: {h}")
        return out
    except ImportError:
        print("[trend] pytrends yok"); return []
    except Exception as h:
        print(f"[trend] pytrends genel: {h}"); return []


def youtube_autocomplete(seed: str) -> list[str]:
    """YouTube'un public suggest endpoint'i (auth yok)."""
    try:
        r = requests.get(
            "https://suggestqueries-clients6.youtube.com/complete/search",
            params={"client": "youtube", "ds": "yt", "q": seed},
            timeout=10,
        )
        # JSONP cevap → çevir
        txt = r.text
        if txt.startswith("window."): txt = txt.split("(", 1)[1].rsplit(")", 1)[0]
        data = json.loads(txt)
        # data[1] = [[suggestion, ...], ...]
        return [s[0] for s in data[1][:8]]
    except Exception as h:
        print(f"  yt-autocomplete {seed}: {h}"); return []


def competitor_ipuclari() -> list[str]:
    f = PANEL_KOK / "competitor_signals.json"
    if not f.exists(): return []
    try:
        d = json.loads(f.read_text())
        return d.get("ipucu_konular", [])
    except Exception:
        return []


def main():
    rapor = {
        "uretim": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "kaynaklar": {},
    }

    print("[trend] Google Trends rising queries...")
    gt = google_trends_yukselen()
    rapor["kaynaklar"]["google_trends_rising"] = gt
    print(f"  {len(gt)} sorgu")

    print("[trend] YouTube autocomplete...")
    yt_sug = []
    for seed in SEED_TERIMLERI:
        sug = youtube_autocomplete(seed)
        yt_sug.extend(sug)
        time.sleep(0.3)
    rapor["kaynaklar"]["youtube_autocomplete"] = list(dict.fromkeys(yt_sug))[:30]
    print(f"  {len(rapor['kaynaklar']['youtube_autocomplete'])} öneri")

    print("[trend] Competitor son 24h ipuçları...")
    comp = competitor_ipuclari()
    rapor["kaynaklar"]["competitor"] = comp
    print(f"  {len(comp)} başlık")

    # Birleşik prompt seed — top 20
    birlesik = []
    for k in ["competitor", "youtube_autocomplete", "google_trends_rising"]:
        for item in rapor["kaynaklar"].get(k, [])[:10]:
            if item and item not in birlesik:
                birlesik.append(item)
    rapor["birlesik_seed"] = birlesik[:25]

    CIKTI.write_text(json.dumps(rapor, ensure_ascii=False, indent=2))
    print(f"\n[trend] Yazıldı: {CIKTI} ({len(birlesik)} seed)")


if __name__ == "__main__":
    main()
