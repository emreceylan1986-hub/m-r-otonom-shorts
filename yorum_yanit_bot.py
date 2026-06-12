"""
yorum_yanit_bot.py — TrendCatcher Yorum Otomatik Yanıt Botu.

Her run'da:
  1. Kanalın son 30 videosunun yorumlarını çek
  2. Daha önce cevaplanmamış + yaşı 5+ dakika olan + sahibimiz olmayan yorumları bul
  3. Gemini ile yoruma uygun, samimi, kısa İngilizce cevap üret
  4. YouTube API üzerinden REPLY olarak gönder
  5. State'e işle (comment_replies.json) — aynı yoruma 2 kez cevap atmaz

Scope: youtube.force-ssl (zaten var — token upgrade'inde aktive edildi)

Kullanım:
    python3 yorum_yanit_bot.py
    python3 yorum_yanit_bot.py --kuru   # test modu, yorum atmaz sadece taslak yazar
    python3 yorum_yanit_bot.py --min-yas 5  # default 5 dakika
    python3 yorum_yanit_bot.py --max-cevap 20  # bir run'da max yanıt
"""
import argparse, json, os, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

PANEL_KOK = Path(__file__).parent
TOKEN = PANEL_KOK / "token.json"
DURUM = PANEL_KOK / "comment_replies.json"
LOG = PANEL_KOK / "yorum_yanit.log"

# Kısa "👏" "🔥" tipi yorumlar — Gemini'ye gitmeden hazır cevap
HIZLI_CEVAPLAR = {
    "👏": ["Thank you! 🙏", "Glad you enjoyed it! 🙌", "Means a lot! ❤️"],
    "🔥": ["So glad you liked it! 🔥", "Thanks for the fire! 🙌", "Appreciate it!"],
    "❤️": ["Thank you! ❤️", "Means everything! 🙏", "Glad you loved it!"],
    "wow": ["Right?! Nature is wild 🌍", "I know, blew my mind too!", "Glad it surprised you!"],
}

SISTEM_PROMPTU = """You are the creator of a YouTube Shorts channel called TrendCatcher.
Niche: animals, nature, amazing facts. Audience: global English-speaking
internet-fluent viewers (Gen Z + Millennial). Tone = like a witty creator
replying to friends, not a customer service rep.

Your job: write a SHORT, confident, TONE-MATCHED REPLY to a viewer's comment.

═══ STEP 1 — DETECT THE TONE ═══

Look at the words + emojis TOGETHER. Internet English uses exaggerated anger
for COMEDIC effect. Don't take literal offense at "damned", "wtf", "bruh",
or 😡/🤬/😤 — these are usually PLAYFUL FRUSTRATION, not real anger.

Tone signals:
- "damned", "wtf", "tf", "bruh", "lol", "fr fr" + 😡/🤬/😅/💀 → PLAYFUL
- Real anger looks like: long rants, multiple lines, no humor markers,
  "this is bad", "garbage", "disappointed"
- Pure curiosity = neutral
- Pure praise = warm

═══ STEP 2 — MATCH THE TONE ═══

- PLAYFUL/joking → match with light humor + fact ("Ha! That huge flat
  oval — sneaky bigfella 😅", "Right?! Nature went wild on this one")
- Neutral question → confident 1-line answer with a fact
- Praise/emoji → warm 1-line thanks, NO emoji overload
- Real criticism (rare) → pivot to a fact, no apology, no promise
- "Where is X / what is X" → describe X with visual cue + tiny fact

═══ HARD RULES ═══

- 1 sentence, max 14 words.
- NEVER apologize. BANNED: sorry, apologies, my bad, fault, mistake,
  "we should have", "next time", "promise", "thanks for the feedback".
- NEVER ask to subscribe, like, comment, share.
- NEVER use hashtags or links.
- NEVER repeat their comment verbatim.
- English only.
- Max 1 emoji per reply (only if it adds vibe).

Output ONLY the reply text — no quotes, no "Reply:" prefix, no formatting."""


def yt_istemci():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl",
              "https://www.googleapis.com/auth/youtube"]
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds.expired and creds.refresh_token: creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    satir = f"[{ts}] {msg}"
    print(satir)
    try:
        LOG.write_text((LOG.read_text() if LOG.exists() else "") + satir + "\n")
    except Exception:
        pass


def durum_oku() -> dict:
    if not DURUM.exists():
        return {"replied": {}, "last_run": None}
    try:
        return json.loads(DURUM.read_text())
    except Exception:
        return {"replied": {}, "last_run": None}


def durum_yaz(d: dict):
    DURUM.write_text(json.dumps(d, ensure_ascii=False, indent=2))


def kanal_bilgisi(yt) -> dict:
    """Kanal sahibi ID — kendi yorumlarımıza cevap vermeyelim."""
    ch = yt.channels().list(part="id,snippet,contentDetails", mine=True).execute()
    ci = ch["items"][0]
    return {
        "id": ci["id"],
        "title": ci["snippet"]["title"],
        "uploads_playlist": ci["contentDetails"]["relatedPlaylists"]["uploads"],
    }


def son_video_idleri(yt, uploads_playlist: str, limit: int = 30) -> list[str]:
    """Son N videonun ID'si."""
    out = []
    nxt = None
    while len(out) < limit:
        r = yt.playlistItems().list(
            part="contentDetails", playlistId=uploads_playlist,
            maxResults=min(50, limit - len(out)), pageToken=nxt
        ).execute()
        out.extend(it["contentDetails"]["videoId"] for it in r.get("items", []))
        nxt = r.get("nextPageToken")
        if not nxt: break
    return out[:limit]


def video_yorumlari(yt, video_id: str) -> list[dict]:
    """Bir videonun TOP-LEVEL yorumları (reply'lar değil)."""
    out = []
    try:
        r = yt.commentThreads().list(
            part="snippet", videoId=video_id, maxResults=100,
            order="time", textFormat="plainText",
        ).execute()
        for it in r.get("items", []):
            s = it["snippet"]["topLevelComment"]["snippet"]
            out.append({
                "comment_id": it["snippet"]["topLevelComment"]["id"],
                "video_id": video_id,
                "author": s.get("authorDisplayName", ""),
                "author_channel_id": s.get("authorChannelId", {}).get("value", ""),
                "metin": s.get("textOriginal", "") or s.get("textDisplay", ""),
                "yayinlanma": s.get("publishedAt", ""),
                "begeni": s.get("likeCount", 0),
                "reply_sayisi": it["snippet"].get("totalReplyCount", 0),
            })
    except Exception as h:
        log(f"  video {video_id[:8]} yorum çekme fail: {str(h)[:140]}")
    return out


def hizli_cevap_var_mi(metin: str) -> str | None:
    """Çok kısa yorumlar için template cevap (Gemini quota tasarrufu)."""
    import random
    m = metin.strip().lower()
    if len(m) <= 4:
        for k, v in HIZLI_CEVAPLAR.items():
            if k in m:
                return random.choice(v)
    return None


def gemini_cevap_uret(yorum: str, video_baslik: str = "") -> str | None:
    """Yoruma uygun Gemini reply üret."""
    import bridge
    prompt = (
        f"Video title: {video_baslik}\n"
        f"Viewer comment: \"{yorum}\"\n\n"
        f"Write your reply now (1 sentence, max 12 words, English only):"
    )
    try:
        cevap = bridge.gemini_metin_uret(
            prompt=prompt,
            sistem_promptu=SISTEM_PROMPTU,
            sicaklik=0.85,
            max_token=80,
        ).strip()
        # Tırnak/format temizle
        cevap = cevap.strip('"').strip("'").strip()
        # Hashtag/link varsa kes
        if "#" in cevap or "http" in cevap.lower():
            cevap = cevap.split("#")[0].split("http")[0].strip()
        if len(cevap) > 200:
            cevap = cevap[:200]
        if not cevap or len(cevap) < 3:
            return None
        return cevap
    except Exception as h:
        log(f"  Gemini cevap üretemedi: {str(h)[:120]}")
        return None


def reply_gonder(yt, parent_comment_id: str, metin: str) -> bool:
    """YouTube'a reply gönder."""
    try:
        r = yt.comments().insert(
            part="snippet",
            body={"snippet": {"parentId": parent_comment_id, "textOriginal": metin}},
        ).execute()
        return True
    except Exception as h:
        log(f"  Reply gönderim fail: {str(h)[:180]}")
        return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--kuru", action="store_true", help="Test modu — sadece taslak yazar, göndermez")
    p.add_argument("--min-yas", type=int, default=5, help="Yorumun min yaşı (dakika)")
    p.add_argument("--max-cevap", type=int, default=20, help="Bir run'da max cevap sayısı")
    p.add_argument("--video-sayisi", type=int, default=30, help="Son N video taranır")
    args = p.parse_args()

    yt = yt_istemci()
    kanal = kanal_bilgisi(yt)
    log(f"=== Bot başladı — Kanal: {kanal['title']} ===")

    durum = durum_oku()
    replied = durum.get("replied", {})

    now = datetime.now(timezone.utc)
    min_yas = timedelta(minutes=args.min_yas)

    video_ids = son_video_idleri(yt, kanal["uploads_playlist"], args.video_sayisi)
    log(f"Son {len(video_ids)} video taranıyor...")

    aday_yorumlar = []
    for vid in video_ids:
        for yorum in video_yorumlari(yt, vid):
            # Atlama kuralları
            if yorum["comment_id"] in replied:
                continue
            if yorum["author_channel_id"] == kanal["id"]:
                continue  # Kendi yorumumuza cevap verme
            if not yorum["metin"].strip():
                continue
            # Yaş kontrolü
            try:
                t = datetime.fromisoformat(yorum["yayinlanma"].replace("Z", "+00:00"))
                if (now - t) < min_yas:
                    continue
            except Exception:
                continue
            yorum["yayinlanma_dt"] = t
            aday_yorumlar.append(yorum)
        time.sleep(0.05)

    # En eski (en az 5 dk önce) önce, ama 24 saat içi
    aday_yorumlar = [y for y in aday_yorumlar if (now - y["yayinlanma_dt"]) < timedelta(hours=72)]
    aday_yorumlar.sort(key=lambda y: y["yayinlanma_dt"])
    log(f"Cevaplanacak aday yorum: {len(aday_yorumlar)} (max {args.max_cevap} işlenecek)")

    cevaplanan = 0
    for yorum in aday_yorumlar[:args.max_cevap]:
        log(f"\n→ Yorum: {yorum['author']}: {yorum['metin'][:80]}")
        # Önce hızlı cevap dene
        cevap = hizli_cevap_var_mi(yorum["metin"])
        kaynak = "hizli"
        if not cevap:
            # Video başlığını al — daha iyi prompt
            try:
                vr = yt.videos().list(part="snippet", id=yorum["video_id"]).execute()
                baslik = vr["items"][0]["snippet"]["title"] if vr.get("items") else ""
            except Exception:
                baslik = ""
            cevap = gemini_cevap_uret(yorum["metin"], baslik)
            kaynak = "gemini"

        if not cevap:
            log(f"  Cevap üretilemedi, atlandı")
            continue

        log(f"  Cevap ({kaynak}): {cevap}")

        if args.kuru:
            log(f"  [KURU MOD] Gönderim atlandı")
            continue

        if reply_gonder(yt, yorum["comment_id"], cevap):
            log(f"  ✓ Reply gönderildi")
            replied[yorum["comment_id"]] = {
                "video_id": yorum["video_id"],
                "author": yorum["author"],
                "asıl_yorum": yorum["metin"][:200],
                "cevap": cevap,
                "kaynak": kaynak,
                "ts": now.isoformat(timespec="seconds"),
            }
            cevaplanan += 1
            durum["replied"] = replied
            durum_yaz(durum)
        else:
            log(f"  ✗ Gönderim başarısız")

        # Rate limit — bot izlenimi vermesin, yorum'lar arası 4-8 sn
        time.sleep(5)

    durum["last_run"] = now.isoformat(timespec="seconds")
    durum["last_replied_count"] = cevaplanan
    durum_yaz(durum)

    log(f"\n=== Bot bitti — {cevaplanan} cevap gönderildi (toplam history: {len(replied)}) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
