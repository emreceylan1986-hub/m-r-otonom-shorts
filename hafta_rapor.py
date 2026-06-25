"""
hafta_rapor.py — Haftalık kanal performans raporu (Pazar gece).

Çıktı: hafta_rapor.md (markdown, repo'ya commit edilir, GitHub Issue açılır).

Metrikler:
  - Abone delta (geçen haftaya göre)
  - Toplam view (son 7 gün)
  - Top 3 video + alt 3 video
  - Pattern analizi (hangi başlık kalıbı ne kadar tuttu)
  - 0/<50 view video sayısı

Kullanım:
  python3 hafta_rapor.py                # rapor üret + repo'ya yaz
  python3 hafta_rapor.py --print-only   # sadece stdout
"""
import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

PANEL_KOK = Path(__file__).parent
TOKEN = PANEL_KOK / "token.json"
RAPOR = PANEL_KOK / "hafta_rapor.md"
GECMIS = PANEL_KOK / "hafta_rapor_gecmis.json"

SCOPES = ["https://www.googleapis.com/auth/youtube"]


def yt_istemci():
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--print-only", action="store_true")
    args = p.parse_args()

    yt = yt_istemci()
    now = datetime.now(timezone.utc)

    # Kanal istatistik
    ch = yt.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()["items"][0]
    st = ch["statistics"]
    kanal_adi = ch["snippet"]["title"]
    abone = int(st.get("subscriberCount", 0))
    toplam_view = int(st.get("viewCount", 0))
    toplam_video = int(st.get("videoCount", 0))

    # Geçen hafta karşılaştırma
    gecmis = []
    if GECMIS.exists():
        try:
            gecmis = json.loads(GECMIS.read_text())
        except Exception:
            gecmis = []
    onceki = gecmis[-1] if gecmis else None
    abone_delta = abone - onceki["abone"] if onceki else 0
    view_delta = toplam_view - onceki["toplam_view"] if onceki else 0

    # Son 14 video (haftalık + bir önceki hafta karşılaştırma)
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    pi = yt.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=30).execute()
    ids = [it["contentDetails"]["videoId"] for it in pi["items"]]
    vlist = []
    for i in range(0, len(ids), 50):
        r = yt.videos().list(part="snippet,statistics", id=",".join(ids[i:i+50])).execute()
        for it in r.get("items", []):
            pub = datetime.fromisoformat(it["snippet"]["publishedAt"].replace("Z", "+00:00"))
            age_h = (now - pub).total_seconds() / 3600
            s = it["statistics"]
            vlist.append({
                "id": it["id"],
                "title": it["snippet"]["title"],
                "views": int(s.get("viewCount", 0)),
                "likes": int(s.get("likeCount", 0)),
                "comments": int(s.get("commentCount", 0)),
                "age_h": age_h,
            })
    vlist.sort(key=lambda x: -x["views"])

    # Haftalık özet
    son7 = [v for v in vlist if v["age_h"] < 168]
    s7_top = sorted(son7, key=lambda x: -x["views"])[:3]
    s7_bot = sorted(son7, key=lambda x: x["views"])[:3]
    s7_toplam_view = sum(v["views"] for v in son7)
    s7_ort_view = s7_toplam_view // max(1, len(son7))
    s7_sifir = sum(1 for v in son7 if v["views"] < 50)

    md = [f"# 📊 {kanal_adi} — Haftalık Rapor",
          f"_{now.isoformat(timespec='minutes')}_\n",
          "## Özet",
          f"- **Abone:** {abone:,} ({abone_delta:+d} bu hafta)",
          f"- **Toplam view:** {toplam_view:,} ({view_delta:+,} bu hafta)",
          f"- **Toplam video:** {toplam_video}",
          f"- **Son 7 gün:** {len(son7)} video, {s7_toplam_view:,} izl, ort {s7_ort_view}/video",
          f"- **<50 izl video sayısı:** {s7_sifir}/{len(son7)} (kalite_temizleyici aday)",
          "",
          "## 🚀 Top 3 (son 7 gün)"]
    for v in s7_top:
        md.append(f"- **{v['views']:,}v** · {v['likes']}👍 · {v['comments']}💬 — {v['title']}")
    md.append("\n## 🪦 Alt 3 (son 7 gün)")
    for v in s7_bot:
        md.append(f"- **{v['views']:,}v** · {v['likes']}👍 · {v['comments']}💬 — {v['title']}")
    md.append("")
    md.append("## Karar verileri")
    md.append(f"- Faz 1 hedef: 500+ abone + günde 1000+ ort view → şu an: **{abone} abone / {s7_ort_view} ort**")
    md.append(f"- Aşıldı mı: {'✅ AŞILDI — Faz 2' if abone >= 500 and s7_ort_view >= 1000 else '❌ Henüz aşılmadı'}")

    rapor = "\n".join(md)
    print(rapor)

    if not args.print_only:
        RAPOR.write_text(rapor, encoding="utf-8")
        gecmis.append({
            "tarih": now.isoformat(timespec="minutes"),
            "abone": abone, "toplam_view": toplam_view, "toplam_video": toplam_video,
            "son7_view": s7_toplam_view, "son7_ort": s7_ort_view,
        })
        GECMIS.write_text(json.dumps(gecmis, ensure_ascii=False, indent=2))
        print(f"\n[hafta_rapor] {RAPOR.name} ve {GECMIS.name} güncellendi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
