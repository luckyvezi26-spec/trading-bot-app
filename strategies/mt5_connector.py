import MetaTrader5 as mt5
import pandas as pd

def test_mt5_connection():
    if not mt5.initialize():
        print(f"initialize() failed, error code = {mt5.last_error()}")
        return

    print("Successfully connected to MetaTrader 5 terminal!")

    terminal_info = mt5.terminal_info()
    if terminal_info is not None:
        print(f"Terminal Connected: {terminal_info.name}")
        print(f"Company: {terminal_info.company}")

    # Search broker symbol list for gold variations
    all_symbols = mt5.symbols_get()
    target_symbol = None

    if all_symbols:
        for s in all_symbols:
            if "XAU" in s.name.upper() or "GOLD" in s.name.upper():
                target_symbol = s.name
                break

    if not target_symbol:
        print("Could not locate a Gold symbol on this broker account. Check Market Watch.")
        mt5.shutdown()
        return

    print(f"Located active Gold symbol: {target_symbol}")

    # Enable symbol in Market Watch
    if not mt5.symbol_select(target_symbol, True):
        print(f"Failed to select {target_symbol}, error code = {mt5.last_error()}")
        mt5.shutdown()
        return

    # Fetch last 100 hourly candles
    rates = mt5.copy_rates_from_pos(target_symbol, mt5.TIMEFRAME_H1, 0, 100)
    mt5.shutdown()

    if rates is not None and len(rates) > 0:
        df_rates = pd.DataFrame(rates)
        df_rates['time'] = pd.to_datetime(df_rates['time'], unit='s')
        print(f"\n--- Successfully fetched {len(df_rates)} live candles for {target_symbol} ---")
        print(df_rates[['time', 'open', 'high', 'low', 'close', 'tick_volume']].tail(5))
    else:
        print(f"Failed to fetch rates for {target_symbol}")

if __name__ == "__main__":
    test_mt5_connection()
