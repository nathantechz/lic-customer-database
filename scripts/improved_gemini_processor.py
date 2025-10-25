import pdfplumber
import sqlite3
import os
import re
import shutil
from pathlib import Path
from datetime import datetime
import json

def get_project_root():
    """Get the project root directory"""
    return Path(__file__).parent.parent

def setup_gemini():
    """Setup Gemini API with key"""
    try:
        import google.generativeai as genai
        api_key_file = get_project_root() / "config" / "gemini_api_key.txt"
        
        if not api_key_file.exists():
            print("❌ Gemini API key not found!")
            print(f"Please create file: {api_key_file}")
            print("And add your Gemini API key to it")
            return None
        
        with open(api_key_file, 'r') as f:
            api_key = f.read().strip()
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        print("✅ Gemini initialized successfully")
        return model
    except Exception as e:
        print(f"❌ Error setting up Gemini: {e}")
        return None

def extract_policy_name_pairs_with_ai(text, filename):
    """Use Gemini AI to extract policy-name pairs from table rows"""
    model = setup_gemini()
    if not model:
        return []
    
    # Detect document type for better prompting
    is_commission = 'Commission' in text or 'PH Name' in text
    is_claims = 'Claims' in text or 'Claim' in text
    is_premium = 'Premium Due' in text or 'Name of Assured' in text
    
    if is_commission:
        doc_type = "Commission document with 'PH Name' column"
        table_format = "Serial_Number PH_Name Policy_Number Plan_Term Due_Date Risk_Date CBO Adjusted_Date Premium Commission"
    elif is_claims:
        doc_type = "Claims document with customer names after plan numbers"
        table_format = "Serial_Number Policy_Number Type Due_Date Plan_Number Customer_Name Amount NEFT_Flag"
    elif is_premium:
        doc_type = "Premium Due document with 'Name of Assured' column"
        table_format = "Policy_Number Name_of_Assured Due_Date Premium_Amount Status"
    else:
        doc_type = "LIC policy document"
        table_format = "Unknown format - extract any policy number and name pairs you can find"
    
    prompt = f"""
You are analyzing a {doc_type}. Extract ONLY policy-name pairs from table rows where you can clearly see both a 9-digit policy number AND a customer name in the same row.

STRICT RULES:
1. Each pair MUST have both a 9-digit policy number AND a customer name from the same table row
2. Ignore any names that don't have corresponding policy numbers in the same row  
3. Customer names are real human names (not amounts, dates, or codes)
4. Policy numbers are exactly 9 digits
5. Table format is typically: {table_format}

Return as JSON array of objects:
[
  {{"policy": "123456789", "name": "Customer Name"}},
  {{"policy": "987654321", "name": "Another Customer"}}
]

Document filename: {filename}

Document text (first 5000 chars):
{text[:5000]}

IMPORTANT: Only return pairs where policy number and name are clearly in the same table row. If no clear pairs exist, return []

Return ONLY the JSON array, nothing else:
"""

    try:
        response = model.generate_content(prompt)
        result_text = response.text.strip()
        print(f"    🤖 AI raw response length: {len(result_text)} chars")
        
        # Clean up the response text
        result_text = result_text.replace('```json', '').replace('```', '').strip()
        
        # Try to find JSON array in the response
        if '[' in result_text and ']' in result_text:
            start_idx = result_text.find('[')
            end_idx = result_text.rfind(']') + 1
            json_str = result_text[start_idx:end_idx]
            
            try:
                pairs_data = json.loads(json_str)
                if isinstance(pairs_data, list):
                    valid_pairs = []
                    for item in pairs_data:
                        if (isinstance(item, dict) and 
                            'policy' in item and 'name' in item and
                            isinstance(item['policy'], str) and 
                            isinstance(item['name'], str) and
                            re.match(r'^\d{9}$', item['policy']) and
                            len(item['name'].strip()) >= 3):
                            
                            policy = item['policy']
                            name = clean_customer_name(item['name'].strip())
                            if name:
                                valid_pairs.append((policy, name))
                                print(f"    🤖 AI extracted: {policy} → {name}")
                    
                    print(f"    🤖 AI found {len(valid_pairs)} valid policy-name pairs")
                    return valid_pairs
                    
            except json.JSONDecodeError as e:
                print(f"    ⚠️ JSON parse error: {e}")
        
        print("    ⚠️ No valid JSON found in AI response")
        return []
        
    except Exception as e:
        print(f"    ❌ AI extraction error: {e}")
        return []

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

def gemini_pdf_processor():
    """Process PDFs from incoming directory using Gemini AI for extraction"""
    db_path = get_project_root() / "data" / "lic_customers_gemini.db"
    incoming_path = get_project_root() / "data" / "pdfs" / "incoming"
    processed_path = get_project_root() / "data" / "pdfs" / "processed_gemini"
    errors_path = get_project_root() / "data" / "pdfs" / "errors_gemini"
    
    # Create directories if they don't exist
    for path in [processed_path, errors_path]:
        path.mkdir(parents=True, exist_ok=True)
    
    # Create database if it doesn't exist
    if not db_path.exists():
        print("📝 Creating Gemini database...")
        from fixed_database_setup import create_database_at_path
        create_database_at_path(db_path)
    
    # Check if Gemini is available
    model = setup_gemini()
    if not model:
        print("❌ Gemini AI is not available. Please set up your API key.")
        return
    
    # Get all PDF files from incoming directory
    if not incoming_path.exists():
        print("❌ Incoming directory not found!")
        return
    
    pdf_files = list(incoming_path.glob("*.pdf"))
    
    if not pdf_files:
        print("📄 No PDF files found in incoming directory")
        print(f"📂 Drop PDF files into: {incoming_path}")
        return
    
    print(f"📄 Found {len(pdf_files)} PDF files to process with Gemini AI...")
    
    # Use proper database connection with error handling
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    policies_added = 0
    customers_added = 0
    files_processed = 0
    files_with_errors = 0
    
    for pdf_file in pdf_files:
        print(f"\n🔄 Processing with AI: {pdf_file.name}")
        
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
                
                # PRIMARY: Use Gemini AI to extract policy-name pairs
                policy_name_pairs = extract_policy_name_pairs_with_ai(full_text, pdf_file.name)
                
                # SECONDARY: Extract standalone policy numbers for validation
                all_policy_numbers = re.findall(r'\b\d{9}\b', full_text)
                unique_policies = list(set(all_policy_numbers))
                
                print(f"  🔗 AI found {len(policy_name_pairs)} policy-name pairs")
                print(f"  📋 Found {len(unique_policies)} total policy numbers in document")
                
                if not policy_name_pairs:
                    error_reason = f"No policy-name pairs found by AI. Found {len(unique_policies)} policies but no associated names."
                    print(f"  ⚠️  {error_reason}")
                    log_error(pdf_file.name, error_reason, errors_path)
                    shutil.move(str(pdf_file), str(errors_path / pdf_file.name))
                    files_with_errors += 1
                    continue
                
                # Process each policy-name pair
                policies_in_this_file = 0
                database_errors = []
                
                for policy, customer_name in policy_name_pairs:
                    try:
                        # Check if policy already exists
                        cursor.execute('SELECT policy_number FROM policies WHERE policy_number = ?', (policy,))
                        if cursor.fetchone():
                            print(f"    ↪️  Policy {policy} already exists")
                            continue
                        
                        # Final validation - ensure it's not a policy number masquerading as a name
                        if re.match(r'^\d{9}$', customer_name.replace(' ', '')):
                            print(f"    ❌ Skipping invalid name: {customer_name}")
                            continue
                        
                        print(f"    👤 Processing: {policy} → {customer_name}")
                        
                        # Insert customer
                        cursor.execute('INSERT INTO customers (customer_name) VALUES (?)', 
                                     (customer_name,))
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
                    print(f"  ✅ AI processed {policies_in_this_file} policy-name pairs from {pdf_file.name}")
                else:
                    error_reason = f"No valid policy-name pairs could be processed by AI. Found {len(policy_name_pairs)} pairs but all had issues."
                    if database_errors:
                        error_reason += f" Database errors: {'; '.join(database_errors)}"
                    
                    print(f"  ⚠️  {error_reason}")
                    log_error(pdf_file.name, error_reason, errors_path)
                    shutil.move(str(pdf_file), str(errors_path / pdf_file.name))
                    files_with_errors += 1
        
        except Exception as e:
            error_reason = f"Exception during AI PDF processing: {str(e)} (Type: {type(e).__name__})"
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
    
    print(f"\n🎉 === GEMINI AI PROCESSING SUMMARY ===")
    print(f"📄 Files processed successfully: {files_processed}")
    print(f"❌ Files with errors: {files_with_errors}")
    print(f"👥 New customers added: {customers_added}")
    print(f"📋 New policies added: {policies_added}")
    print(f"💾 Database saved to: {db_path}")
    print(f"\n📂 Check folders:")
    print(f"  ✅ Processed: {processed_path}")
    print(f"  ❌ Errors: {errors_path}")

if __name__ == "__main__":
    gemini_pdf_processor()