"""
Tests for the transaction classification engine and service.

Covers the required cases from docs/coral-redesign/pr-03-classification.md:
  - rent -> Needs/Housing
  - restaurant -> Wants/Dining
  - internal transfer -> Transfer, not spending
  - HYSA transfer can be Savings when appropriate
  - investment contribution -> Investments
  - user override beats model
  - merchant rule beats LLM
  - ambiguous Amazon flagged for review
  - refunds do not inflate spending
  - credit-card payments are not counted again as expenses

Engine tests (`Test*Engine`) are pure/synchronous — no DB, no LLM, no Ollama.
Service tests (`Test*Service`) exercise the DB-backed precedence chain using
the shared `temp_db` fixture.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.transaction_classification import (
    CashFlowType,
    ClassificationResult,
    ClassificationSource,
    MasterBucket,
    MerchantRule,
    RuleScope,
    TransactionClassificationInput,
    UserOverride,
    classify_transaction,
    is_ambiguous_merchant,
)


def _txn(
    description: str,
    *,
    amount: str = "-50.00",
    transaction_type: str = "purchase",
    merchant_name: str | None = None,
    raw_category: str | None = None,
    account_type: str | None = None,
    transaction_id: str = "t1",
) -> TransactionClassificationInput:
    return TransactionClassificationInput(
        transaction_id=transaction_id,
        description=description,
        merchant_name=merchant_name,
        transaction_type=transaction_type,
        amount=Decimal(amount),
        raw_category=raw_category,
        account_type=account_type,
    )


# ── Engine: required pr-03 cases ────────────────────────────────────────────

class TestClassificationEngine:
    def test_rent_is_needs_housing(self):
        result = classify_transaction(_txn("RENT PAYMENT - ACME PROPERTY MGMT", amount="-2000.00"))
        assert result.master_bucket == MasterBucket.NEEDS
        assert result.category == "Housing"
        assert result.cash_flow_type == CashFlowType.EXPENSE
        assert result.needs_review is False

    def test_restaurant_is_wants_dining(self):
        result = classify_transaction(_txn("STARBUCKS STORE #123", amount="-6.25"))
        assert result.master_bucket == MasterBucket.WANTS
        assert result.category == "Dining"
        assert result.cash_flow_type == CashFlowType.EXPENSE

    def test_internal_transfer_is_transfer_not_spending(self):
        result = classify_transaction(
            _txn("ONLINE TRANSFER TO CHK ...1234", amount="-500.00", transaction_type="transfer")
        )
        assert result.cash_flow_type == CashFlowType.TRANSFER
        assert result.master_bucket == MasterBucket.UNCLASSIFIED
        assert result.master_bucket not in (MasterBucket.NEEDS, MasterBucket.WANTS)

    def test_hysa_transfer_is_savings(self):
        result = classify_transaction(
            _txn(
                "ONLINE TRANSFER TO MARCUS HYSA ...9876",
                amount="-1000.00", transaction_type="transfer",
            )
        )
        assert result.cash_flow_type == CashFlowType.SAVINGS_CONTRIBUTION
        assert result.master_bucket == MasterBucket.SAVINGS

    def test_investment_contribution_is_investments(self):
        result = classify_transaction(
            _txn("TRANSFER TO ETRADE BROKERAGE", amount="-800.00", transaction_type="transfer")
        )
        assert result.cash_flow_type == CashFlowType.INVESTMENT_CONTRIBUTION
        assert result.master_bucket == MasterBucket.INVESTMENTS
        assert result.category == "Taxable Brokerage"

    def test_401k_contribution_gets_specific_category(self):
        result = classify_transaction(
            _txn("401K CONTRIBUTION - PAYROLL", amount="-500.00", transaction_type="transfer")
        )
        assert result.master_bucket == MasterBucket.INVESTMENTS
        assert result.category == "401(k)"

    def test_user_override_beats_everything(self):
        override = UserOverride(
            master_bucket=MasterBucket.WANTS, category="Dining",
            cash_flow_type=CashFlowType.EXPENSE,
        )
        merchant_rule = MerchantRule(
            scope=RuleScope.MERCHANT, master_bucket=MasterBucket.NEEDS,
            category="Groceries", cash_flow_type=CashFlowType.EXPENSE,
        )
        result = classify_transaction(
            _txn("RENT PAYMENT", amount="-2000.00"),
            user_override=override,
            merchant_rule=merchant_rule,
        )
        assert result.source == ClassificationSource.USER
        assert result.master_bucket == MasterBucket.WANTS
        assert result.category == "Dining"
        assert result.needs_review is False
        assert result.confidence == 1.0

    def test_merchant_rule_beats_llm(self):
        merchant_rule = MerchantRule(
            scope=RuleScope.MERCHANT, master_bucket=MasterBucket.NEEDS,
            category="Groceries", cash_flow_type=CashFlowType.EXPENSE,
        )
        llm_result = ClassificationResult(
            master_bucket=MasterBucket.WANTS, category="Shopping",
            cash_flow_type=CashFlowType.EXPENSE, source=ClassificationSource.LLM,
            confidence=0.9,
        )
        result = classify_transaction(
            _txn("AMAZON.COM PURCHASE", amount="-40.00"),
            merchant_rule=merchant_rule,
            llm_result=llm_result,
        )
        assert result.source == ClassificationSource.USER
        assert result.master_bucket == MasterBucket.NEEDS
        assert result.category == "Groceries"

    def test_ambiguous_amazon_flagged_for_review(self):
        result = classify_transaction(_txn("AMAZON.COM*A1B2C3", amount="-40.00"))
        assert result.needs_review is True
        assert result.master_bucket == MasterBucket.UNCLASSIFIED
        assert result.confidence < 0.5

    @pytest.mark.parametrize("merchant", ["Amazon", "Target", "Walmart", "Costco", "CVS"])
    def test_all_known_ambiguous_merchants_flagged(self, merchant):
        result = classify_transaction(_txn(f"{merchant.upper()} STORE #4021", amount="-25.00"))
        assert result.needs_review is True
        assert result.master_bucket == MasterBucket.UNCLASSIFIED

    def test_ambiguous_merchant_not_forced_even_with_trusted_category(self):
        # CVS purchases often carry raw_category="healthcare" from the legacy
        # parser categorizer — must still be flagged, not auto-trusted.
        result = classify_transaction(
            _txn("CVS PHARMACY #123", amount="-18.00", raw_category="healthcare")
        )
        assert result.needs_review is True
        assert result.master_bucket == MasterBucket.UNCLASSIFIED

    def test_refund_does_not_inflate_spending(self):
        result = classify_transaction(
            _txn("REFUND - STARBUCKS STORE #123", amount="6.25", transaction_type="refund")
        )
        assert result.cash_flow_type == CashFlowType.REFUND
        assert result.cash_flow_type != CashFlowType.EXPENSE

    def test_positive_amount_spending_category_treated_as_refund(self):
        # No explicit "refund" keyword, but a positive amount landing in a
        # spending category is treated as money coming back, not new spend.
        result = classify_transaction(_txn("STARBUCKS STORE #123", amount="6.25"))
        assert result.cash_flow_type == CashFlowType.REFUND

    def test_credit_card_payment_not_double_counted(self):
        result = classify_transaction(
            _txn("PAYMENT THANK YOU - WEB", amount="500.00", transaction_type="payment")
        )
        assert result.cash_flow_type == CashFlowType.TRANSFER
        assert result.master_bucket == MasterBucket.UNCLASSIFIED

    def test_checking_side_card_payment_also_neutral(self):
        result = classify_transaction(
            _txn(
                "ONLINE PAYMENT TO CHASE CARD ...4455",
                amount="-500.00", transaction_type="withdrawal",
            )
        )
        assert result.cash_flow_type == CashFlowType.TRANSFER
        assert result.master_bucket == MasterBucket.UNCLASSIFIED

    def test_investment_rollover_is_not_new_contribution(self):
        result = classify_transaction(
            _txn("401K ROLLOVER TO IRA", amount="-15000.00", transaction_type="transfer")
        )
        assert result.cash_flow_type == CashFlowType.INVESTMENT_ACTIVITY
        assert result.cash_flow_type != CashFlowType.INVESTMENT_CONTRIBUTION
        assert result.master_bucket == MasterBucket.INVESTMENTS

    def test_dividend_is_investment_activity_not_contribution(self):
        result = classify_transaction(
            _txn("DIVIDEND REINVESTMENT", amount="12.50", transaction_type="dividend")
        )
        assert result.cash_flow_type == CashFlowType.INVESTMENT_ACTIVITY

    def test_credit_card_interest_charge_is_not_investment_activity(self):
        # amex/chase/discover extractors stamp transaction_type="interest" on
        # credit-card INTEREST CHARGE lines — that is a cost of credit, and
        # must never land in the Investments bucket.
        result = classify_transaction(
            _txn("INTEREST CHARGE ON PURCHASES", amount="-24.13",
                 transaction_type="interest", account_type="credit_card")
        )
        assert result.master_bucket == MasterBucket.UNCLASSIFIED
        assert result.cash_flow_type == CashFlowType.OTHER

    def test_investment_account_interest_is_investment_activity(self):
        result = classify_transaction(
            _txn("INTEREST INCOME - BROKERAGE SWEEP", amount="3.10",
                 transaction_type="interest", account_type="individual_brokerage")
        )
        assert result.master_bucket == MasterBucket.INVESTMENTS
        assert result.cash_flow_type == CashFlowType.INVESTMENT_ACTIVITY

    def test_payroll_deposit_is_income_not_needs_or_wants(self):
        result = classify_transaction(
            _txn("ACME CORP PAYROLL DIRECT DEP", amount="3000.00", transaction_type="deposit")
        )
        assert result.cash_flow_type == CashFlowType.INCOME
        assert result.master_bucket == MasterBucket.UNCLASSIFIED

    def test_unresolvable_transaction_is_unclassified_not_guessed(self):
        result = classify_transaction(_txn("MISC POS 99182734", amount="-9.00"))
        assert result.master_bucket == MasterBucket.UNCLASSIFIED
        assert result.needs_review is True
        assert result.source == ClassificationSource.UNKNOWN

    def test_trusted_existing_category_used_when_no_keyword_hit(self):
        # "Whole Paycheck Deli" doesn't hit our own keyword table directly,
        # but the legacy parser already tagged it "groceries".
        result = classify_transaction(
            _txn("WHOLE PAYCHECK DELI #55", amount="-42.10", raw_category="groceries")
        )
        assert result.master_bucket == MasterBucket.NEEDS
        assert result.category == "Groceries"
        assert result.source == ClassificationSource.EXISTING_CATEGORY

    # ── transaction_type="payment" must not swallow real spending ───────────
    # chase/parser.py::_classify_type and bank_of_america/parser.py::_classify_type
    # stamp transaction_type="payment" on ANY description containing the word
    # "payment", so a naive card-payment rule would neutralize rent, utilities,
    # insurance and loan servicing and understate Needs.

    @pytest.mark.parametrize(
        ("description", "category"),
        [
            ("RENT PAYMENT - ACME PROPERTY MGMT", "Housing"),
            ("MORTGAGE PAYMENT WELLS", "Housing"),
            ("PSEG ELECTRIC PAYMENT", "Utilities"),
            ("GEICO INSURANCE PAYMENT", "Insurance"),
            ("STUDENT LOAN PAYMENT NAVIENT", "Minimum Debt"),
        ],
    )
    def test_payment_typed_bill_still_counts_as_needs(self, description, category):
        result = classify_transaction(
            _txn(description, amount="-500.00", transaction_type="payment")
        )
        assert result.master_bucket == MasterBucket.NEEDS
        assert result.category == category
        assert result.cash_flow_type == CashFlowType.EXPENSE

    @pytest.mark.parametrize(
        "description", ["VERIZON WIRELESS AUTOPAY", "COMCAST XFINITY BILL PAYMENT"],
    )
    def test_autopay_utility_bill_is_still_an_expense(self, description):
        result = classify_transaction(
            _txn(description, amount="-95.00", transaction_type="withdrawal")
        )
        assert result.master_bucket == MasterBucket.NEEDS
        assert result.category == "Connectivity"
        assert result.cash_flow_type == CashFlowType.EXPENSE

    def test_credit_card_payment_wording_is_never_needs_spending(self):
        # Even when the parser did not type it as "payment", card-payment
        # wording must stay neutral — otherwise the card purchases (already
        # expensed individually) would be counted a second time.
        result = classify_transaction(
            _txn("CREDIT CARD PAYMENT CHASE 4455", amount="-500.00",
                 transaction_type="withdrawal")
        )
        assert result.cash_flow_type == CashFlowType.TRANSFER
        assert result.master_bucket == MasterBucket.UNCLASSIFIED

    def test_generic_payment_without_spending_evidence_is_neutral(self):
        result = classify_transaction(
            _txn("ONLINE PAYMENT 8823", amount="-500.00", transaction_type="payment")
        )
        assert result.cash_flow_type == CashFlowType.TRANSFER
        assert result.master_bucket == MasterBucket.UNCLASSIFIED

    # ── Direction: withdrawals are not contributions ────────────────────────

    def test_savings_withdrawal_is_not_a_contribution(self):
        result = classify_transaction(
            _txn("TRANSFER FROM MARCUS SAVINGS", amount="1000.00",
                 transaction_type="transfer", account_type="checking")
        )
        assert result.cash_flow_type == CashFlowType.TRANSFER
        assert result.cash_flow_type != CashFlowType.SAVINGS_CONTRIBUTION
        assert result.master_bucket == MasterBucket.UNCLASSIFIED

    def test_brokerage_withdrawal_to_checking_is_not_a_contribution(self):
        result = classify_transaction(
            _txn("TRANSFER FROM ETRADE BROKERAGE", amount="2500.00",
                 transaction_type="transfer", account_type="checking")
        )
        assert result.cash_flow_type == CashFlowType.TRANSFER
        assert result.cash_flow_type != CashFlowType.INVESTMENT_CONTRIBUTION

    def test_outflow_on_the_brokerage_side_is_not_a_contribution(self):
        # Seen from the brokerage statement, a negative amount is money
        # leaving the investment account.
        result = classify_transaction(
            _txn("WITHDRAWAL TO CHASE CHECKING - BROKERAGE", amount="-2500.00",
                 transaction_type="transfer", account_type="individual_brokerage")
        )
        assert result.cash_flow_type == CashFlowType.TRANSFER
        assert result.cash_flow_type != CashFlowType.INVESTMENT_CONTRIBUTION

    def test_inflow_on_the_brokerage_side_is_a_contribution(self):
        result = classify_transaction(
            _txn("CONTRIBUTION FROM CHASE - ROTH IRA", amount="500.00",
                 transaction_type="transfer", account_type="roth_ira")
        )
        assert result.cash_flow_type == CashFlowType.INVESTMENT_CONTRIBUTION
        assert result.master_bucket == MasterBucket.INVESTMENTS
        assert result.category == "Roth IRA"

    # ── Unexplained deposits must not be labelled refunds ───────────────────

    @pytest.mark.parametrize(
        "description", ["DEPOSIT MOBILE CHECK", "ACH CREDIT ACME CORP"],
    )
    def test_unexplained_deposit_is_not_a_refund(self, description):
        result = classify_transaction(
            _txn(description, amount="1500.00", transaction_type="deposit")
        )
        assert result.cash_flow_type == CashFlowType.OTHER
        assert result.cash_flow_type != CashFlowType.REFUND
        assert result.master_bucket == MasterBucket.UNCLASSIFIED
        assert result.needs_review is True

    # ── Inflow on a savings/investment account is contribution evidence by
    #    account type alone (docs/coral-redesign/BLOCKED.md Option C follow-up:
    #    PR03 previously required a keyword match, so realistic destination-
    #    side statement lines like these landed as `other`/`transfer` even
    #    while sitting on an unambiguous savings/investment account) ─────────

    @pytest.mark.parametrize(
        ("description", "account_type"),
        [
            ("CONTRIBUTION", "ira"),
            ("FUNDS RECEIVED", "individual_brokerage"),
            ("ACH DEPOSIT", "individual_brokerage"),
        ],
    )
    def test_investment_inflow_with_no_keyword_is_contribution_by_account_type(
        self, description, account_type,
    ):
        result = classify_transaction(
            _txn(
                description, amount="500.00",
                transaction_type="deposit", account_type=account_type,
            )
        )
        assert result.cash_flow_type == CashFlowType.INVESTMENT_CONTRIBUTION
        assert result.master_bucket == MasterBucket.INVESTMENTS
        assert result.source == ClassificationSource.DETERMINISTIC_RULE
        assert result.needs_review is False

    def test_transfer_in_wording_on_investment_account_is_contribution_by_account_type(self):
        # "TRANSFER IN" contains the generic transfer keyword, which would
        # otherwise short-circuit to a neutral `transfer` (tier 3g) — being ON
        # the investment account itself is stronger evidence.
        result = classify_transaction(
            _txn(
                "TRANSFER IN", amount="500.00",
                transaction_type="transfer", account_type="roth_ira",
            )
        )
        assert result.cash_flow_type == CashFlowType.INVESTMENT_CONTRIBUTION
        assert result.master_bucket == MasterBucket.INVESTMENTS
        # "TRANSFER IN" carries no goal-specific keyword ("roth"/"401k"/etc) —
        # honestly left uncategorized rather than guessed from the account type.
        assert result.category is None

    def test_deposit_from_checking_on_savings_account_is_contribution_by_account_type(self):
        result = classify_transaction(
            _txn(
                "DEPOSIT FROM CHASE CHECKING", amount="1500.00",
                transaction_type="deposit", account_type="savings",
            )
        )
        assert result.cash_flow_type == CashFlowType.SAVINGS_CONTRIBUTION
        assert result.master_bucket == MasterBucket.SAVINGS
        assert result.category is None

    def test_online_transfer_from_chk_wording_on_savings_is_contribution_by_account_type(self):
        result = classify_transaction(
            _txn(
                "ONLINE TRANSFER FROM CHK", amount="1500.00",
                transaction_type="transfer", account_type="savings",
            )
        )
        assert result.cash_flow_type == CashFlowType.SAVINGS_CONTRIBUTION
        assert result.master_bucket == MasterBucket.SAVINGS

    def test_account_type_inflow_rule_does_not_apply_to_outflows(self):
        # Same account type, same lack of keyword, but money is LEAVING the
        # savings account — must never become a contribution.
        result = classify_transaction(
            _txn(
                "MISC WITHDRAWAL", amount="-500.00",
                transaction_type="withdrawal", account_type="savings",
            )
        )
        assert result.cash_flow_type != CashFlowType.SAVINGS_CONTRIBUTION

    def test_account_type_inflow_rule_does_not_override_refund(self):
        # A refund credited back onto a brokerage account is still a refund,
        # not a new contribution.
        result = classify_transaction(
            _txn(
                "REFUND - ADVISORY FEE", amount="25.00", transaction_type="refund",
                account_type="individual_brokerage",
            )
        )
        assert result.cash_flow_type == CashFlowType.REFUND
        assert result.cash_flow_type != CashFlowType.INVESTMENT_CONTRIBUTION

    # ── Pinned known limitations of the tier-3f2 account-type inflow rule ────
    # Both are documented under "Known limitations" in
    # docs/TRANSACTION_CLASSIFICATION.md. They are pinned here so a future
    # change to the rule ordering is a conscious decision, not an accident.

    def test_payroll_deposit_landing_on_a_savings_account_is_currently_a_contribution(self):
        """KNOWN LIMITATION — tier 3f2 is checked before the income rule (3h),
        so a payroll direct deposit that lands straight on a savings account
        reads as `savings_contribution` rather than `income`. It is genuinely
        both, and a single cash_flow_type cannot express both; the consequence
        is that PR 04's Plannable Income denominator omits it. Currently
        unreachable (every savings-typed account is `parseable=False`), but it
        must be decided before a savings parser lands.

        The same wording on a CASH account is unaffected and still `income` —
        that is the path every real statement takes today.
        """
        on_savings = classify_transaction(
            _txn("ACME CORP PAYROLL DIRECT DEP", amount="3000.00",
                 transaction_type="deposit", account_type="savings")
        )
        assert on_savings.cash_flow_type == CashFlowType.SAVINGS_CONTRIBUTION

        on_checking = classify_transaction(
            _txn("ACME CORP PAYROLL DIRECT DEP", amount="3000.00",
                 transaction_type="deposit", account_type="checking")
        )
        assert on_checking.cash_flow_type == CashFlowType.INCOME
        assert on_checking.master_bucket == MasterBucket.UNCLASSIFIED

    def test_investment_to_investment_transfer_in_currently_reads_as_a_contribution(self):
        """KNOWN LIMITATION — a bare `TRANSFER IN` on an investment account is
        `investment_contribution` regardless of whether the money came from
        checking (a real new contribution) or from another investment account
        (a reallocation). The matching outflow stays neutral, so the movement
        is counted once, never twice — but it does read as new investing.
        Explicit rollover wording is still caught earlier by tier 3a.
        """
        inflow = classify_transaction(
            _txn("TRANSFER IN", amount="5000.00",
                 transaction_type="deposit", account_type="individual_brokerage")
        )
        assert inflow.cash_flow_type == CashFlowType.INVESTMENT_CONTRIBUTION

        # The origin side of the same internal move is neutral -> counted once.
        outflow = classify_transaction(
            _txn("TRANSFER OUT", amount="-5000.00",
                 transaction_type="withdrawal", account_type="advisory")
        )
        assert outflow.cash_flow_type == CashFlowType.TRANSFER
        assert outflow.master_bucket == MasterBucket.UNCLASSIFIED

        # Rollovers remain protected by invariant #7 regardless of 3f2.
        rollover = classify_transaction(
            _txn("401K ROLLOVER", amount="15000.00",
                 transaction_type="deposit", account_type="ira")
        )
        assert rollover.cash_flow_type == CashFlowType.INVESTMENT_ACTIVITY

    def test_is_ambiguous_merchant_whole_word_only(self):
        assert is_ambiguous_merchant("amazon.com purchase") is True
        assert is_ambiguous_merchant("costco wholesale #421") is True
        # Should not false-positive on unrelated substrings.
        assert is_ambiguous_merchant("acme walmartian imports") is False
