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

def is_file_already_processed(file_name, file_path, db_path):
    """Check if a PDF file has already been processed using filename and content"""
    try:
        conn = sqlite3.connect(db_path)
        
        # For generic filenames, use content-based detection
        if is_generic_filename(file_name):
            print(f"  🔍 Generic filename detected, checking content...")
            
            content_hash, content_sample = extract_content_hash(file_path)
            if not content_hash:
                print(f"  ⚠️ Could not extract content hash, falling back to filename check")
                cursor = conn.execute("SELECT COUNT(*) FROM documents WHERE file_name = ?", (file_name,))
                count = cursor.fetchone()[0]
                conn.close()
                return count > 0
            
            # Check if content hash already exists
            cursor = conn.execute(
                "SELECT file_name FROM documents WHERE content_hash = ?",
                (content_hash,)
            )
            existing_file = cursor.fetchone()
            
            if existing_file:
                print(f"  🔄 Content match found with: {existing_file[0]}")
                print(f"  📄 Content sample: {content_sample[:100]}...")
                conn.close()
                return True
            else:
                print(f"  ✅ Unique content detected")
                print(f"  📄 Content sample: {content_sample[:100]}...")
                conn.close()
                return False
        
        # For specific filenames, use traditional filename check
        else:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM documents WHERE file_name = ?",
                (file_name,)
            )
            count = cursor.fetchone()[0]
            conn.close()
            return count > 0
            
    except Exception as e:
        print(f"  ⚠️ Error checking duplicate: {e}")
        return False

def move_to_duplicates(file_path, duplicates_path):
    """Move duplicate file to duplicates folder with timestamp"""
    try:
        duplicates_path.mkdir(parents=True, exist_ok=True)
        
        # Add timestamp to avoid filename conflicts in duplicates folder
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_stem = file_path.stem
        file_suffix = file_path.suffix
        new_name = f"{file_stem}_{timestamp}{file_suffix}"
        
        destination = duplicates_path / new_name
        shutil.move(str(file_path), str(destination))
        
        return destination
    except Exception as e:
        print(f"❌ Error moving duplicate file: {e}")
        return None

def extract_customer_names_from_text(text):
    """Extract customer names from LIC PDF text based on file type"""
    customer_names = []
    
    # Detect file type using both filename and content
    filename = ""
    if "FILENAME:" in text:
        filename = text.split("FILENAME:")[1].split("\n")[0].strip().upper()
    
    # Enhanced detection logic
    is_premium_due = ('PREMDUE' in filename or 'PREMIUM DUE' in filename or 
                     'Premium Due' in text or 'Name of Assured' in text or 'Name of the Assured' in text)
    
    is_commission = ('CM' in filename or 'Commission' in text or 'PH Name' in text or 
                    'Policy Holder' in text or 'Commission Summary' in text)
    
    is_claims = ('CLAIMS' in filename or 'CLAIM' in filename or 'Claims' in text or 
                'Claim' in text or 'Claimant' in text or 'Death' in text or 'Maturity' in text)
    
    if is_premium_due:
        print("  📋 Detected Premium Due format - looking for 'Name of Assured' column")
        customer_names = extract_from_premium_due(text)
    
    elif is_commission:
        print("  💰 Detected Commission format - looking for 'PH Name' column")
        customer_names = extract_from_commission(text)
    
    elif is_claims:
        print("  🏥 Detected Claims format - looking for names in claims table")
        customer_names = extract_from_claims(text)
    
    else:
        print(f"  🔍 Unknown format (filename: {filename}) - trying all patterns")
        customer_names = extract_generic_patterns(text)
    
    # If no names found with specific format, try generic patterns as fallback
    if len(customer_names) == 0:
        print("  🔄 No names found with specific format, trying generic patterns...")
        customer_names = extract_generic_patterns(text)
    
    return list(set(customer_names))

def find_customer_table_section(text):
    """Find the section of text that contains the customer details table"""
    lines = text.split('\n')
    customer_table_start = -1
    customer_table_end = len(lines)
    
    # Look for table headers that indicate customer details table
    for i, line in enumerate(lines):
        line_upper = line.upper()
        # Check for policy column indicators
        has_policy_col = ('POLICY NO' in line_upper or 'POLICYNO' in line_upper or 
                         'POLICY NUMBER' in line_upper or 'POLICY' in line_upper)
        
        # Check for name column indicators - be more flexible
        has_name_col = ('NAME OF ASSURED' in line_upper or 'PH NAME' in line_upper or 
                       'POLICY HOLDER' in line_upper or 'CLAIMANT' in line_upper or
                       ('NAME' in line_upper and 'FILE' not in line_upper and 'USER' not in line_upper))
        
        if has_policy_col or has_name_col:
            # Look for policy numbers in the next 20 lines to confirm this is the right table
            policy_found = False
            for j in range(i, min(i+20, len(lines))):
                if re.search(r'\b\d{9}\b', lines[j]):
                    policy_found = True
                    break
            
            if policy_found:
                customer_table_start = i
                print(f"    📋 Found customer table header at line {i}: {line.strip()}")
                break
    
    if customer_table_start == -1:
        # If no specific table found, look for any section with policy numbers
        for i, line in enumerate(lines):
            if re.search(r'\b\d{9}\b', line):
                customer_table_start = max(0, i-5)  # Start a few lines before first policy
                print(f"    📋 Found policy numbers starting at line {i}, using broader section")
                break
    
    if customer_table_start == -1:
        return text  # Return full text if no specific table found
    
    # Find the end of the table - look for summary sections but be more selective
    for i in range(customer_table_start + 1, len(lines)):
        line = lines[i].strip()
        if not line:  # Empty line
            continue
        # Stop only at actual table end markers, not intermediate summaries
        if (('PAGE TOTAL' in line.upper() and 'PREMIUM' in line.upper()) or 
            ('GRAND TOTAL' in line.upper() and 'PREMIUM' in line.upper()) or
            line.startswith('===') or
            line.startswith('(') and 'Page No' in line):
            customer_table_end = i
            break
        # If we've gone 100 lines without finding an end, stop
        if i - customer_table_start > 100:
            customer_table_end = i
            break
    
    # Extract the customer table section
    table_section = '\n'.join(lines[customer_table_start:customer_table_end])
    print(f"    📊 Extracted customer table section ({customer_table_end - customer_table_start} lines)")
    return table_section

def extract_from_premium_due(text):
    """Extract names from Premium Due PDFs - 'Name of Assured' column"""
    customer_names = []
    
    # First, find the customer details table
    table_section = find_customer_table_section(text)
    
    # Enhanced patterns for premium due format
    patterns = [
        # Policy Number followed by Name (most common pattern)
        r'(?:^|\n)\s*(\d{9})\s+([A-Z][A-Za-z\s.]{3,50}?)(?:\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\s+\d+\.?\d*|\s+Rs|\n|$)',
        # Name of Assured header followed by names
        r'Name of (?:the )?Assured[:\s]*\n\s*([A-Z][A-Za-z\s.]+?)(?:\n|$)',
        # Names in table rows with dates/amounts
        r'(?:^|\n)\s*([A-Z][A-Z\s.]{5,45})\s+(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d+\.?\d*)\s+(?:\d+\.?\d*|Rs)',
        # Names followed by premium amounts
        r'(?:^|\n)\s*([A-Z][A-Za-z\s.]{5,45})\s+Rs\.?\s*\d+',
        # Capitalized names in table context
        r'(?:^|\n)\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d+)',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, table_section, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            if isinstance(match, tuple):
                # Policy number and name tuple - take the name part
                name = match[1] if len(match) > 1 else match[0]
            else:
                name = match
            
            cleaned = clean_customer_name(name)
            if cleaned and len(cleaned) > 2:
                customer_names.append(cleaned)
                print(f"    📝 Extracted name: '{name}' -> '{cleaned}'")
    
    # If still no names found, try more aggressive extraction
    if not customer_names:
        print("    🔍 No names found with standard patterns, trying aggressive extraction...")
        aggressive_patterns = [
            # Any capitalized word sequence near policy numbers
            r'\b\d{9}\b.*?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            # Names in common Indian formats
            r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]*){1,4})\b',
            # Names with common suffixes
            r'\b([A-Z][a-z]+(?:\s+(?:KUMAR|SINGH|SHARMA|GUPTA|REDDY|RAO|DEVI|BAI))*)\b',
        ]
        
        for pattern in aggressive_patterns:
            matches = re.findall(pattern, table_section)
            for match in matches:
                cleaned = clean_customer_name(match)
                if cleaned and len(cleaned) > 5:  # Require longer names for aggressive matching
                    customer_names.append(cleaned)
                    print(f"    🎯 Aggressive extraction: '{match}' -> '{cleaned}'")
                    if len(customer_names) >= 10:  # Limit aggressive extraction
                        break
    
    return customer_names

def log_error(pdf_file_name, error_reason, errors_path):
    """Log error information to a text file in the errors directory"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = errors_path / "error_log.txt"
    
    log_entry = f"[{timestamp}] FILE: {pdf_file_name}\n"
    log_entry += f"ERROR: {error_reason}\n"
    log_entry += "-" * 80 + "\n\n"
    
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        print(f"    📝 Error logged to: {log_file}")
    except Exception as e:
        print(f"    ⚠️  Could not write to error log: {e}")

def extract_from_commission(text):
    """Extract names from Commission PDFs - improved parsing for 'S.No PH Name PolicyNo' format"""
    customer_names = []
    
    # First, find the customer details table
    table_section = find_customer_table_section(text)
    lines = table_section.split('\n')
    
    print("    💰 Parsing commission table rows...")
    
    for line_num, line in enumerate(lines):
        line_clean = line.strip()
        if not line_clean or line_clean.startswith('S.No') or 'PH Name' in line:
            continue
        
        # Look for the commission table pattern: Serial_Number Name Policy_Number Other_Details
        # Example: "1 S MOOGAMBIGAI 744085103 091-21 10/12/2024..."
        # Updated pattern to handle names that can have multiple words and initials
        commission_pattern = r'^\s*(\d+)\s+([A-Z][A-Za-z\s.]{2,50}?)\s+(\d{9})\s+'
        
        match = re.match(commission_pattern, line_clean)
        if match:
            serial_no = match.group(1)
            name = match.group(2).strip()
            policy_no = match.group(3)
            
            cleaned_name = clean_customer_name(name)
            if cleaned_name and len(cleaned_name) > 2:
                customer_names.append(cleaned_name)
                print(f"    📝 Commission: {serial_no}. {name} -> {cleaned_name} (Policy: {policy_no})")
    
    # If no matches found with the main pattern, try fallback patterns
    if not customer_names:
        print("    🔄 No commission rows found, trying fallback patterns...")
        fallback_patterns = [
            # Policy Number followed by Name
            r'(?:^|\n)\s*(\d{9})\s+([A-Z][A-Za-z\s.]{3,50}?)(?:\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\s+Rs\.?\s*\d+|\s+\d+\.?\d*|\n|$)',
            # PH Name header patterns
            r'(?:PH Name|Policy Holder)[:\s]*(?:\n\s*)?([A-Z][A-Za-z\s.]+?)(?:\n|$)',
            # Names with commission amounts
            r'(?:^|\n)\s*([A-Z][A-Za-z\s.]{5,45})\s+(?:Rs\.?\s*\d+|\d+\.\d+)',
        ]
        
        for pattern in fallback_patterns:
            matches = re.findall(pattern, table_section, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                if isinstance(match, tuple):
                    name = match[1] if len(match) > 1 else match[0]
                else:
                    name = match
                
                cleaned = clean_customer_name(name)
                if cleaned and len(cleaned) > 2:
                    customer_names.append(cleaned)
                    print(f"    📝 Fallback commission name: '{name}' -> '{cleaned}'")
    
    return customer_names

def extract_from_claims(text):
    """Extract names from Claims PDFs - improved parsing for claims table format"""
    customer_names = []
    
    # First, find the customer details table
    table_section = find_customer_table_section(text)
    lines = table_section.split('\n')
    
    print("    🏥 Parsing claims table rows...")
    
    for line_num, line in enumerate(lines):
        line_clean = line.strip()
        if not line_clean or line_clean.startswith('S.NO') or 'POLICY NO' in line or line_clean.startswith('---'):
            continue
        
        # Look for the claims table pattern: Serial Policy_No Type Due_Date Plan_No Name Amount NEFT
        # Example: "1 746503066 S.B. 16/12/2025 75 NONDICHAMY 20000.00 Y"
        claims_pattern = r'^\s*(\d+)\s+(\d{9})\s+\S+\s+\d{1,2}/\d{1,2}/\d{4}\s+\d+\s+([A-Z][A-Za-z\s]{2,30}?)\s+\d+\.\d+\s*[YN]?'
        
        match = re.match(claims_pattern, line_clean)
        if match:
            serial_no = match.group(1)
            policy_no = match.group(2)
            name = match.group(3).strip()
            
            cleaned_name = clean_customer_name(name)
            if cleaned_name and len(cleaned_name) > 2:
                customer_names.append(cleaned_name)
                print(f"    📝 Claims: {serial_no}. {name} -> {cleaned_name} (Policy: {policy_no})")
    
    # If no matches found, try fallback patterns
    if not customer_names:
        print("    🔄 No claims rows found, trying fallback patterns...")
        fallback_patterns = [
            # Policy Number followed by Name
            r'(?:^|\n)\s*(\d{9})\s+([A-Z][A-Za-z\s.]{3,50}?)(?:\s+(?:Death|Maturity|Survival|Claim)|\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\s+\d+\.?\d*|\n|$)',
            # Claimant/Name headers
            r'(?:Claimant|Name|Beneficiary)[:\s]*(?:\n\s*)?([A-Z][A-Za-z\s.]+?)(?:\n|$)',
            # Names with claim types
            r'(?:^|\n)\s*([A-Z][A-Za-z\s.]{5,45})\s+(?:Death|Maturity|Survival|Claim|Benefit)',
        ]
        
        for pattern in fallback_patterns:
            matches = re.findall(pattern, table_section, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                if isinstance(match, tuple):
                    name = match[1] if len(match) > 1 else match[0]
                else:
                    name = match
                
                cleaned = clean_customer_name(name)
                if cleaned and len(cleaned) > 2:
                    customer_names.append(cleaned)
                    print(f"    📝 Fallback claims name: '{name}' -> '{cleaned}'")
    
    return customer_names

def extract_generic_patterns(text):
    """Extract names using generic patterns as fallback"""
    customer_names = []
    
    # Generic patterns for any document type
    patterns = [
        # Names near policy numbers
        r'\b\d{9}\b.*?([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})',
        # Common Indian name patterns
        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]*){1,4})\b',
        # Names with titles
        r'\b(?:Mr|Mrs|Ms|Dr)\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            cleaned = clean_customer_name(match)
            if cleaned and len(cleaned) > 5:
                customer_names.append(cleaned)
                print(f"    🔍 Generic pattern: '{match}' -> '{cleaned}'")
                if len(customer_names) >= 5:  # Limit generic extraction
                    break
    
    return customer_names

def clean_customer_name(name):
    """Clean and format customer name with enhanced validation"""
    if not name:
        return None
    
    # Remove extra spaces and clean up
    name = ' '.join(name.split()).strip()
    
    # CRITICAL FIX: Reject if the name is just a policy number (9 digits)
    if re.match(r'^\d{9}$', name.replace(' ', '')):
        return None
    
    # CRITICAL FIX: Reject if name contains mostly digits
    digit_count = len([c for c in name if c.isdigit()])
    alpha_count = len([c for c in name if c.isalpha()])
    
    if digit_count > alpha_count:
        return None
    
    # Remove common non-name words
    remove_words = ['Date', 'Amount', 'Due', 'Premium', 'Policy', 'Number', 'Code', 'Branch', 
                   'Commission', 'Summary', 'Agency', 'Total', 'Grand', 'Sub', 'Claim',
                   'Claims', 'Rs', 'Rupees', 'Only', 'Paisa', 'Lakhs', 'Crores', 'Death',
                   'Maturity', 'Claimant', 'Benefit', 'Assured', 'Holder', 'File', 'Name',
                   'Address', 'Phone', 'Email', 'Mobile', 'Contact', 'Details', 'Information',
                   'Type', 'Plan', 'Gross', 'Neft', 'Risk', 'Cbo', 'Adj', 'Commn', 'Pln', 'Tm']
    
    words = name.split()
    filtered_words = []
    
    for word in words:
        # Keep words that are likely names
        if (len(word) > 1 and 
            word not in remove_words and 
            not word.isdigit() and
            not re.match(r'^\d+[./-]\d+', word) and  # Remove date-like patterns
            not re.match(r'^[A-Z]+\d+$', word)):     # Remove code-like patterns
            filtered_words.append(word.title())
    
    if len(filtered_words) < 1:
        return None
    
    # Only return if it looks like a proper name
    if 1 <= len(filtered_words) <= 5 and 3 <= len(' '.join(filtered_words)) <= 60:
        final_name = ' '.join(filtered_words)
        
        # Enhanced validation
        if (any(c.isalpha() for c in final_name) and 
            not final_name.replace(' ', '').isdigit() and 
            alpha_count >= digit_count and
            not all(word.isupper() and len(word) < 4 for word in filtered_words)):
            return final_name
    
    return None

def extract_policy_name_pairs(text):
    """Extract policy number and customer name pairs more carefully - IMPROVED VERSION"""
    pairs = []
    
    # Find table section first
    table_section = find_customer_table_section(text)
    lines = table_section.split('\n')
    
    print("    🔍 Extracting policy-name pairs from table rows...")
    
    # Determine document type for specific parsing
    is_commission = 'PH Name' in text or 'Commission' in text
    is_claims = 'Claims' in text or 'Claim' in text or 'DUE DATE' in text
    is_premium = 'Name of Assured' in text or 'PREMDUE' in text
    
    for line_num, line in enumerate(lines):
        line_clean = line.strip()
        if not line_clean or line_clean.startswith('S.No') or 'POLICY NO' in line:
            continue
        
        found_pair = False
        
        if is_commission:
            # Commission format: Serial_Number Name Policy_Number Other_Details
            commission_pattern = r'^\s*(\d+)\s+([A-Z][A-Za-z\s.]{3,50}?)\s+(\d{9})\s+'
            match = re.match(commission_pattern, line_clean)
            if match:
                name = match.group(2).strip()
                policy = match.group(3)
                cleaned_name = clean_customer_name(name)
                if cleaned_name:
                    pairs.append((policy, cleaned_name))
                    print(f"    ✅ Commission pair: {policy} → {cleaned_name}")
                    found_pair = True
        
        elif is_claims:
            # Claims format: Serial Policy_No Type Due_Date Plan_No Name Amount NEFT
            claims_pattern = r'^\s*(\d+)\s+(\d{9})\s+\S+\s+\d{1,2}/\d{1,2}/\d{4}\s+\d+\s+([A-Z][A-Za-z\s]{2,30}?)\s+\d+\.\d+\s*[YN]?'
            match = re.match(claims_pattern, line_clean)
            if match:
                policy = match.group(2)
                name = match.group(3).strip()
                cleaned_name = clean_customer_name(name)
                if cleaned_name:
                    pairs.append((policy, cleaned_name))
                    print(f"    ✅ Claims pair: {policy} → {cleaned_name}")
                    found_pair = True
        
        if not found_pair:
            # Generic fallback patterns
            policy_matches = re.findall(r'\b(\d{9})\b', line_clean)
            if policy_matches:
                for policy_num in policy_matches:
                    # Remove the policy number to isolate the name part
                    line_without_policy = re.sub(r'\b' + policy_num + r'\b', ' ', line_clean)
                    line_without_policy = re.sub(r'\s+', ' ', line_without_policy).strip()
                    
                    # Enhanced name extraction patterns
                    name_patterns = [
                        # Proper case names (best quality)
                        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b',
                        # All caps names with reasonable length
                        r'\b([A-Z]{3,}(?:\s+[A-Z]{3,}){0,2})\b',
                        # Mixed case with dots/periods
                        r'\b([A-Z][A-Za-z.]+(?:\s+[A-Z][A-Za-z.]+){0,2})\b'
                    ]
                    
                    name_found = False
                    for pattern in name_patterns:
                        name_matches = re.findall(pattern, line_without_policy)
                        for potential_name in name_matches:
                            cleaned_name = clean_customer_name(potential_name.strip())
                            if cleaned_name and len(cleaned_name) >= 3:
                                pairs.append((policy_num, cleaned_name))
                                print(f"    ✅ Generic pair: {policy_num} → {cleaned_name}")
                                name_found = True
                                break
                        if name_found:
                            break
    
    print(f"    📊 Total policy-name pairs extracted: {len(pairs)}")
    return pairs

def pdf_processor():
    """Process PDFs from incoming directory with IMPROVED extraction logic"""
    db_path = get_project_root() / "data" / "lic_customers.db"  # Use main database
    incoming_path = get_project_root() / "data" / "pdfs" / "incoming"
    processed_path = get_project_root() / "data" / "pdfs" / "processed"
    errors_path = get_project_root() / "data" / "pdfs" / "errors"
    duplicates_path = get_project_root() / "data" / "pdfs" / "duplicates"
    
    # Create directories if they don't exist
    for path in [processed_path, errors_path, duplicates_path]:
        path.mkdir(parents=True, exist_ok=True)
    
    # Create database if it doesn't exist
    if not db_path.exists():
        print("📝 Creating main database...")
        from database_setup import create_database
        create_database()
    
    # Get all PDF files from incoming directory
    if not incoming_path.exists():
        print("❌ Incoming directory not found!")
        return
    
    pdf_files = list(incoming_path.glob("*.pdf"))
    
    if not pdf_files:
        print("📄 No PDF files found in incoming directory")
        print(f"📂 Drop PDF files into: {incoming_path}")
        return
    
    print(f"📄 Found {len(pdf_files)} PDF files to process...")
    
    # Use proper database connection with error handling
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    policies_added = 0
    customers_added = 0
    files_processed = 0
    files_with_errors = 0
    files_duplicated = 0
    
    for pdf_file in pdf_files:
        print(f"\n🔄 Processing: {pdf_file.name}")
        
        # Check if file is already processed
        if is_file_already_processed(pdf_file.name, pdf_file, db_path):
            print(f"  🔄 Duplicate detected! File already processed.")
            
            duplicate_location = move_to_duplicates(pdf_file, duplicates_path)
            if duplicate_location:
                print(f"  📂 Moved to: {duplicate_location}")
                files_duplicated += 1
            else:
                print(f"  ❌ Failed to move duplicate file")
                files_with_errors += 1
            continue
        
        try:
            with pdfplumber.open(pdf_file) as pdf:
                # Extract text from all pages to get complete information
                full_text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        full_text += page_text + "\n"
                
                # Add filename to text for better format detection
                full_text = f"FILENAME: {pdf_file.name}\n" + full_text
                
                # Enhanced text validation with specific error logging
                if not full_text or len(full_text.strip()) < 10:
                    error_reason = "No meaningful text could be extracted from PDF"
                    print(f"  ⚠️  {error_reason}")
                    log_error(pdf_file.name, error_reason, errors_path)
                    shutil.move(str(pdf_file), str(errors_path / pdf_file.name))
                    files_with_errors += 1
                    continue
                
                # Look for agent code
                agent_code = '0163674N'  # Default to A. MUTHURAMALINGAM
                if '0089174N' in full_text:
                    agent_code = '0089174N'  # M. NAGANATHAN
                elif '0009274N' in full_text:
                    agent_code = '0009274N'  # V. POTHUMPEN
                
                print(f"  👤 Agent detected: {agent_code}")
                
                # PRIMARY: Extract policy-name pairs (every name has a policy)
                policy_name_pairs = extract_policy_name_pairs(full_text)
                
                # SECONDARY: Extract standalone policy numbers for validation
                all_policy_numbers = re.findall(r'\b\d{9}\b', full_text)
                unique_policies = list(set(all_policy_numbers))
                
                print(f"  🔗 Found {len(policy_name_pairs)} policy-name pairs")
                print(f"  📋 Found {len(unique_policies)} total policy numbers")
                
                if not policy_name_pairs:
                    error_reason = f"No policy-name pairs found. Found {len(unique_policies)} policies but no associated names."
                    print(f"  ⚠️  {error_reason}")
                    log_error(pdf_file.name, error_reason, errors_path)
                    shutil.move(str(pdf_file), str(errors_path / pdf_file.name))
                    files_with_errors += 1
                    continue
                
                # Process each policy-name pair
                policies_in_this_file = 0
                database_errors = []
                existing_policies_count = 0
                
                for policy, customer_name in policy_name_pairs:
                    try:
                        # Check if policy already exists
                        cursor.execute('SELECT policy_number FROM policies WHERE policy_number = ?', (policy,))
                        if cursor.fetchone():
                            print(f"    ↪️  Policy {policy} already exists")
                            existing_policies_count += 1
                            database_errors.append(f"Policy {policy} already exists")
                            continue
                        
                        # Final validation - ensure it's not a policy number masquerading as a name
                        if re.match(r'^\d{9}$', customer_name.replace(' ', '')):
                            print(f"    ❌ Skipping invalid name: {customer_name}")
                            continue
                        
                        print(f"    👤 Processing: {policy} → {customer_name}")
                        
                        # Insert customer (allow duplicates, they'll be cleaned up later)
                        cursor.execute('INSERT INTO customers (customer_name, extraction_method) VALUES (?, ?)', 
                                     (customer_name, 'regex'))
                        customer_id = cursor.lastrowid
                        customers_added += 1
                        
                        # Insert policy
                        cursor.execute('''
                            INSERT INTO policies (policy_number, customer_id, agent_code, status)
                            VALUES (?, ?, ?, ?)
                        ''', (policy, customer_id, agent_code, 'Active'))
                        policies_added += 1
                        policies_in_this_file += 1
                        
                        print(f"    ✅ Added: {policy} → {customer_name}")
                        
                    except sqlite3.Error as db_err:
                        error_msg = f"Database error for policy {policy}: {db_err}"
                        print(f"    ❌ {error_msg}")
                        database_errors.append(error_msg)
                        continue
                
                if policies_in_this_file > 0:
                    shutil.move(str(pdf_file), str(processed_path / pdf_file.name))
                    files_processed += 1
                    print(f"  ✅ Processed {policies_in_this_file} policy-name pairs from {pdf_file.name}")
                    
                    # Record document in database for duplicate tracking
                    try:
                        # Extract content hash for future duplicate detection
                        content_hash, _ = extract_content_hash(processed_path / pdf_file.name)
                        
                        # Determine document type
                        document_type = "Unknown"
                        filename_upper = pdf_file.name.upper()
                        if "CM-" in filename_upper or "COMMISSION" in filename_upper:
                            document_type = "Commission"
                        elif "CLAIM" in filename_upper:
                            document_type = "Claims"  
                        elif "PREMDUE" in filename_upper or "PREMIUM" in filename_upper:
                            document_type = "Premium Due"
                        
                        # Insert document record
                        cursor.execute("""
                            INSERT INTO documents 
                            (policy_number, document_type, file_name, file_path, content_hash, processed_at)
                            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """, (None, document_type, pdf_file.name, str(processed_path / pdf_file.name), content_hash))
                        
                        print(f"  📝 Document tracked with content hash: {content_hash[:8]}...")
                        
                    except Exception as doc_error:
                        print(f"  ⚠️ Could not track document: {doc_error}")
                        # Continue processing even if document tracking fails
                else:
                    # Check if all database errors were due to existing policies
                    all_existing_policies = all("already exists" in error.lower() for error in database_errors) if database_errors else False
                    
                    if all_existing_policies and len(policy_name_pairs) > 0:
                        # This file contains only existing policies - move to duplicates folder
                        print(f"  🔄 File contains only existing policies ({len(policy_name_pairs)} policies already in database)")
                        
                        duplicate_location = move_to_duplicates(pdf_file, duplicates_path)
                        if duplicate_location:
                            print(f"  📂 Moved to duplicates: {duplicate_location}")
                            files_duplicated += 1
                        else:
                            print(f"  ❌ Failed to move to duplicates")
                            files_with_errors += 1
                    else:
                        # This is a genuine error
                        error_reason = f"No valid policy-name pairs could be processed. Found {len(policy_name_pairs)} pairs but all had issues."
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
                log_error(pdf_file.name, f"{error_reason}. ADDITIONAL ERROR: {additional_error}", errors_path)
    
    # Commit and close connection
    try:
        conn.commit()
        print("✓ Database changes committed")
    except Exception as db_error:
        print(f"  ⚠️  Database commit error: {db_error}")
    finally:
        conn.close()
    
    print(f"\n🎉 === IMPROVED PROCESSING SUMMARY ===")
    print(f"📄 Files processed successfully: {files_processed}")
    print(f"❌ Files with errors: {files_with_errors}")
    print(f"� Files duplicated (already processed): {files_duplicated}")
    print(f"�👥 New customers added: {customers_added}")
    print(f"📋 New policies added: {policies_added}")
    print(f"💾 Database saved to: {db_path}")
    print(f"\n📂 Check folders:")
    print(f"  ✅ Processed: {processed_path}")
    print(f"  ❌ Errors: {errors_path}")
    print(f"  🔄 Duplicates: {duplicates_path}")

if __name__ == "__main__":
    pdf_processor()