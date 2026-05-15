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

LANGUAGE: ALWAYS write in English. Never Turkish, never mixed. Even if the source
is non-English, the script is 100% English. This is non-negotiable.

Required structure:
- HOOK (first sentence, MAX 8 words): a pattern-breaking, curiosity-gap or
  shock opener that physically stops the thumb. Examples of the FEEL:
  "Your code isn't yours anymore." / "This AI just refused to work." /
  "Big Tech doesn't want you to know this." NO slow build-up, NO "Did you know",
  NO "In today's video". Punch immediately.
- TURN (1 sentence): the surprising fact that pays off the hook
- CONTEXT (1-2 sentences): plain-language what happened
- PAYOFF (1 sentence): the "so what" — why the viewer should care
- BUTTON (final short sentence): a thought that lingers. NO hashtags, NO emojis,
  NO "subscribe/like/follow", NO question to the audience.

Constraints:
- Total length: STRICT 70–95 words. Never below 70, never above 95.
  If your draft is under 70 words, expand the CONTEXT with one concrete detail.
- Short, punchy sentences. Spoken rhythm. Contractions OK.
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
        f"Write the Shorts voice-over script now (70-95 words, English only)."
    )
    # Kısa çıkarsa 1 kez daha dene (Gemini bazen 70 altına düşüyor)
    son_senaryo = ""
    for deneme in range(2):
        ek = "" if deneme == 0 else (
            f"\n\nYOUR PREVIOUS DRAFT WAS TOO SHORT ({len(son_senaryo.split())} words). "
            f"Rewrite it 75-90 words by adding one concrete detail to CONTEXT. Keep the same hook."
        )
        senaryo = bridge.gemini_metin_uret(
            prompt=temel_prompt + ek,
            sistem_promptu=SENARYO_SISTEM_PROMPTU,
            sicaklik=0.8,
            max_token=2048,
        ).strip('"').strip()
        son_senaryo = senaryo
        if len(senaryo.split()) >= 60:
            return senaryo
    raise RuntimeError(
        f"Senaryo 2 denemede de çok kısa ({len(son_senaryo.split())} kelime). "
        f"Ham çıktı: {son_senaryo!r}"
    )


def senaryoyu_denetlet(senaryo: str, haber: dict) -> str:
    baglam = (
        f"Bu metin bir 30-45 saniyelik YouTube Shorts seslendirme senaryosu.\n"
        f"Haber: {haber['baslik']}\n"
        f"Kaynak: {haber['url']}\n"
        f"Hedef: 75-110 İngilizce kelime, çarpıcı hook, doğal konuşma."
    )
    rapor = bridge.metin_onay_iste(senaryo, baglam=baglam)
    print(f"[seslendirici] Metin denetimi → {rapor['karar']}: {rapor['ozet']}")
    if rapor.get("iyilestirmeler"):
        for i in rapor["iyilestirmeler"]:
            print(f"  ↪ {i}")
    return rapor.get("revize_metin", senaryo).strip()


def _srt_zaman(ms: float) -> str:
    toplam = int(ms)
    sn, msec = divmod(toplam, 1000)
    saat, sn = divmod(sn, 3600)
    dk, sn = divmod(sn, 60)
    return f"{saat:02d}:{dk:02d}:{sn:02d},{msec:03d}"


def _karaoke_srt(cues: list[tuple[int, int, str]], grup: int = 3) -> str:
    """
    edge-tts boundary cue'larını (offset/duration 100ns birimi) Shorts-style
    KARAOKE altyazıya çevirir: cümle uzunsa süresine orantılı ~3 kelimelik
    hızlı değişen parçalara böler. Hızlı altyazı = yüksek retention.
    """
    parcalar: list[str] = []
    idx = 1
    for offset, duration, metin in cues:
        kelimeler = metin.split()
        if not kelimeler:
            continue
        gruplar = (
            [kelimeler]
            if len(kelimeler) <= 4
            else [kelimeler[i:i + grup] for i in range(0, len(kelimeler), grup)]
        )
        toplam_kelime = len(kelimeler)
        baslangic = offset
        for g in gruplar:
            pay = duration * (len(g) / toplam_kelime)
            bit = baslangic + pay
            bas_ms = baslangic / 10000.0   # 100ns → ms
            bit_ms = bit / 10000.0
            parcalar.append(
                f"{idx}\n{_srt_zaman(bas_ms)} --> {_srt_zaman(bit_ms)}\n{' '.join(g)}\n"
            )
            idx += 1
            baslangic = bit
    return "\n".join(parcalar)


async def _seslendir_async(metin: str, mp3_yolu: Path, srt_yolu: Path) -> None:
    """
    Hem MP3 sesi hem zaman-eşli KARAOKE SRT altyazı üretir.
    edge-tts WordBoundary veya SentenceBoundary event'i verir (sese göre
    değişir); ikisini de toplar, custom builder ile Shorts-style hızlı
    altyazıya çevirir. Sıfır ek maliyet.
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
    srt_yolu.write_text(_karaoke_srt(cues), encoding="utf-8")


def seslendir(metin: str, mp3_yolu: Path, srt_yolu: Path) -> None:
    asyncio.run(_seslendir_async(metin, mp3_yolu, srt_yolu))


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
        srt_yolu = CIKTI_KLASORU / f"altyazi_{damga}.srt"
        txt_yolu.write_text(final_metin, encoding="utf-8")

        print(f"[seslendirici] edge-tts ile ses + altyazı üretiliyor ({SES}, hız {HIZ}, perde {PERDE})...")
        seslendir(final_metin, mp3_yolu, srt_yolu)

        boyut_kb = mp3_yolu.stat().st_size / 1024
        srt_satir = len(srt_yolu.read_text(encoding="utf-8").strip().splitlines())
        print(f"[seslendirici] MP3 hazır: {mp3_yolu.name} ({boyut_kb:.1f} KB)")
        print(f"[seslendirici] SRT hazır: {srt_yolu.name} ({srt_satir} satır)")
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
