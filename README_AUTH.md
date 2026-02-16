# Magic Link Authentication Setup

Municipal Intel now uses passwordless magic link authentication via Resend.

## Quick Setup

### 1. Get Your Resend API Key

1. Go to [resend.com](https://resend.com) and create an account
2. Get your API key from the dashboard
3. Verify your sending domain (or use `onboarding@resend.dev` for testing)

### 2. Configure Environment Variables

Create a `.env` file in the project root:

```bash
# Required for production email sending
RESEND_API_KEY=re_your_api_key_here
RESEND_FROM_EMAIL=Municipal Intel <noreply@govtechdiagnostic.com>

# Required for production
APP_URL=https://your-production-domain.com
JWT_SECRET_KEY=your-random-secret-key-here

# Optional
ANTHROPIC_API_KEY=your-anthropic-key-here
```

### 3. Generate JWT Secret

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy the output to `JWT_SECRET_KEY` in your `.env` file.

### 4. Load Environment Variables

Install python-dotenv:

```bash
pip install python-dotenv
```

Add to the top of `main.py`:

```python
from dotenv import load_dotenv
load_dotenv()
```

## Development Mode

If you don't set `RESEND_API_KEY`, the app runs in dev mode:
- Magic links are printed to console
- Links are returned in the API response
- No emails are sent

## Testing Magic Links

### Dev Mode (No Resend Key)
1. Submit email on landing page
2. Click the blue link that appears
3. Get redirected to `/app` with session cookie

### Production Mode (With Resend Key)
1. Submit email on landing page
2. Check your email inbox
3. Click the "Access Municipal Intel" button
4. Get redirected to `/app` with session cookie

## Email Template

The magic link email includes:
- Clean, professional HTML design
- Big blue button: "Access Municipal Intel"
- 15-minute expiration notice
- One-time use notice
- Branded footer

## Security Features

- **Token**: 32-byte URL-safe random string
- **Expiration**: 15 minutes
- **Single-use**: Token marked as used after verification
- **Session**: 7-day JWT cookie (httponly, secure, samesite=lax)
- **User isolation**: All scans/leads scoped to user_id

## API Endpoints

```
POST /api/auth/request-magic-link
  Body: { "email": "user@company.com" }
  Returns: { "success": true, "message": "Magic link sent" }

GET /auth/verify/{token}
  Verifies token, sets session cookie, redirects to /app

POST /api/auth/logout
  Clears session cookie
```

## Production Checklist

- [ ] Add `RESEND_API_KEY` to environment
- [ ] Add `RESEND_FROM_EMAIL` with verified domain
- [ ] Set `APP_URL` to production domain
- [ ] Generate and set `JWT_SECRET_KEY`
- [ ] Remove `dev_link` from magic link response (already conditional)
- [ ] Enable HTTPS (session cookies use `secure=True`)
- [ ] Test email delivery
- [ ] Check spam folder first time

## Railway Deployment

Add environment variables in Railway dashboard:

1. Go to your Railway project
2. Click "Variables" tab
3. Add:
   - `RESEND_API_KEY`
   - `RESEND_FROM_EMAIL`
   - `APP_URL` (e.g., `https://your-app.up.railway.app`)
   - `JWT_SECRET_KEY`
4. Redeploy

Done! Magic links will be sent via Resend in production.
