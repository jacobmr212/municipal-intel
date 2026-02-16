# 🏛️ Municipal Intel

**Government ERP Lead Intelligence Platform**

Automatically discovers and scans municipal meeting minutes for signals related to ERP software procurement, vendor evaluations, system pain points, and budget discussions. Generates actionable intelligence reports with lead scoring and classification.

Built to replace expensive third-party monitoring services that charge thousands of dollars to manually read town hall meeting notes.

![Python](https://img.shields.io/badge/python-3.10+-blue)
![Streamlit](https://img.shields.io/badge/streamlit-1.31+-red)
![License](https://img.shields.io/badge/license-MIT-green)

---

## How It Works

1. **Select a State** — Pick any US state from the dropdown
2. **Auto-Discovery** — The tool probes each municipality's website to find meeting minutes pages (CivicPlus, Granicus, standard HTML)
3. **Scrape** — Extracts text from HTML pages and PDF documents
4. **Analyze** — Scores each document against 5 weighted signal categories
5. **Report** — Generates a detailed HTML dashboard with lead cards, scores, and recommended actions

### Signal Categories

| Signal | Weight | What It Catches |
|--------|--------|-----------------|
| 🔴 Direct Mention | 10 | Caselle or its products mentioned by name |
| 🟠 Competitor | 8 | Tyler Technologies, Munis, CentralSquare, BS&A, etc. |
| 🟡 ERP/Software | 7 | ERP, fund accounting, payroll system, financial software |
| 🔵 Budget/Procurement | 6 | RFP, vendor evaluation, contract renewal, technology budget |
| ⚪ Pain Point | 5 | Legacy system, audit findings, manual processes, system outages |

### Lead Classification

- **🔥 Hot** — Direct Caselle mention, or competitor + active procurement
- **🟡 Warm** — ERP or budget discussion, or competitor mention alone
- **🔵 Cold** — System pain signals only

---

## Quick Start

### Local Development

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/municipal-intel.git
cd municipal-intel

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

The app will open at `http://localhost:8501`.

### Deploy to Streamlit Cloud (Free)

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repo
4. Set `app.py` as the main file
5. Click Deploy

Your app will be live at `https://your-app.streamlit.app` within minutes.

---

## Configuration

### Municipality Database

The `data/municipalities.json` file contains cities organized by state with population data and website domains. The database is pre-loaded with:

- **Full coverage**: UT, ID, WY, MT, CO, NV, NM, ND, SD, OR, WA (Caselle core territory)
- **Major cities**: All other US states

To add a municipality:

```json
{
  "name": "Your City",
  "population": 25000,
  "domain": "yourcity.gov"
}
```

### AI-Enhanced Analysis (Optional)

Toggle "AI-Enhanced Analysis" in the sidebar to get Claude-powered sales briefs on hot/warm leads. Requires:

```bash
export ANTHROPIC_API_KEY="your-key-here"
```

Or add it as a secret in Streamlit Cloud settings.

### Signal Keywords

Edit `src/signals.py` to customize keyword lists, weights, and lead classification rules.

---

## Project Structure

```
municipal-intel/
├── app.py                  # Streamlit web application
├── requirements.txt        # Python dependencies
├── data/
│   └── municipalities.json # Municipality database (by state)
├── src/
│   ├── signals.py          # Signal definitions & lead classification
│   ├── discovery.py        # Auto-discovery of meeting minutes pages
│   ├── scraper.py          # Web scraping engine (HTML + PDF)
│   ├── analyzer.py         # Document analysis & scoring
│   └── reporter.py         # HTML/JSON report generation
├── reports/                # Generated reports (gitignored)
└── .streamlit/
    └── config.toml         # Streamlit theme configuration
```

---

## Scaling & Next Steps

- **CRM Integration** — Export JSON data to Salesforce, HubSpot, or Pipedrive
- **Slack/Email Alerts** — Webhook for real-time hot lead notifications
- **Scheduled Scans** — Deploy as a cron job for daily/weekly automated monitoring
- **Historical Tracking** — Store results in a database to track trends over time
- **More Platforms** — Add support for Legistar, BoardDocs, and other municipal platforms

---

## License

MIT
