# Streamlit Cloud Deployment Guide

Complete guide to deploy your LIC Customer Database app to Streamlit Cloud with Supabase backend.

## Prerequisites

- [x] Supabase account (free tier is sufficient)
- [x] GitHub account
- [x] Streamlit Cloud account (sign up at [share.streamlit.io](https://share.streamlit.io))

## Step 1: Set Up Supabase Database

### 1.1 Create Supabase Project

1. Go to [supabase.com](https://supabase.com)
2. Click "Start your project"
3. Create a new project:
   - **Name**: lic-customer-db (or your preferred name)
   - **Database Password**: Create a strong password (save it!)
   - **Region**: Choose closest to you
   - **Pricing Plan**: Free tier is fine for starting

### 1.2 Create Database Tables

1. Once your project is created, go to **SQL Editor** in the left sidebar
2. Click "New Query"
3. Copy and paste the entire contents of `supabase_schema.sql` file
4. Click "Run" to execute the SQL

This will create all necessary tables:
- `customers`
- `policies`
- `premium_records`
- `agents`
- `documents`

### 1.3 Get Your Supabase Credentials

1. Go to **Project Settings** (gear icon in sidebar)
2. Click on **API** tab
3. Copy these two values:
   - **Project URL** (e.g., `https://xxxxx.supabase.co`)
   - **anon public** key (long string starting with `eyJ...`)

Keep these safe - you'll need them for Streamlit Cloud!

## Step 2: Push Code to GitHub

### 2.1 Initialize Git Repository (if not already done)

```bash
cd /Users/naganathan/Library/CloudStorage/Dropbox/LIC/lic_database
git init
git add .
git commit -m "Initial commit for Streamlit Cloud deployment"
```

### 2.2 Create GitHub Repository

1. Go to [github.com](https://github.com)
2. Click **New repository**
3. Name it: `lic-customer-database` (or your preferred name)
4. **DO NOT** initialize with README, .gitignore, or license
5. Click "Create repository"

### 2.3 Push to GitHub

```bash
git remote add origin https://github.com/YOUR_USERNAME/lic-customer-database.git
git branch -M main
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub username.

## Step 3: Deploy to Streamlit Cloud

### 3.1 Connect Streamlit Cloud to GitHub

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with GitHub
3. Authorize Streamlit Cloud to access your repositories

### 3.2 Create New App

1. Click **"New app"**
2. Select:
   - **Repository**: `YOUR_USERNAME/lic-customer-database`
   - **Branch**: `main`
   - **Main file path**: `scripts/streamlit_app.py`
3. Click **"Advanced settings"**

### 3.3 Configure Secrets

In the **Advanced settings**, add your Supabase credentials in the **Secrets** section:

```toml
[supabase]
url = "https://your-project.supabase.co"
key = "your-anon-public-key-here"
```

Replace with your actual Supabase URL and key from Step 1.3.

### 3.4 Deploy!

1. Click **"Deploy!"**
2. Wait for the app to build and deploy (2-5 minutes)
3. Your app will be live at `https://your-app-name.streamlit.app`

## Step 4: Verify Deployment

### 4.1 Test the App

1. Open your deployed app URL
2. Check that:
   - ✅ Database connection shows "Connected" in sidebar
   - ✅ Database stats are displayed
   - ✅ You can search customers (if you have data)
   - ✅ You can add new customers and policies

### 4.2 Migrate Existing Data (Optional)

If you have existing SQLite data to migrate:

1. Use the migration script (to be created separately)
2. Or manually add data through the Streamlit app interface

## Step 5: Configure App Settings (Optional)

### 5.1 Custom Domain

If you want a custom domain:
1. Go to your app settings on Streamlit Cloud
2. Follow the custom domain setup guide

### 5.2 App Visibility

- **Public**: Anyone can access your app
- **Private**: Only invited users can access
- Set this in app settings on Streamlit Cloud

## Troubleshooting

### Issue: "Database connection failed"

**Solution**:
- Check that your Supabase credentials are correct in Secrets
- Verify your Supabase project is active
- Check if you're using the correct "anon public" key (not the service role key)

### Issue: "Table 'customers' does not exist"

**Solution**:
- Run the `supabase_schema.sql` file in Supabase SQL Editor
- Make sure all tables were created successfully

### Issue: "Module not found" errors

**Solution**:
- Check that `requirements.txt` has all dependencies
- Redeploy the app after updating requirements.txt

### Issue: App is slow

**Solution**:
- Supabase free tier has some limitations
- Consider upgrading to Supabase Pro for better performance
- Optimize queries if needed

## Security Best Practices

1. ✅ **Never commit** `.streamlit/secrets.toml` to Git
2. ✅ Use Supabase **Row Level Security (RLS)** for production
3. ✅ Enable authentication if app contains sensitive data
4. ✅ Regularly backup your Supabase database
5. ✅ Use environment-specific secrets for dev/prod

## App Features on Cloud

✅ **Available**:
- Customer search and management
- Policy management
- Database statistics
- Add/edit customers and policies
- Duplicate detection

❌ **Not Available** (local-only features):
- PDF processing
- File uploads to local directories
- Local file system access

## Updating Your App

To deploy updates:

```bash
git add .
git commit -m "Your update message"
git push origin main
```

Streamlit Cloud will automatically detect changes and redeploy!

## Costs

- **Streamlit Cloud**: Free tier sufficient for personal use
- **Supabase**: Free tier includes:
  - 500MB database space
  - 2GB bandwidth/month
  - 50,000 monthly active users
  - Unlimited API requests

Upgrade to paid tiers if you exceed these limits.

## Support

- **Streamlit Docs**: https://docs.streamlit.io
- **Supabase Docs**: https://supabase.com/docs
- **Community Forum**: https://discuss.streamlit.io

## Next Steps

1. ✨ Add authentication (Supabase Auth + Streamlit)
2. 📊 Create dashboard with charts and analytics
3. 📧 Add email notifications for premium dues
4. 📱 Make it mobile-responsive
5. 🔄 Set up automated database backups

Congratulations! Your app is now live on the cloud! 🎉
