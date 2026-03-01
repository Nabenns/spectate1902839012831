#!/usr/bin/env python3
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Set

import MetaTrader5 as mt5
import discord

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


def env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name, default)
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def to_float(value: Optional[float], digits: int = 3) -> str:
    if value in (None, 0, 0.0):
        return "-"
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return str(value)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def side_from_order_type(order_type_value) -> str:
    order_type = ORDER_TYPE_LABEL.get(order_type_value, str(order_type_value))
    return "BUY" if "BUY" in order_type else "SELL"


def type_emoji(type_label: str) -> str:
    if type_label.upper() == "LIMIT":
        return "🕒"
    if type_label.upper() == "NOW":
        return "📈"
    return "ℹ️"


def deal_action_label(deal_type, deal_entry) -> str:
    if deal_entry == mt5.DEAL_ENTRY_IN:
        if deal_type == mt5.DEAL_TYPE_BUY:
            return "OPENED BUY"
        if deal_type == mt5.DEAL_TYPE_SELL:
            return "OPENED SELL"
    if deal_entry == mt5.DEAL_ENTRY_OUT:
        if deal_type == mt5.DEAL_TYPE_SELL:
            return "CLOSED BUY"
        if deal_type == mt5.DEAL_TYPE_BUY:
            return "CLOSED SELL"
    if deal_entry == mt5.DEAL_ENTRY_INOUT:
        return "REVERSED POSITION"
    if deal_entry == mt5.DEAL_ENTRY_OUT_BY:
        return "CLOSED BY"
    return "OTHER"


def build_simple_message(
    headline: str,
    type_label: str,
    price: Optional[float],
    sl: Optional[float],
    tp: Optional[float],
    sl_edited: bool = False,
    tp_edited: bool = False,
) -> str:
    sl_suffix = " (edited ✏️)" if sl_edited else ""
    tp_suffix = " (edited ✏️)" if tp_edited else ""
    t_emoji = type_emoji(type_label)
    return (
        f"{headline}\n"
        f"{t_emoji} TYPE : {type_label}\n\n"
        f"PRICE : {to_float(price)}\n"
        f"❌ SL : {to_float(sl)}{sl_suffix}\n"
        f"✅ TP : {to_float(tp)}{tp_suffix}"
    )


def order_message(order, type_label: str, sl_edited: bool = False, tp_edited: bool = False) -> str:
    side = side_from_order_type(order.type)
    headline = f"{side} - {order.symbol}"
    return build_simple_message(
        headline=headline,
        type_label=type_label,
        price=getattr(order, "price_open", 0.0),
        sl=getattr(order, "sl", 0.0),
        tp=getattr(order, "tp", 0.0),
        sl_edited=sl_edited,
        tp_edited=tp_edited,
    )


def order_message_from_cache(cached_order: Dict[str, object], type_label: str) -> str:
    side = side_from_order_type(cached_order.get("type"))
    headline = f"{side} - {cached_order.get('symbol', '-')}"
    return build_simple_message(
        headline=headline,
        type_label=type_label,
        price=float(cached_order.get("price_open", 0.0) or 0.0),
        sl=float(cached_order.get("sl", 0.0) or 0.0),
        tp=float(cached_order.get("tp", 0.0) or 0.0),
    )


def position_message(position, type_label: str, sl_edited: bool = False, tp_edited: bool = False) -> str:
    side = "BUY" if position.type == mt5.POSITION_TYPE_BUY else "SELL"
    headline = f"{side} - {position.symbol}"
    return build_simple_message(
        headline=headline,
        type_label=type_label,
        price=getattr(position, "price_current", getattr(position, "price_open", 0.0)),
        sl=getattr(position, "sl", 0.0),
        tp=getattr(position, "tp", 0.0),
        sl_edited=sl_edited,
        tp_edited=tp_edited,
    )


def deal_message(deal) -> str:
    symbol = str(getattr(deal, "symbol", "-"))
    action = deal_action_label(getattr(deal, "type", -1), getattr(deal, "entry", -1))
    if action.startswith("CLOSED"):
        headline = f"❌ {action} - {symbol}"
    else:
        headline = f"{action} - {symbol}"
    return build_simple_message(
        headline=headline,
        type_label="NOW",
        price=getattr(deal, "price", 0.0),
        sl=getattr(deal, "sl", 0.0),
        tp=getattr(deal, "tp", 0.0),
    )


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


def order_cache(order) -> Dict[str, object]:
    return {
        "ticket": int(order.ticket),
        "symbol": str(order.symbol),
        "type": int(order.type),
        "price_open": float(order.price_open or 0.0),
        "sl": float(order.sl or 0.0),
        "tp": float(order.tp or 0.0),
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


async def send_message(
    channel: discord.abc.Messageable,
    title: str,
    content: str,
    root_message_by_key: Dict[str, int],
    key: Optional[str] = None,
    reply: bool = False,
) -> Optional[int]:
    try:
        kwargs = {}
        if reply and key and key in root_message_by_key and hasattr(channel, "fetch_message"):
            try:
                root_msg = await channel.fetch_message(root_message_by_key[key])  # type: ignore[attr-defined]
                kwargs["reference"] = root_msg
                kwargs["mention_author"] = False
            except Exception:
                pass
        message = await channel.send(content, **kwargs)
        print(f"[OK] Discord sent: {title}")
        return int(message.id)
    except Exception as exc:
        print(f"[WARN] Failed to send Discord message ({title}): {exc}")
        return None


async def upsert_single_reply(
    channel: discord.abc.Messageable,
    title: str,
    content: str,
    root_message_by_key: Dict[str, int],
    update_message_by_key: Dict[str, int],
    key: str,
) -> Optional[int]:
    try:
        # If we already have one reply message for this key, edit it.
        if key in update_message_by_key and hasattr(channel, "fetch_message"):
            try:
                update_msg = await channel.fetch_message(update_message_by_key[key])  # type: ignore[attr-defined]
                await update_msg.edit(content=content)
                print(f"[OK] Discord edited reply: {title}")
                return int(update_msg.id)
            except Exception:
                update_message_by_key.pop(key, None)

        kwargs = {}
        if key in root_message_by_key and hasattr(channel, "fetch_message"):
            try:
                root_msg = await channel.fetch_message(root_message_by_key[key])  # type: ignore[attr-defined]
                kwargs["reference"] = root_msg
                kwargs["mention_author"] = False
            except Exception:
                pass

        message = await channel.send(content, **kwargs)
        update_message_by_key[key] = int(message.id)
        print(f"[OK] Discord sent single reply: {title}")
        return int(message.id)
    except Exception as exc:
        print(f"[WARN] Failed to send/edit single reply ({title}): {exc}")
        return None


def position_key_from_position(position) -> str:
    identifier = int(getattr(position, "identifier", 0) or 0)
    if identifier:
        return f"pos:{identifier}"
    return f"pos:{int(position.ticket)}"


async def monitor_loop(channel: discord.abc.Messageable, interval_sec: int, history_seed_hours: int) -> None:
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

    root_message_by_key: Dict[str, int] = {}
    update_message_by_key: Dict[str, int] = {}
    edited_flags_by_key: Dict[str, Dict[str, bool]] = {}

    await send_message(channel, "MT5 Monitor Online", "🟢 MONITOR ONLINE", root_message_by_key)
    if terminal_info is not None and not terminal_info.trade_allowed:
        await send_message(channel, "MT5 AutoTrading Check", "🟠 AUTOTRADING CHECK: OFF", root_message_by_key)

    print("[INFO] Monitor is running. Press Ctrl+C to stop.")
    while True:
        account_info = mt5.account_info()
        if account_info is None:
            print(f"[WARN] account_info failed: {mt5.last_error()}")
            await asyncio.sleep(interval_sec)
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
            key = f"order:{ticket}"
            msg_id = await send_message(channel, "New MT5 Order", order_message(order, "LIMIT"), root_message_by_key, key=key)
            if msg_id:
                root_message_by_key[key] = msg_id
            edited_flags_by_key[key] = {"sl": False, "tp": False}

        for ticket in sorted(common_orders):
            order = order_map[ticket]
            current_snapshot = order_snapshot(order)
            previous_snapshot = seen_order_snapshots.get(ticket, {})
            updates = changed_keys(previous_snapshot, current_snapshot)
            if not updates:
                continue
            sl_edited = "sl" in updates
            tp_edited = "tp" in updates
            key = f"order:{ticket}"
            flags = edited_flags_by_key.setdefault(key, {"sl": False, "tp": False})
            if sl_edited:
                flags["sl"] = True
            if tp_edited:
                flags["tp"] = True
            await upsert_single_reply(
                channel,
                "Pending Order Updated",
                order_message(order, "LIMIT", sl_edited=flags["sl"], tp_edited=flags["tp"]),
                root_message_by_key,
                update_message_by_key,
                key,
            )

        for ticket in sorted(removed_orders):
            cached_order = seen_order_cache.get(ticket)
            if not cached_order:
                continue
            key = f"order:{ticket}"
            title = "Pending Order Filled/Closed" if ticket in deal_order_tickets else "Pending Order Canceled"
            await send_message(
                channel,
                title,
                order_message_from_cache(cached_order, "LIMIT"),
                root_message_by_key,
                key=key,
                reply=True,
            )
            root_message_by_key.pop(key, None)
            update_message_by_key.pop(key, None)
            edited_flags_by_key.pop(key, None)

        for ticket in sorted(common_positions):
            position = position_map[ticket]
            current_snapshot = position_snapshot(position)
            previous_snapshot = seen_position_snapshots.get(ticket, {})
            updates = changed_keys(previous_snapshot, current_snapshot)
            if not updates:
                continue
            sl_edited = "sl" in updates
            tp_edited = "tp" in updates
            key = position_key_from_position(position)
            flags = edited_flags_by_key.setdefault(key, {"sl": False, "tp": False})
            if sl_edited:
                flags["sl"] = True
            if tp_edited:
                flags["tp"] = True
            await upsert_single_reply(
                channel,
                "Position Protection Updated",
                position_message(position, "NOW", sl_edited=flags["sl"], tp_edited=flags["tp"]),
                root_message_by_key,
                update_message_by_key,
                key,
            )

        for ticket in sorted(fresh_deals):
            deal = deal_map[ticket]
            position_id = int(getattr(deal, "position_id", 0) or 0)
            action = deal_action_label(getattr(deal, "type", -1), getattr(deal, "entry", -1))
            key = f"pos:{position_id}" if position_id else None
            is_open = action.startswith("OPENED")
            is_close = action.startswith("CLOSED")

            msg_id = await send_message(
                channel,
                "New MT5 Deal",
                deal_message(deal),
                root_message_by_key,
                key=key,
                reply=bool(key and not is_open),
            )

            if key and msg_id and is_open:
                root_message_by_key[key] = msg_id
                edited_flags_by_key[key] = {"sl": False, "tp": False}
            if key and is_close:
                root_message_by_key.pop(key, None)
                update_message_by_key.pop(key, None)
                edited_flags_by_key.pop(key, None)

        seen_order_tickets = order_tickets
        seen_position_tickets = position_tickets
        seen_order_snapshots = {int(o.ticket): order_snapshot(o) for o in orders}
        seen_position_snapshots = {int(p.ticket): position_snapshot(p) for p in positions}
        seen_order_cache = {int(o.ticket): order_cache(o) for o in orders}
        seen_deal_tickets.update(fresh_deals)
        await asyncio.sleep(interval_sec)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor MT5 activity and send Discord bot messages.")
    parser.add_argument("--interval", type=int, default=int(env("POLL_INTERVAL_SEC", "3")), help="Polling interval in seconds.")
    parser.add_argument(
        "--history-seed-hours",
        type=int,
        default=int(env("HISTORY_SEED_HOURS", "24")),
        help="Initial history scan window to avoid duplicate old deals.",
    )
    return parser.parse_args()


async def run() -> int:
    if load_dotenv:
        load_dotenv()

    args = parse_args()
    bot_token = env("DISCORD_BOT_TOKEN")
    channel_id_raw = env("DISCORD_CHANNEL_ID")
    if not bot_token:
        print("Missing DISCORD_BOT_TOKEN in environment/.env")
        return 2
    if not channel_id_raw:
        print("Missing DISCORD_CHANNEL_ID in environment/.env")
        return 2

    try:
        channel_id = int(channel_id_raw)
    except ValueError:
        print("DISCORD_CHANNEL_ID must be a numeric channel ID.")
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

    intents = discord.Intents.none()
    client = discord.Client(intents=intents)
    started = {"value": False}

    @client.event
    async def on_ready():
        if started["value"]:
            return
        started["value"] = True
        print(f"[INFO] Logged in as {client.user}")
        channel = client.get_channel(channel_id)
        if channel is None:
            try:
                channel = await client.fetch_channel(channel_id)
            except Exception as exc:
                print(f"[ERR] Could not access channel {channel_id}: {exc}")
                await client.close()
                return
        try:
            await monitor_loop(channel, args.interval, args.history_seed_hours)
        except Exception as exc:
            print(f"[ERR] Runtime failure: {exc}")
            await client.close()

    try:
        await client.start(bot_token)
    finally:
        mt5.shutdown()
    return 0


def main() -> int:
    try:
        return asyncio.run(run())
    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
