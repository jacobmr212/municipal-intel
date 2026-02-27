"""
AI-powered document validation.
Filters out irrelevant documents before they become leads.
"""

import os
import logging
from typing import Optional
import anthropic

logger = logging.getLogger(__name__)

class AIValidator:
    """Uses Claude to validate if a document is actually relevant."""

    def __init__(self):
        self.client = None
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            self.client = anthropic.Anthropic(api_key=api_key)
            logger.info("AI Validator initialized with Claude API")
        else:
            logger.warning("ANTHROPIC_API_KEY not found - AI validation disabled")

    def validate_relevance(self, doc_text: str, signals: list, title: str) -> dict:
        """
        Validate if document is actually about ERP/software procurement.

        Returns:
            dict with keys:
                - is_relevant (bool): True if document is about ERP/software
                - confidence (float): 0.0-1.0 confidence score
                - reason (str): Explanation of decision
        """
        if not self.client:
            # If no API key, default to accepting (permissive)
            return {
                "is_relevant": True,
                "confidence": 0.5,
                "reason": "AI validation disabled - no API key"
            }

        # Extract signal names for context
        signal_names = [s.signal_type for s in signals] if signals else []

        prompt = f"""You are validating whether a municipal government document is relevant for ERP/software sales.

Document Title: {title}
Document Excerpt (first 2000 chars): {doc_text[:2000]}
Signals Detected: {', '.join(signal_names)}

RELEVANT documents are about:
- ERP systems, financial software, accounting software
- Software procurement, software RFPs, software budgets
- Technology modernization, digital transformation
- Software implementation, software migration
- Software vendor selection, software evaluation

IRRELEVANT documents are about:
- Physical equipment (street sweepers, vehicles, mowers, trucks)
- Construction/facilities (buildings, roads, bridges, HVAC)
- Land use, zoning, permits, appeals
- Personnel/HR matters (not related to software)
- General city operations (not technology-related)

Analyze this document and determine: Is this actually about ERP or government software procurement?

Respond in JSON format:
{{
  "is_relevant": true or false,
  "confidence": 0.0 to 1.0,
  "reason": "Brief explanation (1-2 sentences)"
}}"""

        try:
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=500,
                temperature=0,
                messages=[{"role": "user", "content": prompt}]
            )

            # Parse JSON response
            import json
            result_text = response.content[0].text

            # Extract JSON from response (handle markdown code blocks)
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()

            result = json.loads(result_text)

            logger.info(f"AI Validation: {title[:50]} -> {'RELEVANT' if result['is_relevant'] else 'IRRELEVANT'} (confidence: {result['confidence']})")
            logger.info(f"  Reason: {result['reason']}")

            return result

        except Exception as e:
            logger.error(f"AI validation failed: {e}")
            # On error, default to accepting (permissive)
            return {
                "is_relevant": True,
                "confidence": 0.3,
                "reason": f"AI validation error: {str(e)}"
            }
