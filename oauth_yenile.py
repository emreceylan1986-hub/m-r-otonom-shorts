#!/usr/bin/env python3.13
"""TrendCatcher OAuth yenileme (11 Tem — revoke sonrası) — kendi loopback sunucusuyla, state-baypas.
TrendCatcher token yenile (production client). Giriş: @TrendCatcher sahibi Google hesabı. Sadece 'code' içeren isteği
yakalar (favicon/preconnect gürültüsü state hatası yapmasın)."""
import http.server, urllib.parse, json
from google_auth_oauthlib.flow import Flow

SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

flow = Flow.from_client_secrets_file(
    "client_secret.json", scopes=SCOPES,
    redirect_uri="http://localhost:8791/",
)
auth_url, _state = flow.authorization_url(
    prompt="consent", access_type="offline", include_granted_scopes="false",
)
print("AUTH_URL>>>", auth_url, flush=True)

captured = {}

class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in params and "code" not in captured:
            captured["code"] = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h2>Onay alindi — bu sekmeyi kapatabilirsin.</h2>".encode("utf-8"))
        else:
            self.send_response(204); self.end_headers()
    def log_message(self, *a):
        pass

srv = http.server.HTTPServer(("127.0.0.1", 8791), H)
print("SUNUCU_HAZIR: localhost:8791 dinleniyor", flush=True)
while "code" not in captured:
    srv.handle_request()

flow.fetch_token(code=captured["code"])
creds = flow.credentials
with open("token.json", "w") as f:
    f.write(creds.to_json())
print("OK_TOKEN_YAZILDI refresh_var=%s client=%s" % (
    bool(creds.refresh_token), (creds.client_id or "")[:20]), flush=True)
