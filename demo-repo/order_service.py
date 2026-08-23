"""Pure order-pricing helpers for the demo application."""

from pricing import calculate_discount


def price_order(
    line_items: list[dict[str, float | int]],
    customer_type: str,
) -> dict[str, object]:
    """Calculate an order total and its deterministic discount breakdown."""
    order_total = round(
        sum(item["unit_price"] * item["quantity"] for item in line_items),
        2,
    )
    item_count = sum(int(item["quantity"]) for item in line_items)
    discount = calculate_discount(order_total, customer_type, item_count)

    return {
        "order_total": order_total,
        "item_count": item_count,
        "customer_type": customer_type,
        "discount": discount,
    }
