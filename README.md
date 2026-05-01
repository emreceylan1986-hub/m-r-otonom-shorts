# M-R Otonom Shorts Pipeline

YouTube Shorts üretim hattı: haber çekme → senaryo + seslendirme → stok video montajı → YouTube'a yükleme. Her halka kendi kodunu çalıştırmadan önce **Gemini 2.5 Flash** denetiminden geçer; metin çıktıları (senaryo, başlık, açıklama) ayrıca içerik denetimine sunulur.

## Akış

```
haberci.py    → HackerNews + Reddit r/technology, son 24 saat top 3 → haberler.json
seslendirici.py → Gemini script + edge-tts (en-US-AriaNeural)        → ses_ciktilari/*.mp3
montajci.py   → Pexels portrait klipler + ffmpeg                     → shorts_ciktilari/*.mp4
yukleyici.py  → OAuth + YouTube Data API v3, default privacyStatus=private → yuklemeler.json
```

`bridge.py` Gemini köprüsü (kod denetimi + metin denetimi + JSON kurtarıcı parser).
`denetleyici.py` herhangi bir scripti onay-sarmalı çalıştırma aracı (CI'da kullanılmaz, geliştirme aşamasında).

## Bulut çalıştırma — GitHub Actions

`.github/workflows/main.yml` günde 2 kez (TR 19:00 + 22:00 → cron `0 16,19 * * *` UTC) çalışır. Manuel tetikleme için:

```
Actions → M-R Otonom Pipeline → Run workflow → gizlilik seç → Run
```

### Gerekli Secrets (Settings → Secrets and variables → Actions)

| Secret | İçerik |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio API key |
| `PEXELS_API_KEY` | Pexels API key |
| `CLIENT_SECRET_JSON` | Google Cloud OAuth Desktop client JSON (raw) |
| `TOKEN_JSON` | İlk auth sonrası üretilen `token.json` (raw) |

## Lokal çalıştırma

```bash
pip install -r requirements.txt
cp .env.ornek .env  # GEMINI_API_KEY + PEXELS_API_KEY doldur
# client_secret.json + token.json buraya kopyala (token.json ilk OAuth sonrası üretilir)
python haberci.py
python seslendirici.py
python montajci.py
python yukleyici.py --gizlilik private
```

## Kotalar

- **YouTube Data API v3:** 10 000 unit/gün, 1 upload ≈ 1 600 unit → günde maks 6 yükleme
- **Pexels:** 200 istek/saat, 20 000/ay
- **Gemini 2.5 Flash:** ücretli plan, pratik sınır yok
- **edge-tts:** Microsoft Edge TTS uçnoktası (ücretsiz, soft-rate)
