"""
dashboard.py — Lokal HTML KPI Dashboard.

yuklemeler.json + viral_patterns.json + analytics.json'ı birleştirip
plotly tabanlı tek sayfa interaktif dashboard üretir.

Kullanım:
    python dashboard.py                # dashboard.html üretir
    python dashboard.py --ac            # üretip tarayıcıda açar
"""
import argparse, json, os, sys, webbrowser
from datetime import datetime, timedelta
from pathlib import Path

PANEL_KOK = Path(__file__).parent


def html_uret() -> str:
    yj_p = PANEL_KOK / "yuklemeler.json"
    if not yj_p.exists():
        return "<h1>yuklemeler.json yok</h1>"
    yj = json.loads(yj_p.read_text())

    # Stats — YouTube API'den (real-time)
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_file(str(PANEL_KOK / "token.json"),
        ["https://www.googleapis.com/auth/youtube"])
    if creds.expired and creds.refresh_token: creds.refresh(Request())
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    ch = yt.channels().list(part="statistics,snippet", mine=True).execute()
    cs = ch["items"][0]["statistics"]
    cname = ch["items"][0]["snippet"]["title"]

    ids = [v["video_id"] for v in yj if v.get("video_id")]
    videos = []
    for i in range(0, len(ids), 50):
        r = yt.videos().list(part="statistics,snippet,status", id=",".join(ids[i:i+50])).execute()
        for it in r.get("items", []):
            videos.append({
                "id": it["id"],
                "title": it["snippet"]["title"],
                "published": it["snippet"]["publishedAt"][:10],
                "views": int(it["statistics"].get("viewCount", 0)),
                "likes": int(it["statistics"].get("likeCount", 0)),
                "comments": int(it["statistics"].get("commentCount", 0)),
                "privacy": it["status"]["privacyStatus"],
            })

    public = [v for v in videos if v["privacy"] == "public"]
    public.sort(key=lambda v: v["published"], reverse=True)

    # Son 30 gün gün-gün toplama
    from collections import defaultdict
    by_day = defaultdict(lambda: {"yayın": 0, "izlenme": 0})
    for v in public:
        by_day[v["published"]]["yayın"] += 1
        by_day[v["published"]]["izlenme"] += v["views"]
    days_sorted = sorted(by_day.keys())

    # Pattern raporu (varsa)
    vp_p = PANEL_KOK / "viral_patterns.json"
    vp = json.loads(vp_p.read_text()) if vp_p.exists() else None

    # Analytics raporu (varsa)
    an_p = PANEL_KOK / "analytics.json"
    an = json.loads(an_p.read_text()) if an_p.exists() else None

    total_v = sum(v["views"] for v in public)
    total_l = sum(v["likes"] for v in public)
    total_c = sum(v["comments"] for v in public)

    eng = (100 * total_l / total_v) if total_v else 0

    # Plotly HTML — günlük yayın + izlenme dual-axis
    daily_labels = ",".join(f'"{d}"' for d in days_sorted)
    daily_yayin = ",".join(str(by_day[d]["yayın"]) for d in days_sorted)
    daily_izlenme = ",".join(str(by_day[d]["izlenme"]) for d in days_sorted)

    # Top 10 video bar chart
    top10 = sorted(public, key=lambda v: -v["views"])[:10]
    top10_labels = ",".join(f'"{v["title"][:35]}…"' for v in top10)
    top10_views = ",".join(str(v["views"]) for v in top10)

    # İzlenme dağılımı
    buckets = [(0,1,'0'),(1,10,'1-9'),(10,100,'10-99'),(100,500,'100-499'),(500,1000,'500-999'),(1000,9999,'1000+')]
    bucket_labels = ",".join(f'"{lbl}"' for _,_,lbl in buckets)
    bucket_counts = ",".join(str(sum(1 for v in public if lo<=v["views"]<hi)) for lo,hi,_ in buckets)

    # Son 20 video tablo
    son20_rows = "".join(
        f'<tr><td>{v["published"]}</td><td>{v["views"]}</td><td>{v["likes"]}</td><td>{v["comments"]}</td><td><a target=_blank href="https://youtu.be/{v["id"]}">{v["title"][:60]}</a></td></tr>'
        for v in public[:20]
    )

    # Pattern
    pattern_html = ""
    if vp:
        viral_basliklar = "".join(f"<li>{t}</li>" for t in vp.get("viral",{}).get("ornek_basliklar",[])[:5])
        viral_kelimeler = "".join(f"<span class='tag'>{w} ({vc})</span>" for w,vc,_ in vp.get("viral_ozel_kelimeler",[])[:12])
        pattern_html = f"""
        <div class='kart'>
            <h2>🏆 Viral Pattern</h2>
            <p><b>Top 5 viral başlık:</b></p>
            <ul>{viral_basliklar}</ul>
            <p><b>Viral'e özel kelimeler:</b></p>
            <div class='tags'>{viral_kelimeler}</div>
        </div>"""

    # Analytics
    analytics_html = ""
    if an and "gun_gun" in an and "rows" in an["gun_gun"]:
        rows = an["gun_gun"]["rows"]
        tot_v = sum(r[1] for r in rows)
        tot_w = sum(r[2] for r in rows) if len(rows[0]) > 2 else 0
        net_sub = sum(r[3] - r[4] for r in rows) if len(rows[0]) > 4 else 0
        analytics_html = f"""
        <div class='kart'>
            <h2>📊 Analytics ({an.get('gun_kapsam', '?')}g)</h2>
            <p>Toplam izlenme: <b>{tot_v}</b> | Watch time: <b>{tot_w} dk</b> | Net abone: <b>{net_sub:+d}</b></p>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<title>TrendCatcher Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.30.0.min.js"></script>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif; max-width: 1200px; margin: 20px auto; padding: 0 20px; color: #1a1a1a; }}
h1 {{ font-size: 32px; }}
.metrik {{ display: flex; gap: 14px; flex-wrap: wrap; margin: 20px 0; }}
.kutu {{ flex: 1; min-width: 150px; padding: 16px; background: #f6f8fa; border-radius: 12px; }}
.kutu .deger {{ font-size: 28px; font-weight: 700; }}
.kutu .etiket {{ color: #57606a; font-size: 13px; margin-top: 4px; }}
.kart {{ background: #fff; border: 1px solid #e1e4e8; border-radius: 12px; padding: 20px; margin: 18px 0; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid #eee; font-size: 14px; }}
th {{ background: #f6f8fa; }}
.tag {{ display: inline-block; background: #ddf4ff; color: #0969da; padding: 4px 10px; border-radius: 20px; margin: 3px; font-size: 13px; }}
.tags {{ margin: 8px 0; }}
.uretim {{ color: #57606a; font-size: 13px; margin-bottom: 10px; }}
</style>
</head>
<body>
<h1>🎯 TrendCatcher Dashboard</h1>
<div class="uretim">Üretildi: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Kanal: <b>{cname}</b></div>

<div class="metrik">
    <div class="kutu"><div class="deger">{cs.get('subscriberCount','?')}</div><div class="etiket">Toplam Abone</div></div>
    <div class="kutu"><div class="deger">{cs.get('viewCount','?')}</div><div class="etiket">Toplam İzlenme</div></div>
    <div class="kutu"><div class="deger">{cs.get('videoCount','?')}</div><div class="etiket">Kanal Video</div></div>
    <div class="kutu"><div class="deger">{len(public)}</div><div class="etiket">Pipeline Public</div></div>
    <div class="kutu"><div class="deger">{total_v}</div><div class="etiket">Pipeline İzlenme</div></div>
    <div class="kutu"><div class="deger">{eng:.2f}%</div><div class="etiket">Engagement</div></div>
</div>

{analytics_html}

<div class="kart">
    <h2>📈 Gün Gün Yayın + İzlenme</h2>
    <div id="g1" style="height: 380px;"></div>
</div>

<div class="kart">
    <h2>🏆 Top 10 Video (izlenme)</h2>
    <div id="g2" style="height: 420px;"></div>
</div>

<div class="kart">
    <h2>📊 İzlenme Dağılımı</h2>
    <div id="g3" style="height: 300px;"></div>
</div>

{pattern_html}

<div class="kart">
    <h2>📅 Son 20 Yayın</h2>
    <table>
        <tr><th>Tarih</th><th>👁</th><th>👍</th><th>💬</th><th>Başlık</th></tr>
        {son20_rows}
    </table>
</div>

<script>
Plotly.newPlot('g1', [
    {{ x: [{daily_labels}], y: [{daily_yayin}], type: 'bar', name: 'Yayın sayısı', yaxis: 'y2', marker: {{ color: '#0969da' }} }},
    {{ x: [{daily_labels}], y: [{daily_izlenme}], type: 'scatter', mode: 'lines+markers', name: 'İzlenme', line: {{ color: '#cf222e', width: 3 }} }},
], {{ yaxis: {{ title: 'İzlenme' }}, yaxis2: {{ title: 'Yayın', overlaying: 'y', side: 'right' }}, hovermode: 'x unified' }});

Plotly.newPlot('g2', [
    {{ x: [{top10_views}], y: [{top10_labels}], type: 'bar', orientation: 'h', marker: {{ color: '#1f883d' }} }},
], {{ margin: {{ l: 280 }}, yaxis: {{ autorange: 'reversed' }} }});

Plotly.newPlot('g3', [
    {{ x: [{bucket_labels}], y: [{bucket_counts}], type: 'bar', marker: {{ color: '#8250df' }} }},
], {{ xaxis: {{ title: 'İzlenme aralığı' }}, yaxis: {{ title: 'Video sayısı' }} }});
</script>
</body>
</html>"""
    return html


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ac", action="store_true", help="Üretip tarayıcıda aç")
    p.add_argument("--cikti", default=str(PANEL_KOK / "dashboard.html"))
    args = p.parse_args()

    html = html_uret()
    Path(args.cikti).write_text(html, encoding="utf-8")
    print(f"[dashboard] Yazıldı: {args.cikti} ({len(html):,} byte)")
    if args.ac:
        webbrowser.open(f"file://{Path(args.cikti).resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
