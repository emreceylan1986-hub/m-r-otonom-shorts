"""
hook_predictor.py — Senaryo Hook Strength Predictor (Faz 8).

Seslendirici senaryosunun İLK 2 SANİYESİNDE (ilk 6-8 kelime) izleyiciyi
durduran bir hook var mı? Gemini ile 0-10 skor + iyileştirme önerisi al.

Düşük skor (<6) durumunda seslendirici yeniden üretim için işaret bırakır.

Kullanım (modül):
    from hook_predictor import hook_skor_ver
    skor, sebep, oneri = hook_skor_ver(senaryo)
"""
import sys
from pathlib import Path

PANEL_KOK = Path(__file__).parent


SISTEM = """You are a YouTube Shorts retention expert. You score the OPENING
HOOK of a Shorts script — only the FIRST sentence (first 2 seconds when spoken).

The hook decides if a viewer keeps watching or scrolls past.

A GOOD hook:
- Punchy, max 8 words
- Concrete subject (animal, place, phenomenon)
- Specific/surprising detail (number, comparison, contradiction)
- NO clickbait words (shocking, insane, crazy, secret, you won't believe)
- NO question mark
- NO generic openers ("did you know...", "let me tell you...", "today we look at...")

A BAD hook:
- Vague ("nature is amazing")
- Question opener
- Boring statement of fact without surprise
- Long > 10 words
- Trailing setup ("so...", "okay so...")

Score 0-10:
  0-3 = bad hook, viewer scrolls
  4-5 = mediocre, average retention
  6-7 = good, holds attention
  8-10 = excellent, instant grab

Output JSON only:
  {"score": 7, "reason": "concrete subject + surprising number", "alt_hook": "Octopuses have three hearts."}
"""


def hook_skor_ver(senaryo: str) -> tuple[int, str, str]:
    """Returns (skor, sebep, onerilen_alt_hook)."""
    ilk_cumle = senaryo.strip().split(".")[0].strip()
    if not ilk_cumle: return 0, "boş senaryo", ""
    if len(ilk_cumle.split()) > 12:
        ilk_cumle = " ".join(ilk_cumle.split()[:12]) + "..."

    try:
        import bridge
        from google.genai import types as gtypes
    except ImportError:
        return 10, "bridge yok", ""

    prompt = f'Score this Shorts hook (first sentence only):\n\n"{ilk_cumle}"\n\nReturn JSON.'

    try:
        cevap = bridge.gemini_metin_uret(
            prompt=prompt, sistem_promptu=SISTEM,
            sicaklik=0.3, max_token=200,
        )
        import json, re
        m = re.search(r"\{.*\}", cevap, re.DOTALL)
        if not m: return 10, f"parse fail: {cevap[:80]}", ""
        d = json.loads(m.group())
        return int(d.get("score", 10)), d.get("reason", "—"), d.get("alt_hook", "")
    except Exception as h:
        return 10, f"hata: {str(h)[:120]}", ""


def main():
    if len(sys.argv) < 2:
        print("Kullanım: python hook_predictor.py 'senaryo metni'")
        return 1
    skor, sebep, alt = hook_skor_ver(sys.argv[1])
    print(f"Hook skor: {skor}/10")
    print(f"Sebep: {sebep}")
    if alt: print(f"Önerilen alternatif: {alt}")
    return 0 if skor >= 6 else 1


if __name__ == "__main__":
    sys.exit(main())
