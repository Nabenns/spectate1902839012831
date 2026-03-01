# MT5 to Discord Bot Monitor (Python)

Script ini memantau aktivitas akun MetaTrader 5 dan mengirim pesan lewat Discord Bot saat:
- ada order baru
- ada update order pending (harga/SL/TP/lot berubah)
- ada pending order dicancel/terhapus
- ada update SL/TP pada posisi terbuka
- ada deal/eksekusi baru

Format pesan dibuat simple:
- `BUY/SELL - PAIR`
- `TYPE : LIMIT/NOW`
- `PRICE / SL / TP`

Untuk event update (`edited`), bot akan kirim sebagai **reply** ke pesan utama ticket/position yang sama.

## 1) Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

### Windows quick setup

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
copy .env.example .env
```

## 2) Konfigurasi

```bash
cp .env.example .env
```

Isi minimal:
- `DISCORD_BOT_TOKEN`
- `DISCORD_CHANNEL_ID`

Opsional:
- `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`
- `MT5_TERMINAL_PATH` (kalau mau target terminal MT5 tertentu)

### Permission bot Discord

Pastikan bot punya permission:
- `View Channels`
- `Send Messages`
- `Read Message History` (dibutuhkan supaya bisa reply ke message sebelumnya)

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
- Jika `MT5_TERMINAL_PATH` diisi, MT5 biasanya akan terbuka otomatis saat script start.
- Jika login sudah aktif di terminal, biasanya kredensial di `.env` bisa dikosongkan.
- Script ini polling per beberapa detik, bukan event listener native.
- Status tombol AutoTrading/Algo Trading di MT5 tidak bisa dipaksa ON dari Python API (security restriction), jadi nyalakan dari terminal MT5 sebelum monitor dijalankan.
