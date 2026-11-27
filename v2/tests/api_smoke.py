#!/usr/bin/env python3
"""
Uji asap API JualinAja. Hanya stdlib — jalankan terhadap server yang hidup.

    python3 app/server.py 8123 &
    python3 tests/api_smoke.py http://127.0.0.1:8123

Cetak "N ok, M gagal" dan keluar dengan kode 1 kalau ada yang gagal.
"""
import http.cookiejar
import json
import mimetypes
import sys
import urllib.error
import urllib.request
import uuid

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8123").rstrip("/")
ok = fail = 0
FAILED = []


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ok    {name}")
    else:
        fail += 1
        FAILED.append(name)
        print(f"  GAGAL {name} {detail}")


class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def call(self, method, path, payload=None, files=None, raw=False):
        url = BASE + path
        headers = {}
        data = None
        if files is not None:
            boundary = "----ja" + uuid.uuid4().hex
            chunks = []
            for name, filename, content in files:
                ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                chunks.append(f"--{boundary}\r\n".encode())
                chunks.append(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode())
                chunks.append(f"Content-Type: {ctype}\r\n\r\n".encode())
                chunks.append(content + b"\r\n")
            chunks.append(f"--{boundary}--\r\n".encode())
            data = b"".join(chunks)
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=20) as res:
                body = res.read()
                return res.status, (body if raw else json.loads(body or b"{}")), dict(res.headers)
        except urllib.error.HTTPError as e:
            body = e.read()
            try:
                parsed = json.loads(body or b"{}")
            except Exception:
                parsed = {"raw": body[:200].decode("utf-8", "replace")}
            return e.code, parsed, dict(e.headers)


PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
       b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00"
       b"\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")

tag = uuid.uuid4().hex[:8]


def section(title):
    print(f"\n{title}")


def main():
    seller, buyer, moderator = Client(), Client(), Client()

    section("statis")
    st, body, _ = seller.call("GET", "/index.html", raw=True)
    check("beranda 200", st == 200 and b"JualinAja" in body, f"status {st}")
    st, body, _ = seller.call("GET", "/assets/app.js", raw=True)
    check("app.js disajikan", st == 200 and b"JualinAja client" in body, f"status {st}")
    st, body, _ = seller.call("GET", "/404.html", raw=True)
    check("halaman 404 disajikan", st == 200 and b"tidak ada" in body, f"status {st}")
    st, body, _ = seller.call("GET", "/halaman-tidak-ada", raw=True)
    check("path asing jatuh ke 404", st == 404, f"status {st}")
    st, body, _ = seller.call("GET", "/../data/jualinaja.db", raw=True)
    check("path traversal ditolak", st in (403, 404), f"status {st}")

    section("meta")
    st, d, _ = seller.call("GET", "/api/meta")
    check("meta 200", st == 200 and d["ok"])
    check("kategori terisi", len(d["categories"]) == 10, str(len(d["categories"])))
    check("kota terisi", len(d["cities"]) >= 10)

    section("auth")
    st, d, _ = seller.call("POST", "/api/auth/register",
                           {"email": f"uji-{tag}@example.com", "name": "Uji Penjual",
                            "password": "rahasia123", "city": "Bandung"})
    check("registrasi 201", st == 201 and d["ok"], str(d))
    check("kata sandi tidak dikembalikan", "password" not in d.get("user", {}))
    st, d, _ = seller.call("POST", "/api/auth/register",
                           {"email": f"uji-{tag}@example.com", "name": "Dobel", "password": "rahasia123"})
    check("email duplikat ditolak 409", st == 409, f"status {st}")
    st, d, _ = seller.call("POST", "/api/auth/register",
                           {"email": "bukan-email", "name": "X", "password": "pendek"})
    check("registrasi tidak valid 400", st == 400, f"status {st}")
    st, d, _ = seller.call("POST", "/api/auth/login",
                           {"email": f"uji-{tag}@example.com", "password": "rahasia123"})
    check("login 200", st == 200 and d["user"]["name"] == "Uji Penjual", str(d))
    st, d, _ = seller.call("POST", "/api/auth/login",
                           {"email": f"uji-{tag}@example.com", "password": "salah-banget"})
    check("login salah 401", st == 401, f"status {st}")
    st, d, _ = seller.call("GET", "/api/auth/me")
    check("sesi terbaca", st == 200 and d["user"] and d["user"]["name"] == "Uji Penjual")

    buyer_email = f"pembeli-{tag}@example.com"
    st, d, _ = buyer.call("POST", "/api/auth/register",
                          {"email": buyer_email, "name": "Uji Pembeli",
                           "password": "rahasia456", "city": "Jakarta"})
    check("registrasi pembeli 201", st == 201, str(d))
    st, d, _ = moderator.call("POST", "/api/auth/login",
                              {"email": "moderator@example.com", "password": "demo1234"})
    check("moderator bisa masuk", st == 200 and d["user"]["role"] == "moderator", str(d))

    section("tulis butuh sesi")
    st, d, _ = Client().call("POST", "/api/listings",
                             {"title": "Tanpa sesi", "price": 1000, "category": "Elektronik",
                              "condition": "Baru", "city": "Bandung"})
    check("tanpa sesi 401", st == 401, f"status {st}")

    section("listing")
    st, d, _ = seller.call("POST", "/api/listings",
                           {"title": "Kamera uji otomatis", "description": "Body saja.",
                            "price": 1500000, "category": "Elektronik",
                            "condition": "Bekas bagus", "city": "Bandung"})
    check("buat listing 201", st == 201 and d.get("id"), str(d))
    lid = d.get("id")
    st, d, _ = seller.call("POST", "/api/listings",
                           {"title": "ab", "price": 0, "category": "Ngawur",
                            "condition": "Ngawur", "city": ""})
    check("listing tidak valid 400", st == 400, f"status {st}")
    st, d, _ = seller.call("POST", "/api/listings",
                           {"title": "Kamera uji salah kategori", "price": 1000,
                            "category": "Tidak Ada", "condition": "Baru", "city": "Bandung"})
    check("kategori asing 400", st == 400, f"status {st}")

    st, d, _ = seller.call("GET", f"/api/listings/{lid}")
    check("detail listing 200", st == 200 and d["listing"]["id"] == lid)
    check("pemilik terdeteksi", d["listing"]["is_owner"] is True)
    check("deskripsi ikut", d["listing"]["description"] == "Body saja.")

    st, d, _ = seller.call("PATCH", f"/api/listings/{lid}",
                           {"title": "Kamera uji otomatis v2"})
    check("pemilik bisa ubah 200", st == 200, str(d))
    st, d, _ = buyer.call("PATCH", f"/api/listings/{lid}", {"title": "Dibajak"})
    check("bukan pemilik tidak bisa ubah 403", st == 403, f"status {st}")
    st, d, _ = seller.call("PATCH", f"/api/listings/{lid}", {"title": "ab"})
    check("ubah judul terlalu pendek 400", st == 400, f"status {st}")

    section("foto")
    st, d, _ = seller.call("POST", f"/api/listings/{lid}/photos",
                           files=[("photo", "a.png", PNG)])
    check("unggah foto 201", st == 201 and d.get("photos"), str(d))
    photo = d["photos"][0] if d.get("photos") else None
    if photo:
        st, body, _ = buyer.call("GET", f"/uploads/{photo}", raw=True)
        check("foto bisa diambil", st == 200 and body.startswith(b"\x89PNG"), f"status {st}")
    st, d, _ = buyer.call("POST", f"/api/listings/{lid}/photos",
                          files=[("photo", "b.png", PNG)])
    check("bukan pemilik tidak bisa unggah 403", st == 403, f"status {st}")
    st, d, _ = seller.call("POST", f"/api/listings/{lid}/photos",
                           files=[("photo", "x.txt", b"bukan gambar")])
    check("berkas non-gambar 400", st == 400, f"status {st}")

    section("jelajah dan filter")
    st, d, _ = buyer.call("GET", "/api/listings?q=otomatis")
    check("cari kata kunci menemukan", st == 200 and any(l["id"] == lid for l in d["listings"]))
    st, d, _ = buyer.call("GET", "/api/listings?city=Bandung&category=Elektronik")
    check("filter kota+kategori", st == 200 and all(
        l["city"] == "Bandung" and l["category"] == "Elektronik" for l in d["listings"]))
    st, d, _ = buyer.call("GET", "/api/listings?sort=cheap")
    prices = [l["price"] for l in d["listings"]]
    check("sort=cheap terurut naik", prices == sorted(prices), str(prices[:5]))
    st, d, _ = buyer.call("GET", "/api/listings?min=1000000&max=2000000")
    check("filter harga rentang", st == 200 and all(1000000 <= l["price"] <= 2000000 for l in d["listings"]))
    st, d, _ = buyer.call("GET", "/api/listings?page=999")
    check("halaman jauh kosong tapi 200", st == 200 and d["listings"] == [])

    section("tawaran")
    st, d, _ = buyer.call("POST", "/api/offers",
                          {"listing_id": lid, "amount": 1300000, "note": "Bisa ambil sore"})
    check("kirim tawaran 201", st == 201 and d.get("id"), str(d))
    offer_id = d.get("id")
    st, d, _ = seller.call("POST", "/api/offers",
                           {"listing_id": lid, "amount": 1000})
    check("tawar barang sendiri 400", st == 400, f"status {st}")
    st, d, _ = buyer.call("POST", "/api/offers",
                          {"listing_id": lid, "amount": 1400000})
    check("tawar ulang memperbarui", st == 201 and d.get("id") == offer_id, str(d))
    st, d, _ = buyer.call("POST", f"/api/offers/{offer_id}/accept")
    check("pembeli tidak bisa terima 403", st == 403, f"status {st}")
    st, d, _ = seller.call("GET", f"/api/listings/{lid}")
    check("penjual lihat tawaran", len(d["listing"]["offers"]) >= 1, str(d["listing"]["offers"]))
    st, d, _ = seller.call("POST", f"/api/offers/{offer_id}/accept")
    check("penjual bisa terima 200", st == 200, str(d))
    st, d, _ = seller.call("GET", f"/api/listings/{lid}")
    check("tawaran jadi accepted", d["listing"]["offers"][0]["status"] == "accepted")

    section("chat")
    st, d, _ = buyer.call("POST", "/api/messages", {"listing_id": lid, "body": "Masih ada?"})
    check("pembeli kirim pesan 201", st == 201, str(d))
    st, d, _ = seller.call("GET", f"/api/messages?listing_id={lid}")
    check("penjual lihat pesan", st == 200 and len(d["messages"]) == 1, str(d))
    check("pesan bukan milik penjual", d["messages"][0]["mine"] is False)
    st, d, _ = buyer.call("GET", f"/api/messages?listing_id={lid}")
    check("pesan ditandai terbaca", st == 200 and d["messages"][0]["mine"] is True)
    st, d, _ = buyer.call("POST", "/api/messages", {"listing_id": lid, "body": ""})
    check("pesan kosong ditolak 400", st == 400, f"status {st}")

    section("ulasan")
    st, d, _ = buyer.call("POST", "/api/reviews", {"listing_id": lid, "stars": 5, "body": "Mantap"})
    check("ulasan setelah diterima 201", st == 201, str(d))
    st, d, _ = buyer.call("POST", "/api/reviews", {"listing_id": lid, "stars": 4})
    check("ulasan ganda 409", st == 409, f"status {st}")
    st, d, _ = seller.call("POST", "/api/reviews", {"listing_id": lid, "stars": 5})
    check("tanpa tawaran diterima tidak bisa ulas 403", st == 403, f"status {st}")
    st, d, _ = buyer.call("POST", "/api/reviews", {"listing_id": lid, "stars": 9})
    check("bintang di luar 1-5 ditolak", st in (400, 409), f"status {st}")

    section("simpan")
    st, d, _ = buyer.call("POST", f"/api/saved/{lid}")
    check("simpan 201", st == 201 and d["saved"] is True, str(d))
    st, d, _ = buyer.call("GET", "/api/saved")
    check("daftar tersimpan berisi", any(x["id"] == lid for x in d["saved"]))
    st, d, _ = buyer.call("DELETE", f"/api/saved/{lid}")
    check("hapus tersimpan", st == 200 and d["saved"] is False)
    st, d, _ = buyer.call("GET", "/api/saved")
    check("tersimpan kosong lagi", not any(x["id"] == lid for x in d["saved"]))

    section("papan cari")
    st, d, _ = seller.call("POST", "/api/wanted",
                           {"title": "Cari lensa uji otomatis", "description": "50mm",
                            "budget_min": 500000, "budget_max": 900000, "city": "Bandung"})
    check("pasang wanted 201", st == 201 and d.get("id"), str(d))
    st, d, _ = buyer.call("GET", "/api/wanted?city=Bandung")
    check("wanted terfilter kota", st == 200 and any("otomatis" in w["title"] for w in d["wanted"]))
    st, d, _ = seller.call("POST", "/api/wanted",
                           {"title": "Budget terbalik", "budget_min": 900000, "budget_max": 100})
    check("rentang budget terbalik 400", st == 400, f"status {st}")

    section("notifikasi")
    st, d, _ = seller.call("GET", "/api/notifications")
    check("penjual punya notifikasi", st == 200 and d["unread"] >= 1, str(d.get("unread")))
    st, d, _ = Client().call("GET", "/api/notifications")
    check("tamu tidak melihat notifikasi", st == 200 and d["unread"] == 0)
    st, d, _ = seller.call("POST", "/api/notifications/read")
    check("tandai terbaca 200", st == 200, str(d))
    st, d, _ = seller.call("GET", "/api/notifications")
    check("tidak ada sisa belum dibaca", d["unread"] == 0, str(d.get("unread")))

    section("laporan dan blokir")
    st, d, _ = buyer.call("POST", "/api/reports",
                          {"listing_id": lid, "reason": "uji otomatis", "detail": "bukan barang asli"})
    check("laporan 201", st == 201, str(d))
    st, d, _ = moderator.call("GET", "/api/moderation/reports")
    check("moderator lihat laporan", st == 200 and any(
        r["reason"] == "uji otomatis" for r in d["reports"]), str(d)[:200])
    st, d, _ = buyer.call("GET", "/api/moderation/reports")
    check("non-moderator 403", st == 403, f"status {st}")
    st, d, _ = buyer.call("POST", "/api/blocks", {"user_id": 1})
    check("blokir 201", st == 201, str(d))
    st, d, _ = buyer.call("POST", "/api/blocks", {"user_id": 0})
    check("blokir target tidak valid 400", st == 400, f"status {st}")

    section("halaman OG")
    st, body, _ = Client().call("GET", f"/p/{lid}", raw=True)
    text = body.decode("utf-8", "replace")
    check("OG 200", st == 200, f"status {st}")
    check("og:title ada", 'property="og:title"' in text)
    check("harga di judul OG", "Rp1.500.000" in text, text[:200])
    check("judul user ter-escape", "<script>" not in text)

    section("otorisasi hapus")
    st, d, _ = buyer.call("DELETE", f"/api/listings/{lid}")
    check("bukan pemilik tidak bisa hapus 403", st == 403, f"status {st}")
    st, d, _ = seller.call("DELETE", f"/api/listings/{lid}")
    check("pemilik bisa hapus 200", st == 200, str(d))
    st, d, _ = seller.call("GET", f"/api/listings/{lid}")
    check("setelah dihapus 404", st == 404, f"status {st}")

    section("logout")
    st, d, _ = seller.call("POST", "/api/auth/logout")
    check("logout 200", st == 200, str(d))
    st, d, _ = seller.call("GET", "/api/auth/me")
    check("sesi hilang setelah logout", d["user"] is None, str(d))

    print(f"\n{ok} ok, {fail} gagal")
    if fail:
        print("gagal: " + ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
