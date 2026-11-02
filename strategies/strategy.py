import pandas as pd
import numpy as np

def run_pattern_strategy(file_path):
    df = pd.read_csv(file_path, header=0)
    
    if len(df) > 0 and df.iloc[0].astype(str).str.contains('GC=F|\\^NDX|Price').any():
        df = df.iloc[1:].reset_index(drop=True)

    df.columns = [str(col).lower() for col in df.columns]
    close_col = [c for c in df.columns if 'close' in c][0]
    high_col = [c for c in df.columns if 'high' in c][0]
    low_col = [c for c in df.columns if 'low' in c][0]
    
    for col in [close_col, high_col, low_col]:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # Dynamic Support & Resistance
    window = 20
    df['dynamic_resistance'] = df[high_col].rolling(window=window).max()
    df['dynamic_support'] = df[low_col].rolling(window=window).min()
    df['fast_sma'] = df[close_col].rolling(window=10).mean()
    df['slow_sma'] = df[close_col].rolling(window=30).mean()

    # Pattern Recognition: Double Top & Double Bottom Identification
    # A Double Top occurs when price tests the resistance level twice within a tight tolerance percentage (e.g. 0.5%)
    df['is_double_top'] = False
    df['is_double_bottom'] = False

    for i in range(window, len(df)):
        recent_highs = df.loc[i-window:i, high_col]
        res_level = df.loc[i, 'dynamic_resistance']
        
        # Check how many times price got close to the resistance level (within 0.3%)
        touches = recent_highs[(recent_highs >= res_level * 0.997) & (recent_highs <= res_level)]
        if len(touches) >= 2 and df.loc[i, close_col] < res_level:
            df.loc[i, 'is_double_top'] = True

        recent_lows = df.loc[i-window:i, low_col]
        sup_level = df.loc[i, 'dynamic_support']
        touches_low = recent_lows[(recent_lows <= sup_level * 1.003) & (recent_lows >= sup_level)]
        if len(touches_low) >= 2 and df.loc[i, close_col] > sup_level:
            df.loc[i, 'is_double_bottom'] = True

    # Signals & Risk Management based on Playbook rules
    df['signal'] = 0
    df['stop_loss'] = np.nan
    df['take_profit'] = np.nan
    
    # Bearish signal on Double Top breakdown below support/neckline
    double_top_signal = df['is_double_top'] & (df[close_col] < df['dynamic_support'].shift(1))
    df.loc[double_top_signal, 'signal'] = -1
    df.loc[double_top_signal, 'stop_loss'] = df['dynamic_resistance']
    risk_short = df['stop_loss'] - df[close_col]
    df.loc[double_top_signal, 'take_profit'] = df[close_col] - (risk_short * 2.0)

    # Bullish signal on Double Bottom breakout above resistance/neckline
    double_bottom_signal = df['is_double_bottom'] & (df[close_col] > df['dynamic_resistance'].shift(1))
    df.loc[double_bottom_signal, 'signal'] = 1
    df.loc[double_bottom_signal, 'stop_loss'] = df['dynamic_support']
    risk_long = df[close_col] - df['stop_loss']
    df.loc[double_bottom_signal, 'take_profit'] = df[close_col] + (risk_long * 2.0)

    date_col = df.columns[0]
    
    print(f"\n--- XAUUSD Pattern Strategy Analysis ({file_path}) ---")
    active_patterns = df[(df['is_double_top']) | (df['is_double_bottom'])]
    print(f"Total Double Top/Bottom Formations Detected: {len(active_patterns)}")
    
    active_trades = df[df['signal'] != 0]
    if len(active_trades) > 0:
        print("\nTriggered Trades from Patterns:")
        print(active_trades[[date_col, close_col, 'signal', 'stop_loss', 'take_profit']].tail(5))
    else:
        print("No active pattern breakout signals triggered in this view range.")

if __name__ == "__main__":
    run_pattern_strategy("data/gold_data.csv")
