# PR 07 — Banking Cash-Flow Tree

Redesign Banking around:

"Where did my cash go?"

Use the banking redesign mockup under /docs/design/ as visual north star.

Create <BankingFlowTree />.

Concept:
Income
  -> Checking
      -> Needs
      -> Wants
      -> Savings

Support deeper levels when data exists:
Needs -> Housing/Groceries/Transportation/Insurance
Wants -> Dining/Shopping/Entertainment/Travel
Savings -> Emergency/House/Child

This is a read-only financial visualization, not a graph editor.

Prefer clean SVG/D3/Sankey/custom rendering over an editor-like graph library.

Requirements:
- branch thickness may reflect dollar volume
- semantic colors
- smooth period transitions
- accessible summary
- hover/click details
- clicking master buckets filters detail
- avoid excessive labels
- desktop/tablet friendly
- graceful small-screen fallback

Each primary node should show:
- actual $
- actual %
- target %
- variance

Do not treat internal transfers, credit-card payments, or account-to-account movement as consumer spending.

Use normalized financial-engine output.

Keep Banking title, period selector, and advisor summary.
Remove generic KPI row from dominant position.
Make the flow tree the hero.

Add robust tests for the visualization data adapter.
