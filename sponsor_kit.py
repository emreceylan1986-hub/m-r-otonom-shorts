"""
sponsor_kit.py — Sponsor Outreach PDF Generator (Faz 5).

Kanal metric'lerini tek-sayfa profesyonel HTML rapor olarak üretir.
Sponsorlara mail eki, marka outreach kit'i olarak kullanılır.

PDF için weasyprint veya basit HTML → tarayıcı print (manuel).

Kullanım:
    python sponsor_kit.py [--cikti sponsor_kit.html]
"""
import argparse, json
from datetime import datetime, timezone, timedelta
from pathlib import Path

PANEL_KOK = Path(__file__).parent


def istemciler():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    SCOPES = [
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
    ]
    yol = PANEL_KOK / ("token_analytics.json" if (PANEL_KOK / "token_analytics.json").exists() else "token.json")
    creds = Credentials.from_authorized_user_file(str(yol), SCOPES)
    try:
        if creds.expired and creds.refresh_token: creds.refresh(Request())
    except Exception as h:
        # yt-analytics scope yoksa refresh fail eder — youtube only ile devam
        print(f"[sponsor_kit] Analytics scope yok, basit kanal verisi: {str(h)[:80]}")
        # Sadece youtube scope ile yeniden yap
        from google.oauth2.credentials import Credentials as C2
        creds = C2.from_authorized_user_file(str(yol), ["https://www.googleapis.com/auth/youtube"])
        if creds.expired and creds.refresh_token: creds.refresh(Request())
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    try:
        yta = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    except Exception:
        yta = None
    return yt, yta


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cikti", default=str(PANEL_KOK / "sponsor_kit.html"))
    args = p.parse_args()

    yt, yta = istemciler()
    ch = yt.channels().list(part="statistics,snippet,brandingSettings,contentDetails", mine=True).execute()
    ci = ch["items"][0]
    stats = ci["statistics"]
    snippet = ci["snippet"]

    abone = int(stats.get("subscriberCount", 0))
    toplam_v = int(stats.get("viewCount", 0))
    toplam_vid = int(stats.get("videoCount", 0))

    # Son 28g analytics
    son28 = {"views": 0, "watch_dk": 0, "abone_gained": 0, "likes": 0, "comments": 0, "shares": 0}
    son90 = {"views": 0}
    traffic = []
    demografi = []
    if yta is not None:
        now = datetime.now(timezone.utc).date()
        try:
            r = yta.reports().query(
                ids="channel==MINE",
                startDate=(now - timedelta(days=28)).isoformat(),
                endDate=now.isoformat(),
                metrics="views,estimatedMinutesWatched,subscribersGained,likes,comments,shares,averageViewDuration",
            ).execute()
            if r.get("rows"):
                row = r["rows"][0]
                son28["views"] = int(row[0]); son28["watch_dk"] = int(row[1])
                son28["abone_gained"] = int(row[2]); son28["likes"] = int(row[3])
                son28["comments"] = int(row[4]); son28["shares"] = int(row[5])
                son28["avg_view_sn"] = int(row[6])
        except Exception as h: print(f"  son28: {h}")

        try:
            r = yta.reports().query(
                ids="channel==MINE",
                startDate=(now - timedelta(days=90)).isoformat(),
                endDate=now.isoformat(),
                metrics="views",
            ).execute()
            if r.get("rows"): son90["views"] = int(r["rows"][0][0])
        except Exception: pass

        # Traffic source
        try:
            r = yta.reports().query(
                ids="channel==MINE",
                startDate=(now - timedelta(days=28)).isoformat(),
                endDate=now.isoformat(),
                metrics="views",
                dimensions="insightTrafficSourceType",
                sort="-views",
            ).execute()
            traffic = r.get("rows", [])[:5]
        except Exception: pass

        # Geo
        try:
            r = yta.reports().query(
                ids="channel==MINE",
                startDate=(now - timedelta(days=28)).isoformat(),
                endDate=now.isoformat(),
                metrics="views",
                dimensions="country",
                sort="-views",
                maxResults=10,
            ).execute()
            demografi = r.get("rows", [])
        except Exception: pass

    eng = (100 * (son28["likes"] + son28["comments"]) / son28["views"]) if son28["views"] else 0

    traffic_html = "".join(f"<tr><td>{r[0]}</td><td>{int(r[1]):,}</td></tr>" for r in traffic)
    demo_html = "".join(f"<tr><td>{r[0]}</td><td>{int(r[1]):,}</td></tr>" for r in demografi)

    cname = snippet["title"]
    handle = snippet.get("customUrl", "")
    pic = snippet["thumbnails"]["high"]["url"]

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{cname} — Media Kit</title>
<style>
@page {{ size: A4; margin: 1.5cm; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif; color: #111; max-width: 800px; margin: 0 auto; padding: 30px; }}
h1 {{ font-size: 36px; margin-bottom: 0; }}
.sub {{ color: #666; margin-bottom: 30px; }}
.bilezik {{ display: flex; gap: 18px; margin: 24px 0; }}
.metrik {{ flex: 1; background: linear-gradient(135deg, #fff5e6, #ffe0cc); border-radius: 14px; padding: 18px; text-align: center; }}
.metrik .deger {{ font-size: 32px; font-weight: 800; color: #cc4400; }}
.metrik .etiket {{ font-size: 12px; color: #555; text-transform: uppercase; letter-spacing: 1px; }}
table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; }}
th {{ background: #f8f9fa; font-size: 12px; text-transform: uppercase; }}
.bolum {{ margin: 28px 0; }}
.bolum h2 {{ border-left: 5px solid #cc4400; padding-left: 12px; }}
.profil {{ display: flex; gap: 20px; align-items: center; margin-bottom: 20px; }}
.profil img {{ width: 80px; height: 80px; border-radius: 50%; }}
</style></head>
<body>
<div class="profil">
  <img src="{pic}" alt="{cname}">
  <div>
    <h1>{cname}</h1>
    <div class="sub">{snippet.get('description','')[:120]}</div>
    {f'<a href="https://youtube.com/{handle}" style="color:#cc4400">{handle}</a>' if handle else ''}
  </div>
</div>

<div class="bilezik">
  <div class="metrik"><div class="deger">{abone:,}</div><div class="etiket">Subscribers</div></div>
  <div class="metrik"><div class="deger">{toplam_v:,}</div><div class="etiket">Lifetime Views</div></div>
  <div class="metrik"><div class="deger">{toplam_vid:,}</div><div class="etiket">Videos</div></div>
  <div class="metrik"><div class="deger">{eng:.1f}%</div><div class="etiket">Engagement</div></div>
</div>

<div class="bolum">
  <h2>📊 28-Day Performance</h2>
  <table>
    <tr><th>Metric</th><th>Value</th></tr>
    <tr><td>Views</td><td>{son28['views']:,}</td></tr>
    <tr><td>Watch time (min)</td><td>{son28['watch_dk']:,}</td></tr>
    <tr><td>Avg view duration (sec)</td><td>{son28.get('avg_view_sn',0)}</td></tr>
    <tr><td>New subscribers</td><td>+{son28['abone_gained']}</td></tr>
    <tr><td>Likes</td><td>{son28['likes']:,}</td></tr>
    <tr><td>Comments</td><td>{son28['comments']:,}</td></tr>
    <tr><td>Shares</td><td>{son28['shares']:,}</td></tr>
  </table>
</div>

<div class="bolum">
  <h2>🚀 90-Day Shorts Views</h2>
  <p style="font-size: 24px; color: #cc4400; font-weight: 700;">{son90['views']:,}</p>
</div>

<div class="bolum">
  <h2>🌍 Top Traffic Sources (28d)</h2>
  <table><tr><th>Source</th><th>Views</th></tr>{traffic_html}</table>
</div>

<div class="bolum">
  <h2>🗺️ Top Countries (28d)</h2>
  <table><tr><th>Country</th><th>Views</th></tr>{demo_html}</table>
</div>

<div class="bolum">
  <h2>💼 Sponsor Opportunity</h2>
  <p>Niche: <b>Animals · Nature · Amazing Facts</b> — global English-speaking audience with high curiosity engagement.
  Format: 30-second YouTube Shorts published <b>2-3 times daily</b>, autonomous AI-powered pipeline.</p>
  <p>Ideal sponsors: nature documentary platforms, wildlife books, hiking/camping gear,
  pet products, science magazines, eco-tourism, educational apps.</p>
  <p><b>Custom integration options:</b> single Shorts mention, dedicated Short, description link,
  community post, or seasonal series partnership.</p>
</div>

<div style="margin-top: 40px; padding-top: 20px; border-top: 2px solid #cc4400; font-size: 11px; color: #888;">
  Generated automatically · {datetime.now().strftime('%Y-%m-%d %H:%M')} · TrendCatcher Media Kit
</div>
</body></html>"""
    Path(args.cikti).write_text(html, encoding="utf-8")
    print(f"[sponsor_kit] Yazıldı: {args.cikti}  ({len(html):,} byte)")
    print(f"  Kanal: {cname} | {abone:,} abone | son 28g {son28['views']:,} izl")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
