"""Turn free-form job locations ("Noida, UP, IN, 201301", "US-CA-Menlo Park", "Bengaluru - India; Remote")
into a city, a country and a remote flag, so the dashboard can filter by them."""
import re
import unicodedata
from dataclasses import dataclass, field
import pycountry

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "PR": "Puerto Rico",
}

# Region names that should never be mistaken for a city.
REGIONS = {
    # India
    "karnataka", "ka", "telangana", "tg", "ts", "tamil nadu", "tn", "maharashtra", "mh", "uttar pradesh", "up",
    "haryana", "hr", "west bengal", "wb", "kerala", "gujarat", "gj", "rajasthan", "delhi ncr", "ncr", "andhra pradesh",
    "ap", "odisha", "madhya pradesh", "punjab", "in-tn", "in-ka", "in-mh", "in-tg", "in-up", "in-hr",
    # Elsewhere
    "ontario", "on", "quebec", "qc", "british columbia", "bc", "alberta", "england", "scotland", "bavaria",
    "north-rhine-westphalia", "lower-saxony", "community of madrid", "federal territory of kuala lumpur",
    "new south wales", "nsw", "victoria", "vic", "ile-de-france", "metro manila", "ncr - metro manila",
}

# Common job-market cities, mostly so short forms like "Pune, IN" or a bare "Singapore" resolve correctly.
CITY_COUNTRY = {
    **{c: "India" for c in (
        "bengaluru", "bangalore", "hyderabad", "pune", "chennai", "mumbai", "navi mumbai", "noida", "greater noida",
        "gurugram", "gurgaon", "new delhi", "delhi", "kolkata", "ahmedabad", "kochi", "cochin", "coimbatore",
        "thiruvananthapuram", "trivandrum", "chandigarh", "mohali", "jaipur", "indore", "nagpur", "bhubaneswar",
        "mysuru", "mysore", "mangaluru", "mangalore", "vadodara", "visakhapatnam", "vijayawada", "madurai",
        "lucknow", "gandhinagar", "nashik", "kolhapur", "hosur", "salem", "tiruchirappalli", "trichy",
    )},
    **{c: "United States" for c in (
        "seattle", "redmond", "bellevue", "san francisco", "san jose", "santa clara", "sunnyvale", "mountain view",
        "palo alto", "menlo park", "cupertino", "new york", "new york city", "boston", "austin", "dallas", "chicago",
        "atlanta", "los angeles", "san diego", "denver", "raleigh", "durham", "pittsburgh", "washington dc", "arlington",
        "mclean", "herndon", "reston", "houston", "phoenix", "salt lake city", "portland", "miami", "nashville",
        "minneapolis", "detroit", "philadelphia", "columbus", "charlotte", "cary", "irvine", "plano", "richardson",
    )},
    **{c: "United Kingdom" for c in ("london", "manchester", "edinburgh", "glasgow", "cambridge", "reading", "belfast", "bristol", "birmingham", "leeds")},
    **{c: "Canada" for c in ("toronto", "vancouver", "montreal", "ottawa", "calgary", "waterloo", "mississauga", "quebec city")},
    **{c: "Germany" for c in ("berlin", "munich", "frankfurt", "hamburg", "stuttgart", "cologne", "dusseldorf")},
    **{c: "China" for c in ("shanghai", "beijing", "shenzhen", "guangzhou", "hangzhou", "chengdu", "xi'an", "suzhou", "wuhan", "nanjing")},
    **{c: "Japan" for c in ("tokyo", "osaka", "yokohama", "kyoto", "nagoya")},
    "singapore": "Singapore", "hong kong": "Hong Kong", "dublin": "Ireland", "cork": "Ireland", "paris": "France",
    "amsterdam": "Netherlands", "madrid": "Spain", "barcelona": "Spain", "milan": "Italy", "rome": "Italy", "padua": "Italy",
    "warsaw": "Poland", "krakow": "Poland", "wroclaw": "Poland", "prague": "Czechia", "budapest": "Hungary",
    "bucharest": "Romania", "sofia": "Bulgaria", "lisbon": "Portugal", "stockholm": "Sweden", "copenhagen": "Denmark",
    "oslo": "Norway", "helsinki": "Finland", "zurich": "Switzerland", "geneva": "Switzerland", "vienna": "Austria",
    "brussels": "Belgium", "tel aviv": "Israel", "haifa": "Israel", "dubai": "United Arab Emirates",
    "abu dhabi": "United Arab Emirates", "riyadh": "Saudi Arabia", "cairo": "Egypt", "sydney": "Australia",
    "melbourne": "Australia", "brisbane": "Australia", "auckland": "New Zealand", "seoul": "South Korea",
    "taipei": "Taiwan", "hsinchu": "Taiwan", "manila": "Philippines", "kuala lumpur": "Malaysia", "penang": "Malaysia",
    "jakarta": "Indonesia", "bangkok": "Thailand", "ho chi minh city": "Vietnam", "hanoi": "Vietnam",
    "sao paulo": "Brazil", "mexico city": "Mexico", "guadalajara": "Mexico", "bogota": "Colombia",
    "buenos aires": "Argentina", "santiago": "Chile", "johannesburg": "South Africa", "cape town": "South Africa",
    "colombo": "Sri Lanka", "dhaka": "Bangladesh", "karachi": "Pakistan", "lahore": "Pakistan", "nairobi": "Kenya",
    "lagos": "Nigeria", "abuja": "Nigeria", "makati": "Philippines", "taguig": "Philippines", "pasig": "Philippines",
    "quezon city": "Philippines", "cebu": "Philippines", "cebu city": "Philippines", "warszawa": "Poland", "athens": "Greece",
    "casablanca": "Morocco", "rabat": "Morocco", "panama city": "Panama", "lima": "Peru", "montevideo": "Uruguay",
    "san jose costa rica": "Costa Rica", "heredia": "Costa Rica", "neuilly-sur-seine": "France", "courbevoie": "France",
    "puteaux": "France", "la defense": "France", "munchen": "Germany", "koln": "Germany", "milano": "Italy",
    "roma": "Italy", "praha": "Czechia", "wien": "Austria", "lisboa": "Portugal", "kyiv": "Ukraine", "tbilisi": "Georgia",
    "yerevan": "Armenia", "istanbul": "Turkey", "doha": "Qatar", "kuwait city": "Kuwait", "manama": "Bahrain",
    "muscat": "Oman", "amman": "Jordan", "beirut": "Lebanon", "accra": "Ghana",
}
CITY_ALIASES = {"warszawa": "Warsaw", "munchen": "Munich", "koln": "Cologne", "milano": "Milan", "roma": "Rome",
                "praha": "Prague", "wien": "Vienna", "lisboa": "Lisbon", "bangalore": "Bengaluru", "gurgaon": "Gurugram", "bombay": "Mumbai", "madras": "Chennai",
                "cochin": "Kochi", "trivandrum": "Thiruvananthapuram", "mysore": "Mysuru", "mangalore": "Mangaluru",
                "calcutta": "Kolkata", "trichy": "Tiruchirappalli"}

COUNTRY_ALIASES = {
    "usa": "United States", "us": "United States", "u.s.": "United States", "u.s.a.": "United States",
    "united states of america": "United States", "america": "United States",
    "uk": "United Kingdom", "great britain": "United Kingdom", "england": "United Kingdom", "scotland": "United Kingdom",
    "wales": "United Kingdom", "northern ireland": "United Kingdom",
    "uae": "United Arab Emirates", "korea": "South Korea", "republic of korea": "South Korea",
    "russia": "Russia", "czech republic": "Czechia", "turkey": "Turkey", "turkiye": "Turkey", "vietnam": "Vietnam",
    "holland": "Netherlands", "the netherlands": "Netherlands", "mainland china": "China", "prc": "China",
}
# Canonical display names where pycountry's are awkward.
NAME_OVERRIDES = {"RU": "Russia", "TR": "Turkey", "TW": "Taiwan", "KR": "South Korea", "VN": "Vietnam",
                  "IR": "Iran", "SY": "Syria", "LA": "Laos", "MD": "Moldova", "TZ": "Tanzania",
                  "BO": "Bolivia", "VE": "Venezuela", "KP": "North Korea", "CZ": "Czechia"}

_SPLIT_PARTS = re.compile(r"\s*;\s*|\s*\|\s*")
_SPLIT_TOKENS = re.compile(r"\s*,\s*|\s+-\s+|\s*:\s*")
_CODE_DASHED = re.compile(r"^[A-Z]{2,3}[-.]")  # "US-CA-Menlo Park", "CA-Ontario-Toronto", "USA.VA.Reston"
# Workplace words that sometimes sit where a location should be.
_NOT_PLACES = {"hybrid", "in-office", "in office", "on-site", "onsite", "office", "distributed", "anywhere", "flexible"}
_N_LOCATIONS = re.compile(r"^\d+\s+locations?$", re.I)
_MORE = re.compile(r"\+\s*\d+\s*more.*$", re.I)


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().strip().lower()


def _country_name(country) -> str:
    return NAME_OVERRIDES.get(country.alpha_2) or getattr(country, "common_name", None) or country.name


def _build_lookups():
    by_name, by_alpha2, by_alpha3 = {}, {}, {}
    for c in pycountry.countries:
        name = _country_name(c)
        by_alpha2[c.alpha_2] = name
        by_alpha3[c.alpha_3] = name
        for n in (c.name, getattr(c, "common_name", None), getattr(c, "official_name", None), name):
            if n:
                by_name[_fold(n)] = name
    by_name.update({_fold(k): v for k, v in COUNTRY_ALIASES.items()})
    return by_name, by_alpha2, by_alpha3


_BY_NAME, _BY_ALPHA2, _BY_ALPHA3 = _build_lookups()
_US_STATE_NAMES = {_fold(n) for n in US_STATES.values()}


@dataclass
class ParsedLocation:
    city: str | None = None
    country: str | None = None
    countries: list[str] = field(default_factory=list)
    is_remote: bool = False


def _tokens(part: str) -> list[str]:
    part = _MORE.sub("", part).strip()
    if "," not in part and " - " not in part and _CODE_DASHED.match(part):
        tokens = re.split(r"[-.]", part)
    else:
        tokens = _SPLIT_TOKENS.split(part)
    # Drop postal codes and building numbers ("Noida, UP, IN, 201301", "Gurugram 10 C").
    cleaned = []
    for t in tokens:
        words = [w for w in t.split() if not any(ch.isdigit() for ch in w)]
        if words and not (len(words) == 1 and len(words[0]) == 1):
            cleaned.append(" ".join(words))
    return cleaned


def _known_city(folded: str) -> str | None:
    """Match a known city at the start of a token, e.g. "bengaluru millenia" (an office name) -> "bengaluru"."""
    if folded in CITY_COUNTRY:
        return folded
    words = folded.replace("/", " ").split()
    for n in (3, 2, 1):
        if len(words) > n and " ".join(words[:n]) in CITY_COUNTRY:
            return " ".join(words[:n])
    return None


def _parse_part(part: str) -> tuple[str | None, str | None, bool]:
    """(city, country, remote) for one location like "Toronto, ON, CA"."""
    if _N_LOCATIONS.match(part.strip()):
        return None, None, False
    tokens = _tokens(part)
    remote = any(w in t.lower() for t in tokens for w in ("remote", "virtual", "teleworker", "distributed", "anywhere"))
    folded = [_fold(t) for t in tokens]

    country = None
    # 1. Full country names, aliases and 3-letter codes are unambiguous.
    for t, f in zip(tokens, folded):
        country = _BY_NAME.get(f) or (_BY_ALPHA3.get(t.upper()) if len(t) == 3 and t.isupper() else None)
        if country:
            break
    # 2. A well-known city.
    if not country:
        country = next((CITY_COUNTRY[c] for f in folded if (c := _known_city(f))), None)
    # 3. Two-letter codes: "Dallas, US", "Toronto, ON, CA", "US, CA, Santa Clara". "Sunnyvale, CA" is a US state.
    if not country:
        codes = [(i, t.upper()) for i, t in enumerate(tokens) if len(t) == 2 and t.isalpha()]
        for i, code in codes:
            if code not in _BY_ALPHA2:
                continue
            is_state = code in US_STATES
            if not is_state or (i == len(tokens) - 1 and len(tokens) >= 3) or (i == 0 and len(tokens) >= 2):
                country = _BY_ALPHA2[code]
                break
        if not country and any(code in US_STATES for _, code in codes):
            country = "United States"
    # 4. A US state name ("Bellevue, Washington").
    if not country and any(f in _US_STATE_NAMES for f in folded):
        country = "United States"

    city = None
    for t, f in zip(tokens, folded):
        is_code = len(t) <= 3 and t.isupper()
        if (is_code or f in _BY_NAME or f in REGIONS or f in _US_STATE_NAMES or f in _NOT_PLACES
                or any(w in f for w in ("remote", "virtual", "teleworker")) or f in ("all", "multiple locations")):
            continue
        known = _known_city(f)
        if known:
            city = CITY_ALIASES.get(known, " ".join(w.capitalize() for w in known.split()))
            if known == f and not t.isupper():
                city = CITY_ALIASES.get(known, t.strip())
        else:
            city = t.strip().title() if t.isupper() else t.strip()
        break
    if city is None and len(tokens) >= 2 and folded[0] in _US_STATE_NAMES and folded[1] == "dc":
        city = "Washington"
    return city, country, remote


def parse_location(location: str | None, workplace_type: str | None = None) -> ParsedLocation:
    result = ParsedLocation()
    workplace = (workplace_type or "").lower()
    result.is_remote = "remote" in workplace
    for part in _SPLIT_PARTS.split(location or ""):
        if not part.strip():
            continue
        city, country, remote = _parse_part(part)
        result.is_remote = result.is_remote or remote
        if result.city is None and city:
            result.city = city
        if country and country not in result.countries:
            result.countries.append(country)
    result.country = result.countries[0] if result.countries else None
    return result
