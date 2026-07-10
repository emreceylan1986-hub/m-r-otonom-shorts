"""
kanal_config.py — Çok-kanal config kayıt defteri (Faz 22).

Tek pipeline, birden çok YouTube kanalı. Aktif kanal `KANAL` env değişkeniyle
seçilir; ayarlı değilse VARSAYILAN ("trendcatcher") kullanılır → eski davranış
birebir korunur (token.json + TrendCatcher branding).

Yeni kanal eklemek için: KANALLAR sözlüğüne bir giriş ekle + o kanalın
token dosyasını (token_<anahtar>.json) GitHub secret'tan yerleştir.

Kullanım:
    import kanal_config
    cfg = kanal_config.kanal_config()          # aktif kanal (KANAL env)
    cfg = kanal_config.kanal_config("cosmobytes")
    yol = kanal_config.token_yolu()            # PANEL_KOK / token dosyası
"""
import os
from pathlib import Path

PANEL_KOK = Path(__file__).parent
VARSAYILAN = "trendcatcher"

# YouTube kategori ID'leri
KAT_NEWS = "25"      # News & Politics
KAT_TECH = "28"      # Science & Technology
KAT_ANIMALS = "15"   # Pets & Animals


KANALLAR = {
    # -------------------------------------------------------------------
    # TrendCatcher — extreme nature / wildlife niş (mevcut, değerler korundu)
    # -------------------------------------------------------------------
    "trendcatcher": {
        "kanal_adi": "TrendCatcher",
        "handle": "@TrendCatcher",
        "token_dosyasi": "token.json",
        "kategori_id": KAT_ANIMALS,
        "description": (
            "🐐 Daily extreme nature & wildlife shorts that defy belief.\n\n"
            "TrendCatcher brings you the most mind-blowing facts about extreme "
            "animals, anomaly places, and tiny creatures with superpowers — all "
            "in bite-sized 30-60 second Shorts.\n\n"
            "🌍 New wild facts every day at 3 PM, 7 PM, 10 PM and 1 AM (TR).\n"
            "🦅 Designed for the curious mind, the nature lover, the explorer.\n\n"
            "For more wild discoveries → subscribe.\n\n"
            "Business inquiries: emreceylan55555@gmail.com"
        ),
        "keywords": (
            '"nature" "wildlife" "animals" "extreme animals" "science" '
            '"mountain goat" "tardigrade" "blobfish" "mantis shrimp" '
            '"anomaly" "pink lake" "deep sea" "antarctic" "shorts" "wild facts"'
        ),
        "playlists": [
            {
                "title": "Extreme Animals & Superpowers",
                "description": "Animals with unbelievable abilities — climbing cliffs, breaking sound, surviving the impossible. 30-60 sec wild facts.",
                "keywords": ["eagle", "mantis shrimp", "mountain goat", "cone snail", "jumping spider",
                             "pangolin", "shrimp", "ibex", "markhor", "weaver bird", "octopus",
                             "vampire squid", "secretarybird", "raptor"],
            },
            {
                "title": "Anomaly Places & Wonders",
                "description": "Lakes that boil, valleys with no rain, ice that thrives in heat — Earth's strangest places explained.",
                "keywords": ["lake", "antarctic", "ocean", "deep sea", "valley", "cave",
                             "boiling", "pink", "salt", "freshwater", "glacier", "vent",
                             "baikal", "hillier", "dead sea"],
            },
            {
                "title": "Tiny Creatures, Big Survival",
                "description": "Microbes, fungi, parasites, tardigrades — the smallest survivors with the wildest tricks.",
                "keywords": ["tardigrade", "microbe", "fungus", "midge", "ant", "frog",
                             "naked mole-rat", "cavefish", "ice worm", "massospora",
                             "zombie", "tube worm", "extremophile"],
            },
        ],
        "cta_sonek": (
            "\n\n━━━━━━━━━━━━━━━━━━━━\n"
            "🌍 Subscribe for daily wild facts:\n"
            "https://youtube.com/@TrendCatcher?sub_confirmation=1\n\n"
            "🎬 More extreme nature shorts:\n"
            "• Extreme Animals: https://www.youtube.com/playlist?list=PLnsj6ktxididsCSk4MCXcjLanaNsm5Rh7\n"
            "• Anomaly Places: https://www.youtube.com/playlist?list=PLnsj6ktxidifsZko8kPFAEjC0ZZwOvDMd\n"
            "• Tiny Creatures: https://www.youtube.com/playlist?list=PLnsj6ktxidifHQ4dGHE9AcFVNwZOjF4ko"
        ),
    },

    # -------------------------------------------------------------------
    # CosmoBytes — astronomy / cosmos niş (@cosmobytess)
    # Token hazır olunca: token_cosmobytes.json yerleştir + KANAL=cosmobytes
    # Playlist URL'leri kanal_setup.py çalıştıktan SONRA cta_sonek'e eklenebilir.
    # -------------------------------------------------------------------
    "cosmobytes": {
        "kanal_adi": "CosmoBytes",
        "handle": "@cosmobytess",
        "token_dosyasi": "token_cosmobytes.json",
        "kategori_id": KAT_TECH,
        "description": (
            "🌌 Daily astronomy & cosmic wonder shorts in 30 seconds.\n\n"
            "CosmoBytes brings you the most mind-blowing facts about black holes, "
            "galaxies, exoplanets, neutron stars, and the strange physics of the "
            "cosmos — all in bite-sized Shorts.\n\n"
            "🔭 New cosmic facts every day.\n"
            "🌠 For the curious mind, the stargazer, the science lover.\n\n"
            "For more cosmic discoveries → subscribe.\n\n"
            "Business inquiries: emreceylan55555@gmail.com"
        ),
        "keywords": (
            '"astronomy" "space" "cosmos" "universe" "black hole" "neutron star" '
            '"galaxy" "exoplanet" "nebula" "supernova" "pulsar" "dark matter" '
            '"milky way" "shorts" "space facts"'
        ),
        "playlists": [
            {
                "title": "Black Holes & Extreme Objects",
                "description": "Black holes, neutron stars, magnetars, quasars — the most extreme objects in the universe explained in 30 seconds.",
                "keywords": ["black hole", "neutron star", "pulsar", "magnetar", "quasar",
                             "supernova", "white dwarf", "event horizon", "singularity",
                             "gamma ray", "kilonova", "blazar"],
            },
            {
                "title": "Galaxies & Deep Space",
                "description": "Galaxies, nebulae, dark matter and the large-scale structure of the cosmos — the universe at its grandest.",
                "keywords": ["galaxy", "nebula", "milky way", "andromeda", "dark matter",
                             "dark energy", "cosmic web", "star cluster", "supernova remnant",
                             "cosmic", "redshift", "big bang"],
            },
            {
                "title": "Planets & Exoplanets",
                "description": "Exoplanets, gas giants, rogue worlds and the search for life — strange planets near and far.",
                "keywords": ["exoplanet", "planet", "mars", "jupiter", "saturn", "venus",
                             "moon", "habitable", "super-earth", "gas giant", "rogue planet",
                             "solar system"],
            },
        ],
        "cta_sonek": (
            "\n\n━━━━━━━━━━━━━━━━━━━━\n"
            "🌌 Subscribe for daily cosmic facts:\n"
            "https://youtube.com/@cosmobytess?sub_confirmation=1"
        ),
    },
}


def aktif_anahtar() -> str:
    """KANAL env değişkeninden aktif kanal anahtarı (küçük harf). Yoksa VARSAYILAN."""
    a = os.environ.get("KANAL", "").strip().lower()
    return a if a in KANALLAR else VARSAYILAN


def kanal_config(anahtar: str | None = None) -> dict:
    """Verilen (ya da aktif) kanalın config sözlüğü."""
    anahtar = (anahtar or aktif_anahtar()).strip().lower()
    if anahtar not in KANALLAR:
        raise KeyError(f"Bilinmeyen kanal: {anahtar!r}. Geçerli: {list(KANALLAR)}")
    return KANALLAR[anahtar]


def token_yolu(anahtar: str | None = None) -> Path:
    """Aktif kanalın token dosyasının tam yolu (PANEL_KOK altında)."""
    return PANEL_KOK / kanal_config(anahtar)["token_dosyasi"]


if __name__ == "__main__":
    import json as _json
    a = aktif_anahtar()
    cfg = kanal_config(a)
    print(f"Aktif kanal: {a} ({cfg['kanal_adi']}, {cfg['handle']})")
    print(f"Token dosyası: {token_yolu(a)}")
    print(f"Kategori: {cfg['kategori_id']} | Playlist sayısı: {len(cfg['playlists'])}")
    print(f"Tüm kanallar: {list(KANALLAR)}")
