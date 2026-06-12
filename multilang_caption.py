"""
multilang_caption.py — Çoklu dil altyazı üretici.

Mevcut İngilizce ASS altyazısını veya senaryo metnini deep-translator ile
TR/ES/PT/DE/FR'ye çevirip YouTube Data API üzerinden video'ya caption olarak
yükler. Kapsama 4-5× büyür.

Kullanım:
    python multilang_caption.py <video_id> <en_script.txt> --diller tr,es,pt
"""
import argparse, json, sys, tempfile
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

PANEL_KOK = Path(__file__).parent
TOKEN = PANEL_KOK / "token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube"]

# Kapsama × hedef diller
DESTEK_DILLER = {
    "tr": "Türkçe",
    "es": "Español",
    "pt": "Português",
    "de": "Deutsch",
    "fr": "Français",
    "id": "Bahasa Indonesia",
    "hi": "हिन्दी",
}


def yt_istemci():
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds.expired and creds.refresh_token: creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def metin_cevir(metin: str, hedef: str) -> str:
    try:
        from deep_translator import GoogleTranslator
    except ImportError:
        print("[multilang] deep-translator yok"); return ""
    try:
        # 5000 char limit — chunk'a böl
        out = []
        for i in range(0, len(metin), 4500):
            chunk = metin[i:i+4500]
            out.append(GoogleTranslator(source="en", target=hedef).translate(chunk))
        return "\n".join(out)
    except Exception as h:
        print(f"[multilang] çeviri ({hedef}): {h}"); return ""


def srt_uret(metin: str, sure_sn: float = 30) -> str:
    """Tek bir SRT cue üret — basit zaman sınırı, video boyunca."""
    saat = int(sure_sn // 3600)
    dk = int((sure_sn % 3600) // 60)
    sn = int(sure_sn % 60)
    end_ts = f"{saat:02d}:{dk:02d}:{sn:02d},000"
    return f"1\n00:00:00,000 --> {end_ts}\n{metin}\n"


def caption_yukle(yt, video_id: str, dil_kodu: str, dil_adi: str, srt_yolu: Path) -> bool:
    try:
        body = {"snippet": {"videoId": video_id, "language": dil_kodu, "name": dil_adi, "isDraft": False}}
        media = MediaFileUpload(str(srt_yolu), mimetype="application/octet-stream")
        r = yt.captions().insert(part="snippet", body=body, media_body=media).execute()
        print(f"  ✓ {dil_kodu} caption yüklendi: id={r['id']}")
        return True
    except Exception as h:
        print(f"  ✗ {dil_kodu} fail: {h}"); return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("video_id")
    p.add_argument("en_script_dosyasi")
    p.add_argument("--diller", default="tr,es,pt,de,fr",
                   help="Virgülle ayrılmış ISO kodlar")
    args = p.parse_args()

    metin = Path(args.en_script_dosyasi).read_text(encoding="utf-8").strip()
    if not metin:
        print("Senaryo boş"); return 1

    yt = yt_istemci()
    diller = [d.strip() for d in args.diller.split(",") if d.strip() in DESTEK_DILLER]

    basarili = 0
    for kod in diller:
        ceviri = metin_cevir(metin, kod)
        if not ceviri: continue
        srt = srt_uret(ceviri)
        tmp = Path(tempfile.mktemp(suffix=".srt"))
        tmp.write_text(srt, encoding="utf-8")
        if caption_yukle(yt, args.video_id, kod, DESTEK_DILLER[kod], tmp):
            basarili += 1
        tmp.unlink(missing_ok=True)

    print(f"\n[multilang] {basarili}/{len(diller)} dil yüklendi")
    return 0 if basarili else 1


if __name__ == "__main__":
    sys.exit(main())
