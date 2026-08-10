"""
Financial Plan service — the user's INTENDED allocation of income, kept
separate from actual transactions. Plans are versioned and effective-dated:
get_plan_for_date always resolves to whichever version was in force on a
given date, so historical months are judged against the plan that was
actually active then, not today's plan.

No FastAPI imports here — this module is called by the API layer
(app.api.financial_plan) but is equally usable from any future non-HTTP
caller (e.g. a chat-domain handler), exactly like app.db.repositories.
"""

from __future__ import annotations

from decimal import Decimal

from app.domain.entities import AllocationInput
from app.domain.errors import PlanValidationError

_HUNDRED = Decimal("100")


def validate_plan(allocations: list[AllocationInput]) -> None:
    """Pure validation, no DB access.

    Rules: top-level percentages sum to exactly 100; each bucket's
    suballocation percentages sum to exactly that bucket's own percentage;
    no negative percentages; no duplicate bucket/suballocation names.
    """
    if not allocations:
        raise PlanValidationError("Plan must have at least one allocation bucket.")

    seen_buckets: set[str] = set()
    total = Decimal("0")

    for alloc in allocations:
        key = alloc.bucket_name.strip().lower()
        if key in seen_buckets:
            raise PlanValidationError(f"Duplicate bucket name: {alloc.bucket_name!r}")
        seen_buckets.add(key)

        if alloc.percentage < 0:
            raise PlanValidationError(f"Bucket {alloc.bucket_name!r} has a negative percentage.")

        total += alloc.percentage

        if alloc.suballocations:
            seen_subs: set[str] = set()
            sub_total = Decimal("0")
            for sub in alloc.suballocations:
                sub_key = sub.name.strip().lower()
                if sub_key in seen_subs:
                    raise PlanValidationError(
                        f"Duplicate suballocation name {sub.name!r} under {alloc.bucket_name!r}."
                    )
                seen_subs.add(sub_key)
                if sub.percentage < 0:
                    raise PlanValidationError(
                        f"Suballocation {sub.name!r} has a negative percentage."
                    )
                sub_total += sub.percentage

            if sub_total != alloc.percentage:
                raise PlanValidationError(
                    f"Suballocations under {alloc.bucket_name!r} sum to {sub_total}, "
                    f"expected {alloc.percentage}."
                )

    if total != _HUNDRED:
        raise PlanValidationError(f"Allocations sum to {total}%, expected 100%.")
