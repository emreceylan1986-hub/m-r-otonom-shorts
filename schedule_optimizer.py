"""
schedule_optimizer.py — Optimum Yayın Saati Önerici (Faz 7).

YouTube Analytics'ten son 30 günde HANGİ SAATTE yayınlanan videoların daha
iyi performans gösterdiğini çıkarır. En iyi 3 saati öneri olarak yazar.

Cron'u OTOMATIK değiştirmez (güvenlik) — manuel uygulanır. Çıktı:
    schedule_recommendation.md — şu anki cron + önerilen cron + sebep
"""
import json, sys
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from pathlib import Path

PANEL_KOK = Path(__file__).parent
TOKEN = PANEL_KOK / "token.json"
CIKTI = PANEL_KOK / "schedule_recommendation.md"


def main():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    SCOPES = ["https://www.googleapis.com/auth/youtube"]
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds.expired and creds.refresh_token: creds.refresh(Request())
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    yj_yolu = PANEL_KOK / "yuklemeler.json"
    if not yj_yolu.exists():
        print("yuklemeler.json yok"); return 1
    yj = json.loads(yj_yolu.read_text())

    # Son 30 günün public pipeline videoları
    son30_gun = datetime.now(timezone.utc) - timedelta(days=30)
    aday_ids = [v["video_id"] for v in yj if v.get("video_id")]

    # Stats batch
    videos = []
    for i in range(0, len(aday_ids), 50):
        r = yt.videos().list(part="statistics,snippet,status", id=",".join(aday_ids[i:i+50])).execute()
        for it in r.get("items", []):
            try:
                pub = datetime.fromisoformat(it["snippet"]["publishedAt"].replace("Z","+00:00"))
                if pub < son30_gun: continue
                if it["status"]["privacyStatus"] != "public": continue
                videos.append({
                    "saat_utc": pub.hour,
                    "izl": int(it["statistics"].get("viewCount", 0)),
                    "begeni": int(it["statistics"].get("likeCount", 0)),
                    "title": it["snippet"]["title"][:60],
                })
            except Exception:
                pass

    print(f"Analiz edilen video: {len(videos)} (son 30g)")
    if len(videos) < 5:
        print("Yetersiz veri"); return 1

    # Saat bazlı ortalama
    saat_perf = defaultdict(list)
    for v in videos:
        saat_perf[v["saat_utc"]].append(v["izl"])

    saat_skorlari = []
    for h, izls in saat_perf.items():
        ortalama = sum(izls) / len(izls)
        saat_skorlari.append((h, ortalama, len(izls)))
    saat_skorlari.sort(key=lambda x: -x[1])

    # Top 3 saat
    top3 = saat_skorlari[:3]

    # Mevcut cron
    mevcut_saatler = [12, 16, 19]  # UTC

    rapor = "# 📅 Schedule Optimization Önerisi\n\n"
    rapor += f"Oluşturulma: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    rapor += f"Analiz edilen video: {len(videos)} (son 30g, public)\n\n"

    rapor += "## Şu anki cron (UTC)\n"
    rapor += f"`0 {','.join(map(str, mevcut_saatler))} * * *`\n\n"
    rapor += "TR saatleri: " + ", ".join(f"{(h+3)%24:02d}:00" for h in mevcut_saatler) + "\n\n"

    rapor += "## Saat bazlı performans (UTC, ortalama izlenme/video)\n\n"
    rapor += "| Saat UTC | Saat TR | Ort. İzl | Video sayısı |\n|---|---|---|---|\n"
    for h, ort, sayi in saat_skorlari:
        rapor += f"| {h:02d}:00 | {(h+3)%24:02d}:00 | {ort:.1f} | {sayi} |\n"

    rapor += "\n## 🏆 Önerilen optimum 3 saat\n\n"
    onerilen = sorted([h for h, _, _ in top3])
    rapor += f"`0 {','.join(map(str, onerilen))} * * *`\n\n"
    rapor += "TR saatleri: " + ", ".join(f"{(h+3)%24:02d}:00" for h in onerilen) + "\n\n"

    rapor += "## Karşılaştırma\n\n"
    mevcut_ort = sum(saat_perf.get(h, [0]) for h in mevcut_saatler) and \
                 sum(sum(saat_perf.get(h, [0]))/max(len(saat_perf.get(h, [1])),1) for h in mevcut_saatler)/3
    onerilen_ort = sum(t[1] for t in top3) / 3
    if mevcut_ort > 0:
        delta = ((onerilen_ort - mevcut_ort) / mevcut_ort * 100)
        rapor += f"- Mevcut 3 saatin ortalaması: **{mevcut_ort:.0f} izlenme/video**\n"
        rapor += f"- Önerilen 3 saatin ortalaması: **{onerilen_ort:.0f} izlenme/video**\n"
        rapor += f"- Beklenen iyileşme: **{delta:+.0f}%**\n\n"

    rapor += "## Uygulama\n\n"
    rapor += "`.github/workflows/main.yml` içindeki `cron: \"0 12,16,19 * * *\"`\n"
    rapor += f"satırını `cron: \"0 {','.join(map(str, onerilen))} * * *\"` ile değiştir.\n\n"
    rapor += "⚠️ Bu otomatik değişmez — güvenlik için manuel uygulanır.\n"

    CIKTI.write_text(rapor, encoding="utf-8")
    print(f"\n[schedule] Rapor: {CIKTI}")
    print(f"\nTop 3 önerilen saat (UTC): {[h for h,_,_ in top3]}")
    print(f"Top 3 önerilen saat (TR):  {[(h+3)%24 for h,_,_ in top3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
