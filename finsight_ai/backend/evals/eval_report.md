# Coral Chat Eval Report

**Generated:** 2026-06-13 02:30 UTC
**Cases:** 47  |  **Passed:** 46  |  **Failed:** 1  |  **Avg latency:** 11851.1ms

---

## Results by case

| ID | Tags | Intent | Domain | Route Type | Route Risk | Plan Task | Plan Src | Classifier LLM | Answer Strategy | Answer LLM | ms | Status |
|----|------|--------|--------|------------|------------|-----------|----------|----------------|-----------------|------------|----|--------|
| spend_simple_001 | spending, simple | spending_summary | sql | simple_sql | safe | aggregate_transactions | deterministic | Y | template_only | N | 6019 | PASS |
| spend_simple_002 | spending, simple | spending_summary | sql | simple_sql | safe | aggregate_transactions | deterministic | Y | template_only | N | 7440 | PASS |
| spend_simple_003 | spending, simple | spending_summary | sql | simple_sql | safe | aggregate_transactions | deterministic | Y | template_only | N | 7140 | PASS |
| merchant_001 | merchant, spending | spending_summary | sql | simple_sql | safe | aggregate_transactions | deterministic | Y | template_only | N | 7776 | PASS |
| merchant_002 | merchant, transaction | transaction_search | sql | simple_sql | safe | list_transactions | deterministic | Y | template_only | N | 7614 | PASS |
| merchant_003 | merchant, transaction | transaction_search | sql | simple_sql | safe | list_transactions | deterministic | Y | template_only | N | 6886 | PASS |
| category_001 | category, spending | spending_summary | sql | simple_sql | safe | aggregate_transactions | deterministic | Y | template_only | N | 7136 | PASS |
| category_002 | category, spending | spending_summary | sql | simple_sql | safe | aggregate_transactions | deterministic | Y | template_only | N | 6882 | PASS |
| category_003 | category, spending | spending_summary | sql | simple_sql | safe | aggregate_transactions | deterministic | Y | template_only | N | 7423 | PASS |
| institution_001 | institution, fees | fees_summary | hybrid | hybrid | safe | aggregate_transactions | deterministic | Y | template_only | N | 7437 | PASS |
| institution_002 | institution, transaction | transaction_search | sql | simple_sql | safe | list_transactions | deterministic | Y | template_only | N | 7941 | PASS |
| account_001 | account, spending | spending_summary | sql | simple_sql | safe | aggregate_transactions | deterministic | Y | template_only | N | 10979 | PASS |
| account_002 | account, balance | balance_summary | sql | simple_sql | safe | balance_lookup | deterministic | Y | template_only | N | 26010 | PASS |
| daterange_001 | daterange, spending | spending_summary | sql | simple_sql | safe | aggregate_transactions | deterministic | Y | template_only | N | 14233 | PASS |
| daterange_002 | daterange, transaction | transaction_search | sql | simple_sql | safe | list_transactions | deterministic | Y | template_only | N | 20215 | PASS |
| followup_001 | followup, spending | spending_summary | sql | sql_analysis | needs_llm_planner | list_transactions | llm | Y | template_only | N | 57943 | PASS |
| followup_002 | followup, spending, category | spending_summary | sql | sql_analysis | needs_llm_planner | list_transactions | llm | Y | template_only | N | 27703 | PASS |
| nodata_001 | nodata, fallback | transaction_search | sql | simple_sql | safe | list_transactions | deterministic | Y | template_only | N | 15333 | PASS |
| nodata_002 | nodata, balance | balance_summary | sql | simple_sql | safe | balance_lookup | deterministic | Y | template_only | N | 9447 | PASS |
| comparison_001 | comparison | comparison | sql | sql_analysis | needs_llm_planner | compare_spending | llm | Y | template_only | N | 63792 | PASS |
| comparison_002 | comparison, category | comparison | sql | sql_analysis | needs_llm_planner | compare_spending | llm | Y | template_only | N | 39722 | PASS |
| rag_001 | rag, document | document_lookup | rag | document_search | safe | document_search | deterministic | Y | template_only | N | 5442 | PASS |
| rag_002 | rag, document | document_lookup | rag | document_search | safe | document_search | deterministic | Y | template_only | N | 4973 | PASS |
| ambiguous_001 | ambiguous, clarification | investment_summary | hybrid | hybrid | needs_llm_planner | document_search | llm | Y | template_only | N | 12830 | PASS |
| ambiguous_002 | ambiguous, clarification | account_summary | sql | sql_analysis | needs_llm_planner | list_transactions | llm | Y | template_only | N | 16127 | PASS |
| no_relax_001 | nodata, no_relax, merchant, daterange | spending_summary | sql | simple_sql | safe | aggregate_transactions | deterministic | Y | template_only | N | 5462 | PASS |
| no_relax_002 | nodata, no_relax, merchant, daterange | transaction_search | sql | simple_sql | safe | list_transactions | deterministic | Y | template_only | N | 5327 | PASS |
| no_relax_003 | nodata, no_relax, institution, daterange | transaction_search | sql | simple_sql | safe | list_transactions | deterministic | Y | template_only | N | 6133 | PASS |
| no_relax_004 | nodata, no_relax, merchant, category, daterange | spending_summary | sql | simple_sql | safe | aggregate_transactions | deterministic | Y | template_only | N | 6108 | PASS |
| no_relax_005 | nodata, no_relax, institution, daterange | transaction_search | sql | simple_sql | safe | list_transactions | deterministic | Y | template_only | N | 6231 | PASS |
| no_relax_006 | nodata, no_relax, merchant, daterange | transaction_search | sql | simple_sql | safe | list_transactions | deterministic | Y | template_only | N | 5119 | PASS |
| phase56_template_001 | phase56, template, spending | spending_summary | sql | simple_sql | safe | aggregate_transactions | deterministic | Y | template_only | N | 5130 | PASS |
| phase56_template_002 | phase56, template, balance | balance_summary | sql | simple_sql | safe | balance_lookup | deterministic | Y | template_only | N | 5407 | PASS |
| phase56_template_003 | phase56, template, fees | fees_summary | hybrid | hybrid | safe | aggregate_transactions | deterministic | Y | template_only | N | 5626 | PASS |
| phase56_template_004 | phase56, template, transaction | transaction_search | sql | simple_sql | safe | list_transactions | deterministic | Y | template_only | N | 5006 | PASS |
| phase56_template_005 | phase56, template, investment | investment_summary | sql | hybrid | safe | investment_summary | deterministic | Y | template_only | N | 5712 | PASS |
| phase56_llm_001 | phase56, llm, analysis | comparison | sql | sql_analysis | needs_llm_planner | compare_spending | llm | Y | template_only | N | 25272 | PASS |
| phase56_llm_002 | phase56, llm, comparison | comparison | sql | sql_analysis | needs_llm_planner | compare_spending | llm | Y | template_only | N | 20111 | PASS |
| phase56_nodata_001 | phase56, nodata, template | spending_summary | sql | simple_sql | safe | aggregate_transactions | deterministic | Y | template_only | N | 5055 | PASS |
| retrieval_fee_001 | retrieval, fees, fts, document_search | fees_summary | hybrid | hybrid | safe | aggregate_transactions | deterministic | Y | template_only | N | 5365 | PASS |
| retrieval_fee_002 | retrieval, fees, document_search, semantic | fees_summary | hybrid | hybrid | safe | aggregate_transactions | deterministic | Y | template_only | N | 4801 | PASS |
| retrieval_statement_001 | retrieval, statement, fts, document_search | document_lookup | rag | document_search | safe | document_search | deterministic | Y | template_only | N | 4779 | PASS |
| retrieval_investment_001 | retrieval, investments, document_search, semantic | investment_summary | hybrid | hybrid | safe | investment_summary | deterministic | Y | template_only | N | 5404 | PASS |
| retrieval_semantic_001 | retrieval, fees, semantic, fts | fees_summary | hybrid | hybrid | safe | aggregate_transactions | deterministic | Y | template_only | N | 5690 | PASS |
| retrieval_semantic_002 | retrieval, fees, semantic, fts | fees_summary | hybrid | hybrid | safe | aggregate_transactions | deterministic | Y | template_only | N | 5340 | PASS |
| retrieval_doc_evidence_001 | retrieval, document_search, fts, investment_notes | document_lookup | rag | document_search | safe | document_search | deterministic | Y | template_only | N | 4588 | PASS |
| retrieval_hybrid_001 | retrieval, hybrid, spending, document_search | unknown | hybrid | clarification | needs_clarification | clarification | deterministic | Y | llm_narrative | Y | 4895 | **FAIL** |

---

## Failure details

### `retrieval_hybrid_001`

**Question:** How much did I spend on my Chase Sapphire card and what does my statement show?

**Expected:** intent=spending_summary | account_summary  domain=sql | hybrid  route_type=simple_sql | hybrid  route_risk=safe | needs_llm_planner  plan_task_type=—  answer_strategy=—
**Actual:**   intent=unknown  domain=hybrid  route_type=clarification  route_risk=needs_clarification  llm_called=True
**Plan:**     task_type=clarification  metric=total_spent  group_by=—  source=deterministic
**Answer:**   strategy=llm_narrative  llm_called=True
**Complexity signals:** document_detail

**Failures:**
- intent: got 'unknown', expected one of ['spending_summary', 'account_summary']
- route_type: got 'clarification', expected one of ['simple_sql', 'hybrid']
- route_risk: got 'needs_clarification', expected one of ['safe', 'needs_llm_planner']

**Answer excerpt:** `I'm not sure what you're asking about. Could you mention an account, institution, category, or time period?`

---

## How to re-run

```bash
# From the backend/ directory:
python evals/run_chat_evals.py

# Filter to a tag or id prefix:
python evals/run_chat_evals.py --filter spending

# Single case:
python evals/run_chat_evals.py --id merchant_001
```

_This file is auto-generated by `evals/run_chat_evals.py`. Do not edit manually._
