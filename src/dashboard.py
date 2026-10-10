
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "challenges" / "cohort-001" / "retail_sales_synthetic.csv"
OUTPUT_DIR = ROOT / "reports"


def build_dashboard():
    df = pd.read_csv(DATA_PATH).drop_duplicates().copy()

    df["order_date"] = pd.to_datetime(
        df["order_date"], errors="coerce"
    )

    for col in ["quantity", "unit_price_ghs", "discount_pct"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(
        subset=["order_date", "quantity", "unit_price_ghs", "discount_pct"]
    )

    df = df[
        (df["quantity"] > 0)
        & (df["unit_price_ghs"] >= 0)
        & (df["discount_pct"].between(0, 100))
    ].copy()

    df["revenue"] = (
        df["quantity"]
        * df["unit_price_ghs"]
        * (1 - df["discount_pct"] / 100)
    )

    df["month"] = df["order_date"].dt.to_period("M").astype(str)

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))

    df.groupby("branch")["revenue"].sum().sort_values().plot(
        kind="barh", ax=axes[0, 0], title="Revenue by Branch"
    )

    df.groupby("product")["revenue"].sum().sort_values(
        ascending=False
    ).head(8).plot(
        kind="bar", ax=axes[0, 1], title="Top 8 Products by Revenue"
    )

    df.groupby("channel")["revenue"].sum().plot(
        kind="bar", ax=axes[1, 0], title="Revenue by Sales Channel"
    )

    df.groupby("month")["revenue"].sum().sort_index().plot(
        kind="line", marker="o",
        ax=axes[1, 1], title="Monthly Revenue"
    )

    for ax in axes.flat:
        ax.set_ylabel("Revenue (GHS)")
        ax.grid(axis="y", alpha=0.25)

    fig.suptitle(
        "BRIDGELAB | RETAIL SALES ANALYTICS",
        fontsize=17,
        fontweight="bold"
    )

    fig.tight_layout(rect=[0, 0, 1, 0.95])

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / "retail_dashboard.png"

    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)

    print(f"Dashboard generated: {output}")


if __name__ == "__main__":
    build_dashboard()
