"""
pattern_detector.py — Viral video pattern öğrenici.

Tüm yayınları izlenmeye göre bucketle (viral/orta/dip), her bucket için ortak
keyword + başlık şablonu + uzunluk + kategori istatistiği çıkar.

Çıktı: viral_patterns.json — seslendirici + yukleyici prompt'larında kullanılır.

Kullanım:
    python pattern_detector.py [--esik 500]
"""
import argparse, json, re
from collections import Counter
from pathlib import Path
from datetime import datetime

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

PANEL_KOK = Path(__file__).parent
TOKEN = PANEL_KOK / "token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube"]
CIKTI = PANEL_KOK / "viral_patterns.json"

# İngilizce stopword — analizi gürültüden temizler
STOPWORDS = set("""a an the of in on at to for from with by and or but it is are was
were be been being has have had do does did this that these those i you we they
he she his her their our its as not no yes if then so than which what who whose
when where why how can will would could should may might must shall about into
over under between among up down out off across after before above below behind
through during without within against own""".split())


def kelime_cikar(metin: str) -> list[str]:
    return [w for w in re.findall(r"[A-Za-z]{3,}", metin.lower()) if w not in STOPWORDS]


def yt_istemci():
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds.expired and creds.refresh_token: creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--esik", type=int, default=500,
                   help="Viral eşiği (izlenme). Üstü viral, altı orta/dip.")
    args = p.parse_args()

    yj = json.loads((PANEL_KOK / "yuklemeler.json").read_text())
    yt = yt_istemci()
    ids = [v["video_id"] for v in yj if v.get("video_id")]

    # Stats çek (50'şer)
    print(f"[pattern] {len(ids)} video stats çekiliyor...")
    stats = {}
    for i in range(0, len(ids), 50):
        r = yt.videos().list(part="statistics,snippet,status", id=",".join(ids[i:i+50])).execute()
        for it in r.get("items", []):
            stats[it["id"]] = {
                "views": int(it["statistics"].get("viewCount", 0)),
                "likes": int(it["statistics"].get("likeCount", 0)),
                "comments": int(it["statistics"].get("commentCount", 0)),
                "title": it["snippet"]["title"],
                "tags": it["snippet"].get("tags", []),
                "privacy": it["status"]["privacyStatus"],
            }

    public = {k: v for k, v in stats.items() if v["privacy"] == "public"}
    print(f"[pattern] Public: {len(public)} video")

    viral = {k: v for k, v in public.items() if v["views"] >= args.esik}
    orta  = {k: v for k, v in public.items() if 50 <= v["views"] < args.esik}
    dip   = {k: v for k, v in public.items() if v["views"] < 50}

    print(f"[pattern] Viral (>={args.esik}): {len(viral)} | Orta: {len(orta)} | Dip: {len(dip)}")

    def kovacik_analiz(kova: dict, ad: str) -> dict:
        if not kova: return {"video_sayisi": 0}
        baslik_kelimeleri = Counter()
        tag_kelimeleri = Counter()
        baslik_uzunluklari = []
        for v in kova.values():
            baslik_kelimeleri.update(kelime_cikar(v["title"]))
            tag_kelimeleri.update([t.lower() for t in v["tags"]])
            baslik_uzunluklari.append(len(v["title"]))
        ort_uz = sum(baslik_uzunluklari) / len(baslik_uzunluklari) if baslik_uzunluklari else 0
        return {
            "video_sayisi": len(kova),
            "ortalama_izlenme": sum(v["views"] for v in kova.values()) / len(kova),
            "ortalama_baslik_uzunluk": round(ort_uz, 1),
            "top_kelimeler": baslik_kelimeleri.most_common(20),
            "top_tagler": tag_kelimeleri.most_common(15),
            "ornek_basliklar": [v["title"] for v in sorted(kova.values(), key=lambda x: -x["views"])[:5]],
        }

    rapor = {
        "uretim": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "esik_izlenme": args.esik,
        "viral": kovacik_analiz(viral, "VIRAL"),
        "orta": kovacik_analiz(orta, "ORTA"),
        "dip": kovacik_analiz(dip, "DIP"),
    }

    # VIRAL ÜZERİNDE OLAN KELİMELER (dip'te az olan ama viral'de çok olan)
    if viral and dip:
        viral_w = dict(rapor["viral"]["top_kelimeler"])
        dip_w = dict(rapor["dip"]["top_kelimeler"])
        ozel_viral = []
        for w, cnt in viral_w.items():
            dip_cnt = dip_w.get(w, 0)
            # Viral'de >= 2 görünmüş AND dip'te <= 1 görünmüş
            if cnt >= 2 and dip_cnt <= 1:
                ozel_viral.append((w, cnt, dip_cnt))
        ozel_viral.sort(key=lambda x: -x[1])
        rapor["viral_ozel_kelimeler"] = ozel_viral[:15]

    CIKTI.write_text(json.dumps(rapor, ensure_ascii=False, indent=2))
    print(f"[pattern] Yazıldı: {CIKTI}")

    # Konsol özet
    print(f"\n  🏆 VİRAL ÖZEL KELİMELER (viral'de çok, dip'te az):")
    for w, vc, dc in rapor.get("viral_ozel_kelimeler", [])[:10]:
        print(f"    {w:>15}  viral={vc}  dip={dc}")
    print(f"\n  🏆 VIRAL TOP 5 BAŞLIK:")
    for t in rapor["viral"].get("ornek_basliklar", [])[:5]:
        print(f"    - {t}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
