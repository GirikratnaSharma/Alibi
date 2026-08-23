"""Checkpoint tests for the deterministic demo pricing function."""

import importlib.util
import unittest
from pathlib import Path


PRICING_PATH = Path(__file__).parents[1] / "demo-repo" / "pricing.py"
SPEC = importlib.util.spec_from_file_location("demo_pricing", PRICING_PATH)
assert SPEC is not None and SPEC.loader is not None
PRICING = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PRICING)


class CalculateDiscountTests(unittest.TestCase):
    def test_hand_computed_examples(self) -> None:
        cases = [
            (
                (80.00, "regular", 2),
                {
                    "discount_rate": 0.0,
                    "discount_amount": 0.0,
                    "final_total": 80.0,
                },
            ),
            (
                (120.00, "member", 3),
                {
                    "discount_rate": 0.1,
                    "discount_amount": 12.0,
                    "final_total": 108.0,
                },
            ),
            (
                (200.00, "vip", 5),
                {
                    "discount_rate": 0.2,
                    "discount_amount": 40.0,
                    "final_total": 160.0,
                },
            ),
            (
                (150.00, "member", 12),
                {
                    "discount_rate": 0.15,
                    "discount_amount": 22.5,
                    "final_total": 127.5,
                },
            ),
        ]

        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                self.assertEqual(
                    PRICING.calculate_discount(*arguments), expected
                )

    def test_vip_order_discount_boundary_and_cap(self) -> None:
        self.assertEqual(
            PRICING.calculate_discount(100.00, "vip", 1),
            {
                "discount_rate": 0.15,
                "discount_amount": 15.0,
                "final_total": 85.0,
            },
        )
        self.assertEqual(
            PRICING.calculate_discount(101.00, "vip", 10),
            {
                "discount_rate": 0.2,
                "discount_amount": 20.2,
                "final_total": 80.8,
            },
        )

    def test_same_input_always_returns_same_output(self) -> None:
        arguments = (150.00, "member", 12)
        first = PRICING.calculate_discount(*arguments)

        for _ in range(10):
            self.assertEqual(PRICING.calculate_discount(*arguments), first)


if __name__ == "__main__":
    unittest.main()
