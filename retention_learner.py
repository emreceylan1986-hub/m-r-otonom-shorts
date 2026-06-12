"""
retention_learner.py — Retention Drop-off Öğrenici (Faz 4).

YouTube Analytics API'den top 10 viralin retention curve'ünü çek:
    dimensions=elapsedVideoTimeRatio
    metrics=audienceWatchRatio,relativeRetentionPerformance

100 data point (0.01..1.0) verir → en büyük drop-off noktası bul → bu saniyeye
seslendirici.py prompt'una feedback yaz.

Çıktı: retention_feedback.json — seslendirici prompt'una otomatik yedirilir.

Kullanım:
    python retention_learner.py
"""
import json, sys
from datetime import datetime, timezone
from pathlib import Path

PANEL_KOK = Path(__file__).parent
TOKEN_AN = PANEL_KOK / "token_analytics.json"
TOKEN_BASIT = PANEL_KOK / "token.json"
CIKTI = PANEL_KOK / "retention_feedback.json"

# Shorts süresi tahmini (saniye) — 30s baz, ratio*30 ≈ saniye
SHORT_DURATION_SN = 30


def istemciler():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    SCOPES = [
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
    ]
    yol = TOKEN_AN if TOKEN_AN.exists() else TOKEN_BASIT
    if not yol.exists():
        return None, None
    creds = Credentials.from_authorized_user_file(str(yol), SCOPES)
    try:
        if creds.expired and creds.refresh_token: creds.refresh(Request())
    except Exception as h:
        print(f"[retention] refresh fail: {h}"); return None, None
    try:
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        yta = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
        return yt, yta
    except Exception:
        return None, None


def kanal_id(yt) -> str:
    return yt.channels().list(part="id", mine=True).execute()["items"][0]["id"]


def video_retention(yta, ch_id: str, video_id: str) -> list[tuple[float, float]]:
    """Bir video için (ratio, audienceWatchRatio) listesi döner."""
    try:
        r = yta.reports().query(
            ids=f"channel=={ch_id}",
            startDate="2026-01-01",
            endDate=datetime.now(timezone.utc).date().isoformat(),
            metrics="audienceWatchRatio,relativeRetentionPerformance",
            dimensions="elapsedVideoTimeRatio",
            filters=f"video=={video_id};audienceType==ORGANIC",
        ).execute()
        return [(row[0], row[1]) for row in r.get("rows", [])]
    except Exception as h:
        print(f"  retention {video_id[:8]}: {h}"); return []


def drop_noktalari(curve: list[tuple[float, float]]) -> list[dict]:
    """En büyük 3 drop noktasını bul (consecutive watchratio diff)."""
    if len(curve) < 2: return []
    drops = []
    for i in range(1, len(curve)):
        delta = curve[i-1][1] - curve[i][1]
        drops.append({"ratio_baslangic": round(curve[i-1][0], 2),
                      "ratio_son": round(curve[i][0], 2),
                      "watch_baslangic": round(curve[i-1][1], 3),
                      "watch_son": round(curve[i][1], 3),
                      "drop": round(delta, 3),
                      "saniye_yaklasik": round(curve[i][0] * SHORT_DURATION_SN, 1)})
    drops.sort(key=lambda d: -d["drop"])
    return drops[:3]


def main() -> int:
    yt, yta = istemciler()
    if yt is None or yta is None:
        print("[retention] Analytics token yok — atlanır"); return 0

    yj = json.loads((PANEL_KOK / "yuklemeler.json").read_text())
    # Sadece public + en yeni 20 → quota'yı koru
    yj.sort(key=lambda v: v.get("zaman", ""), reverse=True)
    aday_ids = [v["video_id"] for v in yj if v.get("gizlilik", "public") == "public"][:20]

    ch_id = kanal_id(yt)
    print(f"[retention] {len(aday_ids)} video taranıyor...")

    rapor = {
        "uretim": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "video_analizi": {},
        "ortalama_drop_noktalari": {},
    }

    tum_drop_saniyeler = []
    for vid in aday_ids:
        curve = video_retention(yta, ch_id, vid)
        if not curve: continue
        drops = drop_noktalari(curve)
        rapor["video_analizi"][vid] = {
            "veri_nokta": len(curve),
            "ilk_5sn_watch": round(curve[min(4, len(curve)-1)][1], 3) if curve else 0,
            "son_5sn_watch": round(curve[max(0, len(curve)-5)][1], 3) if curve else 0,
            "top_3_drop": drops,
        }
        for d in drops:
            tum_drop_saniyeler.append(d["saniye_yaklasik"])

    # Pattern: en sık drop saniyesi
    if tum_drop_saniyeler:
        from collections import Counter
        # 2'şer saniye aralıklara bucketle
        bucket = Counter(int(s // 2) * 2 for s in tum_drop_saniyeler)
        rapor["ortalama_drop_noktalari"] = {
            "en_sik_kayb_saniyeleri": bucket.most_common(5),
            "toplam_video": len(rapor["video_analizi"]),
        }
        print(f"\n  En sık drop noktası (sn): {bucket.most_common(3)}")

    # Seslendirici prompt'una geri feedback metni
    feedback_metin = (
        "REGISTERED RETENTION DROP-OFF FEEDBACK (own channel data):\n"
        f"Top drop seconds: {sorted(bucket.most_common(5), key=lambda x: -x[1]) if tum_drop_saniyeler else 'no data yet'}\n"
        "→ Place a strong curiosity boost (number, comparison, surprise) AT and JUST BEFORE these seconds.\n"
    )
    rapor["seslendirici_feedback"] = feedback_metin

    CIKTI.write_text(json.dumps(rapor, ensure_ascii=False, indent=2))
    print(f"\n[retention] Yazıldı: {CIKTI}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
