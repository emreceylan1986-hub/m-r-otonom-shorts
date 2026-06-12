"""
token_upgrade.py — YouTube OAuth Token Scope Upgrade.

Mevcut token.json'a 2 yeni scope ekler:
  - yt-analytics.readonly  (retention, CTR, traffic source)
  - youtube.force-ssl      (caption/altyazı upload + community)

Tarayıcı açılır, sen Google hesabına izin verirsin, yeni token.json
ÜSTÜNE yazılır.

Kullanım:
    python3 token_upgrade.py
"""
import json, sys, webbrowser
from pathlib import Path

PANEL_KOK = Path(__file__).parent
CLIENT_SECRET = PANEL_KOK / "client_secret.json"
TOKEN_DOSYASI = PANEL_KOK / "token.json"
TOKEN_YEDEK = PANEL_KOK / "token.json.eski"

SCOPES = [
    "https://www.googleapis.com/auth/youtube",                  # mevcut: upload+delete
    "https://www.googleapis.com/auth/yt-analytics.readonly",    # YENİ: retention, CTR
    "https://www.googleapis.com/auth/youtube.force-ssl",        # YENİ: caption upload
]


def main() -> int:
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CLIENT_SECRET.exists():
        print(f"❌ {CLIENT_SECRET} yok"); return 1

    # 1) Mevcut token yedekle
    if TOKEN_DOSYASI.exists():
        TOKEN_YEDEK.write_bytes(TOKEN_DOSYASI.read_bytes())
        print(f"✓ Yedek: {TOKEN_YEDEK.name}")

    # 2) OAuth flow başlat — tarayıcı açılır
    print(f"\n🌐 Tarayıcı açılıyor... Google'a giriş yap + 'İzin ver' tıkla.")
    print(f"   İstenecek izinler: 3 scope")
    for s in SCOPES:
        print(f"     - {s.split('/')[-1]}")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(
        port=0,
        prompt="consent",          # Force re-consent (yeni scope için zorunlu)
        access_type="offline",     # Refresh token al
        open_browser=True,
    )

    # 3) Yeni token kaydet
    TOKEN_DOSYASI.write_text(creds.to_json(), encoding="utf-8")
    print(f"\n✅ Yeni token kaydedildi: {TOKEN_DOSYASI.name}")
    print(f"\n📋 Token scope kontrolü:")
    for s in creds.scopes or []:
        print(f"     ✓ {s}")

    # 4) Refresh token sağlamlık testi
    print(f"\n🔄 Refresh token testi...")
    try:
        from google.auth.transport.requests import Request
        if creds.refresh_token:
            print(f"  ✓ Refresh token mevcut (uzun ömürlü)")
        else:
            print(f"  ⚠️  Refresh token yok — sadece 1 saat geçerli olabilir")
    except Exception as h:
        print(f"  ✗ {h}")

    # 5) Analytics canlı test
    print(f"\n📊 Analytics canlı test...")
    try:
        from googleapiclient.discovery import build
        yta = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
        from datetime import date, timedelta
        son = date.today(); ilk = son - timedelta(days=14)
        r = yta.reports().query(
            ids="channel==MINE",
            startDate=ilk.isoformat(),
            endDate=son.isoformat(),
            metrics="views,estimatedMinutesWatched,subscribersGained",
        ).execute()
        if r.get("rows"):
            row = r["rows"][0]
            print(f"  ✓ Son 14g: {row[0]} izlenme, {row[1]} dk watch, +{row[2]} abone")
        else:
            print(f"  ⚠️  Veri gelmedi ama API çağrısı OK")
    except Exception as h:
        print(f"  ✗ {h}")

    # 6) GitHub Secrets için yeni içeriği göster
    print(f"\n📦 GitHub Secrets güncelleme:")
    print(f"   Aşağıdaki komut ile TOKEN_JSON secret'ını güncellenir:")
    print(f"   ───────────────────────────────────────────────────────")
    print(f"   gh secret set TOKEN_JSON < token.json -R emreceylan1986-hub/m-r-otonom-shorts")
    print(f"   ───────────────────────────────────────────────────────")
    print(f"\n   Veya Claude bunu otomatik yapacak — script'i çalıştırdıktan sonra")
    print(f"   sadece 'tamam' demen yeter.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
