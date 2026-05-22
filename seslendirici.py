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

SENARYO_SISTEM_PROMPTU = """You are a viral YouTube Shorts scriptwriter. Your job
is RETENTION — the first 2 seconds decide if the video lives or dies.

═══ RULE #0 — FACTUAL FIDELITY (HIGHEST PRIORITY, OVERRIDES EVERYTHING) ═══
The script MUST be 100% factually faithful to the source headline. This is
absolute and beats every other instruction below.
- NEVER overstate, dramatize beyond the facts, or invent a claim.
- NEVER present an unverified/rumored/speculative item as confirmed fact.
- NEVER change the outcome, cause, or actors of an event.
- If the headline itself is sensational or uncertain, DOWNGRADE it: use
  hedges like "reportedly", "appears to", "claims" — do not amplify it.
- A metaphorical or punchy headline must be explained literally in the body.
- The hook can be CURIOUS and PUNCHY, but it must be TRUE. Curiosity comes
  from a real angle, never from invented drama.
A factually wrong script is REJECTED downstream and never publishes — so
accuracy is not optional, it is the whole job.

LANGUAGE: ALWAYS write in English. Never Turkish, never mixed. 100% English.

Required structure:
- HOOK (first sentence, MAX 8 words): a punchy, curiosity-gap opener that
  stops the thumb — but strictly TRUE. Feel: a real surprising angle of the
  actual story. NO "Did you know", NO "In today's video". Punch immediately,
  honestly.
- RETENTION BRIDGE (1 short sentence): a curiosity line that keeps the viewer
  watching — phrased as a real "here's the interesting part", not fake hype.
- TURN (1 sentence): the surprising but TRUE fact that pays off the hook
- CONTEXT (1 sentence): plain-language what actually happened
- PAYOFF (final short sentence): the real "so what" that lingers. NO hashtags,
  NO emojis, NO "subscribe/like/follow", NO question to the audience.

Constraints:
- Total length: STRICT 55–70 words. Never above 70, never below 50.
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
    temel_prompt = (
        f"Headline: {haber['baslik']}\n"
        f"Source URL: {haber['url']}\n"
        f"Engagement signal: score={haber.get('skor')}, "
        f"comments={haber.get('yorum_sayisi')}, age={haber.get('yas_saat')}h\n\n"
        f"Write the Shorts voice-over script now (55-70 words, English only)."
    )
    # Çok kısa çıkarsa 1 kez daha dene
    son_senaryo = ""
    for deneme in range(2):
        ek = "" if deneme == 0 else (
            f"\n\nYOUR PREVIOUS DRAFT WAS TOO SHORT ({len(son_senaryo.split())} words). "
            f"Rewrite it 55-70 words by adding one concrete detail to CONTEXT. Keep the same hook."
        )
        senaryo = bridge.gemini_metin_uret(
            prompt=temel_prompt + ek,
            sistem_promptu=SENARYO_SISTEM_PROMPTU,
            sicaklik=0.8,
            max_token=2048,
        ).strip('"').strip()
        son_senaryo = senaryo
        if len(senaryo.split()) >= 45:
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
        f"Hedef: KESİN 55-70 İngilizce kelime. ASLA uzatma — kısa = yüksek "
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
    edge-tts cue'larından viral-Shorts stili ASS altyazı: 3 kelimelik hızlı
    bloklar + her blokta ANA kelime SARI vurgulu (referans viral videodaki
    stil). libass ile videoya gömülür. Stil ASS içinde — force_style gereksiz.
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
        "Style: Pop,Arial,60,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,"
        "1,0,0,0,100,100,0,0,1,5,2,2,60,60,300,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
    )
    SARI = r"{\c&H0000FFFF&}"
    BEYAZ = r"{\c&H00FFFFFF&}"
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
                parcalar.append(f"{SARI}{w.upper()}{BEYAZ}" if i == vi else w)
            metin_ass = " ".join(parcalar)
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
    referans viral videodaki stile çevirir. Sıfır ek maliyet.
    """
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
