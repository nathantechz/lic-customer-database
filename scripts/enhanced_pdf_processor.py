import pdfplumber
import sqlite3
import os
import re
import shutil
from pathlib import Path
from datetime import datetime

def get_project_root():
    """Get the project root directory"""
    return Path(__file__).parent.parent

def extract_content_hash(file_path):
    """Extract a content hash from PDF for duplicate detection"""
    import hashlib
    
    try:
        with pdfplumber.open(file_path) as pdf:
            # Extract text from first page (usually contains unique identifiers)
            first_page_text = ""
            if pdf.pages:
                first_page_text = pdf.pages[0].extract_text() or ""
            
            # Create hash from first 1000 characters (contains dates, policy numbers, etc.)
            content_sample = first_page_text[:1000].strip()
            content_hash = hashlib.md5(content_sample.encode()).hexdigest()
            
            return content_hash, content_sample[:200]  # Return hash and sample for logging
            
    except Exception as e:
        print(f"  ⚠️ Error extracting content hash: {e}")
        return None, None

def is_generic_filename(file_name):
    """Check if filename is generic (needs content-based duplicate detection)"""
    generic_patterns = [
        "claims-due-list",
        "claim-list", 
        "premium-due",
        "premium-list",
        "policy-list",
        "customer-list"
    ]
    
    file_lower = file_name.lower()
    return any(pattern in file_lower for pattern in generic_patterns)

def extract_document_date(filename, text):
    """Extract document date from filename and PDF text"""
    document_date = None
    
    # First try to extract from filename
    # Look for patterns like CM-74N-20250501, Premdue-202505
    filename_patterns = [
        r'CM-\w+-(\d{8})',  # CM-74N-20250501
        r'Premdue-(\d{6})',  # Premdue-202505
        r'Claims-Due-List.*(\d{8})',  # Claims-Due-List-20250501
    ]
    
    for pattern in filename_patterns:
        match = re.search(pattern, filename)
        if match:
            date_str = match.group(1)
            if len(date_str) == 8:  # YYYYMMDD
                try:
                    year = int(date_str[:4])
                    month = int(date_str[4:6])
                    day = int(date_str[6:8])
                    document_date = f"{year:04d}-{month:02d}-{day:02d}"
                    print(f"    📅 Document date from filename: {document_date}")
                    break
                except ValueError:
                    continue
            elif len(date_str) == 6:  # YYYYMM
                try:
                    year = int(date_str[:4])
                    month = int(date_str[4:6])
                    document_date = f"{year:04d}-{month:02d}-01"  # Use first day of month
                    print(f"    📅 Document date from filename: {document_date}")
                    break
                except ValueError:
                    continue
    
    # If not found in filename, try to extract from text
    if not document_date:
        text_patterns = [
            r'Premium Due List.*For.*(\d{2}/\d{4})',  # Premium Due List For 05/2025
            r'Commission.*(\d{2}/\d{2}/\d{4})',  # Commission on 31/05/2025
            r'Processed on (\d{2}/\d{2}/\d{4})',  # Processed on 31/05/2025
        ]
        
        for pattern in text_patterns:
            match = re.search(pattern, text)
            if match:
                date_str = match.group(1)
                parsed = parse_date(date_str)
                if parsed:
                    document_date = parsed
                    print(f"    📅 Document date from content: {document_date}")
                    break
    
    return document_date

def parse_date(date_str):
    """Parse date string in various formats and return YYYY-MM-DD format"""
    if not date_str or date_str.strip() == "":
        return None
        
    date_str = date_str.strip()
    
    # Common date patterns
    patterns = [
        r'(\d{1,2})/(\d{1,2})/(\d{4})',  # DD/MM/YYYY
        r'(\d{1,2})-(\d{1,2})-(\d{4})',  # DD-MM-YYYY
        r'(\d{4})/(\d{1,2})/(\d{1,2})',  # YYYY/MM/DD
        r'(\d{4})-(\d{1,2})-(\d{1,2})',  # YYYY-MM-DD
    ]
    
    for pattern in patterns:
        match = re.search(pattern, date_str)
        if match:
            groups = match.groups()
            if len(groups) == 3:
                if len(groups[0]) == 4:  # Year first
                    year, month, day = groups
                else:  # Day first (DD/MM/YYYY format)
                    day, month, year = groups
                
                try:
                    # Convert to integers and validate
                    day_int = int(day)
                    month_int = int(month)
                    year_int = int(year)
                    
                    if 1 <= day_int <= 31 and 1 <= month_int <= 12 and 1900 <= year_int <= 2100:
                        return f"{year_int:04d}-{month_int:02d}-{day_int:02d}"
                except ValueError:
                    continue
    
    return None

def extract_commission_details(text):
    """Extract detailed policy information from Commission PDFs"""
    details = []
    
    # Find the customer details table
    table_section = find_customer_table_section(text)
    lines = table_section.split('\n')
    
    print("    💰 Parsing commission table for detailed info...")
    
    for line_num, line in enumerate(lines):
        line_clean = line.strip()
        if not line_clean or line_clean.startswith('S.No') or 'PH Name' in line:
            continue
        
        # Commission pattern: Serial_Number Name Policy_Number Plan/Term Other_Details
        # Example: "1 C NONDICHAMY 308700508 814-21 27/05/2025 27/08/2018 CBK2 26/05/2025 2640.00 132.00"
        commission_pattern = r'^\s*(\d+)\s+([A-Z][A-Za-z\s.]{2,50}?)\s+(\d{9})\s+(\d{3}-\d{2})\s+(\d{1,2}/\d{1,2}/\d{4})?\s*(.*)$'
        
        match = re.match(commission_pattern, line_clean)
        if match:
            serial_no = match.group(1)
            name = match.group(2).strip()
            policy_no = match.group(3)
            plan_type = match.group(4)  # Like "814-21", "836-10" - now specifically captures XXX-XX format
            due_date = match.group(5) if match.group(5) else None
            remaining = match.group(6).strip() if match.group(6) else ""
            
            cleaned_name = clean_customer_name(name)
            if cleaned_name and len(cleaned_name) > 2:
                parsed_due_date = parse_date(due_date) if due_date else None
                
                # Extract additional details from remaining text
                premium_amount = None
                commission_amount = None
                
                # Look for premium and commission amounts
                amounts = re.findall(r'(\d+\.?\d*)', remaining)
                if len(amounts) >= 2:
                    try:
                        premium_amount = float(amounts[-2])  # Second last number is usually premium
                        commission_amount = float(amounts[-1])  # Last number is commission
                    except ValueError:
                        pass
                
                details.append({
                    'policy_number': policy_no,
                    'customer_name': cleaned_name,
                    'plan_type': plan_type,
                    'due_date': parsed_due_date,
                    'premium_amount': premium_amount,
                    'commission_amount': commission_amount
                })
                
                print(f"    ✅ Commission detail: {policy_no} → {cleaned_name} (Plan: {plan_type})")
    
    return details

def extract_premium_due_details(text):
    """Extract detailed policy information from Premium Due PDFs"""
    details = []
    
    # Find the customer details table
    table_section = find_customer_table_section(text)
    lines = table_section.split('\n')
    
    print("    💳 Parsing premium due table for detailed info...")
    
    for line_num, line in enumerate(lines):
        line_clean = line.strip()
        if not line_clean or line_clean.startswith('S.No') or 'PolicyNo' in line:
            continue
        
        # Premium Due pattern: S.No PolicyNo Name D.o.C Pln/Tm Mod FUP Flg InstPrem Due GST TotPrem EstCom
        # Example: "1 319566711 P.MARIMUTHU 14/10/2020 936/21 Hly 10/2024 14689.00 2 661.00 30039 1468.90"
        premium_pattern = r'^\s*(\d+)\s+(\d{9})\s+([A-Z][A-Za-z\s.]{2,50}?)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(\d{3}/\d{2})\s+([^\\s]+)\s+(\d{1,2}/\d{4})\s*(.*)$'
        
        match = re.match(premium_pattern, line_clean)
        if match:
            serial_no = match.group(1)
            policy_no = match.group(2)
            name = match.group(3).strip()
            doc_date = match.group(4)  # Date of Commencement
            plan_type = match.group(5)  # Like "936/21" - now specifically captures XXX/XX format
            mode = match.group(6)  # Like "Hly", "Yly", "Mly", "Qly"
            fup_date = match.group(7)  # Like "10/2024"
            remaining = match.group(8).strip() if match.group(8) else ""
            
            cleaned_name = clean_customer_name(name)
            if cleaned_name and len(cleaned_name) > 2:
                parsed_doc = parse_date(doc_date)
                
                # Parse FUP date (MM/YYYY format)
                parsed_fup = None
                if fup_date:
                    fup_match = re.match(r'(\d{1,2})/(\d{4})', fup_date)
                    if fup_match:
                        month, year = fup_match.groups()
                        parsed_fup = f"{year}-{int(month):02d}-01"  # Use 1st of the month
                
                # Extract amounts from remaining text
                amounts = re.findall(r'(\d+\.?\d*)', remaining)
                inst_prem = None
                due_count = None
                gst_amount = None
                total_prem = None
                est_commission = None
                
                if len(amounts) >= 4:
                    try:
                        inst_prem = float(amounts[0])  # InstPrem
                        due_count = int(float(amounts[1]))  # Due count
                        gst_amount = float(amounts[2])  # GST
                        total_prem = float(amounts[3])  # TotPrem
                        if len(amounts) >= 5:
                            est_commission = float(amounts[4])  # EstCom
                    except (ValueError, IndexError):
                        pass
                
                details.append({
                    'policy_number': policy_no,
                    'customer_name': cleaned_name,
                    'date_of_commencement': parsed_doc,
                    'plan_type': plan_type,
                    'premium_mode': mode,
                    'current_fup_date': parsed_fup,
                    'premium_amount': inst_prem,
                    'due_count': due_count,
                    'gst_amount': gst_amount,
                    'total_amount': total_prem,
                    'estimated_commission': est_commission
                })
                
                print(f"    ✅ Premium detail: {policy_no} → {cleaned_name} (Plan: {plan_type}, FUP: {fup_date})")
    
    return details

def clean_customer_name(name):
    """Clean and standardize customer names"""
    if not name:
        return None
    
    # Remove extra whitespace and normalize
    name = re.sub(r'\s+', ' ', name.strip())
    
    # Remove common prefixes and suffixes
    name = re.sub(r'^(Mr\.?|Mrs\.?|Ms\.?|Dr\.?|Prof\.?)\s+', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+(Jr\.?|Sr\.?|III|IV)$', '', name, flags=re.IGNORECASE)
    
    # Skip if it looks like a policy number or other non-name data
    if re.match(r'^\d+$', name) or len(name) < 3:
        return None
    
    # Skip if it contains too many numbers or special characters
    if len(re.findall(r'\d', name)) > len(name) * 0.3:
        return None
    
    return name.title()

def find_customer_table_section(text):
    """Find and extract the customer table section from PDF text"""
    lines = text.split('\n')
    
    # Look for specific customer table headers
    table_start = -1
    table_end = len(lines)
    
    # More specific patterns for customer tables
    customer_table_patterns = [
        r'S\.No.*PH Name.*PolicyNo',  # Commission table
        r'S\.No.*PolicyNo.*Name of Assured.*D\.o\.C',  # Premium Due table
        r'S\.No.*Policy.*Name.*Due.*Date',  # Claims table
    ]
    
    # First look for specific customer table headers
    for i, line in enumerate(lines):
        for pattern in customer_table_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                table_start = i  # Start from the header line itself
                print(f"    📋 Found customer table header at line {i}: {line[:80]}...")
                break
        if table_start != -1:
            break
    
    # If no specific customer table found, look for general patterns
    if table_start == -1:
        general_patterns = [
            r'Premium Due List.*For',
            r'Commission.*Details.*annexure',
            r'Agent Name.*:'
        ]
        
        for i, line in enumerate(lines):
            for pattern in general_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    table_start = max(0, i - 1)  # Include some context
                    print(f"    📋 Found general table header at line {i}: {line[:80]}...")
                    break
            if table_start != -1:
                break
    
    if table_start == -1:
        table_start = 0
    
    # Find table end (look for summary or footer patterns)
    end_patterns = [
        r'Total.*:',
        r'Grand Total',
        r'Page \d+ of \d+',
        r'Generated on',
        r'^\s*$'  # Multiple empty lines
    ]
    
    empty_line_count = 0
    for i in range(table_start + 5, len(lines)):  # Start checking after initial header lines
        line = lines[i].strip()
        
        if not line:
            empty_line_count += 1
            if empty_line_count >= 3:  # Multiple consecutive empty lines indicate end
                table_end = i
                break
        else:
            empty_line_count = 0
            
        for pattern in end_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                table_end = i
                break
        
        if table_end != len(lines):
            break
    
    # Extract the table section
    table_lines = lines[table_start:table_end]
    return '\n'.join(table_lines)

def is_file_already_processed(file_name, file_path, db_path):
    """Check if a PDF file has already been processed using content-based detection"""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Always use content-based detection first
            print(f"  🔍 Checking content for duplicates...")
            
            content_hash, content_sample = extract_content_hash(file_path)
            if not content_hash:
                print(f"  ⚠️ Could not extract content hash, falling back to filename check")
                cursor.execute("SELECT COUNT(*) FROM documents WHERE file_name = ?", (file_name,))
                count = cursor.fetchone()[0]
                return count > 0, "filename"
            
            # Check if content hash already exists
            cursor.execute(
                "SELECT file_name FROM documents WHERE content_hash = ?",
                (content_hash,)
            )
            existing_file = cursor.fetchone()
            
            if existing_file:
                print(f"  🔄 Content match found with: {existing_file[0]}")
                print(f"  📄 Content sample: {content_sample[:100]}...")
                return True, "content"
            else:
                print(f"  ✅ Unique content detected")
                print(f"  📄 Content sample: {content_sample[:100]}...")
                return False, None
                
    except Exception as e:
        print(f"  ⚠️ Error checking duplicate: {e}")
        return False, None

def move_to_duplicates(pdf_file, duplicates_path):
    """Move PDF to duplicates folder with timestamp"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_name = pdf_file.stem
        extension = pdf_file.suffix
        new_name = f"{base_name}_{timestamp}{extension}"
        
        destination = duplicates_path / new_name
        shutil.move(str(pdf_file), str(destination))
        return destination
        
    except Exception as e:
        print(f"  ❌ Error moving to duplicates: {e}")
        return None

def log_error(filename, error_message, errors_path):
    """Log processing errors to a file"""
    try:
        log_file = errors_path / "error_log.txt"
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {filename}: {error_message}\n")
            
    except Exception as e:
        print(f"  ⚠️ Could not log error: {e}")

def create_database_schema(db_path):
    """Create the database schema if it doesn't exist"""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Create customers table
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
                    extraction_method TEXT DEFAULT 'unknown',
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create policies table with enhanced fields
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
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
                )
            ''')
            
            # Create premium_records table with enhanced fields
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
                    status TEXT DEFAULT 'Due',
                    agent_code TEXT,
                    processed_date TEXT,
                    source_pdf TEXT,
                    payment_date TEXT,
                    payment_notes TEXT,
                    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (policy_number) REFERENCES policies (policy_number)
                )
            ''')
            
            # Create agents table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS agents (
                    agent_code TEXT PRIMARY KEY,
                    agent_name TEXT,
                    branch_code TEXT,
                    relationship TEXT,
                    phone TEXT,
                    email TEXT,
                    active BOOLEAN DEFAULT 1
                )
            ''')
            
            # Create documents table for tracking processed files
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    policy_number TEXT,
                    document_type TEXT,
                    file_name TEXT,
                    file_path TEXT,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    content_hash TEXT,
                    FOREIGN KEY (policy_number) REFERENCES policies (policy_number)
                )
            ''')
            
            conn.commit()
            print("✅ Database schema created/verified")
            
    except Exception as e:
        print(f"❌ Error creating database schema: {e}")

def process_enhanced_pdf_files():
    """Main function to process PDF files with enhanced data extraction"""
    
    # Setup paths
    project_root = get_project_root()
    data_path = project_root / "data"
    pdfs_path = data_path / "pdfs"
    incoming_path = pdfs_path / "incoming"
    processed_path = pdfs_path / "processed"
    errors_path = pdfs_path / "errors"
    duplicates_path = pdfs_path / "duplicates"
    db_path = data_path / "lic_customers.db"
    
    # Create directories if they don't exist
    for path in [processed_path, errors_path, duplicates_path]:
        path.mkdir(parents=True, exist_ok=True)
    
    # Create/verify database schema
    create_database_schema(db_path)
    
    # Find PDF files to process
    pdf_files = list(incoming_path.glob("*.pdf")) if incoming_path.exists() else []
    
    if not pdf_files:
        print("📂 No PDF files found in incoming folder")
        return
    
    print(f"📄 Found {len(pdf_files)} PDF files to process...")
    
    # Processing counters
    files_processed = 0
    files_with_errors = 0
    files_duplicated = 0
    customers_added = 0
    policies_added = 0
    premium_records_added = 0
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        for pdf_file in pdf_files:
            print(f"\n🔄 Processing: {pdf_file.name}")
            
            try:
                # Check if file already processed
                is_duplicate, duplicate_type = is_file_already_processed(pdf_file.name, pdf_file, db_path)
                
                if is_duplicate:
                    print(f"  🔄 File already processed (detected by {duplicate_type})")
                    duplicate_location = move_to_duplicates(pdf_file, duplicates_path)
                    if duplicate_location:
                        print(f"  📂 Moved to duplicates: {duplicate_location}")
                        files_duplicated += 1
                    continue
                
                # Extract text from PDF
                with pdfplumber.open(pdf_file) as pdf:
                    text = ""
                    for page in pdf.pages:
                        text += page.extract_text() or ""
                
                if not text.strip():
                    error_reason = "PDF contains no readable text"
                    print(f"  ❌ {error_reason}")
                    log_error(pdf_file.name, error_reason, errors_path)
                    shutil.move(str(pdf_file), str(errors_path / pdf_file.name))
                    files_with_errors += 1
                    continue
                
                # Extract agent code from filename or content
                agent_code = None
                agent_match = re.search(r'(\d{7}N)', pdf_file.name)
                if agent_match:
                    agent_code = agent_match.group(1)
                    print(f"  👤 Agent detected: {agent_code}")
                
                # Determine document type and extract details
                policy_details = []
                document_type = "unknown"
                
                if 'Commission' in text or 'PH Name' in text or 'CM-' in pdf_file.name:
                    document_type = "commission"
                    policy_details = extract_commission_details(text)
                elif 'Premium Due' in text or 'Name of Assured' in text or 'Premdue' in pdf_file.name.lower():
                    document_type = "premium_due"
                    policy_details = extract_premium_due_details(text)
                else:
                    # Fallback to basic extraction
                    print("  ⚠️ Unknown document type, using generic extraction")
                    # Could add basic extraction here if needed
                
                if not policy_details:
                    print(f"  📋 Found {len(policy_details)} policy details")
                    error_reason = f"No policy details could be extracted from {document_type} document"
                    print(f"  ⚠️ {error_reason}")
                    log_error(pdf_file.name, error_reason, errors_path)
                    shutil.move(str(pdf_file), str(errors_path / pdf_file.name))
                    files_with_errors += 1
                    continue
                
                print(f"  🔗 Found {len(policy_details)} policy details")
                
                # Extract document date for comparison
                document_date = extract_document_date(pdf_file.name, text)
                
                # Process each policy detail
                policies_in_this_file = 0
                database_errors = []
                existing_policies_count = 0
                
                for detail in policy_details:
                    try:
                        policy_number = detail['policy_number']
                        customer_name = detail['customer_name']
                        
                        # First check if customer exists
                        cursor.execute('SELECT customer_id, created_date FROM customers WHERE customer_name = ?', (customer_name,))
                        existing_customer = cursor.fetchone()
                        
                        # Then check if policy already exists and get existing information
                        cursor.execute('''
                            SELECT current_fup_date, last_updated, premium_amount, plan_type, customer_id, created_date
                            FROM policies WHERE policy_number = ?
                        ''', (policy_number,))
                        existing_policy = cursor.fetchone()
                        
                        if existing_policy:
                            existing_fup = existing_policy[0]
                            existing_updated = existing_policy[1]
                            existing_premium = existing_policy[2]
                            existing_plan = existing_policy[3]
                            policy_customer_id = existing_policy[4]
                            policy_created_date = existing_policy[5]
                            
                            new_fup = detail.get('current_fup_date')
                            should_update = False
                            update_reason = ""
                            
                            # Determine if we should update based on document date and data freshness
                            if document_type == "premium_due":
                                # For premium due files, update if:
                                # 1. New FUP date is newer, OR
                                # 2. Document date is newer than last update, OR
                                # 3. We have new information that's missing
                                if new_fup and (not existing_fup or new_fup > existing_fup):
                                    should_update = True
                                    update_reason = f"newer FUP date: {new_fup}"
                                elif document_date and existing_updated:
                                    # Compare document date with last update
                                    existing_date = existing_updated.split()[0] if ' ' in existing_updated else existing_updated
                                    if document_date > existing_date:
                                        should_update = True
                                        update_reason = f"newer document date: {document_date}"
                                elif not existing_premium and detail.get('premium_amount'):
                                    should_update = True
                                    update_reason = "missing premium information"
                            
                            elif document_type == "commission":
                                # For commission files, update if:
                                # 1. Missing plan type, OR
                                # 2. Document date is newer
                                if not existing_plan and detail.get('plan_type'):
                                    should_update = True
                                    update_reason = "missing plan type information"
                                elif document_date and existing_updated:
                                    existing_date = existing_updated.split()[0] if ' ' in existing_updated else existing_updated
                                    if document_date > existing_date:
                                        should_update = True
                                        update_reason = f"newer document date: {document_date}"
                            
                            if should_update:
                                print(f"    🔄 Updating policy {policy_number} - {update_reason}")
                                
                                # Update customer's last_updated with document date
                                cursor.execute('UPDATE customers SET last_updated = ? WHERE customer_id = ?', 
                                             (document_date, policy_customer_id))
                                
                                # For policy created_date, use latest document date containing this policy
                                policy_update_fields = {
                                    'plan_type': detail.get('plan_type'),
                                    'date_of_commencement': detail.get('date_of_commencement'),
                                    'premium_mode': detail.get('premium_mode'),
                                    'current_fup_date': detail.get('current_fup_date'),
                                    'premium_amount': detail.get('premium_amount'),
                                    'last_updated': document_date
                                }
                                
                                # Update created_date if this document is later
                                if document_date > policy_created_date:
                                    policy_update_fields['created_date'] = document_date
                                
                                # Build dynamic query
                                field_updates = []
                                values = []
                                for field, value in policy_update_fields.items():
                                    if field in ['last_updated', 'created_date']:
                                        field_updates.append(f"{field} = ?")
                                        values.append(value)
                                    else:
                                        field_updates.append(f"{field} = COALESCE(?, {field})")
                                        values.append(value)
                                
                                values.append(policy_number)
                                
                                cursor.execute(f'''
                                    UPDATE policies SET {', '.join(field_updates)}
                                    WHERE policy_number = ?
                                ''', values)
                                
                                # Add premium record
                                if document_type == "premium_due":
                                    cursor.execute('''
                                        INSERT INTO premium_records 
                                        (policy_number, due_date, premium_amount, gst_amount, total_amount, 
                                         due_count, estimated_commission, agent_code, source_pdf, document_date)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    ''', (
                                        policy_number,
                                        detail.get('current_fup_date'),
                                        detail.get('premium_amount'),
                                        detail.get('gst_amount'),
                                        detail.get('total_amount'),
                                        detail.get('due_count'),
                                        detail.get('estimated_commission'),
                                        agent_code,
                                        pdf_file.name,
                                        document_date
                                    ))
                                    premium_records_added += 1
                                
                                policies_in_this_file += 1
                                print(f"    ✅ Updated: {policy_number} → {customer_name}")
                            else:
                                print(f"    ↪️  Policy {policy_number} already exists with current/newer data")
                                existing_policies_count += 1
                        
                        else:
                            # New policy
                            print(f"    ➕ Adding new policy {policy_number}")
                            
                            if existing_customer:
                                # Customer exists, use existing customer ID
                                customer_id = existing_customer[0]
                                existing_created_date = existing_customer[1]
                                
                                # Update customer dates - created_date only if this document is earlier
                                if document_date < existing_created_date:
                                    cursor.execute('''UPDATE customers SET 
                                                 created_date = ?, last_updated = ? 
                                                 WHERE customer_id = ?''', 
                                                 (document_date, document_date, customer_id))
                                else:
                                    cursor.execute('UPDATE customers SET last_updated = ? WHERE customer_id = ?', 
                                                 (document_date, customer_id))
                                print(f"    👤 Using existing customer: {customer_name}")
                            else:
                                # New customer
                                cursor.execute('''INSERT INTO customers 
                                             (customer_name, extraction_method, created_date, last_updated) 
                                             VALUES (?, ?, ?, ?)''', 
                                             (customer_name, 'enhanced_regex', document_date, document_date))
                                customer_id = cursor.lastrowid
                                customers_added += 1
                                print(f"    👤 Added new customer: {customer_name}")
                            
                            # Insert new policy with all available details
                            cursor.execute('''
                                INSERT INTO policies 
                                (policy_number, customer_id, agent_code, plan_type, date_of_commencement, 
                                 premium_mode, current_fup_date, premium_amount, status, extraction_method, 
                                 created_date, last_updated)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                policy_number, customer_id, agent_code,
                                detail.get('plan_type'),
                                detail.get('date_of_commencement'),
                                detail.get('premium_mode'),
                                detail.get('current_fup_date'),
                                detail.get('premium_amount'),
                                'Active',
                                'enhanced_regex',
                                document_date,
                                document_date
                            ))
                            policies_added += 1
                            policies_in_this_file += 1
                            
                            # Add premium record if this is a premium due document
                            if document_type == "premium_due":
                                cursor.execute('''
                                    INSERT INTO premium_records 
                                    (policy_number, due_date, premium_amount, gst_amount, total_amount, 
                                     due_count, estimated_commission, agent_code, source_pdf, document_date)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', (
                                    policy_number,
                                    detail.get('current_fup_date'),
                                    detail.get('premium_amount'),
                                    detail.get('gst_amount'),
                                    detail.get('total_amount'),
                                    detail.get('due_count'),
                                    detail.get('estimated_commission'),
                                    agent_code,
                                    pdf_file.name,
                                    document_date
                                ))
                                premium_records_added += 1
                            
                            print(f"    ✅ Added new policy: {policy_number} → {customer_name}")
                        
                    except sqlite3.Error as db_err:
                        error_msg = f"Database error for policy {policy_number}: {db_err}"
                        print(f"    ❌ {error_msg}")
                        database_errors.append(error_msg)
                        continue
                
                if policies_in_this_file > 0:
                    shutil.move(str(pdf_file), str(processed_path / pdf_file.name))
                    files_processed += 1
                    print(f"  ✅ Processed {policies_in_this_file} policies from {pdf_file.name}")
                    
                    # Record document in database for duplicate tracking
                    try:
                        content_hash, _ = extract_content_hash(pdf_file) if is_generic_filename(pdf_file.name) else (None, None)
                        cursor.execute('''
                            INSERT INTO documents (file_name, file_path, document_type, content_hash, document_date)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (pdf_file.name, str(processed_path / pdf_file.name), document_type, content_hash, document_date))
                        print(f"  📝 Document tracked")
                        
                    except Exception as doc_error:
                        print(f"  ⚠️ Could not track document: {doc_error}")
                else:
                    # Check if all database errors were due to existing policies
                    all_existing_policies = all("already exists" in error.lower() for error in database_errors) if database_errors else False
                    
                    if all_existing_policies and len(policy_details) > 0:
                        # This file contains only existing policies - move to duplicates folder
                        print(f"  🔄 File contains only existing policies ({len(policy_details)} policies already in database)")
                        
                        duplicate_location = move_to_duplicates(pdf_file, duplicates_path)
                        if duplicate_location:
                            print(f"  📂 Moved to duplicates: {duplicate_location}")
                            files_duplicated += 1
                        else:
                            print(f"  ❌ Failed to move to duplicates")
                            files_with_errors += 1
                    else:
                        # This is a genuine error
                        error_reason = f"No valid policies could be processed. Found {len(policy_details)} policies but all had issues."
                        if database_errors:
                            error_reason += f" Database errors: {'; '.join(database_errors)}"
                        
                        print(f"  ⚠️  {error_reason}")
                        log_error(pdf_file.name, error_reason, errors_path)
                        shutil.move(str(pdf_file), str(errors_path / pdf_file.name))
                        files_with_errors += 1
            
            except Exception as e:
                error_reason = f"Exception during PDF processing: {str(e)} (Type: {type(e).__name__})"
                print(f"  ❌ {error_reason}")
                log_error(pdf_file.name, error_reason, errors_path)
                try:
                    shutil.move(str(pdf_file), str(errors_path / pdf_file.name))
                    files_with_errors += 1
                except Exception as move_error:
                    additional_error = f"Could not move file to errors folder: {move_error}"
                    print(f"  ⚠️  {additional_error}")
        
        # Commit all changes
        conn.commit()
        print("✓ Database changes committed")
    
    # Print summary
    print(f"\n🎉 === ENHANCED PROCESSING SUMMARY ===")
    print(f"📄 Files processed successfully: {files_processed}")
    print(f"❌ Files with errors: {files_with_errors}")
    print(f"🔄 Files duplicated (already processed): {files_duplicated}")
    print(f"👥 New customers added: {customers_added}")
    print(f"📋 New policies added: {policies_added}")
    print(f"💳 Premium records added: {premium_records_added}")
    print(f"💾 Database saved to: {db_path}")
    
    print(f"\n📂 Check folders:")
    print(f"  ✅ Processed: {processed_path}")
    print(f"  ❌ Errors: {errors_path}")
    print(f"  🔄 Duplicates: {duplicates_path}")

if __name__ == "__main__":
    process_enhanced_pdf_files()