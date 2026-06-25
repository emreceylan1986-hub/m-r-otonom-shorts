"""
kalite_temizleyici.py — Bad Performer Auto-Private (Faz 7 + 25 Haz GÜVENLİK).

7g+ eski + <50 izlenme + <2 beğeni olan public videoları PRIVATE'a alır.
Sebep: YouTube algoritması düşük-performans oranı kanal puanını düşürür.

═══ GÜVENLİK KATMANI (25 Haz, Emre talimatı "temelli çöz") ═══
1) MAX_PER_RUN = 5  → tek çalıştırmada en fazla 5 video silinir, fazla aday varsa
   listeyi raporlar + DUR (sürpriz toplu silme imkansız)
2) temizleyici_log.json → her silme kayıt (id+başlık+zaman), geri alınabilir
3) --geri-al N → son N silme'yi public'e döndürür
4) --gercek flag ZORUNLU → flag yoksa hep kuru mod (workflow accident-proof)

Kullanım:
    python3 kalite_temizleyici.py                     # KURU (rapor)
    python3 kalite_temizleyici.py --gercek            # max 5 silme
    python3 kalite_temizleyici.py --gercek --tavan 10 # max 10 (manuel onay)
    python3 kalite_temizleyici.py --geri-al 36        # son 36 silmeyi geri aç
    python3 kalite_temizleyici.py --geri-al-hepsini   # tüm logdaki silmeleri geri aç
"""
import argparse, json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

PANEL_KOK = Path(__file__).parent
TOKEN = PANEL_KOK / "token.json"
LOG = PANEL_KOK / "kalite_temizleyici.log"
SILINENLER_LOG = PANEL_KOK / "temizleyici_log.json"  # geri-alma defteri
MAX_PER_RUN_VARSAYILAN = 5


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    satir = f"[{ts}] {msg}"
    print(satir)
    try:
        LOG.write_text((LOG.read_text() if LOG.exists() else "") + satir + "\n")
    except Exception:
        pass


def yt_istemci():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    SCOPES = ["https://www.googleapis.com/auth/youtube",
              "https://www.googleapis.com/auth/youtube.force-ssl"]
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def silinenleri_oku() -> list:
    if not SILINENLER_LOG.exists():
        return []
    try:
        return json.loads(SILINENLER_LOG.read_text())
    except Exception:
        return []


def silinenleri_yaz(liste: list):
    SILINENLER_LOG.write_text(json.dumps(liste, ensure_ascii=False, indent=2))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--gercek", action="store_true",
                   help="GERÇEK silme (yoksa otomatik kuru mod — güvenlik)")
    p.add_argument("--tavan", type=int, default=MAX_PER_RUN_VARSAYILAN,
                   help=f"Tek run'da max silme sayısı (varsayılan {MAX_PER_RUN_VARSAYILAN})")
    p.add_argument("--min-yas-saat", type=int, default=168)
    p.add_argument("--min-izlenme", type=int, default=50)
    p.add_argument("--min-begeni", type=int, default=2)
    p.add_argument("--geri-al", type=int, default=0,
                   help="Son N silinen videoyu geri aç (public yap)")
    p.add_argument("--geri-al-hepsini", action="store_true",
                   help="Logdaki TÜM silmeleri geri aç")
    args = p.parse_args()

    yt = yt_istemci()
    silinenler = silinenleri_oku()

    # ─── GERİ ALMA MODU ──────────────────────────────────────────
    if args.geri_al or args.geri_al_hepsini:
        if args.geri_al_hepsini:
            hedef = silinenler[:]
        else:
            hedef = silinenler[-args.geri_al:]
        log(f"=== GERİ ALMA: {len(hedef)} video public'e dönecek ===")
        basarili = []
        for kayit in hedef:
            try:
                yt.videos().update(part="status", body={
                    "id": kayit["id"], "status": {"privacyStatus": "public"}
                }).execute()
                log(f"  ✓ public ← {kayit.get('title','?')[:50]}")
                basarili.append(kayit)
            except Exception as h:
                log(f"  ✗ {kayit['id']}: {str(h)[:120]}")
        # Geri alınanları logdan çıkar
        kalanlar = [k for k in silinenler if k not in basarili]
        silinenleri_yaz(kalanlar)
        log(f"=== Geri alma bitti: {len(basarili)}/{len(hedef)} ===")
        return 0

    # ─── KURU/GERÇEK MOD ─────────────────────────────────────────
    kuru = not args.gercek
    tavan = args.tavan

    yj_yolu = PANEL_KOK / "yuklemeler.json"
    if not yj_yolu.exists():
        log("yuklemeler.json yok"); return 0
    yj = json.loads(yj_yolu.read_text())

    log(f"=== Kalite temizleyici başladı (mod={'KURU' if kuru else 'GERÇEK'}, tavan={tavan}) ===")

    aday_ids = [v["video_id"] for v in yj
                if v.get("gizlilik") == "public"
                and v.get("denetim_karari") == "UYGUN"]
    log(f"Pipeline public video aday sayısı: {len(aday_ids)}")
    if not aday_ids:
        log("Aday yok"); return 0

    now = datetime.now(timezone.utc)
    silinmeyecekler = []
    for i in range(0, len(aday_ids), 50):
        chunk = aday_ids[i:i+50]
        r = yt.videos().list(part="statistics,snippet,status", id=",".join(chunk)).execute()
        for it in r.get("items", []):
            try:
                pub = datetime.fromisoformat(it["snippet"]["publishedAt"].replace("Z","+00:00"))
                yas_saat = (now - pub).total_seconds() / 3600
                izl = int(it["statistics"].get("viewCount", 0))
                begeni = int(it["statistics"].get("likeCount", 0))

                if yas_saat < args.min_yas_saat: continue
                if it["status"]["privacyStatus"] != "public": continue
                if izl >= args.min_izlenme: continue
                if begeni >= args.min_begeni: continue

                silinmeyecekler.append({
                    "id": it["id"],
                    "title": it["snippet"]["title"][:80],
                    "yas_saat": round(yas_saat, 1),
                    "izl": izl, "begeni": begeni,
                })
            except Exception as h:
                log(f"  parse hata {it.get('id')}: {h}")

    silinmeyecekler.sort(key=lambda v: v["izl"])  # önce en az izlenen
    log(f"TESPİT: {len(silinmeyecekler)} video kriteri karşılıyor")

    # ─── GÜVENLIK TAVAN ──────────────────────────────────────────
    if len(silinmeyecekler) > tavan:
        log(f"⚠️  TAVAN AŞILDI ({len(silinmeyecekler)} > {tavan}) — sadece ilk {tavan} işlenecek")
        log(f"⚠️  Tüm listeyi --tavan {len(silinmeyecekler)} ile yeniden çalıştır + onay ver")
        silinmeyecekler = silinmeyecekler[:tavan]

    if kuru:
        log("[KURU MOD] Aşağıdaki videolar GERÇEK çalıştırıldığında silinecek (henüz silinmedi):")
        for v in silinmeyecekler:
            log(f"  [{v['yas_saat']:.0f}h] {v['izl']}izl {v['begeni']}👍 → {v['title']}")
        log(f"=== KURU bitti — {len(silinmeyecekler)} video silinme adayı. Silmek için --gercek ekle. ===")
        return 0

    # ─── GERÇEK SİLME ────────────────────────────────────────────
    log(f"GERÇEK silme başlıyor: {len(silinmeyecekler)} video private'a")
    yeni_silinenler = []
    for v in silinmeyecekler:
        log(f"  [{v['yas_saat']:.0f}h] {v['izl']}izl {v['begeni']}👍 → {v['title']}")
        try:
            yt.videos().update(part="status", body={
                "id": v["id"], "status": {"privacyStatus": "private"}
            }).execute()
            log(f"    ✓ PRIVATE")
            yeni_silinenler.append({
                "id": v["id"],
                "title": v["title"],
                "izl": v["izl"], "begeni": v["begeni"], "yas_saat": v["yas_saat"],
                "ts": now.isoformat(timespec="seconds"),
            })
        except Exception as h:
            log(f"    ✗ {str(h)[:140]}")

    # Geri-alma defterine yaz
    silinenler.extend(yeni_silinenler)
    silinenleri_yaz(silinenler)
    log(f"=== Bitti — {len(yeni_silinenler)} video private, defter: {SILINENLER_LOG.name} ({len(silinenler)} toplam) ===")
    log(f"=== Geri al: python3 kalite_temizleyici.py --geri-al {len(yeni_silinenler)} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
