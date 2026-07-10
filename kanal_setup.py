#!/usr/bin/env python3
"""
CosmoBytes kanal ilk kurulum scripti — workflow_dispatch ile tetiklenir.

Yaptıkları:
  1. Kanal "About" / description doldur (brandingSettings.channel.description)
  2. Banner upload + set (channelBanners.insert + brandingSettings.image)
  3. 3 ana playlist oluştur ve mevcut video'ları kategorize et
  4. Kanal keywords set (brandingSettings.channel.keywords)

Profil resmi (channel avatar) API ile değiştirilemez — Emre Bey manuel set eder.

Çalıştır: python3 kanal_setup.py
"""
import json
import os
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

import kanal_config

PANEL_KOK = Path(__file__).parent
BANNER = PANEL_KOK / "branding" / "banner.png"

# Aktif kanal config (KANAL env; ayarlı değilse trendcatcher)
_CFG = kanal_config.kanal_config()
TOKEN = kanal_config.token_yolu()
KANAL_ADI = _CFG["kanal_adi"]
KANAL_DESCRIPTION = _CFG["description"]
KANAL_KEYWORDS = _CFG["keywords"]
PLAYLISTS = _CFG["playlists"]

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def log(msg):
    print(f"[kanal_setup] {msg}", flush=True)


def yt_istemci():
    if not TOKEN.exists():
        raise SystemExit("token.json yok")
    creds = Credentials.from_authorized_user_file(str(TOKEN), YOUTUBE_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def kanal_bilgi(yt):
    r = yt.channels().list(part="snippet,brandingSettings,contentDetails", mine=True).execute()
    return r["items"][0]


def description_ve_keywords_set(yt, kanal_id, mevcut_branding):
    """Kanal description + keywords güncelle (brandingSettings)."""
    log("1) Kanal description + keywords güncelleniyor...")

    body = {
        "id": kanal_id,
        "brandingSettings": {
            "channel": {
                "description": KANAL_DESCRIPTION,
                "keywords": KANAL_KEYWORDS,
                "defaultLanguage": "en",
                "country": "TR",
            }
        },
    }
    # Mevcut title varsa koru
    eski = mevcut_branding.get("channel", {})
    if eski.get("title"):
        body["brandingSettings"]["channel"]["title"] = eski["title"]

    try:
        r = yt.channels().update(part="brandingSettings", body=body).execute()
        log(f"   ✓ Description set ({len(KANAL_DESCRIPTION)} char)")
        log(f"   ✓ Keywords set")
        return True
    except HttpError as e:
        log(f"   ❌ Hata: {e}")
        return False


def banner_yukle_set(yt, kanal_id):
    """Banner upload + brandingSettings.image set."""
    log("2) Banner upload + set ...")
    if not BANNER.exists():
        log(f"   ❌ banner.png yok: {BANNER}")
        return False

    try:
        media = MediaFileUpload(str(BANNER), mimetype="image/png", resumable=True)
        r = yt.channelBanners().insert(media_body=media).execute()
        banner_url = r.get("url")
        if not banner_url:
            log(f"   ❌ Upload OK ama url yok: {r}")
            return False
        log(f"   ✓ Banner upload OK")

        body = {
            "id": kanal_id,
            "brandingSettings": {
                "channel": {
                    "description": KANAL_DESCRIPTION,
                    "keywords": KANAL_KEYWORDS,
                    "defaultLanguage": "en",
                    "country": "TR",
                },
                "image": {"bannerExternalUrl": banner_url},
            },
        }
        yt.channels().update(part="brandingSettings", body=body).execute()
        log(f"   ✓ Banner kanal'a set edildi")
        return True
    except HttpError as e:
        log(f"   ❌ Hata: {e}")
        return False


def son_videolari_cek(yt, uploads_pl, limit=50):
    """Son N video başlık + id çek."""
    out = []
    nxt = None
    while len(out) < limit:
        r = yt.playlistItems().list(
            part="snippet,contentDetails", playlistId=uploads_pl,
            maxResults=min(50, limit - len(out)), pageToken=nxt
        ).execute()
        for it in r.get("items", []):
            out.append({
                "video_id": it["contentDetails"]["videoId"],
                "title": it["snippet"]["title"],
            })
        nxt = r.get("nextPageToken")
        if not nxt:
            break
    return out


def playlist_kategorize_et(video, playlistler):
    """Bir video'yu en uygun playlist'e eşle (başlık + tag eşleşmesi)."""
    metin = video["title"].lower()
    best = None
    best_score = 0
    for pl in playlistler:
        score = sum(1 for k in pl["keywords"] if k in metin)
        if score > best_score:
            best_score = score
            best = pl
    return best if best_score > 0 else None


def playlistleri_olustur_ve_doldur(yt):
    """3 playlist oluştur + video'ları uygun olana ekle."""
    log("3) Playlist'ler oluşturuluyor + video'lar kategorize ediliyor...")
    kanal = kanal_bilgi(yt)
    uploads_pl = kanal["contentDetails"]["relatedPlaylists"]["uploads"]
    videolar = son_videolari_cek(yt, uploads_pl, limit=50)
    log(f"   Toplam {len(videolar)} video bulundu")

    olusturulan = []
    for pl_cfg in PLAYLISTS:
        body = {
            "snippet": {
                "title": pl_cfg["title"],
                "description": pl_cfg["description"],
                "defaultLanguage": "en",
            },
            "status": {"privacyStatus": "public"},
        }
        try:
            r = yt.playlists().insert(part="snippet,status", body=body).execute()
            pl_id = r["id"]
            log(f"   ✓ Playlist oluşturuldu: '{pl_cfg['title']}' ({pl_id})")
            pl_cfg["id"] = pl_id
            olusturulan.append(pl_cfg)
        except HttpError as e:
            log(f"   ❌ Playlist '{pl_cfg['title']}' oluşturulamadı: {e}")

    # Video'ları kategorize et
    log("   Video'lar kategorize ediliyor...")
    eklendi = 0
    for video in videolar:
        match = playlist_kategorize_et(video, olusturulan)
        if not match:
            continue
        try:
            yt.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": match["id"],
                        "resourceId": {"kind": "youtube#video", "videoId": video["video_id"]},
                    }
                },
            ).execute()
            eklendi += 1
        except HttpError as e:
            log(f"     ! Video {video['video_id'][:8]} eklenemedi: {str(e)[:80]}")

    log(f"   ✓ {eklendi} video playlist'lere eklendi")
    return True


def mevcut_playlistler_var_mi(yt):
    """Bu script'in 3 ana playlist'i zaten oluşturulmuş mu kontrol et."""
    r = yt.playlists().list(part="snippet", mine=True, maxResults=50).execute()
    mevcut = {pl["snippet"]["title"] for pl in r.get("items", [])}
    benim = {pl["title"] for pl in PLAYLISTS}
    return benim.issubset(mevcut)


def playlist_id_haritasi(yt):
    """Mevcut playlistlerden başlık → id sözlüğü."""
    harita = {}
    sayfa_token = None
    while True:
        r = yt.playlists().list(
            part="snippet", mine=True, maxResults=50, pageToken=sayfa_token
        ).execute()
        for pl in r.get("items", []):
            harita[pl["snippet"]["title"]] = pl["id"]
        sayfa_token = r.get("nextPageToken")
        if not sayfa_token:
            break
    return harita


def mevcut_sectionlar(yt):
    r = yt.channelSections().list(part="snippet,contentDetails", mine=True).execute()
    return r.get("items", [])


def section_var_mi(mevcut, type_, playlist_id=None):
    type_l = type_.lower()
    for sec in mevcut:
        sn = sec.get("snippet", {})
        cd = sec.get("contentDetails", {})
        if sn.get("type", "").lower() != type_l:
            continue
        if type_l == "singleplaylist":
            if playlist_id and playlist_id in cd.get("playlists", []):
                return True
        else:
            return True
    return False


def sectionlari_kur(yt):
    """Kanal ana sayfasına 5 bölüm: Recent → Popular → 3 playlist."""
    log("4) Kanal Sections kuruluyor (ana sayfa düzeni)...")
    mevcut = mevcut_sectionlar(yt)
    log(f"   Mevcut section: {len(mevcut)}")

    plist = playlist_id_haritasi(yt)

    plan = [
        {"type": "recentUploads", "title": None, "playlist_id": None},
        {"type": "popularUploads", "title": None, "playlist_id": None},
    ]
    for pl_cfg in PLAYLISTS:
        pl_id = plist.get(pl_cfg["title"])
        if not pl_id:
            log(f"   ! Playlist bulunamadı, atla: {pl_cfg['title']}")
            continue
        plan.append({"type": "singlePlaylist", "title": pl_cfg["title"], "playlist_id": pl_id})

    eklendi = 0
    for pos, sec_cfg in enumerate(plan):
        if section_var_mi(mevcut, sec_cfg["type"], sec_cfg["playlist_id"]):
            log(f"   = Pozisyon {pos}: '{sec_cfg['type']}' zaten var — atla")
            continue
        body = {
            "snippet": {
                "type": sec_cfg["type"],
                "style": "horizontalRow",
                "position": pos,
                "defaultLanguage": "en",
            }
        }
        if sec_cfg["type"] == "singlePlaylist" and sec_cfg["playlist_id"]:
            body["contentDetails"] = {"playlists": [sec_cfg["playlist_id"]]}
        try:
            r = yt.channelSections().insert(part="snippet,contentDetails", body=body).execute()
            etiket = sec_cfg["title"] or sec_cfg["type"]
            log(f"   ✓ Pozisyon {pos}: '{etiket}' eklendi ({r['id']})")
            eklendi += 1
        except HttpError as e:
            log(f"   ❌ Pozisyon {pos} ({sec_cfg['type']}) eklenemedi: {str(e)[:140]}")

    log(f"   ✓ {eklendi} yeni section eklendi")
    return True


def main():
    log(f"=== {KANAL_ADI} kanal kurulumu başladı ===")
    yt = yt_istemci()
    kanal = kanal_bilgi(yt)
    kanal_id = kanal["id"]
    log(f"Kanal: {kanal['snippet']['title']} ({kanal_id})")
    log(f"Mevcut abone: {kanal.get('statistics', {}).get('subscriberCount', '?')}")

    mevcut_branding = kanal.get("brandingSettings", {})

    sonuc = []
    sonuc.append(("Description + Keywords", description_ve_keywords_set(yt, kanal_id, mevcut_branding)))
    sonuc.append(("Banner upload + set", banner_yukle_set(yt, kanal_id)))

    # Playlist'ler önceden oluşturulmuşsa tekrar oluşturma
    if mevcut_playlistler_var_mi(yt):
        log("3) Playlist'ler ZATEN VAR — atlanıyor (duplikasyon önleme)")
        sonuc.append(("Playlist (zaten var)", True))
    else:
        sonuc.append(("Playlist oluştur + doldur", playlistleri_olustur_ve_doldur(yt)))

    sonuc.append(("Sections (ana sayfa düzeni)", sectionlari_kur(yt)))

    log("")
    log("=== ÖZET ===")
    for ad, ok in sonuc:
        log(f"  {'✓' if ok else '❌'} {ad}")

    log("")
    log("⚠️  YAPILMAYAN (Emre Bey elle):")
    log("  • Profil resmi (avatar) — YouTube API channel avatar değiştirmez")
    log("    YouTube Studio → Customization → Branding → Picture")
    log("  • Telefon doğrulaması — YouTube Studio → Settings → Channel → Feature Eligibility")


if __name__ == "__main__":
    main()
