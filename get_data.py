import yfinance as yf
import pandas as pd
tickers = {"Gold": "GC=F", "Nasdaq100": "^NDX"}
print("Downloading historical market data...")
for name, symbol in tickers.items():
    df = yf.download(symbol, period="2y", interval="1d")
    if not df.empty:
        df.to_csv(f"data/{name.lower()}_data.csv")
        print(f"Successfully saved {name} data")
print("Data download complete!")
