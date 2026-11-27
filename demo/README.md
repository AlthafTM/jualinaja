# Demo video

Video demo alur kerja JualinAja, direkam dari aplikasinya sendiri — bukan mockup.

```
jualinaja-demo.mp4        1920x1080, 30fps, 99.7s, 5.1 MB  (master)
jualinaja-demo-web.mp4    1280x720, faststart, 2.0 MB       (untuk dibagikan)
```

## Alur yang diperlihatkan

```
0:00  title card    JualinAja · satu proses Python, tanpa dependensi
0:03  beranda       paling dilihat, baru masuk, statistik
0:06  1 · Jelajah   filter kata kunci + kota + kategori + kondisi + harga
0:15  2 · Detail    galeri, kondisi, penjual, ulasan
0:19  3 · Masuk     PBKDF2 240k, cookie HttpOnly SameSite=Lax
0:30  4 · Tawar     tawaran unik per pembeli, chat per barang
0:46  5 · Penjual   terima satu tawaran, balas chat
1:11  6 · Pasang    form + unggah foto asli
1:30  7 · Dasbor    barang saya, notifikasi
1:36  outro         77 tes API lolos, ukuran kode, responsif 390px
```

## Cara membuat ulang

Butuh: Chromium, Node 22+, Python 3 dengan Pillow, ffmpeg.

```bash
# 1. jalankan aplikasinya
cd .. && python3 v2/app/server.py 8126 &

# 2. rekam alurnya (CDP screencast, timestamp asli per frame)
node demo/record.mjs http://127.0.0.1:8126 demo/frames demo/foto-contoh.png

# 3. gambar motion graphic + rakit video
python3 demo/motion.py
```

`record.mjs` menulis `timeline.json` (frame + penanda waktu). `motion.py` membacanya,
menggambar title card, chapter badge, lower third, zoom, dan outro di atas setiap frame,
lalu merakitnya dengan ffmpeg memakai timestamp asli — jadi kecepatan video sama dengan
kecepatan interaksi sebenarnya, bukan 1/30 per frame.

## Motion graphic

| elemen | kapan | gerak |
|---|---|---|
| title card | 0–4.6s | garis tumbuh dari tengah, judul masuk dari bawah per-kata, chip pop |
| chapter badge | tiap langkah | slide dari kiri, shadow offset, nomor dari teks penanda |
| lower third | tiap langkah | slide naik, bar hijau mengisi, menempel margin bawah |
| zoom punch | awal tiap langkah | 1.0 → 1.045 → 1.0, ease-in-out |
| outro | 4 detik terakhir | kartu lavender, baris statistik pop berurutan |

Semua easing memakai `ease_out` / `ease_in_out` / `back_out` yang sama supaya geraknya
terasa satu bahasa. Palet mengikuti aplikasinya: lavender, ungu, hijau, ink, tanpa sudut bulat.

## Catatan teknis

- `Page.startScreencast` berhenti mengirim frame saat layar diam, jadi `timeline.json`
  menyimpan timestamp jam dinding per frame; frame terakhir ditahan 4.2s supaya outro
  sempat tampil.
- Capture keluar 1600x1000 (screencast mengabaikan `deviceScaleFactor`), lalu diskalakan
  ke kanvas 1920x1080 dengan crop dari atas supaya header aplikasi tetap terlihat.
- Tiap langkah dibungkus `step()` — kalau satu langkah gagal, rekaman tetap jalan dan
  langkah itu dilewati dengan peringatan, bukan membunuh seluruh proses.
