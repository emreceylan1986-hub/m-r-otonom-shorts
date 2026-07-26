# Video Analizi — `q_GwdwSilIA`

> Kaynak: https://www.youtube.com/watch?v=q_GwdwSilIA
> Veriler YouTube Data API v3 üzerinden çekildi (repo'nun kendi OAuth token'ı ile).
> Not: Konuşma transkripti çekilemedi — bu oturumun ağ politikası `youtube.com`
> egress'ini engelliyor (timedtext/caption uçnoktası orada). Metadata, açıklama,
> etiketler ve istatistikler API'den (`youtube.googleapis.com`) tam alındı.

## Künye

| Alan | Değer |
|---|---|
| Başlık | **Tek Prompt ile 50dk Yapay Zeka Animasyon Videosu Yapan Araç Magiclight AI** |
| Kanal | Ülviye Suna |
| Yayın | 2026-01-06 |
| Süre | 17:32 (tanıtılan araç 50 dk'lık video üretiyor) |
| İzlenme | 79.941 |
| Beğeni | 3.834 |
| Yorum | 266 |
| Dil | Türkçe |

## Performans okuması

- **Beğeni/izlenme ≈ %4.8** — referans değerin (genelde %2-4) üzerinde, izleyici
  memnuniyeti yüksek bir tutorial.
- **Yorum/izlenme ≈ %0.33** — eğitim videoları için sağlıklı etkileşim.
- Format **uzun-form tutorial** (17.5 dk), Shorts değil. Bu kanalın modeli:
  araç tanıtımı → izleyiciyi affiliate'e yönlendirme.

## Konu

Tek bir prompt ile **50 dakikalık yapay zeka animasyon videosu** üreten
**Magiclight AI** aracının tanıtımı. Teknik bilgi gerektirmeden:
- Çocuklar için 3D / Pixar tarzı hikaye animasyonları
- Sinematik yetişkin videoları
- Özellikle **dini hikaye / Kuran sureleri hikayeleri** nişi (etiketlerden net)

## Para kazanma modeli (açıklamadan)

Çok katmanlı affiliate + kendi ürünleri:

1. **Ana araç affiliate'i** — Magiclight (`?code=p4jb2noa9`)
2. **Araç yığını affiliate'leri** — OpenArt, Higgsfield, Kling, HeyGen, Invideo, Hera
3. **Kendi eğitimleri** — Shopier mağazası
4. **E-bülten** — Google Forms ile liste toplama (sahip olduğu kitle = en değerli varlık)
5. **Oynatma listeleri** ile kanal içi tutundurma (YT'den para kazanma, ek gelir,
   affiliate marketing, kanal büyütme, AI araçları)

## Etiket / SEO stratejisi

Sadece 3 etiket, hepsi yüksek niyetli Türkçe arama:
- `dini hikaye videoları nasıl yapılır`
- `kuranı kerim surelerinin hikayeleri`
- `yapay zeka animasyon videoları`

Açıklamada İngilizce hashtag'ler (#AnimalStory #BedtimeStories #TextToVideo)
ile uluslararası keşfe de açılmış.

## Çıkarımlar — bu repoya (M-R Otonom Shorts) uygulanabilir dersler

Bu repo şu an İngilizce **tech-haber Shorts** üretiyor (HackerNews/Reddit →
Gemini script → edge-tts → Pexels → YouTube). Videodan transfer edilebilir 5 ders:

1. **Niş + duygusal hikaye, kuru haberden iyi dönüşür.** Videonun başarısı
   "hikaye anlatımı" nişinden geliyor. Repo için: haber Shorts'larına net bir
   hikaye/hook kalıbı eklemek (zaten `hook_predictor.py` ve `viral_patterns.json`
   var — bunları güçlendirmek).

2. **Affiliate katmanı para motoru.** Repo'da `affiliate_link.py` zaten var ama
   bu video, açıklamaya **istiflenmiş çoklu affiliate + kendi ürün + e-bülten**
   yerleşiminin tek videoda nasıl yapıldığının somut şablonu. Açıklama şablonunu
   bu yapıya göre genişletmek değerlendirilebilir.

3. **Az ama yüksek-niyetli etiket.** 3 hedefli "nasıl yapılır" etiketi, 30 genel
   etiketten iyi. `yukleyici.py`/başlık-etiket üretimini "uzun-kuyruk niyet"
   odağına çekmek.

4. **Tutorial/uzun-form, Shorts'u besler.** Bu kanal uzun-form ile otorite +
   affiliate dönüşümü topluyor; Shorts genelde trafik kapısı. Repo'nun salt-Shorts
   modeline ileride bir "uzun-form companion" düşünülebilir (trailer_uret.py'nin
   mantığı buraya uzanabilir).

5. **AI animasyon araç ekosistemi izlenecek.** Magiclight gibi "tek prompt → uzun
   video" araçları, Pexels-stok-klip montajına alternatif bir prodüksiyon yolu.
   `montajci.py`'nin stok-klip yaklaşımına kıyasla maliyet/kalite testi yapılabilir.

## Erişilemeyenler (şeffaflık)

- **Konuşma transkripti:** ağ politikası `youtube.com` egress'ini engelledi.
- **Yorum metinleri:** mevcut OAuth token scope'u (`youtube`) commentThreads
  okuması için yetersiz döndü (403, `force-ssl` gerekiyor).
