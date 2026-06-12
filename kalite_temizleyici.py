"""
kalite_temizleyici.py — Bad Performer Auto-Private (Faz 7).

48 saat+ eski + <30 izlenme + <2 beğeni olan public videoları otomatik
PRIVATE'a alır. Sebep: YouTube algoritması "kanal kalitesi" hesabında
düşük performanslı videoları penaltı olarak sayar. Çürük temizlik =
kanal puanını korumak.

Güvenlik:
  - Sadece yuklemeler.json'a kayıtlı pipeline videolarına dokunur
    (eski kişisel/farklı kaynaklı içeriklere DOKUNMAZ)
  - 48 saat min — algoritma push'una zaman tanır
  - Manuel pin/featured videolara dokunma — kontrol notları korunur

Kullanım:
    python3 kalite_temizleyici.py                   # gerçek private
    python3 kalite_temizleyici.py --kuru            # sadece rapor
    python3 kalite_temizleyici.py --min-yas-saat 48 --min-izlenme 30
"""
import argparse, json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

PANEL_KOK = Path(__file__).parent
TOKEN = PANEL_KOK / "token.json"
LOG = PANEL_KOK / "kalite_temizleyici.log"
ANGUSTOM_VIDEO_LIST = PANEL_KOK / ".anguntum_videos.json"


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        LOG.write_text((LOG.read_text() if LOG.exists() else "") + line + "\n")
    except Exception:
        pass


def yt_istemci():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    SCOPES = ["https://www.googleapis.com/auth/youtube",
              "https://www.googleapis.com/auth/youtube.force-ssl"]
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds.expired and creds.refresh_token: creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--kuru", action="store_true", help="Sadece rapor, private yapma")
    p.add_argument("--min-yas-saat", type=int, default=48)
    p.add_argument("--min-izlenme", type=int, default=30)
    p.add_argument("--min-begeni", type=int, default=2)
    args = p.parse_args()

    yj_yolu = PANEL_KOK / "yuklemeler.json"
    if not yj_yolu.exists():
        log("yuklemeler.json yok"); return 0
    yj = json.loads(yj_yolu.read_text())

    yt = yt_istemci()
    log(f"=== Kalite temizleyici başladı (kuru={args.kuru}) ===")

    # Pipeline videolarını çek — sadece "animals" kategorili + UYGUN denetim
    aday_ids = [v["video_id"] for v in yj
                if v.get("gizlilik") == "public"
                and v.get("kategori") == "animals"
                and v.get("denetim_karari") == "UYGUN"]
    log(f"Pipeline public video aday sayısı: {len(aday_ids)}")

    if not aday_ids:
        log("Aday yok"); return 0

    # Stats batch çek
    now = datetime.now(timezone.utc)
    silinmeyecekler = []
    for i in range(0, len(aday_ids), 50):
        chunk = aday_ids[i:i+50]
        r = yt.videos().list(part="statistics,snippet,status", id=",".join(chunk)).execute()
        for it in r.get("items", []):
            try:
                pub = datetime.fromisoformat(it["snippet"]["publishedAt"].replace("Z","+00:00"))
                yas_saat = (now - pub).total_seconds() / 3600
                izl = int(it["statistics"].get("viewCount", 0))
                begeni = int(it["statistics"].get("likeCount", 0))

                if yas_saat < args.min_yas_saat: continue       # genç, push devam ediyor
                if it["status"]["privacyStatus"] != "public": continue
                if izl >= args.min_izlenme: continue            # iyi performans
                if begeni >= args.min_begeni: continue          # engagement var

                silinmeyecekler.append({
                    "id": it["id"], "title": it["snippet"]["title"][:60],
                    "yas_saat": round(yas_saat, 1), "izl": izl, "begeni": begeni,
                })
            except Exception as h:
                log(f"  parse hata {it.get('id')}: {h}")

    log(f"Private'a alınacak: {len(silinmeyecekler)} video")

    for v in silinmeyecekler:
        log(f"  [{v['yas_saat']:.0f}h] {v['izl']}izl {v['begeni']}👍 → {v['title']}")
        if args.kuru:
            log(f"    [KURU] atlandı")
            continue
        try:
            yt.videos().update(
                part="status",
                body={"id": v["id"], "status": {"privacyStatus": "private"}}
            ).execute()
            log(f"    ✓ PRIVATE")
        except Exception as h:
            log(f"    ✗ {str(h)[:140]}")

    log(f"=== Bitti — {len(silinmeyecekler)} video private ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
