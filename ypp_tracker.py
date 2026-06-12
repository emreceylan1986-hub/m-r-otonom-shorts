"""
ypp_tracker.py — YouTube Partner Program Eligibility Tracker (Faz 5).

Her gün:
  - Toplam abone (mevcut)
  - Son 90 gün Shorts izlenme toplamı
  - Iki eşik için yüzde + tahmini gün

YPP 2026 eşikleri:
  EARLY TIER  → 500 abone + 3 video + 3,000,000 Shorts izlenme / 90g
  FULL TIER   → 1000 abone + 10,000,000 Shorts izlenme / 90g
                (veya 4,000 uzun-form watch saati / 12 ay — Shorts kanal için n/a)

Çıktı: ypp_status.json + konsol özet.

Kullanım:
    python ypp_tracker.py
"""
import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PANEL_KOK = Path(__file__).parent
TOKEN_AN = PANEL_KOK / "token_analytics.json"
TOKEN_BASIT = PANEL_KOK / "token.json"
CIKTI = PANEL_KOK / "ypp_status.json"

EARLY_ABONE = 500
EARLY_SHORTS_90G = 3_000_000
FULL_ABONE = 1000
FULL_SHORTS_90G = 10_000_000


def istemciler():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    SCOPES_FULL = [
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
    ]
    SCOPE_BASIT = ["https://www.googleapis.com/auth/youtube"]
    yol = TOKEN_AN if TOKEN_AN.exists() else TOKEN_BASIT
    if not yol.exists(): return None, None

    creds = Credentials.from_authorized_user_file(str(yol), SCOPES_FULL)
    try:
        if creds.expired and creds.refresh_token: creds.refresh(Request())
    except Exception as h:
        print(f"[ypp] Analytics scope yok, youtube-only ile devam: {str(h)[:80]}")
        creds = Credentials.from_authorized_user_file(str(yol), SCOPE_BASIT)
        try:
            if creds.expired and creds.refresh_token: creds.refresh(Request())
        except Exception as h2:
            print(f"[ypp] youtube-only refresh de fail: {str(h2)[:80]}")
            return None, None
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    try:
        yta = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    except Exception:
        yta = None
    return yt, yta


def main() -> int:
    yt, yta = istemciler()
    if yt is None:
        print("[ypp] Token yok"); return 0

    # Kanal bilgisi
    ch = yt.channels().list(part="statistics,snippet,contentDetails", mine=True).execute()
    ci = ch["items"][0]
    abone = int(ci["statistics"].get("subscriberCount", 0))
    toplam_izl = int(ci["statistics"].get("viewCount", 0))
    toplam_vid = int(ci["statistics"].get("videoCount", 0))

    # 90 gün izlenme (Analytics API ile, eğer scope var)
    son90_views = 0
    son14_views = 0
    if yta is not None:
        now = datetime.now(timezone.utc).date()
        for periot, gun in [("90g", 90), ("14g", 14)]:
            try:
                r = yta.reports().query(
                    ids="channel==MINE",
                    startDate=(now - timedelta(days=gun)).isoformat(),
                    endDate=now.isoformat(),
                    metrics="views",
                ).execute()
                if r.get("rows"):
                    v = r["rows"][0][0]
                    if periot == "90g": son90_views = int(v)
                    else: son14_views = int(v)
            except Exception as h:
                print(f"  Analytics {periot}: {h}")

    # Yüzdeler
    def yuzde(now_val, target):
        if target == 0: return 0
        return min(100, round(100 * now_val / target, 2))

    def tahmini_gun(now_val, target, gunluk_buyume):
        if gunluk_buyume <= 0: return float('inf')
        kalan = target - now_val
        if kalan <= 0: return 0
        return round(kalan / gunluk_buyume)

    # Günlük büyüme tahmini (14g ortalama)
    gunluk_view = son14_views / 14 if son14_views else 0

    rapor = {
        "uretim": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kanal": ci["snippet"]["title"],
        "abone": abone,
        "toplam_video": toplam_vid,
        "toplam_izlenme_yaşam_boyu": toplam_izl,
        "son_90g_izlenme": son90_views,
        "son_14g_izlenme": son14_views,
        "gunluk_izlenme_tahmin": round(gunluk_view, 1),

        "early_tier": {
            "abone_hedef": EARLY_ABONE,
            "abone_yuzde": yuzde(abone, EARLY_ABONE),
            "abone_kalan": max(0, EARLY_ABONE - abone),
            "shorts_hedef_90g": EARLY_SHORTS_90G,
            "shorts_yuzde_90g": yuzde(son90_views, EARLY_SHORTS_90G),
            "shorts_kalan_90g": max(0, EARLY_SHORTS_90G - son90_views),
            "tahmini_gun_shorts": tahmini_gun(son90_views, EARLY_SHORTS_90G, gunluk_view),
        },
        "full_tier": {
            "abone_hedef": FULL_ABONE,
            "abone_yuzde": yuzde(abone, FULL_ABONE),
            "abone_kalan": max(0, FULL_ABONE - abone),
            "shorts_hedef_90g": FULL_SHORTS_90G,
            "shorts_yuzde_90g": yuzde(son90_views, FULL_SHORTS_90G),
            "shorts_kalan_90g": max(0, FULL_SHORTS_90G - son90_views),
            "tahmini_gun_shorts": tahmini_gun(son90_views, FULL_SHORTS_90G, gunluk_view),
        },
    }

    CIKTI.write_text(json.dumps(rapor, ensure_ascii=False, indent=2))

    # Konsol
    print(f"\n  📊 KANAL: {ci['snippet']['title']}")
    print(f"     Abone: {abone}  |  Toplam izl: {toplam_izl}")
    print(f"     Son 14g: {son14_views} izl  |  Son 90g: {son90_views} izl  |  Günlük ort: {gunluk_view:.0f}")
    print()
    print(f"  🎯 EARLY TIER ({EARLY_ABONE} abone + {EARLY_SHORTS_90G:,} Shorts/90g):")
    print(f"     Abone: %{rapor['early_tier']['abone_yuzde']:5.1f}  ({rapor['early_tier']['abone_kalan']} kalan)")
    print(f"     Shorts: %{rapor['early_tier']['shorts_yuzde_90g']:5.2f}  ({rapor['early_tier']['shorts_kalan_90g']:,} izl kalan)")
    g = rapor['early_tier']['tahmini_gun_shorts']
    print(f"     Tahmini gün (Shorts): {'∞' if g == float('inf') else g}")
    print()
    print(f"  🏆 FULL TIER ({FULL_ABONE} abone + {FULL_SHORTS_90G:,} Shorts/90g):")
    print(f"     Abone: %{rapor['full_tier']['abone_yuzde']:5.1f}  ({rapor['full_tier']['abone_kalan']} kalan)")
    print(f"     Shorts: %{rapor['full_tier']['shorts_yuzde_90g']:5.2f}  ({rapor['full_tier']['shorts_kalan_90g']:,} izl kalan)")
    g = rapor['full_tier']['tahmini_gun_shorts']
    print(f"     Tahmini gün (Shorts): {'∞' if g == float('inf') else g}")

    print(f"\n[ypp] Yazıldı: {CIKTI}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
