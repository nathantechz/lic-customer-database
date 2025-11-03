# AM's LIC Customer Database

A complete system to manage LIC customer data with Supabase cloud database and Streamlit web interface.

## 🚀 Features

- 👥 **Customer Management** - Add, edit, search customers
- 📋 **Policy Tracking** - Manage policies with intelligent updates
- 💰 **Premium Records** - Track premium payments and due dates
- � **PDF Processing** - Automated data extraction from LIC PDFs
- 📊 **Analytics** - Compact, mobile-friendly statistics dashboard
- 🔍 **Smart Search** - Find by name, policy number, phone, agent code
- � **Intelligent Updates** - Smart FUP date and premium handling

## 🛠️ Tech Stack

- **Frontend**: Streamlit (Compact, mobile-friendly UI)
- **Backend**: Supabase (Cloud PostgreSQL)
- **PDF Processing**: pdfplumber + custom extraction logic
- **Language**: Python 3.11+

## 📦 Quick Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Supabase credentials**
   - Edit `scripts/.streamlit/secrets.toml`
   - Add your Supabase URL and API key

3. **Run the Streamlit app**
   ```bash
   cd scripts
   streamlit run streamlit_app.py
   ```
   Or double-click `scripts/start_streamlit.command`

4. **Process PDFs** (optional)
   ```bash
   cd scripts
   python3 supabase_pdf_processor.py
   ```
   Place PDFs in `data/pdfs/incoming/` before processing.

## 📁 Project Structure

```
lic_database/
├── scripts/
│   ├── streamlit_app.py           # Main Streamlit web app
│   ├── supabase_pdf_processor.py  # PDF processor with intelligent updates
│   ├── start_streamlit.command    # Launch script
│   ├── .streamlit/
│   │   ├── secrets.toml           # Supabase credentials (not in Git)
│   │   └── config.toml            # App configuration
│   └── README.md                  # Scripts documentation
├── config/
│   └── agents.json                # Agent configuration
├── data/
│   ├── pdfs/
│   │   ├── incoming/              # Drop PDFs here for processing
│   │   └── processed/             # Successfully processed PDFs
│   └── lic_local_backup.db        # Local SQLite backup (auto-created)
├── supabase_schema.sql            # Database schema
├── requirements.txt               # Python dependencies
└── README.md                      # This file
```

## 🗄️ Database Schema

The app uses Supabase (PostgreSQL) with these main tables:

1. **customers** - Customer information (name, phone, email, address, etc.)
2. **policies** - Insurance policies with FUP dates and premium amounts
3. **premium_records** - Premium payment tracking
4. **agents** - Agent details and configurations
5. **documents** - Processed PDF tracking

See `supabase_schema.sql` for complete schema.

## � PDF Processing

The `supabase_pdf_processor.py` implements intelligent update rules:

1. **New Policies**: Creates policy if not in database
2. **FUP Date**: Updates only if PDF has a later date than database
3. **Premium Amount**: Always updates (fixed premium per policy)
4. **Sum Assured**: Validates and normalizes values
5. **Agent Code**: Updates only if database value is empty

This prevents overwriting newer data with older PDFs while keeping premium amounts current.

## 🎯 Current Workflow

```
1. Place PDFs → data/pdfs/incoming/
2. Process    → python3 scripts/supabase_pdf_processor.py
                • Uploads to Supabase Cloud (Primary)
                • Backs up to Local Database (SQLite)
                • Shows success status for each
3. View/Edit  → streamlit run scripts/streamlit_app.py
```

**Dual Database System:**
- **Supabase Cloud:** Primary database (PostgreSQL, cloud-hosted)
- **Local Backup:** Automatic SQLite backup at `data/lic_local_backup.db`

**Processing Output:** After each PDF, you'll see:
```
✅ Supabase Cloud: Created/Updated policy 123456789
✅ Local Database: Created/Updated policy 123456789
🎉 SUCCESS: Policy 123456789 synced to both Cloud and Local DB
```

**Error Handling:** Files with processing errors remain in the `incoming/` folder. Error messages are displayed in the terminal. Fix the issues and rerun the processor to retry failed files.
