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
    "physical design",
    "post-silicon",
    "validation engineer",
    "quality inspector",
    "supplier quality",
    "quality engineer",
    "vehicle test",
    "security",
    "offensive security",
    "product security",
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

    # Hard reject obvious noise first
    if any(bad in text for bad in ROLE_NEGATIVE_KEYWORDS):
        return False

    # Must contain at least one positive signal
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

    non_us_keywords = [
        ", th", " thailand",
        ", fi", " finland",
        ", de", " germany",
        ", pl", " poland",
        ", in", " india",
        ", jp", " japan",
        ", tw", " taiwan",
        ", sg", " singapore",
        ", uk", " united kingdom",
        ", ie", " ireland",
        ", il", " israel",
        ", cn", " china",
        ", kr", " korea",
        ", ca, canada", " canada",
        "toronto", "vancouver", "ottawa", "montreal",
        "espoo", "munich", "rayong", "uusimaa",
        "bengaluru", "tokyo", "cordoba", "argentina",
        "costa rica", "san jose, costa rica"
    ]

    if any(keyword in loc for keyword in non_us_keywords):
        return False

    us_keywords = [
        "united states",
        " usa",
        " us,",
        ", us",
        "virtual us",
        "remote us",
        "united states - remote",
        "remote - us",
        "u.s.",
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
        "dc",
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
        "duluth"
    ]

    return any(keyword in loc for keyword in us_keywords)