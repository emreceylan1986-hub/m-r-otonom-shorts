# mesaj_koprusu — WhatsApp + SMS → telefon push köprüsü

Gelen/giden **WhatsApp** mesajlarını ve gelen **SMS**'leri yakalayıp telefonuna
anlık **push bildirim** (ntfy) olarak iletir. İstersen Gemini ile kısa bir
**"önerilen cevap"** da üretir. Kendi sürekli-açık sunucunda çalışır.

> ⚠️ **WhatsApp ban riski:** Bu, resmi olmayan WhatsApp otomasyonudur (Baileys).
> Meta ToS'una aykırıdır; **numaran yasaklanabilir** (15 Oca 2026 şartları AI
> chatbot'larını açıkça yasaklar). Riski kabul ederek kullanırsın. Mümkünse
> yan/test numarası kullan. — Kullanıcı bu riski açıkça kabul etti.

> ℹ️ **Mahremiyet:** Tüm bunlar SENİN sunucunda, SENİN hesabınla çalışır.
> Hiçbir mesaj bu repoya ya da üçüncü tarafa gitmez; sadece senin ntfy topic'ine.

---

## Gereksinim
- Node.js ≥ 18 olan, **7/24 açık** bir sunucu (VPS / eski telefon+Termux / Raspberry Pi / ev sunucusu).
- Telefonunda **ntfy** uygulaması (App Store / Play Store / F-Droid).

## 1) Telefon: ntfy kur + topic'e abone ol
1. **ntfy** uygulamasını kur.
2. "+" → **Subscribe to topic** → tahmin edilemez bir ad gir
   (örn. `mr-mesaj-emre-9f3k2x`). Bu adı `.env`'deki `NTFY_TOPIC`'e yaz.
   > Topic adı = şifre gibidir; tahmin edilebilir bir şey koyma.

## 2) Sunucu: köprüyü kur
```bash
cd mesaj_koprusu
cp .env.ornek .env        # NTFY_TOPIC'i (ve istersen GEMINI_API_KEY) doldur
npm install
npm start
```
İlk açılışta terminale bir **QR kod** basılır.

## 3) WhatsApp eşleştir
Telefonda: **WhatsApp → Ayarlar → Bağlı Cihazlar → Cihaz Bağla** → terminaldeki
QR'ı okut. Bağlanınca telefonuna "✅ WhatsApp köprüsü bağlı" push'u düşer.
Artık gelen/giden WhatsApp mesajları telefonuna bildirim olarak gelir.
(Oturum `auth_info/` klasöründe saklanır — silersen yeniden QR gerekir.)

## 4) SMS köprüsü (Android)
Telefona bir SMS-forwarder uygulaması kur ve gelen SMS'i sunucuna POST etmesini sağla:
- [android_income_sms_gateway_webhook](https://github.com/bogkonstantin/android_income_sms_gateway_webhook) (en sade)
- [httpsms](https://github.com/NdoleStudio/httpsms) (gönderme de yapar)

Webhook URL'si: `http://SUNUCU_IP:3000/sms`
Gönderdiği JSON `from` + `text` alanları içermeli (uygulamanın şablonunu buna göre ayarla).
İstersen `.env`'de `SMS_WEBHOOK_SECRET` koy ve uygulamadan `secret` alanıyla gönder.

Test:
```bash
curl -X POST http://localhost:3000/sms \
  -H "Content-Type: application/json" \
  -d '{"from":"+9055...","text":"Merhaba, deneme"}'
```

## Sürekli çalıştırma (önerilir)
```bash
npm install -g pm2
pm2 start index.js --name mesaj-koprusu
pm2 save && pm2 startup
```

## Sınırlar (dürüstçe)
- WhatsApp **medya/şifreli aramalar** push edilmez; sadece metin/altyazı.
- Giden mesajların yakalanması cihaz senkronuna bağlıdır (genelde çalışır).
- Bu köprü mesajı **okur ve bildirir**; otomatik cevap **göndermez** (güvenlik).
  Otomatik gönderme istersen ayrı + onaylı bir adım olarak eklenir.
