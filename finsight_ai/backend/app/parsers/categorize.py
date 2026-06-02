"""
Shared merchant categorization for all institution parsers.

Maps a free-text transaction description to a canonical TransactionCategory value
(see app.domain.enums.TransactionCategory). Keyword-based and intentionally
generous on groceries/dining/gas since those drive the most common chatbot
queries. Returns "other" when nothing matches.

Centralized here so every parser categorizes consistently — do not re-implement
per parser.
"""

from __future__ import annotations

# Order matters: earlier categories win on ambiguous descriptions.
_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("groceries", [
        "grocery", "groceries", "supermarket", "super food", "foodtown", "food town",
        "whole foods", "trader joe", "safeway", "kroger", "wegmans", "shoprite",
        "stop & shop", "stop and shop", "aldi", "publix", "h mart", "patel brothers",
        "market basket", "fairway", "sprouts", "food bazaar", "key food", "acme",
    ]),
    ("restaurants", [
        "restaurant", "cafe", "coffee", "pizza", "burger", "grill", "kitchen",
        "starbucks", "mcdonald", "chipotle", "dunkin", "doordash", "uber eats",
        "ubereats", "grubhub", "seamless", "taco", "sushi", "diner", "bakery",
        "bar &", "steakhouse", "panera", "wendys", "subway", "chick-fil",
    ]),
    ("gas", [
        "gas", "fuel", "gasoline", "shell", "chevron", "exxon", "exxonmobil",
        "sunoco", "speedway", "wawa", "valero", "citgo", "76 ", "gulf ",
    ]),
    ("travel", [
        "airline", "airlines", "hotel", "motel", "airbnb", "uber", "lyft",
        "delta", "united", "american air", "jetblue", "southwest", "amtrak",
        "expedia", "booking.com", "marriott", "hilton", "hertz", "avis", "transit",
    ]),
    ("subscriptions", [
        "netflix", "spotify", "hulu", "apple.com", "apple music", "google *",
        "youtube", "disney plus", "disneyplus", "disney+", "hbo", "max ",
        "adobe", "microsoft", "dropbox", "icloud", "prime video", "audible",
        "patreon", "membership", "subscription",
    ]),
    ("shopping", [
        "amazon", "target", "walmart", "costco", "best buy", "ebay", "etsy",
        "home depot", "lowes", "ikea", "macy", "nordstrom", "nike", "apple store",
    ]),
    ("utilities", [
        "electric", "water", "gas co", "internet", "comcast", "xfinity",
        "verizon", "t-mobile", "at&t", "spectrum", "con edison", "pseg", "utility",
    ]),
    ("healthcare", [
        "pharmacy", "hospital", "medical", "dental", "cvs", "walgreens",
        "rite aid", "clinic", "doctor", "health",
    ]),
    ("entertainment", [
        "cinema", "movie", "amc ", "regal", "theater", "theatre", "concert",
        "ticketmaster", "stubhub", "steam", "playstation", "xbox", "nintendo",
    ]),
    ("insurance", ["insurance", "geico", "progressive", "allstate", "state farm"]),
]


# Payments, autopay, and statement credits are not "spending" — they should not
# be tagged with a spending category (e.g. "Payment Thank You-Mobile" must not
# become "gas"). These are detected first and short-circuit to "other".
_PAYMENT_HINTS = (
    "payment thank you", "payment - thank you", "thank you", "autopay",
    "online payment", "mobile payment", "electronic payment", "bill payment",
    "statement credit",
)


def _is_payment_or_credit(d: str) -> bool:
    return any(h in d for h in _PAYMENT_HINTS)


def categorize(description: str | None) -> str:
    """Return a canonical category value for a transaction description.

    Payments / autopays / statement credits are intentionally left as "other" so
    they are never counted as spending in a category.
    """
    if not description:
        return "other"
    d = description.lower()
    if _is_payment_or_credit(d):
        return "other"
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(kw in d for kw in keywords):
            return category
    return "other"
