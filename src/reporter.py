"""
Report Generator
Produces detailed HTML intelligence reports and JSON exports.
"""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path

from jinja2 import Template

logger = logging.getLogger(__name__)


REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Municipal Intel Report — {{ state_name }} — {{ generated_at }}</title>
<style>
:root {
  --bg: #09090B; --card: #111113; --sidebar: #1A1A1F; --surface: #0F0F11;
  --border: #1F1F23; --border-hover: #2F2F33;
  --text: #E5E7EB; --text-dim: #D1D5DB; --muted: #9CA3AF; --subtle: #6B7280;
  --primary: #4F6AFF; --primary-dim: rgba(79,106,255,0.08);
  --hot: #DC3545; --hot-dim: rgba(220,53,69,0.08);
  --warm: #D97706; --warm-dim: rgba(217,119,6,0.08);
  --cold: #3B82F6; --cold-dim: rgba(59,130,246,0.08);
  --success: #22C55E;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica', 'Arial', sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.65;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1100px; margin: 0 auto; padding: 40px 24px; }

/* Top Accent Bar */
body::before {
  content: "";
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, #4F6AFF 0%, #6B7FFF 100%);
  z-index: 9999;
}

/* Header */
.header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  padding-bottom: 24px;
  margin-bottom: 32px;
  border-bottom: 1px solid var(--border);
}
.header h1 {
  font-size: 32px;
  font-weight: 700;
  letter-spacing: -0.03em;
  color: var(--text);
}
.header h1 em {
  font-style: normal;
  color: var(--primary);
  font-weight: 800;
}
.header .sub {
  font-size: 14px;
  color: var(--subtle);
  margin-top: 6px;
  font-weight: 400;
}
.header .right { text-align: right; }
.header .right .big {
  font-size: 24px;
  font-weight: 700;
  color: var(--text);
}

/* Stats */
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 16px;
  margin-bottom: 32px;
}
.stat {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px;
  position: relative;
}
.stat::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  border-radius: 8px 0 0 8px;
}
.stat.total::before { background: var(--primary); }
.stat.hot::before { background: var(--hot); }
.stat.warm::before { background: var(--warm); }
.stat.cold::before { background: var(--cold); }
.stat.docs::before { background: var(--success); }
.stat.munis::before { background: var(--muted); }

.stat .lab {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--subtle);
  margin-bottom: 8px;
  font-weight: 500;
}
.stat .val {
  font-size: 32px;
  font-weight: 700;
  color: var(--text);
  line-height: 1;
}

/* Filters */
.filters {
  display: inline-flex;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px;
  gap: 4px;
  margin-bottom: 24px;
}
.fbtn {
  padding: 6px 14px;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.15s ease;
}
.fbtn:hover { color: var(--text); }
.fbtn.on {
  background: var(--sidebar);
  color: var(--text);
}

/* Lead Cards */
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 12px;
  position: relative;
  transition: border-color 0.2s ease;
}
.card::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  border-radius: 8px 0 0 8px;
}
.card.hot::before { background: var(--hot); }
.card.warm::before { background: var(--warm); }
.card.cold::before { background: var(--cold); }
.card:hover { border-color: var(--border-hover); }

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 14px;
}
.card-title {
  font-size: 17px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.3;
}
.card-meta {
  font-size: 13px;
  color: var(--subtle);
  margin-top: 4px;
  line-height: 1.4;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.badge::before {
  content: "";
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.badge.hot { color: var(--hot); background: var(--hot-dim); }
.badge.hot::before { background: var(--hot); }
.badge.warm { color: var(--warm); background: var(--warm-dim); }
.badge.warm::before { background: var(--warm); }
.badge.cold { color: var(--cold); background: var(--cold-dim); }
.badge.cold::before { background: var(--cold); }

.score {
  font-size: 13px;
  color: var(--subtle);
  margin-top: 6px;
  text-align: right;
}
.score .number {
  font-weight: 600;
  color: var(--muted);
}

.action {
  background: var(--surface);
  border-left: 3px solid var(--primary);
  border-radius: 4px;
  padding: 12px 16px;
  font-size: 14px;
  color: var(--text-dim);
  margin: 12px 0;
  line-height: 1.5;
}

.tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin: 12px 0;
}
.tag {
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 11px;
  background: var(--sidebar);
  color: var(--muted);
  border: 1px solid var(--border);
  font-weight: 500;
}

.ai-box {
  margin-top: 12px;
  padding: 14px 16px;
  background: var(--primary-dim);
  border: 1px solid rgba(79,106,255,0.2);
  border-radius: 6px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-dim);
}
.ai-lab {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--primary);
  margin-bottom: 8px;
  font-weight: 600;
}

.ctx-btn {
  background: none;
  border: none;
  color: var(--primary);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  padding: 4px 0;
  margin-top: 8px;
}
.ctx-btn:hover { color: #6B7FFF; }
.ctx-hidden { display: none; }
.ctx {
  font-size: 13px;
  color: var(--muted);
  background: var(--surface);
  border-radius: 6px;
  padding: 12px 16px;
  margin-top: 8px;
  line-height: 1.6;
  border: 1px solid var(--border);
}
.ctx strong { color: var(--text); }

.src {
  display: inline-block;
  margin-top: 12px;
  color: var(--primary);
  text-decoration: none;
  font-size: 13px;
  font-weight: 500;
}
.src:hover {
  color: #6B7FFF;
  text-decoration: underline;
}

.empty {
  text-align: center;
  padding: 80px 40px;
  color: var(--subtle);
}
.empty h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--muted);
  margin-bottom: 8px;
}
.empty p {
  font-size: 14px;
  line-height: 1.6;
  max-width: 500px;
  margin: 0 auto;
}

footer {
  text-align: center;
  padding: 32px 24px;
  color: var(--subtle);
  font-size: 12px;
  border-top: 1px solid var(--border);
  margin-top: 48px;
}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <div>
      <h1>Municipal <em>Intel</em></h1>
      <div class="sub">{{ state_name }} — Generated {{ generated_at }}</div>
    </div>
    <div class="right">
      <div class="big">{{ total_leads }} Lead{{ 's' if total_leads != 1 else '' }}</div>
      <div class="sub">{{ municipalities_scanned }} municipalities &middot; {{ documents_analyzed }} documents</div>
    </div>
  </div>

  <div class="stats">
    <div class="stat total"><div class="lab">Total Leads</div><div class="val">{{ total_leads }}</div></div>
    <div class="stat hot"><div class="lab">Hot</div><div class="val">{{ hot_count }}</div></div>
    <div class="stat warm"><div class="lab">Warm</div><div class="val">{{ warm_count }}</div></div>
    <div class="stat cold"><div class="lab">Cold</div><div class="val">{{ cold_count }}</div></div>
    <div class="stat docs"><div class="lab">Documents</div><div class="val">{{ documents_analyzed }}</div></div>
    <div class="stat munis"><div class="lab">Sources</div><div class="val">{{ sources_found }}</div></div>
  </div>

  <div class="filters">
    <button class="fbtn on" onclick="filt('all')">All</button>
    <button class="fbtn" onclick="filt('hot')">Hot ({{ hot_count }})</button>
    <button class="fbtn" onclick="filt('warm')">Warm ({{ warm_count }})</button>
    <button class="fbtn" onclick="filt('cold')">Cold ({{ cold_count }})</button>
  </div>

  <div id="cards">
  {% for l in leads %}
  <div class="card {{ l.lead_type }}" data-t="{{ l.lead_type }}">
    <div class="card-top">
      <div>
        <div class="card-title">{{ l.municipality }}, {{ l.state }}</div>
        <div class="card-meta">{{ l.title }} &middot; {{ l.date }}{% if l.population %} &middot; Pop. {{ "{:,}".format(l.population) }}{% endif %}</div>
      </div>
      <div style="text-align:right">
        <span class="badge {{ l.lead_type }}">{{ l.lead_type }}</span>
        <div class="score">Score: <span class="number">{{ l.relevance_score }}</span></div>
      </div>
    </div>
    <div class="action">{{ l.recommended_action }}</div>
    <div class="tags">
      {% for sig in l.signal_labels %}<span class="tag">{{ sig }}</span>{% endfor %}
    </div>
    {% if l.llm_analysis %}
    <div class="ai-box"><div class="ai-lab">AI Analysis</div>{{ l.llm_analysis }}</div>
    {% endif %}
    <button class="ctx-btn" onclick="tog(this)">View {{ l.contexts|length }} match context(s)</button>
    <div class="ctx-hidden">
      {% for c in l.contexts %}
      <div class="ctx"><strong>{{ c.keyword }}</strong> <span class="tag">{{ c.signal_label }}</span><br>{{ c.context }}</div>
      {% endfor %}
    </div>
    <a class="src" href="{{ l.url }}" target="_blank" rel="noopener">View source document</a>
  </div>
  {% endfor %}
  {% if not leads %}
  <div class="empty">
    <h3>No leads detected</h3>
    <p>No ERP-related signals were found in the meeting documents scanned. This could mean the municipalities' documents aren't publicly accessible in standard formats, or there weren't relevant discussions in recent documents.</p>
  </div>
  {% endif %}
  </div>

  <footer>Municipal Intel — Government ERP Lead Intelligence</footer>
</div>
<script>
function filt(t){
  document.querySelectorAll('.card').forEach(c=>c.style.display=(t==='all'||c.dataset.t===t)?'block':'none');
  document.querySelectorAll('.fbtn').forEach(b=>b.classList.remove('on'));
  event.target.classList.add('on');
}
function tog(b){
  const d=b.nextElementSibling;
  const showing=!d.classList.contains('ctx-hidden');
  d.classList.toggle('ctx-hidden');
  b.textContent=showing?b.textContent.replace('Hide','View'):b.textContent.replace('View','Hide');
}
</script>
</body>
</html>"""


class ReportGenerator:
    """Generates intelligence reports."""

    def __init__(self, report_dir: str = "./reports"):
        self.report_dir = Path(report_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def generate_html(self, results: list, state_name: str, state_abbr: str,
                       total_docs: int, total_munis: int, sources_found: int) -> str:
        """Generate HTML dashboard report. Returns filepath."""
        leads_data = []
        for r in results:
            # Deduplicate contexts
            seen = set()
            contexts = []
            for m in r.signal_matches:
                if m.keyword not in seen:
                    seen.add(m.keyword)
                    contexts.append({
                        "keyword": m.keyword,
                        "signal_label": m.signal_label,
                        "context": m.context,
                    })

            leads_data.append({
                "municipality": r.municipality,
                "state": r.state,
                "population": r.population,
                "title": r.title,
                "url": r.url,
                "date": r.date or "Unknown",
                "relevance_score": r.relevance_score,
                "lead_type": r.lead_type,
                "recommended_action": r.recommended_action,
                "signal_labels": r.signal_labels_found,
                "contexts": contexts[:6],
                "llm_analysis": r.llm_analysis,
            })

        template = Template(REPORT_TEMPLATE)
        html = template.render(
            state_name=state_name,
            generated_at=datetime.now().strftime("%B %d, %Y at %I:%M %p"),
            municipalities_scanned=total_munis,
            documents_analyzed=total_docs,
            sources_found=sources_found,
            total_leads=len(results),
            hot_count=sum(1 for r in results if r.lead_type == "hot"),
            warm_count=sum(1 for r in results if r.lead_type == "warm"),
            cold_count=sum(1 for r in results if r.lead_type == "cold"),
            leads=leads_data,
        )

        filename = f"intel_{state_abbr}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = self.report_dir / filename
        filepath.write_text(html)
        logger.info(f"Report saved: {filepath}")
        return str(filepath)

    def generate_json(self, results: list, state_name: str, state_abbr: str,
                       total_docs: int, total_munis: int, sources_found: int) -> str:
        """Generate JSON report. Returns filepath."""
        data = {
            "generated_at": datetime.now().isoformat(),
            "state": {"name": state_name, "abbreviation": state_abbr},
            "scan_stats": {
                "municipalities_scanned": total_munis,
                "documents_analyzed": total_docs,
                "sources_found": sources_found,
            },
            "summary": {
                "total_leads": len(results),
                "hot": sum(1 for r in results if r.lead_type == "hot"),
                "warm": sum(1 for r in results if r.lead_type == "warm"),
                "cold": sum(1 for r in results if r.lead_type == "cold"),
            },
            "leads": [
                {
                    "municipality": r.municipality,
                    "state": r.state,
                    "population": r.population,
                    "title": r.title,
                    "url": r.url,
                    "date": r.date,
                    "relevance_score": r.relevance_score,
                    "lead_type": r.lead_type,
                    "recommended_action": r.recommended_action,
                    "signal_types": list(r.signal_types_found),
                    "match_count": r.match_count,
                    "top_keywords": list(dict.fromkeys(m.keyword for m in r.signal_matches))[:8],
                    "llm_analysis": r.llm_analysis,
                }
                for r in results
            ],
        }

        filename = f"intel_{state_abbr}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.report_dir / filename
        filepath.write_text(json.dumps(data, indent=2))
        logger.info(f"JSON report saved: {filepath}")
        return str(filepath)

    def generate_csv(self, results: list, state_name: str, state_abbr: str) -> str:
        """
        Generate CSV export with sales tracking columns.
        Returns filepath.
        """
        filename = f"intel_{state_abbr}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = self.report_dir / filename

        # Define columns for sales tracking
        fieldnames = [
            # Lead Info
            "city",
            "state",
            "population",
            "lead_type",
            "score",
            "signals_found",
            # Document Info
            "document_title",
            "document_date",
            "document_url",
            # Recommended Action
            "recommended_action",
            # Sales Tracking Columns
            "contact_name",
            "contact_title",
            "contact_email",
            "contact_phone",
            "last_contacted",
            "next_follow_up",
            "status",
            "notes",
        ]

        with open(filepath, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for r in results:
                # Get top signals
                signals = ", ".join(r.signal_labels_found[:3])

                writer.writerow({
                    # Lead Info
                    "city": r.municipality,
                    "state": r.state,
                    "population": r.population,
                    "lead_type": r.lead_type.upper(),
                    "score": r.relevance_score,
                    "signals_found": signals,
                    # Document Info
                    "document_title": r.title,
                    "document_date": r.date,
                    "document_url": r.url,
                    # Recommended Action
                    "recommended_action": r.recommended_action,
                    # Sales Tracking Columns (empty for sales team to fill)
                    "contact_name": "",
                    "contact_title": "",
                    "contact_email": "",
                    "contact_phone": "",
                    "last_contacted": "",
                    "next_follow_up": "",
                    "status": "",  # e.g., "New", "Contacted", "Qualified", "Lost"
                    "notes": "",
                })

        logger.info(f"CSV report saved: {filepath}")
        return str(filepath)
