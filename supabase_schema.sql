-- LIC Customer Database Schema for Supabase
-- Run this SQL in your Supabase SQL Editor to create all necessary tables

-- Enable UUID extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Drop existing tables if needed (for clean install)
-- DROP TABLE IF EXISTS documents CASCADE;
-- DROP TABLE IF EXISTS premium_records CASCADE;
-- DROP TABLE IF EXISTS policies CASCADE;
-- DROP TABLE IF EXISTS customers CASCADE;
-- DROP TABLE IF EXISTS agents CASCADE;

-- Customers table
CREATE TABLE IF NOT EXISTS customers (
    customer_id BIGSERIAL PRIMARY KEY,
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
    created_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Add nickname column if it doesn't exist (for existing databases)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'customers' AND column_name = 'nickname') THEN
        ALTER TABLE customers ADD COLUMN nickname TEXT;
    END IF;
END $$;

-- Policies table
CREATE TABLE IF NOT EXISTS policies (
    policy_number TEXT PRIMARY KEY,
    customer_id BIGINT REFERENCES customers(customer_id) ON DELETE CASCADE,
    agent_code TEXT,
    agent_name TEXT,
    plan_type TEXT,
    plan_name TEXT,
    date_of_commencement TEXT,
    premium_mode TEXT,
    current_fup_date TEXT,
    sum_assured NUMERIC,
    premium_amount NUMERIC,
    status TEXT DEFAULT 'Active',
    maturity_date TEXT,
    policy_term INTEGER,
    premium_paying_term INTEGER,
    last_payment_date TEXT,
    extraction_method TEXT DEFAULT 'unknown',
    created_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Premium records table
CREATE TABLE IF NOT EXISTS premium_records (
    id BIGSERIAL PRIMARY KEY,
    policy_number TEXT REFERENCES policies(policy_number) ON DELETE CASCADE,
    due_date TEXT,
    premium_amount NUMERIC,
    gst_amount NUMERIC,
    total_amount NUMERIC,
    estimated_commission NUMERIC,
    due_count INTEGER,
    status TEXT DEFAULT 'Due',
    agent_code TEXT,
    processed_date TEXT,
    source_pdf TEXT,
    payment_date TEXT,
    payment_notes TEXT,
    updated_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Agents table
CREATE TABLE IF NOT EXISTS agents (
    agent_code TEXT PRIMARY KEY,
    agent_name TEXT,
    branch_code TEXT,
    relationship TEXT,
    phone TEXT,
    email TEXT,
    active BOOLEAN DEFAULT TRUE
);

-- Documents table for PDF tracking
CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    policy_number TEXT REFERENCES policies(policy_number) ON DELETE SET NULL,
    document_type TEXT,
    file_name TEXT,
    file_path TEXT,
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better query performance
DROP INDEX IF EXISTS idx_customers_name;
DROP INDEX IF EXISTS idx_customers_phone;
DROP INDEX IF EXISTS idx_customers_email;
DROP INDEX IF EXISTS idx_customers_aadhaar;
DROP INDEX IF EXISTS idx_customers_nickname;
DROP INDEX IF EXISTS idx_policies_customer;
DROP INDEX IF EXISTS idx_policies_agent;
DROP INDEX IF EXISTS idx_policies_status;
DROP INDEX IF EXISTS idx_premium_records_policy;
DROP INDEX IF EXISTS idx_premium_records_due_date;

CREATE INDEX idx_customers_name ON customers(customer_name);
CREATE INDEX idx_customers_phone ON customers(phone_number);
CREATE INDEX idx_customers_email ON customers(email);
CREATE INDEX idx_customers_aadhaar ON customers(aadhaar_number);
CREATE INDEX idx_customers_nickname ON customers(nickname);
CREATE INDEX idx_policies_customer ON policies(customer_id);
CREATE INDEX idx_policies_agent ON policies(agent_code);
CREATE INDEX idx_policies_status ON policies(status);
CREATE INDEX idx_premium_records_policy ON premium_records(policy_number);
CREATE INDEX idx_premium_records_due_date ON premium_records(due_date);

-- Enable Row Level Security (RLS) - Optional, uncomment if needed
-- ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE policies ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE premium_records ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

-- Create policies for RLS (adjust as needed for your security requirements)
-- Example: Allow all operations for authenticated users
-- CREATE POLICY "Allow all for authenticated users" ON customers FOR ALL USING (auth.role() = 'authenticated');
-- CREATE POLICY "Allow all for authenticated users" ON policies FOR ALL USING (auth.role() = 'authenticated');
-- CREATE POLICY "Allow all for authenticated users" ON premium_records FOR ALL USING (auth.role() = 'authenticated');
-- CREATE POLICY "Allow all for authenticated users" ON agents FOR ALL USING (auth.role() = 'authenticated');
-- CREATE POLICY "Allow all for authenticated users" ON documents FOR ALL USING (auth.role() = 'authenticated');

-- Insert sample agents (optional)
INSERT INTO agents (agent_code, agent_name, branch_code, relationship, active)
VALUES 
    ('0089174N', 'Sample Agent 1', '74N', 'self', TRUE),
    ('0163674N', 'Sample Agent 2', '74N', 'self', TRUE)
ON CONFLICT (agent_code) DO NOTHING;

-- Create a function to automatically update last_updated timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_updated = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers to automatically update last_updated
DROP TRIGGER IF EXISTS update_customers_updated_at ON customers;
DROP TRIGGER IF EXISTS update_policies_updated_at ON policies;

CREATE TRIGGER update_customers_updated_at BEFORE UPDATE ON customers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_policies_updated_at BEFORE UPDATE ON policies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
