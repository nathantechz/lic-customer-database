# Pre-Deployment Checklist

Use this checklist to ensure everything is ready for Streamlit Cloud deployment.

## ✅ Supabase Setup

- [ ] Supabase account created
- [ ] New project created and initialized
- [ ] Database schema SQL executed (`supabase_schema.sql`)
- [ ] All tables created successfully (customers, policies, premium_records, agents, documents)
- [ ] Project URL copied
- [ ] Anon public key copied
- [ ] Optional: Sample data inserted for testing

## ✅ Local Testing

- [ ] `.streamlit/secrets.toml` created with Supabase credentials
- [ ] App runs locally: `streamlit run scripts/streamlit_app.py`
- [ ] Database connection shows "✅ Supabase Connected!" in sidebar
- [ ] Can view database stats
- [ ] Can add a test customer
- [ ] Can add a test policy
- [ ] Search functionality works

## ✅ Code Repository

- [ ] `.gitignore` file exists and includes secrets
- [ ] No sensitive data in code
- [ ] requirements.txt has all dependencies
- [ ] Git repository initialized
- [ ] All files committed to Git
- [ ] GitHub repository created
- [ ] Code pushed to GitHub

## ✅ Files Present

- [ ] `scripts/streamlit_app.py` (main app with Supabase)
- [ ] `requirements.txt` (with supabase>=2.0.0)
- [ ] `.streamlit/config.toml` (Streamlit configuration)
- [ ] `.streamlit/secrets.toml.example` (template)
- [ ] `.gitignore` (protecting secrets)
- [ ] `supabase_schema.sql` (database schema)
- [ ] `STREAMLIT_CLOUD_DEPLOYMENT.md` (deployment guide)
- [ ] `QUICK_START.md` (quick guide)

## ✅ Streamlit Cloud

- [ ] Streamlit Cloud account created
- [ ] Connected to GitHub account
- [ ] New app created
- [ ] Repository selected
- [ ] Main file path set to `scripts/streamlit_app.py`
- [ ] Secrets configured in Advanced settings
- [ ] App deployed successfully
- [ ] App URL accessible

## ✅ Post-Deployment Verification

- [ ] App loads without errors
- [ ] Database connection successful
- [ ] Can view database stats
- [ ] Can search (if data exists)
- [ ] Can add new customer
- [ ] Can add new policy
- [ ] All features working as expected

## 🔒 Security Checklist

- [ ] `.streamlit/secrets.toml` is in `.gitignore`
- [ ] Secrets.toml NOT committed to Git
- [ ] Using "anon public" key (not service role key)
- [ ] Supabase RLS considered (optional but recommended)
- [ ] No hardcoded credentials in code
- [ ] GitHub repository visibility set appropriately

## 📊 Optional Enhancements

- [ ] Custom domain configured
- [ ] App visibility set (public/private)
- [ ] Supabase database backups scheduled
- [ ] Monitoring/analytics setup
- [ ] Authentication added (if needed)

## 🚨 Common Issues - Quick Fixes

**"Failed to connect to Supabase"**
- Check URL format: `https://xxx.supabase.co` (no trailing slash)
- Verify you're using "anon public" key
- Ensure project is not paused

**"Table does not exist"**
- Run `supabase_schema.sql` in Supabase SQL Editor
- Check table names match (lowercase)

**"Module not found"**
- Ensure `supabase>=2.0.0` in requirements.txt
- Redeploy app if you updated requirements

**App shows old version**
- Clear browser cache
- Wait a few minutes for deployment
- Check "Manage app" → "Reboot app"

## 📞 Support Resources

- Streamlit Docs: https://docs.streamlit.io
- Supabase Docs: https://supabase.com/docs  
- Community: https://discuss.streamlit.io
- GitHub Issues: Create in your repo

---

## Ready to Deploy?

If all items in "Supabase Setup", "Local Testing", "Code Repository", and "Files Present" are checked, you're ready to deploy!

Go to [share.streamlit.io](https://share.streamlit.io) and click "New app"! 🚀
