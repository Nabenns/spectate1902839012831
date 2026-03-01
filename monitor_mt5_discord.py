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

def deal_action_label(deal_type, deal_entry) -> str:
    if deal_entry == mt5.DEAL_ENTRY_IN:
        if deal_type == mt5.DEAL_TYPE_BUY:
            return "Opened BUY"
        if deal_type == mt5.DEAL_TYPE_SELL:
            return "Opened SELL"
    if deal_entry == mt5.DEAL_ENTRY_OUT:
        if deal_type == mt5.DEAL_TYPE_SELL:
            return "Closed BUY"
        if deal_type == mt5.DEAL_TYPE_BUY:
            return "Closed SELL"
    if deal_entry == mt5.DEAL_ENTRY_INOUT:
        return "Reversed Position"
    if deal_entry == mt5.DEAL_ENTRY_OUT_BY:
        return "Closed By"
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


def post_discord(webhook_url: str, content: str) -> None:
    payload = {
        "username": "MT5 Monitor Bot",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/5968/5968260.png",
        "content": content,
    }
    response = requests.post(webhook_url, json=payload, timeout=15)
    response.raise_for_status()


def safe_post(webhook_url: str, title: str, content: str) -> None:
    try:
        post_discord(webhook_url, content)
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


def line_value(value: Optional[float], digits: int = 3) -> str:
    if value in (None, 0, 0.0):
        return "-"
    return to_float(value, digits)


def build_simple_message(side: str, symbol: str, type_label: str, price: Optional[float], sl: Optional[float], tp: Optional[float], sl_edited: bool = False, tp_edited: bool = False) -> str:
    sl_suffix = " (edited)" if sl_edited else ""
    tp_suffix = " (edited)" if tp_edited else ""
    return (
        f"{side} - {symbol}\n"
        f"TYPE : {type_label}\n\n"
        f"PRICE : {line_value(price)}\n"
        f"SL : {line_value(sl)}{sl_suffix}\n"
        f"TP : {line_value(tp)}{tp_suffix}"
    )


def build_action_message(action: str, symbol: str, type_label: str, price: Optional[float], sl: Optional[float], tp: Optional[float]) -> str:
    return (
        f"{action} - {symbol}\n"
        f"TYPE : {type_label}\n\n"
        f"PRICE : {line_value(price)}\n"
        f"SL : {line_value(sl)}\n"
        f"TP : {line_value(tp)}"
    )


def order_message(order, type_label: str, sl_edited: bool = False, tp_edited: bool = False) -> str:
    order_type = ORDER_TYPE_LABEL.get(order.type, str(order.type))
    side = "BUY" if "BUY" in order_type else "SELL"
    return build_simple_message(
        side=side,
        symbol=str(order.symbol),
        type_label=type_label,
        price=getattr(order, "price_open", 0.0),
        sl=getattr(order, "sl", 0.0),
        tp=getattr(order, "tp", 0.0),
        sl_edited=sl_edited,
        tp_edited=tp_edited,
    )


def order_message_from_cache(cached_order: Dict[str, object], type_label: str) -> str:
    order_type = str(cached_order.get("type", ""))
    side = "BUY" if "BUY" in order_type else "SELL"
    return build_simple_message(
        side=side,
        symbol=str(cached_order.get("symbol", "-")),
        type_label=type_label,
        price=float(cached_order.get("price_open", 0.0) or 0.0),
        sl=float(cached_order.get("sl", 0.0) or 0.0),
        tp=float(cached_order.get("tp", 0.0) or 0.0),
    )


def position_message(position, type_label: str, sl_edited: bool = False, tp_edited: bool = False) -> str:
    side = "BUY" if position.type == mt5.POSITION_TYPE_BUY else "SELL"
    return build_simple_message(
        side=side,
        symbol=str(position.symbol),
        type_label=type_label,
        price=getattr(position, "price_current", getattr(position, "price_open", 0.0)),
        sl=getattr(position, "sl", 0.0),
        tp=getattr(position, "tp", 0.0),
        sl_edited=sl_edited,
        tp_edited=tp_edited,
    )


def deal_message(deal) -> str:
    deal_symbol = getattr(deal, "symbol", "-")
    deal_type = getattr(deal, "type", "-")
    deal_entry = getattr(deal, "entry", "-")
    deal_price = getattr(deal, "price", 0.0)
    deal_sl = getattr(deal, "sl", None)
    deal_tp = getattr(deal, "tp", None)
    action = deal_action_label(deal_type, deal_entry)
    return build_action_message(
        action=action.upper(),
        symbol=str(deal_symbol),
        type_label="NOW",
        price=deal_price,
        sl=deal_sl,
        tp=deal_tp,
    )


def order_snapshot(order) -> Dict[str, float]:
    return {
        "price_open": float(order.price_open or 0.0),
        "sl": float(order.sl or 0.0),
        "tp": float(order.tp or 0.0),
        "volume_initial": float(order.volume_initial or 0.0),
    }


def order_cache(order) -> Dict[str, object]:
    return {
        "ticket": int(order.ticket),
        "symbol": str(order.symbol),
        "type": ORDER_TYPE_LABEL.get(order.type, str(order.type)),
        "volume_initial": float(order.volume_initial or 0.0),
        "price_open": float(order.price_open or 0.0),
        "sl": float(order.sl or 0.0),
        "tp": float(order.tp or 0.0),
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
    seen_order_cache = {int(o.ticket): order_cache(o) for o in current_orders}

    since = utc_now() - timedelta(hours=history_seed_hours)
    existing_deals = mt5.history_deals_get(since, utc_now()) or []
    seen_deal_tickets = tickets(existing_deals)

    safe_post(
        webhook_url,
        "MT5 Monitor Online",
        "MONITOR ONLINE",
    )
    if terminal_info is not None and not terminal_info.trade_allowed:
        safe_post(
            webhook_url,
            "MT5 AutoTrading Check",
            "AUTOTRADING CHECK: OFF",
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
        removed_orders = seen_order_tickets - order_tickets
        fresh_deals = deal_tickets - seen_deal_tickets
        common_orders = order_tickets & seen_order_tickets
        common_positions = position_tickets & seen_position_tickets
        deal_order_tickets = {int(getattr(d, "order", 0) or 0) for d in new_deals}

        for ticket in sorted(created_orders):
            order = order_map[ticket]
            safe_post(
                webhook_url,
                "New MT5 Order",
                order_message(order, "LIMIT"),
            )

        for ticket in sorted(common_orders):
            order = order_map[ticket]
            current_snapshot = order_snapshot(order)
            previous_snapshot = seen_order_snapshots.get(ticket, {})
            updates = changed_keys(previous_snapshot, current_snapshot)
            if not updates:
                continue
            sl_edited = "sl" in updates
            tp_edited = "tp" in updates
            safe_post(
                webhook_url,
                "Pending Order Updated",
                order_message(order, "LIMIT", sl_edited=sl_edited, tp_edited=tp_edited),
            )

        for ticket in sorted(removed_orders):
            cached_order = seen_order_cache.get(ticket)
            if not cached_order:
                continue
            if ticket in deal_order_tickets:
                title = "Pending Order Filled/Closed"
            else:
                title = "Pending Order Canceled"
            safe_post(
                webhook_url,
                title,
                order_message_from_cache(cached_order, "LIMIT"),
            )

        for ticket in sorted(common_positions):
            position = position_map[ticket]
            current_snapshot = position_snapshot(position)
            previous_snapshot = seen_position_snapshots.get(ticket, {})
            updates = changed_keys(previous_snapshot, current_snapshot)
            if not updates:
                continue
            sl_edited = "sl" in updates
            tp_edited = "tp" in updates
            safe_post(
                webhook_url,
                "Position Protection Updated",
                position_message(position, "NOW", sl_edited=sl_edited, tp_edited=tp_edited),
            )

        for ticket in sorted(fresh_deals):
            deal = deal_map[ticket]
            safe_post(
                webhook_url,
                "New MT5 Deal",
                deal_message(deal),
            )

        seen_order_tickets = order_tickets
        seen_position_tickets = position_tickets
        seen_order_snapshots = {int(o.ticket): order_snapshot(o) for o in orders}
        seen_position_snapshots = {int(p.ticket): position_snapshot(p) for p in positions}
        seen_order_cache = {int(o.ticket): order_cache(o) for o in orders}
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
