"""
denetleyici.py — Kod Çalıştırma Sarmalayıcısı

Bir Python dosyasını ÇALIŞTIRMADAN ÖNCE bridge.py üzerinden Gemini'ye
denetletir. ONAY gelmezse çalıştırmaz, raporu yazar.

Kullanım:
    python denetleyici.py haberci.py
    python denetleyici.py haberci.py --max-deneme 5
    python denetleyici.py haberci.py --otomatik-duzelt   # RED + duzeltilmis_kod gelirse dosyayı günceller

Çıkış kodları:
    0 → ONAY ve script başarıyla çalıştı
    1 → Gemini RED verdi (script çalıştırılmadı)
    2 → Script çalıştı ama hata kodu ile bitti
    3 → Sistem hatası (dosya yok, bridge patladı, vs.)
"""

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import bridge


YEDEK_KLASORU = Path(__file__).parent / "yedekler"


def _yedekle(dosya: Path) -> Path:
    YEDEK_KLASORU.mkdir(exist_ok=True)
    damga = datetime.now().strftime("%Y%m%d_%H%M%S")
    yedek = YEDEK_KLASORU / f"{dosya.stem}_{damga}{dosya.suffix}"
    shutil.copy2(dosya, yedek)
    return yedek


def _raporu_yaz(rapor: dict) -> None:
    print("─" * 60)
    print(f"KARAR    : {rapor.get('karar')}")
    print(f"ÖZET     : {rapor.get('ozet')}")
    if rapor.get("hatalar"):
        print("HATALAR  :")
        for h in rapor["hatalar"]:
            print(f"  • {h}")
    if rapor.get("oneriler"):
        print("ÖNERİLER :")
        for o in rapor["oneriler"]:
            print(f"  • {o}")
    print("─" * 60)


def calistir(script_yolu: Path, max_deneme: int, otomatik_duzelt: bool) -> int:
    if not script_yolu.exists():
        print(f"HATA: dosya bulunamadı → {script_yolu}", file=sys.stderr)
        return 3

    kod = script_yolu.read_text(encoding="utf-8")

    print(f"[denetleyici] {script_yolu.name} Gemini'ye gönderiliyor (max {max_deneme} tur)...")
    try:
        onaylandi, son_kod, rapor = bridge.onay_iste(kod, max_deneme=max_deneme)
    except Exception as hata:
        print(f"HATA: bridge çağrısı başarısız → {hata}", file=sys.stderr)
        return 3

    _raporu_yaz(rapor)

    if not onaylandi:
        print("[denetleyici] Gemini ONAY vermedi. Script ÇALIŞTIRILMADI.")
        return 1

    if son_kod != kod:
        if not otomatik_duzelt:
            print(
                "[denetleyici] Gemini düzeltilmiş kod önerdi ama --otomatik-duzelt "
                "kapalı. Yine de ONAY verildiği için ORİJİNAL kod çalıştırılıyor."
            )
        else:
            yedek = _yedekle(script_yolu)
            script_yolu.write_text(son_kod, encoding="utf-8")
            print(f"[denetleyici] Kod güncellendi. Yedek: {yedek.name}")

    print(f"[denetleyici] ONAY ✓  → {script_yolu.name} çalıştırılıyor...")
    print("═" * 60)
    sonuc = subprocess.run([sys.executable, str(script_yolu)])
    print("═" * 60)
    print(f"[denetleyici] Çıkış kodu: {sonuc.returncode}")
    return 0 if sonuc.returncode == 0 else 2


def main() -> int:
    p = argparse.ArgumentParser(description="Gemini denetimli Python çalıştırıcı")
    p.add_argument("script", help="Çalıştırılacak Python dosyasının yolu")
    p.add_argument("--max-deneme", type=int, default=3, help="ONAY için en fazla tur")
    p.add_argument(
        "--otomatik-duzelt",
        action="store_true",
        help="Gemini düzeltilmiş kod önerirse dosyayı yedekleyip günceller",
    )
    args = p.parse_args()
    return calistir(Path(args.script).resolve(), args.max_deneme, args.otomatik_duzelt)


if __name__ == "__main__":
    sys.exit(main())
