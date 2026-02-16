# 🚀 Quick Start: Deploy to Vercel (30 minutes)

Super simple deployment - just like your Cloudflare Workers workflow!

---

## ✅ Already Done
- ✅ Code on GitHub: `jacobmr212/municipal-intel`
- ✅ Vercel configured (`vercel.json`)
- ✅ Ready to deploy!

---

## 🎯 Step 1: Deploy (5 minutes)

1. **Go to** https://vercel.com
2. **Click** "Sign Up" → "Continue with GitHub"
3. **Click** "Add New" → "Project"
4. **Find** `municipal-intel` repo
5. **Click** "Import"
6. **Click** "Deploy" (leave all settings default)

✅ Done! Vercel builds and deploys automatically.

---

## 🔑 Step 2: Add Environment Variables (5 minutes)

Get your keys:
```bash
cat /Users/jacob/Desktop/municipal-intel/.env
```

In Vercel dashboard:
1. **Go to** Settings → Environment Variables
2. **Add these 5 variables** (copy from `.env` file above):

| Variable Name | Value from .env | All Environments |
|--------------|-----------------|------------------|
| `RESEND_API_KEY` | (starts with `re_`) | ✓ Check all |
| `JWT_SECRET_KEY` | (random string) | ✓ Check all |
| `RESEND_FROM_EMAIL` | `Municipal Intel <noreply@govtechdiagnostic.com>` | ✓ Check all |
| `APP_URL` | `https://govtechdiagnostic.com` | ✓ Check all |
| `ANTHROPIC_API_KEY` | (starts with `sk-ant-`) | ✓ Check all |

3. **Click** Deployments → Redeploy (latest)

---

## 🌐 Step 3: Add Domain (2 minutes)

1. **In Vercel:** Settings → Domains
2. **Type:** `govtechdiagnostic.com`
3. **Click** "Add"

**Vercel shows DNS records to add:**
```
Type: CNAME
Name: @
Value: cname.vercel-dns.com
```

4. **Go to your domain registrar** (Namecheap/GoDaddy/Cloudflare)
5. **Add the CNAME record** Vercel provided
6. **Also add www:**
   ```
   Type: CNAME
   Name: www
   Value: cname.vercel-dns.com
   ```

⏱️ Wait 5-60 minutes for DNS propagation

---

## 📧 Step 4: Verify Email Domain (15 minutes)

1. **Go to** https://resend.com/domains
2. **Click** "Add Domain"
3. **Enter:** `govtechdiagnostic.com`

**Resend shows 3 DNS records. Add to your domain:**

```
Type: TXT | Name: @ | Value: v=spf1 include:_spf.resend.com ~all
Type: TXT | Name: resend._domainkey | Value: <from Resend>
Type: TXT | Name: _dmarc | Value: v=DMARC1; p=none;
```

4. **Wait 5-10 minutes**
5. **Click "Verify"** in Resend
6. **See green checkmark** ✅

---

## ✅ Test Your Site

**Visit:** https://govtechdiagnostic.com

Should see:
- Landing page with email form
- Request magic link
- Get email
- Click link → redirects to /app
- Run a scan!

---

## 📊 That's It!

**Total time:** ~30 minutes active + DNS wait

**Ongoing:** Every git push to `main` auto-deploys (just like Cloudflare!)

**Full guide:** See `VERCEL_DEPLOYMENT.md` for detailed troubleshooting

---

## 💰 Cost

- **Vercel:** FREE (no credit card needed)
- **Resend:** FREE (3,000 emails/month)
- **Total:** $0/month

---

Ready? Go to **vercel.com** and import your repo! 🚀
