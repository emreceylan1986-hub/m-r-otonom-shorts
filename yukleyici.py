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
import kanal_config


PANEL_KOK = Path(__file__).parent
SHORTS_KLASORU = PANEL_KOK / "shorts_ciktilari"
SES_KLASORU = PANEL_KOK / "ses_ciktilari"
CLIENT_SECRET = PANEL_KOK / "client_secret.json"
# Aktif kanalın token dosyası (KANAL env; ayarlı değilse token.json = TrendCatcher)
TOKEN_DOSYASI = PANEL_KOK / kanal_config.kanal_config()["token_dosyasi"]
YUKLEME_LOGU = PANEL_KOK / "yuklemeler.json"
DENETIM_UYARI_FLAG = PANEL_KOK / ".denetim_uyari"   # workflow şüpheli içerik issue tetikleyici
BASARI_BILDIRIM_FLAG = PANEL_KOK / ".basarili_yayin" # workflow başarılı yayın issue tetikleyici

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",  # comment+caption upload
]
# yt-analytics.readonly scope ayrı bir OAuth flow gerektirir; analytics.py
# kendi token'ını yönetir (token_analytics.json). yukleyici stabil kalır.
YOUTUBE_KATEGORI_NEWS = "25"        # News & Politics
YOUTUBE_KATEGORI_TECH = "28"        # Science & Technology
YOUTUBE_KATEGORI_ANIMALS = "15"     # Pets & Animals (yeni niş varsayılanı)

METADATA_SISTEM_PROMPTU = """You produce YouTube Shorts metadata as STRICT JSON.

LANGUAGE: ALL output (title, description, tags) MUST be in ENGLISH ONLY.
Even if the source news is Turkish or any other language, translate and write
100% English. This channel targets a global English-speaking audience for
maximum reach and ad revenue. Non-English output is forbidden — non-negotiable.

This metadata MUST be SEO-optimized for YouTube search.

Schema:
{
  "title": "60-95 characters. FRONT-LOAD the main keyword in the first 50 chars (critical for search). No emojis, no ALL CAPS. BANNED clickbait words/phrases — never use any of: shocking, secretly, secret, hidden, they don't want you to know, you won't believe, this is why, the truth about, exposed, will blow your mind, insane, crazy. The title must be a calm factual statement of what happened.",
  "description": "200-400 characters TOTAL. Structure:
    - LINE 1 (most important — first 100 chars get strongest SEO weight):
      Start with a CONCRETE FACT statement that contains the main keyword.
      Example: 'Lake Hillier in Australia stays permanently bubblegum-pink due to extremophile algae.'
      The keyword MUST appear in the first 80 characters.
      ⚠️ BANNED OPENINGS (AI signal / bot detection risk):
        'Did you know' / 'Ever wonder' / 'Ever wondered' / 'Ever imagine'
        'Do you know' / 'Have you ever' / 'Imagine' / 'Picture this' / 'Meet the'
      Start with a STATEMENT, not a question. Calm factual tone.
    - Lines 2-3: 1-2 short sentences expanding the fact with a concrete number
      or comparison (e.g. '10× saltier than the ocean').
    - Last line: 4-6 hashtags. ALWAYS include #Shorts, then 3-5 niche tags
      like #animals #nature #wildlife #didyouknow #amazingfacts #animallover #fyp
    NO external links. NO 'subscribe' / 'like' / 'follow' calls.",
  "tags": ["8-12 lowercase tags, no '#' prefix, no spaces in single tags. Mix:
            - 3 broad niche tags ('animals', 'nature', 'wildlife', 'didyouknow', 'amazingfacts')
            - 5 specific tags about the actual subject ('octopus', 'deep sea', 'predator')
            - 1-2 HIGH-INTENT long-tail phrases a curious viewer would actually
              search, as a single spaceless-or-quoted tag value
              (e.g. 'why do octopuses have three hearts', 'animal facts you didnt know').
              Few high-intent search phrases beat many generic tags.
            - 2 trending ('shorts', 'fyp', 'animallovers', 'satisfying')"]
}

Rules:
- FACTUAL FIDELITY (highest priority): title + description must be 100%
  faithful to the script. NEVER overstate, never invent, never present a
  rumored/unverified item as confirmed. Do not change outcome/cause/actors.
  A metaphorical script line must be stated literally in the title.
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
    # YouTube API title/description'da < ve > kabul etmiyor (XSS güvenliği).
    # Gemini bazen kaynaktaki HTML tag adlarını (örn '<dl>') başlığa olduğu
    # gibi taşıyor → 'invalidTitle' 400. Tag karakterlerini güvenli formata çevir.
    for alan in ("title", "description"):
        if isinstance(veri.get(alan), str):
            veri[alan] = veri[alan].replace("<", "(").replace(">", ")").strip()
    # Boş title — YouTube reddi; basit fallback (denetim sonrası fark edilirse)
    if not veri.get("title"):
        veri["title"] = "Tech News Update"
    if len(veri["title"]) > 100:
        veri["title"] = veri["title"][:97] + "..."
    if "#Shorts" not in veri["description"]:
        veri["description"] = veri["description"].rstrip() + "\n\n#Shorts"
    # 20 Haz: CTA + Playlist sonek (abone toplama + iç trafik) — kanala özel
    cta_sonek = kanal_config.kanal_config()["cta_sonek"]
    if "sub_confirmation" not in veri["description"]:
        veri["description"] = veri["description"].rstrip() + cta_sonek
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
        "--kategori", choices=["news", "tech", "animals"], default="animals",
        help="YouTube kategori: news=25, tech=28, animals=15. Varsayılan: animals (yeni niş).",
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
        # Kaynak haberi denetime ver — olgusal denetim 'senaryo kaynağa sadık mı'
        # diye yapılsın, 'haber gerçek mi' diye Gemini'nin bilgisinden DEĞİL.
        kaynak_baslik, kaynak_url = "", ""
        try:
            _h = json.loads((PANEL_KOK / "haberler.json").read_text(encoding="utf-8"))
            if _h.get("haberler"):
                kaynak_baslik = _h["haberler"][0].get("baslik", "")
                kaynak_url = _h["haberler"][0].get("url", "")
        except (OSError, json.JSONDecodeError, KeyError, IndexError):
            pass
        denetim = bridge.icerik_uygunluk_denetimi(
            senaryo=senaryo,
            baslik=veri["title"],
            aciklama=veri["description"],
            etiketler=veri["tags"],
            kaynak_baslik=kaynak_baslik,
            kaynak_url=kaynak_url,
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

        # FAZ 5: Affiliate link açıklama zenginleştirici (env'de tag yoksa no-op)
        try:
            from affiliate_link import aciklama_zenginleştir
            zenginlestirilmis = aciklama_zenginleştir(
                veri["description"], veri["title"], veri.get("tags", [])
            )
            if zenginlestirilmis != veri["description"]:
                _alt("Açıklama affiliate link ile zenginleştirildi")
                veri["description"] = zenginlestirilmis
        except Exception as h:
            _alt(f"Affiliate zenginleştirme atlandı: {h}")

        # FAZ 7: Pre-publish hook QC (Gemini Vision)
        try:
            import pre_publish_qc
            hook_skor, hook_sebep = pre_publish_qc.hook_qc(
                mp4, veri["title"], veri.get("tags", [""])[0] if veri.get("tags") else ""
            )
            _alt(f"Hook QC skor: {hook_skor}/10 — {hook_sebep[:80]}")
            if hook_skor < 5:
                _alt(f"⚠️ Hook zayıf (skor {hook_skor}) → gizlilik PRIVATE'a override")
                args.gizlilik = "private"
                hook_uyari = f"Pre-publish QC: hook skor {hook_skor}/10 — {hook_sebep}"
                DENETIM_UYARI_FLAG.write_text(hook_uyari, encoding="utf-8")
        except Exception as h:
            _alt(f"Pre-publish QC atlandı: {str(h)[:100]}")

        _adim(4, "OAuth: kimlik doğrulama / token yenileme...")
        youtube = youtube_istemcisi()
        _alt("YouTube istemcisi hazır ✓")

        kategori_id = {
            "news": YOUTUBE_KATEGORI_NEWS,
            "tech": YOUTUBE_KATEGORI_TECH,
            "animals": YOUTUBE_KATEGORI_ANIMALS,
        }[args.kategori]
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

        # FAZ 4: A/B title test — aktif başlık A, Gemini'den B alternatifi üret + kayıt
        try:
            import ab_title_test
            alt_basliklar = ab_title_test.baslik_iki_uret(veri["title"])
            if alt_basliklar and len(alt_basliklar) >= 2:
                # Gemini A ve B üretir — biz A=aktif başlık (yayında), B=alternatif
                B_baslik = alt_basliklar[1] or alt_basliklar[0]
                ab_title_test.ab_kaydet(
                    veri["title"][:80], video_id,
                    veri["title"], B_baslik
                )
                _alt(f"A/B test kaydedildi — B alternatifi: {B_baslik[:50]}")
        except Exception as ab_h:
            _alt(f"A/B test kayıt atlandı: {str(ab_h)[:100]}")

        # FAZ 4: Creator pinned comment (engagement bomba)
        try:
            import pinned_comment
            pinned_comment.creator_comment_at(youtube, video_id, veri["title"], senaryo[:300])
        except Exception as pc_h:
            _alt(f"Creator comment atlandı: {pc_h}")

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