"""
affiliate_link.py — Açıklama Affiliate Link Otomasyonu (Faz 5).

YouTube açıklamasına konuyla ilgili affiliate link otomatik ekler. YPP
eşiğinden BAĞIMSIZ gelir — affiliate satışları AdSense'den önce başlar.

Stratejiler:
  1) Amazon Associates US (TR'den signup yapılabilir, Payoneer ile ödeme)
  2) AliExpress Affiliate (TR'den OK)
  3) ShareASale (geniş kategori)
  4) Hostinger / NordVPN / digital tool affiliate'leri

Aktif olması için env'de ilgili affiliate tag/code'lar olmalı:
    AMAZON_ASSOCIATES_TAG=trendcatcher-20
    ALIEXPRESS_AFF_KEY=xxx
    EXTRA_AFFILIATE_LINES="📷 Binoculars: https://amzn.to/xx||📚 Guide: https://..."

Faz 21.7 — "İstiflenmiş affiliate" dersi (q_GwdwSilIA video analizi): yüksek
dönüşümlü kanallar tek değil, niş-içi BİRDEN FAZLA hazır affiliate linki istifler.
EXTRA_AFFILIATE_LINES ile creator kendi hazır linklerini '||' ayracıyla istifler.

NOT: Hiç tag yoksa açıklamaya hiçbir şey eklenmez — güvenli no-op.

Kullanım (modül olarak):
    from affiliate_link import aciklama_zenginleştir
    yeni_aciklama = aciklama_zenginleştir(eski_aciklama, baslik, anahtar_kelimeler)
"""
import os
from pathlib import Path


PANEL_KOK = Path(__file__).parent

# Niş — hayvan/doğa — anahtar kelime → product arama eşlemesi
NIS_PRODUCT_HARITASI = {
    "lake": "books about lakes nature",
    "frog": "frog identification guide book",
    "octopus": "octopus aquarium book",
    "bird": "bird watching binoculars",
    "ocean": "ocean documentary 4k",
    "fungus": "mushroom identification guide",
    "antarctica": "antarctica book photography",
    "penguin": "penguin documentary blu-ray",
    "dolphin": "dolphin field guide",
    "spider": "spider field guide",
    "wildlife": "wildlife photography book",
    "nature": "national geographic book",
    "snake": "reptile field guide",
    "shark": "shark documentary",
}


def _env(key: str) -> str | None:
    """Env veya .env'den ham bir değer oku."""
    v = os.environ.get(key)
    if v: return v
    envf = PANEL_KOK / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    return None


def _aff_tag(servis: str) -> str | None:
    """Env veya .env'den affiliate code oku."""
    key = {
        "amazon": "AMAZON_ASSOCIATES_TAG",
        "aliexpress": "ALIEXPRESS_AFF_KEY",
    }.get(servis)
    if not key: return None
    return _env(key)


def _ek_affiliate_satirlari() -> list[str]:
    """Faz 21.7 — 'İstiflenmiş affiliate' dersi (q_GwdwSilIA analizi).

    Yüksek dönüşümlü kanallar açıklamaya TEK link değil, niş-içi BİRDEN FAZLA
    hazır affiliate linki istifler. Burada URL şeması uydurmuyoruz: creator
    önceden ürettiği tam linkleri env'e koyar, biz aynen ekleriz.

    EXTRA_AFFILIATE_LINES formatı (her satır bir link, '||' ile ayrılır):
        "📷 Field binoculars: https://amzn.to/xxx||📚 Nature guide: https://..."
    Hiç tanımlı değilse boş döner (güvenli no-op)."""
    ham = _env("EXTRA_AFFILIATE_LINES")
    if not ham:
        return []
    return [s.strip() for s in ham.split("||") if s.strip()]


def en_uygun_keyword(baslik: str, tags: list[str]) -> str | None:
    """Başlık + tag'lardan en uygun keyword bul."""
    metin = (baslik + " " + " ".join(tags or [])).lower()
    for keyword in NIS_PRODUCT_HARITASI:
        if keyword in metin:
            return keyword
    return None


def amazon_link(keyword: str, tag: str) -> str:
    """Amazon US arama URL'si + affiliate tag."""
    import urllib.parse
    q = urllib.parse.quote_plus(NIS_PRODUCT_HARITASI[keyword])
    return f"https://www.amazon.com/s?k={q}&tag={tag}"


def aciklama_zenginleştir(aciklama: str, baslik: str, tags: list[str] = None) -> str:
    """Açıklamaya konuyla ilgili affiliate link bloğu ekle. Aktif tag yoksa
    no-op (güvenli)."""
    tags = tags or []
    blok_satirlari = []

    # 1) Konuya göre eşleşen Amazon arama linki (mevcut davranış)
    keyword = en_uygun_keyword(baslik, tags)
    amazon_tag = _aff_tag("amazon")
    if keyword and amazon_tag:
        blok_satirlari.append(f"📖 Related read: {amazon_link(keyword, amazon_tag)}")

    # 2) İstiflenmiş ek affiliate linkleri (env'de hazır verilmişse)
    blok_satirlari.extend(_ek_affiliate_satirlari())

    if not blok_satirlari:
        return aciklama

    dipnot = "\n(As an Amazon Associate, we earn from qualifying purchases.)" if amazon_tag and keyword else "\n(Some links are affiliate links — we may earn a commission.)"
    blok = "\n\n--\n" + "\n".join(blok_satirlari) + dipnot
    return aciklama.rstrip() + blok


if __name__ == "__main__":
    # Self test
    test = aciklama_zenginleştir(
        "Glass sponges live for 15000 years.",
        "Glass Sponges Live for 15,000 Years in the Deep Ocean",
        ["nature", "ocean", "biology"],
    )
    print(test)
