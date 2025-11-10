"""
Update Missing Agent Codes from Premium Due PDFs
Processes PDFs from incoming folder and updates agent codes for customers who don't have one.

Agent Code Format: "Agent Code : LICxxxxxxN" where xxxxxxx is the agent code (7 digits + N)
Policy information is in table with columns "PolicyNo" and "Name of Assured"
"""

import pdfplumber
import os
import re
from pathlib import Path
from datetime import datetime
from supabase import create_client, Client

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

def extract_agent_code_from_premium_due_pdf(pdf_path):
    """Extract agent code from Premium Due PDF header (format: Agent Code : LICxxxxxxN)"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            first_page = pdf.pages[0]
            text = first_page.extract_text()
            
            if not text:
                return None
            
            lines = text.split('\n')
            
            # Look for "Agent Code : LICxxxxxxN" in first 20 lines
            for line in lines[:20]:
                # Match pattern: Agent Code : LIC0163674N
                # Extract only the part after LIC (0163674N)
                agent_match = re.search(r'Agent\s+Code\s*:\s*LIC(\d{7}N)', line, re.IGNORECASE)
                if agent_match:
                    agent_code = agent_match.group(1)
                    return agent_code
            
            return None
    except Exception as e:
        print(f"  ❌ Error reading {pdf_path.name}: {e}")
        return None

def extract_agent_code_from_commission_pdf(pdf_path):
    """Extract agent code from Commission Bill PDF (format: LICxxxxxxN-xxxxx)"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            first_page = pdf.pages[0]
            text = first_page.extract_text()
            
            if not text:
                return None
            
            lines = text.split('\n')
            
            # Look for pattern like "LIC0089174N-77375" in first 30 lines
            for line in lines[:30]:
                # Match pattern: LIC followed by 7 digits and N, then optional suffix
                # We want to extract only the part after LIC and before the hyphen
                agent_match = re.search(r'LIC(\d{7}N)(?:-\d+)?', line)
                if agent_match:
                    agent_code = agent_match.group(1)
                    return agent_code
            
            return None
    except Exception as e:
        print(f"  ❌ Error reading {pdf_path.name}: {e}")
        return None

def detect_pdf_type(pdf_path):
    """Detect if PDF is Premium Due or Commission Bill type"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            first_page = pdf.pages[0]
            text = first_page.extract_text()
            
            if not text:
                return None
            
            text_lower = text.lower()
            
            # Check for indicators
            if 'premium due' in text_lower or 'premdue' in pdf_path.name.lower():
                return 'premium_due'
            elif 'commission' in text_lower or 'commission' in pdf_path.name.lower():
                return 'commission'
            
            return None
    except Exception as e:
        print(f"  ❌ Error detecting PDF type for {pdf_path.name}: {e}")
        return None

def extract_policy_details_from_pdf(pdf_path):
    """Extract policy numbers with customer names from PDF
    Returns dict: {policy_number: customer_name}"""
    policy_details = {}
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                
                if not text:
                    continue
                
                lines = text.split('\n')
                
                # Look for lines with policy numbers and names
                for line in lines:
                    # Skip obvious header lines
                    if 'S.No' in line or 'Policy' in line.replace('.', '') and 'No' in line:
                        continue
                    
                    # Find 9-digit policy numbers
                    policy_matches = re.findall(r'\b(\d{9})\b', line)
                    
                    if policy_matches:
                        # Extract potential customer name from the line
                        # Remove the policy number and extract alphabetic text
                        line_clean = line
                        for policy_no in policy_matches:
                            line_clean = line_clean.replace(policy_no, '')
                        
                        # Extract name (sequences of alphabetic characters and spaces)
                        # Look for names that are at least 3 characters
                        name_match = re.search(r'([A-Z][A-Za-z\s\.]{2,50})', line_clean)
                        if name_match:
                            customer_name = name_match.group(1).strip()
                            # Clean up extra spaces
                            customer_name = ' '.join(customer_name.split())
                            
                            for policy_no in policy_matches:
                                if policy_no not in policy_details:
                                    policy_details[policy_no] = customer_name
        
        return policy_details
    except Exception as e:
        print(f"  ❌ Error extracting policy details from {pdf_path.name}: {e}")
        return {}

def extract_policy_numbers_from_pdf(pdf_path):
    """Extract all policy numbers from Premium Due or Commission Bill PDF
    Uses flexible pattern matching to find 9-digit policy numbers with adjacent names"""
    policy_numbers = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                
                if not text:
                    continue
                
                lines = text.split('\n')
                
                # Look for 9-digit policy numbers in the table
                for line in lines:
                    # Skip obvious header lines
                    if 'S.No' in line or 'Policy' in line.replace('.', '') and 'No' in line:
                        continue
                    
                    # Find 9-digit policy numbers
                    # Look for pattern: 9 digits followed by or preceded by text (customer name)
                    # This handles both "PolicyNo Name" and "Name PolicyNo" formats
                    
                    # Pattern 1: Find all 9-digit numbers
                    policy_matches = re.findall(r'\b(\d{9})\b', line)
                    
                    for policy_no in policy_matches:
                        # Verify this line has some alphabetic text (likely a name)
                        # This helps filter out non-policy numbers
                        if re.search(r'[A-Za-z]{3,}', line):
                            if policy_no not in policy_numbers:
                                policy_numbers.append(policy_no)
        
        return policy_numbers
    except Exception as e:
        print(f"  ❌ Error extracting policies from {pdf_path.name}: {e}")
        return []

def get_policies_without_agent_code(supabase):
    """Get all policies that don't have an agent code"""
    try:
        response = supabase.table('policies').select('policy_number, agent_code').execute()
        
        policies_without_agent = []
        for policy in response.data:
            agent_code = policy.get('agent_code')
            # Check if agent_code is None, empty string, or whitespace
            if not agent_code or agent_code.strip() == '':
                policies_without_agent.append(policy)
        
        return policies_without_agent
    except Exception as e:
        print(f"❌ Error fetching policies: {e}")
        return []

def get_all_policy_numbers(supabase):
    """Get all existing policy numbers from database"""
    try:
        response = supabase.table('policies').select('policy_number').execute()
        return set(policy['policy_number'] for policy in response.data)
    except Exception as e:
        print(f"❌ Error fetching policy numbers: {e}")
        return set()

def find_or_create_customer(supabase, customer_name):
    """Find existing customer by name or create new one"""
    try:
        # Try to find existing customer by name (case-insensitive)
        response = supabase.table('customers').select('customer_id, customer_name').ilike('customer_name', customer_name).execute()
        
        if response.data and len(response.data) > 0:
            # Customer exists
            return response.data[0]['customer_id']
        
        # Create new customer
        new_customer = {
            'customer_name': customer_name,
            'extraction_method': 'pdf_auto_import',
            'created_date': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat()
        }
        
        response = supabase.table('customers').insert(new_customer).execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]['customer_id']
        
        return None
    except Exception as e:
        print(f"  ❌ Error finding/creating customer {customer_name}: {e}")
        return None

def create_policy(supabase, policy_number, customer_id, agent_code):
    """Create a new policy in the database"""
    try:
        new_policy = {
            'policy_number': policy_number,
            'customer_id': customer_id,
            'agent_code': agent_code,
            'status': 'Active',
            'extraction_method': 'pdf_auto_import',
            'created_date': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat()
        }
        
        supabase.table('policies').insert(new_policy).execute()
        return True
    except Exception as e:
        print(f"  ❌ Error creating policy {policy_number}: {e}")
        return False

def update_agent_code(supabase, policy_number, agent_code):
    """Update agent code for a specific policy"""
    try:
        supabase.table('policies').update({
            'agent_code': agent_code,
            'last_updated': datetime.now().isoformat()
        }).eq('policy_number', policy_number).execute()
        return True
    except Exception as e:
        print(f"  ❌ Error updating policy {policy_number}: {e}")
        return False

def main():
    print("=" * 70)
    print("🔄 UPDATE MISSING AGENT CODES FROM PREMIUM DUE PDFs")
    print("=" * 70)
    print()
    
    # Setup paths
    project_root = Path(__file__).parent.parent
    incoming_folder = project_root / 'data' / 'pdfs' / 'incoming'
    
    if not incoming_folder.exists():
        print(f"❌ Incoming folder not found: {incoming_folder}")
        return
    
    # Connect to Supabase
    print("📡 Connecting to Supabase...")
    try:
        supabase = get_supabase_client()
        print("✅ Connected to Supabase")
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return
    
    print()
    
    # Get policies without agent codes
    print("🔍 Fetching policies without agent codes...")
    policies_without_agent = get_policies_without_agent_code(supabase)
    print(f"📊 Found {len(policies_without_agent)} policies without agent codes")
    print()
    
    if len(policies_without_agent) == 0:
        print("✅ All policies have agent codes!")
        return
    
    # Create a mapping of policy_number -> policy_number for quick lookup
    policy_mapping = {
        policy['policy_number']: policy['policy_number'] 
        for policy in policies_without_agent
    }
    
    # Process PDF files
    pdf_files = list(incoming_folder.glob('*.pdf'))
    print(f"📁 Found {len(pdf_files)} PDF files in incoming folder")
    print()
    
    total_updates = 0
    updates_by_file = {}
    premium_due_count = 0
    commission_count = 0
    unknown_count = 0
    
    for pdf_file in pdf_files:
        print(f"📄 Processing: {pdf_file.name}")
        
        # Detect PDF type
        pdf_type = detect_pdf_type(pdf_file)
        
        if pdf_type == 'premium_due':
            print(f"  📋 Type: Premium Due List")
            agent_code = extract_agent_code_from_premium_due_pdf(pdf_file)
            premium_due_count += 1
        elif pdf_type == 'commission':
            print(f"  💰 Type: Commission Bill")
            agent_code = extract_agent_code_from_commission_pdf(pdf_file)
            commission_count += 1
        else:
            print(f"  ❓ Type: Unknown - trying both formats")
            # Try both extraction methods
            agent_code = extract_agent_code_from_premium_due_pdf(pdf_file)
            if not agent_code:
                agent_code = extract_agent_code_from_commission_pdf(pdf_file)
            unknown_count += 1
        
        if not agent_code:
            print(f"  ⚠️  No agent code found in header, skipping...")
            print()
            continue
        
        print(f"  🏢 Agent Code: {agent_code}")
        
        # Extract all policy numbers from this PDF
        policy_numbers = extract_policy_numbers_from_pdf(pdf_file)
        print(f"  📋 Found {len(policy_numbers)} policy numbers in PDF")
        
        # Update policies that are in our "missing agent code" list
        file_updates = 0
        for policy_number in policy_numbers:
            if policy_number in policy_mapping:
                
                if update_agent_code(supabase, policy_number, agent_code):
                    print(f"  ✅ Updated policy {policy_number} with agent code {agent_code}")
                    file_updates += 1
                    total_updates += 1
        
        updates_by_file[pdf_file.name] = file_updates
        print(f"  📊 Updated {file_updates} policies from this file")
        print()
    
    # Summary for agent code updates
    print("=" * 70)
    print("📊 AGENT CODE UPDATE SUMMARY")
    print("=" * 70)
    print(f"Total policies updated: {total_updates}")
    print()
    print(f"PDF Types processed:")
    print(f"  📋 Premium Due Lists: {premium_due_count}")
    print(f"  💰 Commission Bills: {commission_count}")
    if unknown_count > 0:
        print(f"  ❓ Unknown type: {unknown_count}")
    print()
    
    if updates_by_file:
        print("Updates by file:")
        for filename, count in updates_by_file.items():
            if count > 0:
                print(f"  • {filename}: {count} policies")
    
    remaining = len(policies_without_agent) - total_updates
    if remaining > 0:
        print()
        print(f"⚠️  {remaining} policies still don't have agent codes")
        print("   (Their policy numbers might not be in the current PDF files)")
    else:
        print()
        print("✅ All policies now have agent codes!")
    
    print()
    print("=" * 70)
    
    # ========================================================================
    # PART 2: CHECK FOR MISSING POLICY NUMBERS AND ADD THEM
    # ========================================================================
    
    print()
    print("=" * 70)
    print("🔍 CHECKING FOR MISSING POLICY NUMBERS")
    print("=" * 70)
    print()
    
    # Get all existing policy numbers from database
    print("📊 Fetching existing policy numbers from database...")
    existing_policies = get_all_policy_numbers(supabase)
    print(f"✅ Found {len(existing_policies)} existing policies in database")
    print()
    
    # Collect all policy numbers and details from PDFs
    print("📄 Scanning PDFs for policy numbers and customer names...")
    all_pdf_policies = {}  # {policy_number: {name, agent_code}}
    
    for pdf_file in pdf_files:
        # Detect PDF type and extract agent code
        pdf_type = detect_pdf_type(pdf_file)
        
        if pdf_type == 'premium_due':
            agent_code = extract_agent_code_from_premium_due_pdf(pdf_file)
        elif pdf_type == 'commission':
            agent_code = extract_agent_code_from_commission_pdf(pdf_file)
        else:
            agent_code = extract_agent_code_from_premium_due_pdf(pdf_file)
            if not agent_code:
                agent_code = extract_agent_code_from_commission_pdf(pdf_file)
        
        if not agent_code:
            continue
        
        # Extract policy details (policy number + customer name)
        policy_details = extract_policy_details_from_pdf(pdf_file)
        
        for policy_number, customer_name in policy_details.items():
            if policy_number not in all_pdf_policies:
                all_pdf_policies[policy_number] = {
                    'customer_name': customer_name,
                    'agent_code': agent_code
                }
    
    print(f"✅ Found {len(all_pdf_policies)} unique policy numbers in PDFs")
    print()
    
    # Find missing policies
    missing_policies = []
    for policy_number, details in all_pdf_policies.items():
        if policy_number not in existing_policies:
            missing_policies.append({
                'policy_number': policy_number,
                'customer_name': details['customer_name'],
                'agent_code': details['agent_code']
            })
    
    if not missing_policies:
        print("✅ No missing policies found. All PDF policies are in the database!")
    else:
        print(f"⚠️  Found {len(missing_policies)} policy numbers missing from database")
        print()
        
        # Show sample of missing policies
        print("Sample of missing policies:")
        for i, policy in enumerate(missing_policies[:10]):
            print(f"  {i+1}. {policy['policy_number']} - {policy['customer_name']} (Agent: {policy['agent_code']})")
        if len(missing_policies) > 10:
            print(f"  ... and {len(missing_policies) - 10} more")
        print()
        
        # Create missing policies
        print("🔄 Creating missing policies in database...")
        created_count = 0
        failed_count = 0
        
        for policy in missing_policies:
            # Find or create customer
            customer_id = find_or_create_customer(supabase, policy['customer_name'])
            
            if customer_id:
                # Create policy
                if create_policy(supabase, policy['policy_number'], customer_id, policy['agent_code']):
                    created_count += 1
                    print(f"  ✅ Created: {policy['policy_number']} - {policy['customer_name']}")
                else:
                    failed_count += 1
            else:
                failed_count += 1
                print(f"  ❌ Failed to create customer for: {policy['customer_name']}")
        
        print()
        print(f"📊 Creation Summary:")
        print(f"  ✅ Successfully created: {created_count} policies")
        if failed_count > 0:
            print(f"  ❌ Failed: {failed_count} policies")
    
    print()
    print("=" * 70)
    print("✅ ALL TASKS COMPLETED!")
    print("=" * 70)

if __name__ == "__main__":
    main()
