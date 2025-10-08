import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
import subprocess
import threading
import time
import sys

CSV_FILE = Path("defi_oi_data.csv")
st.set_page_config(layout="wide", page_title="DeFi OI Ratio Monitor")

scraper_process = None
scraper_running = False

def load_data(file_path):
    if not file_path.exists():
        st.error(f"Error: CSV file not found at {file_path}. Please run the scraper first.")
        return pd.DataFrame()

    try:
        df = pd.read_csv(file_path)
        df['Timestamp (UTC)'] = pd.to_datetime(df['Timestamp (UTC)'])
        return df
    except pd.errors.EmptyDataError:
        st.warning("CSV file is empty. Waiting for scraper data...")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error reading or processing CSV: {e}")
        return pd.DataFrame()

def calculate_ratio(df):
    if df.empty:
        return pd.DataFrame()

    pivot_df = df.pivot_table(
        index='Timestamp (UTC)',
        columns=['Platform', 'Asset'],
        values='Open Interest (Millions USD)'
    )

    pivot_df = pivot_df.replace(0.0, pd.NA).fillna(method='ffill')

    lighter_cols = [(p, a) for p, a in pivot_df.columns if p == 'Lighter']
    hyperliquid_cols = [(p, a) for p, a in pivot_df.columns if p == 'Hyperliquid']

    lighter_oi_sum = pivot_df[lighter_cols].sum(axis=1) if lighter_cols else 0
    hyperliquid_oi_sum = pivot_df[hyperliquid_cols].sum(axis=1) if hyperliquid_cols else 0

    ratio_df = pd.DataFrame({
        'Timestamp (UTC)': pivot_df.index,
        'Lighter OI Sum (M)': lighter_oi_sum,
        'Hyperliquid OI Sum (M)': hyperliquid_oi_sum,
    }).reset_index(drop=True)

    ratio_df['Lighter/Hyperliquid OI Ratio'] = ratio_df.apply(
        lambda row: row['Lighter OI Sum (M)'] / row['Hyperliquid OI Sum (M)']
                    if row['Hyperliquid OI Sum (M)'] > 0 else 0.0, axis=1
    )

    return ratio_df

def main_app():
    st.title("DeFi BTC/ETH Open Interest Ratio Monitor")

    col_a, col_b = st.columns([3, 1])
    with col_b:
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.rerun()

    st.markdown("---")

    data_load_state = st.text('Loading data...')
    df_raw = load_data(CSV_FILE)
    data_load_state.text("Data loaded.")

    if df_raw.empty or len(df_raw) < 4:
        st.warning("Not enough data to calculate ratios. Ensure the scraper is running and has completed at least one cycle.")
        return

    df_ratio = calculate_ratio(df_raw)

    st.header("Latest OI Snapshot (Millions USD)")

    latest_row = df_ratio.iloc[-1]

    col1, col2, col3 = st.columns(3)

    col1.metric("Lighter (BTC+ETH) OI", f"${latest_row['Lighter OI Sum (M)']:.2f}M")
    col2.metric("Hyperliquid (BTC+ETH) OI", f"${latest_row['Hyperliquid OI Sum (M)']:.2f}M")
    col3.metric("Lighter/Hyperliquid Ratio", f"{latest_row['Lighter/Hyperliquid OI Ratio']:.4f}")

    st.markdown("---")

    st.header("Lighter / Hyperliquid OI Ratio Over Time")

    fig_ratio = px.line(
        df_ratio,
        x='Timestamp (UTC)',
        y='Lighter/Hyperliquid OI Ratio',
        title="Ratio: (Lighter BTC+ETH OI) / (Hyperliquid BTC+ETH OI)",
        template="plotly_dark",
        height=500
    )
    fig_ratio.update_traces(mode='lines+markers', marker=dict(size=5))
    fig_ratio.update_layout(hovermode="x unified")
    st.plotly_chart(fig_ratio, use_container_width=True)

    st.markdown("---")

    st.header("Platform Sums")

    df_melt = df_ratio[['Timestamp (UTC)', 'Lighter OI Sum (M)', 'Hyperliquid OI Sum (M)']].melt(
        id_vars='Timestamp (UTC)', var_name='Platform', value_name='Total OI (M)'
    )

    fig_sums = px.line(
        df_melt,
        x='Timestamp (UTC)',
        y='Total OI (M)',
        color='Platform',
        title="Total BTC+ETH OI by Platform",
        template="plotly_dark",
        height=400
    )
    st.plotly_chart(fig_sums, use_container_width=True)

    st.caption("Data refreshes every 5 minutes when the scraper updates the CSV file.")
    st.dataframe(df_raw.tail(8).style.format({"Open Interest (Millions USD)": "{:.4f}M"}), use_container_width=True)

if __name__ == "__main__":
    main_app()
