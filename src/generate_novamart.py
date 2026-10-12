
from pathlib import Path
import csv
import random
from datetime import date, timedelta

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "challenges" / "novamart_002"
OUT.mkdir(parents=True, exist_ok=True)

rng = random.Random(20261012)

products = [
    ("P01", "Rice 5kg", "Groceries", 85, 59, 200),
    ("P02", "Cooking Oil 2L", "Groceries", 65, 44, 160),
    ("P03", "Laundry Detergent", "Household", 48, 31, 130),
    ("P04", "Toilet Tissue 12-pack", "Household", 72, 47, 110),
    ("P05", "Shampoo", "Personal Care", 40, 25, 100),
    ("P06", "Soap 4-pack", "Personal Care", 28, 16, 155),
    ("P07", "Bottled Water 12-pack", "Groceries", 36, 22, 170),
    ("P08", "Notebook Pack", "Stationery", 30, 18, 80),
]


def write_csv(name, fields, rows):
    with (OUT / name).open(
        "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------
# 1. FICTIONAL CUSTOMER DATA
# ---------------------------------------------

customers = []

for i in range(1, 121):
    customers.append({
        "customer_id": f"C{i:03d}",
        "segment": rng.choice([
            "Student",
            "Family",
            "Professional",
            "Small Business"
        ]),
        "acquisition_channel": rng.choice([
            "Walk-in",
            "Social Media",
            "Referral",
            "Flyer"
        ]),
        "signup_month": rng.choice([
            "2026-01",
            "2026-02",
            "2026-03"
        ]),
    })

write_csv(
    "customers.csv",
    customers[0].keys(),
    customers
)


# ---------------------------------------------
# 2. SALES TRANSACTIONS
# ---------------------------------------------

sales = []

for i in range(1, 601):
    item = rng.choice(products)

    day = (
        date(2026, 1, 1)
        + timedelta(days=rng.randrange(90))
    )

    qty = rng.choices(
        [1, 2, 3, 4],
        weights=[45, 32, 18, 5]
    )[0]

    discount = rng.choice([
        0, 0, 0, 0.05, 0.10
    ])

    price = round(
        item[3] * (1 - discount), 2
    )

    sales.append({
        "sale_id": f"S{i:04d}",
        "date": day.isoformat(),
        "customer_id": rng.choice(
            customers
        )["customer_id"],
        "product_id": item[0],
        "quantity": qty,
        "unit_price_ghs": f"{price:.2f}",
        "unit_cost_ghs": f"{item[4]:.2f}",
        "sales_channel": rng.choice([
            "In Store",
            "WhatsApp Order"
        ]),
    })

write_csv(
    "sales.csv",
    sales[0].keys(),
    sales
)


# ---------------------------------------------
# 3. INVENTORY RECORDS
# ---------------------------------------------

inventory = []

for (
    product_id, name, category,
    price, cost, opening
) in products:

    sold = sum(
        int(row["quantity"])
        for row in sales
        if row["product_id"] == product_id
    )

    received = (
        sold // 2
        + rng.randrange(80, 180)
    )

    closing = opening + received - sold

    inventory.append({
        "product_id": product_id,
        "product_name": name,
        "category": category,
        "opening_units": opening,
        "received_units": received,
        "units_sold": sold,
        "closing_units": closing,
        "reorder_point": rng.randrange(35, 76)
    })

write_csv(
    "inventory.csv",
    inventory[0].keys(),
    inventory
)


# ---------------------------------------------
# 4. BUSINESS OPERATING EXPENSES
# ---------------------------------------------

expenses = []

for month in [
    "2026-01", "2026-02", "2026-03"
]:
    for category, amount in [
        ("Rent", 4200),
        ("Wages", 7000),
        ("Utilities", 1300),
        ("Transport", 900),
        ("Packaging", 450),
        ("Advertising", 700)
    ]:
        variation = rng.randrange(
            -150, 151
        )

        expenses.append({
            "month": month,
            "category": category,
            "amount_ghs": amount + variation
        })

write_csv(
    "operating_expenses.csv",
    expenses[0].keys(),
    expenses
)


# ---------------------------------------------
# 5. MARKETING CAMPAIGN RESULTS
# ---------------------------------------------

campaigns = []

for month in [
    "2026-01", "2026-02", "2026-03"
]:
    for channel in [
        "Social Media",
        "Flyers",
        "Referral Incentives"
    ]:
        campaigns.append({
            "month": month,
            "channel": channel,
            "spend_ghs": rng.randrange(
                170, 420
            ),
            "leads": rng.randrange(
                35, 140
            ),
            "attributed_new_customers":
                rng.randrange(6, 24)
        })

write_csv(
    "campaigns.csv",
    campaigns[0].keys(),
    campaigns
)


# ---------------------------------------------
# 6. CHALLENGE INSTRUCTIONS
# ---------------------------------------------

instructions = """
# BridgeLab — The Retail Revival Challenge

## Client: NovaMart

NovaMart is a fictional retail business in
Kumasi, Ghana.

All supplied data are synthetic and cover
January through March 2026.

Currency: Ghana cedis (GHS).

## Business Problem

NovaMart wants to improve its profitability,
customer retention, and business operations.

Management needs evidence-based recommendations.

Participants must choose ONE specialization.

## Track A — Data & Technology

Analyze sales performance, product margins,
and customer purchasing patterns.

Deliver:
- Data analysis
- At least three charts or useful tables
- Findings and recommendations
- Supporting files

Python, Excel, SQL, or Google Sheets may be used.

Coding is optional.

## Track B — Business & Finance

Investigate revenue, costs, and profitability.

Deliver:
- Revenue and cost analysis
- Financial model or budget
- At least two costed recommendations
- An implementation plan

## Track C — Marketing & Growth

Investigate customer behavior and
marketing campaign performance.

Deliver:
- Customer analysis
- Marketing strategy
- Proposed campaign budget
- Performance measurement plan

## Track D — Operations & Management

Investigate stock management and
operational efficiency.

Deliver:
- Inventory analysis
- Workflow or process map
- Improvement recommendations
- Implementation timeline

## Required Submission

Every participant must submit:

1. A written project report.
2. Supporting files relevant to their track.
3. Evidence supporting their recommendations.
4. A realistic improvement or implementation plan.

GitHub is not required.

## Evaluation — 100 Points

Accuracy and evidence: 30
Problem-solving and recommendations: 30
Feasibility and implementation: 20
Communication: 10
Originality and documentation: 10

## Notes on the Data

Sales revenue equals quantity multiplied
by unit selling price.

Cost of goods sold equals quantity multiplied
by unit cost.

Gross profit equals revenue minus cost of
goods sold.

Operating expenses include advertising.
Do not subtract the marketing campaign
spending again when estimating profit.

Campaign results are illustrative and
do not prove causation.

Customer signups do not necessarily represent
active customers.

All data and participants are fictional.

The pilot is not employment.
Real eligibility, deadline, and prize terms
must be established before public launch.
"""

(OUT / "START_HERE.md").write_text(
    instructions.strip() + "\n",
    encoding="utf-8"
)

print()
print("BRIDGELAB — NOVAMART RESOURCE PACK")
print("=" * 42)

print(f"Created folder: {OUT}")

for path in sorted(OUT.iterdir()):
    print(f"[CREATED] {path.name}")

print()
print("NovaMart challenge materials are ready.")
