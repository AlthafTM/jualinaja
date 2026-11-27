#!/bin/sh
# backup.sh — salin basis data JualinAja dengan aman (mode backup SQLite,
# jadi aman dijalankan saat server hidup). Simpan 14 salinan terakhir.
set -e
DIR="${1:-$HOME/Projects/jualinaja}"
DEST="${2:-$HOME/backups/jualinaja}"
mkdir -p "$DEST"
STAMP=$(date +%Y%m%d-%H%M%S)
sqlite3 "$DIR/data/jualinaja.db" ".backup '$DEST/jualinaja-$STAMP.db'"
tar czf "$DEST/photos-$STAMP.tar.gz" -C "$DIR/data" photos
ls -1t "$DEST"/jualinaja-*.db | tail -n +15 | xargs -r rm -f
ls -1t "$DEST"/photos-*.tar.gz | tail -n +15 | xargs -r rm -f
echo "backup selesai: $DEST/jualinaja-$STAMP.db"
