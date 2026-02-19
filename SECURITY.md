# Security Guide

## Environment Configuration

This project uses separate API keys for development and production environments.

### Development Setup

1. **Copy the template:**
   ```bash
   cp .env.example .env
   ```

2. **Create a Resend TEST API key:**
   - Go to https://resend.com/api-keys
   - Click "Create API Key"
   - Name: `municipal-intel-development`
   - Environment: **Test** (not Production)
   - Copy the key and add to `.env`

3. **Generate a JWT secret:**
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
   Add this to `JWT_SECRET_KEY` in `.env`

4. **Never commit `.env`:**
   - `.env` is already in `.gitignore`
   - Only `.env.example` should be committed

### Production Setup (Railway)

Production API keys are stored as Railway environment variables:

| Variable | Source | Notes |
|----------|--------|-------|
| `RESEND_API_KEY` | Resend (Production) | Full send permissions |
| `JWT_SECRET_KEY` | Generated secret | Different from dev |
| `DATABASE_URL` | Neon | Auto-configured by Railway |
| `APP_URL` | Static | `https://govtechdiagnostic.com` |
| `ANTHROPIC_API_KEY` | Anthropic | Optional, for LLM analysis |
| `ADMIN_EMAIL` | Static | Receives waitlist notifications |

### Key Rotation

**When to rotate keys:**
- Immediately if a key is exposed in git history
- Every 90 days as best practice
- When team members leave

**How to rotate:**

1. **Resend API Key:**
   - Create new key in Resend dashboard
   - Update Railway environment variable
   - Delete old key after confirming new one works

2. **JWT Secret:**
   - Generate new secret: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
   - Update Railway environment variable
   - Note: This will invalidate all existing user sessions

### Security Checklist

- [x] `.env` excluded from git
- [x] No hardcoded API keys in source code
- [x] All API endpoints require authentication
- [x] Database uses SSL connections
- [x] Production uses different keys than development
- [x] Admin endpoints use role-based access control
- [x] Scan/lead endpoints verify ownership
- [x] robots.txt blocks sensitive routes

### Reporting Security Issues

If you discover a security vulnerability, please email: jacob@govtechdiagnostic.com

Do NOT create a public GitHub issue.
