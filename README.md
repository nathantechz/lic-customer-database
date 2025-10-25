# LIC Customer Database System

A cloud-ready system to manage LIC customer data with Supabase backend and Streamlit web interface.

## ☁️ Cloud Deployment

This app is ready to deploy to Streamlit Cloud!

**Quick Start**: See `QUICK_START.md` (10 minutes to deploy)  
**Full Guide**: See `STREAMLIT_CLOUD_DEPLOYMENT.md`  
**Checklist**: See `DEPLOYMENT_CHECKLIST.md`

## 🚀 Features

- 👥 Customer management with search
- 📋 Policy tracking and management
- 💰 Premium payment records
- 🔄 Duplicate detection
- 📊 Database statistics and analytics
- ✏️ Add/edit customers and policies
- 🏷️ Nickname support for easy identification
- 🗺️ Google Maps integration for locations

## 🛠️ Tech Stack

- **Frontend**: Streamlit
- **Backend**: Supabase (PostgreSQL)
- **Deployment**: Streamlit Cloud
- **Language**: Python 3.7+

## 📦 Quick Setup

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/lic-customer-database.git
   cd lic-customer-database
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up Supabase**
   - Create account at [supabase.com](https://supabase.com)
   - Create new project
   - Run `supabase_schema.sql` in SQL Editor
   - Copy Project URL and anon public key

4. **Configure secrets**
   - Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`
   - Add your Supabase credentials

5. **Run the app**
   ```bash
   streamlit run scripts/streamlit_app.py
   ```

### Cloud Deployment

See `QUICK_START.md` for step-by-step deployment to Streamlit Cloud.

## 📁 Project Structure

```
lic_database/
├── scripts/
│   └── streamlit_app.py          # Main Streamlit app (Supabase-enabled)
├── .streamlit/
│   ├── config.toml                # Streamlit configuration
│   ├── secrets.toml               # Local secrets (not in Git)
│   └── secrets.toml.example       # Secrets template
├── config/
│   └── agents.json                # Agent configuration
├── supabase_schema.sql            # Database schema for Supabase
├── requirements.txt               # Python dependencies
├── QUICK_START.md                 # 10-minute deployment guide
├── STREAMLIT_CLOUD_DEPLOYMENT.md  # Full deployment guide
├── DEPLOYMENT_CHECKLIST.md        # Pre-deployment checklist
├── MIGRATION_SUMMARY.md           # Migration details
└── README.md                      # This file
```

## 🗄️ Database Schema

The app uses 5 main tables in Supabase:

1. **customers** - Customer information
2. **policies** - Insurance policies  
3. **premium_records** - Premium payments
4. **agents** - Agent details
5. **documents** - Document tracking

See `supabase_schema.sql` for complete schema.

## 🔐 Security

- Secrets stored in `.streamlit/secrets.toml` (not committed)
- Supabase Row Level Security (RLS) support
- Environment-aware configuration
- No hardcoded credentials

## 📊 Features

### Customer Management
- Search by name, phone, email, Aadhaar, policy number
- Add new customers with validation
- Edit customer details
- Nickname support
- Duplicate detection
- Google Maps integration

### Policy Management
- View all policies for a customer
- Add new policies
- Edit policy details
- Track premium payments
- Status tracking (Active, Lapsed, Matured, Surrendered)

### Analytics
- Total customers count
- Total policies count
- Real vs generic names statistics
- Extraction method breakdown

## 💻 Development

### Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Configure Supabase credentials in .streamlit/secrets.toml

# Run app
streamlit run scripts/streamlit_app.py
```

### Making Changes

1. Edit `scripts/streamlit_app.py`
2. Test locally
3. Commit and push to GitHub
4. Streamlit Cloud auto-deploys

## 🚀 Deployment

### Prerequisites
- Supabase account (free)
- GitHub account
- Streamlit Cloud account (free)

### Steps
1. Set up Supabase database (3 min)
2. Test locally (2 min)
3. Push to GitHub (2 min)
4. Deploy on Streamlit Cloud (3 min)

**Total time**: ~10 minutes

See `QUICK_START.md` for detailed steps.

## 🆘 Support

- **Documentation**: Check the `.md` files in this repo
- **Issues**: Create an issue on GitHub
- **Streamlit Docs**: https://docs.streamlit.io
- **Supabase Docs**: https://supabase.com/docs

## 📝 Requirements

- Python 3.7+
- Internet connection (for Supabase)
- Modern web browser

## 💰 Costs

### Free Tier (Sufficient for personal use)
- **Streamlit Cloud**: Unlimited public apps
- **Supabase**: 500MB DB, 2GB bandwidth/month
- **GitHub**: Free for public repos

### Paid (If needed)
- **Streamlit Cloud**: $20/month for private apps
- **Supabase**: Starting at $25/month (8GB DB, 100GB bandwidth)

## 🎯 Roadmap

- [ ] Authentication system
- [ ] Email notifications for premium dues
- [ ] Dashboard with charts
- [ ] Mobile app
- [ ] Automated backups
- [ ] PDF generation for reports

## 📜 License

MIT License - feel free to use for personal or commercial projects

## 🙏 Acknowledgments

- Streamlit team for the amazing framework
- Supabase for the excellent backend platform
- LIC for the business opportunity

---

**Ready to deploy?** Start with `QUICK_START.md`! 🚀
