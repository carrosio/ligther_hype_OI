import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path
import numpy as np
import time

# --- Configuration ---
CSV_FILE = Path("defi_oi_data.csv")
AUTO_REFRESH_INTERVAL_SECONDS = 60  # Auto-refresh every 60 seconds (1 minute)

# Set page config and enforce dark mode/black background
st.set_page_config(
    layout="wide", 
    page_title="DeFi OI Ratio Monitor",
    initial_sidebar_state="collapsed"
)

# Custom CSS to ensure a very dark/black background
st.markdown(f"""
<style>
/* Main app background */
.stApp {{
    background-color: #000000;
}}
/* Ensure main content is also dark */
.main .block-container {{
    background-color: #000000;
}}
/* Ensure headers and text are visible */
h1, h2, h3, h4, h5, h6, .st-emotion-cache-1jmveez, .st-emotion-cache-1jmveez p, .st-emotion-cache-116hyea, .st-emotion-cache-p3n0v5 {{
    color: white !important;
}}
/* Set the meta refresh tag */
</style>
<meta http-equiv="refresh" content="{AUTO_REFRESH_INTERVAL_SECONDS}">
""", unsafe_allow_html=True)


# --- Functions ---

def load_data(file_path):
    """Loads the CSV data without caching."""
    if not file_path.exists():
        st.error(f"Error: CSV file not found at {file_path}. Please run the scraper first.")
        return pd.DataFrame()
    
    try:
        # Load directly to ensure fresh data
        df = pd.read_csv(file_path)
        # Type conversion for robustness
        for col in ['Platform', 'Asset']:
            if col in df.columns:
                df[col] = df[col].astype('category')
        df['Timestamp (UTC)'] = pd.to_datetime(df['Timestamp (UTC)'])
        return df
    except Exception as e:
        st.error(f"Error reading or processing CSV: {e}")
        return pd.DataFrame()

def calculate_ratio(df):
    """Calculates the aggregate OI and the Lighter/Hyperliquid Ratio."""
    if df.empty:
        return pd.DataFrame()

    # FIX 1: Add observed=False to silence FutureWarning about category columns
    pivot_df = df.pivot_table(
        index='Timestamp (UTC)',
        columns=['Platform', 'Asset'],
        values='Open Interest (Millions USD)',
        observed=False  # Fix for FutureWarning in pandas pivot_table
    )
    
    # FIX 2: Replace fillna(method='ffill') with .ffill()
    # Also handles the downcasting warning better by using the dedicated method.
    pivot_df = pivot_df.replace(0.0, pd.NA).ffill() 

    lighter_cols = [(p, a) for p, a in pivot_df.columns if p == 'Lighter']
    hyperliquid_cols = [(p, a) for p, a in pivot_df.columns if p == 'Hyperliquid']
    
    lighter_oi_sum = pivot_df[lighter_cols].sum(axis=1) if lighter_cols else pd.Series(0.0, index=pivot_df.index)
    hyperliquid_oi_sum = pivot_df[hyperliquid_cols].sum(axis=1) if hyperliquid_cols else pd.Series(0.0, index=pivot_df.index)
    
    ratio_df = pd.DataFrame({
        'Timestamp (UTC)': pivot_df.index,
        'Lighter OI Sum (M)': lighter_oi_sum,
        'Hyperliquid OI Sum (M)': hyperliquid_oi_sum,
    }).reset_index(drop=True)
    
    ratio_df['Lighter/Hyperliquid OI Ratio'] = ratio_df.apply(
        lambda row: row['Lighter OI Sum (M)'] / row['Hyperliquid OI Sum (M)'] 
                    if row['Hyperliquid OI Sum (M)'] > 0 else np.nan, axis=1
    )
    
    return ratio_df

def calculate_linear_trend(df_ratio):
    """Calculates and projects the Linear Trend (Degree 1)."""
    df_valid_ratio = df_ratio.dropna(subset=['Lighter/Hyperliquid OI Ratio']).copy()
    
    if len(df_valid_ratio) < 2:
        return df_ratio, 0.0, 0.0

    start_time = df_valid_ratio['Timestamp (UTC)'].iloc[0]
    x = (df_valid_ratio['Timestamp (UTC)'] - start_time).dt.total_seconds() / (24 * 3600)
    y = df_valid_ratio['Lighter/Hyperliquid OI Ratio'].values
    
    m_linear, c_linear = np.polyfit(x.values, y, 1) 
    
    df_ratio['Time_Days'] = (df_ratio['Timestamp (UTC)'] - start_time).dt.total_seconds() / (24 * 3600)
    full_x = df_ratio['Time_Days'].values
    
    df_ratio['Linear_Trend'] = m_linear * full_x + c_linear
    
    return df_ratio, m_linear, c_linear

def plot_oi_ratio_and_nominal(df_ratio, m_linear):
    """Generates the Plotly figure with twin axis."""
    fig = go.Figure()
    
    # --- Traces ---
    fig.add_trace(go.Scatter(
        x=df_ratio['Timestamp (UTC)'], y=df_ratio['Lighter/Hyperliquid OI Ratio'],
        name='Actual OI Ratio', mode='lines', line=dict(color='yellow', width=2), yaxis='y1'
    ))
    fig.add_trace(go.Scatter(
        x=df_ratio['Timestamp (UTC)'], y=df_ratio['Linear_Trend'],
        name=f'Linear Trend (Slope: {m_linear:.4f})', mode='lines',
        line=dict(color='deepskyblue', dash='dash', width=2), yaxis='y1'
    ))
    fig.add_trace(go.Scatter(
        x=df_ratio['Timestamp (UTC)'], y=df_ratio['Lighter OI Sum (M)'],
        name='Lighter OI Sum (M)', mode='lines', line=dict(color='green', width=1), yaxis='y2'
    ))
    fig.add_trace(go.Scatter(
        x=df_ratio['Timestamp (UTC)'], y=df_ratio['Hyperliquid OI Sum (M)'],
        name='Hyperliquid OI Sum (M)', mode='lines', line=dict(color='red', width=1), yaxis='y2'
    ))
    
    # --- Layout ---
    fig.update_layout(
        title="OI Ratio, Linear Trend, and Nominal OI Over Time (Twin Axis)",
        template="plotly_dark", height=600, xaxis=dict(title="Timestamp (UTC)"),
        yaxis=dict(title=dict(text="OI Ratio (Primary)", font=dict(color='yellow')),
            tickfont=dict(color='yellow'), side='left', showgrid=False),
        yaxis2=dict(title=dict(text="Total OI (Millions USD) (Secondary)", font=dict(color='grey')),
            tickfont=dict(color='grey'), overlaying='y', side='right', showgrid=False),
        legend=dict(x=0, y=1.1, orientation="h", bgcolor='rgba(0,0,0,0)')
    )
    fig.update_traces(hoverinfo="all", hoverlabel=dict(bgcolor="black"))
    
    # FIX 3: Replace use_container_width=True with width='stretch'
    st.plotly_chart(fig, width='stretch')


def display_projections(df_ratio, m_linear, c_linear):
    """Calculates and displays the projected ratios."""
    st.header("Projected OI Ratio Based on Linear Trend")
    
    projection_days = {"1d": 1, "7d": 7, "30d": 30, "90d": 90, "1y": 365}
    last_time_days = df_ratio['Time_Days'].iloc[-1]
    
    projections = {}
    
    for label, days in projection_days.items():
        projected_time = last_time_days + days
        projected_ratio = m_linear * projected_time + c_linear
        projections[label] = projected_ratio

    col_proj = st.columns(len(projection_days))
    
    for i, (label, ratio) in enumerate(projections.items()):
        col_proj[i].metric(f"Projected Ratio in {label}", f"{ratio:.4f}")
        
# --- Main Application Logic ---

def main_app_website():
    """The main Streamlit application function."""
    st.title("DeFi BTC/ETH Open Interest Ratio Monitor")
    st.markdown("---")
    
    # --- Status and Manual Refresh ---
    current_time = pd.to_datetime('now', utc=True).strftime("%Y-%m-%d %H:%M:%S UTC")
    st.info(f"Data last loaded from CSV at: **{current_time}**. Auto-refresh is set to {AUTO_REFRESH_INTERVAL_SECONDS} seconds.")
    
    if st.button("Manual Refresh Data"):
        # Corrected method for rerunning the script
        st.rerun()

    st.markdown("---")

    # --- Data Loading and Calculation ---
    df_raw = load_data(CSV_FILE)

    if df_raw.empty or len(df_raw) < 4:
        st.warning("Not enough data to run analysis.")
        return
        
    df_ratio = calculate_ratio(df_raw)
    df_ratio, m_linear, c_linear = calculate_linear_trend(df_ratio)

    # --- Display Latest Snapshot ---
    st.header("Latest OI Snapshot (Millions USD)")
    
    latest_row = df_ratio.iloc[-1]
    
    col1, col2, col3 = st.columns(3)
    
    col1.metric("Lighter (BTC+ETH) OI", f"${latest_row['Lighter OI Sum (M)']:.2f}M")
    col2.metric("Hyperliquid (BTC+ETH) OI", f"${latest_row['Hyperliquid OI Sum (M)']:.2f}M")
    col3.metric("Lighter/Hyperliquid Ratio", f"{latest_row['Lighter/Hyperliquid OI Ratio']:.4f}")
    
    st.markdown("---")
    
    # --- Plotting ---
    plot_oi_ratio_and_nominal(df_ratio, m_linear)
    
    st.markdown("---")
    
    # --- Projections ---
    if m_linear != 0.0:
        display_projections(df_ratio, m_linear, c_linear)

    # --- Raw Data for reference ---
    st.markdown("---")
    st.caption("Raw Data (Last 8 Entries)")
    # FIX 4: Replace use_container_width=True with width='stretch'
    st.dataframe(df_raw.tail(8), width='stretch')

if __name__ == "__main__":
    main_app_website()