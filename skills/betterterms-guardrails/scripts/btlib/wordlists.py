"""Whole-word lists for the gate's review tier (decision 0009
amendment: the review tier is an allowlist).

Every list is matched as whole tokens on the rendered message's
lowercased alphanumeric token stream, never as substrings or regexes.
``CURRENCY_CODES`` is the one exception: it matches the raw token
case-sensitively, because TRY, RUB and CAD are also common words in
lowercase. ``k``, ``m``, ``mil`` and ``thou`` are scale abbreviations
under decision 0010: a bare one is number-shaped enough to route to
the user, so they live in ``SCALE_WORDS`` with the full words.

The guardrails SKILL.md quotes these lists verbatim; a unit test
checks the quote.
"""

NUMBER_WORDS = frozenset(
    "zero one two three four five six seven eight nine ten eleven "
    "twelve thirteen fourteen fifteen sixteen seventeen eighteen "
    "nineteen twenty thirty forty fifty sixty seventy eighty "
    "ninety".split()
)

# The integer each single number word stands for. A word equal to the
# floor's integer part is a restated limit, not a harmless word; scale
# words carry no value here because they never stand alone.
NUMBER_WORD_VALUES = {
    "zero": 0,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
    "ninety": 90,
}

SCALE_WORDS = frozenset(
    "hundred hundreds thousand thousands million millions billion "
    "billions trillion trillions bn mm k m mil thou".split()
)

# ISO-style codes matched case-sensitively on the raw token: "CAD"
# flags, "cad" does not.
CURRENCY_CODES = frozenset(
    "USD EUR GBP SGD JPY CHF CAD AUD NZD HKD CNY CNH SEK NOK DKK "
    "INR BRL MXN KRW ZAR TWD MYR THB IDR PHP VND AED SAR ILS PLN "
    "CZK HUF TRY RUB".split()
)

# Currency words plus the lowercase-safe codes (cad, try and rub are
# also common words, so they are codes only).
CURRENCY_WORDS = frozenset(
    "aed aud brl chf cnh cny czk dkk dollar dollars buck bucks eur "
    "euro euros gbp grand hkd huf idr ils inr jpy krw mxn myr nok "
    "nzd php pln pound pounds quid renminbi sar sek sgd thb twd usd "
    "vnd yen yuan zar".split()
)

COMMIT_WORDS = frozenset(
    "accept acceptance accepted accepting accepts agree agreeable "
    "agreed agreeing agreement agreements charge confirm "
    "confirmation confirmed confirming confirms deal pay".split()
)

# Two- or three-token phrases matched on the lowercased token stream.
COMMIT_PHRASES = frozenset((
    ("cancel", "my"),
    ("glad", "to", "pay"),
    ("go", "ahead"),
    ("happy", "to", "pay"),
    ("process", "it"),
    ("ready", "to", "pay"),
    ("sign", "me", "up"),
    ("sounds", "good"),
    ("willing", "to", "pay"),
    ("work", "for", "me"),
    ("work", "for", "us"),
    ("works", "for", "me"),
    ("works", "for", "us"),
))

# Whole-word month names and their three-letter forms; a 1900-2100
# year right after one is a date, not an amount.
MONTH_WORDS = frozenset(
    "january february march april may june july august september "
    "october november december jan feb mar apr jun jul aug sep oct "
    "nov dec".split()
)
