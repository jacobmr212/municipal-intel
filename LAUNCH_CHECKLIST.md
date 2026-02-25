# 🚀 Launch Checklist - Municipal Intel Enterprise Edition

Complete step-by-step checklist to deploy and launch the enterprise platform.

---

## ✅ Pre-Launch Checklist

### Phase 1: Backend Deployment (30 minutes)

- [ ] **1.1 Push Code to GitHub**
  ```bash
  git status  # Verify all changes committed
  git push origin main  # Already done!
  ```

- [ ] **1.2 Railway Environment Variables**
  - [ ] Verify `DATABASE_URL` is set (already configured)
  - [ ] Verify `JWT_SECRET_KEY` is set (already configured)
  - [ ] Verify `RESEND_API_KEY` is set (already configured)
  - [ ] Verify `RESEND_FROM_EMAIL` is set
  - [ ] Verify `APP_URL` is set
  - [ ] **NEW**: Set `CRM_ENCRYPTION_KEY`:
    ```bash
    # Generate key
    python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

    # Set in Railway
    railway variables set CRM_ENCRYPTION_KEY="<generated-key>"
    ```
  - [ ] Optional: Set `ANTHROPIC_API_KEY` for LLM analysis

- [ ] **1.3 Update requirements.txt on Railway**
  - Railway will auto-detect the updated requirements.txt
  - New dependencies will be installed automatically:
    - simple-salesforce>=1.12.6
    - hubspot-api-client>=9.2.0
    - cryptography>=42.0.5
    - aiohttp>=3.9.0
    - pdfplumber>=0.10.0
    - playwright>=1.42.0

- [ ] **1.4 Deploy to Railway**
  - If connected to GitHub: Auto-deploy on push (already done)
  - If manual: `railway up`
  - Check logs: `railway logs`
  - Look for: "✓ Database initialized" and "Uvicorn running"

### Phase 2: Database Migrations (15 minutes)

Run all 7 migrations in order:

- [ ] **2.1 Lead Deduplication**
  ```bash
  railway run python3 migrations/001_add_lead_deduplication.py
  ```
  Expected: "✓ Migration 001 completed successfully"

- [ ] **2.2 Document Caching**
  ```bash
  railway run python3 migrations/002_add_document_caching.py
  ```
  Expected: "✓ Migration 002 completed successfully"

- [ ] **2.3 Temporal Intelligence**
  ```bash
  railway run python3 migrations/003_add_temporal_intelligence.py
  ```
  Expected: "✓ Migration 003 completed successfully"

- [ ] **2.4 Notification Preferences**
  ```bash
  railway run python3 migrations/004_add_notification_preferences.py
  ```
  Expected: "✓ Migration 004 completed successfully"

- [ ] **2.5 Lead Status Tracking**
  ```bash
  railway run python3 migrations/005_add_lead_status_tracking.py
  ```
  Expected: "✓ Migration 005 completed successfully"

- [ ] **2.6 Competitor Intelligence**
  ```bash
  railway run python3 migrations/006_add_competitor_intelligence.py
  ```
  Expected: "✓ Migration 006 completed successfully"

- [ ] **2.7 CRM Sync Tracking**
  ```bash
  railway run python3 migrations/007_add_crm_sync_tracking.py
  ```
  Expected: "✓ Migration 007 completed successfully"

### Phase 3: Testing (20 minutes)

- [ ] **3.1 Run Automated Tests**
  ```bash
  python3 test_enterprise_features.py \
    --url https://web-production-a13f5.up.railway.app \
    --email your@email.com
  ```
  - [ ] Provide JWT token when prompted
  - [ ] Verify all tests pass (✅ green checkmarks)
  - [ ] Expected: 0 failed tests

- [ ] **3.2 Manual API Testing**
  Test key endpoints manually:

  ```bash
  export TOKEN="your-jwt-token"
  export URL="https://web-production-a13f5.up.railway.app"

  # Test feed with filters
  curl "$URL/api/feed?min_urgency=60&lead_type=hot" \
    -H "Authorization: Bearer $TOKEN"

  # Test analytics
  curl "$URL/api/analytics/dashboard?days=30" \
    -H "Authorization: Bearer $TOKEN"

  # Test CRM config
  curl "$URL/api/crm/config" \
    -H "Authorization: Bearer $TOKEN"

  # Test filter options
  curl "$URL/api/feed/filter-options" \
    -H "Authorization: Bearer $TOKEN"
  ```

- [ ] **3.3 UI Smoke Test**
  - [ ] Visit https://your-app.railway.app
  - [ ] Login via magic link
  - [ ] Navigate to /scanner
  - [ ] Verify feed loads
  - [ ] Check that scanner tab works
  - [ ] Verify no console errors (F12)

### Phase 4: Enrichment (8-12 hours)

Choose your enrichment strategy:

**Option A: Local Enrichment (Recommended)**
- [ ] Run locally, writes to shared Neon database:
  ```bash
  # Top 10 states (2-3 hours)
  python3 scripts/batch_enrich.py --top 10 --workers 5

  # OR all states (8-12 hours)
  python3 scripts/batch_enrich.py --all --workers 8
  ```

**Option B: Railway Background Worker**
- [ ] Create separate Railway service
- [ ] Name: "municipal-intel-worker"
- [ ] Same `DATABASE_URL` as main app
- [ ] Start command: `python3 scripts/batch_enrich.py --all --workers 4`
- [ ] Scale down after completion

**Option C: Scheduled Enrichment**
- [ ] Add Railway Cron plugin
- [ ] Schedule: `0 2 * * 0` (2 AM every Sunday)
- [ ] Command: `python3 scripts/batch_enrich.py --top 15 --workers 4`

- [ ] **Monitor Progress**:
  ```bash
  # Check coverage
  railway run python3 scripts/improve_coverage.py --analyze

  # Expected after full enrichment:
  # - 6,400+ verified domains (95%)
  # - 7,500+ total sources
  # - 1.1 sources per city average
  ```

### Phase 5: Configuration (15 minutes)

- [ ] **5.1 Configure CRM (Optional)**

  **Salesforce**:
  ```bash
  curl -X POST https://your-app.railway.app/api/crm/config \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "provider": "salesforce",
      "credentials": {
        "username": "user@company.com",
        "password": "your-password",
        "security_token": "your-token",
        "domain": "login"
      },
      "auto_sync_hot_leads": true
    }'
  ```

  **HubSpot**:
  ```bash
  curl -X POST https://your-app.railway.app/api/crm/config \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
      "provider": "hubspot",
      "credentials": {
        "access_token": "your-private-app-token",
        "portal_id": "12345678"
      },
      "auto_sync_hot_leads": true
    }'
  ```

- [ ] **5.2 Configure Email Notifications**
  - [ ] Verify Resend sender domain is verified
  - [ ] Test hot lead alert:
    ```bash
    # Run a scan, get a hot lead, verify email arrives
    ```
  - [ ] Configure user notification preferences via UI

- [ ] **5.3 Set Up Weekly Digest (Optional)**

  **Option A: Railway Cron**
  - [ ] Add cron job: `0 18 * * 0` (6 PM Sunday)
  - [ ] Command: `curl -X POST https://your-app.railway.app/api/send-weekly-digest -H "Authorization: Bearer $ADMIN_TOKEN"`

  **Option B: External Cron (cron-job.org)**
  - [ ] Create account at cron-job.org
  - [ ] Add job: POST to `/api/send-weekly-digest`
  - [ ] Schedule: Every Sunday 6 PM
  - [ ] Add Authorization header

---

## 🎯 Launch Readiness Checks

### Technical Readiness

- [ ] ✅ All 13 phases implemented
- [ ] ✅ 7 migrations applied successfully
- [ ] ✅ All tests passing (0 failures)
- [ ] ✅ Enrichment completed or in progress
- [ ] ✅ CRM integration configured (if using)
- [ ] ✅ Email notifications working
- [ ] ✅ No console errors in UI
- [ ] ✅ API response times < 2 seconds

### Data Readiness

- [ ] ✅ At least 1,000 verified domains
- [ ] ✅ At least 100 sources discovered
- [ ] ✅ Sample leads visible in feed
- [ ] ✅ Lead scores calculated correctly
- [ ] ✅ Urgency scores populated
- [ ] ✅ Competitor intelligence detected (on some leads)

### Marketing Readiness

- [ ] Landing page updated with enterprise features
- [ ] Pricing page shows $300-500/mo tier
- [ ] ROI calculator available
- [ ] Demo video or screenshots prepared
- [ ] Case study or testimonial (if available)
- [ ] Sales deck highlighting enterprise features

---

## 📊 Post-Launch Monitoring (Week 1)

### Day 1: Launch Day

- [ ] **Morning**
  - [ ] Final smoke test of all features
  - [ ] Announce launch (email, social media, etc.)
  - [ ] Monitor Railway logs for errors
  - [ ] Check database connection pool usage

- [ ] **Afternoon**
  - [ ] Verify first user sign-ups
  - [ ] Check that scans are completing
  - [ ] Monitor email delivery (Resend dashboard)
  - [ ] Respond to support inquiries

- [ ] **Evening**
  - [ ] Review analytics: total leads, hot leads, CRM syncs
  - [ ] Check error logs for any issues
  - [ ] Verify enrichment is running smoothly

### Days 2-7: First Week

- [ ] **Daily Checks**
  - [ ] Monitor Railway uptime (expect 99.9%)
  - [ ] Check database size (Neon free tier: 512 MB)
  - [ ] Review error logs (Railway dashboard)
  - [ ] Track user engagement metrics

- [ ] **Weekly Review**
  - [ ] Run coverage analysis: `python3 scripts/improve_coverage.py --analyze`
  - [ ] Review scan statistics (completed, failed)
  - [ ] Check CRM sync success rate
  - [ ] Gather user feedback

---

## 🔧 Troubleshooting Guide

### Issue: Migration Fails

**Symptoms**: Migration script returns error
**Solution**:
```bash
# Check if already applied
railway run psql $DATABASE_URL -c "SELECT column_name FROM information_schema.columns WHERE table_name='leads';"

# If column exists, migration already applied (safe to skip)
```

### Issue: CRM Sync Fails

**Symptoms**: "Authentication Error" when syncing
**Checks**:
1. Verify `CRM_ENCRYPTION_KEY` is set: `railway variables | grep CRM`
2. Test CRM credentials in their web UI
3. For Salesforce: Check security token is current
4. For HubSpot: Verify private app token has correct scopes

**Fix**:
```bash
# Re-save CRM config with correct credentials
curl -X POST https://your-app.railway.app/api/crm/config \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{...correct credentials...}'
```

### Issue: Enrichment Running Slow

**Symptoms**: Taking longer than expected
**Causes**:
- Too few workers (increase with `--workers 8`)
- Network latency (run closer to cities being enriched)
- Rate limiting from municipal servers (expected, 1 sec delay per request)

**Fix**:
```bash
# Kill slow enrichment
pkill -f batch_enrich

# Restart with more workers
python3 scripts/batch_enrich.py --states CA TX --workers 8
```

### Issue: Database Connection Timeout

**Symptoms**: "SSL connection timeout" during enrichment
**Solution**: Already handled by session-cycling in EnrichmentEngine
**Check**: Verify pool settings in `src/database.py:350-367`

### Issue: Email Alerts Not Sending

**Checks**:
1. Verify `RESEND_API_KEY` is set
2. Check sender domain is verified in Resend dashboard
3. Check Railway logs for email errors

**Test**:
```bash
# Test Resend API key
curl https://api.resend.com/emails \
  -H "Authorization: Bearer $RESEND_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "from": "noreply@govtechdiagnostic.com",
    "to": "your@email.com",
    "subject": "Test",
    "text": "Test email"
  }'
```

---

## 📈 Success Metrics (Track These)

### Week 1 Goals

- [ ] 10+ user sign-ups
- [ ] 5+ scans completed
- [ ] 100+ leads discovered
- [ ] 10+ hot leads
- [ ] 1+ CRM sync (if configured)
- [ ] 0 critical errors
- [ ] < 2 sec avg API response time

### Month 1 Goals

- [ ] 50+ user sign-ups
- [ ] 100+ scans completed
- [ ] 1,000+ leads discovered
- [ ] 100+ hot leads
- [ ] 50+ CRM syncs
- [ ] 10+ paying customers
- [ ] 1+ deal attributed to tool

### Quarter 1 Goals

- [ ] 200+ users
- [ ] $15,000+ MRR (50 customers @ $300/mo)
- [ ] 5+ case studies with revenue attribution
- [ ] 95% enrichment coverage (6,400+ cities)
- [ ] < 1% churn rate
- [ ] 10+ feature requests logged for roadmap

---

## 🎉 You're Ready to Launch!

### Final Checklist

- [x] ✅ All 13 enterprise phases built
- [x] ✅ 7 database migrations ready
- [x] ✅ 18 new API endpoints tested
- [x] ✅ Automated test suite created
- [x] ✅ Deployment guide written
- [x] ✅ UI enhancement roadmap complete
- [ ] ⏳ Migrations applied to production
- [ ] ⏳ Enrichment running/complete
- [ ] ⏳ CRM configured
- [ ] ⏳ Marketing site updated

### Next Action

**Start here**:
```bash
# 1. Apply migrations (15 min)
railway run python3 migrations/001_add_lead_deduplication.py
# ... (run all 7)

# 2. Test deployment (5 min)
python3 test_enterprise_features.py --url https://your-app.railway.app --email your@email.com

# 3. Start enrichment (launch and let run)
python3 scripts/batch_enrich.py --all --workers 8

# 4. Announce launch! 🚀
```

---

**Your $300-500/mo enterprise platform is ready to launch!** 🎉

*All the hard work is done. Time to make money.* 💰
