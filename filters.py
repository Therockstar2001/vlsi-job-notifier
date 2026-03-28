ROLE_KEYWORDS = [
    "design verification",
    "verification engineer",
    "dv engineer",
    "formal verification",
    "rtl design",
    "rtl engineer",
    "soc verification",
    "cpu verification",
    "emulation engineer",
    "asic verification",
    "asic design engineer",
    "asic development engineer",
    "soc/asic",
    "embedded system engineer",
    "embedded software engineer",
    "hardware & embedded",
    "firmware engineer",
    "embedded firmware",
    "riscv cpu",
    "wireless rtl",
    "soc design verification",
    "cellular soc design verification",
    "asic design and integration",
    "verification",
    "rtl",
    "asic",
    "soc",
    "embedded",
    "firmware",
    "emulation",
    "formal"
]

ROLE_NEGATIVE_KEYWORDS = [
    "marketing",
    "sales",
    "social media",
    "social strategist",
    "content creator",
    "content strategist",
    "creative director",
    "photography",
    "media",
    "brand",
    "communications",
    "public relations",
    "hr ",
    "human resources",
    "business partner",
    "warehouse",
    "shipping",
    "forklift",
    "project coordinator",
    "coordinator",
    "safety specialist",
    "recruiting",
    "people operations",
    "commercial associate",
    "program manager",
    "technical program manager",
    "facilities",
    "supply chain",
    "quality inspector",
    "supplier quality",
    "quality engineer",
    "test specialist",
    "test engineer associate",
    "vehicle test",
    "vehicle",
    "flight software",
    "mechanical engineer",
    "propulsion",
    "finance",
    "legal",
    "machinist",
    "thermal engineer",
    "security",
    "offensive security",
    "product security",
    "devops",
    "full stack",
    "backend",
    "software engineer - backend",
    "software engineer - full stack",
    "manufacturing",
    "pcb",
    "analog layout",
    "post-silicon",
    "chief of staff",
    "architect",
    "physical design",
    "validation engineer",
    "networking engineer",
    "robotics",
    "communications/dsp",
    "cad engineer",
    "librarian",
    "retail",
    "store",
    "designer",
    "design director",
    "customer support",
    "operations"
]


def is_relevant_role(title: str, description: str = "") -> bool:
    text = f"{title} {description}".lower()

    if any(bad in text for bad in ROLE_NEGATIVE_KEYWORDS):
        return False

    return any(word in text for word in ROLE_KEYWORDS)


def get_seniority_bucket(title: str, description: str = "") -> str:
    text = f"{title} {description}".lower()

    if any(word in text for word in [
        "intern",
        "internship",
        "co-op",
        "coop",
        "student"
    ]):
        return "intern"

    if any(word in text for word in [
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
        "1 year"
    ]):
        return "entry_level"

    if any(word in text for word in [
        "2 years",
        "2+ years",
        "3 years",
        "3+ years"
    ]):
        return "mid"

    if any(word in text for word in [
        "senior",
        "staff",
        "principal",
        "director",
        "manager",
        "lead",
        "architect"
    ]):
        return "senior"

    return "mid"


def is_us_location(location: str) -> bool:
    if not location:
        return False

    loc = location.lower()

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
        ", ca, canada", " canada", " toronto", " vancouver",
        "espoo", "munich", "rayong", "uusimaa", "bengaluru", "tokyo"
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
        "hillsboro"
    ]

    return any(keyword in loc for keyword in us_keywords)