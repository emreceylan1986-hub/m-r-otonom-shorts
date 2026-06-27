"""
ab_title_test.py — A/B Başlık Test Loop'u (Faz 3).

Her yeni video için Gemini'den 2 farklı başlık üret, 1.'yi yayında kullan,
2.'yi state'e "alternatif" olarak yaz. 24 saat sonra Analytics ile karşılaştır
(views, ctr); kazanan paterni viral_patterns.json'a feedback olarak gönder.

Kullanım:
    python ab_title_test.py --uret <konu>       # 2 başlık üret, JSON döndür
    python ab_title_test.py --karsilastir       # 24h+ sonra verileri kıyasla
"""
import argparse, json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

PANEL_KOK = Path(__file__).parent
KAYIT = PANEL_KOK / "ab_title_test.json"


def baslik_iki_uret(konu: str) -> list[str]:
    """Gemini'den 2 farklı stil + ton'da başlık üret."""
    import bridge
    prompt = (
        f"Sen YouTube Shorts uzmanısın. Konu: {konu}\n\n"
        "İKİ farklı stilde tam ENGLISH başlık üret (her biri 50 karakterden kısa):\n"
        "1) STİL: Doğal merak — soruyla biten ('?') veya 'this/that' ile başlayan,\n"
        "   sürpriz vurgulu (örnek: 'This Lake Turns Animals to STONE?!').\n"
        "2) STİL: Direkt iddia — sayıyla başlayan veya emoji ile çarpıcı\n"
        "   (örnek: '600V Eels Hunt Like Lightning ⚡').\n\n"
        "JSON döndür (kod bloğu yok, sadece JSON):\n"
        '{"a": "...başlık 1...", "b": "...başlık 2..."}'
    )
    try:
        from bridge import gemini_metin_uret, _json_temizle_ve_parse
        r = gemini_metin_uret(prompt, sicaklik=0.9, max_token=300)
        data = _json_temizle_ve_parse(r.text if hasattr(r, "text") else r)
        return [data.get("a", ""), data.get("b", "")]
    except Exception as h:
        print(f"[ab] gemini hata: {h}"); return []


def ab_kaydet(konu: str, video_id: str, baslik_a: str, baslik_b: str) -> None:
    kayit = json.loads(KAYIT.read_text()) if KAYIT.exists() else []
    kayit.append({
        "zaman": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "konu": konu,
        "video_id": video_id,
        "baslik_a": baslik_a,
        "baslik_b": baslik_b,
        "kazanan": None,
        "olculmus": False,
    })
    KAYIT.write_text(json.dumps(kayit, ensure_ascii=False, indent=2))


def yt_istemci():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_file(str(PANEL_KOK / "token.json"),
        ["https://www.googleapis.com/auth/youtube"])
    if creds.expired and creds.refresh_token: creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def karsilastir():
    """24h+ önce yapılan testlerin sonucu — views ile A vs B kıyas."""
    if not KAYIT.exists():
        print("[ab] Kayıt yok"); return
    kayit = json.loads(KAYIT.read_text())
    yt = yt_istemci()
    now = datetime.now(timezone.utc)
    feedback = []
    for k in kayit:
        if k["olculmus"]: continue
        zaman = datetime.fromisoformat(k["zaman"].replace("Z","+00:00"))
        if (now - zaman).total_seconds() < 24*3600: continue
        r = yt.videos().list(part="statistics,snippet", id=k["video_id"]).execute()
        if not r.get("items"): continue
        v = r["items"][0]
        view = int(v["statistics"].get("viewCount", 0))
        # Hangi başlık seçildi → aktif
        aktif = v["snippet"]["title"]
        kazanan_isim = "A" if aktif == k["baslik_a"] else ("B" if aktif == k["baslik_b"] else "?")
        k["aktif_baslik"] = aktif
        k["kazanan"] = kazanan_isim
        k["view_24h"] = view
        k["olculmus"] = True
        feedback.append({
            "konu": k["konu"], "kazanan": kazanan_isim, "view": view,
            "kazanan_baslik": aktif,
            "kaybeden_baslik": k["baslik_b"] if kazanan_isim == "A" else k["baslik_a"],
        })
        print(f"  {k['video_id']}: {kazanan_isim} kazandı ({view} izl) | {aktif[:50]}")
    KAYIT.write_text(json.dumps(kayit, ensure_ascii=False, indent=2))
    # Feedback dosyası → pattern_detector.py + Gemini prompt'a
    if feedback:
        fb = PANEL_KOK / "ab_feedback.json"
        eski = json.loads(fb.read_text()) if fb.exists() else []
        fb.write_text(json.dumps(eski + feedback, ensure_ascii=False, indent=2))
        print(f"\n[ab] {len(feedback)} feedback → ab_feedback.json")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--uret", help="Konuyu ver, 2 başlık üret JSON yaz")
    p.add_argument("--kaydet", nargs=4, metavar=("KONU","VIDEO_ID","BAS_A","BAS_B"),
                   help="Test kayıtla")
    p.add_argument("--karsilastir", action="store_true",
                   help="24h+ önce yapılan tüm testlerin sonucunu çek")
    args = p.parse_args()

    if args.uret:
        b = baslik_iki_uret(args.uret)
        print(json.dumps({"a": b[0] if b else "", "b": b[1] if len(b)>1 else ""}, ensure_ascii=False))
    elif args.kaydet:
        ab_kaydet(*args.kaydet)
        print("Kayıt OK")
    elif args.karsilastir:
        karsilastir()
    else:
        p.print_help()


if __name__ == "__main__":
    main()
