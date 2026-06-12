"""
seslendirici.py — YouTube Shorts Seslendirme Üreticisi

Akış:
    1) haberler.json içindeki ilk haberi okur
    2) Gemini ile çarpıcı bir İngilizce Shorts senaryosu üretir
    3) Senaryoyu bridge.metin_onay_iste() ile denetler — REVIZE varsa
       revize edilmiş sürümü kullanır
    4) edge-tts (en-US-AriaNeural, sweet tone) ile MP3 dosyasına seslendirir
    5) Hem .txt (metin) hem .mp3 (ses) çıktısı verir

Çıktı klasörü: ses_ciktilari/
    senaryo_<damga>.txt
    seslendirme_<damga>.mp3
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import edge_tts

import bridge


KAYNAK_DOSYA = Path(__file__).parent / "haberler.json"
CIKTI_KLASORU = Path(__file__).parent / "ses_ciktilari"

SES = "en-US-AriaNeural"
HIZ = "-3%"        # hafif yavaş → daha şefkatli/sıcak his
PERDE = "+3Hz"     # hafif yüksek perde → daha tatlı tonlama
SES_SEVIYESI = "+0%"

SENARYO_SISTEM_PROMPTU = """You are a viral YouTube Shorts narrator in the
ANIMAL / NATURE / AMAZING-FACTS niche. Your job is RETENTION — the first
2 seconds decide if the video lives or dies.

═══ RULE #0 — FACTUAL FIDELITY (HIGHEST PRIORITY, OVERRIDES EVERYTHING) ═══
The script MUST be 100% factually faithful to the source post + a viewer-safe
embellishment of well-established nature/animal/science facts.
- NEVER overstate a single source claim, dramatize beyond it, or invent.
- NEVER present a rumored/joke/speculative item as confirmed fact.
- If the source title is a meme/joke ("cat does X"), describe what is ACTUALLY
  shown — do NOT claim things not in the source.
- The hook can be CURIOUS and PUNCHY, but it must be TRUE.
- Stick to widely accepted, well-known animal/nature facts when you expand
  context. Do not invent species, behaviors, or numbers.
A factually wrong script is REJECTED downstream and never publishes.

LANGUAGE: ALWAYS write in English. Never Turkish, never mixed. 100% English.

TONE: Warm, awe-struck, fascinated. Imagine a calm narrator showing the
viewer something beautiful and surprising about the natural world. Conversational,
not academic. NO clickbait words (shocking, insane, crazy, you won't believe).

Required structure (60-75 words total):
- HOOK (first sentence, MAX 8 words): a punchy, curiosity-gap opener about
  the animal/nature subject. Truthful. Feel: "Octopuses have three hearts."
  / "This bird builds traps." / "Trees can warn each other." NO question marks.
  ── REGISTERED VIRAL PATTERN (TrendCatcher kanal verisi 2026-Haz):
     Top performers — "Frogs Freeze & Revive" (1079 izl), "Zombie-Ant Fungus"
     (1074 izl), "Australia Lake Hillier Pink" (1125 izl). ORTAK PATTERN:
     [doğal anomali] + [sürpriz tek-cümle] + [somut sayı/öğe].
- TURN (1 sentence): the surprising-but-true expansion of the hook
- CONTEXT (1-2 sentences): the actual nature/science behind it, plain language.
  ── 8-12. saniye drop-off riski yüksek — bu cümlede SOMUT bir SAYI veya
     karşılaştırma kullan (kaç kat, kaç yıl, kaç metre). Sayı = retention boost.
- PAYOFF (1 short sentence): a wonder-inducing closing thought before the CTA.
  Örnek: "Nature still hides countless wonders like this one."
- SUBSCRIBE CTA (final sentence, MANDATORY, exactly 1 short line, max 7 words):
  ── A casual, warm, NOT pushy subscribe ask. Examples:
     "Hit subscribe for daily nature shorts."
     "Subscribe — more nature gems daily."
     "Subscribe for one wild fact daily."
     "Follow for daily nature secrets."
  ── Variation per video. NEVER say "like", "share", "comment below".
  ── NO hashtags, NO emojis in the script body.

Constraints:
- Total length: STRICT 60–75 words (subscribe CTA dahil). Never above 75.
- Very short, punchy sentences. Spoken rhythm. Contractions OK.
- Output ONLY the spoken script text — no headings, no labels, no quotation marks
"""


def ilk_haberi_oku() -> dict:
    if not KAYNAK_DOSYA.exists():
        raise FileNotFoundError(f"Kaynak yok: {KAYNAK_DOSYA}")
    veri = json.loads(KAYNAK_DOSYA.read_text(encoding="utf-8"))
    haberler = veri.get("haberler") or []
    if not haberler:
        raise ValueError("haberler.json içinde hiç haber yok.")
    return haberler[0]


def senaryo_uret(haber: dict) -> str:
    # FAZ 7 — 60 sn A/B: Pazartesi+Perşembe günlerinde 100-115 kelime uzun varyant
    # (~50-55 sn). Diğer günlerde standart 60-75 (~25-30 sn).
    # Watch-time YPP için kritik — uzun varyant test sayar.
    import datetime
    wd = datetime.datetime.utcnow().weekday()  # 0=Mon, 3=Thu
    hour = datetime.datetime.utcnow().hour
    # Uzun varyant: Pazartesi 12 UTC + Perşembe 16 UTC (haftada 2 video deneme)
    uzun_varyant = (wd == 0 and hour < 14) or (wd == 3 and 14 <= hour < 18)
    if uzun_varyant:
        hedef_kelime = "100-115"
        min_kelime = 95
    else:
        hedef_kelime = "60-75"
        min_kelime = 50

    temel_prompt = (
        f"Headline: {haber['baslik']}\n"
        f"Source URL: {haber['url']}\n"
        f"Engagement signal: score={haber.get('skor')}, "
        f"comments={haber.get('yorum_sayisi')}, age={haber.get('yas_saat')}h\n\n"
        f"Write the Shorts voice-over script now ({hedef_kelime} words, English only)."
    )
    if uzun_varyant:
        temel_prompt += (
            f"\n\nLONG-FORM VARIANT (test): aim for {hedef_kelime} words / ~50-55 sec.\n"
            f"Add 1-2 extra concrete examples or comparisons in CONTEXT.\n"
            f"Hook + subscribe CTA stay punchy; expansion in the middle."
        )
    # Çok kısa çıkarsa 1 kez daha dene
    son_senaryo = ""
    for deneme in range(2):
        ek = "" if deneme == 0 else (
            f"\n\nYOUR PREVIOUS DRAFT WAS TOO SHORT ({len(son_senaryo.split())} words). "
            f"Rewrite it {hedef_kelime} words by adding one concrete detail to CONTEXT. Keep the same hook."
        )
        senaryo = bridge.gemini_metin_uret(
            prompt=temel_prompt + ek,
            sistem_promptu=SENARYO_SISTEM_PROMPTU,
            sicaklik=0.8,
            max_token=2048,
        ).strip('"').strip()
        son_senaryo = senaryo
        if len(senaryo.split()) >= min_kelime:
            return senaryo
    raise RuntimeError(
        f"Senaryo 2 denemede de çok kısa ({len(son_senaryo.split())} kelime). "
        f"Ham çıktı: {son_senaryo!r}"
    )


def senaryoyu_denetlet(senaryo: str, haber: dict) -> str:
    baglam = (
        f"Bu metin ~25-30 saniyelik viral YouTube Shorts seslendirme senaryosu.\n"
        f"Haber: {haber['baslik']}\n"
        f"Kaynak: {haber['url']}\n"
        f"Hedef: KESİN 60-75 İngilizce kelime (subscribe CTA dahil). ASLA uzatma — kısa = yüksek "
        f"tamamlanma oranı (en kritik Shorts sinyali). 70 kelimeyi aşan "
        f"revize KABUL EDİLEMEZ. Güçlü hook + curiosity bridge korunmalı, "
        f"dil İngilizce kalmalı."
    )
    rapor = bridge.metin_onay_iste(senaryo, baglam=baglam)
    print(f"[seslendirici] Metin denetimi → {rapor['karar']}: {rapor['ozet']}")
    if rapor.get("iyilestirmeler"):
        for i in rapor["iyilestirmeler"]:
            print(f"  ↪ {i}")
    return rapor.get("revize_metin", senaryo).strip()


_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "to", "of", "in", "on",
    "at", "for", "and", "or", "but", "it", "its", "this", "that", "with",
    "as", "by", "be", "has", "have", "had", "you", "your", "can", "will",
    "just", "not", "no", "now", "so", "we", "they", "he", "she", "i",
    "from", "up", "out", "if", "all", "do", "does", "did", "what", "why",
}


def _ass_zaman(ms: float) -> str:
    """ASS zaman formatı: H:MM:SS.cc (centisecond)."""
    toplam = int(ms)
    sn, msec = divmod(toplam, 1000)
    saat, sn = divmod(sn, 3600)
    dk, sn = divmod(sn, 60)
    return f"{saat:d}:{dk:02d}:{sn:02d}.{msec // 10:02d}"


def _vurgu_kelime(kelimeler: list[str]) -> int:
    """Bloktaki en güçlü kelimenin index'i: en uzun stopword-olmayan."""
    en_iyi, en_uzun = 0, -1
    for i, k in enumerate(kelimeler):
        sade = "".join(c for c in k.lower() if c.isalnum())
        if sade in _STOPWORDS:
            continue
        if len(sade) > en_uzun:
            en_uzun, en_iyi = len(sade), i
    return en_iyi


def _karaoke_ass(cues: list[tuple[int, int, str]], grup: int = 3) -> str:
    """
    Captacity-tarzı animasyonlu viral altyazı (Captacity repo mantığı, kendi
    implementasyonumuz — ek bağımlılık yok).
    - 3 kelimelik hızlı bloklar
    - Her bloğa POP animasyonu (\\t ile scale büyüt-küçült)
    - Hızlı fade-in (\\fad)
    - Ana kelime SARI + büyütülmüş scale
    - Kalın siyah outline + gölge (sessiz izleyene maksimum okunabilirlik)
    """
    bas = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        # Daha kalın outline (6), gölge (3), italik kapalı, semi-transparent BG
        "Style: Pop,Arial Black,64,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
        "1,0,0,0,100,100,0,0,1,6,3,2,60,60,260,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
    )
    SARI = r"{\c&H0000FFFF&}"
    BEYAZ = r"{\c&H00FFFFFF&}"
    # Captacity-tarzı pop: ilk 120ms scale 70→105→100, fade-in 80ms.
    POP_GIRIS = r"{\fad(80,40)\t(0,80,\fscx110\fscy110)\t(80,160,\fscx100\fscy100)}"
    satirlar: list[str] = []
    for offset, duration, metin in cues:
        kelimeler = metin.split()
        if not kelimeler:
            continue
        gruplar = (
            [kelimeler]
            if len(kelimeler) <= 4
            else [kelimeler[i:i + grup] for i in range(0, len(kelimeler), grup)]
        )
        toplam = len(kelimeler)
        baslangic = offset
        for g in gruplar:
            pay = duration * (len(g) / toplam)
            bit = baslangic + pay
            vi = _vurgu_kelime(g)
            parcalar = []
            for i, w in enumerate(g):
                if i == vi:
                    # ana kelime: sarı + biraz daha büyük (15% scale)
                    parcalar.append(rf"{SARI}{{\fscx115\fscy115}}{w.upper()}{{\fscx100\fscy100}}{BEYAZ}")
                else:
                    parcalar.append(w)
            metin_ass = POP_GIRIS + " ".join(parcalar)
            satirlar.append(
                f"Dialogue: 0,{_ass_zaman(baslangic/10000.0)},"
                f"{_ass_zaman(bit/10000.0)},Pop,,0,0,0,,{metin_ass}"
            )
            baslangic = bit
    return bas + "\n".join(satirlar) + "\n"


async def _seslendir_async(metin: str, mp3_yolu: Path, ass_yolu: Path) -> None:
    """
    MP3 ses + viral-Shorts stili ASS altyazı (sarı keyword highlight).
    edge-tts WordBoundary/SentenceBoundary event'i toplar, _karaoke_ass ile
    referans viral videodaki stile çevirir.

    edge-tts WebSocket 503/Handshake hatalarına karşı 5 denemeli backoff —
    Microsoft Edge TTS uçnoktası ara sıra spike yapıyor.
    """
    import asyncio as _aio
    son_hata: Exception | None = None
    for deneme in range(5):
        try:
            iletisim = edge_tts.Communicate(
                text=metin,
                voice=SES,
                rate=HIZ,
                pitch=PERDE,
                volume=SES_SEVIYESI,
            )
            cues: list[tuple[int, int, str]] = []
            with open(mp3_yolu, "wb") as ses:
                async for chunk in iletisim.stream():
                    if chunk["type"] == "audio":
                        ses.write(chunk["data"])
                    elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                        cues.append((chunk["offset"], chunk["duration"], chunk["text"]))
            if not cues:
                raise RuntimeError("edge-tts hiç altyazı zamanlaması döndürmedi.")
            ass_yolu.write_text(_karaoke_ass(cues), encoding="utf-8")
            return
        except Exception as hata:  # WSServerHandshakeError, NoAudioReceived, vs.
            son_hata = hata
            bekle = min(2 ** (deneme + 2), 60)  # 4, 8, 16, 32, 60 sn
            print(
                f"[seslendirici] edge-tts hata ({type(hata).__name__}) — "
                f"{bekle}s sonra yeniden ({deneme+1}/5)",
                flush=True,
            )
            await _aio.sleep(bekle)
    raise RuntimeError(f"edge-tts 5 denemede de başarısız: {son_hata}")


def seslendir(metin: str, mp3_yolu: Path, ass_yolu: Path) -> None:
    asyncio.run(_seslendir_async(metin, mp3_yolu, ass_yolu))


def main() -> int:
    try:
        CIKTI_KLASORU.mkdir(exist_ok=True)
        damga = datetime.now().strftime("%Y%m%d_%H%M%S")

        print("[seslendirici] İlk haber okunuyor...")
        haber = ilk_haberi_oku()
        print(f"  → {haber['baslik']}")

        print("[seslendirici] Gemini ile senaryo üretiliyor...")
        taslak = senaryo_uret(haber)
        print("─" * 60)
        print(taslak)
        print("─" * 60)

        print("[seslendirici] Senaryo denetime gönderiliyor...")
        final_metin = senaryoyu_denetlet(taslak, haber)
        print("─" * 60)
        print("FİNAL METİN:")
        print(final_metin)
        print("─" * 60)

        txt_yolu = CIKTI_KLASORU / f"senaryo_{damga}.txt"
        mp3_yolu = CIKTI_KLASORU / f"seslendirme_{damga}.mp3"
        ass_yolu = CIKTI_KLASORU / f"altyazi_{damga}.ass"
        txt_yolu.write_text(final_metin, encoding="utf-8")

        print(f"[seslendirici] edge-tts ile ses + ASS altyazı üretiliyor ({SES})...")
        seslendir(final_metin, mp3_yolu, ass_yolu)

        boyut_kb = mp3_yolu.stat().st_size / 1024
        ass_dialog = ass_yolu.read_text(encoding="utf-8").count("Dialogue:")
        print(f"[seslendirici] MP3 hazır: {mp3_yolu.name} ({boyut_kb:.1f} KB)")
        print(f"[seslendirici] ASS hazır: {ass_yolu.name} ({ass_dialog} altyazı bloğu, sarı vurgulu)")
        print(f"[seslendirici] TXT hazır: {txt_yolu.name}")
        return 0
    except (FileNotFoundError, ValueError) as hata:
        print(f"[seslendirici] Veri hatası: {hata}", file=sys.stderr)
        return 2
    except RuntimeError as hata:
        print(f"[seslendirici] Gemini/bridge hatası: {hata}", file=sys.stderr)
        return 3
    except OSError as hata:
        print(f"[seslendirici] Dosya/ağ hatası: {hata}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
