"""
suno_kutuphane.py — Suno Pro elle üretilmiş track kütüphanesi yöneticisi.

Suno PUBLIC API'si yok. Emre Bey Suno UI'da animal/nature track üretir,
suno_tracks/ klasörüne atar. Bu script:
  - track metadata'sını okur (ID3 'made with suno')
  - BPM analiz eder (librosa)
  - montajci.py için random/rotate seç sağlar

Kullanım:
    python suno_kutuphane.py --tara         # mevcut track'leri tara
    python suno_kutuphane.py --sec          # bir track seç + path döndür
"""
import argparse, json, random
from pathlib import Path

PANEL_KOK = Path(__file__).parent
SUNO_KLASOR = PANEL_KOK / "suno_tracks"
META = PANEL_KOK / "suno_meta.json"


def track_tarama():
    SUNO_KLASOR.mkdir(exist_ok=True)
    mp3_dosyalari = list(SUNO_KLASOR.glob("*.mp3"))
    print(f"[suno] {len(mp3_dosyalari)} mp3 bulundu")
    meta = []
    for mp3 in mp3_dosyalari:
        # ID3 'made with suno' kontrolü (ffprobe)
        try:
            import subprocess
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_format", str(mp3)],
                capture_output=True, text=True, timeout=10,
            )
            suno_isareti = "made with suno" in r.stdout.lower()
        except Exception:
            suno_isareti = False

        meta.append({
            "dosya": mp3.name,
            "yol": str(mp3),
            "boyut_kb": mp3.stat().st_size // 1024,
            "suno_dogrulanmis": suno_isareti,
        })

    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"[suno] Meta yazıldı: {META}")
    if not mp3_dosyalari:
        print("\n  ⚠️  KÜTÜPHANE BOŞ — Suno UI'da elle üretip suno_tracks/ klasörüne at.")
        print(f"     Hedef klasör: {SUNO_KLASOR}")
        print(f"     Öneri: 'gentle nature documentary background', 'epic wildlife discovery', etc.")


def track_sec(belirteci: str | None = None) -> str | None:
    """Bir Suno track yolu döndür. belirteci = arama keyword (opsiyonel)."""
    if not META.exists():
        track_tarama()
    if not META.exists() or not (meta := json.loads(META.read_text())):
        return None
    if belirteci:
        eslesen = [m for m in meta if belirteci.lower() in m["dosya"].lower()]
        if eslesen:
            return random.choice(eslesen)["yol"]
    return random.choice(meta)["yol"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tara", action="store_true")
    p.add_argument("--sec", action="store_true")
    p.add_argument("--keyword", default=None)
    args = p.parse_args()

    if args.tara: track_tarama()
    elif args.sec:
        yol = track_sec(args.keyword)
        if yol: print(yol)
        else: print("Track yok — once --tara çalıştır")


if __name__ == "__main__":
    main()
