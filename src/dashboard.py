
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd

from data_processor import load_clean_data

# Project paths
ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "reports"
OUTPUT_PATH = OUTPUT_DIR / "retail_dashboard.png"


def build_dashboard():
    print("BRIDGELAB DASHBOARD V2")
    print("=" * 40)

    # Use the same cleaned dataset as business_analytics.py
    df = load_clean_data()

    total_revenue = df["revenue"].sum()
    total_orders = df["order_id"].nunique()
    total_units = df["quantity"].sum()

    average_order = (
        total_revenue / total_orders
        if total_orders else 0
    )

    # Group performance metrics
    branch_revenue = (
        df.groupby("branch", dropna=False)["revenue"]
        .sum()
        .sort_values()
    )

    # Label missing branches instead of excluding their sales
    branch_revenue.index = [
        "Unknown" if pd.isna(name) else str(name)
        for name in branch_revenue.index
    ]

    product_revenue = (
        df.groupby("product")["revenue"]
        .sum()
        .sort_values(ascending=False)
        .head(8)
        .sort_values()
    )

    channel_revenue = (
        df.groupby("channel")["revenue"]
        .sum()
        .sort_values(ascending=False)
    )

    monthly_revenue = (
        df.groupby("month")["revenue"]
        .sum()
        .sort_index()
    )

    # Dashboard layout
    fig = plt.figure(figsize=(16, 11), facecolor="#F4F7FB")

    grid = fig.add_gridspec(
        3, 4,
        height_ratios=[0.65, 2, 2],
        hspace=0.55,
        wspace=0.38,
        left=0.07,
        right=0.96,
        top=0.87,
        bottom=0.08
    )

    fig.suptitle(
        "BRIDGELAB | RETAIL ANALYTICS DASHBOARD",
        fontsize=21,
        fontweight="bold",
        color="#172B4D",
        y=0.97
    )

    fig.text(
        0.5, 0.92,
        "Business Performance Overview | Synthetic Dataset",
        ha="center",
        fontsize=11,
        color="#62748A"
    )

    # KPI cards
    kpis = [
        ("TOTAL REVENUE", f"GHS {total_revenue:,.2f}"),
        ("TOTAL ORDERS", f"{total_orders:,}"),
        ("UNITS SOLD", f"{total_units:,.0f}"),
        ("AVG ORDER VALUE", f"GHS {average_order:,.2f}")
    ]

    for i, (label, value) in enumerate(kpis):
        ax = fig.add_subplot(grid[0, i])
        ax.set_facecolor("white")

        for spine in ax.spines.values():
            spine.set_visible(False)

        ax.set_xticks([])
        ax.set_yticks([])

        ax.text(
            0.06, 0.72, label,
            transform=ax.transAxes,
            fontsize=10,
            color="#62748A",
            fontweight="bold"
        )

        ax.text(
            0.06, 0.30, value,
            transform=ax.transAxes,
            fontsize=16,
            color="#172B4D",
            fontweight="bold"
        )

    # Revenue by branch
    ax1 = fig.add_subplot(grid[1, :2])
    ax1.set_facecolor("white")

    branch_revenue.plot(
        kind="barh",
        ax=ax1,
        color="#2563EB"
    )

    ax1.set_title("Revenue by Branch", fontweight="bold", pad=15)
    ax1.set_xlabel("Revenue (GHS)")
    ax1.set_ylabel("")

    # Top products
    ax2 = fig.add_subplot(grid[1, 2:])
    ax2.set_facecolor("white")

    product_revenue.plot(
        kind="barh",
        ax=ax2,
        color="#0D9488"
    )

    ax2.set_title("Top 8 Products by Revenue",
                  fontweight="bold", pad=15)
    ax2.set_xlabel("Revenue (GHS)")
    ax2.set_ylabel("")

    # Revenue by channel
    ax3 = fig.add_subplot(grid[2, :2])
    ax3.set_facecolor("white")

    channel_revenue.plot(
        kind="bar",
        ax=ax3,
        color="#7C3AED"
    )

    ax3.set_title("Revenue by Sales Channel",
                  fontweight="bold", pad=15)
    ax3.set_xlabel("")
    ax3.set_ylabel("Revenue (GHS)")
    ax3.tick_params(axis="x", rotation=0)

    # Monthly revenue
    ax4 = fig.add_subplot(grid[2, 2:])
    ax4.set_facecolor("white")

    monthly_revenue.plot(
        kind="line",
        marker="o",
        linewidth=2.5,
        markersize=7,
        ax=ax4,
        color="#EA580C"
    )

    ax4.set_title("Monthly Revenue Trend",
                  fontweight="bold", pad=15)
    ax4.set_xlabel("Month")
    ax4.set_ylabel("Revenue (GHS)")
    ax4.tick_params(axis="x", rotation=0)

    # General chart formatting
    for ax in [ax1, ax2, ax3, ax4]:
        ax.grid(axis="y", alpha=0.15)
        ax.set_axisbelow(True)

        for spine in ax.spines.values():
            spine.set_visible(False)

        ax.tick_params(labelsize=9)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fig.savefig(
        OUTPUT_PATH,
        dpi=180,
        bbox_inches="tight",
        facecolor=fig.get_facecolor()
    )

    plt.close(fig)

    print(f"Records analyzed: {len(df)}")
    print(f"Total revenue: GHS {total_revenue:,.2f}")
    print(f"Dashboard saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    build_dashboard()
