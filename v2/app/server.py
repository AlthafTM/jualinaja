#!/usr/bin/env python3
"""
JualinAja — pasar barang bekas antar warga.

Satu file server, tanpa dependensi pihak ketiga:
  * static file + JSON API + unggah foto (multipart, parsing manual)
  * SQLite (WAL, foreign keys) dibuat otomatis di data/jualinaja.db
  * akun: PBKDF2-HMAC-SHA256 + cookie sesi HttpOnly
  * listing, foto, papan cari (wanted), tawaran, chat, ulasan, laporan, blokir,
    simpanan, pencarian tersimpan, notifikasi, moderasi
  * /p/<id> dirender dengan Open Graph tags supaya enak dibagikan

Jalankan:  python3 app/server.py 8123
"""
import base64
import hashlib
import hmac
import http.cookies
import io
import json
import mimetypes
import os
import re
import secrets
import shutil
import sqlite3
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
PHOTOS = DATA / "photos"
DB_PATH = DATA / "jualinaja.db"
STATIC = HERE

MAX_PHOTO_BYTES = 8 * 1024 * 1024
MAX_PHOTOS = 10
PBKDF2_ROUNDS = 240_000
SESSION_TTL = 60 * 60 * 24 * 30

MIME = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif",
    ".ico": "image/x-icon", ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
}

CATEGORIES = ["Elektronik", "Fashion", "Rumah Tangga", "Hobi", "Otomotif", "Bayi & Anak",
              "Buku", "Olahraga", "Kesehatan", "Lainnya"]
CONDITIONS = ["Baru", "Seperti baru", "Bekas bagus", "Bekas", "Perlu perbaikan"]
CITIES = ["Jakarta", "Bandung", "Surabaya", "Yogyakarta", "Semarang", "Medan", "Makassar",
          "Denpasar", "Bekasi", "Depok", "Tangerang", "Bogor", "Malang", "Palembang"]


# --------------------------------------------------------------------------- db
def connect():
    conn = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=8000")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  password TEXT NOT NULL,
  city TEXT,
  bio TEXT,
  avatar TEXT,
  role TEXT NOT NULL DEFAULT 'user',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at REAL NOT NULL,
  expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS listings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  seller_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  price INTEGER NOT NULL,
  category TEXT NOT NULL,
  `condition` TEXT NOT NULL,
  city TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  views INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS photos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  file TEXT NOT NULL,
  position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS wanted (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  budget_min INTEGER NOT NULL DEFAULT 0,
  budget_max INTEGER NOT NULL DEFAULT 0,
  city TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS offers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  buyer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  amount INTEGER NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'proposed',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  UNIQUE(listing_id, buyer_id)
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  recipient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  body TEXT NOT NULL,
  read_at REAL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  offer_id INTEGER NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
  author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  subject_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  stars INTEGER NOT NULL,
  body TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL,
  UNIQUE(listing_id, author_id)
);
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reporter_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  listing_id INTEGER REFERENCES listings(id) ON DELETE CASCADE,
  reason TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS blocks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  blocked_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at REAL NOT NULL,
  UNIQUE(user_id, blocked_id)
);
CREATE TABLE IF NOT EXISTS saved (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  created_at REAL NOT NULL,
  UNIQUE(user_id, listing_id)
);
CREATE TABLE IF NOT EXISTS searches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  query TEXT NOT NULL,
  city TEXT,
  category TEXT,
  seen_at REAL NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  body TEXT NOT NULL,
  link TEXT,
  read_at REAL,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_listings_seller ON listings(seller_id);
CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_to ON messages(recipient_id, read_at);
CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, read_at);
"""


def init_db():
    DATA.mkdir(parents=True, exist_ok=True)
    PHOTOS.mkdir(parents=True, exist_ok=True)
    conn = connect()
    conn.executescript(SCHEMA)
    seeded = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    if not seeded:
        seed(conn)
    conn.close()


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return "pbkdf2${}${}${}".format(PBKDF2_ROUNDS, base64.b64encode(salt).decode(),
                                    base64.b64encode(digest).decode())


def verify_password(password, stored):
    try:
        algo, rounds, salt_b64, digest_b64 = stored.split("$")
        if algo != "pbkdf2":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(rounds))
        return hmac.compare_digest(expected, actual)
    except Exception:
        return False


DEMO_USERS = [
    ("rangga.putra@example.com", "Rangga Putra", "Bandung", "Kolektor kamera analog dan sepeda lipat."),
    ("sri.wahyuni@example.com", "Sri Wahyuni", "Jakarta", "Ibu rumah tangga, suka barang rumah tangga bekas yang masih bagus."),
    ("dimas.wibowo@example.com", "Dimas Wibowo", "Surabaya", "Anak teknik, jual beli laptop dan komponen."),
    ("laras.ayu@example.com", "Laras Ayu", "Yogyakarta", "Suka buku bekas dan tanaman hias."),
    ("agus.pramana@example.com", "Agus Pramana", "Semarang", "Servis motor, kadang jual sparepart sisa."),
    ("bayu.setiawan@example.com", "Bayu Setiawan", "Bekasi", "Gamer, sering tukar-tambah perangkat."),
    ("adit.nugroho@example.com", "Adit Nugroho", "Depok", "Mahasiswa, cari barang murah buat kos."),
    ("fajar.ramadhan@example.com", "Fajar Ramadhan", "Malang", "Fotografer lepas."),
]

DEMO_LISTINGS = [
    ("Kamera Canon AE-1 body only", "Body kamera film, shutter normal, light seal baru diganti. Dikasih strap original.", 1250000, "Elektronik", "Bekas bagus", "Bandung"),
    ("Sepeda lipat 20 inci 7 speed", "Ringan, sudah servis, ban baru. Cocok buat commuting dalam kota.", 1850000, "Olahraga", "Bekas bagus", "Bandung"),
    ("Blender Philips 2 liter", "Masih halus, jar tidak pecah. Garansi habis tapi normal semua.", 275000, "Rumah Tangga", "Bekas bagus", "Jakarta"),
    ("Set panci stainless 5 pcs", "Baru, belum dipakai, dapat hadiah tapi sudah punya.", 420000, "Rumah Tangga", "Baru", "Jakarta"),
    ("Laptop ThinkPad T480 i5", "RAM 16GB, SSD 512, baterai masih 4 jam. Keyboard normal, layar tanpa dead pixel.", 4200000, "Elektronik", "Bekas bagus", "Surabaya"),
    ("RAM DDR4 8GB SODIMM", "Cabut dari laptop upgrade, tes stabil.", 320000, "Elektronik", "Seperti baru", "Surabaya"),
    ("Buku Sapiens hardcover", "Baca sekali, halaman bersih, ada sedikit lipat di jaket.", 95000, "Buku", "Bekas bagus", "Yogyakarta"),
    ("Monstera deliciosa 60cm", "Sehat, sudah berdaun belah, pot tanah liat.", 180000, "Hobi", "Bekas bagus", "Yogyakarta"),
    ("Sparepart karburator motor 125cc", "Baru, salah beli tipe.", 165000, "Otomotif", "Baru", "Semarang"),
    ("Helm half face SNI", "Pemakaian 6 bulan, busa masih bagus, visor bening.", 145000, "Otomotif", "Bekas bagus", "Semarang"),
    ("Nintendo Switch Lite turquoise", "Layar mulus, sudah tempered glass, charger original.", 1950000, "Elektronik", "Bekas bagus", "Bekasi"),
    ("Kursi kerja mesh", "Sandaran mesh, hidrolik masih kuat, ada baret halus di kaki.", 550000, "Rumah Tangga", "Bekas", "Depok"),
    ("Meja lipat kayu 60x40", "Kuat, ringan, bisa dilipat. Buat kerja di kos.", 130000, "Rumah Tangga", "Bekas bagus", "Depok"),
    ("Lensa kit 18-55mm", "Bebas jamur, fokus lancar, ada debu halus di dalam.", 700000, "Elektronik", "Bekas bagus", "Malang"),
    ("Tas kamera kanvas", "Busa tebal, muat 1 body 2 lensa.", 210000, "Hobi", "Bekas bagus", "Malang"),
]

DEMO_WANTED = [
    ("Cari monitor 24 inci IPS", "Buat kerja, minimal 75Hz, budget ketat.", 700000, 1200000, "Jakarta"),
    ("Butuh kursi ergonomis bekas", "Yang hidroliknya masih bagus, boleh baret.", 400000, 900000, "Depok"),
    ("Cari buku belajar Python", "Edisi apa saja, yang penting halamannya lengkap.", 50000, 150000, "Yogyakarta"),
    ("Cari ban sepeda 26 inci", "Masih tebal, bukan yang sudah botak.", 80000, 180000, "Bandung"),
]


def seed(conn):
    now = time.time()
    ids = {}
    for i, (email, name, city, bio) in enumerate(DEMO_USERS):
        cur = conn.execute(
            "INSERT INTO users(email,name,password,city,bio,created_at) VALUES(?,?,?,?,?,?)",
            (email, name, hash_password("demo1234"), city, bio, now - (len(DEMO_USERS) - i) * 86400))
        ids[email] = cur.lastrowid
    moderator = conn.execute(
        "INSERT INTO users(email,name,password,city,bio,role,created_at) VALUES(?,?,?,?,?,?,?)",
        ("moderator@example.com", "Moderator", hash_password("demo1234"), "Jakarta",
         "Menjaga pasar tetap aman.", "moderator", now)).lastrowid
    sellers = list(ids.values())
    for i, (title, desc, price, cat, cond, city) in enumerate(DEMO_LISTINGS):
        seller = sellers[i % len(sellers)]
        created = now - (len(DEMO_LISTINGS) - i) * 3600
        cur = conn.execute(
            "INSERT INTO listings(seller_id,title,description,price,category,`condition`,city,views,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (seller, title, desc, price, cat, cond, city, 3 + (i * 7) % 40, created, created))
        conn.execute("UPDATE listings SET status='sold' WHERE id=?", (cur.lastrowid,)) if i == 4 else None
    for i, (title, desc, lo, hi, city) in enumerate(DEMO_WANTED):
        conn.execute(
            "INSERT INTO wanted(user_id,title,description,budget_min,budget_max,city,created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (sellers[i % len(sellers)], title, desc, lo, hi, city, now - 7200 - i * 3600))
    print(f"seed: {len(sellers)} penjual, 1 moderator, {len(DEMO_LISTINGS)} listing, {len(DEMO_WANTED)} wanted")


# --------------------------------------------------------------------------- helpers
def now():
    return time.time()


def iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def rupiah(n):
    n = int(n or 0)
    s = f"{n:,}".replace(",", ".")
    return f"Rp{s}"


def esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


def clean(s, limit=2000):
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(s or "")).strip()
    return s[:limit]


class ApiError(Exception):
    def __init__(self, status, message, **extra):
        super().__init__(message)
        self.status = status
        self.payload = {"ok": False, "error": message, **extra}


def need(cond, status, message, **extra):
    if not cond:
        raise ApiError(status, message, **extra)


def parse_multipart(body, content_type):
    """Return [(name, filename, content_type, bytes)] for a multipart/form-data body."""
    m = re.search(r'boundary="?([^";]+)"?', content_type or "")
    if not m:
        raise ApiError(400, "boundary multipart tidak ditemukan")
    boundary = b"--" + m.group(1).encode()
    parts = body.split(boundary)
    out = []
    for part in parts:
        if part in (b"--\r\n", b"--", b"", b"\r\n"):
            continue
        part = part.lstrip(b"\r\n")
        if part.startswith(b"--"):
            continue
        head, _, data = part.partition(b"\r\n\r\n")
        if not _:
            continue
        data = data[:-2] if data.endswith(b"\r\n") else data
        text = head.decode("utf-8", "replace")
        name = re.search(r'name="([^"]*)"', text)
        fname = re.search(r'filename="([^"]*)"', text)
        ctype = re.search(r"Content-Type:\s*([^\r\n;]+)", text, re.I)
        out.append((name.group(1) if name else "",
                    fname.group(1) if fname else None,
                    ctype.group(1).strip() if ctype else None,
                    data))
    return out


# --------------------------------------------------------------------------- server
class Handler(BaseHTTPRequestHandler):
    server_version = "JualinAja/1.0"
    protocol_version = "HTTP/1.1"

    # ---- plumbing
    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def _send(self, status, body=b"", ctype="application/json; charset=utf-8", headers=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload, status=200, headers=None):
        self._send(status, json.dumps(payload, ensure_ascii=False),
                   "application/json; charset=utf-8", headers)

    def _cookies(self):
        raw = self.headers.get("Cookie", "")
        c = http.cookies.SimpleCookie()
        try:
            c.load(raw)
        except http.cookies.CookieError:
            pass
        return c

    def current_user(self, conn):
        token = self._cookies().get("sid")
        if not token:
            return None
        row = conn.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id"
            " WHERE s.token=? AND s.expires_at>?", (token.value, now())).fetchone()
        return dict(row) if row else None

    def read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 24 * 1024 * 1024:
            raise ApiError(413, "body terlalu besar")
        return self.rfile.read(length) if length else b""

    def read_json(self):
        body = self.read_body()
        if not body:
            return {}
        try:
            data = json.loads(body)
        except Exception:
            raise ApiError(400, "body bukan JSON yang valid")
        need(isinstance(data, dict), 400, "body harus objek JSON")
        return data

    # ---- verbs
    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PATCH(self):
        self._dispatch("PATCH")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def _dispatch(self, method):
        parsed = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parsed.path)
        self.query = urllib.parse.parse_qs(parsed.query)
        conn = connect()
        try:
            if path.startswith("/api/"):
                self._api(method, path, conn)
            elif path.startswith("/p/"):
                self._og_page(path, conn)
            elif path.startswith("/uploads/"):
                self._file(PHOTOS / os.path.basename(path))
            else:
                self._static(path, conn)
        except ApiError as e:
            self._json(e.payload, e.status)
        except BrokenPipeError:
            pass
        except Exception as e:  # pragma: no cover - keep the server alive
            sys.stderr.write(f"ERROR {method} {path}: {e!r}\n")
            self._json({"ok": False, "error": "kesalahan server: %s" % type(e).__name__}, 500)
        finally:
            conn.close()

    def q(self, name, default=None):
        return (self.query.get(name) or [default])[0]

    def qi(self, name, default=0):
        try:
            return int(self.q(name, default))
        except (TypeError, ValueError):
            return default

    # ---- files
    def _file(self, path):
        if not path.is_file():
            self._send(404, '{"ok":false,"error":"tidak ditemukan"}')
            return
        ctype = MIME.get(path.suffix.lower()) or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self._send(200, path.read_bytes(), ctype, {"Cache-Control": "public, max-age=86400"})

    def _static(self, path, conn):
        if path in ("/", ""):
            path = "/index.html"
        target = (STATIC / path.lstrip("/")).resolve()
        try:
            target.relative_to(STATIC.resolve())
        except ValueError:
            self._send(403, '{"ok":false,"error":"dilarang"}')
            return
        if not target.is_file():
            notfound = STATIC / "404.html"
            body = notfound.read_bytes() if notfound.is_file() else b"<h1>404</h1>"
            self._send(404, body, "text/html; charset=utf-8")
            return
        ctype = MIME.get(target.suffix.lower()) or "application/octet-stream"
        self._send(200, target.read_bytes(), ctype, {"Cache-Control": "no-cache"})

    def _og_page(self, path, conn):
        """Server-rendered listing page with Open Graph tags, for share previews."""
        m = re.match(r"^/p/(\d+)", path)
        if not m:
            self._send(404, b"<h1>404</h1>", "text/html; charset=utf-8")
            return
        row = conn.execute(
            "SELECT l.*, u.name seller FROM listings l JOIN users u ON u.id=l.seller_id WHERE l.id=?",
            (int(m.group(1)),)).fetchone()
        if not row:
            self._send(404, b"<h1>Listing tidak ditemukan</h1>", "text/html; charset=utf-8")
            return
        photo = conn.execute("SELECT file FROM photos WHERE listing_id=? ORDER BY position LIMIT 1",
                             (row["id"],)).fetchone()
        title = f"{row['title']} — {rupiah(row['price'])} | JualinAja"
        desc = clean(row["description"], 160) or f"Dijual di {row['city']} oleh {row['seller']}"
        image = f"/uploads/{photo['file']}" if photo else "/assets/favicon.svg"
        html = f"""<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta property="og:type" content="product"><meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:image" content="{esc(image)}">
<meta property="og:url" content="/p/{row['id']}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/assets/favicon.svg">
</head><body style="font:16px/1.5 system-ui;margin:0;padding:24px;max-width:720px">
<p style="font:12px/1 ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase;color:#7b5ca8">JualinAja</p>
<h1 style="margin:.2em 0">{esc(row['title'])}</h1>
<p style="font-size:24px;font-weight:700">{rupiah(row['price'])}</p>
<p>{esc(desc)}</p>
<p style="color:#666">{esc(row['city'])} · {esc(row['condition'])} · penjual {esc(row['seller'])}</p>
<p><a href="/listing.html?id={row['id']}">Lihat di JualinAja</a></p>
</body></html>"""
        self._send(200, html, "text/html; charset=utf-8")

    # ---- api
    def _api(self, method, path, conn):
        route = path[5:]

        # ------------- auth
        if route == "auth/register" and method == "POST":
            d = self.read_json()
            email = clean(d.get("email"), 160).lower()
            name = clean(d.get("name"), 60)
            password = str(d.get("password") or "")
            city = clean(d.get("city"), 60) or None
            need(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email), 400, "email tidak valid")
            need(len(name) >= 2, 400, "nama minimal 2 karakter")
            need(len(password) >= 8, 400, "kata sandi minimal 8 karakter")
            exists = conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone()
            need(not exists, 409, "email sudah terdaftar")
            uid = conn.execute(
                "INSERT INTO users(email,name,password,city,created_at) VALUES(?,?,?,?,?)",
                (email, name, hash_password(password), city, now())).lastrowid
            return self._login(conn, uid, 201)

        if route == "auth/login" and method == "POST":
            d = self.read_json()
            email = clean(d.get("email"), 160).lower()
            password = str(d.get("password") or "")
            row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            need(row and verify_password(password, row["password"]), 401, "email atau kata sandi salah")
            return self._login(conn, row["id"], 200)

        if route == "auth/logout" and method == "POST":
            token = self._cookies().get("sid")
            if token:
                conn.execute("DELETE FROM sessions WHERE token=?", (token.value,))
            return self._json({"ok": True}, 200, {"Set-Cookie": "sid=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"})

        if route == "auth/me" and method == "GET":
            user = self.current_user(conn)
            if not user:
                return self._json({"ok": True, "user": None})
            return self._json({"ok": True, "user": public_user(user)})

        # ------------- catalogue
        if route == "meta" and method == "GET":
            return self._json({"ok": True, "categories": CATEGORIES, "conditions": CONDITIONS,
                               "cities": CITIES})

        if route == "listings" and method == "GET":
            return self._list_listings(conn)

        if route == "listings" and method == "POST":
            user = self._require_user(conn)
            d = self.read_json()
            title = clean(d.get("title"), 120)
            price = int(d.get("price") or 0)
            category = clean(d.get("category"), 40)
            cond = clean(d.get("condition"), 40)
            city = clean(d.get("city"), 60)
            desc = clean(d.get("description"), 4000)
            need(len(title) >= 4, 400, "judul minimal 4 karakter")
            need(price > 0, 400, "harga harus lebih dari 0")
            need(category in CATEGORIES, 400, "kategori tidak dikenal")
            need(cond in CONDITIONS, 400, "kondisi tidak dikenal")
            need(city, 400, "kota wajib diisi")
            lid = conn.execute(
                "INSERT INTO listings(seller_id,title,description,price,category,`condition`,city,created_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (user["id"], title, desc, price, category, cond, city, now(), now())).lastrowid
            return self._json({"ok": True, "id": lid}, 201)

        m = re.match(r"^listings/(\d+)$", route)
        if m:
            lid = int(m.group(1))
            if method == "GET":
                return self._get_listing(conn, lid)
            if method == "PATCH":
                user = self._require_user(conn)
                row = conn.execute("SELECT * FROM listings WHERE id=?", (lid,)).fetchone()
                need(row, 404, "listing tidak ditemukan")
                need(row["seller_id"] == user["id"] or user["role"] == "moderator", 403,
                     "bukan pemilik listing")
                d = self.read_json()
                fields, values = [], []
                for key, validator in (("title", lambda v: len(clean(v, 120)) >= 4),
                                       ("price", lambda v: int(v) > 0),
                                       ("category", lambda v: v in CATEGORIES),
                                       ("condition", lambda v: v in CONDITIONS),
                                       ("city", lambda v: bool(clean(v, 60))),
                                       ("description", lambda v: True),
                                       ("status", lambda v: v in ("active", "sold", "hidden"))):
                    if key in d:
                        need(validator(d[key]), 400, f"nilai {key} tidak valid")
                        fields.append(f"`{key}`=?")
                        values.append(int(d[key]) if key == "price" else clean(d[key], 4000))
                need(fields, 400, "tidak ada field yang diubah")
                values += [now(), lid]
                conn.execute(f"UPDATE listings SET {', '.join(fields)}, updated_at=? WHERE id=?", values)
                return self._json({"ok": True})
            if method == "DELETE":
                user = self._require_user(conn)
                row = conn.execute("SELECT * FROM listings WHERE id=?", (lid,)).fetchone()
                need(row, 404, "listing tidak ditemukan")
                need(row["seller_id"] == user["id"] or user["role"] == "moderator", 403,
                     "bukan pemilik listing")
                conn.execute("DELETE FROM listings WHERE id=?", (lid,))
                return self._json({"ok": True})

        m = re.match(r"^listings/(\d+)/photos$", route)
        if m and method == "POST":
            user = self._require_user(conn)
            lid = int(m.group(1))
            row = conn.execute("SELECT * FROM listings WHERE id=?", (lid,)).fetchone()
            need(row, 404, "listing tidak ditemukan")
            need(row["seller_id"] == user["id"], 403, "bukan pemilik listing")
            count = conn.execute("SELECT COUNT(*) c FROM photos WHERE listing_id=?", (lid,)).fetchone()["c"]
            need(count < MAX_PHOTOS, 400, f"maksimal {MAX_PHOTOS} foto")
            parts = parse_multipart(self.read_body(), self.headers.get("Content-Type"))
            saved = []
            for name, filename, ctype, data in parts:
                if name != "photo" or not filename:
                    continue
                need(len(data) <= MAX_PHOTO_BYTES, 413, "foto lebih dari 8 MB")
                need((ctype or "").startswith("image/"), 400, "berkas harus gambar")
                ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
                       "image/gif": ".gif"}.get(ctype, ".jpg")
                fname = f"{secrets.token_hex(12)}{ext}"
                (PHOTOS / fname).write_bytes(data)
                pos = conn.execute("SELECT COALESCE(MAX(position),-1)+1 p FROM photos WHERE listing_id=?",
                                   (lid,)).fetchone()["p"]
                conn.execute("INSERT INTO photos(listing_id,file,position) VALUES(?,?,?)",
                             (lid, fname, pos))
                saved.append(fname)
            need(saved, 400, "tidak ada foto yang diterima")
            return self._json({"ok": True, "photos": saved}, 201)

        # ------------- wanted board
        if route == "wanted" and method == "GET":
            city = self.q("city")
            sql = ("SELECT w.*, u.name owner FROM wanted w JOIN users u ON u.id=w.user_id"
                   " WHERE w.status='open'")
            args = []
            if city:
                sql += " AND w.city=?"
                args.append(city)
            sql += " ORDER BY w.created_at DESC LIMIT 60"
            rows = [dict(r) for r in conn.execute(sql, args)]
            for r in rows:
                r["budget"] = f"{rupiah(r['budget_min'])} – {rupiah(r['budget_max'])}"
                r["created"] = iso(r["created_at"])
            return self._json({"ok": True, "wanted": rows})

        if route == "wanted" and method == "POST":
            user = self._require_user(conn)
            d = self.read_json()
            title = clean(d.get("title"), 120)
            lo, hi = int(d.get("budget_min") or 0), int(d.get("budget_max") or 0)
            need(len(title) >= 4, 400, "judul minimal 4 karakter")
            need(hi >= lo >= 0, 400, "rentang budget tidak valid")
            wid = conn.execute(
                "INSERT INTO wanted(user_id,title,description,budget_min,budget_max,city,created_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (user["id"], title, clean(d.get("description"), 2000), lo, hi,
                 clean(d.get("city"), 60) or user.get("city") or "Jakarta", now())).lastrowid
            return self._json({"ok": True, "id": wid}, 201)

        # ------------- offers
        if route == "offers" and method == "POST":
            user = self._require_user(conn)
            d = self.read_json()
            lid, amount = int(d.get("listing_id") or 0), int(d.get("amount") or 0)
            row = conn.execute("SELECT * FROM listings WHERE id=?", (lid,)).fetchone()
            need(row, 404, "listing tidak ditemukan")
            need(row["seller_id"] != user["id"], 400, "tidak bisa menawar barang sendiri")
            need(row["status"] == "active", 400, "listing tidak aktif")
            need(amount > 0, 400, "nilai tawaran harus lebih dari 0")
            existing = conn.execute("SELECT * FROM offers WHERE listing_id=? AND buyer_id=?",
                                    (lid, user["id"])).fetchone()
            if existing:
                conn.execute("UPDATE offers SET amount=?, note=?, status='proposed', updated_at=?"
                             " WHERE id=?", (amount, clean(d.get("note"), 500), now(), existing["id"]))
                oid = existing["id"]
            else:
                oid = conn.execute(
                    "INSERT INTO offers(listing_id,buyer_id,amount,note,created_at,updated_at)"
                    " VALUES(?,?,?,?,?,?)",
                    (lid, user["id"], amount, clean(d.get("note"), 500), now(), now())).lastrowid
            notify(conn, row["seller_id"], "offer", f"Tawaran baru {rupiah(amount)} untuk {row['title']}",
                   f"/listing.html?id={lid}")
            return self._json({"ok": True, "id": oid}, 201)

        m = re.match(r"^offers/(\d+)/(accept|decline|withdraw)$", route)
        if m and method == "POST":
            user = self._require_user(conn)
            oid, action = int(m.group(1)), m.group(2)
            o = conn.execute("SELECT * FROM offers WHERE id=?", (oid,)).fetchone()
            need(o, 404, "tawaran tidak ditemukan")
            listing = conn.execute("SELECT * FROM listings WHERE id=?", (o["listing_id"],)).fetchone()
            if action == "withdraw":
                need(o["buyer_id"] == user["id"], 403, "bukan tawaran kamu")
                conn.execute("UPDATE offers SET status='withdrawn', updated_at=? WHERE id=?", (now(), oid))
            else:
                need(listing["seller_id"] == user["id"], 403, "hanya penjual yang bisa menjawab")
                need(o["status"] == "proposed", 400, "tawaran sudah dijawab")
                status = "accepted" if action == "accept" else "declined"
                conn.execute("UPDATE offers SET status=?, updated_at=? WHERE id=?", (status, now(), oid))
                if status == "accepted":
                    conn.execute("UPDATE offers SET status='declined', updated_at=?"
                                 " WHERE listing_id=? AND id<>? AND status='proposed'",
                                 (now(), o["listing_id"], oid))
                    notify(conn, o["buyer_id"], "offer",
                           f"Tawaranmu diterima untuk {listing['title']}", f"/listing.html?id={listing['id']}")
                else:
                    notify(conn, o["buyer_id"], "offer",
                           f"Tawaranmu ditolak untuk {listing['title']}", f"/listing.html?id={listing['id']}")
            return self._json({"ok": True})

        # ------------- messages
        if route == "messages" and method == "GET":
            user = self._require_user(conn)
            lid = self.qi("listing_id")
            need(lid, 400, "listing_id wajib")
            rows = conn.execute(
                "SELECT m.*, u.name sender FROM messages m JOIN users u ON u.id=m.sender_id"
                " WHERE m.listing_id=? AND (m.sender_id=? OR m.recipient_id=?) ORDER BY m.created_at",
                (lid, user["id"], user["id"])).fetchall()
            conn.execute("UPDATE messages SET read_at=? WHERE listing_id=? AND recipient_id=?"
                         " AND read_at IS NULL", (now(), lid, user["id"]))
            return self._json({"ok": True, "messages": [
                {"id": r["id"], "sender": r["sender"], "mine": r["sender_id"] == user["id"],
                 "body": r["body"], "created": iso(r["created_at"])} for r in rows]})

        if route == "messages" and method == "POST":
            user = self._require_user(conn)
            d = self.read_json()
            lid = int(d.get("listing_id") or 0)
            body = clean(d.get("body"), 2000)
            need(lid and body, 400, "listing_id dan body wajib")
            listing = conn.execute("SELECT * FROM listings WHERE id=?", (lid,)).fetchone()
            need(listing, 404, "listing tidak ditemukan")
            if listing["seller_id"] != user["id"]:
                to = listing["seller_id"]
            else:
                # penjual membalas: pakai `to` kalau dikirim, kalau tidak ambil lawan bicara terakhir
                to = int(d.get("to") or 0)
                if not to:
                    last = conn.execute(
                        "SELECT sender_id, recipient_id FROM messages WHERE listing_id=?"
                        " ORDER BY created_at DESC LIMIT 1", (lid,)).fetchone()
                    if last:
                        to = last["recipient_id"] if last["sender_id"] == user["id"] else last["sender_id"]
                if not to:
                    offer = conn.execute(
                        "SELECT buyer_id FROM offers WHERE listing_id=? ORDER BY created_at DESC LIMIT 1",
                        (lid,)).fetchone()
                    to = offer["buyer_id"] if offer else 0
            need(to and to != user["id"], 400, "penerima tidak valid")
            blocked = conn.execute("SELECT 1 FROM blocks WHERE user_id=? AND blocked_id=?",
                                   (to, user["id"])).fetchone()
            need(not blocked, 403, "penjual memblokir kamu")
            mid = conn.execute(
                "INSERT INTO messages(listing_id,sender_id,recipient_id,body,created_at) VALUES(?,?,?,?,?)",
                (lid, user["id"], to, body, now())).lastrowid
            notify(conn, to, "message", f"Pesan baru dari {user['name']}", f"/listing.html?id={lid}")
            return self._json({"ok": True, "id": mid}, 201)

        # ------------- saved
        if route == "saved" and method == "GET":
            user = self._require_user(conn)
            rows = conn.execute(
                "SELECT l.*, p.file photo FROM saved s JOIN listings l ON l.id=s.listing_id"
                " LEFT JOIN photos p ON p.listing_id=l.id AND p.position=0"
                " WHERE s.user_id=? ORDER BY s.created_at DESC", (user["id"],)).fetchall()
            return self._json({"ok": True, "saved": [listing_card(r) for r in rows]})

        m = re.match(r"^saved/(\d+)$", route)
        if m:
            user = self._require_user(conn)
            lid = int(m.group(1))
            if method == "POST":
                conn.execute("INSERT OR IGNORE INTO saved(user_id,listing_id,created_at) VALUES(?,?,?)",
                             (user["id"], lid, now()))
                return self._json({"ok": True, "saved": True}, 201)
            if method == "DELETE":
                conn.execute("DELETE FROM saved WHERE user_id=? AND listing_id=?", (user["id"], lid))
                return self._json({"ok": True, "saved": False})

        # ------------- reviews
        if route == "reviews" and method == "POST":
            user = self._require_user(conn)
            d = self.read_json()
            lid, stars = int(d.get("listing_id") or 0), int(d.get("stars") or 0)
            need(1 <= stars <= 5, 400, "bintang 1 sampai 5")
            offer = conn.execute(
                "SELECT * FROM offers WHERE listing_id=? AND buyer_id=? AND status='accepted'",
                (lid, user["id"])).fetchone()
            need(offer, 403, "ulasan hanya untuk tawaran yang diterima")
            listing = conn.execute("SELECT * FROM listings WHERE id=?", (lid,)).fetchone()
            need(not conn.execute("SELECT 1 FROM reviews WHERE listing_id=? AND author_id=?",
                                  (lid, user["id"])).fetchone(), 409, "kamu sudah mengulas listing ini")
            conn.execute(
                "INSERT INTO reviews(listing_id,offer_id,author_id,subject_id,stars,body,created_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (lid, offer["id"], user["id"], listing["seller_id"], stars,
                 clean(d.get("body"), 1000), now()))
            notify(conn, listing["seller_id"], "review", f"Ulasan {stars}★ baru di {listing['title']}",
                   f"/profil.html?id={listing['seller_id']}")
            return self._json({"ok": True}, 201)

        # ------------- reports & blocks
        if route == "reports" and method == "POST":
            user = self._require_user(conn)
            d = self.read_json()
            reason = clean(d.get("reason"), 80)
            need(reason, 400, "alasan wajib")
            conn.execute("INSERT INTO reports(reporter_id,listing_id,reason,detail,created_at)"
                         " VALUES(?,?,?,?,?)",
                         (user["id"], int(d.get("listing_id") or 0) or None, reason,
                          clean(d.get("detail"), 1000), now()))
            return self._json({"ok": True}, 201)

        if route == "blocks" and method == "POST":
            user = self._require_user(conn)
            d = self.read_json()
            target = int(d.get("user_id") or 0)
            need(target and target != user["id"], 400, "target tidak valid")
            conn.execute("INSERT OR IGNORE INTO blocks(user_id,blocked_id,created_at) VALUES(?,?,?)",
                         (user["id"], target, now()))
            conn.execute("DELETE FROM messages WHERE (sender_id=? AND recipient_id=?)"
                         " OR (sender_id=? AND recipient_id=?)".replace("?", "?", 4),
                         (user["id"], target, target, user["id"]))
            return self._json({"ok": True}, 201)

        # ------------- notifications
        if route == "notifications" and method == "GET":
            user = self.current_user(conn)
            if not user:
                return self._json({"ok": True, "notifications": [], "unread": 0})
            rows = conn.execute(
                "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 40",
                (user["id"],)).fetchall()
            unread = conn.execute("SELECT COUNT(*) c FROM notifications WHERE user_id=? AND read_at IS NULL",
                                  (user["id"],)).fetchone()["c"]
            return self._json({"ok": True, "unread": unread, "notifications": [
                {"id": r["id"], "kind": r["kind"], "body": r["body"], "link": r["link"],
                 "read": r["read_at"] is not None, "created": iso(r["created_at"])} for r in rows]})

        if route == "notifications/read" and method == "POST":
            user = self._require_user(conn)
            conn.execute("UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL",
                         (now(), user["id"]))
            return self._json({"ok": True})

        # ------------- dashboard / moderation
        if route == "me/listings" and method == "GET":
            user = self._require_user(conn)
            rows = conn.execute(
                "SELECT l.*, p.file photo,"
                " (SELECT COUNT(*) FROM offers o WHERE o.listing_id=l.id AND o.status='proposed') offers,"
                " (SELECT COUNT(*) FROM messages m WHERE m.listing_id=l.id AND m.recipient_id=?"
                "   AND m.read_at IS NULL) unread"
                " FROM listings l LEFT JOIN photos p ON p.listing_id=l.id AND p.position=0"
                " WHERE l.seller_id=? ORDER BY l.created_at DESC", (user["id"], user["id"])).fetchall()
            return self._json({"ok": True, "listings": [listing_card(r) for r in rows]})

        if route == "moderation/reports" and method == "GET":
            user = self._require_user(conn)
            need(user["role"] == "moderator", 403, "khusus moderator")
            rows = conn.execute(
                "SELECT r.*, u.name reporter, l.title listing FROM reports r"
                " JOIN users u ON u.id=r.reporter_id LEFT JOIN listings l ON l.id=r.listing_id"
                " ORDER BY r.created_at DESC LIMIT 100").fetchall()
            return self._json({"ok": True, "reports": [
                {"id": r["id"], "reason": r["reason"], "detail": r["detail"], "status": r["status"],
                 "reporter": r["reporter"], "listing": r["listing"], "created": iso(r["created_at"])}
                for r in rows]})

        raise ApiError(404, f"endpoint tidak ada: {method} /api/{route}")

    # ---- api pieces
    def _login(self, conn, uid, status):
        token = secrets.token_urlsafe(32)
        conn.execute("INSERT INTO sessions(token,user_id,created_at,expires_at) VALUES(?,?,?,?)",
                     (token, uid, now(), now() + SESSION_TTL))
        user = dict(conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
        cookie = f"sid={token}; Path=/; Max-Age={SESSION_TTL}; HttpOnly; SameSite=Lax"
        return self._json({"ok": True, "user": public_user(user)}, status, {"Set-Cookie": cookie})

    def _require_user(self, conn):
        user = self.current_user(conn)
        if not user:
            raise ApiError(401, "perlu masuk dulu")
        return user

    def _list_listings(self, conn):
        q = clean(self.q("q"), 80)
        city = self.q("city")
        category = self.q("category")
        cond = self.q("condition")
        sort = self.q("sort", "new")
        lo, hi = self.qi("min", 0), self.qi("max", 0)
        page = max(1, self.qi("page", 1))
        per = 12
        user = self.current_user(conn)

        where = ["l.status='active'"]
        args = []
        if user:
            where.append("l.seller_id NOT IN (SELECT blocked_id FROM blocks WHERE user_id=?)")
            args.append(user["id"])
        if q:
            where.append("(l.title LIKE ? OR l.description LIKE ?)")
            args += [f"%{q}%", f"%{q}%"]
        for field, value in (("city", city), ("category", category), ("`condition`", cond)):
            if value:
                where.append(f"l.{field}=?")
                args.append(value)
        if lo:
            where.append("l.price>=?")
            args.append(lo)
        if hi:
            where.append("l.price<=?")
            args.append(hi)
        order = {"new": "l.created_at DESC", "cheap": "l.price ASC", "expensive": "l.price DESC",
                 "popular": "l.views DESC"}.get(sort, "l.created_at DESC")
        clause = " AND ".join(where)
        total = conn.execute(f"SELECT COUNT(*) c FROM listings l WHERE {clause}", args).fetchone()["c"]
        rows = conn.execute(
            f"SELECT l.*, p.file photo, u.name seller,"
            f" (SELECT AVG(stars) FROM reviews r WHERE r.subject_id=l.seller_id) rating"
            f" FROM listings l JOIN users u ON u.id=l.seller_id"
            f" LEFT JOIN photos p ON p.listing_id=l.id AND p.position=0"
            f" WHERE {clause} ORDER BY {order} LIMIT ? OFFSET ?",
            args + [per, (page - 1) * per]).fetchall()
        return self._json({"ok": True, "total": total, "page": page, "pages": max(1, (total + per - 1) // per),
                           "listings": [listing_card(r) for r in rows]})

    def _get_listing(self, conn, lid):
        row = conn.execute(
            "SELECT l.*, u.name seller, u.city seller_city, u.bio seller_bio, u.id seller_id_alias,"
            " (SELECT AVG(stars) FROM reviews r WHERE r.subject_id=l.seller_id) rating,"
            " (SELECT COUNT(*) FROM reviews r WHERE r.subject_id=l.seller_id) review_count"
            " FROM listings l JOIN users u ON u.id=l.seller_id WHERE l.id=?", (lid,)).fetchone()
        need(row, 404, "listing tidak ditemukan")
        user = self.current_user(conn)
        if user and user["id"] != row["seller_id"]:
            conn.execute("UPDATE listings SET views=views+1 WHERE id=?", (lid,))
        photos = [r["file"] for r in conn.execute(
            "SELECT file FROM photos WHERE listing_id=? ORDER BY position", (lid,))]
        offers = []
        if user and user["id"] == row["seller_id"]:
            offers = [{"id": r["id"], "amount": r["amount"], "status": r["status"],
                       "buyer": r["name"], "buyer_id": r["buyer_id"], "note": r["note"],
                       "created": iso(r["created_at"])}
                      for r in conn.execute(
                          "SELECT o.*, u.name FROM offers o JOIN users u ON u.id=o.buyer_id"
                          " WHERE o.listing_id=? ORDER BY o.created_at DESC", (lid,))]
        my_offer = None
        if user and user["id"] != row["seller_id"]:
            o = conn.execute("SELECT * FROM offers WHERE listing_id=? AND buyer_id=?",
                             (lid, user["id"])).fetchone()
            if o:
                my_offer = {"id": o["id"], "amount": o["amount"], "status": o["status"]}
        saved = bool(user and conn.execute("SELECT 1 FROM saved WHERE user_id=? AND listing_id=?",
                                           (user["id"], lid)).fetchone())
        reviews = [{"stars": r["stars"], "body": r["body"], "author": r["name"], "created": iso(r["created_at"])}
                   for r in conn.execute(
                       "SELECT r.*, u.name FROM reviews r JOIN users u ON u.id=r.author_id"
                       " WHERE r.listing_id=? ORDER BY r.created_at DESC", (lid,))]
        data = listing_card(row)
        data.update({"description": row["description"], "photos": photos, "offers": offers,
                     "my_offer": my_offer, "saved": saved, "reviews": reviews,
                     "is_owner": bool(user and user["id"] == row["seller_id"]),
                     "seller": {"id": row["seller_id"], "name": row["seller"],
                                "city": row["seller_city"], "bio": row["seller_bio"],
                                "rating": round(row["rating"], 1) if row["rating"] else None,
                                "reviews": row["review_count"]}})
        return self._json({"ok": True, "listing": data})


def listing_card(row):
    d = dict(row)
    return {"id": d["id"], "title": d["title"], "price": d["price"], "price_text": rupiah(d["price"]),
            "category": d["category"], "condition": d.get("condition"), "city": d["city"],
            "status": d["status"], "views": d["views"], "photo": d.get("photo"),
            "seller": d.get("seller"), "rating": round(d["rating"], 1) if d.get("rating") else None,
            "offers": d.get("offers"), "unread": d.get("unread"),
            "created": iso(d["created_at"])}


def public_user(user):
    return {"id": user["id"], "email": user["email"], "name": user["name"], "city": user.get("city"),
            "bio": user.get("bio"), "role": user["role"], "created": iso(user["created_at"])}


def notify(conn, user_id, kind, body, link):
    conn.execute("INSERT INTO notifications(user_id,kind,body,link,created_at) VALUES(?,?,?,?,?)",
                 (user_id, kind, body, link, now()))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8123
    init_db()
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"JualinAja jalan di http://127.0.0.1:{port}  (db: {DB_PATH})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nberhenti")
        server.server_close()


if __name__ == "__main__":
    main()
