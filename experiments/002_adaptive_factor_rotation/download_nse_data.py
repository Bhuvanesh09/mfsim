"""
Download historical NSE index data from niftyindices.com.

The site limits each API call to ~1 year of data, so this script fetches
year-by-year and stitches everything into a single CSV per index.

SETUP (takes ~2 minutes):
  1. Open https://niftyindices.com/reports/historical-data in Chrome/Brave
  2. Open DevTools → Network tab
  3. Trigger any download (select any index, hit Download)
  4. In the Network tab, find the request to `getHistoricaldatatabletoString`
  5. Right-click → Copy → Copy as cURL
  6. Extract the five cookie values from the -b '...' section and paste below

USAGE:
  uv run python experiments/002_adaptive_factor_rotation/download_nse_data.py

OUTPUT:
  experiments/002_adaptive_factor_rotation/nse_data/
    Nifty 50_Historical_PR_<dates>.csv
    Nifty50 Value 20_Historical_PR_<dates>.csv
    NIFTY200MOMENTM30_Historical_PR_<dates>.csv

NOTE: The data is Price Return (PR), not Total Return (TRI). For strategy
comparison the relative conclusions hold — all funds share the same PR base.
Absolute XIRR figures would be ~1-1.5% p.a. higher with TRI data.
"""

import json
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

# ─── PASTE FRESH COOKIES HERE ────────────────────────────────────────────────
# Cookies expire in a few hours. Re-run the DevTools capture if you get 500s.
COOKIES = {
    "ARRAffinity": "7a1f2672fa9934fc15f6b67d3306c3b1844471380c89534f639678cecd833909",
    "ARRAffinitySameSite": "7a1f2672fa9934fc15f6b67d3306c3b1844471380c89534f639678cecd833909",
    "ASP.NET_SessionId": "qo4vc3osvqf0n1zvmur4dgia",
    "ak_bmsc": "1306D4B7BC7C18C862F913EF42BE7B91~000000000000000000000000000000~YAAQNHxBF36rWFOcAQAAvSSimx4kvIPrzOloioIF4O6lQ2MDHIYf6I+sOTELlXOTBPufYNbeu03YMZEoUFH09Dl6lCzCuTOiHo2i1ldXs1XXeJbqIilULAPhZ0L4zuoPfbIxGFCiyYidHSXa4SwvL0eLoTD3CabBwaYIc29s6Li7OsvTqGEm1T5IBYIGWG2V8gcWMAf0QXlOWcRGKoTE2Bx0dLTzRXpzI0Yzysj4IxDKrPH2O7Os4nniPUJ2656armtnCYqV4hMkUNsFQ5sgspK/vpufHi1E4K2wssNk+A+KCMNrba6949TJbNHho0tIJ3K2h7l37efK/QDE4PX4oTlgLdrM/cX7c0jd2c0v3MPC3N8oJB0LeJ5DS5/h/zz60PRanF21Df0cTsx8zE72C+h58Hx7KhwBkfDtKNDZimycOaPiEWE/0mgFBweX9z1WyQBynhyYJkK0tQ==",
    "bm_sv": "583B3B9124CD1755DB959A561A9C45A4~YAAQFjkgF+BF60+cAQAAerOxmx5hvjbvAsOXz1p/gp1uxu2P9EjiSaYeD6ZvvJ4zFZeGRqLX0YRsXGo8zM72HDZz7acRFc9lkoRoDZfO/x/69f9ArKtYITLBlkZ6AhWcm9+iK5QDfyeAjB0vhowRiY9ZaDzuF6yY9FzUKiMG5ji/gmQcUcZ5QTtMypUFAUqm8K8gLIBa7Cu/toQMf8Wg1fXv9I+SzhOcxpt2lfw+MROFnFL9X7cfmp/elwgYdHUsvw6yemRdaw==~1",
}
# ─────────────────────────────────────────────────────────────────────────────

# Indices to download and their earliest available date
INDICES = {
    "Nifty 50": date(2005, 4, 1),         # available from ~1999; align with Momentum 30 base
    "Nifty50 Value 20": date(2010, 1, 1), # earliest available on this API
    "NIFTY200MOMENTM30": date(2005, 4, 1),# NSE backtested data starts 01-Apr-2005
    # Common period for all three: Jan 2010 → Dec 2025 (15 years)
}

END_DATE = date(2025, 12, 31)  # simulation end date

OUT_DIR = Path(__file__).parent / "nse_data"
API_URL = "https://niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString"
HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/json; charset=UTF-8",
    "Origin": "https://niftyindices.com",
    "Referer": "https://niftyindices.com/reports/historical-data",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}


def _fetch_one_year(index_name: str, year: int) -> list[dict]:
    """Fetch one calendar year of data for an index. Returns list of raw records."""
    start = date(year, 1, 1)
    end = min(date(year, 12, 31), END_DATE, date.today())
    if start > end:
        return []

    cinfo = (
        f"{{'name':'{index_name}',"
        f"'startDate':'{start.strftime('%d-%b-%Y')}',"
        f"'endDate':'{end.strftime('%d-%b-%Y')}',"
        f"'indexName':'{index_name}'}}"
    )
    try:
        r = requests.post(
            API_URL, json={"cinfo": cinfo}, headers=HEADERS, cookies=COOKIES, timeout=20
        )
        r.raise_for_status()
        d = r.json().get("d", "[]")
        if d == "[]" or len(d) < 5:
            return []
        return json.loads(d)
    except Exception as e:
        print(f"    WARNING: {year} fetch failed — {e}", file=sys.stderr)
        return []


def _records_to_df(records: list[dict]) -> pd.DataFrame:
    """Convert raw API records to a clean (date, close) DataFrame."""
    rows = [{"date": r["HistoricalDate"], "close": r["CLOSE"]} for r in records]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], format="%d %b %Y", errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.dropna().drop_duplicates("date").sort_values("date").reset_index(drop=True)


def download_index(index_name: str, start_date: date) -> Path | None:
    """Download full history for one index, save to CSV. Returns output path."""
    all_records: list[dict] = []
    start_year = start_date.year
    end_year = min(END_DATE.year, date.today().year)

    for year in range(start_year, end_year + 1):
        print(f"  {year} ...", end=" ", flush=True)
        records = _fetch_one_year(index_name, year)
        if records:
            all_records.extend(records)
            print(f"{len(records)} rows")
        else:
            print("no data")
        time.sleep(0.4)  # polite delay — avoid hammering the server

    if not all_records:
        print(f"  No data retrieved for {index_name!r}")
        return None

    df = _records_to_df(all_records)
    start_str = df["date"].min().strftime("%d%m%Y")
    end_str = df["date"].max().strftime("%d%m%Y")
    fname = f"{index_name}_Historical_PR_{start_str}to{end_str}.csv"
    out_path = OUT_DIR / fname
    df.to_csv(out_path, index=False)
    print(f"  → {out_path.name}  ({len(df)} trading days)")
    return out_path


def _verify_cookies() -> bool:
    """Quick smoke-test: fetch one day to confirm cookies are still valid."""
    cinfo = "{'name':'Nifty 50','startDate':'01-Jan-2025','endDate':'02-Jan-2025','indexName':'Nifty 50'}"
    try:
        r = requests.post(
            API_URL, json={"cinfo": cinfo}, headers=HEADERS, cookies=COOKIES, timeout=10
        )
        d = r.json().get("d", "[]")
        return d != "[]" and len(d) > 5
    except Exception:
        return False


def main():
    OUT_DIR.mkdir(exist_ok=True)

    print("Verifying cookies ...")
    if not _verify_cookies():
        print(
            "\nERROR: cookies are expired or invalid.\n"
            "  1. Open https://niftyindices.com/reports/historical-data in Chrome\n"
            "  2. DevTools → Network → trigger a download\n"
            "  3. Copy the cookie values from the 'getHistoricaldatatabletoString' request\n"
            "  4. Paste into the COOKIES dict at the top of this script\n",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Cookies OK.\n")

    for index_name, start_date in INDICES.items():
        print(f"=== {index_name} (from {start_date}) ===")
        path = download_index(index_name, start_date)
        if path:
            # Quick sanity check
            df = pd.read_csv(path)
            print(
                f"  Sanity: {len(df)} rows | "
                f"first={df['date'].iloc[0]}  close={df['close'].iloc[0]} | "
                f"last={df['date'].iloc[-1]}  close={df['close'].iloc[-1]}"
            )
        print()

    print("All done. Files saved to:", OUT_DIR)
    print("\nNext step: run the experiment with:")
    print("  uv run python experiments/002_adaptive_factor_rotation/run_experiment.py --use-nse")


if __name__ == "__main__":
    main()
