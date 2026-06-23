"""
viral_radar.py — YouTube son 72h trending Shorts radarı.

YouTube Data API ile son 72 saatte 100K+ izlenmiş niş Shorts videoları tespit
eder. Konularını `viral_targets.json`'a yazar. Haberci.py Gemini prompt'una
"PROVEN VIRAL — adapt these angles" işaretiyle yedirilir.

Kullanım:
    python viral_radar.py
"""
import json, os, sys, re
from datetime import datetime, timezone, timedelta
from pathlib import Path

PANEL_KOK = Path(__file__).parent
TOKEN = PANEL_KOK / "token.json"
CIKTI = PANEL_KOK / "viral_targets.json"

# Niş anahtar kelimeleri — TrendCatcher için extreme/anomaly nature
NIS_ANAHTAR = [
    "mountain goat", "ibex climbing", "markhor", "bighorn",
    "extreme animal", "nature anomaly", "amazing wildlife",
    "rare animal", "deep sea creature", "extremophile",
    "pink lake", "boiling lake", "weird nature",
    "wild facts", "incredible animal", "tardigrade",
]


def yt_istemci():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_file(str(TOKEN),
        ["https://www.googleapis.com/auth/youtube"])
    if creds.expired and creds.refresh_token: creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def son_72h_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()


def search_viral(yt, query: str, esik: int = 100000) -> list[dict]:
    """Son 72h içinde yayınlanmış esik+ izlenmeli Shorts."""
    out = []
    try:
        # 1) search.list — son 72h + sort=viewCount
        r = yt.search().list(
            part="snippet",
            q=f"{query} #shorts",
            type="video",
            videoDuration="short",  # < 4 dk
            order="viewCount",
            publishedAfter=son_72h_iso(),
            maxResults=15,
        ).execute()
        ids = [it["id"]["videoId"] for it in r.get("items", []) if it.get("id", {}).get("videoId")]
        if not ids: return []

        # 2) videos.list — gerçek izlenme + duration filter
        vr = yt.videos().list(part="snippet,statistics,contentDetails", id=",".join(ids)).execute()
        for v in vr.get("items", []):
            izl = int(v["statistics"].get("viewCount", 0))
            if izl < esik: continue
            # 60s altı = Shorts
            dur = v["contentDetails"]["duration"]
            sn_m = re.search(r"PT(\d+)?M?(\d+)?S?", dur)
            sn = 0
            if "M" in dur:
                mm = re.search(r"(\d+)M", dur); sn += int(mm.group(1)) * 60 if mm else 0
            if "S" in dur:
                ss = re.search(r"(\d+)S", dur); sn += int(ss.group(1)) if ss else 0
            if sn > 90: continue  # Shorts max 60-90sn

            out.append({
                "video_id": v["id"],
                "title": v["snippet"]["title"][:100],
                "channel": v["snippet"]["channelTitle"],
                "views": izl,
                "publish": v["snippet"]["publishedAt"][:10],
                "duration_sn": sn,
                "query_match": query,
            })
    except Exception as h:
        msg = str(h)[:100]
        if "quota" in msg.lower():
            print(f"  [{query}] quota dolu, atlandı")
            raise  # üst seviye yakalasın
        print(f"  [{query}] hata: {msg}")
    return out


def main() -> int:
    # KOTA KORUMA: cikti dosyası son 24 saatte üretildiyse skip
    # (viral_radar her query 100 unit → 16 query = 1600 unit/run, günde 1 yeter)
    if CIKTI.exists():
        yas_saat = (datetime.now(timezone.utc).timestamp() - CIKTI.stat().st_mtime) / 3600
        if yas_saat < 24:
            print(f"[viral_radar] cikti {yas_saat:.1f}h yaşında — 24h cache geçerli, skip.")
            return 0

    yt = yt_istemci()
    print(f"[viral_radar] Son 72h niş'te trending Shorts taranıyor...")
    tum_sonuclar = []
    quota_dolu = False
    for q in NIS_ANAHTAR:
        if quota_dolu: break
        try:
            sonuc = search_viral(yt, q, esik=50000)  # 50K+ esik (sıkı değil)
            tum_sonuclar.extend(sonuc)
            print(f"  '{q}': {len(sonuc)} viral")
        except Exception as h:
            if "quota" in str(h).lower():
                quota_dolu = True
                break

    # Dedup by video_id, sort by views
    goren = {}
    for v in tum_sonuclar:
        if v["video_id"] not in goren or v["views"] > goren[v["video_id"]]["views"]:
            goren[v["video_id"]] = v
    sonuclar = sorted(goren.values(), key=lambda x: -x["views"])[:25]

    rapor = {
        "uretim": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "esik_izlenme": 50000,
        "zaman_penceresi_saat": 72,
        "toplam_viral": len(sonuclar),
        "viraller": sonuclar,
        # Haberci için kompakt format
        "angles_for_haberci": [
            f"{v['title'][:80]} ({v['views']:,} izl)"
            for v in sonuclar[:12]
        ],
    }
    CIKTI.write_text(json.dumps(rapor, ensure_ascii=False, indent=2))

    print(f"\n[viral_radar] Top 10 viral (son 72h):")
    for i, v in enumerate(sonuclar[:10], 1):
        print(f"  {i}. {v['views']:>7,} izl  | {v['title'][:65]}")
    print(f"\n  Yazıldı: {CIKTI.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
