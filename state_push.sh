#!/usr/bin/env bash
# State commit v2 — atomic + rebase-first + JSON-aware merge fallback.
# 1) Runner verisini /tmp'ye yedekle.
# 2) git fetch + rebase (local commit varsa korur).
# 3) JSON merge — runner + remote union (her run birleşik state).
# 4) Push 5 kez dene. Her push fail'inde fetch+reset+merge+retry.

set -u

git config user.name  "M-R Otonom Bot"
git config user.email "actions@github.com"

cp -f yuklemeler.json     /tmp/_runner_yk.json 2>/dev/null || echo "[]" > /tmp/_runner_yk.json
cp -f haber_gecmisi.json  /tmp/_runner_hg.json 2>/dev/null || echo '{"islenen_url":[]}' > /tmp/_runner_hg.json
cp -f haberler.json       /tmp/_runner_h.json  2>/dev/null || true
cp -f ypp_status.json     /tmp/_runner_ypp.json  2>/dev/null || true
cp -f kota_state.json     /tmp/_runner_kota.json 2>/dev/null || true
cp -f manuel_konular.json /tmp/_runner_mk.json   2>/dev/null || true
cp -f comment_replies.json /tmp/_runner_cr.json 2>/dev/null || echo '{"replied": {}, "last_run": null}' > /tmp/_runner_cr.json

merge_jsonlar() {
  python3 << 'MERGE_PY'
import json, os
def read(p, default):
    try: return json.load(open(p))
    except Exception: return default

runner_yk = read("/tmp/_runner_yk.json", [])
uzak_yk = read("yuklemeler.json", [])
goren = set(); birlesik = []
for k in uzak_yk + runner_yk:
    vid = k.get("video_id")
    if vid and vid not in goren:
        goren.add(vid); birlesik.append(k)
open("yuklemeler.json","w").write(json.dumps(birlesik, ensure_ascii=False, indent=2))
print(f"  yuklemeler merge: runner {len(runner_yk)} + uzak {len(uzak_yk)} → {len(birlesik)}")

runner_hg = read("/tmp/_runner_hg.json", {"islenen_url":[]})
uzak_hg = read("haber_gecmisi.json", {"islenen_url":[]})
goren = set(); birlesik = []
for u in uzak_hg.get("islenen_url",[]) + runner_hg.get("islenen_url",[]):
    if u and u not in goren:
        goren.add(u); birlesik.append(u)
open("haber_gecmisi.json","w").write(json.dumps({"islenen_url": birlesik}, ensure_ascii=False, indent=2))
print(f"  haber_gecmisi merge → {len(birlesik)} URL")

if os.path.exists("/tmp/_runner_h.json"):
    import shutil
    shutil.copy("/tmp/_runner_h.json", "haberler.json")
    print("  haberler runner versiyonu kullanıldı")
for _tmp, _hedef in [("/tmp/_runner_ypp.json","ypp_status.json"),
                     ("/tmp/_runner_kota.json","kota_state.json"),
                     ("/tmp/_runner_mk.json","manuel_konular.json")]:
    if os.path.exists(_tmp):
        import shutil as _sh; _sh.copy(_tmp, _hedef); print(f"  {_hedef} runner versiyonu")

# 18 Tem FIX: comment_replies.json HİÇ commit edilmiyordu (13 gün donuk kalmıştı) ->
# her run taze checkout'ta "replied" boş/eski bulunuyor -> yorum botu AYNI yoruma
# tekrar tekrar cevap yazıyordu. Artık runner+remote "replied" dict UNION merge.
runner_cr = read("/tmp/_runner_cr.json", {"replied": {}, "last_run": None})
uzak_cr = read("comment_replies.json", {"replied": {}, "last_run": None})
birlesik_replied = dict(uzak_cr.get("replied", {}))
birlesik_replied.update(runner_cr.get("replied", {}))  # runner (en taze) kazanir
son_run = runner_cr.get("last_run") or uzak_cr.get("last_run")
open("comment_replies.json","w").write(json.dumps(
    {"replied": birlesik_replied, "last_run": son_run,
     "last_replied_count": runner_cr.get("last_replied_count", 0)},
    ensure_ascii=False, indent=2))
print(f"  comment_replies merge: runner {len(runner_cr.get('replied',{}))} + uzak {len(uzak_cr.get('replied',{}))} -> {len(birlesik_replied)}")
MERGE_PY
}

# Güncel main + TEMİZ başla — stash/rebase çakışması yok (JSON'lar /tmp'den union merge)
git fetch origin main 2>&1 | tail -1
git reset --hard origin/main 2>&1 | tail -1

# JSON merge — runner + remote union (v1'de bu sadece push reddinde yapılırdı,
# şimdi her zaman → orphan video kaybını kökten önler)
merge_jsonlar

git add yuklemeler.json haberler.json haber_gecmisi.json ypp_status.json kota_state.json comment_replies.json 2>/dev/null || true
if git diff --cached --quiet; then
  echo "State değişmedi, commit yok."
  exit 0
fi

git commit -m "state: $(date -u +'%Y-%m-%dT%H:%MZ') run #${GITHUB_RUN_NUMBER:-?}" || true

for deneme in 1 2 3 4 5; do
  if git push 2>&1; then
    echo "✓ State push OK (deneme $deneme)"
    exit 0
  fi

  echo "Push reddedildi (deneme $deneme/5) — fetch + JSON merge + retry..."
  git rebase --abort 2>/dev/null || true
  git merge --abort 2>/dev/null || true
  git fetch origin main 2>&1 | tail -1
  git reset --hard origin/main 2>&1 | tail -1
  merge_jsonlar
  git add yuklemeler.json haberler.json haber_gecmisi.json ypp_status.json kota_state.json comment_replies.json 2>/dev/null || true
  if git diff --cached --quiet; then
    echo "Merge sonrası değişiklik yok, push'a gerek yok."
    exit 0
  fi
  git commit -m "state: $(date -u +'%Y-%m-%dT%H:%MZ') run #${GITHUB_RUN_NUMBER:-?} [json-merged]" || true
  sleep 2
done

echo "✗ State push 5 denemede başarısız — bir sonraki run telafi eder."
exit 1
