import streamlit as st
import os
import json
import base64
from PIL import Image
from openai import OpenAI

# Page Setup
st.set_page_config(page_title="Lizwi's Multi-Timeframe Strategy Engine", layout="wide")

st.title("📈 Multi-Timeframe Chart & Strategy Analyzer")
st.markdown("""
**Active Rules Loaded:**
* **Allowed Symbols:** `XAUUSD` (Gold), `XAGUSD` (Silver), `BTCUSD` (Bitcoin), `ETHUSD` (Ethereum)
* **Risk Management:** \$150 Max Daily Loss Limit | Base Lot: 0.05 (Auto-drops to 0.03 on XAUUSD if SL risk > \$50)
* **Execution Stack:** Multi-Timeframe HTF/LTF Confluence + Dan's 18 Patterns + Master Register Systems + 10 Golden Rules
""")

st.divider()

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Multi-Timeframe Inputs & Screenshots")
    
    selected_symbol = st.selectbox(
        "Select Instrument", 
        ["XAUUSD (Gold)", "XAGUSD (Silver)", "BTCUSD (Bitcoin)", "ETHUSD (Ethereum)"]
    )
    
    # Dual Image Uploaders for Multi-Timeframe Confluence
    st.markdown("#### 🖼️ Upload Chart Screenshots")
    htf_file = st.file_uploader("Higher Timeframe (HTF) Context [e.g., H1 / H4 Structure & Liquidity]", type=["png", "jpg", "jpeg"], key="htf")
    ltf_file = st.file_uploader("Lower Timeframe (LTF) Entry Trigger [e.g., M5 / M15 FVG & CHoCH]", type=["png", "jpg", "jpeg"], key="ltf")
    
    if htf_file is not None:
        st.image(Image.open(htf_file), caption="HTF Context Chart", use_container_width=True)
    if ltf_file is not None:
        st.image(Image.open(ltf_file), caption="LTF Trigger Chart", use_container_width=True)
        
    user_notes = st.text_area(
        "Strategy Setup Notes / Prompt (Optional)", 
        placeholder="e.g. HTF swept liquidity zone, looking for M15 FVG retest on LTF..."
    )
    
    analyze_btn = st.button("🔍 Run Multi-Timeframe AI Analysis", type="primary", use_container_width=True)

with col2:
    st.subheader("2. Confluence Signal & Execution Output")
    
    if analyze_btn:
        if htf_file is None and ltf_file is None:
            st.error("⚠️ Please upload at least one chart screenshot (HTF or LTF)!")
        else:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                st.warning("🔑 OpenAI API key not detected. Displaying Multi-Timeframe Simulation Fallback...")
                parsed_signal = {
                    "symbol": selected_symbol.split()[0],
                    "status": "WAIT_FOR_CLOSE",
                    "htf_context": "Liquidity sweep identified on higher timeframe.",
                    "ltf_trigger": "Waiting for candle closure on lower timeframe structure.",
                    "strategy_matched": "S004 — HTF Liquidity Sweep + LTF FVG & Dan Playbook Confirmation",
                    "lot_size": 0.03 if "XAUUSD" in selected_symbol else 0.05,
                    "action": "PENDING_CONFLUENCE",
                    "recommendation": "⏳ 10 Golden Rules Check: Do not front-run unclosed candles. Wait for the M15/H1 candle to close before entry."
                }
                st.json(parsed_signal)
            else:
                try:
                    with st.spinner("Analyzing HTF context and LTF triggers against Master Register rules...preparing execution setup..."):
                        client = OpenAI(api_key=api_key)
                        
                        messages_content = [{"type": "text", "text": f"Symbol: {selected_symbol}. Notes: {user_notes}"}]
                        
                        if htf_file:
                            htf_b64 = base64.b64encode(htf_file.getvalue()).decode('utf-8')
                            messages_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{htf_b64}"}})
                        if ltf_file:
                            ltf_b64 = base64.b64encode(ltf_file.getvalue()).decode('utf-8')
                            messages_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{ltf_b64}"}})
                        
                        system_prompt = """
                        You are an expert multi-timeframe quantitative trading engine. You evaluate:
                        1. Higher Timeframe (HTF) charts for key zones, liquidity sweeps, and trend context.
                        2. Lower Timeframe (LTF) charts for exact execution triggers (CHoCH, BOS, FVG, Rejections).
                        3. Dan's 18 Chart Patterns and the 10 Golden Rules (Never front-run unclosed candles; require closed candle confirmation; enforced 1:2 RRR minimum).

                        Evaluate the uploaded charts. If confirmations are missing or candles are open, output status "WAIT".
                        Enforce lot size rules: Standard 0.05 lot, but if XAUUSD risk exceeds $50, output recommended_lot as 0.03.

                        Respond strictly in JSON format:
                        {
                            "symbol": string,
                            "status": "VALID_SIGNAL" or "WAIT",
                            "htf_analysis": string,
                            "ltf_analysis": string,
                            "strategy_matched": string,
                            "action": "BUY_LIMIT" | "SELL_LIMIT" | "BUY_MARKET" | "SELL_MARKET" | "NO_TRADE_WAIT",
                            "entry_price": float or string,
                            "stop_loss": float or string,
                            "take_profit_1": float or string,
                            "recommended_lot": float,
                            "wait_reasoning": string
                        }
                        """
                        
                        response = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": messages_content}
                            ],
                            response_format={"type": "json_object"}
                        )
                        
                        result = json.loads(response.choices[0].message.content)
                        st.success("Multi-Timeframe Analysis Complete!")
                        st.json(result)
                        
                        if result.get("status") == "VALID_SIGNAL":
                            st.button("🚀 Confirm & Send Order to MT5", type="primary")
                        else:
                            st.warning(f"⏳ {result.get('wait_reasoning')}")
                except Exception as e:
                    st.error(f"Error during AI analysis: {str(e)}")