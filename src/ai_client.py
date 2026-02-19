"""
AI Integration Module for Assessment Platform
Uses Anthropic Claude API for real-time analysis and compliance findings.
"""

import os
from typing import Optional, Dict, Any
from anthropic import Anthropic

# Initialize Anthropic client
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    print("WARNING: ANTHROPIC_API_KEY not found in environment variables. AI features will be disabled.")

anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

CLAUDE_MODEL = "claude-sonnet-4-5-20250929"


async def call_claude(system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> Optional[str]:
    """
    Call Claude API with system and user prompts.

    Args:
        system_prompt: System context for the AI
        user_prompt: User's question or data to analyze
        max_tokens: Maximum tokens in response

    Returns:
        AI response text or None if API key not configured
    """
    if not anthropic_client:
        return None

    try:
        message = anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            temperature=0,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": user_prompt
                }
            ]
        )

        # Extract text content from response
        text_content = next(
            (block.text for block in message.content if hasattr(block, 'text')),
            None
        )

        return text_content

    except Exception as e:
        print(f"Error calling Claude API: {e}")
        return None


async def analyze_coa_structure(
    account_count: str,
    last_review: str,
    state: str,
    inactive_percentage: str
) -> Optional[Dict[str, Any]]:
    """
    Analyze Chart of Accounts structure and provide findings.

    Args:
        account_count: Number of GL accounts (e.g., "500-1000")
        last_review: When COA was last reviewed (e.g., "2-5-years")
        state: User's state for state-specific rules
        inactive_percentage: Percentage of inactive accounts

    Returns:
        Dict with findings and recommendations
    """
    system_prompt = f"""You are an expert municipal ERP consultant analyzing Chart of Accounts (COA) structures.

The municipality is in {state}. Provide concise, actionable findings based on municipal government best practices.

Return your analysis as JSON with this structure:
{{
  "findings": [
    {{
      "severity": "critical|high|medium|low",
      "title": "Finding title",
      "description": "What the issue is",
      "impact": "Why it matters",
      "recommendation": "What to do about it"
    }}
  ],
  "summary": "2-3 sentence executive summary"
}}

Focus on:
- COA bloat (municipal COAs should typically have 500-2000 accounts depending on size)
- Inactive account percentages (should be <10%)
- Review frequency (should be every 2-3 years)
- State-specific compliance requirements
"""

    user_prompt = f"""Analyze this COA structure:

- Total GL accounts: {account_count}
- Last comprehensive review: {last_review}
- Inactive accounts: {inactive_percentage}%

What are the key findings and recommendations?"""

    response = await call_claude(system_prompt, user_prompt, max_tokens=2048)

    if not response:
        return None

    try:
        import json
        return json.loads(response)
    except:
        return {"summary": response, "findings": []}


async def analyze_pay_codes(
    pay_codes_by_category: Dict[str, list],
    state: str,
    retirement_system: str
) -> Optional[Dict[str, Any]]:
    """
    Analyze pay code structure for consolidation opportunities and compliance.

    Args:
        pay_codes_by_category: Dict of pay codes organized by category
        state: User's state
        retirement_system: User's retirement system

    Returns:
        Dict with findings about consolidation, compliance, etc.
    """
    system_prompt = f"""You are an expert payroll consultant analyzing municipal pay code structures.

The municipality is in {state} and uses {retirement_system} for retirement.

Identify:
1. Consolidation opportunities (similar pay codes that could be merged)
2. Pay codes with the same GL account (potential orphans or duplicates)
3. Compliance issues (incorrect pensionable or FLSA base status based on {state} rules)
4. Missing critical pay codes for municipal payroll

Return JSON:
{{
  "findings": [
    {{
      "severity": "critical|high|medium|low",
      "category": "consolidation|compliance|risk|missing",
      "title": "Finding title",
      "description": "Detailed description",
      "affected_codes": ["code1", "code2"],
      "recommendation": "What to do"
    }}
  ],
  "summary": "Executive summary",
  "stats": {{
    "total_codes": 0,
    "consolidation_opportunities": 0,
    "compliance_issues": 0
  }}
}}
"""

    # Format pay codes for analysis
    pay_codes_list = []
    for category, codes in pay_codes_by_category.items():
        for code in codes:
            pay_codes_list.append(
                f"- {code.get('name', 'Unknown')} ({category}): "
                f"GL {code.get('glAccount', 'N/A')}, "
                f"Calc: {code.get('calculationMethod', 'N/A')}, "
                f"Pensionable: {code.get('isPensionable', 'unsure')}, "
                f"FLSA Base: {code.get('isFlsaBase', 'unsure')}"
            )

    user_prompt = f"""Analyze these pay codes:

{chr(10).join(pay_codes_list)}

Provide findings on consolidation opportunities, compliance, and recommendations."""

    response = await call_claude(system_prompt, user_prompt, max_tokens=3072)

    if not response:
        return None

    try:
        import json
        return json.loads(response)
    except:
        return {"summary": response, "findings": [], "stats": {}}
