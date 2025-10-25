#!/usr/bin/env python3

import sqlite3
from pathlib import Path

def get_project_root():
    """Get the project root directory"""
    return Path(__file__).parent.parent

def update_schema():
    """Update the database schema to remove CURRENT_TIMESTAMP defaults"""
    
    db_path = get_project_root() / "data" / "lic_customers.db"
    
    print(f"📍 Creating updated database at: {db_path}")
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Create customers table without CURRENT_TIMESTAMP defaults
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            nickname TEXT,
            extraction_method TEXT DEFAULT 'unknown',
            created_date TIMESTAMP,
            last_updated TIMESTAMP
        )
    ''')
    
    # Create policies table without CURRENT_TIMESTAMP defaults
    cursor.execute('''
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
            created_date TIMESTAMP,
            last_updated TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
        )
    ''')
    
    # Create premium records table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS premium_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            policy_number TEXT,
            due_date TEXT,
            premium_amount REAL,
            gst_amount REAL,
            total_amount REAL,
            due_count INTEGER,
            estimated_commission REAL,
            agent_code TEXT,
            source_pdf TEXT,
            document_date TEXT,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (policy_number) REFERENCES policies (policy_number)
        )
    ''')
    
    # Create documents table for duplicate tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            file_path TEXT,
            document_type TEXT,
            content_hash TEXT,
            document_date TEXT,
            processed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create agents table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agents (
            agent_code TEXT PRIMARY KEY,
            agent_name TEXT,
            region TEXT,
            zone TEXT,
            contact_number TEXT,
            email TEXT,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    
    print("✅ Database schema updated successfully!")
    print("📝 Removed CURRENT_TIMESTAMP defaults from customers and policies tables")
    print("📝 Date tracking will now be handled explicitly by the PDF processor")

if __name__ == "__main__":
    update_schema()