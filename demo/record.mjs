// record.mjs — rekam alur kerja JualinAja langsung dari aplikasinya.
// CDP Page.startScreencast menyimpan setiap frame yang dilukis browser beserta timestamp aslinya,
// lalu motion.py menggambar motion graphic di atasnya. Tidak ada mockup, tidak ada gambar tempelan.
//
//   node record.mjs <base-url> <frames-dir> <foto-untuk-upload>
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
const require = createRequire("/home/adminganteng21/.npm/_npx/a8ead9d790d3d81e/node_modules/");
const puppeteer = require("puppeteer-core");

const BASE = process.argv[2] || "http://127.0.0.1:8126";
const OUT = process.argv[3] || "/home/adminganteng21/Projects/jualinaja/demo/frames";
const PHOTO = process.argv[4] || "/home/adminganteng21/Projects/jualinaja/demo/foto-contoh.png";

fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(OUT, { recursive: true });

const W = 1600, H = 1000;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const marks = [];
let t0 = 0;

function mark(text, sub = "") {
  marks.push({ t: +((Date.now() - t0) / 1000).toFixed(2), text, sub });
  console.log(`  [${((Date.now() - t0) / 1000).toFixed(1)}s] ${text}`);
}

const browser = await puppeteer.launch({
  executablePath: "/usr/bin/chromium",
  headless: "new",
  args: ["--no-sandbox", "--disable-dev-shm-usage", "--force-device-scale-factor=2",
         "--hide-scrollbars", "--disable-infobars", "--font-render-hinting=none"],
  defaultViewport: { width: W, height: H, deviceScaleFactor: 2 },
});
const page = await browser.newPage();
await page.setUserAgent("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148 Safari/537.36");

const cdp = await page.createCDPSession();
await cdp.send("Page.enable");

/* ---------- capture ---------- */
const frames = [];
let capturing = false;
cdp.on("Page.screencastFrame", async ev => {
  if (capturing) {
    const file = `f-${String(frames.length).padStart(5, "0")}.jpg`;
    fs.writeFileSync(path.join(OUT, file), Buffer.from(ev.data, "base64"));
    // metadata.timestamp dari Chromium sering sama untuk frame berurutan; pakai jam dinding sebagai acuan utama
    frames.push({ file, t: +(Date.now() / 1000).toFixed(4), meta: +(ev.metadata.timestamp / 1000).toFixed(4) });
  }
  try { await cdp.send("Page.screencastFrameAck", { sessionId: ev.sessionId }); } catch {}
});

/* ---------- helpers ---------- */
async function go(url) {
  await page.goto(BASE + url, { waitUntil: "domcontentloaded" });
  await sleep(500);
}

async function smoothScroll(to, ms = 900) {
  await page.evaluate((to, ms) => new Promise(res => {
    const from = window.scrollY, d = to - from, s = performance.now();
    (function step(now) {
      const k = Math.min(1, (now - s) / ms);
      window.scrollTo(0, from + d * (k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2));
      k < 1 ? requestAnimationFrame(step) : res();
    })(performance.now());
  }), to, ms).catch(() => {});
}

async function waitSel(sel, ms = 12000) {
  try { await page.waitForSelector(sel, { timeout: ms, visible: true }); }
  catch { throw new Error(`tidak ada elemen ${sel} di ${page.url()}`); }
}

async function glide(sel, ms = 460) {
  const box = await page.evaluate(s => {
    const el = document.querySelector(s);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + Math.min(r.height / 2, 24) };
  }, sel);
  if (!box) return null;
  const cur = await page.evaluate(() => window.__mx ?? 900).catch(() => 900);
  const steps = 14;
  for (let i = 1; i <= steps; i++) {
    const k = i / steps, e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
    await cdp.send("Input.dispatchMouseEvent", {
      type: "mouseMoved", x: Math.round(cur + (box.x - cur) * e), y: Math.round(box.y), buttons: 0 }).catch(() => {});
    await sleep(ms / steps);
  }
  await page.evaluate(x => { window.__mx = x; }, box.x).catch(() => {});
  return box;
}

async function click(sel) {
  await waitSel(sel);
  const b = await glide(sel);
  if (!b) throw new Error("tidak ada elemen: " + sel + " di " + page.url());
  await sleep(160);
  await cdp.send("Input.dispatchMouseEvent", { type: "mousePressed", x: b.x, y: b.y, button: "left", clickCount: 1 });
  await sleep(70);
  await cdp.send("Input.dispatchMouseEvent", { type: "mouseReleased", x: b.x, y: b.y, button: "left", clickCount: 1 });
  await sleep(430);
}

async function typeInto(sel, text, perChar = 52) {
  await waitSel(sel);
  await glide(sel, 320);
  await page.click(sel);
  await sleep(130);
  for (const ch of text) { await page.keyboard.type(ch); await sleep(perChar); }
  await sleep(240);
}

async function setValue(sel, value) {
  await waitSel(sel);
  await page.evaluate((s, v) => {
    const el = document.querySelector(s);
    el.value = v;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }, sel, value).catch(() => {});
  await sleep(300);
}

/** jalankan satu langkah; kalau gagal, catat lalu lanjut supaya seluruh rekaman tidak hilang */
async function step(name, fn) {
  try { await fn(); }
  catch (e) { console.warn(`  ! langkah "${name}" dilewati: ${e.message}`); }
}

/** pastikan sesi hidup; tahan terhadap navigasi yang sedang berjalan */
async function ensureAuth(email, pass) {
  for (let i = 0; i < 4; i++) {
    try {
      const res = await page.evaluate(async () => {
        try {
          const r = await fetch("/api/auth/me", { credentials: "same-origin" });
          if (!r.ok) return { err: r.status };
          return { user: (await r.json()).user };
        } catch (e) { return { err: String(e) }; }
      });
      if (res && res.user) return res.user;
      if (res && res.err) break;
    } catch { /* konteks hilang saat navigasi */ }
    await sleep(450);
  }
  try {
    await page.evaluate(async (email, pass) => {
      await fetch("/api/auth/login", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password: pass }),
      });
    }, email, pass);
  } catch {}
  await page.reload({ waitUntil: "domcontentloaded" }).catch(() => {});
  await sleep(800);
}

/* ---------- the flow ---------- */
console.log("mulai rekam…");
await page.goto(BASE + "/index.html", { waitUntil: "networkidle2" });
await page.evaluate(() => {
  const c = document.createElement("div");
  c.id = "__cursor";
  c.style.cssText = "position:fixed;z-index:99999;width:18px;height:18px;pointer-events:none;left:-100px;top:-100px;will-change:transform";
  c.innerHTML = '<svg width="18" height="18" viewBox="0 0 18 18"><path d="M2 1l13 8-6 1.5L6 17z" fill="#fff" stroke="#1b1524" stroke-width="2"/></svg>';
  document.body.appendChild(c);
  document.addEventListener("mousemove", e => { c.style.transform = `translate(${e.clientX - 2}px, ${e.clientY - 2}px)`; }, true);
});
await sleep(800);
t0 = Date.now();
capturing = true;
await cdp.send("Page.startScreencast", { format: "jpeg", quality: 88, maxWidth: 1600, maxHeight: 1000, everyNthFrame: 1 });

mark("JualinAja", "pasar barang bekas antar warga · satu proses Python, tanpa dependensi");
await sleep(1800);
await step("scroll beranda", async () => smoothScroll(560, 1100));
mark("Beranda", "paling dilihat · baru masuk · statistik barang aktif");
await sleep(1500);
await step("balik atas", async () => smoothScroll(0, 800));
await sleep(500);

await step("1 jelajah", async () => {
  mark("1 · Jelajah", "filter kata kunci, kota, kategori, kondisi, rentang harga");
  await go("/jelajah.html");
  await waitSel('input[name="q"]');
  await sleep(800);
  await typeInto('input[name="q"]', "kamera", 62);
  await setValue('select[name="city"]', "Bandung");
  await setValue('select[name="category"]', "Elektronik");
  await click('#filter button[type="submit"]');
  await sleep(1500);
  await smoothScroll(420, 1000);
  await sleep(900);
  await smoothScroll(0, 600);
});

await step("2 detail", async () => {
  mark("2 · Detail barang", "galeri, kondisi, penjual, ulasan");
  await go("/listing.html?id=1");
  await waitSel(".price-big");
  await sleep(1100);
  await smoothScroll(500, 1100);
  await sleep(1200);
  await smoothScroll(0, 700);
});

await step("3 masuk", async () => {
  mark("3 · Masuk", "PBKDF2 240k iterasi · cookie HttpOnly SameSite=Lax");
  await page.evaluate(() => window.JA && window.JA.Auth.logout()).catch(() => {});
  await sleep(700);
  await go("/masuk.html");
  await waitSel("#auth-form input[name=email]");
  await sleep(600);
  await typeInto('input[name="email"]', "sri.wahyuni@example.com", 34);
  await typeInto('input[name="password"]', "demo1234", 60);
  await click("#submit");
  await sleep(2600);
  await smoothScroll(300, 800);
  await sleep(1000);
});

await step("4 tawar", async () => {
  await ensureAuth("sri.wahyuni@example.com", "demo1234");
  mark("4 · Tawar & chat", "tawaran unik per pembeli · chat per barang");
  await go("/listing.html?id=1");
  await waitSel("#offer-form");
  await sleep(900);
  await typeInto('#offer-form input[name="amount"]', "1100000", 70);
  await typeInto('#offer-form input[name="note"]', "Bisa nego? saya ambil minggu ini", 32);
  await click('#offer-form button[type="submit"]');
  await sleep(2200);
  await smoothScroll(700, 900);
  await sleep(500);
  await typeInto('#chat-form input[name="body"]', "Halo, kameranya masih ada?", 34);
  await click('#chat-form button');
  await sleep(1800);
  await smoothScroll(0, 600);
});

await step("5 penjual", async () => {
  mark("5 · Penjual menjawab", "terima satu tawaran → sisanya otomatis ditolak");
  await page.evaluate(() => window.JA && window.JA.Auth.logout()).catch(() => {});
  await sleep(800);
  await go("/masuk.html");
  await waitSel("#auth-form input[name=email]");
  await sleep(500);
  await typeInto('input[name="email"]', "rangga.putra@example.com", 32);
  await typeInto('input[name="password"]', "demo1234", 55);
  await click("#submit");
  await sleep(2400);
  await ensureAuth("rangga.putra@example.com", "demo1234");
  await go("/listing.html?id=1");
  await waitSel('[data-act="accept"]');
  await sleep(1200);
  await smoothScroll(380, 900);
  await sleep(900);
  await click('[data-act="accept"]');
  await sleep(2400);
  await typeInto('#chat-form input[name="body"]', "Masih, silakan datang. Bisa jam 4?", 30);
  await click('#chat-form button');
  await sleep(1900);
  await smoothScroll(0, 600);
});

await step("6 pasang", async () => {
  await ensureAuth("rangga.putra@example.com", "demo1234");
  mark("6 · Pasang barang", "sampai 10 foto · 8 MB per foto · MIME diperiksa");
  await go("/jual.html");
  await waitSel('#form input[name="title"]');
  await sleep(800);
  await typeInto('input[name="title"]', "Meja kerja kayu 120x60", 42);
  await typeInto('input[name="price"]', "475000", 78);
  await setValue('select[name="category"]', "Rumah Tangga");
  await setValue('select[name="condition"]', "Bekas bagus");
  await setValue('select[name="city"]', "Bandung");
  await glide('textarea[name="description"]', 380);
  await page.click('textarea[name="description"]');
  await page.keyboard.type("Kayu solid, dua laci, ada lecet halus di sudut kiri. Bongkar pasang mudah.", { delay: 26 });
  await sleep(400);
  const input = await page.$("#photos");
  await input.uploadFile(PHOTO);
  await sleep(1200);
  await smoothScroll(320, 800);
  await sleep(900);
  await click("#submit");
  await sleep(3400);
  await smoothScroll(200, 800);
  await sleep(1300);
});

await step("7 dasbor", async () => {
  await ensureAuth("rangga.putra@example.com", "demo1234");
  mark("7 · Dasbor", "barang saya · tersimpan · notifikasi");
  await go("/akun.html");
  await waitSel("#tabs button");
  await sleep(1600);
  await smoothScroll(340, 900);
  await sleep(1100);
  await click('#tabs button[data-tab="notif"]');
  await sleep(2000);
  await smoothScroll(0, 700);
});

mark("Selesai", "77 pemeriksaan API lolos · branch feat/jualinaja-v2");
await sleep(2400);

capturing = false;
await cdp.send("Page.stopScreencast").catch(() => {});
await sleep(300);
await browser.close();

/* ---------- timeline ---------- */
if (frames.length < 10) {
  console.error(`hanya ${frames.length} frame — capture gagal`);
  process.exit(1);
}
const t_base = frames[0].t;
const timed = frames.map(f => +(f.t - t_base).toFixed(4));
// screencast berhenti mengirim frame saat layar diam: tahan frame terakhir supaya outro kebagian waktu
const OUTRO_HOLD = 3.6;
const duration = timed[timed.length - 1] + OUTRO_HOLD;
const gaps = timed.slice(1).map((t, i) => t - timed[i]).sort((a, b) => a - b);
const median = gaps[Math.floor(gaps.length / 2)] || 1 / 10;
console.log(`  gap antar frame: median ${(median * 1000).toFixed(0)}ms, min ${(gaps[0] * 1000).toFixed(0)}ms, max ${(gaps[gaps.length - 1] * 1000).toFixed(0)}ms`);

fs.writeFileSync(path.join(OUT, "..", "timeline.json"),
  JSON.stringify({ frames: frames.map((f, i) => ({ file: f.file, t: timed[i] })), marks, duration, median }, null, 1));

console.log(`\n${frames.length} frame, ${duration.toFixed(1)} s, ${marks.length} penanda`);
console.log(`frame tersimpan di ${OUT}`);
