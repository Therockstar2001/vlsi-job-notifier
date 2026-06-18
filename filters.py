ROLE_KEYWORDS = [
    # Core DV / verification
    "design verification",
    "verification engineer",
    "dv engineer",
    "formal verification",
    "soc verification",
    "cpu verification",
    "asic verification",
    "fpga verification",
    "emulation engineer",
    "verification",
    "formal",
    "emulation",

    # RTL / design
    "rtl design",
    "rtl engineer",
    "rtl",
    "asic design engineer",
    "asic development engineer",
    "asic front-end",
    "front-end design",
    "soc design",
    "soc/asic",
    "asic",
    "soc",

    # Embedded / firmware
    "embedded system engineer",
    "embedded systems engineer",
    "embedded software engineer",
    "embedded engineer",
    "firmware engineer",
    "embedded firmware",
    "firmware",
    "embedded",
    "bare metal",
    "device driver",
    "kernel",
    "linux kernel",

    # CPU / architecture / silicon-specific useful signals
    "riscv",
    "risc-v",
    "cpu",
    "silicon engineering",
    "dft engineer",
    "scan",
    "bringup",
    "bring-up"
]


ROLE_NEGATIVE_KEYWORDS = [
    # Business / non-engineering
    "marketing",
    "sales",
    "business development",
    "account executive",
    "account manager",
    "finance",
    "legal",
    "human resources",
    "people operations",
    "recruiting",
    "talent acquisition",
    "public relations",
    "communications",
    "brand",
    "social media",
    "content creator",
    "content strategist",
    "creative director",
    "video producer",
    "producer",
    "policy associate",
    "corporate development",
    "chief of staff",

    # Operations / support / manufacturing-floor noise
    "warehouse",
    "shipping",
    "forklift",
    "facilities",
    "supply chain",
    "material associate",
    "materials associate",
    "production associate",
    "workplace associate",
    "fleet technician",
    "technician",
    "operator",
    "coordinator",
    "project coordinator",
    "customer support",
    "technical support",
    "support specialist",

    # Roles usually outside your target
    "mechanical engineer",
    "propulsion",
    "thermal engineer",
    "cad engineer",
    "librarian",
    "retail",
    "store",
    "analog layout",
    "quality inspector",
    "supplier quality",
    "quality engineer",
    "vehicle test",
    "offensive security",
    "devops",
    "full stack",
    "backend",
    "software engineer - backend",
    "software engineer - full stack",
    "manufacturing",

    # Very noisy generic titles seen in your runs
    "federal materials associate",
    "associate director",
    "satellite policy associate"
]


ENTRY_LEVEL_KEYWORDS = [
    "new grad",
    "new graduate",
    "university graduate",
    "college graduate",
    "entry level",
    "early career",
    "engineer i",
    "graduate",
    "0 years",
    "0-1 years",
    "0 to 1 years",
    "1 year",
    "1+ year",
    "associate engineer"
]


INTERN_KEYWORDS = [
    "intern",
    "internship",
    "co-op",
    "coop",
    "student"
]


MID_LEVEL_KEYWORDS = [
    "2 years",
    "2+ years",
    "3 years",
    "3+ years",
    "4 years",
    "4+ years",
    "ii",
    "engineer 2"
]


SENIOR_LEVEL_KEYWORDS = [
    "senior",
    "staff",
    "principal",
    "director",
    "manager",
    "lead",
    "architect",
    "distinguished"
]


def is_relevant_role(title: str, description: str = "") -> bool:
    title = (title or "").lower().strip()
    description = (description or "").lower().strip()
    text = f"{title} {description}"

    # Strong positive title signals should pass even if description contains noisy words
    strong_title_signals = [
        "design verification",
        "verification engineer",
        "formal verification",
        "soc verification",
        "cpu core design verification",
        "cpu verification",
        "asic verification",
        "silicon design verification",
        "ip verification",
        "subsystem verification",
        "functional verification",
        "rtl design",
        "rtl/logic design",
        "rtl logic design",
        "rtl engineer",
        "asic design",
        "soc silicon design",
        "soc design",
        "dft verification",
        "emulation engineer",
        "fpga prototyping",
        "firmware engineer",
        "embedded systems",
        "embedded software",
    ]

    if any(good in title for good in strong_title_signals):
        return True

    # Hard reject obvious non-engineering noise based mainly on title
    title_blocked = [
        "marketing",
        "sales",
        "business development",
        "account executive",
        "account manager",
        "finance",
        "legal",
        "human resources",
        "people operations",
        "recruiting",
        "talent acquisition",
        "public relations",
        "communications",
        "brand",
        "social media",
        "content creator",
        "content strategist",
        "creative director",
        "video producer",
        "producer",
        "policy associate",
        "corporate development",
        "chief of staff",
        "warehouse",
        "shipping",
        "forklift",
        "facilities",
        "supply chain",
        "material associate",
        "materials associate",
        "production associate",
        "workplace associate",
        "fleet technician",
        "operator",
        "coordinator",
        "project coordinator",
        "customer support",
        "support specialist",
        "devops",
        "full stack",
        "backend",
        "software engineer - backend",
        "software engineer - full stack",
        "manufacturing",
        "quality inspector",
        "supplier quality",
    ]

    if any(bad in title for bad in title_blocked):
        return False

    # Softer negatives should only reject if title has no strong hardware/DV signal
    soft_blocked = [
        "mechanical engineer",
        "propulsion",
        "thermal engineer",
        "analog layout",
        "vehicle test",
        "offensive security",
        "retail",
        "store",
        "technician",
    ]

    if any(bad in title for bad in soft_blocked):
        return False

    # Must contain at least one positive signal in title or description
    return any(word in text for word in ROLE_KEYWORDS)


def get_seniority_bucket(title: str, description: str = "") -> str:
    title = (title or "").lower().strip()
    description = (description or "").lower().strip()
    text = f"{title} {description}"

    if any(word in text for word in INTERN_KEYWORDS):
        return "intern"

    if any(word in text for word in ENTRY_LEVEL_KEYWORDS):
        return "entry_level"

    if any(word in text for word in SENIOR_LEVEL_KEYWORDS):
        return "senior"

    if any(word in text for word in MID_LEVEL_KEYWORDS):
        return "mid"

    return "mid"


def is_us_location(location: str) -> bool:
    if not location:
        return False

    loc = location.lower().strip()

    non_us_country_keywords = [
        "australia",
        "canada",
        "india",
        "thailand",
        "finland",
        "germany",
        "poland",
        "japan",
        "taiwan",
        "singapore",
        "united kingdom",
        "ireland",
        "israel",
        "china",
        "korea",
        "netherlands",
        "france",
        "spain",
        "italy",
        "portugal",
        "romania",
        "malaysia",
        "vietnam",
        "argentina",
        "costa rica",
        "mexico",
        "brazil"
    ]

    if any(country in loc for country in non_us_country_keywords):
        return False

    non_us_city_keywords = [
        "hyderabad",
        "bengaluru",
        "bangalore",
        "pune",
        "mumbai",
        "noida",
        "gurgaon",
        "tokyo",
        "toronto",
        "vancouver",
        "ottawa",
        "montreal",
        "munich",
        "dublin",
        "eindhoven",
        "seoul",
        "shanghai",
        "beijing",
        "taipei",
        "hshinchu",
        "hsinchu",
        "penang",
        "singapore",
        "warsaw",
        "iasi",
        "cork"
    ]

    if any(city in loc for city in non_us_city_keywords):
        return False

    us_keywords = [
        "united states",
        "usa",
        "u.s.",
        "us remote",
        "remote us",
        "remote - us",
        "united states - remote",
        "california",
        "texas",
        "massachusetts",
        "minnesota",
        "michigan",
        "south carolina",
        "illinois",
        "georgia",
        "new york",
        "new jersey",
        "oregon",
        "washington",
        "virginia",
        "north carolina",
        "colorado",
        "arizona",
        "utah",
        "idaho",
        "florida",
        "ohio",
        "pennsylvania",
        "maryland",
        "district of columbia",
        "san francisco",
        "santa clara",
        "austin",
        "boston",
        "milpitas",
        "irvine",
        "san jose",
        "rochester",
        "sunnyvale",
        "el paso",
        "hillsboro",
        "mountain view",
        "costa mesa",
        "reston",
        "lexington",
        "south san francisco",
        "fremont",
        "phoenix",
        "fort collins",
        "quincy",
        "duluth",
        "cupertino",
        "folsom",
        "secaucus",
        "longmont",
        "boxborough",
        "bellevue"
    ]

    if any(keyword in loc for keyword in us_keywords):
        return True

    us_state_abbreviations = {
        "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga",
        "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me", "md",
        "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
        "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc",
        "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy",
        "dc"
    }

    separators = [",", ";", "|", "/", "-"]

    normalized = loc
    for sep in separators:
        normalized = normalized.replace(sep, ",")

    parts = [
        part.strip().replace(".", "")
        for part in normalized.split(",")
        if part.strip()
    ]

    if any(part in us_state_abbreviations for part in parts):
        return True

    return False