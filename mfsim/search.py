"""
Fund search utility for mfsim.

Searches the bundled AMFI fund list (mf_list.json) by keyword.

Usage:
    uv run mfsim-search "nifty momentum"
    uv run mfsim-search "nifty 50 index" --top 20
    uv run mfsim-search "value" --direct --growth
    uv run mfsim-search "nippon nifty" --exact "Nippon India Nifty 50 Value 20"
"""

import argparse
import importlib.resources as resourcelib
import json
import sys


def search_funds(query: str, growth_only: bool = False, direct_only: bool = False) -> list[dict]:
    """Search the bundled fund list for funds matching all keywords in *query*.

    Args:
        query: Space-separated search terms (case-insensitive AND search).
        growth_only: If True, only return funds with "GROWTH" in the name.
        direct_only: If True, only return funds with "DIRECT" in the name.

    Returns:
        List of matching fund dicts with ``schemeCode`` and ``schemeName``.
    """
    fund_list_path = str(resourcelib.files("mfsim") / "data" / "mf_list.json")
    with open(fund_list_path) as f:
        funds = json.load(f)

    keywords = query.upper().split()
    results = []
    for fund in funds:
        name = fund["schemeName"].upper()
        if not all(kw in name for kw in keywords):
            continue
        if growth_only and "GROWTH" not in name:
            continue
        if direct_only and "DIRECT" not in name:
            continue
        results.append(fund)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Search Indian mutual funds from the AMFI fund list.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run mfsim-search "nifty momentum"
  uv run mfsim-search "nifty 50 index" --direct --growth --top 10
  uv run mfsim-search "value 20" --direct --growth
        """,
    )
    parser.add_argument("query", nargs="+", help="Search keywords (case-insensitive AND search)")
    parser.add_argument("--top", type=int, default=30, help="Max results to show (default: 30)")
    parser.add_argument(
        "--direct", action="store_true", help="Filter to Direct plans only"
    )
    parser.add_argument(
        "--growth", action="store_true", help="Filter to Growth option only"
    )
    parser.add_argument(
        "--code", action="store_true", help="Show scheme codes alongside names"
    )
    args = parser.parse_args()

    query = " ".join(args.query)
    results = search_funds(query, growth_only=args.growth, direct_only=args.direct)

    if not results:
        print(f"No funds found matching '{query}'")
        sys.exit(1)

    filters = []
    if args.direct:
        filters.append("direct")
    if args.growth:
        filters.append("growth")
    filter_str = f" [{', '.join(filters)}]" if filters else ""

    print(f"\nFound {len(results)} fund(s) matching '{query}'{filter_str}:\n")

    if args.code:
        print(f"{'Code':<10} {'Name'}")
        print("-" * 90)
        for fund in results[: args.top]:
            print(f"{fund['schemeCode']:<10} {fund['schemeName']}")
    else:
        print("\n".join(f"  {fund['schemeName']}" for fund in results[: args.top]))

    if len(results) > args.top:
        print(f"\n... and {len(results) - args.top} more. Use --top N to see more.")


if __name__ == "__main__":
    main()
