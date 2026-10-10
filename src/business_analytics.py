
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "challenges" / "cohort-001" / "retail_sales_synthetic.csv"
REPORT_DIR = ROOT / "reports"


def run_analysis():
    print("BRIDGELAB BUSINESS ANALYTICS SYSTEM")
    print("=" * 45)

    df = pd.read_csv(DATA_PATH)

    # Remove exact duplicate rows
    df = df.drop_duplicates().copy()

    # Convert dates and numeric fields
    df["order_date"] = pd.to_datetime(
        df["order_date"], errors="coerce"
    )

    for column in ["quantity", "unit_price_ghs", "discount_pct"]:
        df[column] = pd.to_numeric(
            df[column], errors="coerce"
        )

    # Exclude records that cannot support reliable revenue calculations
    df = df.dropna(
        subset=["order_date", "quantity", "unit_price_ghs", "discount_pct"]
    )

    # Discount is assumed to be a percentage from 0 to 100
    df = df[
        (df["quantity"] > 0)
        & (df["unit_price_ghs"] >= 0)
        & (df["discount_pct"].between(0, 100))
    ].copy()

    # Calculate net revenue
    df["revenue"] = (
        df["quantity"]
        * df["unit_price_ghs"]
        * (1 - df["discount_pct"] / 100)
    )

    df["month"] = df["order_date"].dt.to_period("M").astype(str)

    revenue_by_branch = (
        df.dropna(subset=["branch"])
        .groupby("branch")["revenue"]
        .sum()
        .sort_values(ascending=False)
    )

    revenue_by_product = (
        df.groupby("product")["revenue"]
        .sum()
        .sort_values(ascending=False)
    )

    revenue_by_channel = (
        df.groupby("channel")["revenue"]
        .sum()
        .sort_values(ascending=False)
    )

    monthly_revenue = (
        df.groupby("month")["revenue"]
        .sum()
        .sort_index()
    )

    report = [
        "BRIDGELAB - BUSINESS ANALYTICS REPORT",
        "=" * 45,
        f"Source records: {len(pd.read_csv(DATA_PATH))}",
        f"Analyzed records: {len(df)}",
        f"Total revenue (GHS): {df['revenue'].sum():,.2f}",
        "",
        "REVENUE BY BRANCH:",
        revenue_by_branch.to_string(),
        "",
        "REVENUE BY PRODUCT:",
        revenue_by_product.to_string(),
        "",
        "REVENUE BY CHANNEL:",
        revenue_by_channel.to_string(),
        "",
        "MONTHLY REVENUE:",
        monthly_revenue.to_string(),
    ]

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    output = REPORT_DIR / "business_analytics_report.txt"
    output.write_text("\n".join(report), encoding="utf-8")

    print(f"Analysis completed: {len(df)} records")
    print(f"Total revenue: GHS {df['revenue'].sum():,.2f}")
    print(f"Report saved to: {output}")


if __name__ == "__main__":
    run_analysis()
