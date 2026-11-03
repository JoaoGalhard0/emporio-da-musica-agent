# Discovery

Findings in the data and policies. Updated throughout the project.

## Pitfalls identified so far (policies manual v2.1)
- **Two phone numbers:** (67) 3341-4444 (cover and company data table) vs (67) 3321-4500 (section 7,
  WhatsApp). Choice and rationale: to be defined.
- **Email** appears as both `contato@emporiodamusica.com.br` and `contato@empóriodamusica.com.br`.
- **Scope:** the store only sells instruments; accessories (strings, cables, picks, pedals,
  amplifiers, cases) must be politely redirected.
- **PIX (5%)** does not stack with promotional prices (section 6.2); promotional prices must be shown
  next to the original price and the discount percentage.
- **Installments:** minimum installment value varies by range (up to 3x, 4–6x, 7–12x).
- **Returns:** 7-day withdrawal right counted from **delivery** (online purchases); defects within
  30 days; legal warranty of 90 days.
- **Personal data:** order status requires identity verification (LGPD).

## To investigate in the CSVs
- `status` values for products and orders; out-of-stock or discontinued products.
- Promotions with `is_active=0` (expired) vs active.
- Consistency of `total_brl` with `order_items` and prices.
- `specs` field (JSON embedded in CSV) and empty `notes` values.
