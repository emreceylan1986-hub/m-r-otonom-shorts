"""
pinned_comment.py — Creator Comment Bomba (Faz 4 turbo).

Yeni yayın sonrası kanalımız adına TOP-LEVEL yorum atar — "creator's badge"
alır → UI'da üst sıralarda görünür → zincir reaksiyon başlatır.

Yorum şablonu video konusuna uyarlanır (Gemini ile 1 satır):
    "Which fact shocked you most? Drop a 🤯 below!"

NOT: YouTube API ile pinleme yok — pin sadece UI'dan yapılır. AMA creator
comment zaten "Pinned by creator" alanına manuel pin yapılana kadar bile
yüksek görünürlük alır + algoritma engagement signal sayar.

Kullanım (modül olarak):
    from pinned_comment import creator_comment_at
    creator_comment_at(yt, video_id, baslik)
"""
import sys
from pathlib import Path

PANEL_KOK = Path(__file__).parent

# Hazır soru havuzu — Gemini fail olursa düşülecek fallback
SORULAR = [
    "Which fact shocked you most? Drop a 🤯 below!",
    "Did you know this? Tell me in comments 👇",
    "Wait, was this new to you? Let me know!",
    "Nature is wild. What's the weirdest fact YOU know?",
    "This blew my mind. Yours too? 👇",
    "Drop a 🌍 if you learned something new today!",
    "Comment your favorite animal fact 👇",
    "Did this surprise you as much as me?",
]


def gemini_soru_uret(baslik: str, senaryo: str = "") -> str | None:
    """Video konusuna uygun, kısa engagement sorusu üret."""
    try:
        import bridge
    except ImportError:
        return None
    sistem = (
        "You are a YouTube Shorts creator about to write a PINNED COMMENT under "
        "your own video. Goal: trigger replies. Output ONE engaging question "
        "(max 12 words, English). NO hashtags, NO links, NO 'subscribe'. End "
        "with an emoji or 👇."
    )
    prompt = (
        f"Video title: {baslik}\n"
        f"Script context: {senaryo[:250]}\n\n"
        f"Your pinned comment (1 line, max 12 words):"
    )
    try:
        c = bridge.gemini_metin_uret(prompt=prompt, sistem_promptu=sistem,
                                      sicaklik=0.9, max_token=60).strip()
        c = c.strip('"').strip("'").strip()
        if "#" in c or "http" in c.lower():
            c = c.split("#")[0].split("http")[0].strip()
        if 5 < len(c) < 140:
            return c
    except Exception as h:
        print(f"  Gemini soru üretemedi: {str(h)[:120]}")
    return None


def creator_comment_at(yt, video_id: str, baslik: str = "", senaryo: str = "") -> str | None:
    """Creator olarak top-level comment at. Comment ID döner."""
    import random
    soru = gemini_soru_uret(baslik, senaryo) or random.choice(SORULAR)
    try:
        r = yt.commentThreads().insert(
            part="snippet",
            body={"snippet": {
                "videoId": video_id,
                "topLevelComment": {
                    "snippet": {"textOriginal": soru}
                }
            }}
        ).execute()
        cid = r.get("id")
        print(f"  ✓ Creator yorum atıldı: '{soru[:60]}' (id={cid[:30]}...)")
        return cid
    except Exception as h:
        msg = str(h)[:200]
        print(f"  ✗ Creator yorum fail: {msg}")
        return None


def main() -> int:
    """Standalone test: .basarili_yayin'den video_id okuyup yorum at."""
    import json
    f = PANEL_KOK / ".basarili_yayin"
    if not f.exists():
        print("Test için .basarili_yayin yok"); return 1
    d = json.loads(f.read_text())

    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl",
              "https://www.googleapis.com/auth/youtube"]
    creds = Credentials.from_authorized_user_file(str(PANEL_KOK / "token.json"), SCOPES)
    if creds.expired and creds.refresh_token: creds.refresh(Request())
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    cid = creator_comment_at(yt, d["video_id"], d.get("title", ""))
    return 0 if cid else 1


if __name__ == "__main__":
    sys.exit(main())
