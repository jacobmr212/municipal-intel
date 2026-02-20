# Deploy Municipal Intel to Railway

## Overview

Municipal Intel is deployed on **Railway.app** using FastAPI with a PostgreSQL database on Neon.

**Current Production URL:** https://web-production-a13f5.up.railway.app
**Domain (pending DNS):** govtechdiagnostic.com

---

## Quick Deployment Steps

### 1. Prerequisites

- GitHub account with the repository
- Railway account (sign up at https://railway.app)
- Neon database (sign up at https://neon.tech)

### 2. Set Up Database

1. Go to https://neon.tech
2. Create a new project
3. Copy the connection string (starts with `postgresql://`)

### 3. Deploy to Railway

1. Visit https://railway.app
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Choose `jacobmr212/municipal-intel`
5. Railway will auto-detect `main.py` as the FastAPI app

### 4. Configure Environment Variables

In Railway project settings → Variables, add:

**Required:**
```bash
DATABASE_URL=postgresql://neondb_owner:...@neon.tech/neondb?sslmode=require
JWT_SECRET_KEY=your-random-secure-key-here
RESEND_API_KEY=re_your_resend_api_key
RESEND_FROM_EMAIL=Municipal Intel <noreply@govtechdiagnostic.com>
APP_URL=https://your-app.railway.app
```

**Optional:**
```bash
ANTHROPIC_API_KEY=sk-ant-your-claude-api-key  # For AI-enhanced analysis
```

### 5. Generate JWT Secret

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 6. Deploy

Railway will automatically:
- Install dependencies from `requirements.txt`
- Run database migrations
- Start the FastAPI server with `uvicorn main:app`

Your app will be live in 2-3 minutes!

---

## Custom Domain Setup

### Point govtechdiagnostic.com to Railway

1. In Railway project → Settings → Domains
2. Click "Add Domain"
3. Enter `govtechdiagnostic.com`
4. Railway will provide CNAME records
5. Add these records to your DNS provider:
   ```
   CNAME @ your-app.up.railway.app
   ```

---

## Continuous Deployment

Railway auto-deploys on every push to `main`:

```bash
git add .
git commit -m "Your update"
git push origin main
```

View deployment logs in Railway dashboard.

---

## Local Development

```bash
# Clone repo
git clone https://github.com/jacobmr212/municipal-intel.git
cd municipal-intel

# Set up environment
cp .env.example .env
# Edit .env with your DATABASE_URL and API keys

# Install dependencies
pip install -r requirements.txt

# Run locally
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

App will be at http://localhost:8000

---

## Monitoring & Logs

- **Railway Logs:** Dashboard → Your Project → Deployments → View Logs
- **Database Monitoring:** Neon dashboard for connection stats
- **Error Tracking:** Consider adding Sentry (optional)

---

## Rollback

If a deployment breaks:

1. Go to Railway → Deployments
2. Find the last working deployment
3. Click "Redeploy"

Or rollback via git:

```bash
git revert HEAD
git push origin main
```

---

## Production Checklist

- [ ] DATABASE_URL configured and tested
- [ ] JWT_SECRET_KEY set (secure random value)
- [ ] RESEND_API_KEY configured for magic link emails
- [ ] APP_URL matches your Railway domain
- [ ] Custom domain DNS records added (if using)
- [ ] Test login flow (magic link emails working)
- [ ] Test scan functionality
- [ ] Admin access working at /admin
