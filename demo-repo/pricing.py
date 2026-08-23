"""A small deterministic pricing calculator for the Alibi demo."""


def calculate_discount(
    order_total: float, customer_type: str, item_count: int
) -> dict[str, float]:
    """Return the discount and final total for an order.

    Hand-computed examples:
    - calculate_discount(80.00, "regular", 2)
      -> {"discount_rate": 0.0, "discount_amount": 0.0, "final_total": 80.0}
    - calculate_discount(120.00, "member", 3)
      -> {"discount_rate": 0.1, "discount_amount": 12.0, "final_total": 108.0}
    - calculate_discount(200.00, "vip", 5)
      -> {"discount_rate": 0.15, "discount_amount": 30.0, "final_total": 170.0}
    - calculate_discount(150.00, "member", 12)
      -> {"discount_rate": 0.15, "discount_amount": 22.5, "final_total": 127.5}
    """
    discount_rate = {
        "regular": 0.00,
        "member": 0.10,
        "vip": 0.15,
    }.get(customer_type, 0.00)

    if item_count >= 10:
        discount_rate += 0.05

    discount_rate = min(discount_rate, 0.20)
    discount_amount = round(order_total * discount_rate, 2)
    final_total = round(order_total - discount_amount, 2)

    return {
        "discount_rate": discount_rate,
        "discount_amount": discount_amount,
        "final_total": final_total,
    }
