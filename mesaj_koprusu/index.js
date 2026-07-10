/**
 * mesaj_koprusu — WhatsApp + SMS → telefon push (ntfy) köprüsü.
 *
 * Bu KENDİ SUNUCUNDA çalışır (bu repo'nun pipeline'ından bağımsız).
 *   - WhatsApp: Baileys ile "Linked Devices" QR eşleştirmesi (kişisel hesap).
 *   - SMS:      telefondaki bir SMS-forwarder uygulaması POST /sms ile iletir.
 *   - Çıkış:    gelen/giden mesaj özetini ntfy ile telefonuna push atar.
 *   - Opsiyon:  GEMINI_API_KEY varsa kısa bir "önerilen cevap" üretir.
 *
 * ⚠️ UYARI: Resmi olmayan WhatsApp otomasyonu Meta ToS'una aykırıdır ve
 * numaranın yasaklanma riski taşır (15 Oca 2026 şartları AI chatbot'ları yasaklar).
 * Bu riski kabul ederek kullanırsın. Mümkünse yan/test numarası tercih et.
 */
require("dotenv").config();
const express = require("express");
const qrcode = require("qrcode-terminal");
const P = require("pino");
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} = require("baileys");

const PORT = process.env.PORT || 3000;
const NTFY_SERVER = (process.env.NTFY_SERVER || "https://ntfy.sh").replace(/\/+$/, "");
const NTFY_TOPIC = process.env.NTFY_TOPIC;
const NTFY_TOKEN = process.env.NTFY_TOKEN;
const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const SMS_WEBHOOK_SECRET = process.env.SMS_WEBHOOK_SECRET; // basit doğrulama

const log = P({ level: process.env.LOG_LEVEL || "info" });

// --------------------------------------------------------------------------
// Telefona push (ntfy JSON publishing — UTF-8 güvenli)
// --------------------------------------------------------------------------
async function push(title, message, { priority = "default", tags = [], click } = {}) {
  if (!NTFY_TOPIC) {
    log.warn("NTFY_TOPIC yok → push atlandı");
    return;
  }
  try {
    const body = { topic: NTFY_TOPIC, title, message, priority, tags };
    if (click) body.click = click;
    const headers = { "Content-Type": "application/json" };
    if (NTFY_TOKEN) headers["Authorization"] = `Bearer ${NTFY_TOKEN}`;
    await fetch(NTFY_SERVER, { method: "POST", headers, body: JSON.stringify(body) });
  } catch (e) {
    log.error(`ntfy push hata: ${e.message}`);
  }
}

// --------------------------------------------------------------------------
// Opsiyonel: Gemini ile kısa "önerilen cevap"
// --------------------------------------------------------------------------
async function oneriCevap(gelenMetin, kanal) {
  if (!GEMINI_API_KEY || !gelenMetin) return null;
  try {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${GEMINI_API_KEY}`;
    const prompt =
      `Sana ${kanal} üzerinden gelen bir mesaj vereceğim. Türkçe, kibar, KISA ` +
      `(en fazla 2 cümle) bir cevap taslağı öner. Sadece cevabı yaz:\n\n"${gelenMetin}"`;
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] }),
    });
    const j = await r.json();
    return j?.candidates?.[0]?.content?.parts?.[0]?.text?.trim() || null;
  } catch (e) {
    log.error(`Gemini öneri hata: ${e.message}`);
    return null;
  }
}

function kisalt(s, n = 240) {
  if (!s) return "";
  return s.length > n ? s.slice(0, n) + "…" : s;
}

// --------------------------------------------------------------------------
// WhatsApp (Baileys)
// --------------------------------------------------------------------------
function metinCek(msg) {
  const m = msg.message || {};
  return (
    m.conversation ||
    m.extendedTextMessage?.text ||
    m.imageMessage?.caption ||
    m.videoMessage?.caption ||
    m.documentMessage?.caption ||
    ""
  );
}

async function whatsappBaslat() {
  const { state, saveCreds } = await useMultiFileAuthState("auth_info");
  const { version } = await fetchLatestBaileysVersion();
  const sock = makeWASocket({ version, auth: state, logger: P({ level: "silent" }) });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (u) => {
    const { connection, lastDisconnect, qr } = u;
    if (qr) {
      console.log("\n📱 WhatsApp eşleştirme: telefonda WhatsApp → Bağlı Cihazlar → Cihaz Bağla, bu QR'ı okut:\n");
      qrcode.generate(qr, { small: true });
    }
    if (connection === "open") {
      log.info("✅ WhatsApp bağlı");
      push("✅ WhatsApp köprüsü bağlı", "Mesaj izleme aktif.", { tags: ["white_check_mark"] });
    }
    if (connection === "close") {
      const kod = lastDisconnect?.error?.output?.statusCode;
      const tekrar = kod !== DisconnectReason.loggedOut;
      log.warn(`WhatsApp bağlantı kapandı (kod ${kod}) — ${tekrar ? "yeniden bağlanılıyor" : "çıkış yapıldı"}`);
      if (tekrar) whatsappBaslat();
      else push("⚠️ WhatsApp çıkış yapıldı", "Yeniden QR okutman gerekiyor.", { priority: "high", tags: ["warning"] });
    }
  });

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;
    for (const msg of messages) {
      const metin = metinCek(msg);
      if (!metin) continue;
      const giden = !!msg.key.fromMe;
      const kimden = msg.pushName || msg.key.remoteJid?.split("@")[0] || "bilinmiyor";
      const yon = giden ? "↗️ Giden" : "↘️ Gelen";
      let govde = kisalt(metin);

      if (!giden) {
        const oneri = await oneriCevap(metin, "WhatsApp");
        if (oneri) govde += `\n\n💡 Önerilen cevap:\n${oneri}`;
      }
      await push(`💬 WhatsApp ${yon} · ${kimden}`, govde, {
        priority: giden ? "low" : "default",
        tags: ["speech_balloon"],
      });
      log.info(`WhatsApp ${yon} ${kimden}: ${kisalt(metin, 60)}`);
    }
  });

  return sock;
}

// --------------------------------------------------------------------------
// SMS webhook (telefondaki forwarder uygulaması buraya POST eder)
// Beklenen JSON: { from, text, sentStamp, secret? }  (uygulamaya göre eşle)
// --------------------------------------------------------------------------
const app = express();
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.get("/", (_req, res) => res.send("mesaj_koprusu çalışıyor"));

app.post("/sms", async (req, res) => {
  if (SMS_WEBHOOK_SECRET && req.body.secret !== SMS_WEBHOOK_SECRET) {
    return res.status(401).json({ ok: false, error: "secret hatalı" });
  }
  const kimden = req.body.from || req.body.sender || req.body.phone || "bilinmiyor";
  const metin = req.body.text || req.body.message || req.body.content || "";
  if (!metin) return res.status(400).json({ ok: false, error: "boş mesaj" });

  let govde = kisalt(metin);
  const oneri = await oneriCevap(metin, "SMS");
  if (oneri) govde += `\n\n💡 Önerilen cevap:\n${oneri}`;

  await push(`📩 SMS · ${kimden}`, govde, { tags: ["envelope"] });
  log.info(`SMS ${kimden}: ${kisalt(metin, 60)}`);
  res.json({ ok: true });
});

// --------------------------------------------------------------------------
// Başlat
// --------------------------------------------------------------------------
app.listen(PORT, () => log.info(`🌉 SMS webhook dinleniyor: http://0.0.0.0:${PORT}/sms`));
whatsappBaslat().catch((e) => {
  log.error(`WhatsApp başlatma hata: ${e.message}`);
});
