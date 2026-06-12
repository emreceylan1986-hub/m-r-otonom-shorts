"""
analytics.py — YouTube Analytics API v2 köprüsü.
Retention (avg view %), CTR, traffic source, gün-gün abone/izlenme.

Kullanım:
    python analytics.py [--gun 14] [--cikti analytics.json]

Çıktı: analytics.json — son N gün kanal metrikleri + her video başına
       avg view duration + retention.
"""
import argparse, json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

PANEL_KOK = Path(__file__).parent
# Analytics token AYRI tutulur — yukleyici.py'nin youtube token'ını bozmaz
TOKEN_AN = PANEL_KOK / "token_analytics.json"
TOKEN_BASIT = PANEL_KOK / "token.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
CIKTI = PANEL_KOK / "analytics.json"


def istemciler():
    """Önce ayrı analytics token'ı dener. Yoksa flow başlatamaz (headless),
    sadece youtube scope ile YT API döndürür — analytics None olur."""
    if TOKEN_AN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_AN), SCOPES)
    elif TOKEN_BASIT.exists():
        # Fallback: token.json muhtemelen yt-analytics içermez → analytics fail
        # ama yukleyici scope'unu da bozma
        creds = Credentials.from_authorized_user_file(str(TOKEN_BASIT),
            ["https://www.googleapis.com/auth/youtube"])
    else:
        print("[analytics] token yok"); return None, None
    try:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
    except Exception as h:
        print(f"[analytics] refresh hata: {h}"); return None, None
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    try:
        yta = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    except Exception:
        yta = None
    return yt, yta


def kanal_kimligi(yt) -> str:
    ch = yt.channels().list(part="id", mine=True).execute()
    return ch["items"][0]["id"]


def kanal_kpi_gun_gun(yta, channel_id: str, gun: int = 14) -> dict:
    """Son N gün gün-gün izlenme, watch time, abone, beğeni."""
    son = datetime.now(timezone.utc).date()
    ilk = son - timedelta(days=gun)
    try:
        r = yta.reports().query(
            ids=f"channel=={channel_id}",
            startDate=ilk.isoformat(),
            endDate=son.isoformat(),
            metrics="views,estimatedMinutesWatched,subscribersGained,subscribersLost,likes,comments,shares",
            dimensions="day",
            sort="day",
        ).execute()
        return r
    except Exception as h:
        return {"error": str(h)}


def video_retention(yta, channel_id: str, video_id: str) -> dict:
    """Bir video için average view duration + average view percentage."""
    try:
        r = yta.reports().query(
            ids=f"channel=={channel_id}",
            startDate="2026-01-01",
            endDate=datetime.now(timezone.utc).date().isoformat(),
            metrics="views,averageViewDuration,averageViewPercentage,likes,comments,shares,subscribersGained",
            dimensions="video",
            filters=f"video=={video_id}",
        ).execute()
        return r
    except Exception as h:
        return {"error": str(h)}


def traffic_source(yta, channel_id: str, gun: int = 28) -> dict:
    """Traffic source dağılımı — Browse, Search, Suggested, External vs."""
    son = datetime.now(timezone.utc).date()
    ilk = son - timedelta(days=gun)
    try:
        r = yta.reports().query(
            ids=f"channel=={channel_id}",
            startDate=ilk.isoformat(),
            endDate=son.isoformat(),
            metrics="views,estimatedMinutesWatched,averageViewDuration",
            dimensions="insightTrafficSourceType",
            sort="-views",
        ).execute()
        return r
    except Exception as h:
        return {"error": str(h)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--gun", type=int, default=14, help="Son N gün (varsayılan 14)")
    p.add_argument("--cikti", default=str(CIKTI))
    args = p.parse_args()

    yt, yta = istemciler()
    if yt is None:
        print("[analytics] Token yok, çıkılıyor."); return 0
    if yta is None:
        print("[analytics] yt-analytics scope yok — sadece kanal istatistiği")
        ch = yt.channels().list(part="statistics,snippet", mine=True).execute()
        rapor = {"uretim": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "kanal_basit": ch["items"][0]["statistics"], "note": "yt-analytics scope eksik"}
        Path(args.cikti).write_text(json.dumps(rapor, ensure_ascii=False, indent=2))
        return 0
    ch_id = kanal_kimligi(yt)
    print(f"[analytics] Kanal ID: {ch_id}")

    rapor = {
        "uretim": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kanal_id": ch_id,
        "gun_kapsam": args.gun,
    }

    print(f"[analytics] Gün-gün KPI ({args.gun}g)...")
    rapor["gun_gun"] = kanal_kpi_gun_gun(yta, ch_id, args.gun)

    print(f"[analytics] Traffic source (28g)...")
    rapor["traffic_source"] = traffic_source(yta, ch_id, 28)

    # Per-video retention (yuklemeler.json'dan son 20 video)
    yj_dosya = PANEL_KOK / "yuklemeler.json"
    if yj_dosya.exists():
        videos = json.loads(yj_dosya.read_text())
        videos.sort(key=lambda v: v.get("zaman",""), reverse=True)
        rapor["video_retention"] = {}
        for v in videos[:20]:
            vid = v.get("video_id")
            if not vid: continue
            r = video_retention(yta, ch_id, vid)
            if "rows" in r and r["rows"]:
                rapor["video_retention"][vid] = {
                    "title": v.get("title",""),
                    "data": r["rows"][0],
                    "columns": [c["name"] for c in r["columnHeaders"]],
                }

    Path(args.cikti).write_text(json.dumps(rapor, ensure_ascii=False, indent=2))
    print(f"[analytics] Yazıldı: {args.cikti}")

    # Konsol özet
    if "rows" in rapor["gun_gun"]:
        rows = rapor["gun_gun"]["rows"]
        total_v = sum(r[1] for r in rows)
        total_w = sum(r[2] for r in rows) if len(rows[0]) > 2 else 0
        net_sub = sum(r[3] - r[4] for r in rows) if len(rows[0]) > 4 else 0
        print(f"  Son {args.gun}g: {total_v} izlenme, {total_w} dk watch, net {net_sub:+d} abone")
    return 0


if __name__ == "__main__":
    sys.exit(main())
