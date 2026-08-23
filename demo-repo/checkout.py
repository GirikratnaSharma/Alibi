"""Pure checkout presentation helpers for the demo application."""

from pricing import calculate_discount


def build_checkout_summary(
    subtotal: float,
    customer_type: str,
    quantities: list[int],
) -> dict[str, object]:
    """Return the totals shown before an order is submitted."""
    item_count = sum(quantities)
    discount = calculate_discount(subtotal, customer_type, item_count)

    return {
        "subtotal": round(subtotal, 2),
        "item_count": item_count,
        **discount,
    }
