
import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from data_processor import load_clean_data


class TestDataProcessor(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.df = load_clean_data()

    def test_dataset_not_empty(self):
        self.assertGreater(len(self.df), 0)

    def test_required_columns_exist(self):
        required = [
            "order_id",
            "order_date",
            "quantity",
            "unit_price_ghs",
            "discount_pct",
            "revenue",
            "month",
        ]

        for column in required:
            with self.subTest(column=column):
                self.assertIn(column, self.df.columns)

    def test_no_missing_revenue(self):
        self.assertFalse(
            self.df["revenue"].isna().any()
        )

    def test_quantity_positive(self):
        self.assertTrue(
            (self.df["quantity"] > 0).all()
        )

    def test_discount_range(self):
        self.assertTrue(
            self.df["discount_pct"].between(0, 100).all()
        )

    def test_revenue_calculation(self):
        expected = (
            self.df["quantity"]
            * self.df["unit_price_ghs"]
            * (1 - self.df["discount_pct"] / 100)
        )

        pd.testing.assert_series_equal(
            self.df["revenue"],
            expected,
            check_names=False
        )

    def test_no_exact_duplicate_rows(self):
        self.assertEqual(
            int(self.df.duplicated().sum()), 0
        )


if __name__ == "__main__":
    unittest.main()
