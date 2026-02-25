"""
Notification System

Sends email alerts to users when new leads are discovered in their territories.
Supports immediate alerts for hot/urgent leads and batched daily digests.
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import os

logger = logging.getLogger(__name__)

# Email configuration
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "Municipal Intel <alerts@govtechdiagnostic.com>")
APP_URL = os.getenv("APP_URL", "https://govtechdiagnostic.com")


def format_urgency_badge(urgency_score: int) -> str:
    """Generate HTML badge for urgency score."""
    if urgency_score >= 80:
        color = "#dc2626"  # red
        label = "CRITICAL"
    elif urgency_score >= 60:
        color = "#ea580c"  # orange
        label = "HIGH"
    elif urgency_score >= 40:
        color = "#f59e0b"  # amber
        label = "MEDIUM"
    else:
        color = "#6b7280"  # gray
        label = "LOW"

    return f'<span style="background-color: {color}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">{label}</span>'


def format_lead_type_badge(lead_type: str) -> str:
    """Generate HTML badge for lead type."""
    colors = {
        "hot": "#dc2626",
        "warm": "#f59e0b",
        "cold": "#3b82f6"
    }
    return f'<span style="background-color: {colors.get(lead_type, "#6b7280")}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">{lead_type.upper()}</span>'


def format_deadline_warning(days_until_deadline: Optional[int]) -> str:
    """Generate HTML warning for approaching deadlines."""
    if days_until_deadline is None:
        return ""

    if days_until_deadline <= 7:
        return f'<div style="background-color: #fef2f2; border-left: 4px solid #dc2626; padding: 12px; margin: 8px 0;"><strong>⏰ URGENT:</strong> Deadline in {days_until_deadline} days!</div>'
    elif days_until_deadline <= 30:
        return f'<div style="background-color: #fffbeb; border-left: 4px solid #f59e0b; padding: 12px; margin: 8px 0;"><strong>📅 Deadline:</strong> {days_until_deadline} days remaining</div>'
    else:
        return f'<div style="background-color: #f0f9ff; border-left: 4px solid #3b82f6; padding: 12px; margin: 8px 0;"><strong>📅 Deadline:</strong> {days_until_deadline} days out</div>'


def build_lead_card_html(lead: Dict) -> str:
    """Build HTML card for a single lead."""
    deadline_warning = format_deadline_warning(lead.get("days_until_deadline"))
    urgency_badge = format_urgency_badge(lead.get("urgency_score", 0))
    lead_type_badge = format_lead_type_badge(lead.get("lead_type", "cold"))

    # Extract top signals
    signals = lead.get("signal_matches", {})
    signal_list = ""
    if signals:
        signal_items = []
        for signal_type, signal_data in list(signals.items())[:3]:
            keyword = signal_data.get("keyword", "")
            signal_items.append(f"<li><strong>{signal_type.replace('_', ' ').title()}:</strong> {keyword}</li>")
        signal_list = "<ul style='margin: 8px 0; padding-left: 20px;'>" + "".join(signal_items) + "</ul>"

    decision_stage = lead.get("decision_stage", "unknown")
    if decision_stage != "unknown":
        decision_stage_html = f"<p style='margin: 4px 0;'><strong>Decision Stage:</strong> {decision_stage.replace('_', ' ').title()}</p>"
    else:
        decision_stage_html = ""

    return f"""
    <div style="border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; margin: 16px 0; background-color: #ffffff;">
        <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 8px;">
            <h3 style="margin: 0; color: #111827; font-size: 18px;">{lead.get("municipality", "Unknown")}, {lead.get("state", "??")}</h3>
            <div>{lead_type_badge} {urgency_badge}</div>
        </div>

        {deadline_warning}

        <p style="margin: 8px 0; color: #6b7280; font-size: 14px;">{lead.get("title", "Meeting Document")}</p>

        <div style="margin: 12px 0;">
            <p style="margin: 4px 0;"><strong>Relevance Score:</strong> {lead.get("relevance_score", 0):.1f}/100</p>
            <p style="margin: 4px 0;"><strong>Source:</strong> {lead.get("source_type", "meeting_minutes").replace('_', ' ').title()}</p>
            {decision_stage_html}
        </div>

        {signal_list}

        <div style="margin-top: 12px;">
            <a href="{APP_URL}/scanner/leads/{lead.get('id')}" style="display: inline-block; background-color: #2563eb; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px; font-size: 14px; margin-right: 8px;">View Details</a>
            <a href="{lead.get('url')}" style="display: inline-block; background-color: #6b7280; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px; font-size: 14px;">Source Document</a>
        </div>
    </div>
    """


async def send_hot_lead_alert(user_email: str, leads: List[Dict], territory_states: List[str] = None):
    """
    Send immediate email alert for hot/urgent leads.

    Triggered when:
    - Lead type is "hot"
    - OR urgency_score >= 60
    - AND lead is in user's territory
    """
    if not leads:
        return

    try:
        import resend
        resend.api_key = RESEND_API_KEY

        # Sort by urgency score descending
        sorted_leads = sorted(leads, key=lambda l: l.get("urgency_score", 0), reverse=True)

        # Build lead cards
        lead_cards = "\n".join([build_lead_card_html(lead) for lead in sorted_leads[:5]])

        # Additional leads message
        additional_msg = ""
        if len(leads) > 5:
            additional_msg = f"""
            <div style="background-color: #f9fafb; padding: 16px; border-radius: 8px; margin: 16px 0; text-align: center;">
                <p style="margin: 0; color: #6b7280;">+ {len(leads) - 5} more leads</p>
                <a href="{APP_URL}/scanner?urgent_only=true" style="color: #2563eb; text-decoration: none; font-weight: 500;">View all urgent leads →</a>
            </div>
            """

        territory_info = ""
        if territory_states:
            territory_info = f"<p style='color: #6b7280; margin: 8px 0;'>Filtered to your territories: {', '.join(territory_states)}</p>"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #111827; max-width: 600px; margin: 0 auto; padding: 20px;">

            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 24px; border-radius: 8px 8px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 24px;">🔥 Hot Leads Alert</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 8px 0 0 0; font-size: 16px;">{len(leads)} new urgent {('lead' if len(leads) == 1 else 'leads')} detected</p>
            </div>

            <div style="background-color: #ffffff; padding: 24px; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 8px 8px;">
                <p style="margin: 0 0 16px 0; font-size: 16px; color: #374151;">
                    We've detected {len(leads)} high-priority procurement {('signal' if len(leads) == 1 else 'signals')} in municipalities within your territory.
                </p>

                {territory_info}

                {lead_cards}

                {additional_msg}

                <div style="background-color: #f0f9ff; border-left: 4px solid #2563eb; padding: 16px; margin: 24px 0;">
                    <p style="margin: 0; color: #1e40af; font-size: 14px;">
                        <strong>💡 Pro Tip:</strong> Leads with deadlines under 7 days have the highest urgency. Reach out immediately to maximize your chances.
                    </p>
                </div>

                <div style="text-align: center; margin-top: 24px; padding-top: 24px; border-top: 1px solid #e5e7eb;">
                    <a href="{APP_URL}/scanner" style="display: inline-block; background-color: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 500; font-size: 16px;">Go to Scanner Dashboard</a>
                </div>
            </div>

            <div style="text-align: center; margin-top: 24px; color: #6b7280; font-size: 12px;">
                <p>You're receiving this because you have alert notifications enabled.</p>
                <p><a href="{APP_URL}/settings/notifications" style="color: #6b7280;">Manage notification preferences</a></p>
            </div>

        </body>
        </html>
        """

        params = {
            "from": RESEND_FROM_EMAIL,
            "to": [user_email],
            "subject": f"🔥 {len(leads)} Hot Lead{'s' if len(leads) > 1 else ''} in Your Territory",
            "html": html_body,
        }

        response = resend.Emails.send(params)
        logger.info(f"Sent hot lead alert to {user_email}: {len(leads)} leads (email_id: {response.get('id')})")
        return response

    except Exception as e:
        logger.error(f"Failed to send hot lead alert to {user_email}: {e}")
        return None


async def send_daily_digest(user_email: str, leads_summary: Dict, territory_states: List[str] = None):
    """
    Send daily digest of all new leads (not just urgent ones).

    Summary includes:
    - Total leads by type (hot/warm/cold)
    - Top 5 leads by relevance score
    - Deadline summary (how many deadlines this week/month)
    """
    if not leads_summary or leads_summary.get("total_leads", 0) == 0:
        return

    try:
        import resend
        resend.api_key = RESEND_API_KEY

        total = leads_summary.get("total_leads", 0)
        hot = leads_summary.get("hot_leads", 0)
        warm = leads_summary.get("warm_leads", 0)
        cold = leads_summary.get("cold_leads", 0)
        urgent = leads_summary.get("urgent_leads", 0)
        top_leads = leads_summary.get("top_leads", [])

        # Build summary stats
        stats_html = f"""
        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin: 24px 0;">
            <div style="background-color: #fef2f2; padding: 16px; border-radius: 8px; border-left: 4px solid #dc2626;">
                <div style="font-size: 32px; font-weight: bold; color: #dc2626;">{hot}</div>
                <div style="color: #991b1b; font-size: 14px;">Hot Leads</div>
            </div>
            <div style="background-color: #fffbeb; padding: 16px; border-radius: 8px; border-left: 4px solid #f59e0b;">
                <div style="font-size: 32px; font-weight: bold; color: #f59e0b;">{warm}</div>
                <div style="color: #92400e; font-size: 14px;">Warm Leads</div>
            </div>
            <div style="background-color: #fef2f2; padding: 16px; border-radius: 8px; border-left: 4px solid #ea580c;">
                <div style="font-size: 32px; font-weight: bold; color: #ea580c;">{urgent}</div>
                <div style="color: #9a3412; font-size: 14px;">Urgent (Deadlines)</div>
            </div>
            <div style="background-color: #eff6ff; padding: 16px; border-radius: 8px; border-left: 4px solid #3b82f6;">
                <div style="font-size: 32px; font-weight: bold; color: #3b82f6;">{cold}</div>
                <div style="color: #1e40af; font-size: 14px;">Cold Leads</div>
            </div>
        </div>
        """

        # Build top leads section
        top_leads_html = ""
        if top_leads:
            cards = "\n".join([build_lead_card_html(lead) for lead in top_leads[:5]])
            top_leads_html = f"""
            <h2 style="color: #111827; margin: 32px 0 16px 0;">Top Leads</h2>
            {cards}
            """

        territory_info = ""
        if territory_states:
            territory_info = f"<p style='color: #6b7280; margin: 8px 0 16px 0;'>Territory: {', '.join(territory_states)}</p>"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #111827; max-width: 600px; margin: 0 auto; padding: 20px;">

            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 24px; border-radius: 8px 8px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 24px;">📊 Daily Lead Digest</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 8px 0 0 0; font-size: 16px;">{datetime.now().strftime("%B %d, %Y")}</p>
            </div>

            <div style="background-color: #ffffff; padding: 24px; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 8px 8px;">
                <p style="margin: 0 0 8px 0; font-size: 18px; color: #374151; font-weight: 500;">
                    {total} new {('lead' if total == 1 else 'leads')} discovered in the last 24 hours
                </p>

                {territory_info}

                {stats_html}

                {top_leads_html}

                <div style="text-align: center; margin-top: 32px; padding-top: 24px; border-top: 1px solid #e5e7eb;">
                    <a href="{APP_URL}/scanner" style="display: inline-block; background-color: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 500; font-size: 16px;">View All Leads</a>
                </div>
            </div>

            <div style="text-align: center; margin-top: 24px; color: #6b7280; font-size: 12px;">
                <p>Daily digest · Municipal Intel</p>
                <p><a href="{APP_URL}/settings/notifications" style="color: #6b7280;">Manage preferences</a></p>
            </div>

        </body>
        </html>
        """

        params = {
            "from": RESEND_FROM_EMAIL,
            "to": [user_email],
            "subject": f"📊 Daily Digest: {total} New Lead{'s' if total > 1 else ''} ({hot} Hot, {urgent} Urgent)",
            "html": html_body,
        }

        response = resend.Emails.send(params)
        logger.info(f"Sent daily digest to {user_email}: {total} leads (email_id: {response.get('id')})")
        return response

    except Exception as e:
        logger.error(f"Failed to send daily digest to {user_email}: {e}")
        return None


async def send_weekly_digest(user_email: str, weekly_summary: Dict, territory_states: List[str] = None):
    """
    Send comprehensive weekly digest with trends and insights.

    Summary includes:
    - Weekly totals by lead type
    - Week-over-week trends
    - Top 10 leads by relevance
    - Competitor intelligence summary
    - Territory breakdown
    - Deadline urgency overview
    - Action items for the week
    """
    if not weekly_summary or weekly_summary.get("total_leads", 0) == 0:
        return

    try:
        import resend
        resend.api_key = RESEND_API_KEY

        total = weekly_summary.get("total_leads", 0)
        hot = weekly_summary.get("hot_leads", 0)
        warm = weekly_summary.get("warm_leads", 0)
        cold = weekly_summary.get("cold_leads", 0)
        urgent = weekly_summary.get("urgent_leads", 0)
        top_leads = weekly_summary.get("top_leads", [])

        # Trends
        prev_week_total = weekly_summary.get("prev_week_total", 0)
        trend_direction = "📈" if total > prev_week_total else "📉" if total < prev_week_total else "➡️"
        trend_pct = round(((total - prev_week_total) / prev_week_total * 100)) if prev_week_total > 0 else 0
        trend_text = f"{abs(trend_pct)}% {'increase' if total > prev_week_total else 'decrease'}" if trend_pct != 0 else "no change"

        # Competitor insights
        competitor_summary = weekly_summary.get("competitor_summary", {})
        total_competitors = competitor_summary.get("total_competitors", 0)
        top_competitors = competitor_summary.get("top_competitors", [])  # [(vendor, count), ...]

        # Territory breakdown
        territory_breakdown = weekly_summary.get("territory_breakdown", {})  # {state: count}

        # Deadline urgency
        critical_deadlines = weekly_summary.get("critical_deadlines", 0)  # < 7 days
        approaching_deadlines = weekly_summary.get("approaching_deadlines", 0)  # 7-30 days

        # Build weekly stats card
        stats_html = f"""
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 24px; border-radius: 12px; margin: 24px 0;">
            <div style="text-align: center; color: white; margin-bottom: 20px;">
                <div style="font-size: 48px; font-weight: bold;">{total}</div>
                <div style="font-size: 18px; opacity: 0.9;">New Leads This Week</div>
                <div style="font-size: 14px; opacity: 0.8; margin-top: 8px;">{trend_direction} {trend_text} vs. last week</div>
            </div>

            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;">
                <div style="background: rgba(255,255,255,0.2); padding: 12px; border-radius: 8px; text-align: center;">
                    <div style="font-size: 28px; font-weight: bold; color: white;">{hot}</div>
                    <div style="font-size: 12px; color: rgba(255,255,255,0.9);">Hot</div>
                </div>
                <div style="background: rgba(255,255,255,0.2); padding: 12px; border-radius: 8px; text-align: center;">
                    <div style="font-size: 28px; font-weight: bold; color: white;">{warm}</div>
                    <div style="font-size: 12px; color: rgba(255,255,255,0.9);">Warm</div>
                </div>
                <div style="background: rgba(255,255,255,0.2); padding: 12px; border-radius: 8px; text-align: center;">
                    <div style="font-size: 28px; font-weight: bold; color: white;">{cold}</div>
                    <div style="font-size: 12px; color: rgba(255,255,255,0.9);">Cold</div>
                </div>
            </div>
        </div>
        """

        # Urgency alert section
        urgency_html = ""
        if critical_deadlines > 0 or approaching_deadlines > 0:
            urgency_html = f"""
            <div style="background-color: #fef2f2; border-left: 4px solid #dc2626; padding: 16px; margin: 24px 0; border-radius: 4px;">
                <h3 style="margin: 0 0 8px 0; color: #dc2626; font-size: 16px;">⏰ Deadline Urgency</h3>
                <p style="margin: 0; color: #991b1b;">
                    <strong>{critical_deadlines}</strong> lead{'s' if critical_deadlines != 1 else ''} with critical deadlines (< 7 days)<br>
                    <strong>{approaching_deadlines}</strong> lead{'s' if approaching_deadlines != 1 else ''} with approaching deadlines (7-30 days)
                </p>
            </div>
            """

        # Competitor intelligence section
        competitor_html = ""
        if total_competitors > 0:
            competitor_items = "".join([
                f"<li style='margin: 4px 0;'>{vendor}: {count} mention{'s' if count > 1 else ''}</li>"
                for vendor, count in top_competitors[:5]
            ])
            competitor_html = f"""
            <div style="background-color: #f0f9ff; border-left: 4px solid #2563eb; padding: 16px; margin: 24px 0; border-radius: 4px;">
                <h3 style="margin: 0 0 8px 0; color: #1e40af; font-size: 16px;">🎯 Competitive Intelligence</h3>
                <p style="margin: 0 0 8px 0; color: #1e3a8a;"><strong>{total_competitors}</strong> competitor{'s' if total_competitors > 1 else ''} mentioned this week:</p>
                <ul style="margin: 0; padding-left: 20px; color: #1e40af;">{competitor_items}</ul>
            </div>
            """

        # Territory breakdown section
        territory_html = ""
        if territory_breakdown:
            territory_items = "".join([
                f"<div style='display: flex; justify-content: space-between; margin: 4px 0;'><span>{state}</span><strong>{count}</strong></div>"
                for state, count in sorted(territory_breakdown.items(), key=lambda x: x[1], reverse=True)[:5]
            ])
            territory_html = f"""
            <div style="background-color: #f0fdf4; border-left: 4px solid #10b981; padding: 16px; margin: 24px 0; border-radius: 4px;">
                <h3 style="margin: 0 0 8px 0; color: #065f46; font-size: 16px;">📍 Territory Activity</h3>
                <div style="color: #065f46;">{territory_items}</div>
            </div>
            """

        # Top leads section
        top_leads_html = ""
        if top_leads:
            cards = "\n".join([build_lead_card_html(lead) for lead in top_leads[:10]])
            top_leads_html = f"""
            <h2 style="color: #111827; margin: 32px 0 16px 0; font-size: 20px;">🔥 Top Leads This Week</h2>
            {cards}
            """

        # Action items
        action_items = []
        if critical_deadlines > 0:
            action_items.append(f"⚡ <strong>URGENT:</strong> Review {critical_deadlines} lead{'s' if critical_deadlines > 1 else ''} with critical deadlines")
        if hot > 0:
            action_items.append(f"🔥 Follow up on {hot} hot lead{'s' if hot > 1 else ''}")
        if total_competitors > 0:
            action_items.append(f"🎯 Review competitive positioning for {total_competitors} competitor mention{'s' if total_competitors > 1 else ''}")

        action_items_html = ""
        if action_items:
            action_list = "".join([f"<li style='margin: 8px 0;'>{item}</li>" for item in action_items])
            action_items_html = f"""
            <div style="background-color: #fffbeb; border-left: 4px solid #f59e0b; padding: 16px; margin: 24px 0; border-radius: 4px;">
                <h3 style="margin: 0 0 8px 0; color: #92400e; font-size: 16px;">✅ Action Items</h3>
                <ul style="margin: 0; padding-left: 20px; color: #78350f;">{action_list}</ul>
            </div>
            """

        territory_info = ""
        if territory_states:
            territory_info = f"<p style='color: #6b7280; margin: 8px 0 16px 0; text-align: center;'>Your territories: {', '.join(territory_states)}</p>"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #111827; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9fafb;">

            <div style="background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 32px; text-align: center;">
                    <h1 style="color: white; margin: 0; font-size: 28px;">📊 Weekly Intelligence Report</h1>
                    <p style="color: rgba(255,255,255,0.9); margin: 8px 0 0 0; font-size: 16px;">{datetime.now().strftime("%B %d, %Y")}</p>
                    {territory_info}
                </div>

                <div style="padding: 24px;">
                    {stats_html}

                    {urgency_html}

                    {competitor_html}

                    {territory_html}

                    {action_items_html}

                    {top_leads_html}

                    <div style="text-align: center; margin-top: 32px; padding-top: 24px; border-top: 1px solid #e5e7eb;">
                        <a href="{APP_URL}/scanner" style="display: inline-block; background-color: #2563eb; color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px; box-shadow: 0 2px 4px rgba(37,99,235,0.2);">View All Leads →</a>
                    </div>
                </div>
            </div>

            <div style="text-align: center; margin-top: 24px; color: #6b7280; font-size: 12px;">
                <p>Weekly digest · Municipal Intel</p>
                <p><a href="{APP_URL}/settings/notifications" style="color: #6b7280; text-decoration: none;">Manage notification preferences</a></p>
            </div>

        </body>
        </html>
        """

        params = {
            "from": RESEND_FROM_EMAIL,
            "to": [user_email],
            "subject": f"📊 Weekly Report: {total} Leads ({hot} Hot, {urgent} Urgent) • {trend_direction} {trend_text}",
            "html": html_body,
        }

        response = resend.Emails.send(params)
        logger.info(f"Sent weekly digest to {user_email}: {total} leads, {hot} hot (email_id: {response.get('id')})")
        return response

    except Exception as e:
        logger.error(f"Failed to send weekly digest to {user_email}: {e}")
        return None
