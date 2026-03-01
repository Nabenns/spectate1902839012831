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
        {"name": "Login", "value": str(account_info.login), "inline": True},
        {"name": "Server", "value": str(account_info.server), "inline": True},
        {"name": "Currency", "value": str(account_info.currency), "inline": True},
        {"name": "Balance", "value": to_float(account_info.balance, 2), "inline": True},
        {"name": "Equity", "value": to_float(account_info.equity, 2), "inline": True},
        {"name": "Margin", "value": to_float(account_info.margin, 2), "inline": True},
        {"name": "Free Margin", "value": to_float(account_info.margin_free, 2), "inline": True},
        {"name": "Margin Level", "value": to_float(account_info.margin_level, 2), "inline": True},
        {"name": "Profit", "value": to_float(account_info.profit, 2), "inline": True},
    ]


def post_discord(webhook_url: str, title: str, description: str, fields: List[Dict[str, str]]) -> None:
    payload = {
        "username": "MT5 Monitor Bot",
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": 3447003,
                "timestamp": utc_now().isoformat(),
                "fields": fields,
            }
        ],
    }
    response = requests.post(webhook_url, json=payload, timeout=15)
    response.raise_for_status()


def safe_post(webhook_url: str, title: str, description: str, fields: List[Dict[str, str]]) -> None:
    try:
        post_discord(webhook_url, title, description, fields)
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
        {"name": "Ticket", "value": str(order.ticket), "inline": True},
        {"name": "Type", "value": ORDER_TYPE_LABEL.get(order.type, str(order.type)), "inline": True},
        {"name": "Symbol", "value": str(order.symbol), "inline": True},
        {"name": "Volume", "value": to_float(order.volume_initial, 2), "inline": True},
        {"name": "Price Open", "value": to_float(order.price_open, 5), "inline": True},
        {"name": "SL", "value": to_float(order.sl, 5), "inline": True},
        {"name": "TP", "value": to_float(order.tp, 5), "inline": True},
        {"name": "Comment", "value": str(order.comment or "-"), "inline": False},
    ]
    fields.extend(account_fields(account_info))
    return fields


def position_fields(position, account_info) -> List[Dict[str, str]]:
    side = "BUY" if position.type == mt5.POSITION_TYPE_BUY else "SELL"
    fields = [
        {"name": "Ticket", "value": str(position.ticket), "inline": True},
        {"name": "Side", "value": side, "inline": True},
        {"name": "Symbol", "value": str(position.symbol), "inline": True},
        {"name": "Volume", "value": to_float(position.volume, 2), "inline": True},
        {"name": "Price Open", "value": to_float(position.price_open, 5), "inline": True},
        {"name": "Price Current", "value": to_float(position.price_current, 5), "inline": True},
        {"name": "SL", "value": to_float(position.sl, 5), "inline": True},
        {"name": "TP", "value": to_float(position.tp, 5), "inline": True},
        {"name": "Profit", "value": to_float(position.profit, 2), "inline": True},
        {"name": "Comment", "value": str(position.comment or "-"), "inline": False},
    ]
    fields.extend(account_fields(account_info))
    return fields


def deal_fields(deal, account_info) -> List[Dict[str, str]]:
    fields = [
        {"name": "Deal Ticket", "value": str(deal.ticket), "inline": True},
        {"name": "Order Ticket", "value": str(deal.order), "inline": True},
        {"name": "Position ID", "value": str(deal.position_id), "inline": True},
        {"name": "Type", "value": DEAL_TYPE_LABEL.get(deal.type, str(deal.type)), "inline": True},
        {"name": "Entry", "value": DEAL_ENTRY_LABEL.get(deal.entry, str(deal.entry)), "inline": True},
        {"name": "Symbol", "value": str(deal.symbol), "inline": True},
        {"name": "Volume", "value": to_float(deal.volume, 2), "inline": True},
        {"name": "Price", "value": to_float(deal.price, 5), "inline": True},
        {"name": "SL", "value": to_float(deal.sl, 5), "inline": True},
        {"name": "TP", "value": to_float(deal.tp, 5), "inline": True},
        {"name": "Profit", "value": to_float(deal.profit, 2), "inline": True},
        {"name": "Commission", "value": to_float(deal.commission, 2), "inline": True},
        {"name": "Swap", "value": to_float(deal.swap, 2), "inline": True},
        {"name": "Comment", "value": str(deal.comment or "-"), "inline": False},
    ]
    fields.extend(account_fields(account_info))
    return fields


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

    since = utc_now() - timedelta(hours=history_seed_hours)
    existing_deals = mt5.history_deals_get(since, utc_now()) or []
    seen_deal_tickets = tickets(existing_deals)

    safe_post(
        webhook_url,
        "MT5 Monitor Started",
        f"Watching account `{account_info.login}` on `{account_info.server}` every {interval_sec}s.",
        account_fields(account_info),
    )
    if terminal_info is not None and not terminal_info.trade_allowed:
        safe_post(
            webhook_url,
            "MT5 Trading Not Allowed",
            "Terminal connected, but trading/algo may be disabled. Please enable AutoTrading in MT5 terminal.",
            [
                {"name": "Connected", "value": str(terminal_info.connected), "inline": True},
                {"name": "Trade Allowed", "value": str(terminal_info.trade_allowed), "inline": True},
                {"name": "Community Account", "value": str(terminal_info.community_account), "inline": True},
            ],
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

        for ticket in sorted(created_orders):
            order = order_map[ticket]
            safe_post(
                webhook_url,
                "New MT5 Order",
                "A new order has been detected.",
                order_fields(order, account_info),
            )

        for ticket in sorted(opened_positions):
            position = position_map[ticket]
            safe_post(
                webhook_url,
                "New MT5 Position",
                "A new position has been opened.",
                position_fields(position, account_info),
            )

        for ticket in sorted(fresh_deals):
            deal = deal_map[ticket]
            safe_post(
                webhook_url,
                "New MT5 Deal",
                "A new deal/execution has been detected.",
                deal_fields(deal, account_info),
            )

        seen_order_tickets = order_tickets
        seen_position_tickets = position_tickets
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
