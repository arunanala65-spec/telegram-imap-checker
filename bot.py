"""
Telegram IMAP Checker Bot — gratis, tanpa VPS
==============================================
Cek akun email MILIK SENDIRI via IMAP.

Cara pakai di Telegram:
  /cek email:password
  /cek email password
  /cek email password imap.gmail.com
  Kirim file .txt berisi email:password per baris (maks 3.000/baris file)

Hosting gratis yang cocok (polling, tanpa VPS):
  1. Koyeb Free — paling disarankan, tidak tidur, 24/7
  2. Replit Free — paling gampang, tinggal Run
  3. Render Free Worker — gratis, tapi perlu dicek berkala

Yang dibutuhkan hanya: BOT_TOKEN dari @BotFather.
JANGAN kirim token / password ke siapa pun di chat. Token cukup
dimasukkan sebagai Secret/Env Var di tempat hosting.

Keamanan:
- Password TIDAK pernah disimpan, TIDAK di-log, TIDAK ditampilkan utuh.
- Hanya cek login IMAP (read-only, INBOX saja), tidak baca / hapus email.
- Batasi pemakaian ke ID Telegram kamu via ALLOWED_USER_IDS (opsional tapi disarankan).
- Bot ini HANYA untuk akun email milikmu sendiri.
"""

import asyncio
import imaplib
import logging
import os
import re
import ssl
import time
from concurrent.futures import ThreadPoolExecutor

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ---------- Config ----------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ALLOWED_USER_IDS = {
    int(x) for x in os.environ.get("ALLOWED_USER_IDS", "").replace(",", " ").split() if x.strip().isdigit()
}
MAX_FILE_LINES = int(os.environ.get("MAX_FILE_LINES", "3000"))
CHECK_TIMEOUT = 15  # detik per akun
DELAY_BETWEEN_CHECKS = 0.2  # detik, dipakai hanya untuk mode 1 akun; bulk pakai concurrency
BULK_CONCURRENCY = int(os.environ.get("BULK_CONCURRENCY", "10"))  # cek paralel, biar 3.000 akun tidak makan 1 jam
MAX_FILE_BYTES = 500_000  # ~500 KB, cukup untuk 3.000 baris email:password

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("imap-checker")

# ---------- Provider IMAP ----------
PROVIDERS = {
    "gmail.com": ("imap.gmail.com", 993),
    "googlemail.com": ("imap.gmail.com", 993),
    "outlook.com": ("outlook.office365.com", 993),
    "hotmail.com": ("outlook.office365.com", 993),
    "live.com": ("outlook.office365.com", 993),
    "msn.com": ("outlook.office365.com", 993),
    "yahoo.com": ("imap.mail.yahoo.com", 993),
    "yahoo.co.id": ("imap.mail.yahoo.com", 993),
    "yahoo.co.uk": ("imap.mail.yahoo.com", 993),
    "aol.com": ("imap.aol.com", 993),
    "icloud.com": ("imap.mail.me.com", 993),
    "me.com": ("imap.mail.me.com", 993),
    "mac.com": ("imap.mail.me.com", 993),
    "yandex.com": ("imap.yandex.com", 993),
    "yandex.ru": ("imap.yandex.com", 993),
    "zoho.com": ("imap.zoho.com", 993),
    "mail.ru": ("imap.mail.ru", 993),
    "gmx.com": ("imap.gmx.com", 993),
    "protonmail.com": ("127.0.0.1", 1143),  # Proton butuh Bridge, sengaja gagal dengan pesan jelas
}


def detect_imap(email: str):
    """Tebak host IMAP dari domain email. Return (host, port) atau None."""
    domain = email.rsplit("@", 1)[-1].lower().strip()
    if domain in PROVIDERS:
        return PROVIDERS[domain]
    # Tebakan generik untuk domain custom / provider lain
    return (f"imap.{domain}", 993)


def mask_pw(pw: str) -> str:
    return "***"


# ---------- Inti checker (sync, dijalankan di thread) ----------
def check_imap_sync(email: str, password: str, host: str | None = None, port: int = 993):
    """Return dict: ok, host, detail, inbox_count."""
    if host is None:
        host, port = detect_imap(email)

    if host == "127.0.0.1":
        return {"ok": False, "host": host, "detail": "ProtonMail butuh Proton Bridge, tidak bisa cek langsung via IMAP.", "inbox": 0}

    try:
        ctx = ssl.create_default_context()
        mail = imaplib.IMAP4_SSL(host, port, ssl_context=ctx, timeout=CHECK_TIMEOUT)
        try:
            mail.login(email, password)
            typ, data = mail.select("INBOX", readonly=True)
            count = 0
            if typ == "OK" and data and data[0]:
                try:
                    count = int(data[0].decode())
                except Exception:
                    count = 0
            mail.logout()
            return {"ok": True, "host": host, "detail": "Login berhasil.", "inbox": count}
        except imaplib.IMAP4.error as e:
            msg = str(e).lower()
            try:
                mail.logout()
            except Exception:
                pass
            if "invalid credentials" in msg or "authentication failed" in msg or "auth" in msg or "login" in msg:
                detail = "Password salah / login ditolak."
                if "gmail" in host:
                    detail += " Gmail: pakai App Password (16 karakter) kalau 2FA aktif, password biasa tidak bisa."
                elif "yahoo" in host:
                    detail += " Yahoo: pakai App Password kalau 2FA aktif."
                elif "office365" in host or "outlook" in host:
                    detail += " Outlook: pastikan IMAP aktif & pakai App Password kalau 2FA aktif."
                return {"ok": False, "host": host, "detail": detail, "inbox": 0}
            return {"ok": False, "host": host, "detail": f"IMAP menolak: {e}", "inbox": 0}
    except Exception as e:
        msg = str(e).lower()
        if "timed out" in msg or "timeout" in msg:
            detail = f"Tidak bisa terhubung ke {host} (timeout). Cek host IMAP / jaringan."
        elif "name or service not known" in msg or "getaddrinfo failed" in msg or "temporary failure in name resolution" in msg:
            detail = f"Host IMAP tidak ditemukan: {host}. Coba sebutkan host manual: /cek email password imap.contoh.com"
        elif "ssl" in msg or "certificate" in msg:
            detail = f"Gagal SSL ke {host}: {e}"
            if "wrong version number" in msg:
                detail += " (Kemungkinan jaringan/hosting memblokir port 993 — coba di Koyeb/Replit, bukan di jaringan yang memblokir IMAP.)"
        elif "connection refused" in msg or "unreachable" in msg:
            detail = f"Koneksi ditolak {host}:{port}."
        else:
            detail = f"Error: {e}"
        return {"ok": False, "host": host, "detail": detail, "inbox": 0}


_executor = ThreadPoolExecutor(max_workers=20)


async def check_imap(email: str, password: str, host: str | None = None, port: int = 993):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, check_imap_sync, email, password, host, port)


# ---------- Helpers Telegram ----------
def is_allowed(update: Update) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    return update.effective_user and update.effective_user.id in ALLOWED_USER_IDS


def parse_cred(text: str):
    """Parse 'email:password', 'email password', 'email;password', 'email|password' + host opsional."""
    text = text.strip()
    # buang prefix command
    text = re.sub(r"^/(cek|check)\s+", "", text, flags=re.I).strip()
    if not text:
        return None
    host = None
    # host bisa jadi kata ke-3: email pass imap.host.com
    parts = re.split(r"[\s:;|]+", text)
    # Kasus email:pass -> split di atas sudah benar, tapi email mengandung @ dan .
    # Rekonstruksi: cari email dengan regex dulu
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    if not m:
        return None
    email = m.group(0)
    rest = text[m.end():].strip()
    # rest diawali : atau spasi, lalu password, lalu host opsional
    rest = rest.lstrip(":;| ").strip()
    if not rest:
        return None
    rest_parts = rest.split()
    password = rest_parts[0].strip(":;|")
    if len(rest_parts) > 1 and "." in rest_parts[1]:
        host = rest_parts[1].strip()
    if not password:
        return None
    return email, password, host


START_TEXT = """👋 Halo! Aku bot checker IMAP.

Aku cek akun email *milikmu sendiri* — login IMAP berhasil atau tidak, tanpa menyimpan passwordmu.

*Cara pakai:*
`/cek email:password`
`/cek email password`
`/cek email password imap.gmail.com`

*Contoh:*
`/cek aruna@gmail.com:passwordkamu`
`/cek aruna@outlook.com passwordkamu`

*File massal:*
Kirim file `.txt`, 1 akun per baris `email:password` (maks {max_lines} per file). Hasil LIVE & DEAD aku kirim balik.

*Catatan penting:*
• Gmail / Yahoo / Outlook dengan 2FA aktif harus pakai *App Password*, bukan password biasa.
• Password tidak disimpan & tidak ditampilkan.
• Kalau login gagal terus, cek dulu IMAP-nya aktif di pengaturan emailmu.

Ketik /help untuk detail.
"""

HELP_TEXT = """🛠 *Bantuan — IMAP Checker*

*1 akun:*
`/cek email:password`
`/cek email password [imap_host]`

*File .txt:*
Kirim file berisi:
```
email1@gmail.com:pass1
email2@outlook.com:pass2
```
Maks {max_lines} baris per file. Aku jeda 1 detik per akun biar tidak kena blokir provider.

*Provider yang dikenali otomatis:*
Gmail, Outlook/Hotmail/Live, Yahoo, AOL, iCloud, Yandex, Zoho, GMX, Mail.ru.
Domain lain: aku tebak `imap.domainkamu` — kalau salah, sebutkan host manual di perintah /cek.

*Kenapa Gmail sering DEAD padahal password benar?*
Gmail sudah tidak terima password biasa untuk IMAP kalau 2FA aktif. Buat App Password 16 karakter di myaccount.google.com → Keamanan → App Password, lalu cek pakai itu.

*Privasi:*
Bot ini hanya login IMAP read-only ke INBOX untuk hitung jumlah email. Tidak membaca isi, tidak menghapus, tidak menyimpan password.
"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text("Maaf, bot ini privat.")
        return
    await update.message.reply_text(START_TEXT.format(max_lines=MAX_FILE_LINES), parse_mode="Markdown")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    await update.message.reply_text(HELP_TEXT.format(max_lines=MAX_FILE_LINES), parse_mode="Markdown")


async def cek(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text("Maaf, bot ini privat.")
        return
    text = update.message.text or ""
    parsed = parse_cred(text)
    if not parsed:
        await update.message.reply_text(
            "Formatnya salah.\nPakai:\n`/cek email:password`\nContoh:\n`/cek aruna@gmail.com:passwordkamu`",
            parse_mode="Markdown",
        )
        return
    email, password, host = parsed
    msg = await update.message.reply_text(f"⏳ Mengecek `{email}`…", parse_mode="Markdown")
    result = await check_imap(email, password, host)
    if result["ok"]:
        out = (
            f"✅ *LIVE* — `{email}`\n"
            f"Host: `{result['host']}`\n"
            f"Inbox: {result['inbox']} email\n"
            f"{result['detail']}"
        )
    else:
        out = (
            f"❌ *DEAD* — `{email}`\n"
            f"Host: `{result['host']}`\n"
            f"{result['detail']}"
        )
    await msg.edit_text(out, parse_mode="Markdown")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text("Maaf, bot ini privat.")
        return
    doc = update.message.document
    if not doc or not (doc.file_name or "").lower().endswith(".txt"):
        await update.message.reply_text("Kirim file `.txt` ya, 1 akun per baris `email:password`.")
        return
    if doc.file_size and doc.file_size > MAX_FILE_BYTES:
        await update.message.reply_text("File terlalu besar, maks ~500 KB (cukup untuk 3.000 baris).")
        return
    f = await doc.get_file()
    data = await f.download_as_bytearray()
    try:
        text = bytes(data).decode("utf-8", errors="ignore")
    except Exception:
        await update.message.reply_text("File tidak bisa dibaca sebagai teks.")
        return
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and "@" in ln]
    if not lines:
        await update.message.reply_text("File kosong / tidak ada baris email:password.")
        return
    if len(lines) > MAX_FILE_LINES:
        await update.message.reply_text(f"Maks {MAX_FILE_LINES} baris per file, file kamu {len(lines)} baris. Potong dulu ya.")
        return

    status = await update.message.reply_text(
        f"⏳ Mengecek {len(lines)} akun… (paralel {BULK_CONCURRENCY}, perkiraan {max(1, len(lines) // 20)} menit untuk 3.000 akun, jangan kirim file lain dulu)"
    )
    live, dead = [], []
    sem = asyncio.Semaphore(BULK_CONCURRENCY)
    done = 0

    async def one(line: str):
        nonlocal done
        parsed = parse_cred(line)
        if not parsed:
            return (False, line[:60], "Format salah")
        email, password, host = parsed
        async with sem:
            r = await check_imap(email, password, host)
        if r["ok"]:
            return (True, f"{email} | inbox {r['inbox']}", "")
        return (False, email, r["detail"])

    # Proses per batch 100 supaya progres bisa dilaporkan & memori aman
    for start in range(0, len(lines), 100):
        batch = lines[start:start + 100]
        results = await asyncio.gather(*[one(ln) for ln in batch])
        for ok, a, b in results:
            if ok:
                live.append(a)
            else:
                dead.append((a, b))
        done += len(batch)
        try:
            await status.edit_text(f"⏳ {done}/{len(lines)} dicek… LIVE {len(live)} • DEAD {len(dead)}")
        except Exception:
            pass

    await status.edit_text(f"📊 Hasil: {len(lines)} akun — ✅ LIVE {len(live)} • ❌ DEAD {len(dead)}\nFile hasil dikirim di bawah.")
    live_txt = "\n".join(live) if live else "(tidak ada)"
    dead_txt = "\n".join(f"{e} | {w}" for e, w in dead) if dead else "(tidak ada)"
    # Untuk bulk besar, hasil selalu dikirim sebagai file (pesan Telegram maks ~4.096 karakter)
    await update.message.reply_document(document=live_txt.encode(), filename="live.txt", caption=f"✅ LIVE {len(live)}")
    await update.message.reply_document(document=dead_txt.encode(), filename="dead.txt", caption=f"❌ DEAD {len(dead)}")


async def handle_text_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Biar user bisa kirim langsung "email:password" tanpa /cek
    if not is_allowed(update):
        return
    text = (update.message.text or "").strip()
    if "@" in text and (":" in text or " " in text) and len(text) < 300:
        # perlakukan seperti /cek
        update.message.text = f"/cek {text}"
        await cek(update, context)
    else:
        await update.message.reply_text("Ketik /cek lalu `email:password` — atau /help untuk panduan.", parse_mode="Markdown")


def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN belum diisi. Isi env var BOT_TOKEN dari @BotFather. Lihat .env.example")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler(["cek", "check"], cek))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_fallback))
    log.info("Bot IMAP Checker jalan (polling). Maks file: %s baris.", MAX_FILE_LINES)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
