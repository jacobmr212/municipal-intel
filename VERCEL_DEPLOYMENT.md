# 🚀 Deploy to Vercel (Simple & Free)

Your Municipal Intel platform is configured for **Vercel** - similar to how you deploy with Cloudflare Workers!

---

## ✅ What's Already Done

- ✅ Code pushed to GitHub: `jacobmr212/municipal-intel`
- ✅ Vercel configuration created (`vercel.json`)
- ✅ API entry point configured (`api/index.py`)
- ✅ All dependencies listed in `requirements.txt`

---

## 📋 Step 1: Deploy to Vercel (5 minutes)

### 1.1 Go to Vercel
1. Open **https://vercel.com** in your browser
2. Click **"Sign Up"** or **"Login"**
3. Choose **"Continue with GitHub"**

### 1.2 Import Your Project
1. Click **"Add New"** → **"Project"**
2. Vercel shows your GitHub repos
3. Find **`municipal-intel`**
4. Click **"Import"**

### 1.3 Configure Project
Vercel will auto-detect settings. You should see:
- **Framework Preset**: Other
- **Build Command**: (leave empty)
- **Output Directory**: (leave empty)
- **Install Command**: `pip install -r requirements.txt`

Click **"Deploy"** - Vercel will build and deploy automatically!

⏱️ **First deploy takes ~2-3 minutes**

---

## 📋 Step 2: Add Environment Variables (3 minutes)

### 2.1 Go to Project Settings
After deployment:
1. Click your project name
2. Go to **"Settings"** tab
3. Click **"Environment Variables"** in sidebar

### 2.2 Add These Variables

Get your actual values from `.env` file:
```bash
cat /Users/jacob/Desktop/municipal-intel/.env
```

Add each variable:

**Variable 1: RESEND_API_KEY**
- Name: `RESEND_API_KEY`
- Value: `<your_resend_key_from_.env>` (starts with `re_`)
- Environment: Production, Preview, Development (check all)

**Variable 2: JWT_SECRET_KEY**
- Name: `JWT_SECRET_KEY`
- Value: `<your_jwt_secret_from_.env>`
- Environment: Production, Preview, Development

**Variable 3: RESEND_FROM_EMAIL**
- Name: `RESEND_FROM_EMAIL`
- Value: `Municipal Intel <noreply@govtechdiagnostic.com>`
- Environment: Production, Preview, Development

**Variable 4: APP_URL**
- Name: `APP_URL`
- Value: `https://govtechdiagnostic.com` (will update after domain setup)
- Environment: Production, Preview, Development

**Variable 5: ANTHROPIC_API_KEY**
- Name: `ANTHROPIC_API_KEY`
- Value: `<your_anthropic_key_from_.env>` (starts with `sk-ant-`)
- Environment: Production, Preview, Development

### 2.3 Redeploy
After adding variables:
1. Go to **"Deployments"** tab
2. Click **"Redeploy"** on latest deployment
3. Check **"Use existing Build Cache"**
4. Click **"Redeploy"**

---

## 📋 Step 3: Add Custom Domain (2 minutes)

### 3.1 In Vercel Dashboard
1. Go to **"Settings"** → **"Domains"**
2. Type: `govtechdiagnostic.com`
3. Click **"Add"**

### 3.2 Vercel Shows DNS Instructions
Vercel will show you exactly what DNS records to add. It's usually:

**Option A: CNAME (Recommended)**
```
Type: CNAME
Name: @
Value: cname.vercel-dns.com
```

**Also add www:**
```
Type: CNAME
Name: www
Value: cname.vercel-dns.com
```

### 3.3 Add DNS Records
Go to your domain registrar (Namecheap, GoDaddy, Cloudflare, etc.):
1. Find DNS settings
2. Add the CNAME records Vercel provided
3. Save changes

**DNS propagation:** 5 minutes to 1 hour (usually fast!)

### 3.4 Update APP_URL
Once domain is active:
1. Go to **Settings** → **Environment Variables**
2. Edit `APP_URL`
3. Change to: `https://govtechdiagnostic.com`
4. Save and redeploy

---

## 📋 Step 4: Verify Email Domain in Resend (15 minutes)

### 4.1 Add Domain
1. Go to **https://resend.com/domains**
2. Click **"Add Domain"**
3. Enter: `govtechdiagnostic.com`
4. Click **"Add"**

### 4.2 Add DNS Records for Email
Resend shows 3 records to add to your domain DNS:

**1. SPF Record**
```
Type: TXT
Name: @
Value: v=spf1 include:_spf.resend.com ~all
```

**2. DKIM Record**
```
Type: TXT (or CNAME - Resend will specify)
Name: resend._domainkey
Value: <value from Resend dashboard>
```

**3. DMARC Record**
```
Type: TXT
Name: _dmarc
Value: v=DMARC1; p=none;
```

Add all 3 records to your domain registrar's DNS settings.

### 4.3 Verify Domain
1. Wait 5-10 minutes after adding DNS records
2. Go back to Resend → Domains
3. Click **"Verify"** next to `govtechdiagnostic.com`
4. Should show ✅ green checkmark when verified

---

## 🎉 Step 5: Test Your Live Site!

Once everything is set up (usually 30-60 minutes total):

### Test 1: Visit Your Site
Open: **https://govtechdiagnostic.com**
- Should see professional landing page
- "GovTech Diagnostic" branding
- Email capture form

### Test 2: Request Magic Link
1. Enter your email on landing page
2. Click **"Request Access"**
3. Check your email inbox
4. You should receive magic link email

### Test 3: Login & Scan
1. Click magic link in email
2. Should redirect to `/app` dashboard
3. Select a state (e.g., Utah)
4. Choose population tier
5. Click **"Start Scan"**
6. Watch real-time progress
7. View results when complete

---

## 📊 Vercel Features You'll Love

**Automatic Deployments**
- Every git push to `main` branch auto-deploys
- Just like Cloudflare Workers workflow you know!

**Preview Deployments**
- Every pull request gets a preview URL
- Test before merging to production

**Analytics**
- See traffic, performance, errors
- Free on all plans

**Logs**
- Real-time function logs
- Debug easily from dashboard

---

## 🔍 Monitoring & Logs

### View Logs
1. Vercel Dashboard → Your Project
2. Click **"Logs"** tab
3. See real-time server output and errors

### View Analytics
1. Click **"Analytics"** tab
2. See traffic, performance metrics
3. Error tracking included

---

## 🆘 Troubleshooting

### "Function Execution Timeout"
Vercel free tier has 10-second timeout. If scans take longer:
- Background tasks continue running
- Users see progress via polling
- Should work fine for your use case

### "Module Not Found" Error
- Check `requirements.txt` includes all dependencies
- Redeploy after fixing

### "DNS Not Propagating"
- Wait up to 1 hour
- Check with: `dig govtechdiagnostic.com`
- Clear browser cache

### "Emails Going to Spam"
- Verify all 3 DNS records in Resend (SPF, DKIM, DMARC)
- Domain must show verified ✅ in Resend

---

## ✅ Deployment Checklist

- [ ] Vercel account created
- [ ] Project imported from GitHub
- [ ] All environment variables added
- [ ] Project redeployed with env vars
- [ ] Custom domain added in Vercel
- [ ] CNAME records added to domain DNS
- [ ] www subdomain added
- [ ] Domain verified in Vercel (shows checkmark)
- [ ] APP_URL updated to production domain
- [ ] Domain added to Resend
- [ ] SPF record added to DNS
- [ ] DKIM record added to DNS
- [ ] DMARC record added to DNS
- [ ] Domain verified in Resend ✅
- [ ] Site loads at govtechdiagnostic.com
- [ ] Magic link email received and works
- [ ] Can login and run scans

---

## 💰 Cost

**Vercel:**
- **Free tier**: Perfect for your needs
- Includes: HTTPS, automatic deployments, 100GB bandwidth
- No credit card required to start

**Resend:**
- **Free tier**: 3,000 emails/month
- **Paid**: $20/month for 50,000 emails

**Total: $0/month to start** (free tier), then $0-20/month depending on email volume

---

## 📞 Support

- **Vercel Docs**: https://vercel.com/docs
- **Vercel Discord**: Very active community
- **Resend Docs**: https://resend.com/docs

---

## 🎯 Quick Start Summary

1. **Vercel**: Import `jacobmr212/municipal-intel` → Deploy (5 min)
2. **Environment Variables**: Add 5 variables from `.env` → Redeploy (3 min)
3. **Domain**: Add `govtechdiagnostic.com` → Update DNS (2 min + wait)
4. **Email**: Verify domain in Resend with 3 DNS records (15 min)
5. **Test**: Visit site, request magic link, login, run scan (5 min)

**Total active time: ~30 minutes** (plus DNS propagation wait)

---

You're all set! Vercel is even easier than Railway - very similar to your Cloudflare Workers workflow. 🚀

Next step: Just go to **vercel.com** and import your GitHub repo!
