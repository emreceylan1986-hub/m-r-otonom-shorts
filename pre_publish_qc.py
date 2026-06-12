"""
pre_publish_qc.py — Yayın Öncesi Kalite Kontrolü (Faz 7).

Video upload edilmeden ÖNCE çağrılır:
  1) ffmpeg ile final mp4'ün 1. saniyesinden frame al
  2) Gemini Vision'a sor: "Bu hook çekici mi? Konu net mi?" (skor 0-10)
  3) Skor <5 ise UYARI flag — workflow private upload + denetim mail tetikler

Kullanım (modül):
    from pre_publish_qc import hook_qc
    skor, sebep = hook_qc(mp4_yolu, baslik, "main subject keyword")
"""
import os, sys, subprocess, tempfile
from pathlib import Path

PANEL_KOK = Path(__file__).parent


def hook_qc(mp4_yolu: Path, baslik: str = "", konu_keyword: str = "") -> tuple[int, str]:
    """Returns (skor 0-10, sebep). Skor <5 yayında flag açar."""
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return 10, "ffmpeg yok, QC atlandı"

    tmp_png = Path(tempfile.mktemp(suffix=".png"))
    try:
        r = subprocess.run(
            [ffmpeg, "-y", "-ss", "1", "-i", str(mp4_yolu),
             "-vframes", "1", "-q:v", "2", str(tmp_png)],
            capture_output=True, timeout=20,
        )
        if r.returncode != 0 or not tmp_png.exists():
            return 10, "frame alınamadı"

        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            envf = PANEL_KOK / ".env"
            if envf.exists():
                for line in envf.read_text().splitlines():
                    if line.startswith("GEMINI_API_KEY="):
                        api_key = line.split("=", 1)[1].strip()
                        break
        if not api_key:
            return 10, "no api key, QC atlandı"

        from google import genai
        from google.genai import types as gtypes
        image_bytes = tmp_png.read_bytes()

        soru = (
            f"This is the FIRST FRAME (1st second) of a YouTube Shorts video.\n"
            f"Video title: '{baslik}'\n"
            f"Subject keyword: '{konu_keyword}'\n\n"
            f"Rate the HOOK quality 0-10 considering:\n"
            f"  - Is the subject clearly visible and on-topic?\n"
            f"  - Would a viewer scrolling Shorts STOP at this frame?\n"
            f"  - Is the visual interesting/striking (color, action, novelty)?\n\n"
            f"  0-3 = bad hook (boring/wrong subject/blurry)\n"
            f"  4-5 = mediocre (recognizable but not striking)\n"
            f"  6-7 = good (clear subject + visual interest)\n"
            f"  8-10 = excellent (instant grab)\n\n"
            f"Output a single integer 0-10 then a 1-line reason.\n"
            f"Format: '7|Clear octopus shot but dim lighting'"
        )
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[gtypes.Content(role="user", parts=[
                gtypes.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                gtypes.Part.from_text(text=soru),
            ])],
            config=gtypes.GenerateContentConfig(
                temperature=0.2, max_output_tokens=80,
                thinking_config=gtypes.ThinkingConfig(thinking_budget=0),
            ),
        )
        cevap = (resp.text or "").strip()
        import re
        m = re.search(r"(\d+)\s*\|?\s*(.*)", cevap)
        if not m:
            return 10, f"parse fail: {cevap[:80]}"
        skor = int(m.group(1))
        sebep = m.group(2).strip() or "—"
        return skor, sebep
    except Exception as h:
        return 10, f"hata: {str(h)[:120]}"
    finally:
        tmp_png.unlink(missing_ok=True)


def main():
    if len(sys.argv) < 2:
        print("Kullanım: python pre_publish_qc.py <mp4_path> [baslik] [keyword]")
        return 1
    skor, sebep = hook_qc(
        Path(sys.argv[1]),
        sys.argv[2] if len(sys.argv) > 2 else "",
        sys.argv[3] if len(sys.argv) > 3 else "",
    )
    print(f"Skor: {skor}/10")
    print(f"Sebep: {sebep}")
    return 0 if skor >= 5 else 1


if __name__ == "__main__":
    sys.exit(main())
