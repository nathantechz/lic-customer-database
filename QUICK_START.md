# Quick Start Guide - Streamlit Cloud Deployment

## ⚡ Fast Track (10 minutes)

### 1. Set Up Supabase (3 min)
```
1. Go to supabase.com → Sign up/Login
2. Create new project → Choose name & password
3. Wait for project to initialize (~2 min)
4. Go to SQL Editor → New Query
5. Copy all content from `supabase_schema.sql`
6. Paste and click "Run"
```

### 2. Get Credentials (1 min)
```
1. Click "Project Settings" (gear icon)
2. Go to "API" tab  
3. Copy:
   - Project URL
   - anon public key
```

### 3. Update Local Secrets (1 min)
```
1. Open `.streamlit/secrets.toml`
2. Replace with your credentials:
   url = "https://YOUR-PROJECT.supabase.co"
   key = "YOUR-ANON-KEY"
3. Save file
```

### 4. Test Locally (2 min)
```bash
cd /Users/naganathan/Library/CloudStorage/Dropbox/LIC/lic_database
streamlit run scripts/streamlit_app.py
```

Check if "✅ Supabase Connected!" appears in sidebar.

### 5. Push to GitHub (2 min)
```bash
# If not already initialized
git init
git add .
git commit -m "Deploy to Streamlit Cloud"

# Create repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/lic-customer-database.git
git push -u origin main
```

### 6. Deploy to Streamlit Cloud (1 min)
```
1. Go to share.streamlit.io
2. Sign in with GitHub
3. Click "New app"
4. Select your repository
5. Set main file: scripts/streamlit_app.py
6. Click "Advanced settings"
7. Add secrets from step 2
8. Click "Deploy!"
```

## ✅ Done!

Your app will be live in 2-5 minutes at:
`https://your-app-name.streamlit.app`

## 🔧 Add Your Supabase Credentials

**Option 1: Local file (for testing)**
Edit `.streamlit/secrets.toml`:
```toml
[supabase]
url = "https://abcdefgh.supabase.co"
key = "eyJhbGc...your-key-here"
```

**Option 2: Streamlit Cloud (for production)**
In app settings → Secrets, add:
```toml
[supabase]
url = "https://abcdefgh.supabase.co"
key = "eyJhbGc...your-key-here"
```

## 📝 Important Files

- `scripts/streamlit_app.py` - Main app (Supabase-enabled)
- `requirements.txt` - Python dependencies
- `supabase_schema.sql` - Database schema
- `.streamlit/secrets.toml` - Local secrets (don't commit!)
- `.gitignore` - Protects secrets from Git

## 🚀 Features

✅ Search customers by name, phone, policy
✅ Add/edit customers and policies  
✅ Duplicate detection
✅ Database statistics
✅ Cloud-ready architecture

## 🆘 Need Help?

Check `STREAMLIT_CLOUD_DEPLOYMENT.md` for detailed guide.

## 📊 Test Your Setup

Run locally:
```bash
streamlit run scripts/streamlit_app.py
```

Should see:
- ✅ Supabase Connected!
- Database stats displayed
- Search functionality working

Happy deploying! 🎉
