# Discovery

Findings in the policies manual (v2.1) and the CSVs. Every finding ends with the **handling** the
agent or the data layer will apply. IDs (`P#`, `D#`) are referenced from `requirements.md`/`plan.md`.

## A. Policies manual

| ID | Finding | Handling |
|----|---------|----------|
| P1 | **Two phone numbers:** (67) 3341-4444 (cover, header, company table "Telefone / WhatsApp") vs (67) 3321-4500 (section 7, WhatsApp). | Use 3341-4444 (appears 3x, incl. the official company table). Flag in README as an assumption the store should confirm. |
| P2 | **Email** written both as `emporiodamusica.com.br` and `empóriodamusica.com.br`. | Use the ASCII domain (cover version). Same README note. |
| P3 | **Installment rules conflict:** table says credit up to 12x with R$ 100 minimum; section 3.1 says 4–6x needs R$ 80, up to 3x has no minimum (except below R$ 50). | Section 3.1 is the specific rule, so it wins. Computed by code, not by the LLM. Documented. |
| P4 | **Defect window conflict:** 4.2 says exchange within 30 days of *purchase* then manufacturer; 8.1 says legal warranty of 90 days from *receipt*. | Agent states both: exchange in store ≤30 days; between 31–90 days it is a legal-warranty claim, handed to a human. Documented. |
| P5 | **Catalog claim vs data:** manual says 300+ items incl. woodwinds, brass and orchestral strings; the CSV has 65 products and **0** in categories 6, 7, 8. | Agent only claims what the catalog tool returns. Never promises those categories. |
| P6 | **Scope:** instruments only; accessories (strings, picks, cables, cases, pedals, amps) are redirected politely, suggesting partner stores when possible (no partner list exists). | System prompt rule + eval cases. Do not invent partner store names. |
| P7 | **PIX 5%** applies to list price only and **never** on promotional prices (6.2). Promotions are not cumulative. Promo prices must show the original price and the discount %. | Pricing function in code returns `list`, `promo`, `pix` and the reason. |
| P8 | **Freight:** free **above** R$ 500, else flat R$ 35 (metro area of Campo Grande); other cities use Correios/Jadlog with CEP-based quote that we cannot compute. Exactly R$ 500.00 pays the fee. | Compute metro rule in code; for other cities give deadlines per carrier and say the exact price needs the CEP. No invented prices. |
| P9 | **Withdrawal right (7 days)** applies to *online* purchases and counts from **receipt**. Defect: 30 days. Preference exchange: 7 days, subject to stock. Non-eligible: custom setups, "final sale" items, wind mouthpieces. | `check_return_eligibility` tool does the date math and returns the applicable rule and reasons. |
| P10 | **Complaints:** listen, register, forward; human callback within 24 business hours. Doubts about policy application → consult management. | `escalate_to_human` tool writes a ticket log; agent never decides exceptions. |
| P11 | **Opening hours:** Mon–Fri 09–18, Sat 09–13, closed Sun/holidays. Outside hours the assistant must say when the store returns. No holiday calendar is provided. | Time-aware tool using America/Campo_Grande; holidays listed as known limitation. |
| P12 | **Manual is internal** ("restricted use"). | Agent paraphrases rules for customers and does not dump internal procedure text. |
| P13 | **Tone:** informal but professional, "like a friend who knows music"; greet by name if known; never state price/stock/deadline without consulting the system (7.1). | Persona prompt + hard rule enforced by tool-first design and evals. |

## B. Data (CSV)

| ID | Finding | Handling |
|----|---------|----------|
| D1 | 65 products: 62 `active`, 2 `discontinued` (113, 136), 1 `coming_soon` (130). Categories 6, 7, 8 are empty. Row order is not sorted (id 145 sits before 131). | Search filters by status; discontinued/coming soon get the manual's 7.3 wording and alternatives. |
| D2 | Product 96 (Giannini GF-3D) is `active` with `stock_quantity=0`, so "active" does not mean available. | Availability = active **and** stock > 0. Out of stock → suggest alternatives (7.3). |
| D3 | Product 130 (`coming_soon`) is in a **delivered** order (3) and a pending one (14), which is inconsistent. | Report as-is from orders; do not argue with the data. Listed as data-quality note. |
| D4 | Only 4 promotions are active (`is_active=1`): products 127 (10%), 121 (20%), 90 (18%), 94 (8%). 21 are expired. Promotions have **no dates**, only a flag. Products 93, 96, 99 have 2 expired promos each. | Only `is_active=1` counts; expired promos are never offered (7.3). If the customer cites an old promo, say it ended and show the current price. |
| D5 | `total_brl` matches the item sum in 18 of 20 orders. **Order 3** (stored 3450, computed 3498) and **order 20** (1400 vs 1488) differ; cause unknown (possibly a historical price/discount). PIX orders (1, 5) were charged list price, with no 5% discount. | The agent reports the stored order total and never recomputes it. Logged as data-quality note. |
| D6 | Order statuses: `delivered` 7, `shipped` 1, `confirmed` 4, `pending` 4, `cancelled` 4 (reason in `notes`). Tracking code exists only for delivered/shipped; format `BR` + 9 alnum + `BR` matches the manual. | Status answers use status-specific templates (no tracking for confirmed/pending; cancellation reason from `notes`). |
| D7 | Orders have only `estimated_delivery`, no actual delivery date or channel (online vs in store). | Assumption: all orders are online (they have tracking/shipping) and the return window counts from `estimated_delivery` as a proxy for receipt. Documented. |
| D8 | **Reference date:** data runs 2025-10-15 to 2026-03-22; the real "today" is later, so every pending/confirmed order looks stale and every delivery is outside the 7-day window. | Single injectable `today` (env var `STORE_TODAY`, default = real date). Demos use a fixed date so the examples are reproducible. |
| D9 | **Duplicate email:** customers 11 "Bruno Carvalho Martins" and 43 "Bruno Martins" share `bruno.martins@jmail.com`. | Identity check must be tied to the **order**: order id + email *or* phone must match the customer who owns that order. Email alone is never enough. |
| D10 | Customers: 49 rows, 5 cities (Campo Grande 24, Dourados 7, Três Lagoas 7, Corumbá 6, Ponta Porã 6); no empty cells. 25 customers are outside the metro area → other-city shipping rules. | Customer city drives which freight rule applies. |
| D11 | `specs` is JSON inside the CSV (all 65 rows parse). Files are UTF-8 (console "�" was only a terminal artifact). Prices are floats (e.g. 599.9). | Parse specs at load; read files explicitly as UTF-8; money computed with `Decimal`. |
| D12 | Product names carry no consistent aliases ("Takamine GD20" is "Takamine GD20 Dreadnought Natural", id 95, R$ 2,199, stock 5, no active promo). | Name search is case/accents-insensitive, token-based, with disambiguation when several match. |
| D13 | "Violões ≤ R$ 1000" (suggested scenario): category 5 has 35 items, among which price filtering must ignore discontinued/out of stock and show promo prices. | `search_products` returns availability and promo info already computed. |

## C. Open questions (assumed, not asked)
The challenge allows assuming and documenting. Assumptions so far: P1, P2, P3, P4, D7, D8. They go
verbatim into the README "Assumptions" section.
