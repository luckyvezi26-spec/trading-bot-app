import streamlit as st
import json
from PIL import Image
from google import genai
from google.genai import types

# Page Setup
st.set_page_config(page_title="Lizwi's Multi-Timeframe Strategy Engine", layout="wide")

st.title("📈 Multi-Timeframe Chart & Strategy Analyzer")
st.markdown("""
**Active Rules Loaded:**
- **Allowed Symbols:** `XAUUSD` (Gold), `XAGUSD` (Silver), `BTCUSD` (Bitcoin), `ETHUSD` (Ethereum)
- **Risk Management:** $150 Max Daily Loss Limit | Base Lot: 0.05 (Auto-drops to 0.03 on XAUUSD if SL risk > $50)
- **Execution Mode:** Immediate Buy Limit / Sell Limit Setup (Direct Entry, SL, TP1, TP2)
- **Engine:** Powered by Google Gemini (100% Free Vision AI)
""")

st.divider()

# Sidebar for API Key
with st.sidebar:
    st.header("⚙️ API Configuration")
    gemini_api_key = st.text_input("Gemini API Key", type="password")

# Layout
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Multi-Timeframe Inputs & Screenshots")
    symbol = st.selectbox("Select Instrument", ["XAUUSD (Gold)", "XAGUSD (Silver)", "BTCUSD (Bitcoin)", "ETHUSD (Ethereum)"])
    
    st.markdown("#### 📷 Upload Chart Screenshots")
    htf_file = st.file_uploader("Higher Timeframe (HTF) Context [e.g., H1 / H4 Structure & Liquidity]", type=["png", "jpg", "jpeg"])
    ltf_file = st.file_uploader("Lower Timeframe (LTF) Entry Trigger [e.g., M5 / M15 FVG & CHoCH]", type=["png", "jpg", "jpeg"])
    
    notes = st.text_area("Strategy Setup Notes / Prompt (Optional)", placeholder="e.g. HTF swept liquidity zone, looking for M15 FVG retest...")
    
    if htf_file:
        st.image(htf_file, caption="HTF Context Chart", use_container_width=True)
    if ltf_file:
        st.image(ltf_file, caption="LTF Entry Chart", use_container_width=True)

with col2:
    st.subheader("2. Confluence Signal & Execution Output")
    
    if htf_file and ltf_file:
        clean_symbol = symbol.split()[0]
        
        if gemini_api_key:
            try:
                client = genai.Client(api_key=gemini_api_key)
                
                htf_img = Image.open(htf_file)
                ltf_img = Image.open(ltf_file)
                
                prompt = f"""
                You are an elite institutional trader analyzing a multi-timeframe setup for {clean_symbol}.
                You are given an HTF chart (higher timeframe context) and an LTF chart (lower timeframe entry trigger).
                
                Analyze the charts using:
                - Dan's 18 Playbook Patterns
                - 8 Master Register Strategies
                - HTF Liquidity Sweeps, Order Blocks, and FVGs
                
                Rules:
                1. DO NOT force the user to wait for candle closures. Output immediate actionable limit orders (BUY_LIMIT or SELL_LIMIT).
                2. Extract specific price levels directly from the chart axes where possible:
                   - direction: "BUY" or "SELL"
                   - order_type: "BUY_LIMIT" or "SELL_LIMIT"
                   - entry_price: float / exact level for limit order
                   - stop_loss: float / exact stop level
                   - take_profit_1: float / conservative target
                   - take_profit_2: float / extended target
                   - lot_size: 0.05 base lot (if symbol is XAUUSD and stop loss risk exceeds $50, auto-reduce lot size to 0.03)
                   - strategy_matched: Name of matching strategy or pattern
                   - confluence_reasoning: Short explanation of HTF + LTF alignment
                
                Return ONLY a valid JSON object matching this structure:
                {{
                    "symbol": "{clean_symbol}",
                    "direction": "BUY or SELL",
                    "order_type": "BUY_LIMIT or SELL_LIMIT",
                    "entry_price": 0.0,
                    "stop_loss": 0.0,
                    "take_profit_1": 0.0,
                    "take_profit_2": 0.0,
                    "lot_size": 0.05,
                    "status": "READY_TO_EXECUTE",
                    "strategy_matched": "Strategy Name",
                    "confluence_reasoning": "Reasoning..."
                }}
                """
                
                with st.spinner("Gemini is analyzing HTF/LTF Confluence..."):
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=[prompt, htf_img, ltf_img],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json"
                        )
                    )
                    
                    result_json = json.loads(response.text)
                    st.success("✅ Trade Signal Generated!")
                    st.json(result_json)
                    
            except Exception as e:
                st.error(f"Error during Gemini Vision analysis: {str(e)}")
        else:
            st.warning("🔑 Gemini API Key not entered. Showing instant Limit Order format sample:")
            
            lot = 0.03 if clean_symbol == "XAUUSD" else 0.05
            
            simulated_output = {
                "symbol": clean_symbol,
                "direction": "BUY",
                "order_type": "BUY_LIMIT",
                "entry_price": "Extracted from LTF FVG/Liquidity Sweep",
                "stop_loss": "Extracted below swing low",
                "take_profit_1": "Target 1 (1:2 RR)",
                "take_profit_2": "Target 2 (HTF Liquidity Pool)",
                "lot_size": lot,
                "status": "READY_TO_EXECUTE",
                "strategy_matched": "S004 - HTF Sweep + LTF FVG Retest",
                "confluence_reasoning": "HTF liquidity swept into key demand zone. Immediate Buy Limit set at LTF FVG."
            }
            st.json(simulated_output)
    else:
        st.info("Upload both Higher Timeframe (HTF) and Lower Timeframe (LTF) screenshots to generate signals.")