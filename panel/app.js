// M-R Kanal Paneli — statik PWA. Pipeline'ın ürettiği JSON'ları okur.
// Kanal başına dosya yoksa (örn. CosmoBytes henüz veri üretmediyse) "veri bekleniyor".

const KANALLAR = {
  trendcatcher: {
    ad: "TrendCatcher", emoji: "🐐", handle: "@TrendCatcher",
    ypp: "../ypp_status.json", analytics: "../analytics.json", yuklemeler: "../yuklemeler.json",
  },
  cosmobytes: {
    ad: "CosmoBytes", emoji: "🌌", handle: "@cosmobytess",
    ypp: "../ypp_status_cosmobytes.json", analytics: "../analytics_cosmobytes.json", yuklemeler: "../yuklemeler_cosmobytes.json",
  },
};

let aktif = "trendcatcher";

const $ = (s) => document.querySelector(s);
const fmt = (n) => (n == null ? "—" : Number(n).toLocaleString("tr-TR"));

async function getJSON(url) {
  try {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) return null;
    return await r.json();
  } catch { return null; }
}

function sekmeleriCiz() {
  const tabs = $("#tabs");
  tabs.innerHTML = "";
  for (const [key, k] of Object.entries(KANALLAR)) {
    const b = document.createElement("button");
    b.className = "tab" + (key === aktif ? " active" : "");
    b.innerHTML = `${k.emoji} ${k.ad}`;
    b.onclick = () => { aktif = key; render(); };
    tabs.appendChild(b);
  }
}

function statKart(v, l, d) {
  return `<div class="stat"><div class="v">${v}</div><div class="l">${l}</div>${d ? `<div class="d">${d}</div>` : ""}</div>`;
}

function tierBar(ad, yuzde, kalan, birim) {
  const p = Math.min(100, Number(yuzde) || 0);
  return `<div class="bar-row"><div class="name">${ad}</div>
    <div class="bar"><span style="width:${p}%"></span></div>
    <div class="pct">${p.toFixed(1)}%</div></div>
    <div class="d" style="color:var(--sub);font-size:11px;margin:-2px 0 8px 130px">kalan ${fmt(kalan)} ${birim}</div>`;
}

function spark(rows) {
  // analytics rows: [day, views, ...]; son 14 günün views barları
  if (!rows || !rows.length) return "";
  const views = rows.map((r) => r[1]);
  const max = Math.max(...views, 1);
  const bars = views.map((v) => `<div style="height:${Math.max(4, (v / max) * 100)}%" title="${v} görüntülenme"></div>`).join("");
  return `<div class="bar-wrap"><div class="d" style="color:var(--sub)">Son ${rows.length} gün — günlük görüntülenme</div><div class="spark">${bars}</div></div>`;
}

function videoSatiri(u) {
  const vid = u.video_id;
  const thumb = `https://i.ytimg.com/vi/${vid}/mqdefault.jpg`;
  const giz = (u.gizlilik || "").toLowerCase();
  const gizChip = giz ? `<span class="chip ${giz === "public" ? "public" : "private"}">${giz}</span>` : "";
  const den = (u.denetim_karari || "").toUpperCase();
  const denChip = den && den !== "ONAY" && den !== "TEMIZ" ? `<span class="chip warn">${den}</span>` : "";
  const tarih = (u.zaman || "").replace("T", " ").slice(0, 16);
  return `<a class="vid" href="${u.watch_url || "#"}" target="_blank" rel="noopener">
    <img class="thumb" src="${thumb}" loading="lazy" alt="" onerror="this.style.visibility='hidden'"/>
    <div class="meta">
      <div class="t">${(u.title || "(başlıksız)")}</div>
      <div class="s">${tarih}${gizChip}${denChip}</div>
    </div></a>`;
}

async function render() {
  sekmeleriCiz();
  const k = KANALLAR[aktif];
  const main = $("#icerik");
  main.innerHTML = `<div class="loader">${k.ad} yükleniyor…</div>`;

  const [ypp, an, yuk] = await Promise.all([getJSON(k.ypp), getJSON(k.analytics), getJSON(k.yuklemeler)]);

  if (!ypp && !yuk) {
    main.innerHTML = `<div class="empty"><div class="big">${k.emoji}</div>
      <div><b>${k.ad}</b> için veri henüz yok.</div>
      <div style="margin-top:8px;font-size:12px;color:var(--sub)">
      Bu kanal pipeline'da çalışıp JSON üretince panel otomatik dolacak.<br/>
      (Aktivasyon: <code>KANAL=${aktif}</code> + token)</div></div>`;
    $("#guncelleme").textContent = `${k.handle} · veri bekleniyor`;
    return;
  }

  let html = "";

  // --- Özet kartlar (ypp_status.json) ---
  if (ypp) {
    html += `<div class="grid">
      ${statKart(fmt(ypp.abone), "Abone")}
      ${statKart(fmt(ypp.toplam_video), "Video")}
      ${statKart(fmt(ypp.toplam_izlenme_yaşam_boyu ?? ypp.toplam_izlenme), "Toplam izlenme")}
      ${statKart(fmt(Math.round(ypp.gunluk_izlenme_tahmin)), "Günlük izlenme ~")}
    </div>`;
    html += `<div class="grid">
      ${statKart(fmt(ypp.son_90g_izlenme), "Son 90g izlenme")}
      ${statKart(fmt(ypp.son_14g_izlenme), "Son 14g izlenme")}
    </div>`;
  }

  // --- YPP ilerleme ---
  if (ypp && (ypp.early_tier || ypp.full_tier)) {
    html += `<div class="section-title">YPP Hedefleri</div><div class="bar-wrap">`;
    if (ypp.early_tier) {
      html += tierBar("Abone (500)", ypp.early_tier.abone_yuzde, ypp.early_tier.abone_kalan, "abone");
      html += tierBar("Shorts 90g (3M)", ypp.early_tier.shorts_yuzde_90g, ypp.early_tier.shorts_kalan_90g, "izlenme");
    }
    if (ypp.full_tier) {
      html += tierBar("Abone (1000)", ypp.full_tier.abone_yuzde, ypp.full_tier.abone_kalan, "abone");
      html += tierBar("Shorts 90g (10M)", ypp.full_tier.shorts_yuzde_90g, ypp.full_tier.shorts_kalan_90g, "izlenme");
    }
    html += `</div>`;
  }

  // --- Trend (analytics.json) ---
  if (an && an.gun_gun && an.gun_gun.rows) {
    html += `<div class="section-title">Trend</div>` + spark(an.gun_gun.rows);
  }

  // --- Son yüklemeler ---
  if (yuk && yuk.length) {
    const son = yuk.slice(-12).reverse();
    html += `<div class="section-title">Son Yüklemeler (${yuk.length})</div>`;
    html += son.map(videoSatiri).join("");
  }

  main.innerHTML = html;

  const guncel = (ypp && ypp.uretim) || (an && an.uretim) || "";
  $("#guncelleme").textContent = `${k.handle} · güncel: ${guncel.replace("T", " ").slice(0, 16) || "?"}`;
}

// --- Yenile ---
$("#yenile").onclick = () => render();

// --- PWA install ---
let deferredPrompt = null;
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  deferredPrompt = e;
  const hint = $("#kurulum");
  hint.hidden = false;
  const btn = $("#kurBtn");
  btn.hidden = false;
  btn.onclick = async () => { hint.hidden = true; deferredPrompt.prompt(); deferredPrompt = null; };
});
$("#kapatHint").onclick = () => { $("#kurulum").hidden = true; };

// iOS ipucu (beforeinstallprompt yok)
const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
const standalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone;
if (isIOS && !standalone) { $("#kurulum").hidden = false; }

// --- Service worker ---
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}

render();
