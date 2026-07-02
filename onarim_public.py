#!/usr/bin/env python3
"""Bakım: private videoları public yap + Q/A-önekli bozuk başlıkları onar.
GitHub Actions'ta çalışır (Mac'te googleapis DNS engelli). Idempotent.
NOT: Denetim-RED videosu olan kanallarda (Akasha) KULLANMA — orada private bilinçli."""
import json, re
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

QA_ONEK = re.compile(r"^\s*(?:[QA]|Soru|Cevap|Question|Answer)\s*[:\-–.]\s*", re.I)


def yt_client():
    info = json.loads(Path("token.json").read_text())
    cs_raw = json.loads(Path("client_secret.json").read_text())
    cs = cs_raw.get("installed") or cs_raw.get("web") or {}
    creds = Credentials(
        token=info.get("token"),
        refresh_token=info.get("refresh_token"),
        token_uri=info.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=info.get("client_id") or cs.get("client_id"),
        client_secret=info.get("client_secret") or cs.get("client_secret"),
        scopes=info.get("scopes"),
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def video_idler():
    d = json.loads(Path("yuklemeler.json").read_text())
    items = d if isinstance(d, list) else d.get("yuklemeler", [])
    out = []
    for k in items:
        vid = k.get("video_id") or k.get("id") or ""
        if not vid and k.get("watch_url"):
            m = re.search(r"(?:youtu\.be/|v=)([\w-]{11})", k["watch_url"])
            vid = m.group(1) if m else ""
        if vid:
            out.append(vid)
    return out


def main():
    yt = yt_client()
    vids = video_idler()
    print(f"{len(vids)} video kayıtlı — tarama başlıyor")
    acilan = onarilan = 0
    for i in range(0, len(vids), 50):
        grup = vids[i:i + 50]
        resp = yt.videos().list(part="status,snippet", id=",".join(grup)).execute()
        for item in resp.get("items", []):
            vid = item["id"]
            # 1) private → public
            if item["status"]["privacyStatus"] == "private":
                yt.videos().update(part="status", body={
                    "id": vid,
                    "status": {"privacyStatus": "public",
                               "selfDeclaredMadeForKids": item["status"].get("selfDeclaredMadeForKids", False)},
                }).execute()
                print(f"  🔓 public: {vid}  {item['snippet']['title'][:55]}")
                acilan += 1
            # 2) Q/A-önekli başlık onarımı
            t = item["snippet"]["title"]
            yeni = QA_ONEK.sub("", t).strip()
            if yeni and yeni != t:
                sn = item["snippet"]
                sn["title"] = yeni[:100]
                yt.videos().update(part="snippet", body={"id": vid, "snippet": sn}).execute()
                print(f"  ✏️ başlık: {vid}  {t[:40]!r} → {yeni[:40]!r}")
                onarilan += 1
    print(f"BİTTİ: {acilan} public yapıldı, {onarilan} başlık onarıldı.")


if __name__ == "__main__":
    main()
