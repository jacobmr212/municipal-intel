"""
Report Generator
Produces detailed HTML intelligence reports and JSON exports.
"""

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
  --bg: #0b0d11; --s1: #141720; --s2: #1c2030; --s3: #252a3a;
  --border: #2a3050; --text: #dee1ef; --muted: #7a809e;
  --accent: #5e8aff; --accent-dim: rgba(94,138,255,.12);
  --hot: #ff4466; --hot-bg: rgba(255,68,102,.1);
  --warm: #ffb040; --warm-bg: rgba(255,176,64,.1);
  --cold: #40b8ff; --cold-bg: rgba(64,184,255,.1);
  --green: #4cd97b;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text);line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:1100px;margin:0 auto;padding:32px 24px}

/* --- Header --- */
.header{display:flex;justify-content:space-between;align-items:flex-end;padding-bottom:28px;margin-bottom:28px;border-bottom:1px solid var(--border)}
.header h1{font-size:28px;font-weight:700;letter-spacing:-.5px}
.header h1 em{font-style:normal;color:var(--accent)}
.header .sub{font-size:13px;color:var(--muted);margin-top:4px}
.header .right{text-align:right}
.header .right .big{font-size:22px;font-weight:700;color:var(--accent)}

/* --- Stats --- */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-bottom:32px}
.stat{background:var(--s1);border:1px solid var(--border);border-radius:14px;padding:20px}
.stat .lab{font-size:11px;text-transform:uppercase;letter-spacing:1.2px;color:var(--muted);margin-bottom:2px}
.stat .val{font-size:34px;font-weight:800}
.stat.hot .val{color:var(--hot)} .stat.warm .val{color:var(--warm)}
.stat.cold .val{color:var(--cold)} .stat.total .val{color:var(--accent)}
.stat.docs .val{color:var(--green)} .stat.munis .val{color:var(--muted)}

/* --- Filters --- */
.filters{display:flex;gap:6px;margin-bottom:24px;flex-wrap:wrap}
.fbtn{padding:7px 16px;border-radius:8px;border:1px solid var(--border);background:var(--s1);color:var(--muted);cursor:pointer;font-size:13px;font-weight:500;transition:.15s}
.fbtn:hover,.fbtn.on{background:var(--s2);color:var(--text);border-color:var(--accent)}

/* --- Cards --- */
.card{background:var(--s1);border:1px solid var(--border);border-radius:14px;padding:24px;margin-bottom:14px;border-left:4px solid transparent;transition:.15s}
.card:hover{border-color:var(--accent)}
.card.hot{border-left-color:var(--hot)} .card.warm{border-left-color:var(--warm)} .card.cold{border-left-color:var(--cold)}

.card-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px}
.card-title{font-size:18px;font-weight:600}
.card-meta{font-size:13px;color:var(--muted);margin-top:3px}

.badge{display:inline-block;padding:3px 12px;border-radius:50px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px}
.badge.hot{background:var(--hot-bg);color:var(--hot)}
.badge.warm{background:var(--warm-bg);color:var(--warm)}
.badge.cold{background:var(--cold-bg);color:var(--cold)}

.bar{width:100%;height:5px;background:var(--s3);border-radius:3px;margin:10px 0;overflow:hidden}
.fill{height:100%;border-radius:3px}
.fill.hot{background:var(--hot)} .fill.warm{background:var(--warm)} .fill.cold{background:var(--cold)}

.action{background:var(--s2);border-radius:8px;padding:12px 16px;font-size:14px;margin:10px 0;border-left:3px solid var(--accent)}
.action strong{color:var(--accent)}

.tags{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}
.tag{padding:3px 10px;border-radius:6px;font-size:12px;background:var(--s2);color:var(--muted)}

.ai-box{margin-top:10px;padding:14px 16px;background:var(--accent-dim);border:1px solid rgba(94,138,255,.2);border-radius:8px;font-size:14px;line-height:1.5}
.ai-lab{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--accent);margin-bottom:6px;font-weight:600}

.ctx-btn{background:none;border:none;color:var(--accent);cursor:pointer;font-size:13px;padding:4px 0}
.ctx-hidden{display:none}
.ctx{font-size:13px;color:var(--muted);background:var(--s2);border-radius:8px;padding:12px 16px;margin-top:6px;line-height:1.5}
.ctx mark{background:rgba(94,138,255,.25);color:var(--text);padding:1px 4px;border-radius:3px}
.ctx strong{color:var(--text)}

.src{display:inline-block;margin-top:10px;color:var(--accent);text-decoration:none;font-size:13px}
.src:hover{text-decoration:underline}

.empty{text-align:center;padding:60px;color:var(--muted)}
footer{text-align:center;padding:28px;color:var(--muted);font-size:11px;border-top:1px solid var(--border);margin-top:40px}
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
    <div class="stat munis"><div class="lab">Sources Found</div><div class="val">{{ sources_found }}</div></div>
  </div>

  <div class="filters">
    <button class="fbtn on" onclick="filt('all')">All</button>
    <button class="fbtn" onclick="filt('hot')">🔥 Hot ({{ hot_count }})</button>
    <button class="fbtn" onclick="filt('warm')">🟡 Warm ({{ warm_count }})</button>
    <button class="fbtn" onclick="filt('cold')">🔵 Cold ({{ cold_count }})</button>
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
        <div class="card-meta" style="margin-top:4px">Score: {{ l.relevance_score }}</div>
      </div>
    </div>
    <div class="bar"><div class="fill {{ l.lead_type }}" style="width:{{ l.relevance_score }}%"></div></div>
    <div class="action"><strong>→</strong> {{ l.recommended_action }}</div>
    <div class="tags">
      {% for sig in l.signal_labels %}<span class="tag">{{ sig }}</span>{% endfor %}
    </div>
    {% if l.llm_analysis %}
    <div class="ai-box"><div class="ai-lab">AI Analysis</div>{{ l.llm_analysis }}</div>
    {% endif %}
    <button class="ctx-btn" onclick="tog(this)">Show {{ l.contexts|length }} match context(s) ▼</button>
    <div class="ctx-hidden">
      {% for c in l.contexts %}
      <div class="ctx"><strong>{{ c.keyword }}</strong> <span class="tag">{{ c.signal_label }}</span><br>{{ c.context }}</div>
      {% endfor %}
    </div>
    <a class="src" href="{{ l.url }}" target="_blank" rel="noopener">View source →</a>
  </div>
  {% endfor %}
  {% if not leads %}
  <div class="empty">
    <h3 style="margin-bottom:8px">No leads detected</h3>
    <p>No ERP-related signals found in the meeting documents scanned for {{ state_name }}.</p>
    <p style="margin-top:8px">This could mean the municipalities' meeting minutes aren't publicly posted in a standard format, or there simply weren't relevant discussions in recent documents.</p>
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
  if(d.classList.contains('ctx-hidden')){d.classList.remove('ctx-hidden');b.textContent=b.textContent.replace('Show','Hide').replace('▼','▲')}
  else{d.classList.add('ctx-hidden');b.textContent=b.textContent.replace('Hide','Show').replace('▲','▼')}
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
