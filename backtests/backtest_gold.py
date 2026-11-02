import pandas as pd
import numpy as np

def run_backtest(file_path):
    df = pd.read_csv(file_path, header=0)
    
    if len(df) > 0 and df.iloc[0].astype(str).str.contains('GC=F|\\^NDX|Price').any():
        df = df.iloc[1:].reset_index(drop=True)

    df.columns = [str(col).lower() for col in df.columns]
    close_col = [c for c in df.columns if 'close' in c][0]
    high_col = [c for c in df.columns if 'high' in c][0]
    low_col = [c for c in df.columns if 'low' in c][0]
    
    for col in [close_col, high_col, low_col]:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # Indicators & Dynamic Levels
    window = 20
    df['dynamic_resistance'] = df[high_col].rolling(window=window).max()
    df['dynamic_support'] = df[low_col].rolling(window=window).min()
    df['fast_sma'] = df[close_col].rolling(window=10).mean()
    df['slow_sma'] = df[close_col].rolling(window=30).mean()

    # Signals & Risk Management
    df['signal'] = 0
    df['stop_loss'] = np.nan
    df['take_profit'] = np.nan
    
    breakout_long = (df[close_col] > df['dynamic_resistance'].shift(1)) & (df['fast_sma'] > df['slow_sma'])
    df.loc[breakout_long, 'signal'] = 1
    df.loc[breakout_long, 'stop_loss'] = df['dynamic_support']
    risk_long = df[close_col] - df['stop_loss']
    df.loc[breakout_long, 'take_profit'] = df[close_col] + (risk_long * 2.0)

    breakout_short = (df[close_col] < df['dynamic_support'].shift(1)) & (df['fast_sma'] < df['slow_sma'])
    df.loc[breakout_short, 'signal'] = -1
    df.loc[breakout_short, 'stop_loss'] = df['dynamic_resistance']
    risk_short = df['stop_loss'] - df[close_col]
    df.loc[breakout_short, 'take_profit'] = df[close_col] - (risk_short * 2.0)

    # Simple Backtest Loop Simulation
    trades = []
    in_trade = False
    trade_type = 0
    entry_price = 0
    sl = 0
    tp = 0

    for i in range(len(df)):
        current_price = df.loc[i, close_col]
        current_high = df.loc[i, high_col]
        current_low = df.loc[i, low_col]
        sig = df.loc[i, 'signal']

        if in_trade:
            if trade_type == 1: # Long Trade
                if current_high >= tp:
                    trades.append({'Result': 'WIN', 'PnL': tp - entry_price})
                    in_trade = False
                elif current_low <= sl:
                    trades.append({'Result': 'LOSS', 'PnL': sl - entry_price})
                    in_trade = False
            elif trade_type == -1: # Short Trade
                if current_low <= tp:
                    trades.append({'Result': 'WIN', 'PnL': entry_price - tp})
                    in_trade = False
                elif current_high >= sl:
                    trades.append({'Result': 'LOSS', 'PnL': entry_price - sl})
                    in_trade = False
        
        elif sig != 0 and not in_trade:
            # Only enter if stop loss is valid and positive risk
            current_sl = df.loc[i, 'stop_loss']
            current_tp = df.loc[i, 'take_profit']
            if not np.isnan(current_sl) and not np.isnan(current_tp):
                in_trade = True
                trade_type = sig
                entry_price = current_price
                sl = current_sl
                tp = current_tp

    print(f"\n--- Backtest Results for Gold ({file_path}) ---")
    if len(trades) > 0:
        wins = len([t for t in trades if t['Result'] == 'WIN'])
        losses = len([t for t in trades if t['Result'] == 'LOSS'])
        win_rate = (wins / len(trades)) * 100
        print(f"Total Trades Taken: {len(trades)}")
        print(f"Winning Trades: {wins}")
        print(f"Losing Trades: {losses}")
        print(f"Win Rate: {win_rate:.2f}%")
    else:
        print("No completed trades simulated in this dataset window.")

if __name__ == "__main__":
    run_backtest("data/gold_data.csv")
