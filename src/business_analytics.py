
from pathlib import Path
import pandas as pd
from data_processor import load_clean_data

# Project paths
ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "challenges" / "cohort-001" / "retail_sales_synthetic.csv"
REPORT_DIR = ROOT / "reports"
REPORT_PATH = REPORT_DIR / "business_analytics_report.txt"


def run_analysis():
    print("BRIDGELAB BUSINESS ANALYTICS SYSTEM")
    print("=" * 45)

    # Load cleaned data from our shared processor
    df = load_clean_data()

    # Read original data to compare record counts
    original_df = pd.read_csv(DATA_PATH)

    source_records = len(original_df)
    analyzed_records = len(df)
    excluded_records = source_records - analyzed_records

    # Calculate key business metrics
    total_revenue = df["revenue"].sum()
    total_units = df["quantity"].sum()
    unique_orders = df["order_id"].nunique()

    average_order_value = (
        total_revenue / unique_orders
        if unique_orders > 0 else 0
    )

    # Revenue by branch
    revenue_by_branch = (
        df.groupby("branch", dropna=False)["revenue"]
        .sum()
        .sort_values(ascending=False)
    )

    # Revenue by product
    revenue_by_product = (
        df.groupby("product")["revenue"]
        .sum()
        .sort_values(ascending=False)
    )

    # Revenue by category
    revenue_by_category = (
        df.groupby("category")["revenue"]
        .sum()
        .sort_values(ascending=False)
    )

    # Revenue by sales channel
    revenue_by_channel = (
        df.groupby("channel")["revenue"]
        .sum()
        .sort_values(ascending=False)
    )

    # Monthly revenue
    monthly_revenue = (
        df.groupby("month")["revenue"]
        .sum()
        .sort_index()
    )

    # Identify top performers
    top_branch = revenue_by_branch.index[0]
    top_product = revenue_by_product.index[0]
    top_channel = revenue_by_channel.index[0]

    # Build report
    report = [
        "BRIDGELAB - BUSINESS ANALYTICS REPORT",
        "=" * 50,
        "",
        "DATA SUMMARY",
        "-" * 30,
        f"Source records: {source_records}",
        f"Analyzed records: {analyzed_records}",
        f"Excluded records: {excluded_records}",
        "",
        "KEY PERFORMANCE INDICATORS",
        "-" * 30,
        f"Total revenue (GHS): {total_revenue:,.2f}",
        f"Total units sold: {total_units:,.0f}",
        f"Unique orders: {unique_orders}",
        f"Average order value (GHS): {average_order_value:,.2f}",
        "",
        "REVENUE BY BRANCH",
        "-" * 30,
        revenue_by_branch.to_string(),
        "",
        "REVENUE BY PRODUCT",
        "-" * 30,
        revenue_by_product.to_string(),
        "",
        "REVENUE BY CATEGORY",
        "-" * 30,
        revenue_by_category.to_string(),
        "",
        "REVENUE BY SALES CHANNEL",
        "-" * 30,
        revenue_by_channel.to_string(),
        "",
        "MONTHLY REVENUE",
        "-" * 30,
        monthly_revenue.to_string(),
        "",
        "BUSINESS INSIGHTS",
        "-" * 30,
        f"Highest revenue branch: {top_branch}",
        f"Highest revenue product: {top_product}",
        f"Highest revenue sales channel: {top_channel}",
        "",
        "DATA QUALITY NOTES",
        "-" * 30,
        f"{excluded_records} source records were excluded.",
        "Exact duplicate rows were removed.",
        "Records with invalid essential revenue fields were excluded.",
        "Missing branch values remain in overall revenue totals.",
        "",
        "END OF REPORT"
    ]

    # Save report
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    REPORT_PATH.write_text(
        "\n".join(report),
        encoding="utf-8"
    )

    # Display summary in terminal
    print(f"Source records: {source_records}")
    print(f"Analyzed records: {analyzed_records}")
    print(f"Excluded records: {excluded_records}")
    print(f"Total revenue: GHS {total_revenue:,.2f}")
    print(f"Total units sold: {total_units:,.0f}")
    print(f"Unique orders: {unique_orders}")
    print(f"Average order value: GHS {average_order_value:,.2f}")
    print()
    print(f"Top branch: {top_branch}")
    print(f"Top product: {top_product}")
    print(f"Top sales channel: {top_channel}")
    print()
    print(f"Report saved to: {REPORT_PATH}")


if __name__ == "__main__":
    run_analysis()
