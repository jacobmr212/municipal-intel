# Deploy to Railway (5 Minutes)

Per CLAUDE.md architecture - Municipal Intel runs on Railway for persistent processes.

---

## ✅ Ready to Deploy

- ✅ Code on GitHub: `jacobmr212/municipal-intel`
- ✅ Procfile configured
- ✅ Requirements.txt complete
- ✅ Database: Neon PostgreSQL (shared with govtech-erp-platform)

---

## 🚀 Step 1: Create Railway Project (2 min)

1. **Go to** https://railway.app
2. **Click** "Login" → "Login with GitHub"
3. **Click** "New Project"
4. **Click** "Deploy from GitHub repo"
5. **Select** `jacobmr212/municipal-intel`
6. **Click** "Deploy Now"

Railway will automatically:
- Detect it's a Python app
- Install dependencies from requirements.txt
- Use Procfile to start the server

---

## 🔑 Step 2: Add Environment Variables (2 min)

**In Railway dashboard:**

1. **Click** your project → **Variables** tab
2. **Click** "New Variable" and add each:

```bash
# Get actual values from: cat /Users/jacob/Desktop/municipal-intel/.env

# Database (shared with govtech-erp-platform)
DATABASE_URL=<your_neon_database_url_from_.env>

# Email (Resend)
RESEND_API_KEY=<your_resend_key_from_.env>
RESEND_FROM_EMAIL=Municipal Intel <noreply@govtechdiagnostic.com>

# Security
JWT_SECRET_KEY=<your_jwt_secret_from_.env>

# Domain
APP_URL=https://govtechdiagnostic.com

# AI (Optional)
ANTHROPIC_API_KEY=<your_anthropic_key_from_.env>
```

3. **Railway auto-redeploys** after adding variables

---

## 🌐 Step 3: Add Custom Domain (1 min)

**In Railway dashboard:**

1. **Click** Settings → **Domains**
2. **Click** "Add Custom Domain"
3. **Enter** `govtechdiagnostic.com`
4. **Railway shows DNS records** to add

**In your domain registrar:**

Add CNAME record:
```
Type: CNAME
Host: @
Value: <railway-provided-domain>.up.railway.app
```

Also add www:
```
Type: CNAME
Host: www
Value: govtechdiagnostic.com
```

---

## ✅ Done!

Once DNS propagates (~30 min):
- Visit: https://govtechdiagnostic.com
- See landing page
- Request magic link
- Login and run scans

---

## 💰 Cost

**Railway:**
- Free tier: $5/month credit
- Hobby plan: $5/month (recommended)

**Neon PostgreSQL:**
- Already set up (shared with govtech-erp-platform)
- Free tier

**Resend:**
- Free: 3,000 emails/month

**Total: $0-5/month**

---

## 🔍 Why Railway (Not Vercel)?

Per CLAUDE.md architecture:

✅ **Railway:**
- Persistent process (background tasks work)
- Long-running scans (no timeouts)
- Perfect for FastAPI

❌ **Vercel:**
- Serverless functions (10s timeout)
- No background tasks
- Made for Next.js (use for govtech-erp-platform)

---

**Next:** Go to railway.app and deploy! 🚀
