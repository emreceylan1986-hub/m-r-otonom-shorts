"""
gemini_tts.py — denetleme_paneli doğal seslendirme (Leda) (Gemini 2.5 TTS)

edge-tts "dijital" kalıyordu; Emre 26 Haz "Leda" sesini seçti. Gemini TTS
gerçek insan gibi + ücretsiz (mevcut GEMINI_API_KEY, ~45k karakter/ay, limit 1M).

Tek sorun: Gemini TTS kelime-zamanlaması (WordBoundary) VERMEZ → karaoke ASS
altyazı için seslendirici.py edge-tts cue'larını alır ve Gemini süresine
ÖLÇEKLER (ikisi de aynı metni aynı sırada söyler → lineer ölçek yeterince
isabetli). Bu modül SADECE sesi üretir; cue/ASS işi seslendirici.py'de.

Çıktı: 24kHz mono 16-bit PCM → MP3 (ffmpeg).
"""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg
from google.genai import types

import bridge

# Emre 26 Haz seçimi: Leda (genç/taze, sıcak). Alternatifler: Achernar(yumuşak),
# Sulafat(sıcak), Despina(pürüzsüz), Vindemiatrix(nazik).
SES = "Leda"
MODEL = "gemini-2.5-flash-preview-tts"

# Ton talimatı (konuşulmaz, sadece stil yönlendirir) — spiritüel/Mevlana havası
STIL = ("Narrate warmly, with fascination and wonder, like a nature documentary — calm, clear, engaging: ")

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def _pcm_to_mp3(pcm: bytes, mp3_yolu: Path) -> float:
    """24kHz mono 16-bit PCM → MP3. Saniye cinsinden süre döner."""
    gecici_wav = mp3_yolu.with_suffix(".tts.wav")
    with wave.open(str(gecici_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)
    sure = len(pcm) / (24000 * 2)  # bytes / (örnek hızı * 2 byte)
    subprocess.run(
        [FFMPEG, "-y", "-i", str(gecici_wav), "-codec:a", "libmp3lame",
         "-b:a", "192k", str(mp3_yolu)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    gecici_wav.unlink(missing_ok=True)
    return sure


def seslendir(metin: str, mp3_yolu: Path, ses: str = SES) -> float | None:
    """
    Metni Gemini TTS ile seslendir → mp3_yolu. Süre (sn) döner.
    Başarısızsa None döner (çağıran edge-tts'e düşer).
    """
    client = bridge._client()
    son_hata = None
    for deneme in range(3):
        try:
            r = client.models.generate_content(
                model=MODEL,
                contents=STIL + metin,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=ses
                            )
                        )
                    ),
                ),
            )
            pcm = r.candidates[0].content.parts[0].inline_data.data
            if not pcm:
                raise RuntimeError("boş audio")
            return _pcm_to_mp3(pcm, mp3_yolu)
        except Exception as h:
            son_hata = h
            import time
            time.sleep(min(2 ** (deneme + 1), 15))
    print(f"[gemini_tts] başarısız ({son_hata}) → edge-tts'e düşülecek", flush=True)
    return None


if __name__ == "__main__":
    import sys
    metin = sys.argv[1] if len(sys.argv) > 1 else "Merhaba dostum, içindeki sessizliği dinle."
    sure = seslendir(metin, Path("/tmp/gemini_tts_cli.mp3"))
    print(f"süre: {sure}sn → /tmp/gemini_tts_cli.mp3" if sure else "BAŞARISIZ")
