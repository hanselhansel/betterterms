"""Word lists for the gate's review tier (decision 0009 amendment:
the review tier is an allowlist; 0010 amendment: digits always route
and number words match inside letter runs).

``NUMBER_WORDS`` and ``SCALE_WORD_STEMS`` are matched as substrings
of each lowercased letter run, so "twelvehundred", "fiftyish",
"halfmillion", "thousandfold" and "grandtotal" still flag; the
singular stem also covers its plurals and glued k-suffix forms
("twok" flags on "two").
``NUMBER_WORD_EXCEPTIONS`` lists the common English words that
contain a number word or scale stem yet are not number forms
("often", "tone", "money", "attentive"); the exception is whole-run
only, so "oftener" still flags.
Every other list is matched as whole tokens on the rendered message's
token stream (tokens keep interior apostrophes, so "i'll" is one
word and "won't" is not "won"). ``CURRENCY_CODES`` is the one
exception: it matches the raw token case-sensitively, because TRY,
RUB and CAD are also common words in lowercase. ``k``, ``m``,
``mil`` and ``thou`` are scale abbreviations under decision 0010: a
bare one is number-shaped enough to route to the user, so they live
in ``SCALE_WORDS`` with the full words, but inside a letter run they
are ordinary letters ("milk", "family") and stay whole-token only.

``NUMBER_WORD_EXCEPTIONS`` was computed with a standard approach: a
standard common-English word list (the top 10,000 of
google-10000-english), keep every word containing a number word that
the number-parse rule does not flag (a word parses as a number when
it equals a number word, starts or ends with one and the remainder
is another number word, a scale word or empty, or is a concatenation
of number and scale words), then drop the number forms that still
slipped in (ordinals like "fourth" and "sixth", compounds like
"threesome") and the artifacts that are not English words. "ones"
stays: it is anaphoric English, not a count.

The guardrails SKILL.md quotes these lists verbatim; a unit test
checks the quote.
"""

NUMBER_WORDS = frozenset(
    "zero one two three four five six seven eight nine ten eleven "
    "twelve thirteen fourteen fifteen sixteen seventeen eighteen "
    "nineteen twenty thirty forty fifty sixty seventy eighty "
    "ninety dozen fifth ninth twelfth".split()
)

NUMBER_WORD_EXCEPTIONS = frozenset(
    "abandoned alone antenna anyone artwork attend attendance "
    "attended attending attention attentive bitten bone bones clone "
    "commissioner commissioners competent component components "
    "consistency consistent consistently content contents done "
    "everyone existence extend extended extending extends extension "
    "extensions extensive extent forgotten freight frightened gone "
    "gotten headphones height heights honest honestly honey hormone "
    "hydrocodone indonesia indonesian intend intended intense "
    "intensity intensive intent intention intentionally jones leone "
    "liechtenstein lightweight listen listened listening lone lonely "
    "maintenance mentioned microphone monetary money network "
    "networking networks nintendo none nonetheless often oftentimes "
    "ones opponent opponents ozone patent patents persistent phone "
    "phoned phones phoning pioneer potential potentially "
    "practitioner practitioners prisoner prisoners retention "
    "ringtone ringtones sentence sentences softened someone soonest "
    "stationery stone stones superintendent telephone tenant tend "
    "tender tennessee tennis tension tent tenure threatened "
    "threatening tone toned toner tones weight weighted weights "
    "written zone zones".split()
)

SCALE_WORDS = frozenset(
    "hundred hundreds thousand thousands million millions billion "
    "billions trillion trillions quadrillion quadrillions lakh lakhs "
    "crore crores bn mm k m mil thou mn mln bln tn bil".split()
)

# The singular full scale words (plus "grand") match as substrings of
# a lowercased letter run, like number words: "halfmillion",
# "thousandfold", "hundredish", "grandtotal". The plural stems are
# covered by the singulars. The abbreviations stay whole-token.
SCALE_WORD_STEMS = frozenset(
    "billion crore grand hundred lakh million quadrillion thousand "
    "trillion".split()
)

# ISO-style codes matched case-sensitively on the raw token: "CAD"
# flags, "cad" does not.
CURRENCY_CODES = frozenset(
    "USD EUR GBP SGD JPY CHF CAD AUD NZD HKD CNY CNH SEK NOK DKK "
    "INR BRL MXN KRW ZAR TWD MYR THB IDR PHP VND AED SAR ILS PLN "
    "CZK HUF TRY RUB RMB BTC".split()
)

# Currency words plus the lowercase-safe codes (cad, try and rub are
# also common words, so they are codes only). Some entries are common
# words too ("won", "real", "rand"): a whole-token false positive is
# still routed to the user, never a silent send.
CURRENCY_WORDS = frozenset(
    "aed aud baht bahts brl buck bucks cent cents chf cnh cny czk "
    "dinar dinars dirham dirhams dkk dollar dollars dong dongs eur "
    "euro euros franc francs gbp grand hkd huf idr ils inr jpy "
    "krona kronas krone kroner krones kronor krw lira liras lire "
    "mxn myr naira nairas nok nzd pence pennies penny peso pesos "
    "php pln pound pounds quid quids rand rands reais real "
    "renminbi ringgit ringgits riyal riyals ruble rubles rupee "
    "rupees rupiah rupiahs sar sek sgd shekel shekels sterling "
    "thb twd usd vnd won wons yen yens yuan yuans zar zloty "
    "zlotys".split()
)

COMMIT_WORDS = frozenset(
    "accept acceptance accepted accepting accepts agree agreeable "
    "agreed agreeing agreement agreements agrees cancel cancelling "
    "cancellation charge charged confirm confirmation confirmed "
    "confirming confirms deal deals paid pay paying sold".split()
)

# Two- or three-token phrases matched on the lowercased token stream;
# interior apostrophes stay inside the token ("i'll take" matches).
COMMIT_PHRASES = frozenset((
    ("cancel", "my"),
    ("count", "me", "in"),
    ("count", "us", "in"),
    ("glad", "to", "pay"),
    ("go", "ahead"),
    ("happy", "to", "pay"),
    ("i'll", "take"),
    ("let's", "do"),
    ("process", "it"),
    ("ready", "to", "pay"),
    ("sign", "me", "up"),
    ("sign", "us", "up"),
    ("sounds", "good"),
    ("take", "it"),
    ("we'll", "take"),
    ("willing", "to", "pay"),
    ("work", "for", "me"),
    ("work", "for", "us"),
    ("works", "for", "me"),
    ("works", "for", "us"),
    ("you", "have", "a", "deal"),
))
