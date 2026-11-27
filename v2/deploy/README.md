# Deploy

## 1. Jalan lokal

```bash
python3 app/server.py 8123
# http://127.0.0.1:8123
```

Tidak ada dependensi Python. Basis data dibuat otomatis di `data/jualinaja.db`
dan diisi data contoh saat pertama jalan.

## 2. Sebagai service (systemd user)

```bash
mkdir -p ~/.config/systemd/user
cp deploy/jualinaja.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now jualinaja.service
systemctl --user status jualinaja.service
tail -f data/server.log
```

Agar tetap hidup setelah logout:

```bash
loginctl enable-linger "$USER"
```

## 3. HTTPS (Caddy)

```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile   # ganti contoh.id
sudo systemctl reload caddy
```

Caddy menerbitkan sertifikat otomatis dan meneruskan ke `127.0.0.1:8123`.

## 4. Backup

```bash
sh deploy/backup.sh
# atau pasang di cron harian:
# 0 3 * * * sh $HOME/Projects/jualinaja/deploy/backup.sh
```

`.backup` memakai mode backup SQLite, jadi aman walau server sedang melayani.

## Reset data contoh

```bash
systemctl --user stop jualinaja
rm -f data/jualinaja.db*
systemctl --user start jualinaja
```
