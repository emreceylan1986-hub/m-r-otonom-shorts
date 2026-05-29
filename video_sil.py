"""
video_sil.py — YouTube video toplu silici.
İlk çalıştırmada `youtube` scope ile OAuth flow yapar (mevcut upload-only
token'ı genişletir). Sonraki silmeler otomatik.
"""

import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

PANEL_KOK = Path(__file__).parent
CLIENT_SECRET = PANEL_KOK / "client_secret.json"
TOKEN_DOSYASI = PANEL_KOK / "token.json"
# youtube scope = upload + read + delete + update (geniş; mevcut upload-only
# token'ı bunla genişletip overwrite ediyoruz)
SCOPES = ["https://www.googleapis.com/auth/youtube"]


def youtube_istemcisi():
    creds = None
    if TOKEN_DOSYASI.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_DOSYASI), SCOPES)
        except Exception:
            creds = None
    if not creds or not creds.valid or set(SCOPES) - set(creds.scopes or []):
        if creds and creds.expired and creds.refresh_token and not (set(SCOPES) - set(creds.scopes or [])):
            print("[sil] Token süresi dolmuş, refresh...")
            creds.refresh(Request())
        else:
            print("[sil] OAuth flow başlıyor — tarayıcı açılacak, 'Authorize' tıkla.")
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0, prompt="consent", open_browser=True)
        TOKEN_DOSYASI.write_text(creds.to_json(), encoding="utf-8")
        print(f"[sil] Token kaydedildi (scope: {' '.join(creds.scopes or [])}).")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def videoyu_sil(youtube, vid: str) -> bool:
    try:
        youtube.videos().delete(id=vid).execute()
        return True
    except HttpError as h:
        print(f"  ✗ {vid} → HATA {h.resp.status}: {str(h)[:120]}")
        return False


def main() -> int:
    if len(sys.argv) < 2:
        print("kullanım: python video_sil.py <ID> [ID] ...")
        return 2
    youtube = youtube_istemcisi()
    basari, hata = 0, 0
    for vid in sys.argv[1:]:
        if videoyu_sil(youtube, vid):
            print(f"  ✓ {vid} silindi")
            basari += 1
        else:
            hata += 1
    print(f"\n[sil] Toplam: {basari} silindi, {hata} hata")
    return 0 if hata == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
