import re
import asyncio
import datetime
import MetaTrader5 as mt5
from telethon import TelegramClient, events

# --- YOUR TELEGRAM API CREDENTIALS ---
API_ID = 30429157
API_HASH = '593ecf3e83e31176de2a8269118893d8'

# --- FUNDED ACCOUNT & RISK MANAGEMENT SETTINGS ---
SYMBOLS = ["XAUUSD", "BTCUSD", "ETHUSD"]  # Allowed assets only
LOT_SIZES = {
    "XAUUSD": 0.05,
    "BTCUSD": 0.03,
    "ETHUSD": 0.10
}
REDUCED_XAU_LOT = 0.03  # Reduced lot size when risk exceeds $50 or approaches limits
MAGIC_NUMBER = 202630
MAX_DAILY_LOSS = 150.0  # Strict hard cap: Stop trading & close all if daily loss hits $150
MAX_SINGLE_TRADE_RISK = 50.0  # Max $50 risk for order 1

client = TelegramClient('telegram_session', API_ID, API_HASH)

current_trading_day = datetime.date.today()
daily_loss_triggered = False
golden_circle_peaks = {}  # {ticket: peak_price}
autonomous_scanned_bars = {} # Tracks last scanned bar time per symbol

def get_todays_realized_pl():
    today = datetime.date.today()
    utc_from = datetime.datetime(today.year, today.month, today.day, 0, 0, 0)
    utc_to = datetime.datetime.now()
    
    deals = mt5.history_deals_get(utc_from, utc_to)
    if not deals:
        return 0.0
    
    total_pl = 0.0
    for deal in deals:
        if deal.magic == MAGIC_NUMBER and deal.entry == mt5.DEAL_ENTRY_OUT:
            total_pl += deal.profit + deal.swap + deal.commission
    return total_pl

def get_floating_unrealized_pl():
    positions = mt5.positions_get()
    if not positions:
        return 0.0
    
    floating_pl = 0.0
    for pos in positions:
        if pos.magic == MAGIC_NUMBER:
            floating_pl += pos.profit + pos.swap
    return floating_pl

def calculate_trade_risk(symbol, lot_size, entry_price, sl_price):
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info and hasattr(symbol_info, 'trade_contract_size') and symbol_info.trade_contract_size > 0:
        contract_size = symbol_info.trade_contract_size
    else:
        contract_size = 100.0 if symbol == "XAUUSD" else 1.0
            
    price_diff = abs(entry_price - sl_price)
    risk_usd = price_diff * lot_size * contract_size
    return risk_usd

def execute_telegram_trades(symbol, action, price, sl, tp1, tp2, is_pending=False, is_golden_circle=False):
    global daily_loss_triggered
    if daily_loss_triggered:
        print(f"\n[BLOCKED] Daily loss limit of ${MAX_DAILY_LOSS} reached. No new trades will be taken today.")
        return

    total_day_pl = get_todays_realized_pl() + get_floating_unrealized_pl()
    if total_day_pl <= -MAX_DAILY_LOSS:
        print(f"\n[SAFETY LOCK] Daily loss limit of ${MAX_DAILY_LOSS} reached! Blocking new entries.")
        daily_loss_triggered = True
        close_all_bot_trades()
        return

    lot_size = LOT_SIZES.get(symbol, 0.05)
    
    # Evaluate initial order risk
    risk_1 = calculate_trade_risk(symbol, lot_size, price, sl)
    
    # Gold Risk Reduction Rule: If risk exceeds $50 or daily drawdown is heavy, downscale XAUUSD lot size to 0.03
    if symbol == "XAUUSD" and (risk_1 > MAX_SINGLE_TRADE_RISK or total_day_pl <= -100.0):
        lot_size = REDUCED_XAU_LOT
        risk_1 = calculate_trade_risk(symbol, lot_size, price, sl)
        print(f"\n[RISK ADJUSTMENT] XAUUSD risk exceeded threshold or drawdown active. Reduced lot size to {lot_size} (New Risk: ${risk_1:.2f})")

    print(f"\n[RISK EVALUATION] {symbol} Order 1 Dollar Risk: ${risk_1:.2f} (Lot Size: {lot_size})")
    
    num_orders = 1
    if risk_1 <= MAX_SINGLE_TRADE_RISK:
        num_orders = 2
        print(f"[RISK CHECK PASSED] Order 1 Risk (${risk_1:.2f}) <= ${MAX_SINGLE_TRADE_RISK}. Placing BOTH orders.")
    else:
        print(f"[RISK CHECK CAP EXCEEDED] Order 1 Risk (${risk_1:.2f}) > ${MAX_SINGLE_TRADE_RISK}. Placing ONLY 1 order.")

    risk_dist = abs(price - sl)
    if is_golden_circle:
        tp_target1 = price + (risk_dist * 2.5) if action == "BUY" else price - (risk_dist * 2.5)
        tp_target2 = price + (risk_dist * 8.0) if action == "BUY" else price - (risk_dist * 8.0)
        tps = [round(tp_target1, 2), round(tp_target2, 2)]
    else:
        tps = [tp1, tp2]

    if is_pending:
        order_type = mt5.ORDER_TYPE_BUY_STOP if action == "BUY" else mt5.ORDER_TYPE_SELL_STOP
        action_type_desc = "PENDING STOP ORDER"
    else:
        order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL
        action_type_desc = "MARKET EXECUTION"

    comment_tag = "GoldenCircle" if is_golden_circle else "SignalTrade"
    print(f"\n[FUNDED EXECUTION - {action_type_desc}] Placing {num_orders} {action} on {symbol} at entry {price}...")
    
    for i in range(num_orders):
        request = {
            "action": mt5.TRADE_ACTION_PENDING if is_pending else mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot_size,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tps[i],
            "deviation": 20,
            "magic": MAGIC_NUMBER,
            "comment": f"{comment_tag} #{i+1}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(request)
        if res.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"[SUCCESS] {symbol} {action_type_desc} #{i+1} placed | Price: {price} | SL: {sl} | TP: {tps[i]}")
        else:
            print(f"[ERROR] {symbol} Trade #{i+1} failed with retcode: {res.retcode}")

def close_single_position(position, close_volume=None):
    ticket = position.ticket
    lot = close_volume if close_volume else position.volume
    pos_type = position.type
    sym = position.symbol
    
    close_action = mt5.ORDER_TYPE_SELL if pos_type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
    tick = mt5.symbol_info_tick(sym)
    if not tick:
        return False
    close_price = tick.bid if pos_type == mt5.POSITION_TYPE_BUY else tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": sym,
        "volume": lot,
        "type": close_action,
        "position": ticket,
        "price": close_price,
        "deviation": 20,
        "magic": MAGIC_NUMBER,
        "comment": "Partial / Full Exit",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(request)
    return res.retcode == mt5.TRADE_RETCODE_DONE

def close_all_bot_trades():
    positions = mt5.positions_get()
    if not positions:
        return

    print(f"\n[EMERGENCY CLOSE] Closing all active bot trades across all symbols...")
    for pos in positions:
        if pos.magic == MAGIC_NUMBER:
            close_single_position(pos)

def move_trades_to_breakeven(symbol=None, position_ticket=None):
    positions = mt5.positions_get()
    if not positions:
        return

    for pos in positions:
        if pos.magic == MAGIC_NUMBER:
            if symbol and pos.symbol != symbol:
                continue
            if position_ticket and pos.ticket != position_ticket:
                continue
            if pos.sl != pos.price_open:
                request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "symbol": pos.symbol,
                    "position": pos.ticket,
                    "sl": pos.price_open,
                    "tp": pos.tp,
                }
                res = mt5.order_send(request)
                if res.retcode == mt5.TRADE_RETCODE_DONE:
                    print(f"[BREAK EVEN SUCCESS] {pos.symbol} Position #{pos.ticket} SL moved to entry price ({pos.price_open}).")

# --- GOLD TRADER DAN AUTONOMOUS CHART PATTERN SCANNER ---
def check_autonomous_chart_patterns():
    global autonomous_scanned_bars, daily_loss_triggered
    if daily_loss_triggered:
        return

    symbol = "XAUUSD"
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 10)
    if rates is None or len(rates) < 10:
        return

    latest_bar_time = rates[-1]['time']
    if symbol in autonomous_scanned_bars and autonomous_scanned_bars[symbol] == latest_bar_time:
        return  # Already scanned this candle
    
    autonomous_scanned_bars[symbol] = latest_bar_time
    
    # Simple Gold Trader Dan Playbook Logic: Double Bottom / Double Top & Flag Detection
    closes = [r['close'] for r in rates]
    highs = [r['high'] for r in rates]
    lows = [r['low'] for r in rates]
    
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return

    # Check for Double Bottom (Bullish Reversal Pattern)
    if lows[-3] <= min(lows[-10:-3]) + 0.5 and lows[-1] > lows[-3]:
        print(f"\n[DAN PATTERN ENGINE] Double Bottom detected on {symbol} H1! Executing Autonomous Long...")
        entry = tick.ask
        sl = min(lows[-5:]) - 2.0
        tp = entry + ((entry - sl) * 2.5)
        execute_telegram_trades(symbol, "BUY", entry, sl, tp, tp + 5.0, is_pending=False, is_golden_circle=True)

    # Check for Double Top (Bearish Reversal Pattern)
    elif highs[-3] >= max(highs[-10:-3]) - 0.5 and highs[-1] < highs[-3]:
        print(f"\n[DAN PATTERN ENGINE] Double Top detected on {symbol} H1! Executing Autonomous Short...")
        entry = tick.bid
        sl = max(highs[-5:]) + 2.0
        tp = entry - ((sl - entry) * 2.5)
        execute_telegram_trades(symbol, "SELL", entry, sl, tp, tp - 5.0, is_pending=False, is_golden_circle=True)

async def background_risk_monitor():
    global daily_loss_triggered, current_trading_day, golden_circle_peaks
    
    while True:
        await asyncio.sleep(2)

        today = datetime.date.today()
        if today != current_trading_day:
            current_trading_day = today
            daily_loss_triggered = False

        # Run autonomous pattern check
        try:
            check_autonomous_chart_patterns()
        except Exception as e:
            pass

        positions = mt5.positions_get()
        total_day_pl = get_todays_realized_pl() + (sum(p.profit + p.swap for p in positions if p.magic == MAGIC_NUMBER) if positions else 0.0)
        
        if total_day_pl <= -MAX_DAILY_LOSS and not daily_loss_triggered:
            print(f"\n[CRITICAL WARNING] DAILY LOSS LIMIT HIT (${total_day_pl:.2f})! Shutting down trading for today.")
            daily_loss_triggered = True
            close_all_bot_trades()
            continue

        if not positions:
            continue

        for pos in positions:
            if pos.magic != MAGIC_NUMBER:
                continue
                
            tick = mt5.symbol_info_tick(pos.symbol)
            if not tick:
                continue

            is_gc = "GoldenCircle" in pos.comment
            
            # --- DAN THE GOLDEN CIRCLE CUSTOM PROFIT TAKING & RETRACEMENT EXIT ---
            if is_gc:
                point_val = mt5.symbol_info(pos.symbol).point if mt5.symbol_info(pos.symbol) else 0.01
                pip_40_dist = point_val * 400 if pos.symbol == "XAUUSD" else point_val * 40

                risk_dist = abs(pos.price_open - pos.sl) if pos.sl > 0 else 0
                target_2_5_dist = risk_dist * 2.5
                
                current_dist = (tick.bid - pos.price_open) if pos.type == mt5.POSITION_TYPE_BUY else (pos.price_open - tick.ask)

                if risk_dist > 0 and current_dist >= target_2_5_dist:
                    if round(pos.volume, 2) >= 0.05:
                        all_gc_pos = [p for p in positions if p.magic == MAGIC_NUMBER and p.symbol == pos.symbol and "GoldenCircle" in p.comment]
                        
                        if len(all_gc_pos) > 1:
                            print(f"\n[GOLDEN CIRCLE 1:2.5 HIT] Closing Order 1 (#{pos.ticket}) full lot...")
                            close_single_position(pos)
                        else:
                            print(f"\n[GOLDEN CIRCLE 1:2.5 HIT] Trimming 0.03 lot from Order (#{pos.ticket}), leaving runner...")
                            close_single_position(pos, close_volume=0.03)
                            move_trades_to_breakeven(pos.symbol, pos.ticket)

                    if pos.sl != pos.price_open:
                        move_trades_to_breakeven(pos.symbol, pos.ticket)

                # 40-Pip Retracement Exit on Runner
                if round(pos.volume, 2) <= 0.02 and pos.sl == pos.price_open:
                    current_price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask
                    
                    if pos.ticket not in golden_circle_peaks:
                        golden_circle_peaks[pos.ticket] = current_price
                    else:
                        if pos.type == mt5.POSITION_TYPE_BUY:
                            golden_circle_peaks[pos.ticket] = max(golden_circle_peaks[pos.ticket], current_price)
                            drop_from_peak = golden_circle_peaks[pos.ticket] - current_price
                            if drop_from_peak >= pip_40_dist:
                                print(f"\n[40-PIP RETRACEMENT EXIT] {pos.symbol} BUY dropped {drop_from_peak:.2f} from peak. Closing runner!")
                                close_single_position(pos)
                                golden_circle_peaks.pop(pos.ticket, None)
                        else:
                            golden_circle_peaks[pos.ticket] = min(golden_circle_peaks[pos.ticket], current_price)
                            rise_from_peak = current_price - golden_circle_peaks[pos.ticket]
                            if rise_from_peak >= pip_40_dist:
                                print(f"\n[40-PIP RETRACEMENT EXIT] {pos.symbol} SELL rose {rise_from_peak:.2f} from peak. Closing runner!")
                                close_single_position(pos)
                                golden_circle_peaks.pop(pos.ticket, None)

            else:
                if pos.sl == pos.price_open:
                    continue
                if pos.tp > 0:
                    if pos.type == mt5.POSITION_TYPE_BUY and tick.bid >= pos.tp:
                        move_trades_to_breakeven(pos.symbol, pos.ticket)
                    elif pos.type == mt5.POSITION_TYPE_SELL and tick.ask <= pos.tp:
                        move_trades_to_breakeven(pos.symbol, pos.ticket)

@client.on(events.NewMessage)
async def handle_new_signal(event):
    if event.message.forward:
        return

    text = event.message.text
    if not text:
        return

    sender_name = ""
    chat = await event.get_chat()
    if chat and hasattr(chat, 'title') and chat.title:
        sender_name = chat.title

    is_golden_circle = "dan the golden circle" in sender_name.lower() or "golden circle" in sender_name.lower()

    upper_text = text.upper()

    target_symbol = "XAUUSD"
    if "BTC" in upper_text or "BITCOIN" in upper_text:
        target_symbol = "BTCUSD"
    elif "ETH" in upper_text or "ETHEREUM" in upper_text:
        target_symbol = "ETHUSD"
    elif "GOLD" in upper_text or "XAU" in upper_text:
        target_symbol = "XAUUSD"

    be_keywords = ["BREAK EVEN", "BREAKEVEN", "SL TO ENTRY", "SL TO COST", "MOVE SL", "TP2 HIT"]
    if any(keyword in upper_text for keyword in be_keywords):
        move_trades_to_breakeven(target_symbol)
        return

    exit_keywords = ["COLLECT", "PARTIAL", "CLOSE", "TAKE PROFIT"]
    if any(keyword in upper_text for keyword in exit_keywords):
        close_all_bot_trades()
        return

    action = None
    if "BUY" in upper_text:
        action = "BUY"
    elif "SELL" in upper_text:
        action = "SELL"
        
    if not action:
        return

    sl_match = re.search(r'SL[:\s@]+([\d\.]+)', text, re.IGNORECASE)
    tp_matches = re.findall(r'TP\d*[:\s@]+([\d\.]+)', text, re.IGNORECASE)

    if not sl_match:
        return

    sl = float(sl_match.group(1))
    
    entry_range_match = re.search(r'(?:ENTRY|ZONE|PRICE)?[:\s@]*([\d\.]+)\s*(?:-|TO)\s*([\d\.]+)', text, re.IGNORECASE)
    specific_entry_match = re.search(r'(?:ENTRY|AT)[:\s@]+([\d\.]+)', text, re.IGNORECASE)

    tick = mt5.symbol_info_tick(target_symbol)
    if not tick:
        return

    market_price = tick.ask if action == "BUY" else tick.bid
    entry_price = market_price
    is_pending = False

    if is_golden_circle and (entry_range_match or specific_entry_match):
        is_pending = True
        if entry_range_match:
            range_low = float(entry_range_match.group(1))
            range_high = float(entry_range_match.group(2))
            if action == "BUY":
                entry_price = max(range_low, range_high)
            else:
                entry_price = min(range_low, range_high)
        elif specific_entry_match:
            entry_price = float(specific_entry_match.group(1))
    else:
        if entry_range_match:
            range_low = float(entry_range_match.group(1))
            range_high = float(entry_range_match.group(2))
            min_range = min(range_low, range_high)
            max_range = max(range_low, range_high)

            if not (min_range <= market_price <= max_range):
                print(f"\n[RANGE CHECK] {target_symbol} price ({market_price}) outside range [{min_range} - {max_range}]. Skipping.")
                return
            entry_price = market_price
        elif specific_entry_match:
            entry_price = float(specific_entry_match.group(1))

    risk = abs(entry_price - sl)

    tps = [float(tp) for tp in tp_matches] if tp_matches else []
    
    if len(tps) >= 3:
        tp1 = tps[1]
        tp2 = tps[2]
    elif len(tps) == 2:
        tp1 = tps[0]
        tp2 = tps[1]
    else:
        multiplier = 2.5 if target_symbol == "XAUUSD" else 2.0
        if action == "BUY":
            tp1 = round(entry_price + (risk * multiplier), 2)
            tp2 = round(entry_price + (risk * (multiplier + 0.5)), 2)
        else:
            tp1 = round(entry_price - (risk * multiplier), 2)
            tp2 = round(entry_price - (risk * (multiplier + 0.5)), 2)

    source_label = "DAN THE GOLDEN CIRCLE" if is_golden_circle else "VIP CHANNEL"
    print(f"\n==========================================")
    print(f"[NEW SIGNAL VALIDATED - {source_label}] ({target_symbol})")
    print(f"Action: {action} | Mode: {'Pending Stop' if is_pending else 'Market'} | Entry: {entry_price} | SL: {sl}")
    print(f"==========================================")

    execute_telegram_trades(target_symbol, action, entry_price, sl, tp1, tp2, is_pending=is_pending, is_golden_circle=is_golden_circle)

async def main():
    if not mt5.initialize():
        print("MT5 Initialization failed.")
        return
        
    print(f"=== Multi-Asset Telegram & Autonomous Pattern Auto-Trader Active ===")
    print(f"Watching Assets: {SYMBOLS} | Lot Sizes: {LOT_SIZES} | Max Daily Loss Protection: ${MAX_DAILY_LOSS}")
    
    asyncio.create_task(background_risk_monitor())

    while True:
        try:
            print("\n[TELEGRAM] Connecting to Telegram client...")
            await client.start()
            print("[TELEGRAM] Connected successfully and listening for signals & chart patterns!")
            
            await client.run_until_disconnected()
        except Exception as e:
            print(f"\n[CONNECTION ERROR] Lost connection: {e}")
            print("[RECONNECTION] Retrying connection in 10 seconds...")
            await asyncio.sleep(10)
        except KeyboardInterrupt:
            print("\n[SHUTDOWN] Bot stopped manually by user.")
            break

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram terminated.")
        