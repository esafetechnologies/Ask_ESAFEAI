# Sales Insights

Use this skill when a user asks for sales performance, comparisons, trends, or a summary of Sales Orders and Sales Invoices.

## Build the analysis

- Ask for a date range when the user has not specified one. Use the site's company, currency, and timezone context.
- Read only records available to the current user. Prefer submitted Sales Invoices for completed sales; identify draft, cancelled, returned, or unpaid documents separately when relevant.
- Group results by the requested dimension, such as item, customer, salesperson, territory, or month. State the filters and calculation used.
- Keep net sales, taxes, discounts, returns, and outstanding balances distinct. Do not add tax to net sales unless requested.
- Use ERPNext reports or permission-checked records. Do not use raw SQL or infer missing amounts.
- For requested changes to orders or invoices, prepare a normal ERPNext proposal and wait for explicit confirmation.
