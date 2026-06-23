"""
competitor_scan.py — Rakip kanal trend tarayıcısı.

YouTube Data API ile hayvan/doğa nişindeki top kanalların son 7 günlük
yayınlarını çeker, izlenme + başlık paterni analizi yapar.

Çıktı: competitor_signals.json — haberci.py'nin Gemini fallback'ine ek seed.

Kullanım:
    python competitor_scan.py
"""
import json, re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import Counter

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

PANEL_KOK = Path(__file__).parent
TOKEN = PANEL_KOK / "token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube"]
CIKTI = PANEL_KOK / "competitor_signals.json"

# Animal/nature niche kanalları — manuel seçilmiş, yüksek izlenmeli
RAKIP_KANALLAR = [
    {"name": "Brave Wilderness", "handle": "@BraveWilderness"},
    {"name": "BBC Earth", "handle": "@bbcearth"},
    {"name": "National Geographic", "handle": "@NatGeo"},
    {"name": "Smithsonian Channel", "handle": "@SmithsonianChannel"},
    {"name": "Wild Films India", "handle": "@WildFilmsIndia"},
    {"name": "Animal Planet", "handle": "@animalplanet"},
    {"name": "World Wildlife Fund", "handle": "@worldwildlifefund"},
    {"name": "Free High-Quality Documentaries", "handle": "@freedocumentary"},
]

STOPWORDS = set("a an the of in on at to for from with by and or but it is are was were be has have had do does did this that these those i you we they he she his her their our its as not no yes if then so than which what who when where why how can will would could should may might must about into over under between among up down out off across after before above below behind through during without within against own".split())


def yt_istemci():
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds.expired and creds.refresh_token: creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def kanal_id_ve_uploads(yt, handle: str) -> tuple[str, str] | None:
    """Handle → (channel_id, uploads_playlist_id). 1 unit quota."""
    try:
        r = yt.channels().list(part="id,contentDetails", forHandle=handle).execute()
        if not r.get("items"):
            return None
        ch = r["items"][0]
        return (ch["id"], ch["contentDetails"]["relatedPlaylists"]["uploads"])
    except Exception:
        return None


def son_yayinlar(yt, uploads_pl: str, gun: int = 7) -> list[dict]:
    """uploads playlist → 1 unit (search.list 100 unit yerine). Tarih client-side filtre."""
    after_dt = datetime.now(timezone.utc) - timedelta(days=gun)
    out = []
    try:
        r = yt.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_pl,
            maxResults=20,
        ).execute()
        for it in r.get("items", []):
            pub = it["contentDetails"].get("videoPublishedAt") or it["snippet"]["publishedAt"]
            try:
                pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except ValueError:
                continue
            if pub_dt < after_dt:
                continue
            out.append({
                "id": it["contentDetails"]["videoId"],
                "title": it["snippet"]["title"],
                "published": pub[:10],
            })
    except Exception as h:
        print(f"  playlistItems hata: {h}")
    return out


def main():
    # KOTA KORUMA: 24h cache
    if CIKTI.exists():
        yas_saat = (datetime.now(timezone.utc).timestamp() - CIKTI.stat().st_mtime) / 3600
        if yas_saat < 24:
            print(f"[competitor] cikti {yas_saat:.1f}h yaşında — 24h cache geçerli, skip.")
            return

    yt = yt_istemci()
    print(f"[competitor] {len(RAKIP_KANALLAR)} kanal taranıyor...")

    tum_video_ids = []
    kanal_yayinlari = {}
    for k in RAKIP_KANALLAR:
        info = kanal_id_ve_uploads(yt, k["handle"])
        if not info:
            print(f"  {k['name']} ID bulunamadı"); continue
        cid, uploads = info
        vids = son_yayinlar(yt, uploads, gun=7)
        kanal_yayinlari[k["name"]] = vids
        tum_video_ids.extend(v["id"] for v in vids)
        print(f"  {k['name']}: {len(vids)} yayın (7g)")

    # Stats batch
    stats = {}
    for i in range(0, len(tum_video_ids), 50):
        r = yt.videos().list(part="statistics,snippet", id=",".join(tum_video_ids[i:i+50])).execute()
        for it in r.get("items", []):
            stats[it["id"]] = {
                "views": int(it["statistics"].get("viewCount", 0)),
                "title": it["snippet"]["title"],
            }

    # En çok izlenen 30
    sirali = sorted(stats.values(), key=lambda v: -v["views"])
    top30 = sirali[:30]

    # Başlık kelime analizi
    kelime_sayaci = Counter()
    for v in top30:
        for w in re.findall(r"[A-Za-z]{3,}", v["title"].lower()):
            if w not in STOPWORDS:
                kelime_sayaci[w] += 1

    rapor = {
        "uretim": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kanal_sayisi": len([k for k, v in kanal_yayinlari.items() if v]),
        "toplam_yayin_7g": len(tum_video_ids),
        "rakip_top_30_izlenme": [{"title": v["title"][:80], "views": v["views"]} for v in top30],
        "rakiplerden_top_kelimeler": kelime_sayaci.most_common(20),
        # Gemini fallback prompt'a sokulacak — taze + 'sıcak' başlık ipucu
        "ipucu_konular": [v["title"][:120] for v in top30[:10]],
    }

    CIKTI.write_text(json.dumps(rapor, ensure_ascii=False, indent=2))
    print(f"\n[competitor] Yazıldı: {CIKTI}")
    print(f"  Top 5 rakip yayın:")
    for v in top30[:5]:
        print(f"    {v['views']:>8} izl | {v['title'][:60]}")


if __name__ == "__main__":
    main()
