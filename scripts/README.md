# Scripts Folder

This folder contains the essential scripts for the LIC Customer Database application.

## 📁 Files

### Core Application
- **`streamlit_app.py`** - Main Streamlit web application for viewing and managing customer/policy data
- **`supabase_pdf_processor.py`** - PDF processor that extracts data and syncs to Supabase

### Launch Scripts
- **`start_streamlit.command`** - Double-click to launch the Streamlit web app

### Configuration
- **`.streamlit/`** - Contains Streamlit configuration and secrets (Supabase credentials)
  - `secrets.toml` - Supabase connection details (DO NOT commit to Git)
  - `config.toml` - Streamlit app configuration

---

## 🚀 Usage

### Running the Web Application
```bash
# Option 1: Double-click
Double-click start_streamlit.command

# Option 2: Command line
cd /path/to/lic_database/scripts
streamlit run streamlit_app.py
```

### Processing PDFs
```bash
cd /path/to/lic_database/scripts
python3 supabase_pdf_processor.py
```

**Note:** PDFs should be placed in `data/pdfs/incoming/` before processing.

---

## 📊 Current Workflow

1. **Upload PDFs** → Place commission/premium PDFs in `data/pdfs/incoming/`
2. **Process PDFs** → Run `supabase_pdf_processor.py` to extract and sync data
3. **View/Manage Data** → Use Streamlit app to search, edit, and manage records

**Note:** Files with errors remain in `incoming/` folder. Error messages are displayed in terminal output. Fix the issues and run the processor again to retry.

---

## 🔧 Update Rules (supabase_pdf_processor.py)

The PDF processor follows these intelligent update rules:

1. **New Policies**: Creates policy if not in database
2. **FUP Date**: Updates only if PDF has a later date than database
3. **Premium Amount**: Always updates (fixed premium)
4. **Sum Assured**: Validates and normalizes (50 → 50,000 for specific policies)
5. **Agent Code**: Updates only if database value is empty

---

## 🗑️ Deleted Files (Cleanup on 2025-11-03)

The following obsolete files were removed as they were related to:
- SQLite database operations (migrated to Supabase)
- One-time migration scripts (already executed)
- Broken launch scripts (referenced non-existent files)

**Deleted:**
- `compare_databases.py`
- `database_setup.py`
- `database_stats.py`
- `enhanced_pdf_processor.py`
- `fix_customer_names.py`
- `fixed_database_setup.py`
- `migrate_to_supabase.py`
- `populate_documents_table.py`
- `sync_csv_to_supabase.py`
- `update_schema_dates.py`
- `ai_process.command`
- `start_app.command`

---

## 📝 Notes

- All data is now stored in **Supabase** (cloud PostgreSQL)
- Local SQLite databases are no longer used
- The Streamlit app connects directly to Supabase for real-time data
