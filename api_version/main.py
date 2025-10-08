import time
import datetime
import csv
import requests
from pathlib import Path

SCRAPE_INTERVAL_SECONDS = 5 * 60
CSV_FILE = Path("defi_oi_data.csv")

API_CONFIG = {
    "Hyperliquid": {
        "url": "https://api.hyperliquid.xyz/info",
        "method": "POST",
        "body": {"type": "metaAndAssetCtxs"},
        "pairs": {"BTC": 0, "ETH": 1}
    },
    "Lighter": {
        "url": "https://mainnet.zklighter.elliot.ai/api/v1/exchangestats",
        "method": "GET",
        "pairs": ["BTC", "ETH"]
    }
}

def init_csv_file():
    if not CSV_FILE.exists():
        print(f"Creating new CSV file: {CSV_FILE}")
        with open(CSV_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Timestamp (UTC)', 'Platform', 'Asset', 'Open Interest (Millions USD)'])

def fetch_hyperliquid_oi():
    try:
        response = requests.post(
            API_CONFIG["Hyperliquid"]["url"],
            json=API_CONFIG["Hyperliquid"]["body"],
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        results = {}
        asset_ctxs = data[1] if len(data) > 1 else []

        for pair_name, index in API_CONFIG["Hyperliquid"]["pairs"].items():
            if index < len(asset_ctxs):
                oi_raw = float(asset_ctxs[index].get("openInterest", "0"))
                mark_px = float(asset_ctxs[index].get("markPx", "1"))
                oi_usd = oi_raw * mark_px
                oi_millions = oi_usd / 1_000_000
                results[pair_name] = oi_millions
                print(f"  -> Hyperliquid {pair_name}: ${oi_millions:.2f}M")
            else:
                results[pair_name] = 0.0
                print(f"  -> Hyperliquid {pair_name}: ERROR - index out of range")

        return results
    except Exception as e:
        print(f"  -> ERROR fetching Hyperliquid data: {e}")
        return {pair: 0.0 for pair in API_CONFIG["Hyperliquid"]["pairs"].keys()}

def fetch_lighter_oi():
    try:
        response = requests.get(API_CONFIG["Lighter"]["url"], timeout=30)
        response.raise_for_status()
        data = response.json()

        results = {}
        for pair in API_CONFIG["Lighter"]["pairs"]:
            oi_millions = 0.0

            if isinstance(data, list):
                for market in data:
                    if pair in market.get("symbol", "").upper():
                        oi_raw = float(market.get("openInterest", 0))
                        results[pair] = oi_raw / 1_000_000
                        print(f"  -> Lighter {pair}: ${oi_raw / 1_000_000:.2f}M")
                        break
            elif isinstance(data, dict):
                market_key = f"{pair}-PERP"
                if market_key in data:
                    oi_raw = float(data[market_key].get("openInterest", 0))
                    results[pair] = oi_raw / 1_000_000
                    print(f"  -> Lighter {pair}: ${oi_raw / 1_000_000:.2f}M")

            if pair not in results:
                results[pair] = 0.0
                print(f"  -> Lighter {pair}: No data found")

        return results
    except Exception as e:
        print(f"  -> ERROR fetching Lighter data: {e}")
        return {pair: 0.0 for pair in API_CONFIG["Lighter"]["pairs"]}

def main():
    print("--- DeFi OI Monitor (API Version): Starting 5-Minute Scrape Cycle ---")
    init_csv_file()

    while True:
        try:
            start_time = time.time()
            timestamp_utc = datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S')
            print(f"\n--- Cycle Start: {timestamp_utc} UTC ---")

            cycle_data = []

            print("Fetching Hyperliquid data...")
            hyperliquid_oi = fetch_hyperliquid_oi()
            for pair, oi in hyperliquid_oi.items():
                cycle_data.append([timestamp_utc, "Hyperliquid", pair, oi])

            print("Fetching Lighter data...")
            lighter_oi = fetch_lighter_oi()
            for pair, oi in lighter_oi.items():
                cycle_data.append([timestamp_utc, "Lighter", pair, oi])

            with open(CSV_FILE, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerows(cycle_data)
            print(f"Successfully saved {len(cycle_data)} records to {CSV_FILE}.")

            end_time = time.time()
            elapsed_time = end_time - start_time
            wait_time = max(0, SCRAPE_INTERVAL_SECONDS - elapsed_time)

            next_run_time = datetime.datetime.now() + datetime.timedelta(seconds=wait_time)
            print(f"Cycle completed in {elapsed_time:.2f} seconds.")
            print(f"Waiting {wait_time:.0f} seconds (next run at {next_run_time:%H:%M:%S})...")

            time.sleep(wait_time)

        except KeyboardInterrupt:
            print("\n\nScraper stopped by user (Ctrl+C).")
            break
        except Exception as e:
            print(f"\n\nERROR in main loop: {e}")
            print("Retrying in 30 seconds...")
            time.sleep(30)

if __name__ == "__main__":
    main()
