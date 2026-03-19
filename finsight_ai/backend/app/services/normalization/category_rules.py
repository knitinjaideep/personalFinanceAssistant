"""
Deterministic merchant-to-category rules.

Strategy:
- Rules are applied in priority order; first match wins.
- Each rule is a list of lowercase substrings to search in the cleaned
  merchant name / transaction description.
- LLM fallback is invoked by MerchantNormalizer only when no rule matches
  and the caller opts in (normalize_with_llm_fallback=True).

Adding rules:
- Add entries to _CATEGORY_RULES below.
- Strings are matched as substrings of the lowercased description.
- More specific strings (longer) should appear before generic ones to
  avoid false positives — but order within a category does not matter
  since we stop at the first matching category.
"""

from __future__ import annotations

from app.domain.enums import TransactionCategory

# Priority-ordered list of (category, [substrings]).
# First category with any matching substring wins.
_CATEGORY_RULES: list[tuple[TransactionCategory, list[str]]] = [
    # ── Subscriptions (check before shopping/entertainment) ───────────────────
    (
        TransactionCategory.SUBSCRIPTIONS,
        [
            "netflix", "hulu", "disney+", "disneyplus", "hbo max", "hbomax",
            "paramount+", "peacock", "apple tv", "apple one", "apple music",
            "spotify", "pandora", "tidal", "sirius xm", "siriusxm",
            "amazon prime", "amazon music", "youtube premium", "youtube tv",
            "google one", "google storage", "icloud", "dropbox", "box.com",
            "microsoft 365", "office 365", "adobe", "canva",
            "nytimes", "new york times", "wsj.com", "wall street journal",
            "washington post", "the atlantic", "medium.com",
            "duolingo", "babbel", "audible",
            "linkedin premium", "indeed", "ziprecruiter",
            "planet fitness", "gold's gym", "equinox", "peloton",
            "calm", "headspace", "noom",
            "lastpass", "1password", "nordvpn", "expressvpn",
            "github", "atlassian", "jira", "slack",
            "zoom", "webex", "gotomeeting",
        ],
    ),
    # ── Travel ────────────────────────────────────────────────────────────────
    (
        TransactionCategory.TRAVEL,
        [
            "delta air", "united air", "american airlines", "southwest air",
            "jetblue", "spirit airlines", "frontier airlines", "alaska airlines",
            "lufthansa", "british airways", "air france", "emirates",
            "expedia", "orbitz", "priceline", "kayak", "trivago",
            "booking.com", "airbnb", "vrbo", "hotels.com", "marriott",
            "hilton", "hyatt", "holiday inn", "westin", "sheraton",
            "hertz", "enterprise rent", "avis", "budget rent", "national car",
            "alamo", "dollar rent", "thrifty car",
            "uber", "lyft", "taxi", "cab",
            "amtrak", "greyhound",
            "tsa precheck", "global entry", "clear travel",
            "airport", "lounge", "parking garage",
        ],
    ),
    # ── Groceries ─────────────────────────────────────────────────────────────
    (
        TransactionCategory.GROCERIES,
        [
            "whole foods", "trader joe", "kroger", "safeway", "publix",
            "wegmans", "heb", "h-e-b", "meijer", "stop & shop",
            "stop and shop", "giant food", "food lion", "harris teeter",
            "aldi", "lidl", "costco", "sam's club", "samsclub",
            "bj's wholesale", "target grocery", "walmart grocery",
            "sprouts", "fresh market", "earth fare", "natural grocers",
            "market basket", "price chopper", "shoprite", "hannaford",
            "ralphs", "vons", "albertsons", "stater bros", "winco",
            "smart & final", "grocery outlet",
            "instacart", "shipt", "fresh direct", "amazon fresh",
            "doordash grocery", "gopuff",
        ],
    ),
    # ── Restaurants ───────────────────────────────────────────────────────────
    (
        TransactionCategory.RESTAURANTS,
        [
            "mcdonald", "burger king", "wendy's", "wendys", "chick-fil-a",
            "chickfila", "taco bell", "chipotle", "qdoba", "del taco",
            "subway", "jersey mike", "firehouse subs", "jimmy john",
            "domino's", "dominos", "pizza hut", "papa john", "little caesar",
            "panera", "einstein bagel", "corner bakery",
            "starbucks", "dunkin", "dunkin donuts", "peet's", "tim horton",
            "krispy kreme", "mcdonald's",
            "olive garden", "red lobster", "applebee", "chili's", "chillis",
            "outback steakhouse", "buffalo wild wings", "bww",
            "cheesecake factory", "ihop", "denny's", "waffle house",
            "five guys", "shake shack", "in-n-out", "whataburger",
            "sweetgreen", "cosi", "au bon pain",
            "doordash", "grubhub", "ubereats", "uber eats", "postmates",
            "seamless", "caviar", "delivery",
        ],
    ),
    # ── Gas ───────────────────────────────────────────────────────────────────
    (
        TransactionCategory.GAS,
        [
            "exxon", "mobil", "exxonmobil", "shell", "bp", "chevron",
            "texaco", "sunoco", "citgo", "marathon", "speedway",
            "circle k fuel", "wawa fuel", "kwik trip", "kwiktrip",
            "racetrac", "raceway", "pilot flying j", "flying j",
            "loves travel", "ta travel center", "casey's general",
            "gas station", "fuel", "gasoline",
        ],
    ),
    # ── Utilities ─────────────────────────────────────────────────────────────
    (
        TransactionCategory.UTILITIES,
        [
            "con edison", "conedison", "consolidated edison",
            "pg&e", "pacific gas", "southern california gas", "socal gas",
            "national grid", "dominion energy", "duke energy", "xcel energy",
            "at&t", "verizon", "t-mobile", "tmobile", "sprint", "boost mobile",
            "comcast", "xfinity", "spectrum", "cox", "optimum", "verizon fios",
            "centurylink", "lumen", "frontier comm",
            "directv", "dish network", "sling",
            "water utility", "city water", "sewer", "garbage", "waste management",
            "trash pickup", "republic services",
        ],
    ),
    # ── Healthcare ────────────────────────────────────────────────────────────
    (
        TransactionCategory.HEALTHCARE,
        [
            "cvs pharmacy", "cvs health", "walgreens", "rite aid",
            "pharmacy", "rx", "prescription",
            "hospital", "medical center", "urgent care", "clinic",
            "doctor", "dr.", "physician", "dentist", "dental",
            "optometrist", "eye care", "vision",
            "health insurance", "blue cross", "bluecross", "aetna", "cigna",
            "united health", "humana", "kaiser",
            "lab corp", "quest diagnostics", "labcorp",
            "planned parenthood",
            "mental health", "therapist", "counseling",
        ],
    ),
    # ── Shopping (online and retail) ──────────────────────────────────────────
    (
        TransactionCategory.SHOPPING,
        [
            "amazon", "amazon.com", "amzn",
            "walmart", "target", "costco", "sam's club",
            "best buy", "bestbuy", "apple store", "apple.com/us",
            "home depot", "homedepot", "lowe's", "lowes",
            "bed bath", "crate and barrel", "pottery barn", "west elm",
            "wayfair", "ikea",
            "macy's", "macys", "nordstrom", "bloomingdale",
            "gap", "old navy", "banana republic", "h&m", "zara",
            "uniqlo", "j.crew", "jcrew", "express", "forever 21",
            "tj maxx", "tjmaxx", "marshalls", "ross dress", "burlington coat",
            "nike", "adidas", "under armour", "lululemon",
            "ebay", "etsy", "shopify",
            "chewy", "petco", "petsmart",
            "dollar general", "family dollar", "dollar tree",
        ],
    ),
    # ── Entertainment ─────────────────────────────────────────────────────────
    (
        TransactionCategory.ENTERTAINMENT,
        [
            "amc theatre", "regal cinema", "cinemark", "movie",
            "ticketmaster", "stubhub", "seat geek", "eventbrite",
            "live nation", "concert", "broadway",
            "museum", "zoo", "aquarium", "theme park", "six flags", "disney world",
            "dave & buster", "topgolf", "bowling", "arcade",
            "steam", "playstation", "xbox", "nintendo", "gamestop",
            "twitch", "patreon",
        ],
    ),
    # ── Education ─────────────────────────────────────────────────────────────
    (
        TransactionCategory.EDUCATION,
        [
            "tuition", "university", "college", "community college",
            "coursera", "udemy", "udacity", "skillshare", "masterclass",
            "khan academy", "chegg", "bartleby",
            "textbook", "bookstore", "school supplies",
        ],
    ),
    # ── Insurance ─────────────────────────────────────────────────────────────
    (
        TransactionCategory.INSURANCE,
        [
            "state farm", "allstate", "progressive", "geico", "usaa",
            "farmers insurance", "liberty mutual", "travelers insurance",
            "nationwide insurance",
            "life insurance", "auto insurance", "home insurance", "renters insurance",
            "lemonade insurance",
        ],
    ),
    # ── ATM/Cash ──────────────────────────────────────────────────────────────
    (
        TransactionCategory.ATM_CASH,
        [
            "atm withdrawal", "atm cash", "cash advance", "check cashing",
        ],
    ),
    # ── Transfers ─────────────────────────────────────────────────────────────
    (
        TransactionCategory.TRANSFERS,
        [
            "zelle", "venmo", "paypal", "cash app", "cashapp",
            "wire transfer", "ach transfer", "bank transfer",
            "western union", "moneygram",
        ],
    ),
    # ── Fees ──────────────────────────────────────────────────────────────────
    (
        TransactionCategory.FEES,
        [
            "annual fee", "monthly fee", "late fee", "overdraft fee",
            "foreign transaction fee", "balance transfer fee",
            "returned payment fee", "cash advance fee",
        ],
    ),
]


def categorize_merchant(description: str) -> tuple[TransactionCategory, float]:
    """
    Apply deterministic rules to categorize a transaction description.

    Args:
        description: Raw transaction description or merchant name.

    Returns:
        (category, confidence) — confidence is 1.0 for rule matches,
        0.0 for no match (caller should decide on LLM fallback).
    """
    lower = description.lower()
    for category, keywords in _CATEGORY_RULES:
        for kw in keywords:
            if kw in lower:
                return category, 1.0
    return TransactionCategory.OTHER, 0.0


# Common subscription detection keywords (used independently of category rules)
_SUBSCRIPTION_SIGNALS: frozenset[str] = frozenset(
    kw for _, kws in _CATEGORY_RULES
    if _ == TransactionCategory.SUBSCRIPTIONS
    for kw in kws
)


def is_likely_subscription(description: str) -> bool:
    """
    Quick check whether a transaction description looks like a subscription.

    Returns True if any known subscription keyword matches, OR if the
    description contains recurring billing signals.
    """
    lower = description.lower()
    # Known subscription services
    for kw in _SUBSCRIPTION_SIGNALS:
        if kw in lower:
            return True
    # Generic recurring billing signals
    recurring_signals = [
        "monthly", "annual subscription", "yearly subscription",
        "auto-renew", "auto renew", "billing cycle", "membership fee",
        "recurring", "subscription",
    ]
    return any(sig in lower for sig in recurring_signals)
