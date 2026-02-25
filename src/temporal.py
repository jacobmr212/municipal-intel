"""
Temporal Intelligence Analyzer

Extracts urgency signals from meeting documents:
- Deadline detection (RFP due dates, proposal deadlines)
- Timeline extraction (implementation schedules, fiscal year planning)
- Decision stage identification (early exploration vs ready to buy)
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    from dateutil import parser as dateparser
    DATEUTIL_AVAILABLE = True
except ImportError:
    DATEUTIL_AVAILABLE = False
    logger.warning("dateutil not available - date parsing will be limited")


@dataclass
class UrgencySignal:
    """A detected urgency indicator."""
    signal_type: str  # "deadline" | "timeline" | "active_procurement" | "budget_cycle"
    description: str  # Human-readable description
    date: Optional[datetime] = None  # Extracted date if applicable
    days_until: Optional[int] = None  # Days from now
    confidence: str = "medium"  # "high" | "medium" | "low"
    context: str = ""  # Surrounding text


@dataclass
class TemporalAnalysis:
    """Complete temporal analysis of a document."""
    urgency_score: int  # 0-100
    deadline_date: Optional[datetime] = None
    days_until_deadline: Optional[int] = None
    urgency_signals: List[UrgencySignal] = None
    decision_stage: str = "unknown"  # "exploration" | "evaluation" | "procurement" | "implementation"
    fiscal_year: Optional[str] = None  # e.g., "FY2025"

    def __post_init__(self):
        if self.urgency_signals is None:
            self.urgency_signals = []


class TemporalAnalyzer:
    """Analyzes documents for temporal urgency signals."""

    # Deadline patterns
    DEADLINE_PATTERNS = [
        # Explicit deadline language
        r'(?:due|deadline|closes?|expires?|submit|submission)(?:\s+(?:by|on|before))?\s+(\w+\s+\d{1,2},?\s*\d{4})',
        r'(?:due|deadline|closes?)(?:\s+(?:by|on|before))?\s+(\d{1,2}/\d{1,2}/\d{2,4})',
        r'responses?\s+(?:due|must be submitted)(?:\s+(?:by|on|before))?\s+([^.;]+)',
        r'proposal[s]?\s+(?:due|deadline)(?:\s+(?:by|on|before))?\s+([^.;]+)',

        # RFP-specific
        r'RFP\s+(?:due|closes|deadline)(?:\s+(?:by|on|before))?\s+([^.;]+)',
        r'bid[s]?\s+(?:due|close|deadline)(?:\s+(?:by|on|before))?\s+([^.;]+)',

        # Meeting/decision dates
        r'(?:final\s+)?decision\s+(?:by|on|in)\s+([^.;]+)',
        r'(?:board|council)\s+(?:vote|decision|approval)\s+(?:scheduled\s+for|on)\s+([^.;]+)',
    ]

    # Timeline patterns
    TIMELINE_PATTERNS = [
        r'implementation\s+(?:in|by|during|planned\s+for)\s+(\w+\s+\d{4})',
        r'(?:Q[1-4]|fiscal\s+year|FY)\s*(\d{4})',
        r'(\d{4})\s+budget',
        r'(?:complete|finish|deploy)(?:d|ed)?\s+(?:by|in)\s+(\w+\s+\d{4})',
        r'(?:start|begin|commence)(?:ing|s)?\s+(?:in|by)\s+(\w+\s+\d{4})',
    ]

    # Active procurement indicators
    ACTIVE_RFP_PATTERNS = [
        r'RFP\s+#?(\w+-?\d+)',
        r'Request\s+for\s+Proposal',
        r'(?:active|open|current)\s+(?:solicitation|procurement|RFP)',
        r'accepting\s+(?:proposals|bids)',
        r'vendor\s+responses?\s+(?:requested|sought)',
    ]

    # Decision stage indicators
    DECISION_STAGES = {
        'exploration': [
            'exploring options', 'researching', 'investigating', 'feasibility study',
            'needs assessment', 'preliminary', 'considering', 'reviewing options'
        ],
        'evaluation': [
            'evaluating', 'vendor demos', 'product demonstrations', 'comparing',
            'assessment phase', 'reviewing proposals', 'short list', 'finalist'
        ],
        'procurement': [
            'RFP', 'request for proposal', 'solicitation', 'bid', 'proposal',
            'vendor selection', 'contract negotiation', 'final decision'
        ],
        'implementation': [
            'implementation', 'deployment', 'go-live', 'migration',
            'training', 'onboarding', 'rollout', 'transition'
        ]
    }

    def __init__(self):
        # Pre-compile regex patterns
        self._deadline_patterns = [re.compile(p, re.IGNORECASE) for p in self.DEADLINE_PATTERNS]
        self._timeline_patterns = [re.compile(p, re.IGNORECASE) for p in self.TIMELINE_PATTERNS]
        self._active_rfp_patterns = [re.compile(p, re.IGNORECASE) for p in self.ACTIVE_RFP_PATTERNS]

    def _extract_context(self, text: str, pos: int, window: int = 150) -> str:
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

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Try to parse a date string into a datetime object."""
        if not DATEUTIL_AVAILABLE:
            return None

        try:
            # Clean up the date string
            date_str = date_str.strip().rstrip('.,;:')

            # Handle common formats
            parsed = dateparser.parse(date_str, fuzzy=True)
            if parsed:
                # If no year specified, assume current or next year
                if parsed.year < datetime.now().year:
                    parsed = parsed.replace(year=datetime.now().year)
                return parsed
        except Exception as e:
            logger.debug(f"Failed to parse date '{date_str}': {e}")

        return None

    def _detect_deadlines(self, text: str) -> List[UrgencySignal]:
        """Detect deadline-related urgency signals."""
        signals = []

        for pattern in self._deadline_patterns:
            for match in pattern.finditer(text):
                date_str = match.group(1)
                parsed_date = self._parse_date(date_str)

                if parsed_date:
                    days_until = (parsed_date - datetime.now()).days

                    # Only include future deadlines
                    if days_until >= 0:
                        # Determine confidence based on clarity
                        confidence = "high" if days_until <= 90 else "medium"

                        signal = UrgencySignal(
                            signal_type="deadline",
                            description=f"Deadline in {days_until} days",
                            date=parsed_date,
                            days_until=days_until,
                            confidence=confidence,
                            context=self._extract_context(text, match.start())
                        )
                        signals.append(signal)

        return signals

    def _detect_timelines(self, text: str) -> List[UrgencySignal]:
        """Detect timeline-related signals (implementation plans, fiscal years)."""
        signals = []

        for pattern in self._timeline_patterns:
            for match in pattern.finditer(text):
                timeline_str = match.group(1) if match.groups() else match.group(0)

                signal = UrgencySignal(
                    signal_type="timeline",
                    description=f"Timeline: {timeline_str}",
                    confidence="medium",
                    context=self._extract_context(text, match.start())
                )
                signals.append(signal)

        return signals

    def _detect_active_procurement(self, text: str) -> List[UrgencySignal]:
        """Detect active procurement/RFP signals."""
        signals = []

        for pattern in self._active_rfp_patterns:
            for match in pattern.finditer(text):
                signal = UrgencySignal(
                    signal_type="active_procurement",
                    description="Active procurement detected",
                    confidence="high",
                    context=self._extract_context(text, match.start())
                )
                signals.append(signal)

        return signals

    def _determine_decision_stage(self, text: str) -> str:
        """Determine what stage of the buying process they're in."""
        text_lower = text.lower()

        # Score each stage based on keyword matches
        stage_scores = {}
        for stage, keywords in self.DECISION_STAGES.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            stage_scores[stage] = score

        # Return stage with highest score, or 'unknown' if all zero
        if max(stage_scores.values()) == 0:
            return "unknown"

        return max(stage_scores.items(), key=lambda x: x[1])[0]

    def _extract_fiscal_year(self, text: str) -> Optional[str]:
        """Extract fiscal year mentions."""
        fy_pattern = re.compile(r'(?:FY|fiscal\s+year)\s*(\d{4})', re.IGNORECASE)
        match = fy_pattern.search(text)
        if match:
            return f"FY{match.group(1)}"
        return None

    def _calculate_urgency_score(self, signals: List[UrgencySignal], decision_stage: str) -> int:
        """Calculate overall urgency score (0-100)."""
        score = 0

        # Deadline-based scoring (most important)
        deadline_signals = [s for s in signals if s.signal_type == "deadline"]
        if deadline_signals:
            # Find the nearest deadline
            nearest = min(deadline_signals, key=lambda s: s.days_until or 999)
            if nearest.days_until is not None:
                if nearest.days_until <= 7:
                    score += 50  # URGENT - due within a week
                elif nearest.days_until <= 30:
                    score += 35  # Soon - due within a month
                elif nearest.days_until <= 90:
                    score += 20  # Upcoming - due within 3 months
                else:
                    score += 10  # Future deadline

        # Active procurement boost
        if any(s.signal_type == "active_procurement" for s in signals):
            score += 25

        # Decision stage multiplier
        stage_multipliers = {
            "procurement": 1.5,
            "evaluation": 1.2,
            "implementation": 0.8,
            "exploration": 0.6,
            "unknown": 1.0
        }
        score = int(score * stage_multipliers.get(decision_stage, 1.0))

        # Cap at 100
        return min(score, 100)

    def analyze(self, document_text: str) -> TemporalAnalysis:
        """Perform complete temporal analysis on a document."""
        signals = []

        # Detect all types of urgency signals
        signals.extend(self._detect_deadlines(document_text))
        signals.extend(self._detect_timelines(document_text))
        signals.extend(self._detect_active_procurement(document_text))

        # Determine decision stage
        decision_stage = self._determine_decision_stage(document_text)

        # Extract fiscal year
        fiscal_year = self._extract_fiscal_year(document_text)

        # Calculate urgency score
        urgency_score = self._calculate_urgency_score(signals, decision_stage)

        # Find the nearest deadline
        deadline_signals = [s for s in signals if s.signal_type == "deadline" and s.date]
        deadline_date = None
        days_until_deadline = None
        if deadline_signals:
            nearest = min(deadline_signals, key=lambda s: s.days_until or 999)
            deadline_date = nearest.date
            days_until_deadline = nearest.days_until

        return TemporalAnalysis(
            urgency_score=urgency_score,
            deadline_date=deadline_date,
            days_until_deadline=days_until_deadline,
            urgency_signals=signals,
            decision_stage=decision_stage,
            fiscal_year=fiscal_year
        )
