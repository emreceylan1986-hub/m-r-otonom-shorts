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
MERGE_PY
}

# Fetch + rebase: local commit'ler korunur, runner'a güncel main gelir
git fetch origin main 2>&1 | tail -1
git stash -u 2>&1 | tail -1 || true
git rebase origin/main 2>&1 | tail -1 || git rebase --abort 2>/dev/null || true
git stash pop 2>&1 | tail -1 || true

# JSON merge — runner + remote union (v1'de bu sadece push reddinde yapılırdı,
# şimdi her zaman → orphan video kaybını kökten önler)
merge_jsonlar

git add yuklemeler.json haberler.json haber_gecmisi.json ypp_status.json 2>/dev/null || true
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
  git add yuklemeler.json haberler.json haber_gecmisi.json ypp_status.json 2>/dev/null || true
  if git diff --cached --quiet; then
    echo "Merge sonrası değişiklik yok, push'a gerek yok."
    exit 0
  fi
  git commit -m "state: $(date -u +'%Y-%m-%dT%H:%MZ') run #${GITHUB_RUN_NUMBER:-?} [json-merged]" || true
  sleep 2
done

echo "✗ State push 5 denemede başarısız — bir sonraki run telafi eder."
exit 1
