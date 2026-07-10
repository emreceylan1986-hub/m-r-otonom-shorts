#!/usr/bin/env python3
"""
telefon_bildirim.py — Telefona anlık push bildirim (ntfy) (Faz 23).

Pipeline olaylarını (başarılı yayın / hata / günlük özet) telefona PUSH atar.
Kanal: ntfy.sh — hesap GEREKTİRMEZ. Telefonda 'ntfy' uygulamasını kur, bir
topic'e abone ol, o topic adını NTFY_TOPIC secret'ına koy.

Env:
    NTFY_TOPIC   = abone olduğun topic adı (örn. "mr-otonom-emre-9f3k")
    NTFY_SERVER  = sunucu (varsayılan https://ntfy.sh)
    NTFY_TOKEN   = (opsiyonel) korumalı topic için erişim token'ı

NTFY_TOPIC yoksa → hiçbir şey yapmaz (güvenli no-op).

Kullanım:
    from telefon_bildirim import bildir
    bildir("Başlık", "mesaj gövdesi", oncelik="high", etiketler=["warning"], link="https://...")

CLI:
    python telefon_bildirim.py --baslik "Test" --mesaj "merhaba"
    python telefon_bildirim.py --durum success      # yuklemeler.json'dan son video
    python telefon_bildirim.py --durum failure
    python telefon_bildirim.py --ozet               # ypp_status.json günlük özet
"""
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

PANEL_KOK = Path(__file__).parent


def _env(key: str, vars=None) -> str | None:
    v = os.environ.get(key)
    if v:
        return v.strip()
    envf = PANEL_KOK / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    return None


def bildir(baslik: str, mesaj: str, oncelik: str = "default",
           etiketler: list[str] | None = None, link: str | None = None) -> bool:
    """Telefona ntfy push atar. NTFY_TOPIC yoksa no-op (False döner)."""
    topic = _env("NTFY_TOPIC")
    if not topic:
        print("[telefon_bildirim] NTFY_TOPIC yok → no-op (bildirim atlandı)")
        return True  # yapılandırılmamış = güvenli atlama, hata değil
    server = (_env("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
    url = f"{server}/{topic}"

    headers = {
        "Title": baslik.encode("utf-8"),
        "Priority": oncelik,  # max, high, default, low, min
    }
    if etiketler:
        headers["Tags"] = ",".join(etiketler)
    if link:
        headers["Click"] = link
    token = _env("NTFY_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        req = urllib.request.Request(url, data=mesaj.encode("utf-8"), headers=headers, method="POST")
        urllib.request.urlopen(req, timeout=15)
        print(f"[telefon_bildirim] push gönderildi → {server}/{topic}")
        return True
    except Exception as e:
        print(f"[telefon_bildirim] push BAŞARISIZ: {type(e).__name__}: {str(e)[:160]}")
        return False


def _son_video() -> dict | None:
    try:
        d = json.loads((PANEL_KOK / "yuklemeler.json").read_text(encoding="utf-8"))
        return d[-1] if isinstance(d, list) and d else None
    except Exception:
        return None


def _ypp() -> dict | None:
    try:
        return json.loads((PANEL_KOK / "ypp_status.json").read_text(encoding="utf-8"))
    except Exception:
        return None


def durum_bildir(durum: str) -> bool:
    """Pipeline sonucuna göre hazır bildirim (workflow'dan çağrılır)."""
    durum = (durum or "").lower()
    if durum == "success":
        v = _son_video()
        if v:
            return bildir(
                f"✅ Yeni video yayında",
                f"{v.get('title', '(başlık yok)')}\nGizlilik: {v.get('gizlilik', '?')}",
                oncelik="default", etiketler=["white_check_mark"],
                link=v.get("watch_url"),
            )
        return bildir("✅ Pipeline tamam", "Çalışma başarılı.", etiketler=["white_check_mark"])
    elif durum == "failure":
        return bildir(
            "🚨 Pipeline FAIL",
            "Otomatik çalışma başarısız oldu. GitHub Actions run'ını kontrol et.",
            oncelik="high", etiketler=["rotating_light"],
        )
    else:
        return bildir("ℹ️ Pipeline", f"Durum: {durum}", etiketler=["information_source"])


def ozet_bildir() -> bool:
    """Günlük kanal özeti push'u (ypp_status.json'dan)."""
    y = _ypp()
    if not y:
        return bildir("📊 Kanal özeti", "Veri bulunamadı (ypp_status.json yok).")
    et = y.get("early_tier", {})
    mesaj = (
        f"Abone: {y.get('abone', '?')}  ·  Video: {y.get('toplam_video', '?')}\n"
        f"Toplam izlenme: {y.get('toplam_izlenme_yaşam_boyu', y.get('toplam_izlenme', '?'))}\n"
        f"Son 14g: {y.get('son_14g_izlenme', '?')}  ·  günlük ~{round(y.get('gunluk_izlenme_tahmin', 0))}\n"
        f"YPP abone: %{et.get('abone_yuzde', '?')}  (kalan {et.get('abone_kalan', '?')})"
    )
    return bildir(f"📊 {y.get('kanal', 'Kanal')} günlük özet", mesaj, etiketler=["bar_chart"])


def main() -> int:
    p = argparse.ArgumentParser(description="Telefona ntfy push bildirim")
    p.add_argument("--baslik")
    p.add_argument("--mesaj")
    p.add_argument("--oncelik", default="default", choices=["max", "high", "default", "low", "min"])
    p.add_argument("--etiket", action="append", default=[])
    p.add_argument("--link")
    p.add_argument("--durum", help="success | failure (workflow için)")
    p.add_argument("--ozet", action="store_true", help="Günlük kanal özeti gönder")
    a = p.parse_args()

    if a.ozet:
        ok = ozet_bildir()
    elif a.durum:
        ok = durum_bildir(a.durum)
    elif a.baslik and a.mesaj:
        ok = bildir(a.baslik, a.mesaj, a.oncelik, a.etiket or None, a.link)
    else:
        p.error("--baslik+--mesaj veya --durum veya --ozet gerekli")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
