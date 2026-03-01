# MT5 to Discord Monitor (Python)

Script ini memantau aktivitas akun MetaTrader 5 dan otomatis kirim notifikasi ke Discord webhook saat:
- ada order baru
- ada posisi baru
- ada deal/eksekusi baru

Notifikasi berisi detail seperti pair/symbol, lot, SL, TP, price, profit, plus data akun (balance/equity/margin).

## 1) Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2) Konfigurasi

```bash
cp .env.example .env
```

Isi minimal:
- `DISCORD_WEBHOOK_URL`

Opsional:
- `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`
- `MT5_TERMINAL_PATH` (kalau mau target terminal MT5 tertentu)

## 3) Jalankan

```bash
python monitor_mt5_discord.py
```

Opsi:

```bash
python monitor_mt5_discord.py --interval 2 --history-seed-hours 48
```

## Catatan

- Terminal MT5 harus terpasang dan bisa diakses dari mesin ini.
- Jika login sudah aktif di terminal, biasanya kredensial di `.env` bisa dikosongkan.
- Script ini polling per beberapa detik, bukan event listener native.
