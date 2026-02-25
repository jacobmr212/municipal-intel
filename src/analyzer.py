"""
Document Analyzer
Scores meeting documents against weighted signal categories and classifies leads.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

from .signals import SIGNALS, classify_lead
from .temporal import TemporalAnalyzer

logger = logging.getLogger(__name__)

# ── Physical/infrastructure procurement — if these appear near a budget/RFP signal,
# the match is equipment/construction procurement, not software. Downgrade to low confidence.
PHYSICAL_PROCUREMENT_TERMS = [
    "street sweeper", "sweeper", "mower", "lawn mower", "excavator", "backhoe",
    "grader", "snowplow", "snow plow", "dump truck", "fire truck", "ambulance",
    "patrol car", "police vehicle", "fleet vehicle", "fleet management",
    "hvac", "elevator", "generator", "lift station", "pump station",
    "water line", "sewer line", "sewer main", "water main", "water pipe",
    "stormwater", "storm water", "road construction", "pavement", "paving",
    "asphalt", "concrete repair", "bridge", "culvert", "sidewalk",
    "building renovation", "roofing", "roof replacement", "landscaping",
    "park equipment", "playground", "street light", "traffic signal",
]

# ── Tech-context terms required to validate RFP/budget signals as software-related ──
# These must appear within ±50 words of the trigger keyword.
TECH_CONTEXT_TERMS = [
    "software", "system", "technology", "erp", "financial system",
    "accounting system", "payroll system", "billing system",
    "information technology", "it department", "it services",
    "implementation", "digital", "database", "application", "platform",
    "cloud", "saas", "hosted", "license", "subscription",
    "data migration", "integration", "interface",
]


@dataclass
class SignalMatch:
    """A single keyword match found in a document."""
    signal_type: str
    signal_label: str
    keyword: str
    context: str
    weight: int
    position: int
    confidence: str = "high"  # "high" or "low" - used for context validation


@dataclass
class AnalysisResult:
    """Complete analysis of a single document."""
    municipality: str
    state: str
    population: int
    title: str
    url: str
    date: Optional[str]
    relevance_score: float
    source_type: str = "meeting_minutes"  # meeting_minutes, procurement, budget, job_posting, agenda_packet, audit
    signal_matches: list[SignalMatch] = field(default_factory=list)
    summary: str = ""
    lead_type: str = ""
    customer_status: str = "unknown"  # existing_customer | new_opportunity | unknown
    recommended_action: str = ""
    llm_analysis: str = ""
    document_text: str = ""  # Full document text for deduplication hashing

    # Temporal intelligence
    urgency_score: int = 0  # 0-100
    deadline_date: Optional[str] = None  # ISO format date string
    days_until_deadline: Optional[int] = None
    decision_stage: str = "unknown"
    fiscal_year: Optional[str] = None

    @property
    def match_count(self) -> int:
        return len(self.signal_matches)

    @property
    def signal_types_found(self) -> set:
        return {m.signal_type for m in self.signal_matches}

    @property
    def signal_labels_found(self) -> list[str]:
        seen = set()
        labels = []
        for m in self.signal_matches:
            if m.signal_type not in seen:
                seen.add(m.signal_type)
                labels.append(m.signal_label)
        return labels


class DocumentAnalyzer:
    """Analyzes scraped documents for sales-relevant signals."""

    def __init__(self, use_llm: bool = False, llm_model: str = "claude-sonnet-4-20250514"):
        self.use_llm = use_llm
        self.llm_model = llm_model

        # Initialize temporal analyzer
        self.temporal_analyzer = TemporalAnalyzer()

        # Pre-compile patterns
        self._compiled = {}
        for sig_type, sig_cfg in SIGNALS.items():
            patterns = []
            for kw in sig_cfg["keywords"]:
                pattern = re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
                patterns.append((kw, pattern))
            self._compiled[sig_type] = {
                "patterns": patterns,
                "weight": sig_cfg["weight"],
                "label": sig_cfg["label"],
                "requires_context": sig_cfg.get("requires_context", False),
            }

    def _extract_context(self, text: str, pos: int, window: int = 250) -> str:
        """Extract surrounding text for context."""
        start = max(0, pos - window)
        end = min(len(text), pos + window)
        ctx = text[start:end].strip()
        ctx = re.sub(r'\s+', ' ', ctx)
        if start > 0:
            ctx = "..." + ctx
        if end < len(text):
            ctx = ctx + "..."
        return ctx

    def _extract_window(self, text: str, pos: int, num_words: int = 50) -> str:
        """Extract ±num_words words around pos as a lowercase string."""
        words_per_char = 0.16  # ~6 chars per word average
        char_window = int(num_words / words_per_char)
        start = max(0, pos - char_window)
        end = min(len(text), pos + char_window)
        return text[start:end].lower()

    def _is_physical_procurement(self, text: str, pos: int) -> bool:
        """
        Returns True if physical/infrastructure keywords appear within ±50 words.
        Used to downgrade budget/RFP signals that are about equipment, not software.
        """
        window = self._extract_window(text, pos, num_words=50)
        return any(term in window for term in PHYSICAL_PROCUREMENT_TERMS)

    def _has_tech_context(self, text: str, pos: int) -> bool:
        """
        Returns True if at least one tech/software keyword appears within ±50 words.
        Required to validate that budget/RFP signals are software-related.
        """
        window = self._extract_window(text, pos, num_words=50)
        return any(term in window for term in TECH_CONTEXT_TERMS)

    def _validate_procurement_context(self, text: str, pos: int, signal_type: str = "") -> bool:
        """
        Validate that a procurement signal appears in relevant tech/software context.

        For active_rfp_signals: requires TECH context terms within ±50 words.
          The old approach checked for any procurement word (including "rfp"), which
          caused circular validation — "rfp" on any page validated "deadline for submission"
          even when the deadline referred to meeting agenda submissions.

        For budget_signals: requires TECH context within ±50 words AND no physical
          procurement terms (to filter street sweeper / equipment RFPs).

        Returns True (high confidence) if the signal is in a tech/software context.
        """
        # Step 1: Reject if physical procurement terms are nearby
        if self._is_physical_procurement(text, pos):
            return False

        # Step 2: Require at least one tech-context term nearby
        if not self._has_tech_context(text, pos):
            return False

        return True

    def _find_matches(self, text: str) -> list[SignalMatch]:
        """Run keyword matching across all signal categories."""
        matches = []
        for sig_type, sig_data in self._compiled.items():
            requires_context = sig_data.get("requires_context", False)

            for kw, pattern in sig_data["patterns"]:
                for match in pattern.finditer(text):
                    # For signals that require context validation, check for tech context
                    # and absence of physical procurement terms.
                    confidence = "high"
                    if requires_context:
                        if not self._validate_procurement_context(text, match.start(), sig_type):
                            confidence = "low"

                    matches.append(SignalMatch(
                        signal_type=sig_type,
                        signal_label=sig_data["label"],
                        keyword=kw,
                        context=self._extract_context(text, match.start()),
                        weight=sig_data["weight"],
                        position=match.start(),
                        confidence=confidence,
                    ))
        return matches

    def _calculate_score(self, matches: list[SignalMatch]) -> float:
        """Calculate relevance score (0-100)."""
        if not matches:
            return 0.0

        base = sum(m.weight for m in matches)
        unique_types = len({m.signal_type for m in matches})
        diversity_bonus = min(unique_types * 5, 20)
        direct_bonus = 25 if any(m.signal_type == "direct_mentions" for m in matches) else 0

        return min(round(base + diversity_bonus + direct_bonus, 1), 100)

    def _llm_enhance(self, text: str, matches: list[SignalMatch], municipality: str) -> str:
        """Use Claude for deeper contextual analysis."""
        if not self.use_llm:
            return ""
        try:
            import anthropic
            client = anthropic.Anthropic()

            match_summary = "\n".join([
                f"- [{m.signal_label}] '{m.keyword}': {m.context[:150]}"
                for m in matches[:8]
            ])

            response = client.messages.create(
                model=self.llm_model,
                max_tokens=400,
                messages=[{
                    "role": "user",
                    "content": f"""You are a government ERP sales intelligence analyst for Caselle Inc.

Analyze this municipal meeting excerpt from {municipality}. Provide a 3-4 sentence sales brief covering:
1. What's happening that's relevant to government ERP software?
2. Is there active procurement or just early discussion?
3. Timeline/urgency indicators?
4. Any decision-makers or influencers named?

Signal matches:
{match_summary}

Document (first 6000 chars):
{text[:6000]}

Reply with ONLY the sales brief."""
                }]
            )
            return response.content[0].text
        except Exception as e:
            logger.warning(f"LLM analysis failed for {municipality}: {e}")
            return ""

    def analyze_document(self, doc, population: int = 0,
                          min_score: float = 10, source_type: str = "meeting_minutes") -> Optional[AnalysisResult]:
        """Analyze a single document for lead signals."""
        matches = self._find_matches(doc.text)
        if not matches:
            return None

        score = self._calculate_score(matches)
        if score < min_score:
            return None

        signal_types = {m.signal_type for m in matches}
        high_confidence_signals = {m.signal_type for m in matches if m.confidence == "high"}
        lead_type, action = classify_lead(score, signal_types, source_type, high_confidence_signals)

        # Determine customer status based on direct mentions
        customer_status = "existing_customer" if "direct_mentions" in signal_types else "new_opportunity"

        # Build summary
        unique_kws = list(dict.fromkeys(m.keyword for m in matches))[:6]
        summary = f"{len(matches)} signal(s): {', '.join(unique_kws)}"

        # LLM enhancement for hot/warm leads
        llm_text = ""
        if self.use_llm and lead_type in ("hot", "warm"):
            llm_text = self._llm_enhance(doc.text, matches, doc.municipality)

        # Temporal analysis
        temporal = self.temporal_analyzer.analyze(doc.text)

        # Boost relevance score based on urgency
        if temporal.urgency_score > 50:
            score = min(score + (temporal.urgency_score * 0.2), 100)

        return AnalysisResult(
            municipality=doc.municipality,
            state=doc.state,
            population=population,
            title=doc.title,
            url=doc.url,
            date=doc.date.strftime("%Y-%m-%d") if doc.date else "Unknown",
            relevance_score=score,
            source_type=source_type,
            signal_matches=matches,
            summary=summary,
            lead_type=lead_type,
            customer_status=customer_status,
            recommended_action=action,
            llm_analysis=llm_text,
            document_text=doc.text,  # Store for deduplication
            urgency_score=temporal.urgency_score,
            deadline_date=temporal.deadline_date.isoformat() if temporal.deadline_date else None,
            days_until_deadline=temporal.days_until_deadline,
            decision_stage=temporal.decision_stage,
            fiscal_year=temporal.fiscal_year
        )

    def analyze_all(self, documents: list, population_map: dict = None,
                     min_score: float = 10, progress_callback=None) -> list[AnalysisResult]:
        """Analyze all documents and return sorted results."""
        if population_map is None:
            population_map = {}

        results = []
        total = len(documents)

        for i, doc in enumerate(documents):
            if progress_callback:
                progress_callback(i, total, f"Analyzing: {doc.municipality}")

            pop = population_map.get(doc.municipality, 0)
            result = self.analyze_document(doc, population=pop, min_score=min_score)
            if result:
                results.append(result)

        results.sort(key=lambda r: r.relevance_score, reverse=True)

        hot = sum(1 for r in results if r.lead_type == "hot")
        warm = sum(1 for r in results if r.lead_type == "warm")
        cold = sum(1 for r in results if r.lead_type == "cold")
        logger.info(f"Analysis: {len(results)} leads from {total} docs — 🔥{hot} 🟡{warm} 🔵{cold}")

        return results
