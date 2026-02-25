"""
Competitor Intelligence Analysis

Extracts and analyzes competitor mentions from municipal documents.
Helps sales teams understand competitive landscape and position Caselle effectively.
"""

import re
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class CompetitorMention:
    """Single competitor mention with context."""
    vendor: str  # Normalized vendor name
    raw_keyword: str  # Exact text matched
    context: str  # Surrounding text
    position: int  # Character position in document
    relationship: str  # existing_vendor | evaluating | rfp_respondent | mentioned


# Competitor database with normalized names and aliases
COMPETITORS = {
    "Tyler Technologies": [
        "tyler technologies",
        "tyler tech",
        "munis",
        "incode",
        "eden",  # Tyler's ERP product
        "exaction",  # Tyler's permitting software
    ],
    "CentralSquare": [
        "central square",
        "centralsquare",
        "naviline",  # CentralSquare ERP product
    ],
    "BS&A Software": [
        "bs&a",
        "bs&a software",
        "bsa software",
    ],
    "Springbrook": [
        "springbrook",
        "springbrook software",
        "cirrus",  # Springbrook cloud product
    ],
    "Harris": [
        "harris local government",
        "harris computers",
        "northstar",  # Harris product
    ],
    "Edmunds GovTech": [
        "edmunds govtech",
        "edmunds",
        "govstar",
    ],
    "FreeBalance": [
        "freebalance",
    ],
    "Questica": [
        "questica",
    ],
    "OpenGov": [
        "opengov",
        "opengov inc",
    ],
    "Accela": [
        "accela",
    ],
}


# Relationship detection patterns
RELATIONSHIP_PATTERNS = {
    "existing_vendor": [
        r"current\s+(?:system|vendor|provider|solution)",
        r"existing\s+(?:system|vendor|provider|solution)",
        r"we\s+(?:use|utilize|have)\s+(?:\w+\s+){{0,5}}{{competitor}}",
        r"currently\s+(?:using|utilizing)",
        r"maintenance\s+(?:contract|agreement)",
        r"annual\s+(?:support|maintenance)",
        r"renew(?:al|ing)?\s+(?:contract|agreement)",
    ],
    "evaluating": [
        r"demo(?:nstration)?",
        r"evaluat(?:e|ing|ion)",
        r"compar(?:e|ing|ison)",
        r"consider(?:ing)?",
        r"review(?:ing)?",
        r"shortlist",
        r"vendor\s+(?:list|selection|comparison)",
    ],
    "rfp_respondent": [
        r"(?:proposal|bid|response)\s+(?:from|by|received)",
        r"vendor\s+(?:proposals|responses|bids)",
        r"submitted\s+(?:a\s+)?(?:proposal|bid)",
        r"responded\s+to\s+(?:rfp|rfq)",
    ],
}


class CompetitorAnalyzer:
    """Analyzes competitor mentions and competitive landscape."""

    def __init__(self):
        # Build unified keyword → vendor mapping
        self.keyword_to_vendor = {}
        for vendor, keywords in COMPETITORS.items():
            for keyword in keywords:
                self.keyword_to_vendor[keyword.lower()] = vendor

        # Compile relationship patterns
        self.relationship_regex = {}
        for rel_type, patterns in RELATIONSHIP_PATTERNS.items():
            self.relationship_regex[rel_type] = [
                re.compile(pattern, re.IGNORECASE) for pattern in patterns
            ]

    def _extract_context(self, text: str, pos: int, window: int = 100) -> str:
        """Extract context around a match position."""
        start = max(0, pos - window)
        end = min(len(text), pos + window)
        return text[start:end].replace("\n", " ").strip()

    def _detect_relationship(self, context: str, vendor: str) -> str:
        """
        Detect relationship type based on context.

        Returns: existing_vendor | evaluating | rfp_respondent | mentioned
        """
        context_lower = context.lower()

        # Check each relationship type
        for rel_type, patterns in self.relationship_regex.items():
            for pattern in patterns:
                # For patterns with {competitor} placeholder, replace with vendor name
                pattern_str = pattern.pattern.replace("{competitor}", vendor.lower())
                if re.search(pattern_str, context_lower, re.IGNORECASE):
                    return rel_type

        # Default: just mentioned (no clear relationship context)
        return "mentioned"

    def analyze(self, document_text: str) -> Dict:
        """
        Analyze document for competitor mentions.

        Returns:
        {
            "competitors_mentioned": ["Tyler Technologies", "CentralSquare"],
            "mentions": [CompetitorMention, ...],
            "competitive_summary": {
                "existing_vendors": ["Tyler Technologies"],
                "evaluating": [],
                "rfp_respondents": ["CentralSquare"],
                "total_competitors": 2
            }
        }
        """
        text_lower = document_text.lower()
        mentions = []

        # Find all competitor mentions
        for keyword, vendor in self.keyword_to_vendor.items():
            pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
            for match in pattern.finditer(document_text):
                context = self._extract_context(document_text, match.start(), window=150)
                relationship = self._detect_relationship(context, vendor)

                mentions.append(
                    CompetitorMention(
                        vendor=vendor,
                        raw_keyword=match.group(),
                        context=context,
                        position=match.start(),
                        relationship=relationship,
                    )
                )

        # Deduplicate by vendor (keep first mention)
        vendors_seen = set()
        unique_mentions = []
        for mention in mentions:
            if mention.vendor not in vendors_seen:
                vendors_seen.add(mention.vendor)
                unique_mentions.append(mention)

        # Build competitive summary
        competitive_summary = {
            "existing_vendors": [m.vendor for m in unique_mentions if m.relationship == "existing_vendor"],
            "evaluating": [m.vendor for m in unique_mentions if m.relationship == "evaluating"],
            "rfp_respondents": [m.vendor for m in unique_mentions if m.relationship == "rfp_respondent"],
            "total_competitors": len(vendors_seen),
        }

        return {
            "competitors_mentioned": sorted(list(vendors_seen)),
            "mentions": unique_mentions,
            "competitive_summary": competitive_summary,
        }

    def get_strategic_context(self, competitive_analysis: Dict) -> str:
        """
        Generate strategic context for sales team.

        Returns a human-readable summary of the competitive situation.
        """
        if not competitive_analysis["competitors_mentioned"]:
            return "No competitors mentioned."

        summary = competitive_analysis["competitive_summary"]
        lines = []

        total = summary["total_competitors"]
        lines.append(f"{total} competitor{'s' if total > 1 else ''} mentioned:")

        if summary["existing_vendors"]:
            vendors = ", ".join(summary["existing_vendors"])
            lines.append(f"  • EXISTING VENDOR: {vendors} (displacement opportunity)")

        if summary["evaluating"]:
            vendors = ", ".join(summary["evaluating"])
            lines.append(f"  • EVALUATING: {vendors} (get Caselle in the mix)")

        if summary["rfp_respondents"]:
            vendors = ", ".join(summary["rfp_respondents"])
            lines.append(f"  • RFP RESPONDENTS: {vendors} (active procurement)")

        # Mentioned but no clear context
        mentioned_only = set(competitive_analysis["competitors_mentioned"])
        for key in ["existing_vendors", "evaluating", "rfp_respondents"]:
            mentioned_only -= set(summary[key])

        if mentioned_only:
            vendors = ", ".join(sorted(mentioned_only))
            lines.append(f"  • MENTIONED: {vendors}")

        return "\n".join(lines)
