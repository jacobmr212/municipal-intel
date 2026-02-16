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
    "active_rfp_signals": {
        "label": "Active RFP",
        "weight": 10,
        "description": "Active procurement with due date — HOT buying signal",
        "requires_context": True,  # Must validate context
        "keywords": [
            # Specific deadline phrases
            "submission deadline",
            "bid deadline",
            "proposal deadline",
            "proposals due",
            "bids due",
            "deadline for submission",
            # Procurement-specific events
            "pre-bid conference",
            "pre-proposal meeting",
            "mandatory pre-bid",
            "bid bond required",
            "proposal bond",
            # Specific procurement identifiers
            "solicitation number",
            "bid number",
            "rfp number",
            "project number",
            "sealed bid",
            "bid opening",
            # Removed overly generic:
            # - "currently accepting" (matches volunteers, jobs, etc.)
            # - "now accepting proposals" (too generic)
            # - "due date" (appears in all contexts)
            # - "closing date" (too generic)
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
# PROCUREMENT PORTAL URL PATTERNS
# Used to find RFP, bid, and purchasing pages.
# ============================================================

PROCUREMENT_PATTERNS = [
    # Common procurement page paths
    "/bids",
    "/rfps",
    "/rfp",
    "/purchasing",
    "/procurement",
    "/bid-opportunities",
    "/requests-for-proposals",
    "/open-bids",
    "/current-bids",
    "/solicitations",
    "/vendor-opportunities",
    # Department-specific
    "/departments/purchasing",
    "/departments/procurement",
    "/finance/purchasing",
    "/finance/bids",
    # Government paths
    "/government/purchasing",
    "/government/procurement",
    "/government/bids",
    # Business/vendor paths
    "/business/bids",
    "/business/purchasing",
    "/doing-business/bids",
    "/vendors/opportunities",
    "/vendor-center",
]

# ============================================================
# COMMON MEETING MINUTES URL PATTERNS
# Used by the discovery engine to find meeting pages.
# ============================================================

URL_PATTERNS = [
    # CivicPlus AgendaCenter (MOST common platform for small-mid gov)
    "/AgendaCenter",
    "/agendacenter",
    "/Agendacenter",
    "/Archive.aspx",  # CivicPlus archive pages
    "/archive.aspx",
    "/DocumentCenter",  # CivicPlus document center
    "/documentcenter",
    "/DocumentCenter/Index",
    # Granicus/Legistar (common municipal platform)
    "/ViewPublishedAgendas.ashx",
    "/PublishedAgendas.ashx",
    "/Meetings.aspx",
    "/Calendar.aspx",
    "/meetings.aspx",
    "/calendar.aspx",
    # BoardDocs
    "/meetings/Board",
    "/BoardDocs",
    "/boarddocs",
    # Common paths - council
    "/city-council",
    "/city-council/meetings",
    "/city-council/agendas",
    "/city-council/agendas-minutes",
    "/city-council/agendas-and-minutes",
    "/council",
    "/council/meetings",
    "/council/agendas",
    "/council/agendas-minutes",
    "/council/minutes",  # Common pattern
    "/council-meetings",
    "/city-council-meetings",
    "/meetings/city-council",  # Common pattern
    # Common paths - government
    "/government/agendas-minutes",
    "/government/meetings",
    "/government/agendas",
    "/government/city-council",
    "/government/city-council/agendas-minutes",
    "/government/city-council/meetings",
    "/government/boards-commissions/city-council",  # Common pattern
    "/government/council/meetings",  # Common pattern
    "/city-government/agendas-minutes",
    "/city-government/meetings",
    "/your-government/agendas-minutes",
    "/your-government/meetings",
    "/our-government/city-council/agendas-minutes",  # Common pattern
    # Common paths - meetings
    "/meetings",
    "/agendas-minutes",
    "/agendas-and-minutes",
    "/agendas",
    "/minutes",
    "/meeting-agendas",
    "/meeting-minutes",
    "/MeetingMinutes",  # Common pattern
    "/meetingminutes",
    "/public-meetings",
    # Common paths - departments / city clerk
    "/departments/city-clerk",
    "/departments/city-clerk/agendas-minutes",
    "/departments/city-clerk/meetings",
    "/departments/clerk",
    "/city-clerk",
    "/city-clerk/meetings",
    "/city-clerk/agendas",
    "/city-clerk/agendas-minutes",  # Common pattern
    "/clerk/agendas-minutes",
    "/clerk/meetings",
    # Other common patterns
    "/our-city/agendas-and-minutes",
    "/residents/agendas-minutes",
    "/about/agendas-minutes",
    "/services/agendas-minutes",
]

# ============================================================
# LEAD CLASSIFICATION RULES
# ============================================================

def classify_lead(score: float, signal_types: set, source_type: str = "meeting_minutes",
                  high_confidence_signals: set = None) -> tuple[str, str]:
    """
    Classify a lead based on score, signal types, source type, and signal confidence.
    Returns (lead_type, recommended_action).

    high_confidence_signals: set of signal_types that had high-confidence matches
    """
    # Default to treating all signals as high confidence if not specified
    if high_confidence_signals is None:
        high_confidence_signals = signal_types

    # HOT: Active RFP with deadline (HIGHEST PRIORITY) - but only if HIGH confidence
    if "active_rfp_signals" in high_confidence_signals:
        if "erp_signals" in signal_types or "budget_signals" in signal_types:
            return "hot", "URGENT: Active RFP with deadline detected — review immediately and prepare response. Time-sensitive opportunity"
        return "hot", "HIGH PRIORITY: Active procurement with deadline — review to determine if ERP-related"

    # HOT: Direct Caselle mention
    if "direct_mentions" in signal_types:
        if "budget_signals" in signal_types or "erp_signals" in signal_types:
            return "hot", "IMMEDIATE ACTION: Caselle mentioned in budget/ERP context — contact city IT director and account manager ASAP"
        return "hot", "IMMEDIATE ACTION: Caselle mentioned directly — review full document and coordinate with account team"

    # HOT: Procurement source with ERP signals
    if source_type == "procurement" and "erp_signals" in signal_types:
        return "hot", "HIGH PRIORITY: ERP-related procurement posting found — city is actively seeking software. Engage now"

    # HOT: Competitor + procurement activity
    if "competitor_mentions" in signal_types and ("budget_signals" in signal_types or "erp_signals" in signal_types):
        return "hot", "HIGH PRIORITY: Active vendor evaluation in progress — competitors being considered. Engage immediately to get Caselle into the mix"

    # HOT: Active RFP (even without competitor names)
    if "budget_signals" in signal_types and "erp_signals" in signal_types and score >= 50:
        return "hot", "HIGH PRIORITY: Active ERP procurement discussion — likely issuing or planning an RFP. Get on their radar now"

    # WARM: Procurement source (even without strong ERP signals)
    if source_type == "procurement":
        return "warm", "FOLLOW UP: Procurement posting found — review for software/technology relevance"

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
