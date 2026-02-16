"""
Signal definitions for municipal meeting intelligence.
Centralized configuration of all keyword categories, weights, and lead classification rules.
"""

# ============================================================
# SIGNAL CATEGORIES
# Each category has a weight (1-10) and a list of keywords.
# Higher weight = stronger sales signal.
# ============================================================

SIGNALS = {
    "direct_mentions": {
        "label": "Direct Mention",
        "weight": 10,
        "description": "Caselle or its products mentioned by name",
        "keywords": [
            "caselle",
            "caselle inc",
            "caselle clarity",
            "clarity erp",
            "clarity software",
        ],
    },
    "competitor_mentions": {
        "label": "Competitor",
        "weight": 8,
        "description": "Competitor vendors mentioned — they're actively shopping",
        "keywords": [
            "tyler technologies",
            "tyler tech",
            "munis",
            "incode",
            "central square",
            "centralsquare",
            "bs&a",
            "bs&a software",
            "bsa software",
            "springbrook",
            "springbrook software",
            "edmunds govtech",
            "govstar",
            "harris local government",
            "harris computers",
            "freebalance",
            "accufund",
            "sage intacct",
            "opengov",
            "workday",
            "oracle netsuite",
            "sap",
            "superion",
            "new world systems",
            "sungard",
            "civic systems",
            "banyon data",
            "banyon",
            "black mountain software",
            "black mountain",
            "municipay",
            "govolution",
            "gus software",
        ],
    },
    "erp_signals": {
        "label": "ERP/Software",
        "weight": 7,
        "description": "ERP, financial, or government software discussion",
        "keywords": [
            "erp system",
            "erp software",
            "erp implementation",
            "erp migration",
            "erp solution",
            "erp vendor",
            "erp replacement",
            "erp upgrade",
            "enterprise resource planning",
            "financial software",
            "accounting software",
            "fund accounting",
            "government accounting",
            "governmental accounting",
            "utility billing software",
            "utility billing system",
            "payroll system",
            "payroll software",
            "payroll solution",
            "financial management system",
            "financial management software",
            "general ledger system",
            "general ledger software",
            "accounts payable system",
            "accounts receivable system",
            "municipal software",
            "government software",
            "city software",
        ],
    },
    "budget_signals": {
        "label": "Budget/Procurement",
        "weight": 6,
        "description": "Budget discussions, procurement, or RFP activity",
        "keywords": [
            "software procurement",
            "technology upgrade",
            "technology modernization",
            "system replacement",
            "system migration",
            "software evaluation",
            "software demo",
            "software demonstration",
            "vendor demonstration",
            "vendor demo",
            "request for proposal",
            "request for information",
            "request for qualifications",
            "rfp",
            "rfi",
            "rfq",
            "capital improvement",
            "it budget",
            "technology budget",
            "software budget",
            "software license",
            "software contract",
            "contract renewal",
            "vendor selection",
            "vendor evaluation",
            "vendor scoring",
            "vendor matrix",
            "bid opening",
            "sole source",
            "procurement process",
            "competitive bid",
            "software acquisition",
            "technology investment",
        ],
    },
    "pain_signals": {
        "label": "Pain Point",
        "weight": 5,
        "description": "Complaints, issues, or frustrations with current systems",
        "keywords": [
            "system outage",
            "software issues",
            "software problems",
            "legacy system",
            "outdated system",
            "outdated software",
            "aging system",
            "aging software",
            "end of life",
            "end-of-life",
            "no longer supported",
            "not supported",
            "manual process",
            "manual entry",
            "manual data entry",
            "data entry errors",
            "reconciliation issues",
            "reconciliation problems",
            "audit findings",
            "audit deficiency",
            "material weakness",
            "significant deficiency",
            "software frustration",
            "workaround",
            "work around",
            "inefficient",
            "inefficiency",
            "time consuming",
            "time-consuming",
            "double entry",
            "duplicate entry",
            "system crash",
            "system failure",
            "downtime",
            "data integrity",
            "reporting limitations",
            "reporting issues",
            "cannot generate reports",
            "lack of integration",
        ],
    },
}

# ============================================================
# COMMON MEETING MINUTES URL PATTERNS
# Used by the discovery engine to find meeting pages.
# ============================================================

URL_PATTERNS = [
    # CivicPlus AgendaCenter (very common)
    "/AgendaCenter",
    "/agendacenter",
    # Common paths
    "/agendas-minutes",
    "/agendas-and-minutes",
    "/meetings",
    "/city-council/meetings",
    "/city-council/agendas-minutes",
    "/government/agendas-minutes",
    "/government/meetings",
    "/government/city-council/agendas-minutes",
    "/government/city-council/meetings",
    "/council/meetings",
    "/council/agendas",
    "/city-government/agendas-minutes",
    "/city-government/meetings",
    "/departments/city-clerk/agendas-minutes",
    "/departments/city-clerk/meetings",
    "/clerk/agendas-minutes",
    "/your-government/agendas-minutes",
    "/our-city/agendas-and-minutes",
    "/minutes",
    "/meeting-agendas",
    "/meeting-minutes",
    "/public-meetings",
    "/council-meetings",
    "/city-council-meetings",
]

# ============================================================
# LEAD CLASSIFICATION RULES
# ============================================================

def classify_lead(score: float, signal_types: set) -> tuple[str, str]:
    """
    Classify a lead based on score and signal types.
    Returns (lead_type, recommended_action).
    """
    # HOT: Direct Caselle mention
    if "direct_mentions" in signal_types:
        if "budget_signals" in signal_types or "erp_signals" in signal_types:
            return "hot", "IMMEDIATE ACTION: Caselle mentioned in budget/ERP context — contact city IT director and account manager ASAP"
        return "hot", "IMMEDIATE ACTION: Caselle mentioned directly — review full document and coordinate with account team"

    # HOT: Competitor + procurement activity
    if "competitor_mentions" in signal_types and ("budget_signals" in signal_types or "erp_signals" in signal_types):
        return "hot", "HIGH PRIORITY: Active vendor evaluation in progress — competitors being considered. Engage immediately to get Caselle into the mix"

    # HOT: Active RFP (even without competitor names)
    if "budget_signals" in signal_types and "erp_signals" in signal_types and score >= 50:
        return "hot", "HIGH PRIORITY: Active ERP procurement discussion — likely issuing or planning an RFP. Get on their radar now"

    # WARM: ERP or budget discussion
    if "erp_signals" in signal_types:
        return "warm", "FOLLOW UP: ERP or financial software discussion detected — monitor for RFP and consider proactive outreach"

    if "budget_signals" in signal_types:
        return "warm", "FOLLOW UP: Technology budget or procurement discussion — may be planning a software evaluation cycle"

    # WARM: Competitor mention alone
    if "competitor_mentions" in signal_types:
        return "warm", "MONITOR: Competitor vendor mentioned — track for procurement timeline and engagement opportunity"

    # COLD: Pain signals only
    if "pain_signals" in signal_types:
        return "cold", "WATCH LIST: System pain points detected — could develop into an active opportunity. Add to nurture list"

    return "cold", "LOW SIGNAL: Minor indicators detected — add to watch list for future monitoring"
