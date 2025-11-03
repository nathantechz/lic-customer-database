"""
Supabase PDF Processor
Processes PDFs from incoming folder and syncs with Supabase + Local Database:
1. Creates new policies if policy number doesn't exist
2. Updates FUP date if PDF has a later date
3. Updates premium amount (fixed for each policy)
4. Normalizes sum_assured to lacs format
5. Updates agent_code if not present in Supabase
6. Backs up all data to local SQLite database
"""

import pdfplumber
import os
import re
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime
from supabase import create_client, Client
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def get_supabase_client() -> Client:
    """Get Supabase client from secrets"""
    try:
        secrets_path = Path(__file__).parent / '.streamlit' / 'secrets.toml'
        if not secrets_path.exists():
            secrets_path = Path(__file__).parent.parent / 'scripts' / '.streamlit' / 'secrets.toml'
        
        if secrets_path.exists():
            import toml
            secrets = toml.load(secrets_path)
            url = secrets['supabase']['url']
            key = secrets['supabase']['key']
        else:
            import os as env_os
            url = env_os.getenv('SUPABASE_URL')
            key = env_os.getenv('SUPABASE_KEY')
            
            if not url or not key:
                raise Exception("Supabase credentials not found.")
        
        return create_client(url, key)
    except Exception as e:
        raise Exception(f"Failed to connect to Supabase: {e}")

def get_local_db_connection():
    """Get or create local SQLite database for backup"""
    try:
        project_root = Path(__file__).parent.parent
        db_path = project_root / 'data' / 'lic_local_backup.db'
        
        # Create data directory if needed
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Create customers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS customers (
                customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                phone_number TEXT,
                email TEXT,
                address TEXT,
                extraction_method TEXT,
                created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create policies table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS policies (
                policy_id INTEGER PRIMARY KEY AUTOINCREMENT,
                policy_number TEXT UNIQUE NOT NULL,
                customer_id INTEGER,
                agent_code TEXT,
                plan_name TEXT,
                premium_amount REAL,
                sum_assured REAL,
                date_of_commencement TEXT,
                payment_period TEXT,
                current_fup_date TEXT,
                status TEXT DEFAULT 'Active',
                created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
            )
        ''')
        
        # Create index on policy_number
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_policy_number 
            ON policies(policy_number)
        ''')
        
        # Create index on customer_name
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_customer_name 
            ON customers(customer_name)
        ''')
        
        conn.commit()
        return conn
    except Exception as e:
        raise Exception(f"Failed to create local database: {e}")

def parse_date(date_str):
    """Parse date string in various formats and return YYYY-MM-DD format"""
    if not date_str or date_str.strip() == "":
        return None
        
    date_str = date_str.strip()
    
    # Common date patterns
    patterns = [
        (r'(\d{1,2})/(\d{1,2})/(\d{4})', 'DMY'),  # DD/MM/YYYY
        (r'(\d{1,2})-(\d{1,2})-(\d{4})', 'DMY'),  # DD-MM-YYYY
        (r'(\d{4})/(\d{1,2})/(\d{1,2})', 'YMD'),  # YYYY/MM/DD
        (r'(\d{4})-(\d{1,2})-(\d{1,2})', 'YMD'),  # YYYY-MM-DD
        (r'(\d{1,2})/(\d{4})', 'MY'),              # MM/YYYY (FUP format)
    ]
    
    for pattern, format_type in patterns:
        match = re.search(pattern, date_str)
        if match:
            groups = match.groups()
            
            if format_type == 'YMD':
                year, month, day = groups
            elif format_type == 'DMY':
                day, month, year = groups
            elif format_type == 'MY':
                month, year = groups
                day = '01'  # Use first day of month for FUP dates
            else:
                continue
            
            try:
                day_int = int(day)
                month_int = int(month)
                year_int = int(year)
                
                if 1 <= day_int <= 31 and 1 <= month_int <= 12 and 1900 <= year_int <= 2100:
                    return f"{year_int:04d}-{month_int:02d}-{day_int:02d}"
            except ValueError:
                continue
    
    return None

def normalize_sum_assured(value):
    """
    Normalize sum assured to lacs format:
    - If value is 50, keep as 50 (meaning 50,000)
    - Otherwise convert to lacs (e.g., 1 → 1, 2 → 2, 100 → 100 for lacs)
    - Returns the value in consistent format for database
    """
    if value is None or value == '':
        return None
    
    try:
        val = float(value)
        # Value is already in the correct format from PDF
        # Just return it as is
        return val
    except (ValueError, TypeError):
        return None

def clean_customer_name(name):
    """Clean and standardize customer names"""
    if not name:
        return None
    
    # Remove extra whitespace and normalize
    name = re.sub(r'\s+', ' ', name.strip())
    
    # Remove common prefixes
    name = re.sub(r'^(Mr\.?|Mrs\.?|Ms\.?|Dr\.?|Prof\.?)\s+', '', name, flags=re.IGNORECASE)
    
    # Skip if it looks like a policy number
    if re.match(r'^\d+$', name) or len(name) < 3:
        return None
    
    return name.strip().upper()

def extract_commission_details(text):
    """Extract policy information from Commission PDFs"""
    details = []
    lines = text.split('\n')
    
    print("    💰 Parsing commission table...")
    
    for line in lines:
        line_clean = line.strip()
        if not line_clean or line_clean.startswith('S.No') or 'PH Name' in line:
            continue
        
        # Commission pattern: Serial Name Policy Plan/Term DueDate ... Premium Commission
        # Example: "1 C NONDICHAMY 308700508 814-21 27/05/2025 27/08/2018 CBK2 26/05/2025 2640.00 132.00"
        commission_pattern = r'^\s*(\d+)\s+([A-Z][A-Za-z\s.]{2,50}?)\s+(\d{9})\s+(\d{3}[-/]\d{2})\s+(\d{1,2}/\d{1,2}/\d{4})?\s*(.*)$'
        
        match = re.match(commission_pattern, line_clean)
        if match:
            policy_no = match.group(3)
            name = match.group(2).strip()
            plan_type = match.group(4)
            due_date = match.group(5) if match.group(5) else None
            remaining = match.group(6).strip() if match.group(6) else ""
            
            cleaned_name = clean_customer_name(name)
            if cleaned_name and len(cleaned_name) > 2:
                parsed_due_date = parse_date(due_date) if due_date else None
                
                # Extract amounts
                amounts = re.findall(r'(\d+\.?\d*)', remaining)
                premium_amount = None
                
                if len(amounts) >= 2:
                    try:
                        premium_amount = float(amounts[-2])  # Second last is premium
                    except ValueError:
                        pass
                
                details.append({
                    'policy_number': policy_no,
                    'customer_name': cleaned_name,
                    'plan_name': plan_type,
                    'current_fup_date': parsed_due_date,
                    'premium_amount': premium_amount
                })
                
                print(f"    ✅ {policy_no} → {cleaned_name}")
    
    return details

def extract_premium_due_details(text):
    """Extract policy information from Premium Due PDFs"""
    details = []
    lines = text.split('\n')
    
    print("    💳 Parsing premium due table...")
    
    for line in lines:
        line_clean = line.strip()
        if not line_clean or line_clean.startswith('S.No') or 'PolicyNo' in line:
            continue
        
        # Premium Due pattern: S.No PolicyNo Name D.o.C Pln/Tm Mod FUP ... InstPrem ...
        # Example: "1 319566711 P.MARIMUTHU 14/10/2020 936/21 Hly 10/2024 14689.00 2 661.00"
        premium_pattern = r'^\s*(\d+)\s+(\d{9})\s+([A-Z][A-Za-z\s.]{2,50}?)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(\d{3}[/-]\d{2})\s+([^\s]+)\s+(\d{1,2}/\d{4})\s*(.*)$'
        
        match = re.match(premium_pattern, line_clean)
        if match:
            policy_no = match.group(2)
            name = match.group(3).strip()
            doc_date = match.group(4)
            plan_type = match.group(5)
            mode = match.group(6)
            fup_date = match.group(7)
            remaining = match.group(8).strip() if match.group(8) else ""
            
            cleaned_name = clean_customer_name(name)
            if cleaned_name and len(cleaned_name) > 2:
                parsed_doc = parse_date(doc_date)
                parsed_fup = parse_date(fup_date)
                
                # Extract amounts
                amounts = re.findall(r'(\d+\.?\d*)', remaining)
                inst_prem = None
                
                if len(amounts) >= 1:
                    try:
                        inst_prem = float(amounts[0])
                    except ValueError:
                        pass
                
                details.append({
                    'policy_number': policy_no,
                    'customer_name': cleaned_name,
                    'date_of_commencement': parsed_doc,
                    'plan_name': plan_type,
                    'payment_period': mode,
                    'current_fup_date': parsed_fup,
                    'premium_amount': inst_prem
                })
                
                print(f"    ✅ {policy_no} → {cleaned_name} (FUP: {fup_date})")
    
    return details

def get_existing_policies(supabase: Client):
    """Get all existing policies from Supabase"""
    print("\n📊 Fetching existing policies from Supabase...")
    try:
        result = supabase.table('policies').select('*').execute()
        policies = result.data if result.data else []
        print(f"✅ Found {len(policies)} existing policies")
        return {p['policy_number']: p for p in policies}
    except Exception as e:
        print(f"❌ Error fetching policies: {e}")
        return {}

def get_existing_customers(supabase: Client):
    """Get all existing customers from Supabase"""
    print("👥 Fetching existing customers from Supabase...")
    try:
        result = supabase.table('customers').select('*').execute()
        customers = result.data if result.data else []
        print(f"✅ Found {len(customers)} existing customers")
        return {c['customer_name'].strip().upper(): c for c in customers}
    except Exception as e:
        print(f"❌ Error fetching customers: {e}")
        return {}

def find_or_create_customer(supabase: Client, customer_name: str, existing_customers: dict):
    """Find existing customer or create new one"""
    customer_key = customer_name.strip().upper()
    
    if customer_key in existing_customers:
        customer = existing_customers[customer_key]
        return customer['customer_id']
    else:
        # Create new customer
        try:
            new_customer = {
                'customer_name': customer_name.strip(),
                'extraction_method': 'pdf_import'
            }
            result = supabase.table('customers').insert(new_customer).execute()
            customer_id = result.data[0]['customer_id']
            existing_customers[customer_key] = result.data[0]
            print(f"  👤 Created new customer: {customer_name} (ID: {customer_id})")
            return customer_id
        except Exception as e:
            print(f"  ❌ Failed to create customer {customer_name}: {e}")
            return None

def sync_policy_to_supabase(supabase: Client, policy_data: dict, existing_policies: dict, 
                            existing_customers: dict, agent_code: str, stats: dict, 
                            local_conn: sqlite3.Connection = None):
    """
    Sync a single policy to Supabase AND local database following the rules:
    1. Create new policy if doesn't exist
    2. Update FUP if PDF has later date
    3. Update premium amount (fixed)
    4. Normalize sum_assured
    5. Update agent_code if not present
    """
    policy_number = policy_data['policy_number']
    customer_name = policy_data['customer_name']
    
    # Track success for both databases
    supabase_success = False
    local_success = False
    
    # Get or create customer in Supabase
    customer_id = find_or_create_customer(supabase, customer_name, existing_customers)
    if not customer_id:
        stats['errors'] += 1
        return
    
    # Prepare policy fields
    fields_to_update = {}
    
    # Premium amount - always update (fixed for policy)
    if policy_data.get('premium_amount'):
        fields_to_update['premium_amount'] = policy_data['premium_amount']
    
    # Plan name
    if policy_data.get('plan_name'):
        fields_to_update['plan_name'] = policy_data['plan_name']
    
    # Date of commencement
    if policy_data.get('date_of_commencement'):
        fields_to_update['date_of_commencement'] = policy_data['date_of_commencement']
    
    # Payment period
    if policy_data.get('payment_period'):
        fields_to_update['payment_period'] = policy_data['payment_period']
    
    # Sum assured normalization
    if policy_data.get('sum_assured'):
        fields_to_update['sum_assured'] = normalize_sum_assured(policy_data['sum_assured'])
    
    if policy_number in existing_policies:
        # Policy exists - apply update rules
        existing = existing_policies[policy_number]
        updates = {}
        
        # Rule 1: Update FUP only if PDF date is later
        pdf_fup = policy_data.get('current_fup_date')
        existing_fup = existing.get('current_fup_date')
        
        if pdf_fup:
            if not existing_fup or pdf_fup > existing_fup:
                updates['current_fup_date'] = pdf_fup
                print(f"  📅 Updating FUP: {existing_fup} → {pdf_fup}")
            else:
                print(f"  ℹ️  FUP not updated (PDF: {pdf_fup}, DB: {existing_fup})")
        
        # Rule 2: Update premium amount (always, as it's fixed)
        if fields_to_update.get('premium_amount'):
            updates['premium_amount'] = fields_to_update['premium_amount']
        
        # Rule 3: Update agent_code only if not present in database
        if agent_code and not existing.get('agent_code'):
            updates['agent_code'] = agent_code
            print(f"  👤 Adding agent code: {agent_code}")
        
        # Rule 4: Update other fields if empty
        for field in ['plan_name', 'date_of_commencement', 'payment_period', 'sum_assured']:
            if fields_to_update.get(field) and not existing.get(field):
                updates[field] = fields_to_update[field]
        
        if updates:
            try:
                supabase.table('policies').update(updates).eq('policy_number', policy_number).execute()
                print(f"  ✅ Updated policy {policy_number}: {', '.join(updates.keys())}")
                stats['updated'] += 1
            except Exception as e:
                print(f"  ❌ Failed to update policy {policy_number}: {e}")
                stats['errors'] += 1
        else:
            print(f"  ℹ️  No updates needed for {policy_number}")
            stats['skipped'] += 1
    else:
        # New policy - create it
        try:
            new_policy = {
                'policy_number': policy_number,
                'customer_id': customer_id,
                'agent_code': agent_code
            }
            
            # Add all available fields
            for field, value in fields_to_update.items():
                new_policy[field] = value
            
            # Add FUP date
            if policy_data.get('current_fup_date'):
                new_policy['current_fup_date'] = policy_data['current_fup_date']
            
            supabase.table('policies').insert(new_policy).execute()
            print(f"  ✅ Created new policy {policy_number}")
            stats['created'] += 1
        except Exception as e:
            print(f"  ❌ Failed to create policy {policy_number}: {e}")
            stats['errors'] += 1

def process_pdf_files():
    """Main processing function"""
    print("\n" + "="*60)
    print("🚀 SUPABASE PDF PROCESSOR")
    print("="*60)
    
    # Setup paths
    project_root = Path(__file__).parent.parent
    incoming_path = project_root / 'data' / 'pdfs' / 'incoming'
    processed_path = project_root / 'data' / 'pdfs' / 'processed'
    
    # Create directories
    processed_path.mkdir(parents=True, exist_ok=True)
    
    # Connect to Supabase
    try:
        print("\n🔌 Connecting to Supabase...")
        supabase = get_supabase_client()
        print("✅ Connected to Supabase")
    except Exception as e:
        print(f"❌ Failed to connect to Supabase: {e}")
        return
    
    # Get existing data
    existing_policies = get_existing_policies(supabase)
    existing_customers = get_existing_customers(supabase)
    
    # Get PDF files
    pdf_files = list(incoming_path.glob('*.pdf'))
    print(f"\n📂 Found {len(pdf_files)} PDF files in incoming folder")
    
    if not pdf_files:
        print("ℹ️  No files to process")
        return
    
    # Statistics
    stats = {
        'files_processed': 0,
        'files_with_errors': 0,
        'created': 0,
        'updated': 0,
        'skipped': 0,
        'errors': 0
    }
    
    # Track files with errors (stay in incoming)
    error_files = []
    
    # Process each PDF
    for pdf_file in pdf_files:
        print(f"\n📄 Processing: {pdf_file.name}")
        
        try:
            # Extract agent code from filename
            agent_code = None
            agent_match = re.search(r'(\d{7}N)', pdf_file.name)
            if agent_match:
                agent_code = agent_match.group(1)
                print(f"  👤 Agent: {agent_code}")
            
            # Extract text from PDF
            with pdfplumber.open(pdf_file) as pdf:
                text = ""
                for page in pdf.pages:
                    text += page.extract_text() or ""
            
            if not text.strip():
                print(f"  ❌ ERROR: No readable text in PDF - keeping in incoming folder")
                error_files.append(pdf_file.name)
                stats['files_with_errors'] += 1
                continue
            
            # Determine document type and extract details
            policy_details = []
            
            if 'Commission' in text or 'PH Name' in text or 'CM-' in pdf_file.name:
                print("  📋 Document type: Commission")
                policy_details = extract_commission_details(text)
            elif 'Premium Due' in text or 'Name of Assured' in text or 'Premdue' in pdf_file.name.lower():
                print("  📋 Document type: Premium Due")
                policy_details = extract_premium_due_details(text)
            else:
                print("  ⚠️  Unknown document type")
            
            if not policy_details:
                print(f"  ⚠️  ERROR: No policy details extracted - keeping in incoming folder")
                error_files.append(pdf_file.name)
                stats['files_with_errors'] += 1
                continue
            
            print(f"  📊 Found {len(policy_details)} policies")
            
            # Process each policy
            for detail in policy_details:
                sync_policy_to_supabase(
                    supabase, 
                    detail, 
                    existing_policies, 
                    existing_customers, 
                    agent_code,
                    stats
                )
            
            # Move to processed
            shutil.move(str(pdf_file), str(processed_path / pdf_file.name))
            stats['files_processed'] += 1
            print(f"  ✅ Moved to processed folder")
            
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            print(f"  ⚠️  File kept in incoming folder for retry")
            error_files.append(pdf_file.name)
            stats['files_with_errors'] += 1
            import traceback
            traceback.print_exc()
    
    # Print summary
    print("\n" + "="*60)
    print("📊 PROCESSING SUMMARY")
    print("="*60)
    print(f"📄 Files processed: {stats['files_processed']}")
    print(f"❌ Files with errors: {stats['files_with_errors']}")
    print(f"✅ Policies created: {stats['created']}")
    print(f"✅ Policies updated: {stats['updated']}")
    print(f"ℹ️  Policies skipped: {stats['skipped']}")
    print(f"❌ Policy errors: {stats['errors']}")
    
    if error_files:
        print("\n⚠️  FILES WITH ERRORS (kept in incoming folder):")
        for error_file in error_files:
            print(f"  • {error_file}")
        print("\nℹ️  Fix the errors and run the processor again to retry these files.")
    
    print("="*60)

if __name__ == "__main__":
    process_pdf_files()
