import sqlite3
import psycopg2
from psycopg2.extras import execute_values
import os
from pathlib import Path

# Supabase connection details (replace with your values)
SUPABASE_URL = "postgresql://postgres:Salus2016$@db.nezuyvhlcryvefwixypy.supabase.co:5432/postgres"
SUPABASE_PASSWORD = "Salus2016$"

def get_sqlite_connection():
    db_path = Path(__file__).parent.parent / "data" / "lic_customers.db"
    return sqlite3.connect(str(db_path))

def get_supabase_connection():
    return psycopg2.connect(SUPABASE_URL)

def migrate_table(cursor_sqlite, conn_pg, table_name, columns):
    print(f"Migrating {table_name}...")
    cursor_sqlite.execute(f"SELECT {', '.join(columns)} FROM {table_name}")
    rows = cursor_sqlite.fetchall()
    
    if rows:
        cursor_pg = conn_pg.cursor()
        # Create table if not exists (adjust schema as needed)
        if table_name == "customers":
            cursor_pg.execute('''
                CREATE TABLE IF NOT EXISTS customers (
                    customer_id SERIAL PRIMARY KEY,
                    customer_name TEXT NOT NULL,
                    phone_number TEXT,
                    alt_phone_number TEXT,
                    email TEXT,
                    aadhaar_number TEXT,
                    date_of_birth TEXT,
                    occupation TEXT,
                    full_address TEXT,
                    google_maps_link TEXT,
                    customer_photo_path TEXT,
                    aadhaar_image_path TEXT,
                    notes TEXT,
                    extraction_method TEXT DEFAULT 'unknown',
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        elif table_name == "policies":
            cursor_pg.execute('''
                CREATE TABLE IF NOT EXISTS policies (
                    policy_number TEXT PRIMARY KEY,
                    customer_id INTEGER,
                    agent_code TEXT,
                    agent_name TEXT,
                    plan_type TEXT,
                    plan_name TEXT,
                    date_of_commencement TEXT,
                    premium_mode TEXT,
                    current_fup_date TEXT,
                    sum_assured REAL,
                    premium_amount REAL,
                    status TEXT DEFAULT 'Active',
                    maturity_date TEXT,
                    policy_term INTEGER,
                    premium_paying_term INTEGER,
                    extraction_method TEXT DEFAULT 'unknown',
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
                )
            ''')
        # Add other tables similarly (premium_records, agents, documents)
        
        # Insert data
        query = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES %s ON CONFLICT DO NOTHING"
        execute_values(cursor_pg, query, rows)
        conn_pg.commit()
        print(f"Migrated {len(rows)} rows to {table_name}")

def main():
    conn_sqlite = get_sqlite_connection()
    conn_pg = get_supabase_connection()
    
    cursor_sqlite = conn_sqlite.cursor()
    
    # Migrate each table
    migrate_table(cursor_sqlite, conn_pg, "customers", ["customer_id", "customer_name", "phone_number", "alt_phone_number", "email", "aadhaar_number", "date_of_birth", "occupation", "full_address", "google_maps_link", "customer_photo_path", "aadhaar_image_path", "notes", "extraction_method", "created_date", "last_updated"])
    migrate_table(cursor_sqlite, conn_pg, "policies", ["policy_number", "customer_id", "agent_code", "agent_name", "plan_type", "plan_name", "date_of_commencement", "premium_mode", "current_fup_date", "sum_assured", "premium_amount", "status", "maturity_date", "policy_term", "premium_paying_term", "extraction_method", "created_date", "last_updated"])
    # Add migrations for premium_records, agents, documents
    
    conn_sqlite.close()
    conn_pg.close()
    print("Migration complete!")

if __name__ == "__main__":
    main()
