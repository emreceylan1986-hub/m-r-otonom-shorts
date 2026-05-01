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

SENARYO_SISTEM_PROMPTU = """You are a senior YouTube Shorts scriptwriter.
Convert the given news headline + URL context into a 30-45 second voice-over script.

Required structure:
- HOOK: a single short sentence that stops the scroll in 3 seconds
- CONTEXT: 1–2 sentences explaining the news in plain language
- INSIGHT: the surprising angle or "so what" of the story
- CLOSING: a sharp, thought-provoking final line (NO hashtags, NO emojis, NO "subscribe", NO "follow")

Constraints:
- Total length: 75–110 words
- Conversational, natural spoken English (contractions OK)
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
    kullanici_promptu = (
        f"Headline: {haber['baslik']}\n"
        f"Source URL: {haber['url']}\n"
        f"Engagement signal: score={haber.get('skor')}, "
        f"comments={haber.get('yorum_sayisi')}, age={haber.get('yas_saat')}h\n\n"
        f"Write the 30-45 second Shorts voice-over script now."
    )
    senaryo = bridge.gemini_metin_uret(
        prompt=kullanici_promptu,
        sistem_promptu=SENARYO_SISTEM_PROMPTU,
        sicaklik=0.8,
        max_token=2048,
    )
    senaryo = senaryo.strip('"').strip()
    kelime_sayisi = len(senaryo.split())
    if kelime_sayisi < 60:
        raise RuntimeError(
            f"Üretilen senaryo çok kısa ({kelime_sayisi} kelime). "
            f"Hedef 75-110. Ham çıktı: {senaryo!r}"
        )
    return senaryo


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


async def _seslendir_async(metin: str, mp3_yolu: Path) -> None:
    iletisim = edge_tts.Communicate(
        text=metin,
        voice=SES,
        rate=HIZ,
        pitch=PERDE,
        volume=SES_SEVIYESI,
    )
    await iletisim.save(str(mp3_yolu))


def seslendir(metin: str, mp3_yolu: Path) -> None:
    asyncio.run(_seslendir_async(metin, mp3_yolu))


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
        txt_yolu.write_text(final_metin, encoding="utf-8")

        print(f"[seslendirici] edge-tts ile seslendiriliyor ({SES}, hız {HIZ}, perde {PERDE})...")
        seslendir(final_metin, mp3_yolu)

        boyut_kb = mp3_yolu.stat().st_size / 1024
        print(f"[seslendirici] MP3 hazır: {mp3_yolu.name} ({boyut_kb:.1f} KB)")
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
