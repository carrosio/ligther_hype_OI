import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

# --- Configuration ---
CSV_FILE = Path("defi_oi_data.csv")
st.set_page_config(layout="wide", page_title="DeFi OI Ratio Monitor")

def load_data(file_path):
    """Loads the CSV data and converts the Timestamp column to datetime."""
    if not file_path.exists():
        st.error(f"Error: CSV file not found at {file_path}. Please run the scraper first.")
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(file_path)
        # Convert Timestamp to a proper datetime object
        df['Timestamp (UTC)'] = pd.to_datetime(df['Timestamp (UTC)'])
        return df
    except pd.errors.EmptyDataError:
        st.warning("CSV file is empty. Waiting for scraper data...")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error reading or processing CSV: {e}")
        return pd.DataFrame()

def calculate_ratio(df):
    """
    Calculates the aggregate OI for each platform and then the Lighter/Hyperliquid Ratio.
    """
    if df.empty:
        return pd.DataFrame()

    # 1. Pivot the data to get Platform as columns
    pivot_df = df.pivot_table(
        index='Timestamp (UTC)',
        columns=['Platform', 'Asset'],
        values='Open Interest (Millions USD)'
    )
    
    # Fill any missing values (due to scrape errors) with 0.0 for calculation
    pivot_df = pivot_df.fillna(0.0)

    # 2. Calculate the Sum of OI for Lighter (BTC + ETH) and Hyperliquid (BTC + ETH)
    lighter_cols = [(p, a) for p, a in pivot_df.columns if p == 'Lighter']
    hyperliquid_cols = [(p, a) for p, a in pivot_df.columns if p == 'Hyperliquid']
    
    # Handle cases where one asset might be missing from the scrape (e.g., column not created)
    lighter_oi_sum = pivot_df[lighter_cols].sum(axis=1) if lighter_cols else 0
    hyperliquid_oi_sum = pivot_df[hyperliquid_cols].sum(axis=1) if hyperliquid_cols else 0
    
    # 3. Create the final ratio DataFrame
    ratio_df = pd.DataFrame({
        'Timestamp (UTC)': pivot_df.index,
        'Lighter OI Sum (M)': lighter_oi_sum,
        'Hyperliquid OI Sum (M)': hyperliquid_oi_sum,
    }).reset_index(drop=True)
    
    # Calculate Ratio: Lighter / Hyperliquid
    ratio_df['Lighter/Hyperliquid OI Ratio'] = ratio_df.apply(
        lambda row: row['Lighter OI Sum (M)'] / row['Hyperliquid OI Sum (M)'] 
                    if row['Hyperliquid OI Sum (M)'] > 0 else 0.0, axis=1
    )
    
    return ratio_df

def main_app():
    """The main Streamlit application function."""
    st.title("DeFi BTC/ETH Open Interest Ratio Monitor")
    st.markdown("---")
    
    # --- Data Loading and Calculation ---
    data_load_state = st.text('Loading data...')
    df_raw = load_data(CSV_FILE)
    data_load_state.text("Data loaded.")

    if df_raw.empty or len(df_raw) < 4:  # Need at least 1 full cycle (4 rows)
        st.warning("Not enough data to calculate ratios. Ensure the scraper is running and has completed at least one cycle.")
        return
        
    df_ratio = calculate_ratio(df_raw)

    # --- Display Latest Snapshot ---
    st.header("Latest OI Snapshot (Millions USD)")
    
    # Get the last row of the ratio data
    latest_row = df_ratio.iloc[-1]
    
    col1, col2, col3 = st.columns(3)
    
    col1.metric("Lighter (BTC+ETH) OI", f"${latest_row['Lighter OI Sum (M)']:.2f}M")
    col2.metric("Hyperliquid (BTC+ETH) OI", f"${latest_row['Hyperliquid OI Sum (M)']:.2f}M")
    col3.metric("Lighter/Hyperliquid Ratio", f"{latest_row['Lighter/Hyperliquid OI Ratio']:.4f}")
    
    st.markdown("---")
    
    # --- Plotting ---
    st.header("Lighter / Hyperliquid OI Ratio Over Time")
    
    # Ratio Chart
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
    
    # --- Raw Data Sums ---
    st.header("Platform Sums")
    
    # Plotting Sums (for context)
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

    # --- Live Refresh Information ---
    st.caption("Data refreshes every 5 minutes when the scraper updates the CSV file.")
    st.dataframe(df_raw.tail(8).style.format({"Open Interest (Millions USD)": "{:.4f}M"}), use_container_width=True)

if __name__ == "__main__":
    main_app()