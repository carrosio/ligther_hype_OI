import sys
import time
import datetime
import csv
from pathlib import Path
import re  # <<< Import the regular expression module >>>
from playwright.sync_api import sync_playwright, expect

# --- Configuration ---
SCRAPE_INTERVAL_SECONDS = 5 * 60  # 5 minutes
OI_ELEMENT_TIMEOUT_MS = 60000    # 10 seconds timeout for element to appear
CSV_FILE = Path("defi_oi_data.csv")

# --- Platform-Specific Configurations ---

PLATFORM_CONFIG = {
    "Lighter": {
        "url_base": "https://app.lighter.xyz/trade/",
        # Lighter Fix: Find the button named 'Open Interest $', then the value inside it.
        "oi_locator": lambda page: page.get_by_role("button", name="Open Interest $").locator(".tabular-nums"),
        "pairs": ["BTC", "ETH"]
    },
    "Hyperliquid": {
        "url_base": "https://app.hyperliquid.xyz/trade/",
        # Hyperliquid Selector: Find the container that holds the header stats (OI is always in there)
        "oi_locator": lambda page: page.locator("div")
                                     .filter(has_text="Open Interest")
                                     .filter(has_text="24h Volume")
                                     .first, 
        "pairs": ["BTC", "ETH"]
    }
}


# --- Functions ---

def init_csv_file():
    """Ensures the CSV file exists and writes the header row if it's new."""
    if not CSV_FILE.exists():
        print(f"Creating new CSV file: {CSV_FILE}")
        with open(CSV_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Timestamp (UTC)', 'Platform', 'Asset', 'Open Interest (Millions USD)'])

def format_oi_value(oi_text: str, platform: str) -> tuple[float, str]:
    """
    Cleans the currency text and converts it to a nominal number in millions.
    Returns (OI_MILLIONS, CLEANED_OI_TEXT)
    """
    # 1. Hyperliquid-specific extraction (if we got the whole block of text)
    if platform == "Hyperliquid":
        # Regex to find '$' followed by digits and commas after 'Open Interest'
        # Group 1: The full dollar amount including '$' and ','
        match = re.search(r'Open Interest(\$[\d,]+\.?\d+)', oi_text)
        if match:
            oi_string = match.group(1).strip()
            # Remove '$' and ','
            cleaned_value = oi_string.replace('$', '').replace(',', '')
            try:
                oi_millions = float(cleaned_value) / 1_000_000
                return oi_millions, oi_string
            except ValueError:
                return 0.0, oi_string
        else:
            return 0.0, "ERROR: Value not found by regex."
            
    # 2. Lighter-specific (or fallback if the text is clean)
    else:
        # Check if the text is a percentage (the failure case), and if so, return 0.0
        if '%' in oi_text:
            return 0.0, oi_text
            
        oi_string = oi_text.strip()
        cleaned_value = oi_string.replace('$', '').replace(',', '')
        try:
            oi_millions = float(cleaned_value) / 1_000_000
            return oi_millions, oi_string
        except ValueError:
            return 0.0, oi_text


def scrape_market(platform: str, pair: str, page) -> float:
    """
    Navigates to the platform/pair page and scrapes the OI value.
    """
    config = PLATFORM_CONFIG[platform]
    url = f"{config['url_base']}{pair}"
    
    print(f"  -> Scraping {platform} {pair} from {url}...")
    
    try:
        # 1. Navigate to the page
        page.goto(url, wait_until="domcontentloaded")
        
        # 2. Locate the element and get its text content
        oi_locator = config["oi_locator"](page)
        
        # This will wait up to 10 seconds for the element to be visible and available
        oi_value_text = oi_locator.text_content(timeout=OI_ELEMENT_TIMEOUT_MS)
        
        # 3. Format and return the value
        oi_millions, cleaned_oi_text = format_oi_value(oi_value_text, platform)

        if oi_millions > 0.0:
            print(f"    -> Success: {cleaned_oi_text} ({oi_millions:,.2f}M)")
        else:
            print(f"    -> ERROR: Failed to extract OI from data. Raw text check: {cleaned_oi_text}. Returning 0.0.")

        return oi_millions
        
    except Exception as e:
        print(f"    -> ERROR: Failed to scrape {platform} {pair} OI. (Timeout/Locator Error). Details: {e}")
        return 0.0 # Return 0.0 on failure

def main():
    """Main function to initialize, schedule, and execute the scraping process."""
    
    print("--- DeFi OI Monitor: Starting 5-Minute Scrape Cycle ---")
    init_csv_file()
    
    with sync_playwright() as p:
        # Launch browser once outside the loop
        print("Launching Chromium browser...")
        try:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            while True:
                start_time = time.time()
                # Using datetime.datetime.now(datetime.UTC) to fix the DeprecationWarning
                timestamp_utc = datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S')
                print(f"\n--- Cycle Start: {timestamp_utc} UTC ---")
                
                cycle_data = []

                # --- Loop through all platforms and pairs ---
                for platform, config in PLATFORM_CONFIG.items():
                    for pair in config['pairs']:
                        oi_millions = scrape_market(platform, pair, page)
                        
                        # Store data for batch writing
                        cycle_data.append([timestamp_utc, platform, pair, oi_millions])

                # --- Save to CSV ---
                with open(CSV_FILE, 'a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerows(cycle_data)
                print(f"Successfully saved {len(cycle_data)} records to {CSV_FILE}.")
                
                # --- Wait for the next cycle ---
                end_time = time.time()
                elapsed_time = end_time - start_time
                wait_time = max(0, SCRAPE_INTERVAL_SECONDS - elapsed_time)
                
                next_run_time = datetime.datetime.now() + datetime.timedelta(seconds=wait_time)
                print(f"Cycle completed in {elapsed_time:.2f} seconds.")
                print(f"Waiting {wait_time:.0f} seconds (next run at {next_run_time:%H:%M:%S})...")
                
                time.sleep(wait_time)

        except KeyboardInterrupt:
            print("\n\nScraper stopped by user (Ctrl+C).")
        except Exception as e:
            if "Connection closed while reading from the driver" in str(e):
                 print("\n\nPlaywright Connection closed unexpectedly. Exiting gracefully.")
            else:
                 print(f"\n\nFATAL ERROR: {e}")
        finally:
            if 'browser' in locals() and browser:
                browser.close()
                print("Browser closed.")

if __name__ == "__main__":
    main()