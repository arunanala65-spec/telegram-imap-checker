# Telegram IMAP Checker Bot — Gratis, Tanpa VPS

Cek akun email **milikmu sendiri** lewat Telegram. Bot login IMAP (read-only, cuma hitung inbox), lalu jawab LIVE / DEAD. Password tidak disimpan, tidak di-log, tidak ditampilkan.

## Cara pakai di Telegram

```
/cek email:password
/cek email password
/cek email password imap.gmail.com
```

Atau kirim langsung `email:password` tanpa perintah.

**File massal:** kirim file `.txt`, 1 akun per baris `email:password`, maks 3.000 baris per file. Hasil LIVE & DEAD dikirim balik.

Provider otomatis dikenali: Gmail, Outlook/Hotmail/Live, Yahoo, AOL, iCloud, Yandex, Zoho, GMX, Mail.ru. Domain lain ditebak `imap.domainkamu` — kalau salah, sebutkan host manual.

> Gmail / Yahoo / Outlook dengan 2FA aktif **harus pakai App Password** (16 karakter), bukan password biasa. Gmail: myaccount.google.com → Keamanan → App Password.

## Langkah 1 — Buat bot (2 menit, gratis)

1. Buka Telegram, cari `@BotFather`
2. Kirim `/newbot`, ikuti: nama bot → username bot (harus berakhiran `bot`, misal `CekImapRudyBot`)
3. Salin token yang diberikan, contoh: `123456789:ABCdef...`
4. (Disarankan) Cari `@userinfobot`, kirim `/start`, catat ID Telegram kamu untuk `ALLOWED_USER_IDS` — supaya bot cuma bisa dipakai kamu.

**Jangan kirim token ke siapa pun di chat.** Token cuma dimasukkan sebagai Secret di hosting.

## Langkah 2 — Deploy gratis, tinggal pakai

Pilih SATU yang paling gampang buat kamu:

### A. Koyeb — disarankan (gratis, tidak tidur, 24/7)

1. Buka [koyeb.com](https://www.koyeb.com), daftar gratis (pakai GitHub/Google).
2. Buat repo GitHub dari folder ini (atau upload via Koyeb Git), lalu di Koyeb: **Create Service → GitHub → pilih repo ini**.
3. Builder: **Buildpack / Python**, Run command: `python bot.py`
4. Di **Environment variables**, tambah:
   - `BOT_TOKEN` = token dari BotFather
   - `ALLOWED_USER_IDS` = ID Telegram kamu
5. Deploy. Buka Telegram, kirim `/start` ke bot kamu. Selesai.

Gratis Koyeb: 1 instance Nano gratis, cukup untuk bot polling seperti ini.

### B. Replit — paling gampang (gratis)

1. Buka [replit.com](https://replit.com), **Create Repl → Import from GitHub** (paste URL repo ini) atau upload file `bot.py` + `requirements.txt`.
2. Buka tab **Secrets** (ikon gembok), tambah `BOT_TOKEN` = token kamu, dan `ALLOWED_USER_IDS` = ID kamu.
3. Klik **Run**. Selama tab Replit / Deployment aktif, bot jalan.
4. Supaya tidak tidur: di Replit, pakai **Deployments → Autoscale** (free tier) atau biarkan Run aktif.

### C. Render — gratis (Worker)

1. Buka [dashboard.render.com](https://dashboard.render.com), **New → Background Worker**, hubungkan repo GitHub ini.
2. Build: `pip install -r requirements.txt`, Start: `python bot.py`
3. Tambah Environment Variable `BOT_TOKEN` (dan `ALLOWED_USER_IDS`).
4. Deploy. File `render.yaml` di repo ini sudah berisi setting yang sama — bisa juga pakai **New → Blueprint**.

Catatan: Render Free Web Service tidur setelah 15 menit tidak ada traffic, jadi pilih **Worker**, bukan Web Service.

## Jalankan di laptop / HP (tanpa hosting, untuk tes)

```bash
pip install -r requirements.txt
cp .env.example .env
# isi BOT_TOKEN di .env
python bot.py
```

Di HP Android bisa pakai Termux dengan perintah yang sama, tapi bot mati kalau Termux ditutup — jadi untuk 24/7 tetap pakai Koyeb/Replit di atas.

## File di repo ini

| File | Fungsi |
|---|---|
| `bot.py` | Semua logika bot + checker IMAP |
| `requirements.txt` | `python-telegram-bot` |
| `render.yaml` | Setting deploy Render Worker |
| `Procfile` | Setting worker (Render/Heroku-style) |
| `.env.example` | Contoh env var, tanpa token asli |
| `.gitignore` | Supaya `.env` tidak ke-commit |

## Keamanan & batasan

- Hanya untuk akun email milikmu sendiri.
- Bot tidak membaca isi email, tidak menghapus, tidak menyimpan password.
- Maks 3.000 akun per file, dicek paralel 10 akun sekaligus — 3.000 akun perkiraan belasan menit, tergantung provider. Kalau provider memblokir karena terlalu cepat, turunkan BULK_CONCURRENCY ke 5 di env var.
- Kalau provider memblokir login berulang, tunggu sebentar lalu coba lagi, dan pastikan IMAP aktif di pengaturan emailmu.
- Token bot bocor? Revoke di `@BotFather` → `/revoke` lalu ganti token di hosting.
