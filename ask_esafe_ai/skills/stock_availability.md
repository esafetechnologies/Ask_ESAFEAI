# Stock Availability

Use this skill when a user asks whether an item is in stock, where stock is held, or how much may be available to sell or purchase.

## Check stock

- Confirm the exact item code and the relevant company, warehouse, and date. Ask when several items or warehouses match.
- Read permission-visible Item, Bin, Warehouse, and Stock Ledger data. Prefer current Bin quantities for a quick availability check and use a stock report when the user needs movement history.
- Report actual quantity, reserved quantity, and projected quantity as separate values when available. Never describe projected quantity as physically on hand.
- Include the warehouse and timestamp or as-of date. Do not promise availability across warehouses unless the user asks for a combined total.
- Do not create stock entries, reservations, or transfers without preparing the standard ERPNext proposal and receiving explicit confirmation.
