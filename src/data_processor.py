
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "challenges" / "cohort-001" / "retail_sales_synthetic.csv"


def load_clean_data():
    """Load, clean, and prepare sales data for analysis."""

    df = pd.read_csv(DATA_PATH)

    # Remove exact duplicate records.
    df = df.drop_duplicates().copy()

    # Convert dates.
    df["order_date"] = pd.to_datetime(
        df["order_date"], errors="coerce"
    )

    # Convert numeric fields.
    numeric_columns = [
        "quantity",
        "unit_price_ghs",
        "discount_pct"
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column], errors="coerce"
        )

    # Remove records missing essential revenue fields.
    df = df.dropna(
        subset=["order_date"] + numeric_columns
    )

    # Apply business validation rules.
    df = df[
        (df["quantity"] > 0)
        & (df["unit_price_ghs"] >= 0)
        & (df["discount_pct"].between(0, 100))
    ].copy()

    # Calculate revenue.
    df["revenue"] = (
        df["quantity"]
        * df["unit_price_ghs"]
        * (1 - df["discount_pct"] / 100)
    )

    # Extract reporting month.
    df["month"] = (
        df["order_date"]
        .dt.to_period("M")
        .astype(str)
    )

    return df


if __name__ == "__main__":
    clean_data = load_clean_data()

    print("BRIDGELAB DATA PROCESSOR")
    print("=" * 35)
    print(f"Clean records: {len(clean_data)}")
    print(f"Total revenue: GHS {clean_data['revenue'].sum():,.2f}")
