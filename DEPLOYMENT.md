# Deploy Municipal Intel to Streamlit Cloud

## Quick Deployment Steps

### 1. Go to Streamlit Cloud
Visit: https://share.streamlit.io

### 2. Sign In
- Click "Continue with GitHub"
- Sign in with: jacobmr212@gmail.com

### 3. Create New App
- Click "New app" button (top right)
- Fill in the form:
  - **Repository:** jacobmr212/municipal-intel
  - **Branch:** main
  - **Main file path:** app.py
  - **App URL (optional):** Choose a custom name like "municipal-intel"

### 4. Configure Secrets (Optional - for AI features)
- Click "Advanced settings"
- Under "Secrets", add:
  ```toml
  ANTHROPIC_API_KEY = "sk-ant-api03-your-key-here"
  ```
- Note: The app works fine WITHOUT this - AI analysis is optional!

### 5. Deploy
- Click "Deploy"
- Wait 2-3 minutes for installation
- Your app will be live!

## Share Your App

Once deployed, you'll get a URL like:
```
https://municipal-intel.streamlit.app
```

**Share this URL with anyone** - they can:
- Select any US state
- Scan municipalities for ERP leads
- Download reports
- No login required!

## Manage Your App

- View/edit at: https://share.streamlit.io
- Update code: Just push to GitHub, app auto-redeploys
- View logs: Click "Manage app" → "Logs"
- Restart: Click "Manage app" → "Reboot app"

## Make App Public

By default, your app is **public** - anyone with the URL can use it.

To restrict access:
- Go to app settings
- Under "Sharing", add email addresses
- Or keep it public for maximum reach!
