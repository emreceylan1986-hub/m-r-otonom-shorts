"""
community_post.py — YouTube Community Tab Post (Faz 7).

YouTube Community Post resmi API'si HENÜZ public DEĞİL (2024-2026).
Workaround stratejileri:

1) youtube.channelSections veya activities API ile post deneme (resmi yol)
2) Web flow + selenium (yasak — bot policy)
3) Manuel rehber döküman → kullanıcı her viral video sonrası elle paylaşır

Bu modül: viral video tespit eder + manuel paylaşım için talimat raporu üretir.

Çıktı: community_post_queue.json — kuyruktaki "manuel paylaşılacak" pollar.

Kullanım:
    python3 community_post.py            # son 7g viral'leri tara + kuyruğa ekle
    python3 community_post.py --raporu   # kuyruğu listele
"""
import argparse, json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PANEL_KOK = Path(__file__).parent
TOKEN = PANEL_KOK / "token.json"
KUYRUK = PANEL_KOK / "community_post_queue.json"

VIRAL_ESIK = 500  # 500+ izlenme = viral, Community Post adayı


def yt_istemci():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    SCOPES = ["https://www.googleapis.com/auth/youtube"]
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds.expired and creds.refresh_token: creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def gemini_poll_uret(baslik: str) -> dict:
    """Video başlığına göre Community Post poll metni üret."""
    try:
        import bridge
    except ImportError:
        return {"baslik": "What did you think?", "secenekler": ["🤯 Mind-blown", "😍 Loved it", "🤔 Hmm"]}
    sistem = (
        "You write YouTube Community Tab POLLS for a nature/animals shorts channel. "
        "Output JSON: {\"question\": \"...\", \"options\": [\"...\", \"...\", \"...\"]}. "
        "Question max 15 words. 3 options, each max 5 words. Add an emoji to each option. "
        "Tone: playful, casual."
    )
    try:
        r = bridge.gemini_metin_uret(
            prompt=f"Video: {baslik}\n\nWrite the poll (3 options, JSON):",
            sistem_promptu=sistem,
            sicaklik=0.9, max_token=180,
        )
        # JSON parse
        import re
        m = re.search(r"\{.*\}", r, re.DOTALL)
        if m:
            d = json.loads(m.group())
            return {
                "baslik": d.get("question", "What blew your mind?"),
                "secenekler": d.get("options", [])[:3],
            }
    except Exception as h:
        print(f"  Gemini fail: {str(h)[:100]}")
    return {"baslik": f"Did you know about {baslik[:30]}?",
            "secenekler": ["🤯 Mind-blown", "😍 Loved it", "🤔 Knew it"]}


def kuyruga_ekle(yt, viral_videos: list[dict]):
    """Viral video adaylarını manuel paylaşım kuyruğuna ekle."""
    kuyruk = json.loads(KUYRUK.read_text()) if KUYRUK.exists() else []
    eklenen_ids = {q["video_id"] for q in kuyruk}
    yeni_eklenen = 0
    for v in viral_videos:
        if v["id"] in eklenen_ids: continue
        poll = gemini_poll_uret(v["title"])
        kuyruk.append({
            "video_id": v["id"],
            "title": v["title"],
            "izl": v["izl"],
            "publish": v["publish"],
            "poll": poll,
            "queued_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "posted": False,
        })
        yeni_eklenen += 1
        print(f"  + Kuyruğa eklendi: {v['title'][:50]} ({v['izl']} izl)")
    KUYRUK.write_text(json.dumps(kuyruk, ensure_ascii=False, indent=2))
    return yeni_eklenen


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raporu", action="store_true", help="Mevcut kuyruğu listele")
    p.add_argument("--gun", type=int, default=7, help="Son N gün tara")
    p.add_argument("--esik", type=int, default=VIRAL_ESIK)
    args = p.parse_args()

    if args.raporu:
        if not KUYRUK.exists():
            print("Kuyruk boş"); return 0
        kuyruk = json.loads(KUYRUK.read_text())
        bekleyen = [q for q in kuyruk if not q.get("posted")]
        print(f"📋 Community Post Kuyruğu: {len(bekleyen)} bekliyor")
        for q in bekleyen:
            print(f"\n  📹 {q['title']}")
            print(f"     ID: {q['video_id']}  |  {q['izl']} izl  |  {q['publish']}")
            print(f"     Poll: {q['poll']['baslik']}")
            for opt in q['poll']['secenekler']:
                print(f"       • {opt}")
            print(f"     Studio: https://studio.youtube.com/channel/UC.../community")
        print(f"\n→ Bu poll'leri YouTube Studio → Community Tab'da elle yayınla.")
        return 0

    # Viral video adayları
    yt = yt_istemci()
    yj_yolu = PANEL_KOK / "yuklemeler.json"
    yj = json.loads(yj_yolu.read_text()) if yj_yolu.exists() else []
    aday_ids = [v["video_id"] for v in yj if v.get("video_id")][-50:]

    son_n_gun = datetime.now(timezone.utc) - timedelta(days=args.gun)
    viraller = []
    for i in range(0, len(aday_ids), 50):
        r = yt.videos().list(part="statistics,snippet,status", id=",".join(aday_ids[i:i+50])).execute()
        for it in r.get("items", []):
            try:
                pub = datetime.fromisoformat(it["snippet"]["publishedAt"].replace("Z","+00:00"))
                if pub < son_n_gun: continue
                if it["status"]["privacyStatus"] != "public": continue
                izl = int(it["statistics"].get("viewCount", 0))
                if izl < args.esik: continue
                viraller.append({
                    "id": it["id"], "title": it["snippet"]["title"][:80],
                    "publish": it["snippet"]["publishedAt"][:10], "izl": izl,
                })
            except Exception: pass

    print(f"\n🎯 Son {args.gun}g'de viral video ({args.esik}+): {len(viraller)}")
    eklenen = kuyruga_ekle(yt, viraller)
    print(f"\n[community] {eklenen} yeni poll kuyruğa eklendi → '--raporu' ile listele")
    return 0


if __name__ == "__main__":
    sys.exit(main())
