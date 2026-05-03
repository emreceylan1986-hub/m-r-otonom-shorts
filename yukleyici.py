import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

import bridge


PANEL_KOK = Path(__file__).parent
SHORTS_KLASORU = PANEL_KOK / "shorts_ciktilari"
SES_KLASORU = PANEL_KOK / "ses_ciktilari"
CLIENT_SECRET = PANEL_KOK / "client_secret.json"
TOKEN_DOSYASI = PANEL_KOK / "token.json"
YUKLEME_LOGU = PANEL_KOK / "yuklemeler.json"
DENETIM_UYARI_FLAG = PANEL_KOK / ".denetim_uyari"   # workflow şüpheli içerik issue tetikleyici
BASARI_BILDIRIM_FLAG = PANEL_KOK / ".basarili_yayin" # workflow başarılı yayın issue tetikleyici

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_KATEGORI_NEWS = "25"        # News & Politics
YOUTUBE_KATEGORI_TECH = "28"        # Science & Technology

METADATA_SISTEM_PROMPTU = """You produce YouTube Shorts metadata as STRICT JSON.

This metadata MUST be SEO-optimized for YouTube search.

Schema:
{
  "title": "60-95 characters. FRONT-LOAD the main keyword in the first 50 chars (critical for search). No emojis, no ALL CAPS, no clickbait words like 'shocking' or 'you won't believe'.",
  "description": "200-400 characters TOTAL. Structure:
    - Line 1: Punchy SEO hook (first 100 chars MUST contain the main keyword — this is what Google indexes)
    - Lines 2-3: 1-2 short sentences explaining the news factually
    - Last line: 4-6 hashtags including #Shorts plus 3-5 topical tags (e.g. #Shorts #AI #TechNews #Anthropic)
    NO external links. NO 'subscribe' / 'like' / 'follow' calls.",
  "tags": ["8-12 lowercase tags, no '#' prefix, no spaces in single tags. Mix:
            - 3 broad (e.g. 'tech news', 'ai', 'technology')
            - 5 specific (e.g. 'claude code', 'openclaw', 'ai bias')
            - 2 trending (e.g. 'ai 2026', 'youtube shorts')"]
}

Rules:
- Title is a FACTUAL hook, not a question, not fake controversy
- Description summarizes the script faithfully (no invented claims, no hype)
- Hashtags in description help YouTube clustering — 4-6 max, last line only
- Tags drive search match — be specific to the actual story
- Output ONLY the JSON object, no prose
"""


def _adim(n, m: str) -> None:
    print(f"\n[yukleyici · adım {n}] {m}", flush=True)


def _alt(m: str) -> None:
    print(f"   ↳ {m}", flush=True)


# ---------------------------------------------------------------------------
# Dosya seçimi
# ---------------------------------------------------------------------------
_DAMGA_RE = re.compile(r"_(\d{8}_\d{6})\.")


def _en_son(klasor: Path, desen: str) -> Path:
    adaylar = sorted(klasor.glob(desen), key=lambda p: p.stat().st_mtime, reverse=True)
    if not adaylar:
        raise FileNotFoundError(f"Bulunamadı: {klasor}/{desen}")
    return adaylar[0]


def _damga(yol: Path) -> str:
    e = _DAMGA_RE.search(yol.name)
    if not e:
        raise RuntimeError(f"Dosya adında zaman damgası yok: {yol.name}")
    return e.group(1)


def en_son_video_ve_senaryo() -> tuple[Path, str]:
    """
    En son MP4 alınır. Senaryo TXT, en son MP3 ile aynı damgadan okunur
    (TXT ↔ MP3 üretimde birlikte yazılır; MP4 sonradan başka bir damgayla
    montajlanmış olabilir).
    """
    mp4 = _en_son(SHORTS_KLASORU, "shorts_*.mp4")
    mp3 = _en_son(SES_KLASORU, "seslendirme_*.mp3")
    damga = _damga(mp3)
    txt = SES_KLASORU / f"senaryo_{damga}.txt"
    if not txt.exists():
        raise FileNotFoundError(f"MP3 ile eşleşen senaryo yok: {txt.name}")
    return mp4, txt.read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# Metadata üretimi + denetimi
# ---------------------------------------------------------------------------

def _metadata_dogrula(veri: dict) -> dict:
    """Metadata alanlarını YouTube gereksinimlerine göre doğrular ve düzeltir."""
    if len(veri["title"]) > 100:
        veri["title"] = veri["title"][:97] + "..."
    if "#Shorts" not in veri["description"]:
        veri["description"] = veri["description"].rstrip() + "\n\n#Shorts"
    return veri


def metadata_uret(senaryo: str) -> dict:
    yanit = bridge.gemini_metin_uret(
        prompt=f"Script:\n{senaryo}",
        sistem_promptu=METADATA_SISTEM_PROMPTU,
        sicaklik=0.6,
        max_token=2048,
    )
    eslesme = re.search(r"\{.*\}", yanit, re.DOTALL)
    if not eslesme:
        raise RuntimeError(f"Metadata JSON çıkmadı:\n{yanit}")
    veri = json.loads(eslesme.group(0))
    veri.setdefault("title", "")
    veri.setdefault("description", "")
    veri.setdefault("tags", [])
    return _metadata_dogrula(veri)


def metadatayi_denetlet(veri: dict, senaryo: str) -> dict:
    metin_paketi = (
        f"TITLE: {veri['title']}\n\n"
        f"DESCRIPTION:\n{veri['description']}\n\n"
        f"TAGS: {', '.join(veri['tags'])}"
    )
    baglam = (
        "Bu bir YouTube Shorts metadata paketi (başlık + açıklama + etiketler). "
        "Senaryoya sadık, dürüst ve ilgi çekici olmalı. Clickbait, abartı, "
        "yanıltıcı vaatler kabul edilmez.\n\n"
        f"Senaryo:\n{senaryo}"
    )
    rapor = bridge.metin_onay_iste(metin_paketi, baglam=baglam)
    print(f"   ↳ Metin denetimi → {rapor['karar']}: {rapor['ozet']}")
    if rapor["karar"] != "REVIZE":
        return veri

    yeni = rapor.get("revize_metin", "")

    # Gemini bazen revize_metin alanını dict (yapılandırılmış) olarak döndürüyor.
    # Bu durumda doğrudan title/description/tags alanlarını çekmeyi dene;
    # değilse JSON'a serialize edip regex parser'a düş.
    if isinstance(yeni, dict):
        if any(k in yeni for k in ("title", "description", "tags")):
            if yeni.get("title"):
                veri["title"] = str(yeni["title"]).strip()
            if yeni.get("description"):
                veri["description"] = str(yeni["description"]).strip()
            tags = yeni.get("tags")
            if isinstance(tags, list) and tags:
                veri["tags"] = [str(t).strip() for t in tags if str(t).strip()]
            return _metadata_dogrula(veri)
        yeni = json.dumps(yeni, ensure_ascii=False)
    elif not isinstance(yeni, str):
        yeni = str(yeni)

    # Daha sağlam, bağımsız regex'ler kullanın
    # Başlık: TITLE: ile başlayan ve bir sonraki satıra veya dizenin sonuna kadar olan her şeyi arayın
    yt_match = re.search(r"TITLE:\s*(.+?)(?:\n|$)", yeni)
    if yt_match:
        veri["title"] = yt_match.group(1).strip()

    # Açıklama: DESCRIPTION: ile başlayan ve TAGS: veya dizenin sonuna kadar olan her şeyi arayın
    # Yeni satırları eşleştirmek için re.DOTALL kullanın
    yd_match = re.search(r"DESCRIPTION:\s*(.*?)(?=\n\nTAGS:|$)", yeni, re.DOTALL)
    if yd_match:
        veri["description"] = yd_match.group(1).strip()

    # Etiketler: TAGS: ile başlayan ve bir sonraki satıra veya dizenin sonuna kadar olan her şeyi arayın
    yg_match = re.search(r"TAGS:\s*(.+?)(?:\n|$)", yeni)
    if yg_match:
        veri["tags"] = [t.strip() for t in yg_match.group(1).split(",") if t.strip()]
    
    # Revize edilmiş metin üzerinde doğrulamayı yeniden uygulayın
    return _metadata_dogrula(veri)


# ---------------------------------------------------------------------------
# OAuth + YouTube istemcisi
# ---------------------------------------------------------------------------
def youtube_istemcisi():
    if not CLIENT_SECRET.exists():
        raise FileNotFoundError(
            f"client_secret.json yok: {CLIENT_SECRET}. "
            "Google Cloud Console'dan OAuth Desktop client oluştur, indir ve buraya koy."
        )
    creds = None
    if TOKEN_DOSYASI.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_DOSYASI), YOUTUBE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            _alt("OAuth token süresi dolmuş, refresh ediliyor...")
            creds.refresh(Request())
        else:
            _alt("İlk OAuth açılışı: tarayıcı pencerelenecek, izin ver...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET), YOUTUBE_SCOPES
            )
            creds = flow.run_local_server(port=0, prompt="consent", open_browser=True)
        TOKEN_DOSYASI.write_text(creds.to_json(), encoding="utf-8")
        _alt(f"Token kaydedildi: {TOKEN_DOSYASI.name}")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


# ---------------------------------------------------------------------------
# Yükleme
# ---------------------------------------------------------------------------
def videoyu_yukle(
    youtube,
    video_yolu: Path,
    veri: dict,
    gizlilik: str,
    cocuk_icerikli: bool,
    kategori_id: str,
) -> str:
    body = {
        "snippet": {
            "title": veri["title"],
            "description": veri["description"],
            "tags": veri["tags"],
            "categoryId": kategori_id,
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": gizlilik,
            "selfDeclaredMadeForKids": cocuk_icerikli,
            "embeddable": True,
        },
    }
    medya = MediaFileUpload(
        str(video_yolu),
        mimetype="video/mp4",
        chunksize=1024 * 1024,
        resumable=True,
    )
    istek = youtube.videos().insert(part="snippet,status", body=body, media_body=medya)

    yanit = None
    son_yuzde = -1
    while yanit is None:
        durum, yanit = istek.next_chunk()
        if durum:
            yuzde = int(durum.progress() * 100)
            if yuzde != son_yuzde:
                _alt(f"Yükleniyor: %{yuzde}")
                son_yuzde = yuzde
    return yanit["id"]


def yukleme_loguna_yaz(kayit: dict) -> None:
    log = []
    if YUKLEME_LOGU.exists():
        try:
            log = json.loads(YUKLEME_LOGU.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log = []
    log.append(kayit)
    YUKLEME_LOGU.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Ana akış
# ---------------------------------------------------------------------------
def main() -> int:
    p = argparse.ArgumentParser(description="Gemini denetimli YouTube Shorts yükleyici")
    p.add_argument(
        "--gizlilik", choices=["private", "unlisted", "public"], default="private",
        help="Yayın gizliliği. Varsayılan: private (Studio'da inceleyip yayınla).",
    )
    p.add_argument(
        "--made-for-kids", choices=["yes", "no"], default="no",
        help="COPPA/Made for Kids beyanı. Varsayılan: no (haber içeriği).",
    )
    p.add_argument(
        "--kategori", choices=["news", "tech"], default="tech",
        help="YouTube kategori: news=25, tech=28. Varsayılan: tech.",
    )
    args = p.parse_args()

    try:
        _adim(1, "En son MP4 ve eşleşen senaryo bulunuyor...")
        mp4, senaryo = en_son_video_ve_senaryo()
        boyut_mb = mp4.stat().st_size / (1024 * 1024)
        _alt(f"Video:    {mp4.name} ({boyut_mb:.2f} MB)")
        _alt(f"Senaryo:  {len(senaryo.split())} kelime")

        _adim(2, "Gemini ile başlık + açıklama + etiketler üretiliyor...")
        veri = metadata_uret(senaryo)
        _alt(f"Title:    {veri['title']}")
        _alt(f"Tags:     {', '.join(veri['tags'])}")

        _adim(3, "Metin paketi içerik denetimine gönderiliyor...")
        veri = metadatayi_denetlet(veri, senaryo)
        _alt(f"Final title: {veri['title']}")

        _adim("3b", "Yayın uygunluk denetimi (telif/clickbait/olgusal/politika/marka)...")
        denetim = bridge.icerik_uygunluk_denetimi(
            senaryo=senaryo,
            baslik=veri["title"],
            aciklama=veri["description"],
            etiketler=veri["tags"],
        )
        _alt(f"Karar: {denetim['karar']} — {denetim['sebep']}")
        if denetim.get("risk_alanlari"):
            _alt(f"Risk: {', '.join(denetim['risk_alanlari'])}")

        denetim_notu = None
        if denetim["karar"] in {"SUPHELI", "REDDED"}:
            denetim_notu = f"{denetim['karar']}: {denetim['sebep']} (risk: {','.join(denetim.get('risk_alanlari', []))})"
            if args.gizlilik != "private":
                _alt(f"⚠️ Şüpheli içerik → gizlilik PRIVATE'a override edildi (orijinal istek: {args.gizlilik})")
                args.gizlilik = "private"
            DENETIM_UYARI_FLAG.write_text(denetim_notu, encoding="utf-8")

        _adim(4, "OAuth: kimlik doğrulama / token yenileme...")
        youtube = youtube_istemcisi()
        _alt("YouTube istemcisi hazır ✓")

        kategori_id = (
            YOUTUBE_KATEGORI_NEWS if args.kategori == "news" else YOUTUBE_KATEGORI_TECH
        )
        _adim(
            5,
            f"YouTube'a yükleniyor — gizlilik={args.gizlilik}, "
            f"made_for_kids={args.made_for_kids}, kategori={args.kategori}({kategori_id})...",
        )
        video_id = videoyu_yukle(
            youtube,
            mp4,
            veri,
            gizlilik=args.gizlilik,
            cocuk_icerikli=(args.made_for_kids == "yes"),
            kategori_id=kategori_id,
        )

        watch_url = f"https://youtu.be/{video_id}"
        studio_url = f"https://studio.youtube.com/video/{video_id}/edit"
        _adim(6, "Yükleme tamamlandı ✓")
        _alt(f"Video ID:    {video_id}")
        _alt(f"Watch:       {watch_url}")
        _alt(f"Studio:      {studio_url}")

        yukleme_loguna_yaz({
            "zaman": datetime.now().isoformat(timespec="seconds"),
            "video_id": video_id,
            "title": veri["title"],
            "tags": veri["tags"],
            "gizlilik": args.gizlilik,
            "made_for_kids": args.made_for_kids,
            "kategori": args.kategori,
            "kaynak_dosya": mp4.name,
            "boyut_mb": round(boyut_mb, 2),
            "watch_url": watch_url,
            "studio_url": studio_url,
            "denetim_notu": denetim_notu,
            "denetim_karari": denetim["karar"],
        })
        _alt(f"Log: {YUKLEME_LOGU.name} güncellendi")

        if args.gizlilik == "private":
            print(
                "\n[yukleyici] HATIRLATMA: Video PRIVATE olarak yüklendi. "
                "YouTube Studio'da incele, hazırsa yayına al."
            )

        # Başarı bildirimi: yalnızca UYGUN denetim + public/unlisted yayında flag yaz
        if denetim["karar"] == "UYGUN" and args.gizlilik in {"public", "unlisted"}:
            BASARI_BILDIRIM_FLAG.write_text(
                json.dumps({
                    "video_id": video_id,
                    "title": veri["title"],
                    "watch_url": watch_url,
                    "studio_url": studio_url,
                    "gizlilik": args.gizlilik,
                    "tag_sayisi": len(veri["tags"]),
                    "aciklama_uzunluk": len(veri["description"]),
                }, ensure_ascii=False),
                encoding="utf-8",
            )
        return 0

    except FileNotFoundError as hata:
        print(f"[yukleyici] Eksik dosya: {hata}", file=sys.stderr)
        return 2
    except HttpError as hata:
        print(f"[yukleyici] YouTube API hatası: {hata}", file=sys.stderr)
        return 3
    except RuntimeError as hata:
        print(f"[yukleyici] Çalışma hatası: {hata}", file=sys.stderr)
        return 4
    except OSError as hata:
        print(f"[yukleyici] Sistem/IO hatası: {hata}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    sys.exit(main())