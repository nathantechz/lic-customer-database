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
    Normalize sum assured to actual rupee values with minimum ₹50,000:
    - Any value less than 1000 is assumed to be abbreviated
    - Values < 50 → multiply by 100,000 (lacs) - e.g., 1 → 1,00,000, 2 → 2,00,000, 5 → 5,00,000
    - Values 50-999 → multiply by 1,000 (thousands) - e.g., 50 → 50,000, 100 → 1,00,000
    - Values >= 1000 → keep as is (already in proper format)
    - Minimum value after conversion: ₹50,000
    """
    if value is None or value == '':
        return None
    
    try:
        val = float(value)
        
        # If value is less than 50, it's in lacs
        if 0 < val < 50:
            converted = val * 100000  # 1 → 1,00,000 (1 lac), 5 → 5,00,000
        
        # If value is between 50 and 999, it's in thousands
        elif 50 <= val < 1000:
            converted = val * 1000  # 50 → 50,000, 100 → 1,00,000
        
        # If value is 1000 or more, assume it's already in proper format
        else:
            converted = val
        
        # Ensure minimum sum assured of ₹50,000
        if converted < 50000:
            print(f"⚠️  Warning: Sum assured {val} → ₹{converted:,.2f} is below minimum ₹50,000. Setting to ₹50,000")
            return 50000
        
        return converted
            
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
    
    # First, try to extract agent code from the header
    agent_code_from_header = None
    for line in lines[:20]:  # Check first 20 lines for agent code
        agent_match = re.search(r'Agent\s+Code\s*:\s*LIC(\d{7}N)', line, re.IGNORECASE)
        if agent_match:
            agent_code_from_header = agent_match.group(1)
            print(f"    📋 Found Agent Code in header: {agent_code_from_header}")
            break
    
    for line in lines:
        line_clean = line.strip()
        if not line_clean or line_clean.startswith('S.No') or 'P/H Name' in line or 'Agent commmision' in line:
            continue
        
        # Commission pattern: Serial P/H_Name PolicyNo Pln/Tm DueDate ... Premium Commission
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
                
                # Extract amounts - Premium is before Commission
                # Format: ... FUP_Date Premium Commission
                # Example: "11/10/2025 812.00 48.72"
                # Look for decimal amounts only (not dates)
                amounts = re.findall(r'\b(\d+\.\d{2})\b', remaining)
                premium_amount = None
                
                if len(amounts) >= 2:
                    try:
                        # Premium is second-to-last, commission is last
                        premium_amount = float(amounts[-2])
                    except ValueError:
                        pass
                elif len(amounts) == 1:
                    # Only one amount - assume it's premium
                    try:
                        premium_amount = float(amounts[0])
                    except ValueError:
                        pass
                
                details.append({
                    'policy_number': policy_no,
                    'customer_name': cleaned_name,
                    'plan_name': plan_type,
                    'current_fup_date': parsed_due_date,
                    'premium_amount': premium_amount,
                    'agent_code_from_pdf': agent_code_from_header  # Store agent code from header
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
                            local_conn: sqlite3.Connection = None, is_commission_pdf: bool = False):
    """
    Sync a single policy to Supabase AND local database following the rules:
    1. Create new policy if doesn't exist
    2. Update FUP if PDF has later date
    3. Update premium amount (fixed)
    4. Normalize sum_assured
    5. Update agent_code if not present
    
    Commission PDF specific rules:
    - Use agent code from PDF header (stored in policy_data['agent_code_from_pdf'])
    - Customer name from P/H Name column is final - update DB if different
    - Plan type (pln/tm) from PDF is final - always update
    - Premium amount from "Premium" column is final - always update
    """
    policy_number = policy_data['policy_number']
    customer_name = policy_data['customer_name']
    
    # Use agent code from PDF header if available (for commission PDFs)
    if is_commission_pdf and policy_data.get('agent_code_from_pdf'):
        agent_code = policy_data['agent_code_from_pdf']
    
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
        
        # Commission PDF specific: Check if customer name matches
        if is_commission_pdf:
            existing_customer_id = existing.get('customer_id')
            if existing_customer_id:
                # Get existing customer name
                try:
                    result = supabase.table('customers').select('customer_name').eq('customer_id', existing_customer_id).execute()
                    if result.data:
                        existing_customer_name = result.data[0]['customer_name'].strip().upper()
                        if existing_customer_name != customer_name.strip().upper():
                            # Name mismatch - customer name from PDF is final
                            print(f"  ⚠️  Customer name mismatch!")
                            print(f"     Database: {existing_customer_name}")
                            print(f"     PDF (final): {customer_name}")
                            
                            # Update customer name in customers table
                            try:
                                supabase.table('customers').update({
                                    'customer_name': customer_name
                                }).eq('customer_id', existing_customer_id).execute()
                                print(f"  ✅ Updated customer name to: {customer_name}")
                                # Update local cache
                                existing_customers[customer_name.strip().upper()] = {
                                    'customer_id': existing_customer_id,
                                    'customer_name': customer_name
                                }
                            except Exception as e:
                                print(f"  ❌ Failed to update customer name: {e}")
                except Exception as e:
                    print(f"  ⚠️  Could not verify customer name: {e}")
        
        # Rule 1: Update FUP only if PDF date is later
        pdf_fup = policy_data.get('current_fup_date')
        existing_fup = existing.get('current_fup_date')
        
        if pdf_fup:
            if not existing_fup or pdf_fup > existing_fup:
                updates['current_fup_date'] = pdf_fup
                print(f"  📅 Updating FUP: {existing_fup} → {pdf_fup}")
            else:
                print(f"  ℹ️  FUP not updated (PDF: {pdf_fup}, DB: {existing_fup})")
        
        # Rule 2: Premium amount - always update for commission PDFs (it's final)
        if is_commission_pdf and fields_to_update.get('premium_amount'):
            updates['premium_amount'] = fields_to_update['premium_amount']
            print(f"  💰 Updating premium amount: {fields_to_update['premium_amount']}")
        elif fields_to_update.get('premium_amount'):
            updates['premium_amount'] = fields_to_update['premium_amount']
        
        # Rule 3: Plan type - always update for commission PDFs (it's final)
        if is_commission_pdf and fields_to_update.get('plan_name'):
            updates['plan_name'] = fields_to_update['plan_name']
            if existing.get('plan_name') != fields_to_update['plan_name']:
                print(f"  📋 Updating plan type: {existing.get('plan_name')} → {fields_to_update['plan_name']}")
        
        # Rule 4: Update agent_code if not present OR if from commission PDF header
        if agent_code:
            if not existing.get('agent_code'):
                updates['agent_code'] = agent_code
                print(f"  👤 Adding agent code: {agent_code}")
            elif is_commission_pdf and existing.get('agent_code') != agent_code:
                # Commission PDF agent code is authoritative
                updates['agent_code'] = agent_code
                print(f"  👤 Updating agent code: {existing.get('agent_code')} → {agent_code}")
        
        # Rule 5: Update other fields if empty (only for non-commission PDFs)
        if not is_commission_pdf:
            for field in ['plan_name', 'date_of_commencement', 'payment_period', 'sum_assured']:
                if fields_to_update.get(field) and not existing.get(field):
                    updates[field] = fields_to_update[field]
        
        if updates:
            try:
                supabase.table('policies').update(updates).eq('policy_number', policy_number).execute()
                print(f"  ✅ Supabase Cloud: Updated policy {policy_number}")
                supabase_success = True
                stats['updated'] += 1
            except Exception as e:
                print(f"  ❌ Supabase Cloud: Failed to update policy {policy_number}: {e}")
                stats['errors'] += 1
        else:
            print(f"  ℹ️  No updates needed for {policy_number}")
            supabase_success = True  # No updates needed is considered success
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
            print(f"  ✅ Supabase Cloud: Created new policy {policy_number}")
            supabase_success = True
            stats['created'] += 1
        except Exception as e:
            print(f"  ❌ Supabase Cloud: Failed to create policy {policy_number}: {e}")
            stats['errors'] += 1
    
    # Sync to local database
    if local_conn and customer_id:
        try:
            cursor = local_conn.cursor()
            
            # Get or create customer in local DB
            cursor.execute('SELECT customer_id FROM customers WHERE customer_name = ?', 
                          (customer_name,))
            local_customer = cursor.fetchone()
            
            if not local_customer:
                cursor.execute('''
                    INSERT INTO customers (customer_name, extraction_method, created_date, last_updated)
                    VALUES (?, ?, ?, ?)
                ''', (customer_name, 'pdf_import', datetime.now().isoformat(), datetime.now().isoformat()))
                local_customer_id = cursor.lastrowid
            else:
                local_customer_id = local_customer[0]
            
            # Check if policy exists in local DB
            cursor.execute('SELECT policy_id FROM policies WHERE policy_number = ?', 
                          (policy_number,))
            local_policy = cursor.fetchone()
            
            if local_policy:
                # Update existing policy
                update_fields = []
                update_values = []
                
                if policy_data.get('current_fup_date'):
                    update_fields.append('current_fup_date = ?')
                    update_values.append(policy_data['current_fup_date'])
                
                if fields_to_update.get('premium_amount'):
                    update_fields.append('premium_amount = ?')
                    update_values.append(fields_to_update['premium_amount'])
                
                if fields_to_update.get('plan_name'):
                    update_fields.append('plan_name = ?')
                    update_values.append(fields_to_update['plan_name'])
                
                if fields_to_update.get('sum_assured'):
                    update_fields.append('sum_assured = ?')
                    update_values.append(fields_to_update['sum_assured'])
                
                if agent_code:
                    update_fields.append('agent_code = ?')
                    update_values.append(agent_code)
                
                update_fields.append('last_updated = ?')
                update_values.append(datetime.now().isoformat())
                
                if update_fields:
                    update_values.append(policy_number)
                    cursor.execute(f'''
                        UPDATE policies 
                        SET {', '.join(update_fields)}
                        WHERE policy_number = ?
                    ''', update_values)
                    print(f"  ✅ Local Database: Updated policy {policy_number}")
                    local_success = True
            else:
                # Insert new policy
                cursor.execute('''
                    INSERT INTO policies (
                        policy_number, customer_id, agent_code, plan_name, 
                        premium_amount, sum_assured, date_of_commencement, 
                        payment_period, current_fup_date, created_date, last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    policy_number,
                    local_customer_id,
                    agent_code,
                    fields_to_update.get('plan_name'),
                    fields_to_update.get('premium_amount'),
                    fields_to_update.get('sum_assured'),
                    fields_to_update.get('date_of_commencement'),
                    fields_to_update.get('payment_period'),
                    policy_data.get('current_fup_date'),
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                ))
                print(f"  ✅ Local Database: Created new policy {policy_number}")
                local_success = True
            
            local_conn.commit()
            
        except Exception as e:
            print(f"  ❌ Local Database: Failed to sync policy {policy_number}: {e}")
            local_conn.rollback()
    
    # Print overall status
    if supabase_success and local_success:
        print(f"  🎉 SUCCESS: Policy {policy_number} synced to both Cloud and Local DB")
    elif supabase_success:
        print(f"  ⚠️  PARTIAL: Policy {policy_number} synced to Cloud only")
    elif local_success:
        print(f"  ⚠️  PARTIAL: Policy {policy_number} synced to Local DB only")
    else:
        print(f"  ❌ FAILED: Policy {policy_number} not synced to any database")

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
        print("\n🔌 Connecting to Supabase Cloud...")
        supabase = get_supabase_client()
        print("✅ Connected to Supabase Cloud")
    except Exception as e:
        print(f"❌ Failed to connect to Supabase: {e}")
        return
    
    # Connect to local database
    try:
        print("💾 Connecting to Local Database...")
        local_conn = get_local_db_connection()
        print("✅ Connected to Local Database")
        print(f"   📍 Location: {Path(__file__).parent.parent / 'data' / 'lic_local_backup.db'}")
    except Exception as e:
        print(f"⚠️  Warning: Local database not available: {e}")
        print("   Continuing with Supabase Cloud only...")
        local_conn = None
    
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
            is_commission_pdf = False
            
            if 'Commission' in text or 'P/H Name' in text or 'CM-' in pdf_file.name or 'Agent Code' in text:
                print("  📋 Document type: Commission")
                is_commission_pdf = True
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
                    stats,
                    local_conn,
                    is_commission_pdf
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
    
    # Close local database connection
    if local_conn:
        local_conn.close()
        print("\n💾 Local database connection closed")
        print(f"📍 Backup saved at: {Path(__file__).parent.parent / 'data' / 'lic_local_backup.db'}")

if __name__ == "__main__":
    process_pdf_files()
