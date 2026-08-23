# Ticket 001 — VIP order discount

Update `calculate_discount` so VIP orders with an `order_total` greater than
$100 receive an additional 5 percentage-point discount.

Keep the function signature and returned fields unchanged. The new discount
must stack with the existing item-count discount, remain subject to the
existing 20% cap, and leave all other customer and order behavior unchanged.
