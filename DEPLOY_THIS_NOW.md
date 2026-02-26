# 🚨 DEPLOY VENDOR NEUTRALITY - MANUAL STEPS REQUIRED

**Status:** Code is ready in GitHub, Railway is NOT auto-deploying

**You need to manually trigger deployment from Railway dashboard**

---

## THE PROBLEM

Railway's auto-deploy from GitHub is not working. I've:
- ✅ Pushed 6 commits to main branch
- ✅ Tried `railway up` command multiple times
- ✅ Created empty commits to trigger webhooks
- ✅ Bumped version numbers (historical pattern)

**None worked.** Live site still shows version 2.0.1 (should be 2.1.0) and `/api/vendor-config` returns 404 (should exist).

---

## SOLUTION: MANUAL DEPLOY (2 MINUTES)

### Option 1: Deploy Latest Commit

1. Go to **https://railway.app**
2. Log in with GitHub
3. Find **"municipal-intel"** project
4. Click **"web"** service
5. Go to **"Deployments"** tab
6. Click **"Deploy"** button (top right)
7. Select latest commit: **797e9fb** or **28852c8**
8. Wait ~2-3 minutes for build

### Option 2: Enable Auto-Deploy (Fix for Future)

1. In Railway → **Project Settings**
2. Go to **"Source"** or **"GitHub"** section
3. Verify: Repository = **jacobmr212/municipal-intel**
4. Verify: Branch = **main**
5. Find **"Auto Deploy"** toggle
6. **Enable it** if it's off
7. Save
8. Then manually deploy once (Option 1)

---

## VERIFY DEPLOYMENT WORKED

### Check 1: Health Endpoint
```bash
curl https://web-production-a13f5.up.railway.app/health
```

**Should return:**
```json
{"status":"ok","version":"2.1.0"}
```

**Currently returns:** `{"version":"2.0.1"}` ❌

### Check 2: Vendor Config API Exists
```bash
curl https://web-production-a13f5.up.railway.app/api/vendor-config
```

**Should return:** `401 Unauthorized` (not 404) - means endpoint exists but requires auth

**Currently returns:** `404 Not Found` ❌

### Check 3: Scanner UI
1. Open https://web-production-a13f5.up.railway.app/scanner
2. Log in
3. Look for **"Vendor Configuration"** section
4. Should appear **ABOVE** "Configure Scan" section
5. Should have two text inputs + Save button

**Currently:** Section does not exist ❌

---

## WHAT GETS DEPLOYED

When you deploy commit **797e9fb**, you're deploying:

### Backend Changes (6 commits)
- `1bb397a` - Vendor config API endpoints (GET/PATCH /api/vendor-config)
- `7f0f87d` - Dynamic signal detection (no hardcoded Caselle)
- `64de320` - Scan execution fix (passes vendor config to analyzer)
- `72d673c` - Empty commit (trigger attempt)
- `28852c8` - Version bump to 2.1.0
- `797e9fb` - Documentation

### Files Modified
- `main.py` - API endpoints + scan execution fix
- `src/signals.py` - Dynamic signals
- `src/analyzer.py` - Vendor-aware analysis
- `src/competitor.py` - Vendor-aware competitor detection
- `templates/scanner.html` - Vendor Configuration UI
- `migrations/011_add_vendor_config.py` - Database migration

---

## AFTER DEPLOYMENT: RUN MIGRATION

Once deployment completes and health check shows v2.1.0:

```bash
railway run python3 migrations/011_add_vendor_config.py
```

This adds `vendor_name` and `vendor_competitors` columns to the `users` table.

---

## FULL TESTING CHECKLIST

After deploy + migration:

### Test 1: UI Exists
- [ ] /scanner shows "Vendor Configuration" section
- [ ] Section has "Your Vendor" text input
- [ ] Section has "Competitors to Track" text input
- [ ] Section has "Save Configuration" button
- [ ] Status indicator shows "Not configured"

### Test 2: Save Configuration
- [ ] Enter "Tyler Technologies" as vendor
- [ ] Enter "Caselle, CentralSquare, Infor" as competitors
- [ ] Click Save
- [ ] See success message
- [ ] Status shows "Configured: Tyler Technologies (tracking 3 competitors)"

### Test 3: Config Persists
- [ ] Refresh page
- [ ] Vendor name field still shows "Tyler Technologies"
- [ ] Competitors field still shows entered values

### Test 4: Vendor-Aware Scanning
- [ ] Select Wyoming in Scanner
- [ ] Choose "Small (2.5K-10K)" tier
- [ ] Click "Start Scan"
- [ ] Wait for completion
- [ ] Check results:
   - [ ] If Tyler is mentioned → shows "EXISTING CUSTOMER"
   - [ ] AI summaries say "Tyler Technologies" not "Caselle"
   - [ ] Lead detail pages reference Tyler not Caselle

### Test 5: Neutral Mode
- [ ] Clear both vendor config fields
- [ ] Save
- [ ] Run new scan
- [ ] Results use generic "ERP vendor" language
- [ ] No vendor-specific branding in summaries

---

## WHY RAILWAY ISN'T AUTO-DEPLOYING

Possible causes:

1. **Auto-deploy disabled** - Toggle is off in settings
2. **Wrong branch** - Watching a different branch than main
3. **Webhook not set up** - GitHub webhook to Railway broken
4. **Requires approval** - Manual deployment approval enabled
5. **Deploy on push disabled** - Setting exists but is off

**You need dashboard access to fix this.** I cannot access Railway settings from CLI.

---

## ROLLBACK IF NEEDED

If deployment breaks something:

### Railway Dashboard
1. Go to Deployments
2. Find previous working deployment
3. Click "Redeploy"

### Or via Git
```bash
git revert 797e9fb 28852c8 72d673c 64de320 7f0f87d 1bb397a
git push origin main
```

---

## FILES FOR REFERENCE

- **VENDOR_NEUTRALITY_STATUS.md** - Complete technical documentation
- **This file** - Quick deploy instructions
- **DEPLOYMENT.md** - General Railway deployment guide

---

## BOTTOM LINE

**The code is done. Railway just needs to deploy it.**

You must:
1. Go to Railway dashboard
2. Manually trigger deploy of latest commit
3. Run migration 011
4. Test the vendor configuration feature

That's it. Everything else is ready.
