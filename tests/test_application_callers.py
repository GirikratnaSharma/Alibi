"""Tests for realistic pure callers in the demo application."""

from pathlib import Path
import sys
import unittest


DEMO_REPO = Path(__file__).parents[1] / "demo-repo"
sys.path.insert(0, str(DEMO_REPO))

from checkout import build_checkout_summary  # noqa: E402
from order_service import price_order  # noqa: E402


class ApplicationCallerTests(unittest.TestCase):
    def test_checkout_summary_uses_derived_item_count(self) -> None:
        summary = build_checkout_summary(
            subtotal=200.0,
            customer_type="vip",
            quantities=[2, 1, 2],
        )

        self.assertEqual(
            summary,
            {
                "subtotal": 200.0,
                "item_count": 5,
                "discount_rate": 0.2,
                "discount_amount": 40.0,
                "final_total": 160.0,
            },
        )

    def test_order_service_uses_derived_total_and_item_count(self) -> None:
        priced = price_order(
            line_items=[
                {"unit_price": 30.0, "quantity": 2},
                {"unit_price": 20.0, "quantity": 3},
            ],
            customer_type="member",
        )

        self.assertEqual(
            priced,
            {
                "order_total": 120.0,
                "item_count": 5,
                "customer_type": "member",
                "discount": {
                    "discount_rate": 0.1,
                    "discount_amount": 12.0,
                    "final_total": 108.0,
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
