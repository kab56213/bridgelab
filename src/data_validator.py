
from pathlib import Path
import pandas as pd

# Find the project root regardless of where the script is run.
ROOT = Path(__file__).resolve().parent.parent

DATA_PATH = ROOT / "challenges" / "cohort-001" / "retail_sales_synthetic.csv"
REPORT_DIR = ROOT / "reports"
REPORT_PATH = REPORT_DIR / "data_quality_report.txt"


def validate_data():
    print("BRIDGELAB DATA VALIDATION SYSTEM")
    print("=" * 40)

    if not DATA_PATH.exists():
        print(f"ERROR: Dataset not found at {DATA_PATH}")
        return

    df = pd.read_csv(DATA_PATH)

    print(f"Dataset loaded: {len(df)} rows, {len(df.columns)} columns")

    # Count missing values
    missing = df.isna().sum()

    # Count fully duplicated rows
    duplicate_count = int(df.duplicated().sum())

    # Find unexpected negative numeric values
    numeric_columns = df.select_dtypes(include="number").columns
    negative_counts = {
        col: int((df[col] < 0).sum())
        for col in numeric_columns
    }

    # Create a report
    lines = [
        "BRIDGELAB - DATA QUALITY REPORT",
        "=" * 40,
        f"Total rows: {len(df)}",
        f"Total columns: {len(df.columns)}",
        f"Duplicate rows: {duplicate_count}",
        "",
        "MISSING VALUES:",
        missing.to_string(),
        "",
        "NEGATIVE NUMERIC VALUES (REVIEW REQUIRED):",
    ]

    for column, count in negative_counts.items():
        lines.append(f"{column}: {count}")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")

    print(f"Validation completed. Report saved to: {REPORT_PATH}")


if __name__ == "__main__":
    validate_data()
