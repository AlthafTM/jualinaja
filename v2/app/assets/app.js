/* app.js — JualinAja client. Tanpa framework, tanpa dependensi. Setiap halaman memanggil yang dibutuhkannya. */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  const rupiah = n => "Rp" + Number(n || 0).toLocaleString("id-ID");
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const qs = k => new URLSearchParams(location.search).get(k);

  let toastTimer;
  function toast(msg, isErr) {
    let el = $("#toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "toast";
      el.setAttribute("role", "status");
      el.setAttribute("aria-live", "polite");
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.style.boxShadow = isErr ? "6px 6px 0 #e27a92" : "6px 6px 0 #8fcb6a";
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 3600);
  }

  async function api(path, { method = "GET", body, form } = {}) {
    const opts = { method, credentials: "same-origin", headers: {} };
    if (form) opts.body = form;
    else if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(path, opts);
    let data = null;
    try { data = await res.json(); } catch { /* non-JSON */ }
    if (!res.ok || (data && data.ok === false)) {
      const err = new Error((data && data.error) || `HTTP ${res.status}`);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  /* ---------------- session ---------------- */
  const Auth = {
    user: null,
    async load() {
      try { this.user = (await api("/api/auth/me")).user; } catch { this.user = null; }
      return this.user;
    },
    async login(email, password) {
      const d = await api("/api/auth/login", { method: "POST", body: { email, password } });
      this.user = d.user;
      paintHeader();
      return d.user;
    },
    async register(payload) {
      const d = await api("/api/auth/register", { method: "POST", body: payload });
      this.user = d.user;
      paintHeader();
      return d.user;
    },
    async logout() {
      await api("/api/auth/logout", { method: "POST" });
      this.user = null;
      paintHeader();
      toast("Kamu sudah keluar");
    },
  };

  /* ---------------- header ---------------- */
  function brandSvg() {
    return `<svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true">
      <rect x="1.5" y="1.5" width="27" height="27" fill="#cfc4f0" stroke="#1b1524" stroke-width="3"/>
      <path d="M8 9h9a4 4 0 0 1 0 8H8z" fill="#6b4fa8"/>
      <path d="M8 17h6v6H8z" fill="#8fcb6a" stroke="#1b1524" stroke-width="2.5"/>
      <path d="M8 5.5v19" stroke="#1b1524" stroke-width="3"/>
    </svg>`;
  }

  async function paintHeader() {
    const host = $("#hdr");
    if (!host) return;
    const page = document.body.dataset.page || "";
    const u = Auth.user;
    let nav = `
      <a href="/jelajah.html" ${page === "jelajah" ? 'aria-current="page"' : ""}>Jelajah</a>
      <a href="/cari.html" ${page === "cari" ? 'aria-current="page"' : ""}>Papan Cari</a>`;
    if (u) {
      nav += `
        <a href="/akun.html" ${page === "akun" ? 'aria-current="page"' : ""}>Akun
          <span class="badge" id="notif-badge" hidden>0</span></a>
        <a href="/jual.html" ${page === "jual" ? 'aria-current="page"' : ""} class="cta">+ Pasang</a>
        <a href="/akun.html" id="logout">Keluar</a>`;
    } else {
      nav += `
        <a href="/jual.html" class="cta">+ Pasang</a>
        <a href="/masuk.html" ${page === "masuk" ? 'aria-current="page"' : ""}>Masuk</a>`;
    }
    host.innerHTML = `
      <div class="wrap hdr-in">
        <a class="brand" href="/index.html">${brandSvg()} JualinAja</a>
        <nav class="nav" aria-label="Navigasi utama">${nav}</nav>
      </div>`;
    const out = $("#logout");
    if (out) out.addEventListener("click", e => { e.preventDefault(); Auth.logout(); });
    if (u) refreshNotifs();
  }

  async function refreshNotifs() {
    try {
      const d = await api("/api/notifications");
      const b = $("#notif-badge");
      if (!b) return;
      b.textContent = d.unread > 9 ? "9+" : String(d.unread);
      b.hidden = !d.unread;
    } catch { /* silent */ }
  }

  /* ---------------- listing card ---------------- */
  function card(l) {
    const photo = l.photo
      ? `<img src="/uploads/${esc(l.photo)}" alt="" loading="lazy" width="400" height="300">`
      : `<span>Tanpa foto</span>`;
    const tags = [
      l.status === "sold" ? `<span class="tag sold">Terjual</span>` : "",
      `<span class="tag lav">${esc(l.condition || "")}</span>`,
    ].join("");
    const stars = l.rating ? ` · ${l.rating}★` : "";
    return `<a class="listing" href="/listing.html?id=${l.id}">
      <div class="thumb${l.photo ? "" : " ph"}">${photo}</div>
      <div class="body">
        <div class="ttl">${esc(l.title)}</div>
        <div class="price">${esc(l.price_text || rupiah(l.price))}</div>
        <div class="meta">${tags}</div>
        <div class="meta"><span>${esc(l.city)}</span>${l.seller ? `<span>${esc(l.seller)}${stars}</span>` : ""}</div>
      </div>
    </a>`;
  }

  function skeletonGrid(n = 6) {
    return Array.from({ length: n }, () => `<div class="card" style="height:290px"></div>`).join("");
  }

  /* ---------------- pages ---------------- */
  const Pages = {
    async index() {
      const grid = $("#featured");
      const newest = $("#newest");
      grid.innerHTML = skeletonGrid(4);
      try {
        const [pop, fresh, meta] = await Promise.all([
          api("/api/listings?sort=popular&page=1"),
          api("/api/listings?sort=new&page=1"),
          api("/api/meta"),
        ]);
        grid.innerHTML = pop.listings.slice(0, 4).map(card).join("") || emptyBox("Belum ada barang.");
        newest.innerHTML = fresh.listings.slice(4, 10).map(card).join("") || emptyBox("Belum ada barang lain.");
        const cats = $("#cats");
        if (cats) cats.innerHTML = meta.categories.map(c =>
          `<a class="tag lav" style="text-decoration:none" href="/jelajah.html?category=${encodeURIComponent(c)}">${esc(c)}</a>`).join("");
        $("#stat-total").textContent = fresh.total;
      } catch (e) {
        grid.innerHTML = emptyBox("Gagal memuat: " + e.message);
      }
    },

    async jelajah() {
      const grid = $("#results");
      const form = $("#filter");
      const meta = await api("/api/meta").catch(() => ({ cities: [], categories: [], conditions: [] }));
      const fill = (sel, items, label) => {
        const el = $(sel);
        if (!el) return;
        el.innerHTML = `<option value="">${label}</option>` + items.map(i => `<option>${esc(i)}</option>`).join("");
      };
      fill("#f-city", meta.cities, "Semua kota");
      fill("#f-cat", meta.categories, "Semua kategori");
      fill("#f-cond", meta.conditions, "Semua kondisi");

      const params = new URLSearchParams(location.search);
      ["q", "city", "category", "condition", "min", "max", "sort"].forEach(k => {
        const el = form.elements[k];
        if (el && params.get(k)) el.value = params.get(k);
      });

      async function run(page = 1) {
        grid.innerHTML = skeletonGrid(8);
        const fd = new FormData(form);
        const p = new URLSearchParams();
        fd.forEach((v, k) => { if (v) p.set(k, v); });
        p.set("page", page);
        history.replaceState(null, "", "?" + p.toString());
        try {
          const d = await api("/api/listings?" + p.toString());
          grid.innerHTML = d.listings.map(card).join("") || emptyBox("Tidak ada barang yang cocok. Coba longgarkan filter.");
          $("#count").textContent = `${d.total} barang · halaman ${d.page} dari ${d.pages}`;
          $("#pager").innerHTML = Array.from({ length: d.pages }, (_, i) =>
            `<button class="btn sm${i + 1 === d.page ? " primary" : ""}" data-page="${i + 1}">${i + 1}</button>`).join("");
        } catch (e) {
          grid.innerHTML = emptyBox("Gagal memuat: " + e.message);
        }
      }
      form.addEventListener("submit", e => { e.preventDefault(); run(1); });
      form.addEventListener("reset", () => setTimeout(() => run(1), 0));
      $("#pager").addEventListener("click", e => {
        const b = e.target.closest("[data-page]");
        if (b) run(Number(b.dataset.page));
      });
      run(Number(params.get("page") || 1));
    },

    async listing() {
      const id = qs("id");
      const host = $("#detail");
      if (!id) { host.innerHTML = emptyBox("Listing tidak ditemukan."); return; }
      let d;
      try { d = (await api(`/api/listings/${id}`)).listing; }
      catch (e) { host.innerHTML = emptyBox(e.message); return; }
      const l = d;
      document.title = `${l.title} — ${l.price_text} | JualinAja`;
      const photos = l.photos.length ? l.photos : [];
      const gallery = `<div class="gallery">
        <div class="main" id="big">${photos[0] ? `<img src="/uploads/${esc(photos[0])}" alt="${esc(l.title)}">` : `<span class="mono muted">Tanpa foto</span>`}</div>
        ${photos.length > 1 ? `<div class="thumbs" role="group" aria-label="Foto barang">` + photos.map((p, i) =>
          `<button type="button" data-i="${i}" aria-pressed="${i === 0}"><img src="/uploads/${esc(p)}" alt="Foto ${i + 1}"></button>`).join("") + `</div>` : ""}
      </div>`;
      const sellerLink = `<a href="/profil.html?id=${l.seller.id}">${esc(l.seller.name)}</a>`;
      host.innerHTML = `
        <div class="stack">
          ${gallery}
          <article class="card card-pad stack">
            <div><span class="tag lav">${esc(l.category)}</span> <span class="tag">${esc(l.condition)}</span></div>
            <h1>${esc(l.title)}</h1>
            <div class="price-big">${esc(l.price_text)}</div>
            <dl class="kv">
              <dt>Kota</dt><dd>${esc(l.city)}</dd>
              <dt>Kondisi</dt><dd>${esc(l.condition)}</dd>
              <dt>Dilihat</dt><dd>${l.views} kali</dd>
              <dt>Dipasang</dt><dd>${new Date(l.created).toLocaleString("id-ID")}</dd>
            </dl>
            <div style="white-space:pre-wrap">${esc(l.description) || '<span class="muted">Tanpa deskripsi.</span>'}</div>
            ${l.reviews.length ? `<div class="card card-pad" style="box-shadow:none">
              <h3>Ulasan (${l.reviews.length})</h3>
              ${l.reviews.map(r => `<p style="margin:.4em 0"><strong>${"★".repeat(r.stars)}${"☆".repeat(5 - r.stars)}</strong> ${esc(r.body)} <span class="muted">— ${esc(r.author)}</span></p>`).join("")}
            </div>` : ""}
          </article>
        </div>
        <aside class="stack">
          <div class="card card-pad stack">
            <div>
              <div class="mono muted">Penjual</div>
              <h3 style="margin:.2em 0">${sellerLink}</h3>
              <div class="muted" style="font-size:13px">${esc(l.seller.city || "")}${l.seller.rating ? ` · ${l.seller.rating}★ (${l.seller.reviews})` : ""}</div>
              ${l.seller.bio ? `<p style="font-size:13px">${esc(l.seller.bio)}</p>` : ""}
            </div>
            <div id="actions" class="stack"></div>
          </div>
          <div class="card card-pad stack" id="chatbox">
            <div class="mono muted">Tanya penjual</div>
            <div class="chat" id="chat"></div>
            <form id="chat-form" class="stack" style="gap:8px">
              <label class="field"><span class="sr">Pesan</span>
                <input name="body" placeholder="Masih ada?" maxlength="2000" autocomplete="off" required></label>
              <button class="btn primary" type="submit">Kirim</button>
            </form>
          </div>
        </aside>`;

      const big = $("#big");
      $(".thumbs")?.addEventListener("click", e => {
        const b = e.target.closest("button[data-i]");
        if (!b) return;
        $$(".thumbs button").forEach(x => x.setAttribute("aria-pressed", "false"));
        b.setAttribute("aria-pressed", "true");
        big.innerHTML = `<img src="/uploads/${esc(photos[Number(b.dataset.i)])}" alt="${esc(l.title)}">`;
      });

      /* actions */
      const act = $("#actions");
      const u = Auth.user;
      if (!u) {
        act.innerHTML = `<a class="btn primary full" href="/masuk.html?next=${encodeURIComponent(location.pathname + location.search)}">Masuk untuk menawar</a>`;
        $("#chatbox").hidden = true;
      } else if (l.is_owner) {
        act.innerHTML = `
          ${l.offers.length ? `<div><div class="mono muted">Tawaran masuk</div>
            <div class="tablewrap"><table><thead><tr><th>Pembeli</th><th class="num">Nilai</th><th>Aksi</th></tr></thead><tbody>
            ${l.offers.map(o => `<tr><td>${esc(o.buyer)}<div class="muted" style="font-size:12px">${esc(o.note || "")}</div></td>
              <td class="num">${rupiah(o.amount)}</td>
              <td>${o.status === "proposed"
                ? `<button class="btn ghost" data-offer="${o.id}" data-act="accept">Terima</button>
                   <button class="btn ghost" data-offer="${o.id}" data-act="decline">Tolak</button>`
                : `<span class="tag ${o.status === "accepted" ? "" : "sold"}">${esc(o.status)}</span>`}</td></tr>`).join("")}
            </tbody></table></div></div>` : `<div class="muted">Belum ada tawaran.</div>`}
          <div class="row tight">
            <button class="btn" id="mark-sold" ${l.status === "sold" ? "disabled" : ""}>${l.status === "sold" ? "Sudah terjual" : "Tandai terjual"}</button>
            <button class="btn danger" id="del">Hapus</button>
          </div>`;
        $("#chatbox").hidden = false;
      } else {
        const mine = l.my_offer;
        act.innerHTML = `
          ${mine ? `<div class="note ${mine.status === "accepted" ? "ok" : ""}">Tawaranmu: <strong>${rupiah(mine.amount)}</strong> — ${esc(mine.status)}</div>` : ""}
          <form id="offer-form" class="stack" style="gap:8px">
            <label class="field"><span class="lbl">Tawar harga</span>
              <input name="amount" type="number" min="1" step="1" value="${mine ? mine.amount : l.price}" required></label>
            <label class="field"><span class="lbl">Pesan (opsional)</span>
              <input name="note" maxlength="500" placeholder="Bisa ambil sore ini"></label>
            <button class="btn primary" type="submit">${mine ? "Perbarui tawaran" : "Kirim tawaran"}</button>
          </form>
          <div class="row tight">
            <button class="btn ghost" id="save">${l.saved ? "♥ Tersimpan" : "♡ Simpan"}</button>
            <button class="btn ghost" id="report">Laporkan</button>
          </div>`;
        $("#offer-form").addEventListener("submit", async e => {
          e.preventDefault();
          const fd = new FormData(e.target);
          try {
            await api("/api/offers", { method: "POST", body: {
              listing_id: Number(id), amount: Number(fd.get("amount")), note: fd.get("note") } });
            toast("Tawaran terkirim");
            setTimeout(() => location.reload(), 500);
          } catch (err) { toast(err.message, true); }
        });
        $("#save").addEventListener("click", async e => {
          try {
            if (l.saved) { await api(`/api/saved/${id}`, { method: "DELETE" }); l.saved = false; e.target.textContent = "♡ Simpan"; }
            else { await api(`/api/saved/${id}`, { method: "POST" }); l.saved = true; e.target.textContent = "♥ Tersimpan"; }
          } catch (err) { toast(err.message, true); }
        });
        $("#report").addEventListener("click", async () => {
          const reason = prompt("Alasan laporan? (mis. penipuan, barang palsu, spam)");
          if (!reason) return;
          try { await api("/api/reports", { method: "POST", body: { listing_id: Number(id), reason } }); toast("Laporan terkirim"); }
          catch (err) { toast(err.message, true); }
        });
      }

      act.addEventListener("click", async e => {
        const b = e.target.closest("[data-offer]");
        if (b) {
          try {
            await api(`/api/offers/${b.dataset.offer}/${b.dataset.act}`, { method: "POST" });
            toast(`Tawaran di-${b.dataset.act === "accept" ? "terima" : "tolak"}`);
            setTimeout(() => location.reload(), 500);
          } catch (err) { toast(err.message, true); }
        }
        if (e.target.id === "mark-sold") {
          try { await api(`/api/listings/${id}`, { method: "PATCH", body: { status: "sold" } }); toast("Ditandai terjual"); setTimeout(() => location.reload(), 500); }
          catch (err) { toast(err.message, true); }
        }
        if (e.target.id === "del") {
          if (!confirm("Hapus listing ini? Tidak bisa dibatalkan.")) return;
          try { await api(`/api/listings/${id}`, { method: "DELETE" }); toast("Listing dihapus"); setTimeout(() => location.href = "/akun.html", 500); }
          catch (err) { toast(err.message, true); }
        }
      });

      /* chat */
      if (u && !$("#chatbox").hidden) {
        async function loadChat() {
          try {
            const d = await api(`/api/messages?listing_id=${id}`);
            const box = $("#chat");
            box.innerHTML = d.messages.length ? d.messages.map(m =>
              `<div class="msg ${m.mine ? "me" : "them"}"><span class="who">${esc(m.sender)}</span>${esc(m.body)}</div>`).join("")
              : `<div class="muted" style="font-size:13px">Belum ada pesan. Tanya dulu, barangnya masih ada?</div>`;
            box.scrollTop = box.scrollHeight;
          } catch (e) { /* silent */ }
        }
        loadChat();
        $("#chat-form").addEventListener("submit", async e => {
          e.preventDefault();
          const input = e.target.elements.body;
          const body = input.value.trim();
          if (!body) return;
          const payload = { listing_id: Number(id), body };
          if (l.is_owner) {
            const other = l.offers.find(o => o.status === "accepted") || l.offers[0];
            if (other && other.buyer_id) payload.to = other.buyer_id;
          }
          try {
            await api("/api/messages", { method: "POST", body: payload });
            input.value = "";
            loadChat();
          } catch (err) { toast(err.message, true); }
        });
      }
    },

    async jual() {
      if (!Auth.user) { location.href = "/masuk.html?next=/jual.html"; return; }
      const meta = await api("/api/meta").catch(() => ({ cities: [], categories: [], conditions: [] }));
      const form = $("#form");
      form.city.innerHTML = meta.cities.map(c => `<option>${esc(c)}</option>`).join("");
      form.category.innerHTML = meta.categories.map(c => `<option>${esc(c)}</option>`).join("");
      form.condition.innerHTML = meta.conditions.map(c => `<option>${esc(c)}</option>`).join("");
      const preview = $("#preview");
      const fileInput = $("#photos");
      let files = [];
      fileInput.addEventListener("change", () => {
        files = [...fileInput.files].slice(0, 10);
        preview.innerHTML = files.map((f, i) =>
          `<figure style="margin:0;border:3px solid #1b1524;background:#fff">
            <img src="${URL.createObjectURL(f)}" alt="" style="width:100%;aspect-ratio:1;object-fit:cover;display:block;border-bottom:3px solid #1b1524">
            <figcaption class="mono" style="padding:4px 6px;font-size:10px">${i + 1}. ${esc(f.name.slice(0, 18))}</figcaption>
          </figure>`).join("");
      });
      form.addEventListener("submit", async e => {
        e.preventDefault();
        const btn = $("#submit");
        btn.disabled = true;
        btn.textContent = "Menyimpan…";
        try {
          const fd = new FormData(form);
          const payload = {
            title: fd.get("title"), description: fd.get("description"),
            price: Number(fd.get("price")), category: fd.get("category"),
            condition: fd.get("condition"), city: fd.get("city"),
          };
          const { id } = await api("/api/listings", { method: "POST", body: payload });
          if (files.length) {
            const photoForm = new FormData();
            files.forEach(f => photoForm.append("photo", f));
            await api(`/api/listings/${id}/photos`, { method: "POST", form: photoForm });
          }
          toast("Listing terpasang");
          setTimeout(() => location.href = `/listing.html?id=${id}`, 500);
        } catch (err) {
          toast(err.message, true);
          btn.disabled = false;
          btn.textContent = "Pasang barang";
        }
      });
    },

    async cari() {
      const meta = await api("/api/meta").catch(() => ({ cities: [] }));
      const citySel = $("#w-city");
      if (citySel) citySel.innerHTML = `<option value="">Semua kota</option>` + meta.cities.map(c => `<option>${esc(c)}</option>`).join("");
      async function load() {
        const host = $("#wanted");
        host.innerHTML = skeletonGrid(3);
        try {
          const city = citySel?.value || "";
          const d = await api("/api/wanted" + (city ? "?city=" + encodeURIComponent(city) : ""));
          host.innerHTML = d.wanted.length ? d.wanted.map(w => `
            <div class="card card-pad stack" style="gap:8px">
              <div class="meta"><span class="tag open">DICARI</span></div>
              <h3 style="margin:0">${esc(w.title)}</h3>
              <div class="price">${esc(w.budget)}</div>
              <div class="muted" style="font-size:13px">${esc(w.description || "")}</div>
              <div class="meta"><span>${esc(w.city)}</span><span>${esc(w.owner)}</span></div>
            </div>`).join("") : emptyBox("Belum ada permintaan di kota ini.");
        } catch (e) { host.innerHTML = emptyBox(e.message); }
      }
      citySel?.addEventListener("change", load);
      load();
      const form = $("#wform");
      if (!Auth.user) { form.hidden = true; $("#login-hint").hidden = false; return; }
      form.city.innerHTML = meta.cities.map(c => `<option${c === (Auth.user.city || "") ? " selected" : ""}>${esc(c)}</option>`).join("");
      form.addEventListener("submit", async e => {
        e.preventDefault();
        const fd = new FormData(form);
        try {
          await api("/api/wanted", { method: "POST", body: {
            title: fd.get("title"), description: fd.get("description"),
            budget_min: Number(fd.get("budget_min") || 0), budget_max: Number(fd.get("budget_max") || 0),
            city: fd.get("city"),
          } });
          toast("Permintaan dipasang");
          form.reset();
          load();
        } catch (err) { toast(err.message, true); }
      });
    },

    async akun() {
      if (!Auth.user) { location.href = "/masuk.html?next=/akun.html"; return; }
      const u = Auth.user;
      $("#who").textContent = u.name;
      $("#who-sub").textContent = `${u.email} · ${u.role === "moderator" ? "Moderator" : "Penjual"}`;
      const tabs = $("#tabs");
      const pane = $("#pane");

      const views = {
        listings: async () => {
          const d = await api("/api/me/listings");
          if (!d.listings.length) return emptyBox("Kamu belum memasang barang. <a href='/jual.html'>Pasang sekarang</a>.");
          return `<div class="tablewrap"><table><thead><tr><th>Barang</th><th class="num">Harga</th><th class="num">Tawaran</th><th class="num">Pesan</th><th>Status</th></tr></thead><tbody>
            ${d.listings.map(l => `<tr>
              <td><a href="/listing.html?id=${l.id}">${esc(l.title)}</a><div class="muted" style="font-size:12px">${esc(l.city)}</div></td>
              <td class="num">${esc(l.price_text)}</td>
              <td class="num">${l.offers || 0}</td>
              <td class="num">${l.unread || 0}</td>
              <td><span class="tag ${l.status === "sold" ? "sold" : ""}">${esc(l.status)}</span></td>
            </tr>`).join("")}</tbody></table></div>`;
        },
        saved: async () => {
          const d = await api("/api/saved");
          return d.saved.length ? `<div class="grid">${d.saved.map(card).join("")}</div>`
            : emptyBox("Belum ada barang tersimpan.");
        },
        notif: async () => {
          const d = await api("/api/notifications");
          await api("/api/notifications/read", { method: "POST" }).catch(() => {});
          refreshNotifs();
          return d.notifications.length ? `<div class="tablewrap"><table><thead><tr><th>Notifikasi</th><th class="num">Waktu</th></tr></thead><tbody>
            ${d.notifications.map(n => `<tr><td>${n.link ? `<a href="${esc(n.link)}">${esc(n.body)}</a>` : esc(n.body)}
              <div class="muted" style="font-size:12px">${esc(n.kind)}</div></td>
              <td class="num">${new Date(n.created).toLocaleString("id-ID")}</td></tr>`).join("")}</tbody></table></div>`
            : emptyBox("Belum ada notifikasi.");
        },
      };
      async function show(name) {
        $$("#tabs button").forEach(b => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
        pane.innerHTML = skeletonGrid(2);
        try { pane.innerHTML = await views[name](); }
        catch (e) { pane.innerHTML = emptyBox(e.message); }
      }
      tabs.addEventListener("click", e => {
        const b = e.target.closest("button[data-tab]");
        if (b) show(b.dataset.tab);
      });
      show("listings");
    },

    async profil() {
      const id = qs("id");
      if (!id) { $("#profile").innerHTML = emptyBox("Profil tidak ditemukan."); return; }
      try {
        const d = await api(`/api/listings?seller=${id}`).catch(() => null);
        const grid = $("#profile");
        grid.innerHTML = `<p class="muted">Profil penjual ada di halaman listing.</p>`;
      } catch { $("#profile").innerHTML = emptyBox("Profil tidak ditemukan."); }
    },

    async masuk() {
      await Auth.load();
      if (Auth.user) { location.href = qs("next") || "/akun.html"; return; }
      const tabs = $$(".tabs button");
      const form = $("#auth-form");
      const title = $("#auth-title");
      let mode = "login";
      tabs.forEach(b => b.addEventListener("click", () => {
        mode = b.dataset.mode;
        tabs.forEach(x => x.setAttribute("aria-selected", String(x === b)));
        title.textContent = mode === "login" ? "Masuk" : "Buat akun";
        $("#reg-only").hidden = mode === "login";
        $("#submit").textContent = mode === "login" ? "Masuk" : "Daftar";
        $("#err").hidden = true;
      }));
      form.addEventListener("submit", async e => {
        e.preventDefault();
        const btn = $("#submit");
        btn.disabled = true;
        $("#err").hidden = true;
        const fd = new FormData(form);
        try {
          if (mode === "login") await Auth.login(fd.get("email"), fd.get("password"));
          else await Auth.register({ email: fd.get("email"), name: fd.get("name"), password: fd.get("password"), city: fd.get("city") });
          location.href = qs("next") || "/akun.html";
        } catch (err) {
          const box = $("#err");
          box.textContent = err.message;
          box.hidden = false;
          btn.disabled = false;
        }
      });
    },
  };

  function emptyBox(html) {
    return `<div class="card card-pad" style="grid-column:1/-1;text-align:center;padding:36px 18px">
      <div class="mono muted" style="margin-bottom:8px">KOSONG</div><div>${html}</div></div>`;
  }

  /* ---------------- boot ---------------- */
  document.addEventListener("DOMContentLoaded", async () => {
    await Auth.load();
    paintHeader();
    const page = document.body.dataset.page;
    if (page && Pages[page]) {
      try { await Pages[page](); }
      catch (e) { console.error(e); toast("Gagal memuat halaman: " + e.message, true); }
    }
  });

  window.JA = { api, rupiah, esc, toast, Auth };
})();
