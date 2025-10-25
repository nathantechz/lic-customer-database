# Supabase Setup Guide

## Quick Setup Steps

### 1. Get Your Supabase Credentials

1. Go to [https://supabase.com/dashboard](https://supabase.com/dashboard)
2. Sign in or create a new account
3. Select your existing project or create a new one
4. Go to **Settings** → **API**
5. You'll see two important values:
   - **Project URL** (e.g., `https://abcdefghijk.supabase.co`)
   - **anon public key** (a long string starting with `eyJ...`)

### 2. Configure the Secrets File

1. Open the file: `scripts/.streamlit/secrets.toml`
2. Replace the placeholder values:

```toml
[supabase]
url = "https://your-actual-project-url.supabase.co"
key = "your-actual-anon-public-key-here"
```

### 3. Verify Your Database Tables

Make sure your Supabase project has these tables:
- `customers`
- `policies`
- `premium_records`
- `agents`
- `documents`

You can check this in: **Table Editor** section of your Supabase dashboard

### 4. Restart the Streamlit App

After configuring the secrets file, restart your Streamlit app:

```bash
cd scripts
streamlit run streamlit_app.py
```

## Troubleshooting

### "No secrets found" error
- Make sure `scripts/.streamlit/secrets.toml` exists
- Check that the file is in the correct location
- Verify the TOML syntax is correct (no extra quotes, proper formatting)

### "Connection Failed" error
- Verify your Project URL is correct
- Verify your anon key is correct
- Check that your Supabase project is active
- Ensure you have internet connection

### "Table not found" errors
- Run the SQL schema in your Supabase SQL Editor
- The schema file should be in `supabase_schema.sql`
- Go to **SQL Editor** in Supabase dashboard and run the schema

## Security Notes

⚠️ **IMPORTANT:**
- Never commit `secrets.toml` to git (it's already in .gitignore)
- Never share your anon public key publicly
- The anon key is safe for client-side use but keep it secure
- For production, use Row Level Security (RLS) in Supabase

## Testing the Connection

Once configured, the app will:
1. Show "✅ Supabase Connected!" in the sidebar
2. Display database statistics on the main page
3. Allow you to search and manage customers

If you see connection errors, double-check your credentials in the secrets.toml file.
