#!/usr/bin/env python3
"""
motion.py — bikin motion graphic untuk demo JualinAja.

Input : demo/frames/*.jpg + demo/timeline.json (dari record.mjs)
Output: demo/overlay/*.png  (lapisan RGBA, satu per frame)
        demo/assembled.mp4   (video 1080p tanpa audio)

Motion graphic yang digambar:
  * title card     — kartu pembuka neobrutalis dengan garis tumbuh dan teks per-kata
  * chapter badge  — label bab di kiri-atas saat tiap langkah mulai, dengan easing slide
  * lower third   — penjelasan singkat di bawah, bar aksen yang mengisi
  * zoom punch     — skala 1.0→1.06 saat klik penting, lalu kembali
  * callout        — kotak pembatas + panah ke elemen penting
  * outro          — kartu penutup dengan statistik

Semua posisi memakai easing yang sama supaya gerak terasa satu bahasa.
"""
import json
import math
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = Path(__file__).resolve().parent
FRAMES = HERE / "frames"
OVERLAY = HERE / "overlay"
TIMELINE = HERE / "timeline.json"
OUT = HERE / "assembled.mp4"

W, H = 1920, 1080          # kanvas video
SCALE = 2                   # frame capture 1600x1000 @2x = 3200x2000, kita turunkan
FPS = 30

INK = (27, 21, 36)
PAPER = (250, 247, 242)
LAV = (207, 196, 240)
LAV2 = (168, 148, 224)
VIOLET = (107, 79, 168)
VIOLET_DK = (74, 53, 120)
GREEN = (143, 203, 106)
ROSE = (226, 122, 146)
YELLOW = (242, 201, 76)


def font(size, bold=True, mono=False):
    """Cari font yang ada di sistem; fallback ke DejaVu."""
    candidates = []
    if mono:
        candidates = [
            "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        ]
    else:
        if bold:
            candidates = [
                "/usr/share/fonts/truetype/inter/Inter-Bold.ttf",
                "/usr/share/fonts/truetype/inter/Inter-ExtraBold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            ]
        else:
            candidates = [
                "/usr/share/fonts/truetype/inter/Inter-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]
    for c in candidates:
        if os.path.exists(c):
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def ease_out(k):
    k = max(0.0, min(1.0, k))
    return 1 - (1 - k) ** 3


def ease_in_out(k):
    k = max(0.0, min(1.0, k))
    return 2 * k * k if k < .5 else 1 - (-2 * k + 2) ** 2 / 2


def back_out(k, s=1.7):
    k = max(0.0, min(1.0, k))
    return 1 + (s + 1) * (k - 1) ** 3 + s * (k - 1) ** 2


def seg(t, a, b):
    if b <= a:
        return 1.0 if t >= b else 0.0
    return max(0.0, min(1.0, (t - a) / (b - a)))


# ---------------------------------------------------------------- primitives
def shadow_box(d, box, fill, offset=(10, 10), radius=0, outline=INK, width=6):
    x0, y0, x1, y1 = box
    d.rounded_rectangle([x0 + offset[0], y0 + offset[1], x1 + offset[0], y1 + offset[1]],
                        radius=radius, fill=INK)
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def text_tracked(d, xy, text, f, fill, tracking=0):
    """Gambar teks dengan letter-spacing; PIL tidak punya tracking bawaan."""
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + tracking
    return x


def measure_tracked(d, text, f, tracking=0):
    return sum(d.textlength(c, font=f) + tracking for c in text) - (tracking if text else 0)


# ---------------------------------------------------------------- scenes
def draw_title_card(img, d, k, alpha_k):
    """Kartu pembuka: latar lavender penuh, judul per-kata, garis tumbuh."""
    if alpha_k <= 0:
        return
    a = int(255 * alpha_k)
    layer = Image.new("RGBA", (W, H), LAV + (a,))
    img.alpha_composite(layer)

    # garis atas dan bawah yang tumbuh dari tengah
    gw = int(W * ease_out(seg(k, 0, .45)))
    d.rectangle([(W - gw) // 2, 120, (W + gw) // 2, 132], fill=INK + (a,))
    d.rectangle([(W - gw) // 2, H - 132, (W + gw) // 2, H - 120], fill=INK + (a,))

    # eyebrow: satu kali, dengan tracking manual (jangan digambar dua kali)
    if k > .18:
        f = font(30, mono=True)
        t = "PASAR BARANG BEKAS · ANTAR WARGA"
        tw = measure_tracked(d, t, f, 6)
        x = (W - tw) / 2
        for ch in t:
            d.text((x, 300), ch, font=f, fill=VIOLET_DK + (a,))
            x += d.textlength(ch, font=f) + 6

    # judul per-kata, masuk dari bawah
    words = ["JualinAja"]
    f = font(150, bold=True)
    total = sum(d.textlength(w, font=f) for w in words) + 20 * (len(words) - 1)
    x = (W - total) / 2
    for i, w in enumerate(words):
        wk = ease_out(seg(k, .12 + i * .08, .5 + i * .08))
        dy = (1 - wk) * 60
        d.text((x, 400 + dy), w, font=f, fill=INK + (int(a * wk),))
        x += d.textlength(w, font=f) + 20

    # subjudul
    if k > .42:
        sk = ease_out(seg(k, .42, .75))
        f2 = font(48, bold=False)
        sub = "satu proses Python. tanpa dependensi."
        sw = d.textlength(sub, font=f2)
        d.text(((W - sw) / 2, 600 + (1 - sk) * 30), sub, font=f2, fill=INK + (int(a * sk),))

    # chip fakta
    if k > .6:
        ck = back_out(seg(k, .6, .9))
        chips = ["0 dependensi", "77 tes API", "SQLite WAL", "stdout only"]
        f3 = font(26, mono=True)
        widths = [d.textlength(c, font=f3) + 44 for c in chips]
        total = sum(widths) + 18 * (len(chips) - 1)
        x = (W - total) / 2
        y = 720
        for c, w in zip(chips, widths):
            box = [x, y, x + w, y + 58]
            if ck > .05:
                d.rectangle([box[0] + 6, box[1] + 6, box[2] + 6, box[3] + 6], fill=INK + (int(a * ck),))
                d.rectangle(box, fill=GREEN + (int(a * ck),), outline=INK + (int(a * ck),), width=5)
                d.text((x + 20, y + 14), c, font=f3, fill=INK + (int(a * ck),))
            x += w + 18


def draw_chapter(d, t, mark, alpha, idx):
    """Badge bab: kotak ungu dengan nomor dan judul, slide dari kiri."""
    if alpha <= 0:
        return
    a = int(255 * alpha)
    slide = (1 - ease_out(alpha)) * -90
    x0, y0 = 70 + slide, 70
    title = mark["text"]
    sub = mark.get("sub", "")

    fm = font(30, mono=True)
    ft = font(52, bold=True)
    fs = font(28, bold=False)
    tw = d.textlength(title, font=ft)
    sw = d.textlength(sub, font=fs) if sub else 0
    # jangan pernah melewati tepi kanan: sisakan 80px, dan potong subteks kalau perlu
    max_w = W - 70 - 80
    lead = 88 if idx is not None else 30
    box_w = min(max(tw + (lead - 30), sw + (lead - 30), 360) + 76, max_w)
    if sub and 88 + sw + 40 > box_w:
        fsz = getattr(fs, "size", 28)
        while fsz > 18 and d.textlength(sub, font=font(fsz, bold=False)) + 88 + 40 > box_w:
            fsz -= 2
        fs = font(fsz, bold=False)
        sub = sub if d.textlength(sub, font=fs) + 88 + 40 <= box_w else sub[:max(8, int(len(sub) * (box_w - 128) / max(1, d.textlength(sub, font=fs))))].rstrip() + "…"
    box_h = 130 if sub else 100

    # bayangan
    d.rectangle([x0 + 12, y0 + 12, x0 + box_w + 12, y0 + box_h + 12], fill=INK + (a,))
    d.rectangle([x0, y0, x0 + box_w, y0 + box_h], fill=VIOLET + (a,), outline=INK + (a,), width=6)
    # strip nomor hanya kalau bab ini memang bernomor
    tx = x0 + 30
    if idx is not None:
        d.rectangle([x0, y0, x0 + 64, y0 + box_h], fill=GREEN + (a,), outline=INK + (a,), width=6)
        d.text((x0 + 20, y0 + box_h / 2 - 20), f"{idx}", font=fm, fill=INK + (a,))
        tx = x0 + 88
    d.text((tx, y0 + (18 if sub else 26)), title, font=ft, fill=PAPER + (a,))
    if sub:
        d.text((tx, y0 + 78), sub, font=fs, fill=LAV + (a,))


def draw_lower_third(d, k, text, alpha):
    """Bar bawah: latar ink, garis aksen mengisi, teks mono."""
    if alpha <= 0:
        return
    a = int(255 * alpha)
    h = 62
    y = H - h - 18          # menempel di margin bawah, tidak menutupi kartu
    slide = (1 - ease_out(seg(k, 0, .35))) * 40
    x0 = 70
    f = font(28, bold=False)
    f2 = font(24, mono=True)
    # batasi lebar bar: kalau teks panjang, kecilkan font sampai muat
    avail = W - 70 * 2 - 40
    size = 24
    while size > 15 and measure_tracked(d, text, font(size, mono=True)) > avail:
        size -= 1
    f2 = font(size, mono=True)
    tw = d.textlength(text, font=f2)

    d.rectangle([x0 + 8, y + 8 + slide, x0 + tw + 64, y + h + 8 + slide], fill=INK + (a,))
    d.rectangle([x0, y + slide, x0 + tw + 64, y + h + slide], fill=INK + (a,))
    # bar aksen mengisi dari kiri
    fill_w = int((tw + 64) * ease_in_out(seg(k, .12, .9)))
    if fill_w > 4:
        d.rectangle([x0, y + h - 8 + slide, x0 + fill_w, y + h + slide], fill=GREEN + (a,))
    d.text((x0 + 28, y + 17 + slide), text, font=f2, fill=PAPER + (a,))


def draw_outro(img, d, k, alpha_k, stats):
    if alpha_k <= 0:
        return
    a = int(255 * alpha_k)
    img.alpha_composite(Image.new("RGBA", (W, H), LAV + (a,)))

    gw = int(W * ease_out(seg(k, 0, .4)))
    d.rectangle([(W - gw) // 2, 150, (W + gw) // 2, 162], fill=INK + (a,))

    f = font(110, bold=True)
    t = "Selesai."
    d.text(((W - d.textlength(t, font=f)) / 2, 330), t, font=f, fill=INK + (a,))

    fm = font(34, mono=True)
    y = 520
    for label, value in stats:
        b = back_out(seg(k, .2 + y * 0.0002, .6))
        if b < .05:
            y += 78
            continue
        d.rectangle([380, y, 380 + 1160, y + 66], fill=PAPER + (int(a * b),), outline=INK + (int(a * b),), width=5)
        d.rectangle([380 + 1160 - 6, y + 6, 380 + 1154, y + 60], fill=GREEN + (int(a * b),))
        d.text((410, y + 16), label, font=fm, fill=VIOLET_DK + (int(a * b),))
        vw = d.textlength(value, font=fm)
        d.text((380 + 1160 - 40 - vw, y + 16), value, font=fm, fill=INK + (int(a * b),))
        y += 78

    f3 = font(30, bold=False)
    s = "branch feat/jualinaja-v2 · PR siap direview"
    d.text(((W - d.textlength(s, font=f3)) / 2, 900), s, font=f3, fill=INK + (a,))


def callout(d, box, k, label):
    """Kotak pembatas + label kecil, muncul dengan pop."""
    if k <= 0:
        return
    a = int(255 * min(1, k * 2))
    x0, y0, x1, y1 = box
    grow = ease_out(min(1, k * 1.6))
    pad = 14
    bx0 = x0 - pad
    by0 = y0 - pad
    bx1 = bx0 + (x1 - x0 + pad * 2) * grow
    by1 = by0 + (y1 - y0 + pad * 2) * grow
    d.rectangle([bx0, by0, bx1, by1], outline=ROSE + (a,), width=6)
    if k > .5 and label:
        f = font(26, mono=True)
        tw = d.textlength(label, font=f)
        ly = max(20, by0 - 46)
        d.rectangle([bx0, ly, bx0 + tw + 26, ly + 40], fill=ROSE + (a,), outline=INK + (a,), width=4)
        d.text((bx0 + 13, ly + 7), label, font=f, fill=PAPER + (a,))


# ---------------------------------------------------------------- main
def main():
    tl = json.loads(TIMELINE.read_text())
    frames = tl["frames"]
    marks = tl["marks"]
    duration = tl["duration"]
    # penanda terakhir bisa jatuh SETELAH frame terakhir (mark ditulis setelah sleep).
    # clamp ke dalam durasi, dan pastikan outro selalu kebagian minimal 4 detik.
    for m in marks:
        m["t"] = min(m["t"], max(0.0, duration - 0.4))
    # screencast berhenti mengirim frame saat layar diam, jadi penanda terakhir sering
    # jatuh di luar durasi video. Paksa outro mulai tepat 4 detik sebelum akhir supaya
    # kartu penutupnya benar-benar terlihat dan sempat beranimasi.
    if len(marks) >= 2:
        marks[-1]["t"] = max(marks[-2]["t"] + 2.0, duration - 4.0)
    marks.sort(key=lambda m: m["t"])
    print(f"{len(frames)} frame, {duration:.1f}s, {len(marks)} penanda "
          f"(terakhir di {marks[-1]['t']:.1f}s)")

    OVERLAY.mkdir(exist_ok=True)
    for f in OVERLAY.glob("*.png"):
        f.unlink()

    # durasi tiap chapter: dari mark ini sampai mark berikutnya.
    # nomor badge diambil dari teks penanda kalau ada ("4 · Tawar & chat" → 4), bukan nomor urut.
    import re as _re
    chapters = []
    for i, m in enumerate(marks):
        end = marks[i + 1]["t"] if i + 1 < len(marks) else duration
        num = _re.match(r"^\s*(\d+)\s*·", m["text"])
        chapters.append({"idx": int(num.group(1)) if num else None, "t0": m["t"], "t1": end,
                         "text": m["text"], "sub": m.get("sub", "")})

    title = chapters[0]
    outro = chapters[-1]
    steps = chapters[1:-1]

    # skala zoom: dorong sedikit saat bab berganti
    zooms = []
    for c in steps:
        zooms.append((c["t0"], 1.0))
        zooms.append((c["t0"] + .45, 1.045))
        zooms.append((min(c["t1"], c["t0"] + 3.4), 1.045))
        zooms.append((min(c["t1"], c["t0"] + 4.2), 1.0))

    def zoom_at(t):
        if not zooms:
            return 1.0
        prev_t, prev_z = zooms[0]
        for zt, zz in zooms:
            if t < zt:
                k = ease_in_out(seg(t, prev_t, zt))
                return prev_z + (zz - prev_z) * k
            prev_t, prev_z = zt, zz
        return prev_z

    # ukuran frame capture dibaca dari file aslinya (screencast mengabaikan deviceScaleFactor)
    probe = Image.open(FRAMES / frames[0]["file"])
    base_w, base_h = probe.size
    print(f"frame capture: {base_w}x{base_h} → kanvas 1920x1080")

    # durasi tiap PNG = jarak ke frame berikutnya (capture-nya variable rate, jadi time-based).
    # screencast berhenti mengirim frame saat layar diam, jadi frame terakhir ditahan lebih lama
    # supaya kartu penutup sempat tampil.
    OUTRO_HOLD = 4.2
    holds = []
    for i, fr in enumerate(frames):
        nxt = frames[i + 1]["t"] if i + 1 < len(frames) else duration + OUTRO_HOLD
        holds.append(max(1 / 60, nxt - fr["t"]))
    duration = frames[-1]["t"] + OUTRO_HOLD
    print(f"durasi final: {duration:.2f}s (outro ditahan {OUTRO_HOLD}s)")

    for i, fr in enumerate(frames):
        t = fr["t"]
        src = Image.open(FRAMES / fr["file"]).convert("RGB")

        # zoom: crop sekecil z dari tengah-atas, lalu skala ke 1920 lebar
        z = zoom_at(t)
        if abs(z - 1.0) > .001:
            cw, ch = int(base_w / z), int(base_h / z)
            cx, cy = (base_w - cw) // 2, max(0, int((base_h - ch) * .35))
            src = src.crop((cx, cy, cx + cw, cy + ch))
        # skala ke lebar kanvas; jaga aspek
        new_h = int(1920 * src.height / src.width)
        src = src.resize((1920, new_h), Image.LANCZOS)
        # tempatkan di kanvas 1920x1080: kalau lebih tinggi, ambil dari atas (header penting);
        # kalau lebih pendek, letakkan di atas dengan sisa latar paper
        canvas = Image.new("RGB", (1920, 1080), PAPER)
        if new_h >= 1080:
            src = src.crop((0, 0, 1920, 1080))
            canvas.paste(src, (0, 0))
        else:
            canvas.paste(src, (0, 0))
        src = canvas

        img = src.convert("RGBA")
        d = ImageDraw.Draw(img, "RGBA")

        # title card menutup layar 0 → 4.2 s
        if t < 4.6:
            k = seg(t, 0, 3.0)
            a = 1 - ease_in_out(seg(t, 3.7, 4.5))
            draw_title_card(img, d, k, a)

        # chapter badge
        for c in steps:
            if c["t0"] - .2 <= t <= c["t1"] - .1:
                a = ease_out(seg(t, c["t0"] - .2, c["t0"] + .45)) * (1 - ease_out(seg(t, c["t1"] - .5, c["t1"] - .1)))
                draw_chapter(d, t, c, a, c["idx"])
                # lower third: teks penjelasan
                la = ease_out(seg(t, c["t0"] + .1, c["t0"] + .6)) * (1 - ease_out(seg(t, c["t1"] - .6, c["t1"] - .15)))
                lk = seg(t, c["t0"] + .1, min(c["t1"], c["t0"] + 3.2))
                if c["sub"]:
                    draw_lower_third(d, lk, c["sub"], la)

        # outro
        if t > outro["t0"] - .3:
            k = seg(t, outro["t0"] - .3, outro["t0"] + 2.4)
            a = ease_in_out(seg(t, outro["t0"] - .3, outro["t0"] + .5))
            draw_outro(img, d, k, a, [
                ("API smoke test", "77 ok, 0 gagal"),
                ("Baris server", "1049 (stdlib)"),
                ("Baris klien", "595 (vanilla)"),
                ("Halaman", "11"),
                ("Responsif 390px", "overflow 0"),
            ])

        img.convert("RGB").save(OVERLAY / f"o-{i:05d}.png", optimize=False, compress_level=1)
        if i % 60 == 0:
            print(f"  frame {i}/{len(frames)} t={t:.1f}s")

    print(f"overlay selesai: {len(list(OVERLAY.glob('*.png')))} png")

    # rakit video dari overlay (yang sudah berisi capture + motion graphic)
    concat = HERE / "concat_overlay.txt"
    with concat.open("w") as fh:
        for i in range(len(frames)):
            fh.write(f"file '{(OVERLAY / f'o-{i:05d}.png').as_posix()}'\nduration {holds[i]:.4f}\n")
        fh.write(f"file '{(OVERLAY / f'o-{len(frames)-1:05d}.png').as_posix()}'\n")

    subprocess.run([str(Path.home() / "bin/ffmpeg"), "-y", "-loglevel", "error",
                    "-f", "concat", "-safe", "0", "-i", str(concat),
                    "-vf", f"fps={FPS},format=yuv420p",
                    "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                    str(OUT)], check=True)
    print(f"video: {OUT}  ({OUT.stat().st_size/1024/1024:.1f} MB)")


if __name__ == "__main__":
    main()
