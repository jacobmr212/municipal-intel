# Deployment Guide: govtechdiagnostic.com

Complete guide to deploy Municipal Intel to Railway with custom domain.

## Quick Deploy to Railway

### 1. Push to GitHub

```bash
# Initialize git if not already done
git init
git add .
git commit -m "Initial commit: Municipal Intel platform with magic link auth"

# Create GitHub repo and push
# (Create repo at github.com/new first)
git remote add origin https://github.com/YOUR_USERNAME/municipal-intel.git
git branch -M main
git push -u origin main
```

### 2. Deploy to Railway

1. Go to [railway.app](https://railway.app) and sign in
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Choose your `municipal-intel` repository
5. Railway will automatically detect the Python app and deploy

### 3. Set Environment Variables

In Railway dashboard, go to your project → Variables → Add the following:

```bash
# Use your actual keys from .env file (not committed to Git)

# Required - Resend Email
RESEND_API_KEY=re_your_resend_api_key_here
RESEND_FROM_EMAIL=Municipal Intel <noreply@govtechdiagnostic.com>

# Required - Security
JWT_SECRET_KEY=your_jwt_secret_key_here

# Required - Domain (update after Railway gives you URL)
APP_URL=https://govtechdiagnostic.com

# Optional - AI Features
ANTHROPIC_API_KEY=sk-ant-your_anthropic_api_key_here

# Railway sets this automatically
PORT=8000
```

### 4. Configure Custom Domain (govtechdiagnostic.com)

#### In Railway:

1. Go to your project → Settings → Domains
2. Click "Add Custom Domain"
3. Enter: `govtechdiagnostic.com`
4. Railway will give you a CNAME or A record to add to your DNS

#### In Your Domain Registrar (e.g., Namecheap, GoDaddy, Cloudflare):

Add DNS records (Railway will provide the exact values):

**Option 1: CNAME (Recommended)**
```
Type: CNAME
Host: @
Value: <railway-provided-domain>.up.railway.app
TTL: Automatic
```

**Option 2: A Record**
```
Type: A
Host: @
Value: <railway-provided-IP>
TTL: Automatic
```

**Also add www subdomain:**
```
Type: CNAME
Host: www
Value: govtechdiagnostic.com
TTL: Automatic
```

DNS propagation takes 5 minutes to 48 hours (usually ~1 hour).

### 5. Verify Domain Email (Resend)

Since you're using a custom domain for emails (`noreply@govtechdiagnostic.com`):

1. Go to [resend.com](https://resend.com) dashboard
2. Click "Domains" → "Add Domain"
3. Enter: `govtechdiagnostic.com`
4. Resend will give you DNS records to add:
   - **SPF record** (TXT)
   - **DKIM record** (TXT or CNAME)
   - **DMARC record** (TXT)

Add these to your domain registrar's DNS settings.

Example DNS records from Resend:
```
Type: TXT
Host: @
Value: v=spf1 include:_spf.resend.com ~all

Type: TXT
Host: resend._domainkey
Value: [Resend will provide]

Type: TXT
Host: _dmarc
Value: v=DMARC1; p=none;
```

### 6. Test Production Deployment

Once DNS propagates:

```bash
# Test health endpoint
curl https://govtechdiagnostic.com/health

# Test landing page
curl https://govtechdiagnostic.com/

# Test magic link (should send email)
curl -X POST https://govtechdiagnostic.com/api/auth/request-magic-link \
  -H "Content-Type: application/json" \
  -d '{"email":"your-email@example.com"}'
```

## Production Checklist

- [ ] GitHub repo created and code pushed
- [ ] Railway project deployed
- [ ] All environment variables set in Railway
- [ ] Custom domain (govtechdiagnostic.com) added in Railway
- [ ] DNS records updated at domain registrar
- [ ] DNS propagation complete (check with `dig govtechdiagnostic.com`)
- [ ] Domain verified in Resend
- [ ] Email DNS records (SPF, DKIM, DMARC) added
- [ ] SSL certificate active (Railway handles automatically)
- [ ] Magic link emails sending successfully
- [ ] `/health` endpoint returning 200 OK
- [ ] Landing page loads at https://govtechdiagnostic.com
- [ ] Authentication flow tested end-to-end

## Database in Production

**Current Setup:** SQLite file (`data/municipal_intel.db`)

**For Production Scale:**
- Railway's filesystem is ephemeral (resets on deploy)
- For production, upgrade to PostgreSQL:
  1. Add Railway Postgres plugin to your project
  2. Railway auto-sets `DATABASE_URL` environment variable
  3. Update `src/database.py` to use `DATABASE_URL` if present:

```python
import os
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/municipal_intel.db")
engine = create_engine(DATABASE_URL)
```

## Monitoring

Railway provides:
- **Logs**: View real-time application logs
- **Metrics**: CPU, memory, network usage
- **Deployments**: See deploy history and rollback if needed

## Rollback

If something breaks:
1. Go to Railway → Deployments
2. Find last working deployment
3. Click "Redeploy"

## Support

- Railway Docs: https://docs.railway.app
- Resend Docs: https://resend.com/docs
- DNS Checker: https://dnschecker.org

## Cost Estimate

**Railway:**
- Free tier: $5/month credit (usually enough for development)
- Hobby plan: $5/month (recommended for production)
- Pay-as-you-go beyond free credit

**Resend:**
- Free tier: 3,000 emails/month
- Paid: $20/month for 50,000 emails

**Total:** ~$5-25/month depending on usage
