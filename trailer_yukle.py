#!/usr/bin/env python3
"""
trailer_yukle.py — branding/trailer.mp4 YouTube'a yükle + kanal trailer set.

Kullanım: python3 trailer_yukle.py
"""
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

PANEL = Path(__file__).parent
TOKEN = PANEL / "token.json"
BRANDING = PANEL / "branding"
TRAILER_MP4 = BRANDING / "trailer.mp4"

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

TRAILER_TITLE = "Welcome to TrendCatcher — Wild Facts in 30 Seconds"

TRAILER_DESC = """Welcome to TrendCatcher — wild facts about extreme animals, anomaly places, and the planet's strangest survivors.

Eagles that hunt goats off cliffs. Lakes that boil. Creatures that shouldn't exist.

Four new shorts every day at 3 PM, 7 PM, 10 PM and 1 AM (TR).

For the curious. For the explorer. For anyone who still wonders.

Subscribe → https://youtube.com/@TrendCatcher?sub_confirmation=1

#Shorts #nature #wildlife #animals #science #anomaly"""

TRAILER_TAGS = [
    "trendcatcher", "wildlife", "nature", "animals", "extreme animals",
    "science", "shorts", "wild facts", "channel trailer", "welcome",
]


def log(msg):
    print(f"[trailer_yukle] {msg}", flush=True)


def yt_istemci():
    if not TOKEN.exists():
        raise SystemExit("token.json yok")
    creds = Credentials.from_authorized_user_file(str(TOKEN), YOUTUBE_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def video_yukle(yt, mp4: Path) -> str:
    log(f"1) Trailer yükleniyor: {mp4.name} ({mp4.stat().st_size//1024} KB)")
    body = {
        "snippet": {
            "title": TRAILER_TITLE,
            "description": TRAILER_DESC,
            "tags": TRAILER_TAGS,
            "categoryId": "15",  # Pets & Animals (TC nişi)
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "embeddable": True,
            "madeForKids": False,
        },
    }
    medya = MediaFileUpload(str(mp4), mimetype="video/mp4", chunksize=1024*1024, resumable=True)
    istek = yt.videos().insert(part="snippet,status", body=body, media_body=medya)
    yanit = None
    son = -1
    while yanit is None:
        durum, yanit = istek.next_chunk()
        if durum:
            yuzde = int(durum.progress() * 100)
            if yuzde != son:
                log(f"   Yükleniyor: %{yuzde}")
                son = yuzde
    vid = yanit["id"]
    log(f"   ✓ Video ID: {vid}")
    log(f"   URL: https://youtube.com/watch?v={vid}")
    return vid


def trailer_set(yt, video_id: str):
    log("2) Kanal trailer set ediliyor (unsubscribedTrailer)...")
    r = yt.channels().list(part="brandingSettings", mine=True).execute()
    kanal = r["items"][0]
    kanal_id = kanal["id"]
    mevcut = kanal.get("brandingSettings", {})
    eski_trailer = mevcut.get("channel", {}).get("unsubscribedTrailer")

    body = {
        "id": kanal_id,
        "brandingSettings": {
            "channel": {
                **mevcut.get("channel", {}),
                "unsubscribedTrailer": video_id,
            }
        },
    }
    try:
        yt.channels().update(part="brandingSettings", body=body).execute()
        log(f"   ✓ Yeni trailer set: {video_id}")
        if eski_trailer and eski_trailer != video_id:
            try:
                yt.videos().delete(id=eski_trailer).execute()
                log(f"   ✓ Eski trailer silindi: {eski_trailer}")
            except HttpError as e:
                log(f"   ⚠ Eski trailer silinemedi ({eski_trailer}): {str(e)[:80]}")
        return True
    except HttpError as e:
        log(f"   ❌ Trailer set hata: {e}")
        return False


def main():
    if not TRAILER_MP4.exists():
        raise SystemExit(f"trailer yok: {TRAILER_MP4}\nÖnce: python3 trailer_uret.py")

    yt = yt_istemci()
    vid = video_yukle(yt, TRAILER_MP4)
    ok = trailer_set(yt, vid)

    # Creator yorumu (shorts pipeline ile aynı)
    try:
        import pinned_comment
        pinned_comment.creator_comment_at(yt, vid, TRAILER_TITLE, TRAILER_DESC[:300])
    except Exception as e:
        log(f"  Creator yorum atlandı: {e}")

    log("")
    log("=== ÖZET ===")
    log(f"  Video: https://youtube.com/watch?v={vid}")
    log(f"  Trailer set: {'✓' if ok else '❌'}")


if __name__ == "__main__":
    main()
