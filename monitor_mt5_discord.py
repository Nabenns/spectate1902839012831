#!/usr/bin/env python3
import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Set

import MetaTrader5 as mt5
import requests

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None


ORDER_TYPE_LABEL = {
    mt5.ORDER_TYPE_BUY: "BUY",
    mt5.ORDER_TYPE_SELL: "SELL",
    mt5.ORDER_TYPE_BUY_LIMIT: "BUY_LIMIT",
    mt5.ORDER_TYPE_SELL_LIMIT: "SELL_LIMIT",
    mt5.ORDER_TYPE_BUY_STOP: "BUY_STOP",
    mt5.ORDER_TYPE_SELL_STOP: "SELL_STOP",
    mt5.ORDER_TYPE_BUY_STOP_LIMIT: "BUY_STOP_LIMIT",
    mt5.ORDER_TYPE_SELL_STOP_LIMIT: "SELL_STOP_LIMIT",
    mt5.ORDER_TYPE_CLOSE_BY: "CLOSE_BY",
}

DEAL_ENTRY_LABEL = {
    mt5.DEAL_ENTRY_IN: "IN",
    mt5.DEAL_ENTRY_OUT: "OUT",
    mt5.DEAL_ENTRY_INOUT: "INOUT",
    mt5.DEAL_ENTRY_OUT_BY: "OUT_BY",
}

DEAL_TYPE_LABEL = {
    mt5.DEAL_TYPE_BUY: "BUY",
    mt5.DEAL_TYPE_SELL: "SELL",
    mt5.DEAL_TYPE_BALANCE: "BALANCE",
    mt5.DEAL_TYPE_CREDIT: "CREDIT",
    mt5.DEAL_TYPE_CHARGE: "CHARGE",
    mt5.DEAL_TYPE_CORRECTION: "CORRECTION",
    mt5.DEAL_TYPE_BONUS: "BONUS",
    mt5.DEAL_TYPE_COMMISSION: "COMMISSION",
    mt5.DEAL_TYPE_COMMISSION_DAILY: "COMMISSION_DAILY",
    mt5.DEAL_TYPE_COMMISSION_MONTHLY: "COMMISSION_MONTHLY",
    mt5.DEAL_TYPE_COMMISSION_AGENT_DAILY: "COMMISSION_AGENT_DAILY",
    mt5.DEAL_TYPE_COMMISSION_AGENT_MONTHLY: "COMMISSION_AGENT_MONTHLY",
    mt5.DEAL_TYPE_INTEREST: "INTEREST",
    mt5.DEAL_TYPE_BUY_CANCELED: "BUY_CANCELED",
    mt5.DEAL_TYPE_SELL_CANCELED: "SELL_CANCELED",
}


def deal_action_label(deal_type, deal_entry) -> str:
    if deal_entry == mt5.DEAL_ENTRY_IN:
        if deal_type == mt5.DEAL_TYPE_BUY:
            return "Open BUY"
        if deal_type == mt5.DEAL_TYPE_SELL:
            return "Open SELL"
    if deal_entry == mt5.DEAL_ENTRY_OUT:
        if deal_type == mt5.DEAL_TYPE_SELL:
            return "Close BUY"
        if deal_type == mt5.DEAL_TYPE_BUY:
            return "Close SELL"
    if deal_entry == mt5.DEAL_ENTRY_INOUT:
        return "Reverse Position"
    if deal_entry == mt5.DEAL_ENTRY_OUT_BY:
        return "Close By"
    return "Other"


def env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name, default)
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def to_float(value: Optional[float], digits: int = 5) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return str(value)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def account_fields(account_info) -> List[Dict[str, str]]:
    return [
        {"name": "Balance", "value": to_float(account_info.balance, 2), "inline": True},
        {"name": "Equity", "value": to_float(account_info.equity, 2), "inline": True},
        {"name": "Free Margin", "value": to_float(account_info.margin_free, 2), "inline": True},
        {"name": "Floating P/L", "value": to_float(account_info.profit, 2), "inline": True},
    ]


def post_discord(webhook_url: str, title: str, description: str, fields: List[Dict[str, str]], color: int) -> None:
    payload = {
        "username": "MT5 Monitor Bot",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/5968/5968260.png",
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": color,
                "timestamp": utc_now().isoformat(),
                "fields": fields,
                "footer": {"text": "Spectate MT5 Monitor"},
            }
        ],
    }
    response = requests.post(webhook_url, json=payload, timeout=15)
    response.raise_for_status()


def safe_post(webhook_url: str, title: str, description: str, fields: List[Dict[str, str]], color: int) -> None:
    try:
        post_discord(webhook_url, title, description, fields, color)
        print(f"[OK] Discord sent: {title}")
    except Exception as exc:
        print(f"[WARN] Failed to send Discord webhook: {exc}")


def init_mt5(login: Optional[int], password: Optional[str], server: Optional[str], terminal_path: Optional[str]) -> None:
    kwargs = {}
    if terminal_path:
        kwargs["path"] = terminal_path
    if login:
        kwargs["login"] = login
    if password:
        kwargs["password"] = password
    if server:
        kwargs["server"] = server

    ok = mt5.initialize(**kwargs) if kwargs else mt5.initialize()
    if not ok:
        code, message = mt5.last_error()
        raise RuntimeError(f"MT5 initialize failed: {code} {message}")


def order_fields(order, account_info) -> List[Dict[str, str]]:
    fields = [
        {"name": "Symbol", "value": str(order.symbol), "inline": True},
        {"name": "Type", "value": ORDER_TYPE_LABEL.get(order.type, str(order.type)), "inline": True},
        {"name": "Ticket", "value": str(order.ticket), "inline": True},
        {"name": "Lot", "value": to_float(order.volume_initial, 2), "inline": True},
        {"name": "Entry Price", "value": to_float(order.price_open, 5), "inline": True},
        {"name": "SL", "value": to_float(order.sl, 5), "inline": True},
        {"name": "TP", "value": to_float(order.tp, 5), "inline": True},
    ]
    fields.extend(account_fields(account_info))
    return fields


def position_fields(position, account_info) -> List[Dict[str, str]]:
    side = "BUY" if position.type == mt5.POSITION_TYPE_BUY else "SELL"
    fields = [
        {"name": "Symbol", "value": str(position.symbol), "inline": True},
        {"name": "Side", "value": side, "inline": True},
        {"name": "Ticket", "value": str(position.ticket), "inline": True},
        {"name": "Lot", "value": to_float(position.volume, 2), "inline": True},
        {"name": "Open Price", "value": to_float(position.price_open, 5), "inline": True},
        {"name": "Current Price", "value": to_float(position.price_current, 5), "inline": True},
        {"name": "SL", "value": to_float(position.sl, 5), "inline": True},
        {"name": "TP", "value": to_float(position.tp, 5), "inline": True},
        {"name": "Profit", "value": to_float(position.profit, 2), "inline": True},
    ]
    fields.extend(account_fields(account_info))
    return fields


def deal_fields(deal, account_info) -> List[Dict[str, str]]:
    deal_symbol = getattr(deal, "symbol", "-")
    deal_type = getattr(deal, "type", "-")
    deal_entry = getattr(deal, "entry", "-")
    deal_ticket = getattr(deal, "ticket", "-")
    deal_volume = getattr(deal, "volume", 0.0)
    deal_price = getattr(deal, "price", 0.0)
    deal_sl = getattr(deal, "sl", None)
    deal_tp = getattr(deal, "tp", None)
    deal_profit = getattr(deal, "profit", 0.0)
    action = deal_action_label(deal_type, deal_entry)

    fields = [
        {"name": "Symbol", "value": str(deal_symbol), "inline": True},
        {"name": "Action", "value": action, "inline": True},
        {"name": "Raw", "value": f"{DEAL_TYPE_LABEL.get(deal_type, str(deal_type))} / {DEAL_ENTRY_LABEL.get(deal_entry, str(deal_entry))}", "inline": True},
        {"name": "Deal Ticket", "value": str(deal_ticket), "inline": True},
        {"name": "Lot", "value": to_float(deal_volume, 2), "inline": True},
        {"name": "Price", "value": to_float(deal_price, 5), "inline": True},
        {"name": "SL", "value": to_float(deal_sl, 5), "inline": True},
        {"name": "TP", "value": to_float(deal_tp, 5), "inline": True},
        {"name": "Profit", "value": to_float(deal_profit, 2), "inline": True},
    ]
    fields.extend(account_fields(account_info))
    return fields


def order_snapshot(order) -> Dict[str, float]:
    return {
        "price_open": float(order.price_open or 0.0),
        "sl": float(order.sl or 0.0),
        "tp": float(order.tp or 0.0),
        "volume_initial": float(order.volume_initial or 0.0),
    }


def position_snapshot(position) -> Dict[str, float]:
    return {
        "sl": float(position.sl or 0.0),
        "tp": float(position.tp or 0.0),
    }


def changed_keys(prev: Dict[str, float], curr: Dict[str, float], precision: int = 8) -> List[str]:
    changed = []
    for key in curr.keys():
        if round(prev.get(key, 0.0), precision) != round(curr.get(key, 0.0), precision):
            changed.append(key)
    return changed


def humanize_change_keys(keys: List[str]) -> str:
    labels = {
        "price_open": "Entry Price",
        "sl": "SL",
        "tp": "TP",
        "volume_initial": "Lot",
    }
    return ", ".join(labels.get(k, k) for k in keys) if keys else "-"


def tickets(items: Optional[Iterable], attr: str = "ticket") -> Set[int]:
    if not items:
        return set()
    return {int(getattr(i, attr)) for i in items}


def monitor_loop(webhook_url: str, interval_sec: int, history_seed_hours: int) -> None:
    account_info = mt5.account_info()
    if account_info is None:
        raise RuntimeError(f"Could not fetch account info. MT5 error: {mt5.last_error()}")
    terminal_info = mt5.terminal_info()

    current_orders = mt5.orders_get() or []
    current_positions = mt5.positions_get() or []
    seen_order_tickets = tickets(current_orders)
    seen_position_tickets = tickets(current_positions)
    seen_order_snapshots = {int(o.ticket): order_snapshot(o) for o in current_orders}
    seen_position_snapshots = {int(p.ticket): position_snapshot(p) for p in current_positions}

    since = utc_now() - timedelta(hours=history_seed_hours)
    existing_deals = mt5.history_deals_get(since, utc_now()) or []
    seen_deal_tickets = tickets(existing_deals)

    safe_post(
        webhook_url,
        "MT5 Monitor Online",
        f"Monitoring running every **{interval_sec}s**.",
        account_fields(account_info),
        0x2ECC71,
    )
    if terminal_info is not None and not terminal_info.trade_allowed:
        safe_post(
            webhook_url,
            "MT5 AutoTrading Check",
            "Terminal connected, but trading/algo may be disabled. Please enable AutoTrading in MT5 terminal.",
            [
                {"name": "Connected", "value": str(terminal_info.connected), "inline": True},
                {"name": "Trade Allowed", "value": str(terminal_info.trade_allowed), "inline": True},
                {"name": "Community Account", "value": str(terminal_info.community_account), "inline": True},
            ],
            0xF39C12,
        )

    print("[INFO] Monitor is running. Press Ctrl+C to stop.")
    while True:
        account_info = mt5.account_info()
        if account_info is None:
            print(f"[WARN] account_info failed: {mt5.last_error()}")
            time.sleep(interval_sec)
            continue

        orders = mt5.orders_get() or []
        positions = mt5.positions_get() or []
        now = utc_now()
        new_deals = mt5.history_deals_get(now - timedelta(seconds=interval_sec + 5), now) or []

        order_map = {int(o.ticket): o for o in orders}
        position_map = {int(p.ticket): p for p in positions}
        deal_map = {int(d.ticket): d for d in new_deals}

        order_tickets = set(order_map.keys())
        position_tickets = set(position_map.keys())
        deal_tickets = set(deal_map.keys())

        created_orders = order_tickets - seen_order_tickets
        opened_positions = position_tickets - seen_position_tickets
        fresh_deals = deal_tickets - seen_deal_tickets
        common_orders = order_tickets & seen_order_tickets
        common_positions = position_tickets & seen_position_tickets

        for ticket in sorted(created_orders):
            order = order_map[ticket]
            safe_post(
                webhook_url,
                "New MT5 Order",
                "Pending/market order created.",
                order_fields(order, account_info),
                0x3498DB,
            )

        for ticket in sorted(common_orders):
            order = order_map[ticket]
            current_snapshot = order_snapshot(order)
            previous_snapshot = seen_order_snapshots.get(ticket, {})
            updates = changed_keys(previous_snapshot, current_snapshot)
            if not updates:
                continue
            fields = [
                {"name": "Updated", "value": humanize_change_keys(updates), "inline": False},
            ]
            fields.extend(order_fields(order, account_info))
            safe_post(
                webhook_url,
                "Pending Order Updated",
                "Order parameters changed.",
                fields,
                0x9B59B6,
            )

        for ticket in sorted(opened_positions):
            position = position_map[ticket]
            safe_post(
                webhook_url,
                "New MT5 Position",
                "Position opened/executed.",
                position_fields(position, account_info),
                0x1ABC9C,
            )

        for ticket in sorted(common_positions):
            position = position_map[ticket]
            current_snapshot = position_snapshot(position)
            previous_snapshot = seen_position_snapshots.get(ticket, {})
            updates = changed_keys(previous_snapshot, current_snapshot)
            if not updates:
                continue
            fields = [
                {"name": "Updated", "value": humanize_change_keys(updates), "inline": False},
            ]
            fields.extend(position_fields(position, account_info))
            safe_post(
                webhook_url,
                "Position Protection Updated",
                "SL/TP on open position changed.",
                fields,
                0xE67E22,
            )

        for ticket in sorted(fresh_deals):
            deal = deal_map[ticket]
            safe_post(
                webhook_url,
                "New MT5 Deal",
                "Execution/deal detected.",
                deal_fields(deal, account_info),
                0xE74C3C,
            )

        seen_order_tickets = order_tickets
        seen_position_tickets = position_tickets
        seen_order_snapshots = {int(o.ticket): order_snapshot(o) for o in orders}
        seen_position_snapshots = {int(p.ticket): position_snapshot(p) for p in positions}
        seen_deal_tickets.update(fresh_deals)
        time.sleep(interval_sec)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor MetaTrader5 account activity and send notifications to Discord webhook."
    )
    parser.add_argument("--interval", type=int, default=int(env("POLL_INTERVAL_SEC", "3")), help="Polling interval in seconds.")
    parser.add_argument(
        "--history-seed-hours",
        type=int,
        default=int(env("HISTORY_SEED_HOURS", "24")),
        help="Initial history scan window to avoid duplicate old deals.",
    )
    return parser.parse_args()


def main() -> int:
    if load_dotenv:
        load_dotenv()

    args = parse_args()
    webhook_url = env("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("Missing DISCORD_WEBHOOK_URL in environment/.env")
        return 2

    login_raw = env("MT5_LOGIN")
    login = int(login_raw) if login_raw else None
    password = env("MT5_PASSWORD")
    server = env("MT5_SERVER")
    terminal_path = env("MT5_TERMINAL_PATH")

    try:
        init_mt5(login, password, server, terminal_path)
    except Exception as exc:
        print(f"[ERR] {exc}")
        return 1

    try:
        monitor_loop(webhook_url, args.interval, args.history_seed_hours)
    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user.")
    except Exception as exc:
        print(f"[ERR] Runtime failure: {exc}")
        return 1
    finally:
        mt5.shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())
