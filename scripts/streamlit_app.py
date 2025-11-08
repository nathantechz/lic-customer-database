import streamlit as st
import pandas as pd
from pathlib import Path
import re
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import os
from supabase import create_client, Client

def get_supabase_client() -> Client:
    """Get Supabase client connection"""
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"❌ Failed to connect to Supabase: {e}")
        st.info("Please configure Supabase credentials in .streamlit/secrets.toml")
        st.stop()

def validate_email(email):
    """Validate email format"""
    if not email:
        return True, ""  # Optional field
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if re.match(pattern, email):
        return True, ""
    else:
        return False, "Invalid email format"

def validate_phone_number(phone):
    """Validate Indian phone number format (+91 followed by 10 digits)"""
    if not phone:
        return True, ""  # Optional field
    
    # Remove all spaces and special characters except +
    cleaned_phone = re.sub(r'[^\d+]', '', phone)
    
    # Check if it matches +91 followed by exactly 10 digits
    pattern = r'^\+91\d{10}$'
    if re.match(pattern, cleaned_phone):
        return True, cleaned_phone
    else:
        return False, "Phone number must be in format +91XXXXXXXXXX (10 digits after +91)"

def validate_aadhaar(aadhaar):
    """Validate Aadhaar number format (12 digits)"""
    if not aadhaar:
        return True, ""  # Optional field
    
    # Remove all spaces and special characters
    cleaned_aadhaar = re.sub(r'[^\d]', '', aadhaar)
    
    if len(cleaned_aadhaar) == 12 and cleaned_aadhaar.isdigit():
        return True, cleaned_aadhaar
    else:
        return False, "Aadhaar number must be exactly 12 digits"

def validate_date_of_birth(dob):
    """Validate date of birth (should not be in future and reasonable age)"""
    if not dob:
        return True, ""  # Optional field
    
    if isinstance(dob, str):
        try:
            dob = datetime.strptime(dob, '%Y-%m-%d').date()
        except:
            return False, "Invalid date format"
    
    today = date.today()
    
    if dob > today:
        return False, "Date of birth cannot be in the future"
    
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if age > 120:
        return False, "Date of birth seems unrealistic (age > 120 years)"
    
    return True, dob.strftime('%Y-%m-%d')

@st.cache_data
def get_project_root():
    """Get the project root directory"""
    # Check if running on Streamlit Cloud
    if os.getenv('STREAMLIT_SHARING_MODE') or os.getenv('STREAMLIT_CLOUD'):
        # Use current working directory on cloud
        return Path.cwd()
    
    # Local development - try to find the root directory
    current_file = Path(__file__).resolve()
    # Go up from scripts/ to project root
    return current_file.parent.parent

def check_database_exists():
    """Check if Supabase connection is available"""
    try:
        supabase = get_supabase_client()
        # Test connection by querying customers table
        response = supabase.table('customers').select("customer_id", count='exact').limit(1).execute()
        return True, "Supabase"
    except Exception as e:
        return False, f"Error: {str(e)}"

def get_database_connection():
    """Get Supabase client connection"""
    try:
        supabase = get_supabase_client()
        return supabase
    except Exception as e:
        st.error(f"❌ Could not connect to Supabase: {e}")
        return None

def find_potential_duplicates(customers):
    """Find potential duplicate customers based on multiple identifiers"""
    potential_duplicates = []
    
    for i, customer1 in enumerate(customers):
        for j, customer2 in enumerate(customers[i+1:], i+1):
            match_reasons = []
            
            # Check for exact name match (case insensitive)
            name1 = (customer1.get('customer_name') or '').strip().lower()
            name2 = (customer2.get('customer_name') or '').strip().lower()
            
            if name1 and name2 and name1 == name2:
                match_reasons.append("Same name")
            
            # Check for phone number match
            phone1 = (customer1.get('phone_number') or '').strip()
            phone2 = (customer2.get('phone_number') or '').strip()
            
            if phone1 and phone2 and phone1 == phone2:
                match_reasons.append("Same phone")
            
            # Check for Aadhaar match
            aadhaar1 = (customer1.get('aadhaar_number') or '').strip()
            aadhaar2 = (customer2.get('aadhaar_number') or '').strip()
            
            if aadhaar1 and aadhaar2 and aadhaar1 == aadhaar2:
                match_reasons.append("Same Aadhaar")
            
            # Check for DOB match
            dob1 = (customer1.get('date_of_birth') or '').strip()
            dob2 = (customer2.get('date_of_birth') or '').strip()
            
            if dob1 and dob2 and dob1 == dob2:
                match_reasons.append("Same DOB")
            
            # If we have at least 2 matching criteria, consider them potential duplicates
            if len(match_reasons) >= 2:
                potential_duplicates.append({
                    'customer1': customer1,
                    'customer2': customer2,
                    'match_reasons': match_reasons
                })
    
    return potential_duplicates

def search_customers(query=""):
    """Search customers in the database with duplicate detection - searches by name, phone, address, aadhaar, policy number, and premium amount"""
    supabase = get_database_connection()
    if not supabase:
        return [], 0
    
    try:
        if query:
            # First, search in customers table by name, phone, email, aadhaar, nickname, address
            response = supabase.table('customers').select(
                '*, policies(*, premium_records(*))'
            ).or_(
                f'customer_name.ilike.%{query}%,'
                f'phone_number.ilike.%{query}%,'
                f'alt_phone_number.ilike.%{query}%,'
                f'email.ilike.%{query}%,'
                f'aadhaar_number.ilike.%{query}%,'
                f'nickname.ilike.%{query}%,'
                f'full_address.ilike.%{query}%'
            ).order('customer_name').execute()
            
            customers_dict = {}
            if response.data:
                for customer in response.data:
                    customers_dict[customer['customer_id']] = customer
            
            # Also search in policies table for policy number, agent code, and premium amount
            try:
                # Try to parse query as a number for premium search
                query_as_number = None
                try:
                    query_as_number = float(query.replace(',', '').replace('₹', '').strip())
                except:
                    pass
                
                # Search policies by policy number or agent code
                policy_search_filter = f'policy_number.ilike.%{query}%,agent_code.ilike.%{query}%'
                
                # Add premium amount search if query is a number
                if query_as_number is not None:
                    # Search for premiums within ±10% of the query amount (rounded search)
                    min_premium = query_as_number * 0.9
                    max_premium = query_as_number * 1.1
                    
                    # Get policies matching policy number/agent code
                    policy_response = supabase.table('policies').select(
                        'customer_id, policy_number, premium_amount, agent_code, premium_records(*)'
                    ).or_(policy_search_filter).execute()
                    
                    # Also get policies with matching premium amounts
                    premium_response = supabase.table('policies').select(
                        'customer_id, policy_number, premium_amount, agent_code, premium_records(*)'
                    ).gte('premium_amount', min_premium).lte('premium_amount', max_premium).execute()
                    
                    # Combine results
                    all_policies = []
                    if policy_response.data:
                        all_policies.extend(policy_response.data)
                    if premium_response.data:
                        # Add premium matches, avoiding duplicates
                        existing_policy_numbers = {p['policy_number'] for p in all_policies}
                        for p in premium_response.data:
                            if p['policy_number'] not in existing_policy_numbers:
                                all_policies.append(p)
                else:
                    # Just search by policy number and agent code
                    policy_response = supabase.table('policies').select(
                        'customer_id, policy_number, premium_amount, agent_code, premium_records(*)'
                    ).or_(policy_search_filter).execute()
                    all_policies = policy_response.data if policy_response.data else []
                
                # Get customer IDs from matching policies
                customer_ids_from_policies = set()
                for policy in all_policies:
                    customer_id = policy.get('customer_id')
                    if customer_id:
                        customer_ids_from_policies.add(customer_id)
                
                # Fetch customers for these policy matches if not already in results
                if customer_ids_from_policies:
                    missing_customer_ids = customer_ids_from_policies - set(customers_dict.keys())
                    if missing_customer_ids:
                        missing_customers_response = supabase.table('customers').select(
                            '*, policies(*, premium_records(*))'
                        ).in_('customer_id', list(missing_customer_ids)).execute()
                        
                        if missing_customers_response.data:
                            for customer in missing_customers_response.data:
                                customers_dict[customer['customer_id']] = customer
            
            except Exception as e:
                # If policy search fails, just continue with customer results
                pass
            
            # Convert dict back to list
            customers = list(customers_dict.values())
        else:
            # Get first 100 customers
            response = supabase.table('customers').select(
                '*, policies(*, premium_records(*))'
            ).order('customer_name').limit(100).execute()
            customers = response.data if response.data else []
        
        # Process customers data
        customers_with_policies = []
        total_policies = 0
        
        for customer in customers:
            # Get policies for this customer
            policies = customer.get('policies', [])
            
            # Process each policy to add latest premium
            processed_policies = []
            for policy in policies:
                premium_records = policy.get('premium_records', [])
                if premium_records:
                    # Sort by due_date and get the latest
                    sorted_premiums = sorted(
                        premium_records, 
                        key=lambda x: x.get('due_date', ''), 
                        reverse=True
                    )
                    policy['latest_premium'] = sorted_premiums[0] if sorted_premiums else None
                else:
                    policy['latest_premium'] = None
                processed_policies.append(policy)
            
            customer['policies'] = processed_policies
            total_policies += len(processed_policies)
            customers_with_policies.append(customer)
        
        # Check for potential duplicates
        if customers_with_policies:
            potential_duplicates = find_potential_duplicates(customers_with_policies)
            
            # Add duplicate information to customers
            for customer in customers_with_policies:
                customer['potential_duplicates'] = []
                for dup in potential_duplicates:
                    if (dup['customer1']['customer_id'] == customer['customer_id'] or 
                        dup['customer2']['customer_id'] == customer['customer_id']):
                        customer['potential_duplicates'].append(dup)
        
        return customers_with_policies, total_policies
        
    except Exception as e:
        st.error(f"❌ Database query error: {e}")
        return [], 0

def get_all_addresses():
    """Get all unique addresses from the database"""
    try:
        supabase = get_supabase_client()
        
        # Get all customers with addresses
        response = supabase.table('customers').select('full_address').execute()
        
        addresses = set()
        for customer in response.data:
            address = customer.get('full_address')
            if address and address.strip() and address.lower() != 'n/a':
                addresses.add(address.strip())
        
        return sorted(list(addresses))
    except Exception as e:
        st.error(f"❌ Error fetching addresses: {e}")
        return []

def get_policies_by_address(address):
    """Get all policies for customers at a specific address, sorted by FUP date"""
    try:
        supabase = get_supabase_client()
        
        # Get customers with this address
        customers_response = supabase.table('customers').select(
            'customer_id, customer_name, phone_number, full_address'
        ).eq('full_address', address).execute()
        
        if not customers_response.data:
            return []
        
        customer_ids = [c['customer_id'] for c in customers_response.data]
        customer_map = {c['customer_id']: c for c in customers_response.data}
        
        # Get all policies for these customers
        policies_response = supabase.table('policies').select(
            'policy_number, customer_id, premium_amount, current_fup_date'
        ).in_('customer_id', customer_ids).execute()
        
        # Combine customer and policy data
        policy_list = []
        for policy in policies_response.data:
            customer = customer_map.get(policy['customer_id'])
            if customer:
                policy_list.append({
                    'policy_number': policy['policy_number'],
                    'customer_name': customer['customer_name'],
                    'phone_number': customer['phone_number'],
                    'premium_amount': policy.get('premium_amount'),
                    'fup_date': policy.get('current_fup_date'),
                })
        
        # Sort by FUP date (most recent first)
        # Handle None values and parse dates
        from datetime import datetime
        
        def parse_fup_date(policy):
            fup = policy.get('fup_date')
            if not fup:
                return datetime.min
            try:
                # Try different date formats
                for fmt in ['%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%d-%m-%y']:
                    try:
                        return datetime.strptime(fup, fmt)
                    except:
                        continue
                return datetime.min
            except:
                return datetime.min
        
        policy_list.sort(key=parse_fup_date, reverse=True)
        
        return policy_list
        
    except Exception as e:
        st.error(f"❌ Error fetching policies by address: {e}")
        return []

def is_sunday_or_holiday(check_date):
    """
    Check if a date is Sunday or an Indian national holiday
    
    Args:
        check_date (datetime.date): Date to check
    
    Returns:
        bool: True if Sunday or holiday
    """
    # Check if Sunday (weekday() returns 6 for Sunday)
    if check_date.weekday() == 6:
        return True
    
    # Indian National Holidays (2025-2026)
    # Format: (month, day)
    indian_holidays = [
        (1, 26),   # Republic Day
        (8, 15),   # Independence Day
        (10, 2),   # Gandhi Jayanti
        # Add other major holidays as needed
    ]
    
    return (check_date.month, check_date.day) in indian_holidays

def get_premium_fine_details(due_date, today_date, payment_mode, modal_premium, commencement_date=None, last_premium_paid_date=None):
    """
    Calculate the fine and policy status based on missed premium due date.
    
    For Monthly: 5% per month fine, 15 days grace period
    For Others: 0.9% per month fine (90 paise per 100 rupees), calculate each missed due separately
    
    Args:
        due_date (datetime.date): The specific due date of the missed premium (FUP date)
        today_date (datetime.date): The current date for calculation
        payment_mode (str): The policy's payment frequency ('Monthly', 'Quarterly', 'HalfYearly', 'Yearly')
        modal_premium (float): The premium amount for the specified mode
        commencement_date (datetime.date, optional): Policy commencement date for calculating future due dates
        last_premium_paid_date (datetime.date, optional): Last premium payment date to calculate pending payments
    
    Returns:
        dict: {'fine': float, 'policy_status': str, 'months_pending': int, 'next_due_dates': list, 
               'calculation_base_date': date, 'dues_breakdown': list}
    """
    
    # Step 1: Determine the calculation base date
    # Use whichever is latest: FUP date (due_date) or last premium paid date
    if last_premium_paid_date and last_premium_paid_date > due_date:
        calculation_base_date = last_premium_paid_date
    else:
        calculation_base_date = due_date
    
    # Step 2: Calculate days_late from the calculation base date
    days_late = (today_date - calculation_base_date).days
    
    # Step 3: Determine grace_period and fine calculation based on payment_mode
    if payment_mode == 'Monthly':
        grace_period = 15  # Monthly policies have 15 days grace period
        fine_rate = 0.05  # 5% per month for monthly
    else:
        # For non-monthly: grace period is 29 days
        grace_period = 29  # Quarterly, HalfYearly, Yearly have 29 days grace period
        fine_rate = 0.009  # 0.9% per month (90 paise per 100 rupees)
    
    # Step 4: Calculate all missed dues from commencement date
    missed_dues = []
    dues_breakdown = []
    
    if commencement_date and payment_mode != 'Monthly':
        # For non-monthly, calculate each missed due separately
        due_day = commencement_date.day
        current_due = calculation_base_date
        
        # Get payment interval in months
        if payment_mode == 'Quarterly':
            interval_months = 3
        elif payment_mode == 'HalfYearly':
            interval_months = 6
        else:  # Yearly
            interval_months = 12
        
        # Find all dues from calculation_base_date to today
        while current_due <= today_date:
            # Calculate grace end date for this due
            grace_end = current_due + relativedelta(days=29)
            
            # Check if this due has passed its grace period
            if today_date > grace_end:
                # Calculate months from this due date to today
                time_from_due = relativedelta(today_date, current_due)
                months_from_due = time_from_due.months + (time_from_due.years * 12)
                
                # Calculate fine for this due
                due_fine = modal_premium * fine_rate * months_from_due
                
                dues_breakdown.append({
                    'due_date': current_due,
                    'grace_end': grace_end,
                    'months_late': months_from_due,
                    'fine': due_fine,
                    'premium': modal_premium
                })
            
            # Move to next due date
            current_due = current_due + relativedelta(months=interval_months)
    
    # Step 5: Calculate pending months/payments
    months_pending = 0
    
    if last_premium_paid_date:
        # Calculate how many payment periods have passed since last payment
        time_diff = relativedelta(today_date, last_premium_paid_date)
        
        if payment_mode == 'Monthly':
            months_pending = time_diff.months + (time_diff.years * 12)
        elif payment_mode == 'Quarterly':
            months_pending = (time_diff.months + (time_diff.years * 12)) // 3
        elif payment_mode == 'HalfYearly':
            months_pending = (time_diff.months + (time_diff.years * 12)) // 6
        elif payment_mode == 'Yearly':
            months_pending = time_diff.years
    
    # Step 6: Calculate next due dates if commencement_date is provided
    next_due_dates = []
    if commencement_date:
        # Get the day of month from commencement date
        due_day = commencement_date.day
        
        # Calculate next few due dates based on payment mode
        current_date = today_date
        for i in range(3):  # Show next 3 due dates
            if payment_mode == 'Monthly':
                next_due = current_date + relativedelta(months=i+1, day=due_day)
            elif payment_mode == 'Quarterly':
                next_due = current_date + relativedelta(months=(i+1)*3, day=due_day)
            elif payment_mode == 'HalfYearly':
                next_due = current_date + relativedelta(months=(i+1)*6, day=due_day)
            else:  # Yearly
                next_due = current_date + relativedelta(years=i+1, day=due_day)
            next_due_dates.append(next_due)
    
    # Step 7: Check Policy Status and Calculate Fine
    
    # For non-monthly modes with dues breakdown: Use separate calculation
    if payment_mode != 'Monthly' and dues_breakdown:
        # Calculate total fine from all missed dues
        total_fine = sum(due['fine'] for due in dues_breakdown)
        total_premium = sum(due['premium'] for due in dues_breakdown)
        
        # Check if lapsed
        lapse_threshold = calculation_base_date + relativedelta(months=5, days=29)
        
        if today_date >= lapse_threshold:
            policy_status = 'Pakka Lapse'
        else:
            policy_status = 'Late'
        
        return {
            'fine': total_fine,
            'total_premium_due': total_premium,
            'policy_status': policy_status,
            'months_pending': len(dues_breakdown),
            'next_due_dates': next_due_dates,
            'calculation_base_date': calculation_base_date,
            'dues_breakdown': dues_breakdown
        }
    
    # For non-monthly modes: Grace period is 29 days, fine starts on 30th day
    if payment_mode != 'Monthly':
        # Grace period: 29 days (no fine until day 29)
        # Fine starts from day 30 onwards
        if days_late <= 29:
            # Still in grace period (day 0 to day 29)
            return {
                'fine': 0.0,
                'total_premium_due': modal_premium,
                'policy_status': 'In Grace',
                'months_pending': months_pending,
                'next_due_dates': next_due_dates,
                'calculation_base_date': calculation_base_date,
                'dues_breakdown': []
            }
    
    # Case 1: In Grace Period (for Monthly mode)
    # If the number of days late is within the grace period, no fine is charged
    if days_late <= grace_period:
        return {
            'fine': 0.0,
            'total_premium_due': modal_premium,
            'policy_status': 'In Grace',
            'months_pending': months_pending,
            'next_due_dates': next_due_dates,
            'calculation_base_date': calculation_base_date,
            'dues_breakdown': []
        }
    
    # Case 2: Lapsed ("Pakka Lapse")
    # Check if today_date is at least 5 months and 29 days past the calculation_base_date
    # Using relativedelta to accurately calculate the time difference
    lapse_threshold = calculation_base_date + relativedelta(months=5, days=29)
    
    # Calculate the number of months from base date for fine calculation
    time_diff = relativedelta(today_date, calculation_base_date)
    months_from_base = time_diff.months + (time_diff.years * 12)
    
    # For monthly: Use actual months from base date
    months_for_fine = months_from_base
    
    # Calculate fine based on payment mode
    fine = modal_premium * fine_rate * months_for_fine
    
    if today_date >= lapse_threshold:
        # Policy has fully lapsed, but fine is still applicable
        return {
            'fine': fine,
            'total_premium_due': modal_premium,
            'policy_status': 'Pakka Lapse',
            'months_pending': months_pending,
            'next_due_dates': next_due_dates,
            'calculation_base_date': calculation_base_date,
            'dues_breakdown': []
        }
    
    # Case 3: Late (Fine Applicable)
    return {
        'fine': fine,
        'total_premium_due': modal_premium,
        'policy_status': 'Late',
        'months_pending': months_pending,
        'next_due_dates': next_due_dates,
        'calculation_base_date': calculation_base_date,
        'dues_breakdown': []
    }

def normalize_payment_mode(payment_mode):
    """
    Normalize payment mode from database to match selectbox options
    
    Args:
        payment_mode (str): Payment mode from database
    
    Returns:
        str: Normalized payment mode ('Monthly', 'Quarterly', 'HalfYearly', 'Yearly')
    """
    if not payment_mode:
        return 'Monthly'
    
    # Convert to lowercase and remove spaces/hyphens for comparison
    mode_lower = str(payment_mode).lower().strip().replace(' ', '').replace('-', '')
    
    # Map various formats to standard format
    if mode_lower in ['monthly', 'month', 'm']:
        return 'Monthly'
    elif mode_lower in ['quarterly', 'quarter', 'q', '3months']:
        return 'Quarterly'
    elif mode_lower in ['halfyearly', 'semiannual', 'h', '6months']:
        return 'HalfYearly'
    elif mode_lower in ['yearly', 'annual', 'annually', 'year', 'y', '12months']:
        return 'Yearly'
    
    # If exact match found, return as-is
    if payment_mode in ['Monthly', 'Quarterly', 'HalfYearly', 'Yearly']:
        return payment_mode
    
    # Default to Monthly if can't match
    return 'Monthly'

def search_policies_by_number(partial_policy_number):
    """
    Search for policies matching the partial policy number
    
    Args:
        partial_policy_number (str): Partial policy number to search for
    
    Returns:
        list: List of tuples (display_text, policy_number, full_data_dict)
    """
    try:
        if not partial_policy_number or len(partial_policy_number) < 1:
            return []
        
        supabase = get_supabase_client()
        
        # Search for policies starting with the partial number
        policy_response = supabase.table('policies').select(
            'policy_number, customer_id, payment_period, premium_amount, '
            'date_of_commencement, current_fup_date'
        ).ilike('policy_number', f'{partial_policy_number}%').limit(20).execute()
        
        if not policy_response.data:
            return []
        
        # Get customer names for matching policies
        customer_ids = [p['customer_id'] for p in policy_response.data]
        customer_response = supabase.table('customers').select(
            'customer_id, customer_name'
        ).in_('customer_id', customer_ids).execute()
        
        # Create a mapping of customer_id to customer_name
        customer_map = {c['customer_id']: c['customer_name'] for c in customer_response.data}
        
        # Build results list with display format: "PolicyNumber - CustomerName"
        results = []
        for policy in policy_response.data:
            customer_name = customer_map.get(policy['customer_id'], 'Unknown')
            display_text = f"{policy['policy_number']} - {customer_name}"
            
            policy_data = {
                'policy_number': policy['policy_number'],
                'customer_name': customer_name,
                'payment_mode': normalize_payment_mode(policy.get('payment_period')),
                'premium_amount': policy.get('premium_amount'),
                'commencement_date': policy.get('date_of_commencement'),
                'fup_date': policy.get('current_fup_date')
            }
            
            results.append((display_text, policy['policy_number'], policy_data))
        
        return results
        
    except Exception as e:
        st.error(f"❌ Error searching policies: {e}")
        return []

def get_policy_details_for_calculator(policy_number):
    """
    Fetch policy details from database for premium calculator
    
    Args:
        policy_number (str): The policy number to search for
    
    Returns:
        dict: Policy details or None if not found
    """
    try:
        supabase = get_supabase_client()
        
        # Get policy details
        policy_response = supabase.table('policies').select(
            'policy_number, customer_id, payment_period, premium_amount, '
            'date_of_commencement, current_fup_date'
        ).eq('policy_number', policy_number).execute()
        
        if not policy_response.data:
            return None
        
        policy = policy_response.data[0]
        
        # Get customer details to potentially get last payment info
        customer_response = supabase.table('customers').select(
            'customer_name'
        ).eq('customer_id', policy['customer_id']).execute()
        
        customer_name = customer_response.data[0]['customer_name'] if customer_response.data else 'Unknown'
        
        return {
            'policy_number': policy['policy_number'],
            'customer_name': customer_name,
            'payment_mode': normalize_payment_mode(policy.get('payment_period')),
            'premium_amount': policy.get('premium_amount'),
            'commencement_date': policy.get('date_of_commencement'),
            'fup_date': policy.get('current_fup_date')
        }
        
    except Exception as e:
        st.error(f"❌ Error fetching policy details: {e}")
        return None

def display_customer_card(customer, card_index=0):
    """Display a customer card with collapsible details"""
    # Color palette for distinguishing customer cards
    colors = [
        '#E8F4FD',  # Light blue
        '#FFF4E6',  # Light orange
        '#E8F8F5',  # Light green
        '#F4E8FD',  # Light purple
        '#FDE8F4',  # Light pink
        '#FFFACD',  # Light yellow
        '#E0F2F1',  # Light teal
        '#FFF0F5',  # Light lavender
    ]
    
    # Get color for this card (cycle through colors)
    card_color = colors[card_index % len(colors)]
    
    # Determine customer name styling
    is_generic = customer['customer_name'].startswith('Customer_')
    nickname = customer.get('nickname', '')
    has_duplicates = customer.get('potential_duplicates', [])
    policy_count = len(customer.get('policies', []))
    
    # Create customer name display with emoji and policy count
    if nickname:
        display_name = f"👤 {customer['customer_name']} - 🏷️ {nickname} ({policy_count} policies)"
    else:
        display_name = f"👤 {customer['customer_name']} ({policy_count} policies)"
    
    # Add warning indicators
    if has_duplicates:
        display_name = "🔄 " + display_name + " ⚠️ Duplicates"
    elif is_generic:
        display_name = "⚠️ " + display_name + " (Generic)"
    
    # Add custom CSS for this specific expander
    st.markdown(f"""
        <style>
        div[data-testid="stExpander"]:nth-of-type({card_index + 1}) {{
            background: linear-gradient(145deg, {card_color}, #ffffff);
            border-radius: 12px;
            padding: 0.5rem;
            margin-bottom: 1rem;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
        }}
        </style>
    """, unsafe_allow_html=True)
    
    # Main expandable customer section
    with st.expander(display_name, expanded=False):
        # Edit button at the top
        col1, col2, col3 = st.columns([3, 1, 1])
        with col2:
            edit_key = f"edit_{customer['customer_id']}"
            if st.button("✏️ Edit Customer", key=edit_key, type="secondary", use_container_width=True):
                st.session_state.edit_customer_id = customer['customer_id']
                st.rerun()
        
        with col3:
            add_policy_key = f"add_policy_btn_{customer['customer_id']}"
            if st.button("➕ Add Policy", key=add_policy_key, type="primary", use_container_width=True):
                st.session_state.add_policy_customer_id = customer['customer_id']
                st.session_state.add_policy_customer_name = customer['customer_name']
                st.rerun()
        
        st.markdown("---")
        
        # Show potential duplicates if any
        if customer.get('potential_duplicates'):
            with st.expander("🔄 Potential Duplicate Customers", expanded=False):
                for dup in customer['potential_duplicates']:
                    other_customer = (dup['customer2'] if dup['customer1']['customer_id'] == customer['customer_id'] 
                                    else dup['customer1'])
                    match_reasons = ", ".join(dup['match_reasons'])
                    
                    st.info(f"**{other_customer['customer_name']}** (ID: {other_customer['customer_id']}) - "
                           f"Match reasons: {match_reasons}")
                    
                    # Show basic details for comparison
                    st.write(f"📞 Phone: {other_customer.get('phone_number', 'N/A')} | "
                           f"🆔 Aadhaar: {other_customer.get('aadhaar_number', 'N/A')} | "
                           f"🎂 DOB: {other_customer.get('date_of_birth', 'N/A')}")
                    st.markdown("---")
        
        # Customer details in compact 3D highlighted sections
        st.markdown("""
            <div style='background: linear-gradient(145deg, #ffffff, #f8f9fa); 
                        padding: 1rem; border-radius: 12px; margin-bottom: 0.8rem;
                        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.8);'>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown(f"<p style='margin: 0; padding: 2px 0; line-height: 1.4;'>🏷️ <strong>Nickname:</strong> {customer.get('nickname') or 'N/A'}</p>", unsafe_allow_html=True)
            st.markdown(f"<p style='margin: 0; padding: 2px 0; line-height: 1.4;'>📞 <strong>Phone:</strong> {customer.get('phone_number') or 'N/A'}</p>", unsafe_allow_html=True)
            st.markdown(f"<p style='margin: 0; padding: 2px 0; line-height: 1.4;'>📧 <strong>Email:</strong> {customer.get('email') or 'N/A'}</p>", unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"<p style='margin: 0; padding: 2px 0; line-height: 1.4;'>💼 <strong>Occupation:</strong> {customer.get('occupation') or 'N/A'}</p>", unsafe_allow_html=True)
            st.markdown(f"<p style='margin: 0; padding: 2px 0; line-height: 1.4;'>🆔 <strong>Aadhaar:</strong> {customer.get('aadhaar_number') or 'N/A'}</p>", unsafe_allow_html=True)
            st.markdown(f"<p style='margin: 0; padding: 2px 0; line-height: 1.4;'>🎂 <strong>DOB:</strong> {customer.get('date_of_birth') or 'N/A'}</p>", unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"<p style='margin: 0; padding: 2px 0; line-height: 1.4;'>📞 <strong>Alt Phone:</strong> {customer.get('alt_phone_number') or 'N/A'}</p>", unsafe_allow_html=True)
            st.markdown(f"<p style='margin: 0; padding: 2px 0; line-height: 1.4;'>🏠 <strong>Address:</strong> {customer.get('full_address') or 'N/A'}</p>", unsafe_allow_html=True)
            st.markdown(f"<p style='margin: 0; padding: 2px 0; line-height: 1.4;'>🔄 <strong>Updated:</strong> {customer.get('last_updated') or 'N/A'}</p>", unsafe_allow_html=True)
            
        st.markdown("</div>", unsafe_allow_html=True)
        
        # Address and location in separate 3D section
        if customer.get('full_address') or customer.get('google_maps_link'):
            st.markdown("""
                <div style='background: linear-gradient(145deg, #ffffff, #f8f9fa); 
                            padding: 1rem; border-radius: 12px; margin-bottom: 0.8rem;
                            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.8);'>
            """, unsafe_allow_html=True)
            
            if customer.get('full_address'):
                st.markdown(f"🏠 **Address:** {customer.get('full_address')}")
            
            if customer.get('google_maps_link'):
                st.markdown(f"[📍 Open in Google Maps]({customer.get('google_maps_link')})")
            
            st.markdown("</div>", unsafe_allow_html=True)
        
        # Notes (if any)
        if customer.get('notes'):
            st.markdown("""
                <div style='background: linear-gradient(145deg, #fffef0, #faf9e8); 
                            padding: 1rem; border-radius: 12px; margin-bottom: 0.8rem;
                            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.8);'>
            """, unsafe_allow_html=True)
            st.markdown(f"📝 **Notes:** {customer.get('notes')}")
            st.markdown("</div>", unsafe_allow_html=True)
        
        # Enhanced Policies section with nested expandable - each policy is collapsible
        if customer['policies']:
            st.markdown("---")
            st.markdown(f"### 📋 Policies ({len(customer['policies'])})")
            
            for i, policy in enumerate(customer['policies']):
                    # Policy header with edit button
                    header_col, edit_col = st.columns([4, 1])
                    
                    with header_col:
                        st.subheader(f"Policy #{i+1}: {policy['policy_number']}")
                    
                    # Define keys consistently
                    edit_button_key = f"btn_edit_policy_{policy['policy_number']}"
                    edit_mode_key = f"mode_edit_policy_{policy['policy_number']}"
                    
                    with edit_col:
                        if st.button("✏️ Edit Policy", key=edit_button_key, type="secondary"):
                            st.session_state[edit_mode_key] = True
                            st.rerun()
                    
                    # Check if we're in edit mode for this policy
                    if st.session_state.get(edit_mode_key, False):
                        display_policy_edit_form(policy)
                    else:
                        # Display mode - Policy information in compact 3D sections
                        
                        # Basic Information Section (3D highlight)
                        st.markdown("""
                            <div style='background: linear-gradient(145deg, #e8f4fd, #d6ebf5); 
                                        padding: 0.8rem; border-radius: 10px; margin-bottom: 0.6rem;
                                        box-shadow: 0 3px 10px rgba(102, 126, 234, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.6);'>
                        """, unsafe_allow_html=True)
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown(f"📝 **Plan Name:** {policy.get('plan_name', 'N/A')}")
                            st.markdown(f"🏢 **Agent Code:** {policy.get('agent_code', 'N/A')}")
                        with col2:
                            payment_period = policy.get('payment_period', 'N/A')
                            st.markdown(f"📆 **Payment Term:** {payment_period}")
                        
                        st.markdown("</div>", unsafe_allow_html=True)
                        
                        # Dates Section (3D highlight)
                        st.markdown("""
                            <div style='background: linear-gradient(145deg, #fef5e7, #fdebd0); 
                                        padding: 0.8rem; border-radius: 10px; margin-bottom: 0.6rem;
                                        box-shadow: 0 3px 10px rgba(243, 156, 18, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.6);'>
                        """, unsafe_allow_html=True)
                        
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            commencement = policy.get('date_of_commencement', 'N/A')
                            if commencement and commencement != 'N/A' and str(commencement).strip():
                                st.markdown(f"<p style='margin: 0; padding: 2px 0; line-height: 1.4;'>🗓️ <strong>Commencement:</strong> {commencement}</p>", unsafe_allow_html=True)
                            else:
                                st.markdown("<p style='margin: 0; padding: 2px 0; line-height: 1.4;'>🗓️ <strong>Commencement:</strong> 📄 <em>Premium Due only</em></p>", unsafe_allow_html=True)
                        
                        with col2:
                            fup_date = policy.get('current_fup_date', 'N/A')
                            if fup_date and fup_date != 'N/A' and str(fup_date).strip():
                                st.markdown(f"<p style='margin: 0; padding: 2px 0; line-height: 1.4;'>📅 <strong>FUP (Next Due):</strong> {fup_date}</p>", unsafe_allow_html=True)
                            else:
                                if policy.get('latest_premium') and policy['latest_premium'].get('due_date'):
                                    due_date = policy['latest_premium']['due_date']
                                    st.markdown(f"<p style='margin: 0; padding: 2px 0; line-height: 1.4;'>📅 <strong>Latest Due:</strong> {due_date}</p>", unsafe_allow_html=True)
                                else:
                                    st.markdown("<p style='margin: 0; padding: 2px 0; line-height: 1.4;'>📅 <strong>FUP:</strong> 💳 <em>Premium Due only</em></p>", unsafe_allow_html=True)
                        
                        with col3:
                            last_payment = policy.get('last_payment_date', 'N/A')
                            if last_payment and last_payment != 'N/A' and str(last_payment).strip():
                                st.markdown(f"<p style='margin: 0; padding: 2px 0; line-height: 1.4;'>💳 <strong>Last Payment:</strong> {last_payment}</p>", unsafe_allow_html=True)
                            else:
                                st.markdown("<p style='margin: 0; padding: 2px 0; line-height: 1.4;'>💳 <strong>Last Payment:</strong> Not recorded</p>", unsafe_allow_html=True)
                        
                        st.markdown("</div>", unsafe_allow_html=True)
                        
                        # Financial Information Section (3D highlight)
                        st.markdown("""
                            <div style='background: linear-gradient(145deg, #e8f8f5, #d0f0e8); 
                                        padding: 0.8rem; border-radius: 10px; margin-bottom: 0.6rem;
                                        box-shadow: 0 3px 10px rgba(46, 204, 113, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.6);'>
                        """, unsafe_allow_html=True)
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            premium_amount = policy.get('premium_amount')
                            if premium_amount:
                                st.markdown(f"<p style='margin: 0; padding: 2px 0; line-height: 1.4;'>💰 <strong>Premium Amount:</strong> ₹{premium_amount:,.2f}</p>", unsafe_allow_html=True)
                            else:
                                st.markdown("<p style='margin: 0; padding: 2px 0; line-height: 1.4;'>💰 <strong>Premium Amount:</strong> Not Available</p>", unsafe_allow_html=True)
                            
                            sum_assured = policy.get('sum_assured')
                            if sum_assured:
                                st.markdown(f"<p style='margin: 0; padding: 2px 0; line-height: 1.4;'>🏦 <strong>Sum Assured:</strong> ₹{sum_assured:,.2f}</p>", unsafe_allow_html=True)
                            else:
                                st.markdown("<p style='margin: 0; padding: 2px 0; line-height: 1.4;'>🏦 <strong>Sum Assured:</strong> Not Available</p>", unsafe_allow_html=True)
                        
                        with col2:
                            # Show due count prominently if available
                            if policy.get('latest_premium') and policy['latest_premium'].get('due_count'):
                                due_count = policy['latest_premium']['due_count']
                                if due_count > 1:
                                    st.warning(f"⚠️ **{due_count} Premiums Due**")
                                else:
                                    st.info(f"ℹ️ **{due_count} Premium Due**")
                        
                        st.markdown("</div>", unsafe_allow_html=True)
                        
                    if i < len(customer['policies']) - 1:
                        st.markdown("---")
        else:
            st.info("No policies found for this customer")

def display_policy_edit_form(policy):
    """Display policy edit form"""
    with st.form(f"edit_policy_form_{policy['policy_number']}"):
        st.markdown("**✏️ Edit Policy Information**")
        
        # Basic Information
        st.markdown("**Basic Information**")
        col1, col2 = st.columns(2)
        
        with col1:
            plan_name = st.text_input("Plan Name", value=policy.get('plan_name', '') or '')
            agent_code = st.text_input("Agent Code", value=policy.get('agent_code', '') or '')
            payment_term = st.selectbox("Payment Term", 
                                      options=['Yearly', 'Half-Yearly', 'Quarterly', 'Monthly', 'One-time'], 
                                      index=0 if not policy.get('payment_period') 
                                      else (['Yearly', 'Half-Yearly', 'Quarterly', 'Monthly', 'One-time'].index(policy.get('payment_period')) 
                                           if policy.get('payment_period') in ['Yearly', 'Half-Yearly', 'Quarterly', 'Monthly', 'One-time'] else 0))
        
        with col2:
            pass  # Empty column for now
        
        # Dates
        st.markdown("**Dates**")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            commencement_date = st.date_input("Date of Commencement", 
                                            value=None if not policy.get('date_of_commencement') 
                                            else pd.to_datetime(policy.get('date_of_commencement')).date() 
                                            if policy.get('date_of_commencement') != 'N/A' else None)
        
        with col2:
            fup_date = st.date_input("Current FUP Date", 
                                   value=None if not policy.get('current_fup_date') 
                                   else pd.to_datetime(policy.get('current_fup_date')).date() 
                                   if policy.get('current_fup_date') != 'N/A' else None)
        
        with col3:
            maturity_date = st.date_input("Maturity Date", 
                                        value=None if not policy.get('maturity_date') 
                                        else pd.to_datetime(policy.get('maturity_date')).date() 
                                        if policy.get('maturity_date') != 'N/A' else None)
        
        # Payment Information
        st.markdown("**Payment Information**")
        last_payment_date = st.date_input("Last Payment Date", 
                                        value=None if not policy.get('last_payment_date') 
                                        else pd.to_datetime(policy.get('last_payment_date')).date() 
                                        if policy.get('last_payment_date') != 'N/A' else None,
                                        help="Manually update the last payment date when premium is paid")
        
        # Financial Information
        st.markdown("**Financial Information**")
        col1, col2 = st.columns(2)
        
        with col1:
            premium_amount = st.number_input("Premium Amount (₹)", 
                                           value=float(policy.get('premium_amount', 0)) if policy.get('premium_amount') else 0.0,
                                           min_value=0.0, step=100.0)
            policy_term = st.number_input("Policy Term (Years)", 
                                        value=int(policy.get('policy_term', 0)) if policy.get('policy_term') else 0,
                                        min_value=0, step=1)
        
        with col2:
            sum_assured = st.number_input("Sum Assured (₹)", 
                                        value=float(policy.get('sum_assured', 0)) if policy.get('sum_assured') else 0.0,
                                        min_value=0.0, step=1000.0)
        
        # Form buttons
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            submit_button = st.form_submit_button("💾 Update Policy", type="primary")
        
        with col2:
            cancel_button = st.form_submit_button("❌ Cancel")
        
        if submit_button:
            updates = {
                'plan_name': plan_name,
                'agent_code': agent_code,
                'payment_period': payment_term,
                'date_of_commencement': commencement_date.strftime('%Y-%m-%d') if commencement_date else None,
                'current_fup_date': fup_date.strftime('%Y-%m-%d') if fup_date else None,
                'maturity_date': maturity_date.strftime('%Y-%m-%d') if maturity_date else None,
                'last_payment_date': last_payment_date.strftime('%Y-%m-%d') if last_payment_date else None,
                'premium_amount': premium_amount if premium_amount > 0 else None,
                'sum_assured': sum_assured if sum_assured > 0 else None,
                'policy_term': policy_term if policy_term > 0 else None
            }
            
            success, message = update_policy_details(policy['policy_number'], updates)
            
            if success:
                st.success(f"✅ {message}")
                st.session_state[f"mode_edit_policy_{policy['policy_number']}"] = False
                st.session_state.show_results = True
                st.rerun()
            else:
                st.error(f"❌ {message}")
        
        if cancel_button:
            st.session_state[f"mode_edit_policy_{policy['policy_number']}"] = False
            st.rerun()

def update_customer_details(customer_id, updates):
    """Update customer details in the database"""
    supabase = get_database_connection()
    if not supabase:
        return False, "Database connection failed"
    
    try:
        # Build the update data
        update_data = {}
        
        for field, value in updates.items():
            if field in ['nickname', 'phone_number', 'alt_phone_number', 'email', 'aadhaar_number', 
                        'date_of_birth', 'occupation', 'full_address', 'google_maps_link', 'notes']:
                update_data[field] = value if (value and str(value).strip()) else None
        
        if not update_data:
            return False, "No valid fields to update"
        
        # Add last_updated timestamp
        update_data['last_updated'] = datetime.now().isoformat()
        
        # Update in Supabase
        response = supabase.table('customers').update(update_data).eq('customer_id', customer_id).execute()
        
        if response.data:
            return True, "Customer details updated successfully"
        else:
            return False, "Customer not found"
            
    except Exception as e:
        return False, f"Error updating customer: {str(e)}"

def update_policy_details(policy_number, updates):
    """Update policy details in the database"""
    supabase = get_database_connection()
    if not supabase:
        return False, "Database connection failed"
    
    try:
        # Build the update data
        update_data = {}
        
        for field, value in updates.items():
            if field in ['agent_code', 'plan_name', 
                        'date_of_commencement', 'payment_period', 'current_fup_date', 
                        'sum_assured', 'premium_amount', 'status', 'maturity_date', 
                        'policy_term', 'last_payment_date']:
                if field in ['sum_assured', 'premium_amount', 'policy_term']:
                    # Handle numeric fields
                    try:
                        update_data[field] = float(value) if value and str(value).strip() else None
                    except (ValueError, TypeError):
                        update_data[field] = None
                else:
                    update_data[field] = value if value and str(value).strip() else None
        
        if not update_data:
            return False, "No valid fields to update"
        
        # Add last_updated timestamp
        update_data['last_updated'] = datetime.now().isoformat()
        
        # Update in Supabase
        response = supabase.table('policies').update(update_data).eq('policy_number', policy_number).execute()
        
        if response.data:
            return True, "Policy details updated successfully"
        else:
            return False, "Policy not found"
            
    except Exception as e:
        return False, f"Error updating policy: {str(e)}"

def get_customer_by_id(customer_id):
    """Get customer details by ID"""
    supabase = get_database_connection()
    if not supabase:
        return None
    
    try:
        response = supabase.table('customers').select(
            '*, policies(*)'
        ).eq('customer_id', customer_id).execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
        
    except Exception as e:
        st.error(f"Error fetching customer: {e}")
        return None

def add_new_customer(customer_data):
    """Add a new customer to the database"""
    supabase = get_database_connection()
    if not supabase:
        return False, "Database connection failed"
    
    try:
        # Check for potential duplicates
        existing_customers = check_existing_customer(
            customer_data.get('customer_name', ''),
            customer_data.get('phone_number', ''),
            customer_data.get('aadhaar_number', '')
        )
        
        if existing_customers:
            return False, f"Potential duplicate found: {', '.join([c['customer_name'] for c in existing_customers])}"
        
        # Prepare insert data
        insert_data = {
            'customer_name': customer_data.get('customer_name'),
            'phone_number': customer_data.get('phone_number'),
            'alt_phone_number': customer_data.get('alt_phone_number'),
            'email': customer_data.get('email'),
            'aadhaar_number': customer_data.get('aadhaar_number'),
            'date_of_birth': customer_data.get('date_of_birth'),
            'occupation': customer_data.get('occupation'),
            'full_address': customer_data.get('full_address'),
            'google_maps_link': customer_data.get('google_maps_link'),
            'notes': customer_data.get('notes'),
            'nickname': customer_data.get('nickname'),
            'extraction_method': 'manual',
            'created_date': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat()
        }
        
        response = supabase.table('customers').insert(insert_data).execute()
        
        if response.data:
            customer_id = response.data[0]['customer_id']
            return True, f"Customer added successfully with ID: {customer_id}"
        else:
            return False, "Failed to add customer"
        
    except Exception as e:
        return False, f"Error adding customer: {str(e)}"

def add_new_policy(policy_data, customer_id, document_date=None):
    """Add a new policy to the database with date update logic"""
    supabase = get_database_connection()
    if not supabase:
        return False, "Database connection failed"
    
    try:
        # Check if policy already exists
        existing_response = supabase.table('policies').select('*').eq(
            'policy_number', policy_data.get('policy_number')
        ).execute()
        
        existing_policy = existing_response.data[0] if existing_response.data else None
        
        current_date = document_date or pd.Timestamp.now().strftime('%Y-%m-%d')
        
        if existing_policy:
            # Policy exists - check if we should update with newer information
            existing_date = existing_policy.get('last_updated') or existing_policy.get('created_date') or '1900-01-01'
            
            if current_date > existing_date:
                # Update with newer information
                update_data = {}
                
                for field, value in policy_data.items():
                    if field != 'policy_number' and value:
                        update_data[field] = value
                
                if update_data:
                    update_data['last_updated'] = current_date
                    
                    response = supabase.table('policies').update(update_data).eq(
                        'policy_number', policy_data['policy_number']
                    ).execute()
                    
                    if response.data:
                        return True, f"Policy {policy_data['policy_number']} updated with newer information"
                    else:
                        return False, "Failed to update policy"
                else:
                    return False, "No new information to update"
            else:
                return False, f"Policy {policy_data['policy_number']} already exists with newer or equal date"
        else:
            # New policy - insert
            insert_data = {
                'policy_number': policy_data.get('policy_number'),
                'customer_id': customer_id,
                'agent_code': policy_data.get('agent_code'),
                'plan_name': policy_data.get('plan_name'),
                'date_of_commencement': policy_data.get('date_of_commencement'),
                'payment_period': policy_data.get('payment_period'),
                'current_fup_date': policy_data.get('current_fup_date'),
                'sum_assured': policy_data.get('sum_assured'),
                'premium_amount': policy_data.get('premium_amount'),
                'status': policy_data.get('status', 'Active'),
                'maturity_date': policy_data.get('maturity_date'),
                'policy_term': policy_data.get('policy_term'),
                'last_payment_date': policy_data.get('last_payment_date'),
                'extraction_method': 'manual',
                'created_date': current_date,
                'last_updated': current_date
            }
            
            response = supabase.table('policies').insert(insert_data).execute()
            
            if response.data:
                return True, f"Policy {policy_data['policy_number']} added successfully"
            else:
                return False, "Failed to add policy"
            
    except Exception as e:
        return False, f"Error adding/updating policy: {str(e)}"

def check_existing_customer(name, phone=None, aadhaar=None):
    """Check for existing customers with similar details"""
    supabase = get_database_connection()
    if not supabase:
        return []
    
    try:
        # Build query conditions
        query = supabase.table('customers').select('*')
        
        # Search by name
        query = query.ilike('customer_name', f'%{name}%')
        
        response = query.execute()
        results = response.data if response.data else []
        
        # Also check by phone if provided
        if phone:
            phone_response = supabase.table('customers').select('*').eq('phone_number', phone).execute()
            if phone_response.data:
                results.extend(phone_response.data)
        
        # Also check by aadhaar if provided
        if aadhaar:
            aadhaar_response = supabase.table('customers').select('*').eq('aadhaar_number', aadhaar).execute()
            if aadhaar_response.data:
                results.extend(aadhaar_response.data)
        
        # Remove duplicates based on customer_id
        seen_ids = set()
        unique_results = []
        for customer in results:
            if customer['customer_id'] not in seen_ids:
                seen_ids.add(customer['customer_id'])
                unique_results.append(customer)
        
        return unique_results
        
    except Exception as e:
        st.error(f"Error checking existing customers: {e}")
        return []

def show_customer_edit_form(customer_data):
    """Show form to edit customer details"""
    st.markdown("### ✏️ Edit Customer Details")
    
    # Show customer identification
    st.info(f"**Editing:** 👤 {customer_data['customer_name']} (ID: {customer_data['customer_id']})")
    
    # Show policy numbers for this customer
    if customer_data.get('policies'):
        policy_numbers = [policy['policy_number'] for policy in customer_data['policies']]
        st.info(f"**Policy Numbers:** 📋 {', '.join(policy_numbers)}")
    
    with st.form("customer_edit_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Basic Information**")
            nickname = st.text_input("🏷️ Nickname", value=customer_data.get('nickname', '') or '')
            phone = st.text_input("Phone Number", value=customer_data.get('phone_number', '') or '')
            alt_phone = st.text_input("Alternative Phone", value=customer_data.get('alt_phone_number', '') or '')
            email = st.text_input("Email", value=customer_data.get('email', '') or '')
            aadhaar = st.text_input("Aadhaar Number", value=customer_data.get('aadhaar_number', '') or '')
            
        with col2:
            st.markdown("**Personal Information**")
            dob = st.text_input("Date of Birth", value=customer_data.get('date_of_birth', '') or '')
            occupation = st.text_input("Occupation", value=customer_data.get('occupation', '') or '')
            address = st.text_area("Full Address", value=customer_data.get('full_address', '') or '', height=100)
            
        st.markdown("**Location & Additional Information**")
        col_location, col_notes = st.columns([1, 1])
        
        with col_location:
            google_maps_link = st.text_input(
                "🗺️ Google Maps Location", 
                value=customer_data.get('google_maps_link', '') or '',
                help="Paste Google Maps URL or coordinates here"
            )
            
        with col_notes:
            notes = st.text_area("📝 Notes", value=customer_data.get('notes', '') or '', height=80)
        
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            submit_button = st.form_submit_button("💾 Update Details", type="primary")
        
        with col2:
            cancel_button = st.form_submit_button("❌ Cancel")
        
        if submit_button:
            updates = {
                'nickname': nickname,
                'phone_number': phone,
                'alt_phone_number': alt_phone,
                'email': email,
                'aadhaar_number': aadhaar,
                'date_of_birth': dob,
                'occupation': occupation,
                'full_address': address,
                'google_maps_link': google_maps_link,
                'notes': notes
            }
            
            success, message = update_customer_details(customer_data['customer_id'], updates)
            
            if success:
                st.success(f"✅ {message}")
                st.session_state.edit_customer_id = None
                st.session_state.show_results = True
                st.rerun()
            else:
                st.error(f"❌ {message}")
        
        if cancel_button:
            st.session_state.edit_customer_id = None
            st.rerun()

def show_database_stats():
    """Show database statistics"""
    supabase = get_database_connection()
    if not supabase:
        st.warning("Cannot show stats - database not available")
        return
    
    try:
        # Get total counts
        customer_response = supabase.table('customers').select('customer_id', count='exact').execute()
        total_customers = customer_response.count if customer_response.count is not None else 0
        
        policy_response = supabase.table('policies').select('policy_number', count='exact').execute()
        total_policies = policy_response.count if policy_response.count is not None else 0
        
        # Get agent-wise stats
        # Get all policies with agent codes
        policies_response = supabase.table('policies').select('agent_code, customer_id').execute()
        policies_data = policies_response.data if policies_response.data else []
        
        # Count by agent
        agent_customers = {}
        agent_policies = {}
        
        for policy in policies_data:
            agent_code = policy.get('agent_code', 'Unknown')
            if not agent_code:
                agent_code = 'Unknown'
            
            # Count policies
            if agent_code not in agent_policies:
                agent_policies[agent_code] = 0
            agent_policies[agent_code] += 1
            
            # Count unique customers
            customer_id = policy.get('customer_id')
            if customer_id:
                if agent_code not in agent_customers:
                    agent_customers[agent_code] = set()
                agent_customers[agent_code].add(customer_id)
        
        # Convert sets to counts
        for agent_code in agent_customers:
            agent_customers[agent_code] = len(agent_customers[agent_code])
        
        # Display compact overview
        st.markdown("### 📊 Overview")
        
        st.markdown(f"""
        <div style='background-color: #f0f2f6; padding: 0.5rem; border-radius: 0.3rem; margin-bottom: 0.5rem;'>
            <p style='margin: 0; font-size: 0.85rem; color: #31333F;'>
                <strong>📊 Total:</strong> {total_customers} customers • {total_policies} policies
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        # Display agent-wise stats in compact format
        all_agents = sorted(set(list(agent_customers.keys()) + list(agent_policies.keys())))
        
        if all_agents:
            agent_stats = []
            for agent_code in all_agents:
                customers_count = agent_customers.get(agent_code, 0)
                policies_count = agent_policies.get(agent_code, 0)
                agent_stats.append(f"{agent_code}: {customers_count}c • {policies_count}p")
            
            agent_text = " | ".join(agent_stats)
            
            st.markdown(f"""
            <div style='background-color: #f0f2f6; padding: 0.5rem; border-radius: 0.3rem;'>
                <p style='margin: 0; font-size: 0.8rem; color: #31333F;'>
                    <strong>👥 By Agent:</strong> {agent_text}
                </p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("No agent data available yet.")
        
    except Exception as e:
        st.error(f"Error getting database stats: {e}")

def show_setup_instructions():
    """Show setup instructions if database doesn't exist"""
    st.error("❌ Database Connection Failed")
    
    st.markdown("### 🔧 Setup Required")
    st.markdown("""
    Cannot connect to Supabase. Please follow these steps:
    
    1. **Create a Supabase project:**
       - Go to [supabase.com](https://supabase.com)
       - Create a new project
       - Note your project URL and anon key
    
    2. **Configure secrets:**
       - Create `.streamlit/secrets.toml` file
       - Add your Supabase credentials:
       ```toml
       [supabase]
       url = "https://your-project.supabase.co"
       key = "your-anon-key"
       ```
    
    3. **Create database tables:**
       - Run the SQL schema in your Supabase SQL editor
       - Tables needed: customers, policies, premium_records, agents, documents
    
    4. **Refresh this page** after setup is complete
    """)
    
    # Add a button to check again
    if st.button("🔄 Check Connection Again"):
        st.rerun()

def show_manual_entry_forms():
    """Show forms for manually adding customers and policies"""
    tab1, tab2 = st.tabs(["👤 Add Customer", "➕ Add Policy to Existing Customer"])
    
    with tab1:
        st.markdown("### 👤 Add New Customer")
        
        with st.form("add_customer_form"):
            st.markdown("**Basic Information**")
            col1, col2 = st.columns(2)
            
            with col1:
                customer_name = st.text_input("Customer Name*", placeholder="Full name")
                phone_number = st.text_input("Phone Number", 
                                            placeholder="+91XXXXXXXXXX", 
                                            help="Format: +91 followed by 10 digits")
                email = st.text_input("Email", 
                                    placeholder="email@example.com",
                                    help="Valid email address")
                aadhaar_number = st.text_input("Aadhaar Number", 
                                             placeholder="12-digit number",
                                             help="Exactly 12 digits")
            
            with col2:
                nickname = st.text_input("Nickname", placeholder="Short name")
                alt_phone_number = st.text_input("Alternate Phone", 
                                                placeholder="+91XXXXXXXXXX",
                                                help="Format: +91 followed by 10 digits")
                date_of_birth = st.date_input("Date of Birth", 
                                            value=None,
                                            help="Select your date of birth")
                occupation = st.text_input("Occupation", placeholder="Job/profession")
            
            st.markdown("**Address & Location**")
            full_address = st.text_area("Full Address", placeholder="Complete address")
            google_maps_link = st.text_input("Google Maps Link", placeholder="Maps URL")
            
            notes = st.text_area("Notes", placeholder="Any additional information")
            
            col1, col2 = st.columns([1, 3])
            with col1:
                submit_customer = st.form_submit_button("👤 Add Customer", type="primary")
            
            if submit_customer:
                # Validation
                errors = []
                
                if not customer_name:
                    errors.append("Customer name is required!")
                
                # Validate email
                email_valid, email_msg = validate_email(email)
                if not email_valid:
                    errors.append(email_msg)
                
                # Validate phone number
                phone_valid, phone_cleaned = validate_phone_number(phone_number)
                if not phone_valid:
                    errors.append(phone_cleaned)  # phone_cleaned contains error message when invalid
                
                # Validate alternate phone
                alt_phone_valid, alt_phone_cleaned = validate_phone_number(alt_phone_number)
                if not alt_phone_valid:
                    errors.append(f"Alternate phone: {alt_phone_cleaned}")
                
                # Validate Aadhaar
                aadhaar_valid, aadhaar_cleaned = validate_aadhaar(aadhaar_number)
                if not aadhaar_valid:
                    errors.append(aadhaar_cleaned)
                
                # Validate date of birth
                dob_valid, dob_formatted = validate_date_of_birth(date_of_birth)
                if not dob_valid:
                    errors.append(dob_formatted)  # contains error message when invalid
                
                if errors:
                    for error in errors:
                        st.error(f"❌ {error}")
                else:
                    customer_data = {
                        'customer_name': customer_name,
                        'phone_number': phone_cleaned if phone_valid and phone_cleaned else None,
                        'alt_phone_number': alt_phone_cleaned if alt_phone_valid and alt_phone_cleaned else None,
                        'email': email or None,
                        'aadhaar_number': aadhaar_cleaned if aadhaar_valid and aadhaar_cleaned else None,
                        'date_of_birth': dob_formatted if dob_valid and dob_formatted else None,
                        'occupation': occupation or None,
                        'full_address': full_address or None,
                        'google_maps_link': google_maps_link or None,
                        'notes': notes or None,
                        'nickname': nickname or None
                    }
                    
                    success, message = add_new_customer(customer_data)
                    
                    if success:
                        st.success(f"✅ {message}")
                        st.session_state.show_results = True
                        st.rerun()
                    else:
                        st.error(f"❌ {message}")
    
    with tab2:
        st.markdown("### ➕ Add Policy to Existing Customer")
        
        # Customer selection with enhanced search
        st.markdown("**Step 1: Find & Select Customer**")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            customer_search_existing = st.text_input("Search customer", 
                                                   placeholder="Name, phone, or policy number",
                                                   key="search_existing_customer")
        with col2:
            search_existing_btn = st.button("🔍 Search", key="search_existing")
        
        selected_existing_customer_id = None
        
        if customer_search_existing and search_existing_btn:
            supabase = get_database_connection()
            if supabase:
                try:
                    # Search for customers with policies
                    response = supabase.table('customers').select(
                        'customer_id, customer_name, phone_number, nickname, policies(policy_number)'
                    ).or_(
                        f'customer_name.ilike.%{customer_search_existing}%,'
                        f'phone_number.ilike.%{customer_search_existing}%,'
                        f'nickname.ilike.%{customer_search_existing}%'
                    ).limit(15).execute()
                    
                    found_customers_existing = response.data if response.data else []
                    
                    if found_customers_existing:
                        st.markdown("**Found Customers:**")
                        for customer in found_customers_existing:
                            with st.container():
                                col1, col2, col3 = st.columns([3, 1, 1])
                                with col1:
                                    nickname_text = f" ({customer['nickname']})" if customer.get('nickname') else ""
                                    phone_text = f" - {customer['phone_number']}" if customer.get('phone_number') else ""
                                    policy_count = len(customer.get('policies', []))
                                    policy_count_text = f" [{policy_count} policies]"
                                    st.write(f"**{customer['customer_name']}**{nickname_text}{phone_text}{policy_count_text}")
                                
                                with col2:
                                    if st.button("Select", key=f"select_existing_{customer['customer_id']}"):
                                        st.session_state.selected_existing_customer_id = customer['customer_id']
                                        st.session_state.selected_existing_customer_name = customer['customer_name']
                                        st.rerun()
                                
                                with col3:
                                    if st.button("👁️ View", key=f"view_existing_{customer['customer_id']}"):
                                        st.session_state.view_customer_id = customer['customer_id']
                                
                                st.markdown("---")
                    else:
                        st.warning("No customers found matching your search.")
                        
                except Exception as e:
                    st.error(f"Error searching customers: {e}")
        
        # Use session state for selected customer
        if 'selected_existing_customer_id' in st.session_state:
            selected_existing_customer_id = st.session_state.selected_existing_customer_id
            customer_name = st.session_state.get('selected_existing_customer_name', 'Unknown')
            
            st.success(f"Selected Customer: **{customer_name}**")
            
            # Show existing policies for this customer
            supabase = get_database_connection()
            if supabase:
                try:
                    response = supabase.table('policies').select(
                        'policy_number, plan_name, status, premium_amount'
                    ).eq('customer_id', selected_existing_customer_id).order('policy_number').execute()
                    
                    existing_policies = response.data if response.data else []
                    
                    if existing_policies:
                        st.markdown("**Existing Policies:**")
                        for policy in existing_policies:
                            premium_amount = policy.get('premium_amount')
                            premium_text = f"₹{premium_amount:,.2f}" if premium_amount else "N/A"
                            plan_name = policy.get('plan_name') or 'N/A'
                            status = policy.get('status') or 'Active'
                            st.write(f"• **{policy['policy_number']}** - {plan_name} - {status} - {premium_text}")
                    else:
                        st.info("No existing policies found for this customer.")
                    
                except Exception as e:
                    st.error(f"Error fetching existing policies: {e}")
            
            st.markdown("**Step 2: Add New Policy**")
            
            with st.form("add_policy_to_existing_form"):
                col1, col2 = st.columns(2)
                
                with col1:
                    new_policy_number = st.text_input("Policy Number*", placeholder="New policy number")
                    new_plan_name = st.text_input("Plan Name", placeholder="e.g., 075-20, 814-15")
                    new_agent_code = st.text_input("Agent Code", placeholder="Agent code")
                    new_payment_term = st.selectbox("Payment Term", 
                                                  options=['', 'Yearly', 'Half-Yearly', 'Quarterly', 'Monthly', 'One-time'])
                    new_premium_amount = st.number_input("Premium Amount (₹)", min_value=0.0, value=0.0)
                
                with col2:
                    new_sum_assured = st.number_input("Sum Assured (₹)", min_value=0.0, value=0.0)
                    new_policy_term = st.number_input("Policy Term (Years)", min_value=0, value=0)
                
                st.markdown("**Dates**")
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    new_date_of_commencement = st.date_input("Date of Commencement", key="new_comm_date")
                with col2:
                    new_current_fup_date = st.date_input("Current FUP Date", key="new_fup_date")
                with col3:
                    new_maturity_date = st.date_input("Maturity Date", key="new_maturity_date")
                
                st.markdown("**Payment Information**")
                new_last_payment_date_existing = st.date_input("Last Payment Date", 
                                                             value=None,
                                                             key="new_last_payment_date_existing",
                                                             help="Date of the last premium payment (optional)")
                
                new_document_date = st.date_input("Document Date", 
                                                value=pd.Timestamp.now().date(),
                                                key="new_doc_date",
                                                help="Date of the document containing this information")
                
                col1, col2, col3 = st.columns([1, 1, 2])
                with col1:
                    submit_new_policy = st.form_submit_button("📋 Add Policy", type="primary")
                with col2:
                    clear_selection = st.form_submit_button("🔄 Clear Selection")
                
                if clear_selection:
                    if 'selected_existing_customer_id' in st.session_state:
                        del st.session_state.selected_existing_customer_id
                    if 'selected_existing_customer_name' in st.session_state:
                        del st.session_state.selected_existing_customer_name
                    st.rerun()
                
                if submit_new_policy:
                    if not new_policy_number:
                        st.error("Policy number is required!")
                    else:
                        new_policy_data = {
                            'policy_number': new_policy_number,
                            'plan_name': new_plan_name or None,
                            'agent_code': new_agent_code or None,
                            'payment_period': new_payment_term if new_payment_term else None,
                            'status': 'Active',
                            'date_of_commencement': new_date_of_commencement.strftime('%Y-%m-%d') if new_date_of_commencement else None,
                            'current_fup_date': new_current_fup_date.strftime('%Y-%m-%d') if new_current_fup_date else None,
                            'maturity_date': new_maturity_date.strftime('%Y-%m-%d') if new_maturity_date else None,
                            'last_payment_date': new_last_payment_date_existing.strftime('%Y-%m-%d') if new_last_payment_date_existing else None,
                            'premium_amount': new_premium_amount if new_premium_amount > 0 else None,
                            'sum_assured': new_sum_assured if new_sum_assured > 0 else None,
                            'policy_term': new_policy_term if new_policy_term > 0 else None
                        }
                        
                        success, message = add_new_policy(
                            new_policy_data, 
                            selected_existing_customer_id, 
                            new_document_date.strftime('%Y-%m-%d')
                        )
                        
                        if success:
                            st.success(f"✅ {message}")
                            # Clear selection
                            if 'selected_existing_customer_id' in st.session_state:
                                del st.session_state.selected_existing_customer_id
                            if 'selected_existing_customer_name' in st.session_state:
                                del st.session_state.selected_existing_customer_name
                            st.session_state.show_results = True
                            st.rerun()
                        else:
                            st.error(f"❌ {message}")
        else:
            st.info("👆 Search and select a customer above to add a new policy")

def show_add_policy_form(customer_id, customer_name):
    """Show form to add a new policy to an existing customer"""
    
    st.info(f"👤 **Customer:** {customer_name} (ID: {customer_id})")
    
    # Back button
    col1, col2, col3 = st.columns([1, 1, 3])
    with col1:
        if st.button("⬅️ Back to Search", key="back_to_search"):
            st.session_state.add_policy_customer_id = None
            st.session_state.add_policy_customer_name = None
            st.rerun()
    
    st.markdown("---")
    
    with st.form("add_policy_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            new_policy_number = st.text_input("Policy Number*", placeholder="New policy number")
            new_plan_name = st.text_input("Plan Name", placeholder="e.g., 075-20, 814-15")
            new_agent_code = st.text_input("Agent Code", placeholder="Agent code")
            new_payment_term = st.selectbox("Payment Term", 
                                          options=['', 'Yearly', 'Half-Yearly', 'Quarterly', 'Monthly', 'One-time'])
            new_premium_amount = st.number_input("Premium Amount (₹)", min_value=0.0, value=0.0)
        
        with col2:
            new_sum_assured = st.number_input("Sum Assured (₹)", min_value=0.0, value=0.0)
            new_policy_term = st.number_input("Policy Term (Years)", min_value=0, value=0)
        
        st.markdown("**Dates**")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            new_date_of_commencement = st.date_input("Date of Commencement", key="add_policy_comm_date")
        with col2:
            new_current_fup_date = st.date_input("Current FUP Date", key="add_policy_fup_date")
        with col3:
            new_maturity_date = st.date_input("Maturity Date", key="add_policy_maturity_date")
        
        st.markdown("**Payment Information**")
        new_last_payment_date = st.date_input("Last Payment Date", 
                                             value=None,
                                             key="add_policy_last_payment_date",
                                             help="Date of the last premium payment (optional)")
        
        new_document_date = st.date_input("Document Date", 
                                        value=pd.Timestamp.now().date(),
                                        key="add_policy_doc_date",
                                        help="Date of the document containing this information")
        
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            submit_new_policy = st.form_submit_button("📋 Add Policy", type="primary")
        with col2:
            cancel_add_policy = st.form_submit_button("❌ Cancel")
        
        if cancel_add_policy:
            st.session_state.add_policy_customer_id = None
            st.session_state.add_policy_customer_name = None
            st.rerun()
        
        if submit_new_policy:
            if not new_policy_number:
                st.error("Policy number is required!")
            else:
                new_policy_data = {
                    'policy_number': new_policy_number,
                    'plan_name': new_plan_name or None,
                    'agent_code': new_agent_code or None,
                    'payment_period': new_payment_term if new_payment_term else None,
                    'status': 'Active',
                    'date_of_commencement': new_date_of_commencement.strftime('%Y-%m-%d') if new_date_of_commencement else None,
                    'current_fup_date': new_current_fup_date.strftime('%Y-%m-%d') if new_current_fup_date else None,
                    'maturity_date': new_maturity_date.strftime('%Y-%m-%d') if new_maturity_date else None,
                    'last_payment_date': new_last_payment_date.strftime('%Y-%m-%d') if new_last_payment_date else None,
                    'premium_amount': new_premium_amount if new_premium_amount > 0 else None,
                    'sum_assured': new_sum_assured if new_sum_assured > 0 else None,
                    'policy_term': new_policy_term if new_policy_term > 0 else None
                }
                
                success, message = add_new_policy(
                    new_policy_data, 
                    customer_id, 
                    new_document_date.strftime('%Y-%m-%d')
                )
                
                if success:
                    st.success(f"✅ {message}")
                    # Clear the add policy state after successful addition
                    st.session_state.add_policy_customer_id = None
                    st.session_state.add_policy_customer_name = None
                    st.rerun()
                else:
                    st.error(f"❌ {message}")

def main():
    """Main Streamlit app"""
    st.set_page_config(
        page_title="AM's LIC Database",
        page_icon="🏢",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Add mobile-friendly custom CSS with 3D effects
    st.markdown("""
        <style>
        /* Mobile responsive adjustments */
        @media (max-width: 768px) {
            .main .block-container {
                padding-left: 0.5rem;
                padding-right: 0.5rem;
                max-width: 100%;
            }
            
            /* Make metrics stack on mobile */
            [data-testid="stMetric"] {
                margin-bottom: 0.5rem;
            }
            
            /* Reduce font sizes for mobile */
            h1 {
                font-size: 1.5rem !important;
            }
            h2 {
                font-size: 1.2rem !important;
            }
            h3 {
                font-size: 1rem !important;
            }
            
            /* Full width buttons on mobile */
            .stButton button {
                width: 100%;
                padding: 0.75rem 1rem;
            }
        }
        
        /* 3D Card styling with shadows and depth */
        .stContainer {
            background: linear-gradient(145deg, #ffffff, #f0f0f0);
            padding: 1.5rem;
            border-radius: 15px;
            margin-bottom: 1rem;
            box-shadow: 
                0 10px 30px rgba(0, 0, 0, 0.1),
                0 1px 8px rgba(0, 0, 0, 0.05),
                inset 0 1px 0 rgba(255, 255, 255, 0.8);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        
        .stContainer:hover {
            transform: translateY(-5px);
            box-shadow: 
                0 15px 40px rgba(0, 0, 0, 0.15),
                0 5px 15px rgba(0, 0, 0, 0.1);
        }
        
        /* 3D Button styling */
        .stButton button {
            border-radius: 12px;
            font-weight: 600;
            padding: 0.6rem 1.5rem;
            transition: all 0.3s ease;
            box-shadow: 
                0 4px 15px rgba(102, 126, 234, 0.3),
                0 2px 5px rgba(0, 0, 0, 0.1);
            background: linear-gradient(145deg, #667eea, #764ba2);
            border: none;
        }
        
        .stButton button:hover {
            transform: translateY(-2px);
            box-shadow: 
                0 6px 20px rgba(102, 126, 234, 0.4),
                0 3px 10px rgba(0, 0, 0, 0.15);
        }
        
        .stButton button:active {
            transform: translateY(0px);
            box-shadow: 
                0 2px 10px rgba(102, 126, 234, 0.3);
        }
        
        /* 3D Input fields */
        .stTextInput input, .stTextArea textarea {
            border-radius: 10px;
            border: 2px solid #e0e0e0;
            box-shadow: 
                inset 0 2px 5px rgba(0, 0, 0, 0.05);
            transition: all 0.3s ease;
        }
        
        .stTextInput input:focus, .stTextArea textarea:focus {
            border-color: #667eea;
            box-shadow: 
                0 0 0 3px rgba(102, 126, 234, 0.1),
                inset 0 2px 5px rgba(0, 0, 0, 0.05);
        }
        
        /* 3D Expander */
        .streamlit-expanderHeader {
            border-radius: 10px;
            background: linear-gradient(145deg, #f8f9fa, #e9ecef);
            box-shadow: 
                0 2px 8px rgba(0, 0, 0, 0.1);
            transition: all 0.3s ease;
        }
        
        .streamlit-expanderHeader:hover {
            box-shadow: 
                0 4px 12px rgba(0, 0, 0, 0.15);
            transform: translateY(-1px);
        }
        
        /* Remove default margins for app-like feel */
        .main {
            background: linear-gradient(to bottom, #f8f9fa 0%, #ffffff 100%);
        }
        
        /* Improve spacing */
        .element-container {
            margin-bottom: 0.5rem;
        }
        
        /* 3D effect for metrics */
        [data-testid="stMetric"] {
            background: linear-gradient(145deg, #ffffff, #f0f0f0);
            padding: 1rem;
            border-radius: 12px;
            box-shadow: 
                0 4px 12px rgba(0, 0, 0, 0.08),
                inset 0 1px 0 rgba(255, 255, 255, 0.8);
        }
        
        /* Smooth scrolling */
        html {
            scroll-behavior: smooth;
        }
        
        /* Hide Streamlit branding for app-like feel */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        </style>
    """, unsafe_allow_html=True)
    
    # Header with custom styling and 3D effect
    st.markdown("""
        <div style='text-align: center; padding: 1.5rem 0 1rem 0; 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    border-radius: 15px; 
                    margin-bottom: 1.5rem;
                    box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4),
                                0 5px 15px rgba(0, 0, 0, 0.1);'>
            <h1 style='color: white; margin: 0; font-size: 2.5rem; font-weight: 700; 
                       text-shadow: 3px 3px 6px rgba(0,0,0,0.3);
                       letter-spacing: 1px;'>
                🏢 AM's LIC Database
            </h1>
            <p style='color: #f0f0f0; margin: 0.5rem 0 0 0; font-size: 1rem;
                      text-shadow: 1px 1px 3px rgba(0,0,0,0.2);'>
                Manage customers and policies efficiently
            </p>
        </div>
    """, unsafe_allow_html=True)
    
    # Sidebar with project info
    with st.sidebar:
        st.markdown("### 📁 Project Info")
        
        db_exists, db_info = check_database_exists()
        st.write(f"**Database:** {'✅ Connected' if db_exists else '❌ Disconnected'}")
        
        if db_exists:
            st.success("✅ Supabase Connected!")
            st.info(f"Using: {db_info}")
            
            # Agent Statistics
            st.markdown("---")
            st.markdown("### 📊 Agent Statistics")
            
            try:
                supabase = get_supabase_client()
                
                # Get all policies with agent codes
                policies_response = supabase.table('policies').select('agent_code, customer_id').execute()
                policies_data = policies_response.data
                
                if policies_data:
                    # Count customers per agent code
                    agent_stats = {}
                    for policy in policies_data:
                        agent_code = policy.get('agent_code', 'Unknown')
                        if not agent_code or agent_code.strip() == '':
                            agent_code = 'No Agent Code'
                        
                        if agent_code not in agent_stats:
                            agent_stats[agent_code] = set()
                        agent_stats[agent_code].add(policy['customer_id'])
                    
                    # Convert to sorted list with counts
                    agent_list = []
                    for agent_code, customer_ids in agent_stats.items():
                        agent_list.append({
                            'agent_code': agent_code,
                            'customer_count': len(customer_ids)
                        })
                    
                    # Sort by customer count descending
                    agent_list.sort(key=lambda x: x['customer_count'], reverse=True)
                    
                    # Display stats
                    total_agents = len(agent_list)
                    total_customers = len(set(policy['customer_id'] for policy in policies_data))
                    
                    st.metric("Total Agents", total_agents)
                    st.metric("Total Customers", total_customers)
                    
                    with st.expander(f"📋 View Customer Count by Agent ({total_agents} agents)"):
                        for agent in agent_list:
                            st.text(f"🔹 {agent['agent_code']}: {agent['customer_count']} customer(s)")
                else:
                    st.info("No policies found")
                    
            except Exception as e:
                st.error(f"Error loading agent stats: {e}")
            
            # Cleanup utility
            st.markdown("---")
            st.markdown("### 🧹 Admin Tools")
            
            # Initialize session state for cleanup
            if 'customers_to_delete' not in st.session_state:
                st.session_state.customers_to_delete = None
            
            if st.button("🗑️ Clean Empty Customers", help="Delete customers without any policies"):
                with st.spinner("Checking for customers without policies..."):
                    try:
                        supabase = get_supabase_client()
                        
                        # Get all customers
                        customers_response = supabase.table('customers').select('customer_id, customer_name').execute()
                        all_customers = customers_response.data
                        
                        # Get all customer IDs that have policies
                        policies_response = supabase.table('policies').select('customer_id').execute()
                        customer_ids_with_policies = set(policy['customer_id'] for policy in policies_response.data)
                        
                        # Find customers without policies
                        customers_without_policies = [
                            customer for customer in all_customers 
                            if customer['customer_id'] not in customer_ids_with_policies
                        ]
                        
                        if not customers_without_policies:
                            st.success("✅ No empty customers found. Database is clean!")
                            st.session_state.customers_to_delete = None
                        else:
                            st.session_state.customers_to_delete = customers_without_policies
                    
                    except Exception as e:
                        st.error(f"❌ Error: {e}")
                        st.session_state.customers_to_delete = None
            
            # Show confirmation UI if there are customers to delete
            if st.session_state.customers_to_delete:
                customers_to_delete = st.session_state.customers_to_delete
                st.warning(f"⚠️ Found {len(customers_to_delete)} customers without policies")
                
                with st.expander(f"View {len(customers_to_delete)} customers to delete"):
                    for customer in customers_to_delete:
                        st.text(f"• {customer['customer_name']} (ID: {customer['customer_id']})")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"✅ Confirm Delete {len(customers_to_delete)} Customers", type="primary", use_container_width=True):
                        supabase = get_supabase_client()
                        deleted_count = 0
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        for idx, customer in enumerate(customers_to_delete):
                            try:
                                supabase.table('customers').delete().eq('customer_id', customer['customer_id']).execute()
                                deleted_count += 1
                                status_text.text(f"Deleting: {customer['customer_name']}")
                                progress_bar.progress((idx + 1) / len(customers_to_delete))
                            except Exception as e:
                                st.error(f"Failed to delete {customer['customer_name']}: {e}")
                        
                        progress_bar.empty()
                        status_text.empty()
                        st.success(f"✅ Successfully deleted {deleted_count} customers!")
                        st.session_state.customers_to_delete = None
                        st.rerun()
                
                with col2:
                    if st.button("❌ Cancel", use_container_width=True):
                        st.session_state.customers_to_delete = None
                        st.rerun()
        else:
            st.error("❌ Connection Failed")
            st.code(str(db_info))
    
    # Main content
    db_exists, _ = check_database_exists()
    
    if not db_exists:
        show_setup_instructions()
        st.stop()
    
    # Create tabs
    tab1, tab2, tab3 = st.tabs(["🔍 Search Customers", "📍 Filter by Location", "🧮 Premium Calculator"])
    
    # TAB 1: Search Customers
    with tab1:
        # Search section with search button
        col1, col2 = st.columns([4, 1])
        
        with col1:
            search_query = st.text_input(
                "🔍 Search by name, phone, address, Aadhaar, policy number, agent code, or premium amount",
                placeholder="Type customer name, phone, address, policy number, premium amount...",
                label_visibility="visible"
            )
        
        with col2:
            st.markdown("<div style='margin-top: 1.85rem;'></div>", unsafe_allow_html=True)
            search_button = st.button("🔍 Search", type="primary", use_container_width=True)
        
        # Add Customer button below search bar
        st.markdown("---")
        add_new_customer_btn = st.button("➕ Add New Customer", type="primary", use_container_width=True)
        st.markdown("---")
        
        # Show Add Customer form if button clicked
        if 'show_add_customer_form' not in st.session_state:
            st.session_state.show_add_customer_form = False
        
        if add_new_customer_btn:
            st.session_state.show_add_customer_form = not st.session_state.show_add_customer_form
        
        if st.session_state.show_add_customer_form:
            with st.expander("➕ Add New Customer & Policy", expanded=True):
                show_manual_entry_forms()
            st.markdown("---")
        
        # Initialize session state for search and editing
        if 'show_results' not in st.session_state:
            st.session_state.show_results = False
        if 'edit_customer_id' not in st.session_state:
            st.session_state.edit_customer_id = None
        if 'add_policy_customer_id' not in st.session_state:
            st.session_state.add_policy_customer_id = None
        if 'add_policy_customer_name' not in st.session_state:
            st.session_state.add_policy_customer_name = None
        if 'search_query' not in st.session_state:
            st.session_state.search_query = ""
        
        # Check if we're in edit mode
        if st.session_state.edit_customer_id:
            st.markdown("---")
            customer_data = get_customer_by_id(st.session_state.edit_customer_id)
            if customer_data:
                show_customer_edit_form(customer_data)
            else:
                st.error("Customer not found!")
                st.session_state.edit_customer_id = None
            st.stop()
        
        # Check if we're in add policy mode
        if st.session_state.add_policy_customer_id:
            st.markdown("---")
            st.header(f"➕ Add New Policy for {st.session_state.add_policy_customer_name}")
            
            customer_data = get_customer_by_id(st.session_state.add_policy_customer_id)
            if customer_data:
                # Show policy addition form
                show_add_policy_form(st.session_state.add_policy_customer_id, st.session_state.add_policy_customer_name)
            else:
                st.error("Customer not found!")
                st.session_state.add_policy_customer_id = None
                st.session_state.add_policy_customer_name = None
            st.stop()
        
        # Perform search - on search button
        if search_button:
            query = search_query
            st.session_state.show_results = True
            st.session_state.search_query = query
            
            with st.spinner("🔍 Searching database..."):
                customers, total_policies = search_customers(query)
            
            if customers:
                st.success(f"📊 Found **{len(customers)}** customers with **{total_policies}** policies")
                
                # Display customers
                for i, customer in enumerate(customers):
                    display_customer_card(customer, card_index=i)
                    
                    # Add pagination for large results
                    if i > 0 and (i + 1) % 10 == 0 and i + 1 < len(customers):
                        if not st.button(f"Show more... ({len(customers) - i - 1} remaining)", key=f"more_{i}"):
                            break
            else:
                if query:
                    st.warning(f"🔍 No customers found matching: **{query}**")
                else:
                    st.info("📋 No customers in database yet. Process some PDFs first!")
        
        # Also show results if we have them in session state
        elif st.session_state.get('show_results', False) and 'search_query' in st.session_state:
            query = st.session_state.search_query
            
            with st.spinner("🔍 Loading results..."):
                customers, total_policies = search_customers(query)
            
            if customers:
                st.success(f"📊 Found **{len(customers)}** customers with **{total_policies}** policies")
                
                # Display customers
                for i, customer in enumerate(customers):
                    display_customer_card(customer, card_index=i)
                    
                    # Add pagination for large results
                    if i > 0 and (i + 1) % 10 == 0 and i + 1 < len(customers):
                        if not st.button(f"Show more... ({len(customers) - i - 1} remaining)", key=f"more_{i}"):
                            break
            else:
                if query:
                    st.warning(f"🔍 No customers found matching: **{query}**")
                else:
                    st.info("📋 No customers in database yet. Process some PDFs first!")
    
    # TAB 2: Filter by Location
    with tab2:
        st.markdown("### 📍 View Policies by Location")
        st.markdown("Select an address to view all policies for customers at that location")
        st.markdown("---")
        
        # Get all addresses for dropdown
        addresses = get_all_addresses()
        
        if addresses:
            selected_address = st.selectbox(
                "Select Location",
                options=["-- Select an Address --"] + addresses,
                key="address_filter_tab"
            )
            
            # Display policies by selected address in table format
            if selected_address and selected_address != "-- Select an Address --":
                with st.spinner("🔍 Loading policies for this location..."):
                    policies = get_policies_by_address(selected_address)
                
                if policies:
                    st.success(f"📊 Found **{len(policies)}** policies at **{selected_address}**")
                    
                    # Create DataFrame for table display
                    import pandas as pd
                    
                    table_data = []
                    for policy in policies:
                        table_data.append({
                            'Policy Number': policy['policy_number'],
                            'Customer Name': policy['customer_name'],
                            'Phone Number': policy['phone_number'] or 'N/A',
                            'Premium Amount': f"₹{policy['premium_amount']:,.0f}" if policy['premium_amount'] else 'N/A',
                        })
                    
                    df = pd.DataFrame(table_data)
                    
                    # Display the table
                    st.dataframe(
                        df,
                        use_container_width=True,
                        hide_index=True,
                        height=400
                    )
                else:
                    st.info(f"ℹ️ No policies found for address: {selected_address}")
        else:
            st.warning("⚠️ No addresses found in the database")
    
    # TAB 3: Premium Calculator
    with tab3:
        st.markdown("### 🧮 Premium Fine Calculator")
        st.markdown("Calculate fine and policy status for missed premium payments")
        st.markdown("---")
        
        # Optional: Policy Number Lookup with Autocomplete
        st.markdown("#### 🔍 Quick Lookup (Optional)")
        
        # Initialize session state for policy lookup
        if 'fetched_policy_data' not in st.session_state:
            st.session_state.fetched_policy_data = None
        if 'policy_search_text' not in st.session_state:
            st.session_state.policy_search_text = ""
        if 'selected_policy_number' not in st.session_state:
            st.session_state.selected_policy_number = ""
        
        # Create two columns for search input and display
        search_col1, search_col2 = st.columns([3, 1])
        
        with search_col1:
            # Text input for typing policy number
            search_input = st.text_input(
                "Type Policy Number (Optional)",
                placeholder="Start typing policy number to search...",
                help="Type to search for policies - matching customer names will appear below. Select from dropdown to auto-fill calculator fields.",
                key="policy_search_input"
            )
        
        # Search for matching policies when user types
        matching_policies = []
        if search_input and len(search_input) >= 1:
            matching_policies = search_policies_by_number(search_input)
        
        # Show dropdown with matching policies if found
        if matching_policies and len(matching_policies) > 0:
            with search_col1:
                # Create dropdown options: ["Select...", "policy1 - name1", "policy2 - name2", ...]
                dropdown_options = ["Select a policy..."] + [match[0] for match in matching_policies]
                
                selected_dropdown = st.selectbox(
                    f"Found {len(matching_policies)} matching policies:",
                    options=dropdown_options,
                    key="policy_dropdown",
                    label_visibility="visible"
                )
                
                # If user selected a policy from dropdown
                if selected_dropdown != "Select a policy...":
                    # Find the selected policy data
                    for match in matching_policies:
                        if match[0] == selected_dropdown:
                            # Extract policy number and data
                            _, policy_number, policy_data = match
                            
                            # Update session state with selected policy
                            st.session_state.selected_policy_number = policy_number
                            st.session_state.fetched_policy_data = policy_data
                            
                            # Show success message
                            st.success(f"✅ Selected policy **{policy_number}** for **{policy_data['customer_name']}** - Details auto-filled below")
                            break
        
        # Show clear button if a policy is selected
        if st.session_state.selected_policy_number:
            with search_col2:
                st.markdown("<div style='margin-top: 1.85rem;'></div>", unsafe_allow_html=True)
                if st.button("🗑️ Clear", type="secondary", use_container_width=True):
                    st.session_state.selected_policy_number = ""
                    st.session_state.fetched_policy_data = None
                    st.rerun()
        
        st.markdown("---")
        
        # Parse dates from fetched data if available
        fetched_data = st.session_state.fetched_policy_data
        
        # Default values - use fetched data if available
        from datetime import datetime
        
        default_fup_date = date.today() - relativedelta(months=2)
        default_commencement = date.today() - relativedelta(years=2)
        default_payment_mode = 'Monthly'
        default_premium = 5000.0
        
        if fetched_data:
            # Parse FUP date
            if fetched_data.get('fup_date'):
                try:
                    fup_str = fetched_data['fup_date']
                    for fmt in ['%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y']:
                        try:
                            default_fup_date = datetime.strptime(fup_str, fmt).date()
                            break
                        except:
                            continue
                except:
                    pass
            
            # Parse commencement date
            if fetched_data.get('commencement_date'):
                try:
                    comm_str = fetched_data['commencement_date']
                    for fmt in ['%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y']:
                        try:
                            default_commencement = datetime.strptime(comm_str, fmt).date()
                            break
                        except:
                            continue
                except:
                    pass
            
            # Set payment mode and premium
            if fetched_data.get('payment_mode'):
                default_payment_mode = fetched_data['payment_mode']
            if fetched_data.get('premium_amount'):
                default_premium = float(fetched_data['premium_amount'])
        
        # Create two columns for input
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### � Date Information")
            
            # Due Date input
            due_date_input = st.date_input(
                "Premium Due Date (FUP) *",
                value=default_fup_date,
                help="Select the original due date of the premium (auto-filled from database if policy found)"
            )
            
            # Today's Date input
            today_date_input = st.date_input(
                "Today's Date *",
                value=date.today(),
                help="Select the current date for calculation"
            )
            
            # Optional: Commencement Date
            st.markdown("---")
            st.markdown("**Optional Fields**")
            
            use_commencement = st.checkbox(
                "Include Commencement Date",
                value=fetched_data is not None and fetched_data.get('commencement_date') is not None,
                help="Use this to calculate future due dates based on policy start"
            )
            
            commencement_date_input = None
            if use_commencement:
                commencement_date_input = st.date_input(
                    "Policy Commencement Date",
                    value=default_commencement,
                    help="The day from this date will be used for calculating future due dates (auto-filled from database if policy found)"
                )
        
        with col2:
            st.markdown("#### 💰 Premium Information")
            
            # Payment Mode selection
            payment_mode = st.selectbox(
                "Payment Mode *",
                options=['Monthly', 'Quarterly', 'HalfYearly', 'Yearly'],
                index=['Monthly', 'Quarterly', 'HalfYearly', 'Yearly'].index(default_payment_mode) if default_payment_mode in ['Monthly', 'Quarterly', 'HalfYearly', 'Yearly'] else 0,
                help="Select the payment frequency of the policy (auto-filled from database if policy found)"
            )
            
            # Modal Premium input
            modal_premium = st.number_input(
                "Modal Premium Amount (₹) *",
                min_value=0.0,
                value=default_premium,
                step=100.0,
                help="Enter the premium amount for the selected payment mode (auto-filled from database if policy found)"
            )
            
            # Optional: Last Premium Paid Date
            st.markdown("---")
            st.markdown("**Optional Fields**")
            
            use_last_paid = st.checkbox(
                "Include Last Premium Paid Date",
                help="Use this to calculate pending payments/months"
            )
            
            last_premium_paid_input = None
            if use_last_paid:
                last_premium_paid_input = st.date_input(
                    "Last Premium Paid Date",
                    value=date.today() - relativedelta(months=6),
                    help="Date when the last premium was paid"
                )
        
        st.markdown("---")
        
        # Calculate button
        if st.button("🧮 Calculate Fine & Status", type="primary", use_container_width=True):
            # Validate that today's date is not before due date
            if today_date_input < due_date_input:
                st.error("❌ Today's date cannot be before the due date!")
            else:
                # Calculate using the function
                result = get_premium_fine_details(
                    due_date=due_date_input,
                    today_date=today_date_input,
                    payment_mode=payment_mode,
                    modal_premium=modal_premium,
                    commencement_date=commencement_date_input,
                    last_premium_paid_date=last_premium_paid_input
                )
                
                # Display results with proper styling
                st.markdown("---")
                
                # Add custom CSS for better visibility
                st.markdown("""
                    <style>
                    div[data-testid="stMetricValue"] {
                        color: #1f1f1f !important;
                        font-weight: 600 !important;
                    }
                    div[data-testid="stMetricLabel"] {
                        color: #4f4f4f !important;
                    }
                    </style>
                """, unsafe_allow_html=True)
                
                st.markdown("### 📊 Calculation Results")
                
                # Show which date was used for calculation
                calculation_base = result['calculation_base_date']
                if last_premium_paid_input and last_premium_paid_input > due_date_input:
                    st.info(f"📌 **Calculation based on:** Last Premium Paid Date ({calculation_base.strftime('%d-%m-%Y')}) - as it's more recent than FUP Date")
                else:
                    st.info(f"📌 **Calculation based on:** FUP Date ({calculation_base.strftime('%d-%m-%Y')})")
                
                # Calculate additional details for display
                days_from_base = (today_date_input - calculation_base).days
                grace_period = 15 if payment_mode == 'Monthly' else 29
                
                # Calculate days since lapse threshold (5 months 29 days) for all statuses
                lapse_threshold_date = calculation_base + relativedelta(months=5, days=29)
                days_since_lapse_threshold = (today_date_input - lapse_threshold_date).days
                
                # Create unified result display columns showing both day metrics
                res_col1, res_col2, res_col3, res_col4, res_col5 = st.columns(5)
                
                with res_col1:
                    st.metric(
                        label="Policy Status",
                        value=result['policy_status']
                    )
                
                with res_col2:
                    st.metric(
                        label="Days from Base Date",
                        value=f"{days_from_base} days",
                        help=f"Total days since {calculation_base.strftime('%d-%m-%Y')}"
                    )
                
                with res_col3:
                    if days_since_lapse_threshold >= 0:
                        st.metric(
                            label="Days Since Lapse Threshold",
                            value=f"{days_since_lapse_threshold} days",
                            help="Days since crossing 5 months 29 days (Pakka Lapse threshold)"
                        )
                    else:
                        st.metric(
                            label="Days to Lapse Threshold",
                            value=f"{abs(days_since_lapse_threshold)} days",
                            help="Days remaining before 5 months 29 days (Pakka Lapse threshold)"
                        )
                
                with res_col4:
                    st.metric(
                        label="Fine Amount",
                        value=f"₹{result['fine']:,.2f}"
                    )
                
                with res_col5:
                    if result['months_pending'] > 0:
                        st.metric(
                            label="Pending Payments",
                            value=f"{result['months_pending']}"
                        )
                
                # Show next due dates if commencement date was provided
                if result['next_due_dates']:
                    st.markdown("---")
                    st.markdown("#### 📅 Upcoming Due Dates")
                    due_dates_col1, due_dates_col2, due_dates_col3 = st.columns(3)
                    
                    for idx, next_due in enumerate(result['next_due_dates']):
                        with [due_dates_col1, due_dates_col2, due_dates_col3][idx]:
                            st.info(f"**Next {idx+1}:** {next_due.strftime('%d-%m-%Y')}")
                
                # Status-based messaging
                st.markdown("---")
                
                if result['policy_status'] == 'In Grace':
                    st.success(f"""
                    ✅ **Policy is in Grace Period**
                    
                    - Grace period for {payment_mode} mode: **{grace_period} days**
                    - Days from base date: **{days_from_base} days**
                    - No fine applicable
                    - Premium can still be paid without penalty
                    """)
                    
                    if result['months_pending'] > 0:
                        st.info(f"📌 **Note:** {result['months_pending']} payment(s) pending since last premium paid date")
                
                elif result['policy_status'] == 'Pakka Lapse':
                    lapse_date = calculation_base + relativedelta(months=5, days=29)
                    time_diff = relativedelta(today_date_input, calculation_base)
                    months_late = time_diff.months + (time_diff.years * 12)
                    
                    # Calculate days from the base calculation date (FUP or last premium paid)
                    days_from_base = (today_date_input - calculation_base).days
                    # Calculate days since the lapse threshold (5 months 29 days)
                    days_since_lapse = (today_date_input - lapse_date).days
                    
                    # Check if we have dues breakdown (for non-monthly with multiple missed dues)
                    if result.get('dues_breakdown') and len(result['dues_breakdown']) > 0:
                        # Show detailed breakdown for each missed due
                        total_premium = result.get('total_premium_due', modal_premium)
                        total_fine = result['fine']
                        
                        st.error(f"""
                        ❌ **Policy has Lapsed (Pakka Lapse)**
                        
                        - Policy lapsed on: **{lapse_date.strftime('%d-%m-%Y')}** (5 months 29 days from base date)
                        - Days since lapse threshold: **{days_since_lapse} days**
                        - Days from base date ({calculation_base.strftime('%d-%m-%Y')}): **{days_from_base} days**
                        - Number of missed dues: **{len(result['dues_breakdown'])} due(s)**
                        - Total amount for revival: **₹{(total_premium + total_fine):,.2f}**
                        """)
                        
                        # Show detailed breakdown table for each due
                        import pandas as pd
                        
                        st.markdown("#### 📋 Detailed Breakdown by Due Date")
                        
                        # Custom CSS for scrollable table with no text wrapping
                        st.markdown("""
                        <style>
                        .scrollable-table {
                            overflow-x: auto;
                            -webkit-overflow-scrolling: touch;
                        }
                        .scrollable-table table {
                            width: 100%;
                            white-space: nowrap;
                            font-size: 14px;
                        }
                        .scrollable-table th, .scrollable-table td {
                            padding: 8px 12px;
                            text-align: left;
                            white-space: nowrap;
                        }
                        </style>
                        """, unsafe_allow_html=True)
                        
                        breakdown_data = []
                        for idx, due in enumerate(result['dues_breakdown'], 1):
                            breakdown_data.append({
                                'Due #': f"Due {idx}",
                                'Due Date': due['due_date'].strftime('%d-%m-%Y'),
                                'Grace End': due['grace_end'].strftime('%d-%m-%Y'),
                                'Months Late': due['months_late'],
                                'Premium': f"₹{due['premium']:,.2f}",
                                'Fine (0.9%/month)': f"₹{due['fine']:,.2f}",
                                'Subtotal': f"₹{(due['premium'] + due['fine']):,.2f}"
                            })
                        
                        breakdown_df = pd.DataFrame(breakdown_data)
                        
                        # Display table in a scrollable container
                        st.markdown('<div class="scrollable-table">', unsafe_allow_html=True)
                        st.table(breakdown_df)
                        st.markdown('</div>', unsafe_allow_html=True)
                        
                        # Show total summary
                        st.markdown("#### 💳 Revival Payment Summary")
                        summary_df = pd.DataFrame({
                            'Component': ['Total Premium (All Dues)', 'Total Fine', 'Grand Total for Revival'],
                            'Amount': [
                                f"₹{total_premium:,.2f}",
                                f"₹{total_fine:,.2f}",
                                f"₹{(total_premium + total_fine):,.2f}"
                            ]
                        })
                        st.table(summary_df)
                    
                    else:
                        # Single due calculation (or monthly mode)
                        # Fine formula varies by payment mode
                        if payment_mode == 'Monthly':
                            fine_formula = f"₹{modal_premium:,.2f} × 5% × {months_late} months"
                        else:
                            # For non-monthly, show grace end date and actual months from base
                            grace_end_date = calculation_base + relativedelta(days=29)
                            fine_formula = f"₹{modal_premium:,.2f} × 0.9% × {months_late} months (Grace ended: {grace_end_date.strftime('%d-%m-%Y')})"
                        
                        st.error(f"""
                        ❌ **Policy has Lapsed (Pakka Lapse)**
                        
                        - Policy lapsed on: **{lapse_date.strftime('%d-%m-%Y')}** (5 months 29 days from base date)
                        - Days since lapse threshold: **{days_since_lapse} days**
                        - Days from base date ({calculation_base.strftime('%d-%m-%Y')}): **{days_from_base} days**
                        - Months late: **{months_late} months**
                        - Fine calculation: {fine_formula} = **₹{result['fine']:,.2f}**
                        - Total amount for revival: **₹{(modal_premium + result['fine']):,.2f}**
                        """)
                        
                        if result['months_pending'] > 0:
                            st.info(f"📌 **Pending payments:** {result['months_pending']} payment(s) missed")
                        
                        # Additional breakdown for Pakka Lapse
                        import pandas as pd
                        
                        # Fine label varies by payment mode
                        if payment_mode == 'Monthly':
                            fine_label = 'Fine (5% per month)'
                        else:
                            fine_label = 'Fine (0.9% per month)'
                        
                        st.markdown("#### 💳 Revival Payment Breakdown")
                        breakdown_df = pd.DataFrame({
                            'Component': ['Modal Premium', fine_label, 'Total for Revival'],
                            'Amount': [
                                f"₹{modal_premium:,.2f}",
                                f"₹{result['fine']:,.2f}",
                                f"₹{(modal_premium + result['fine']):,.2f}"
                            ]
                        })
                        st.table(breakdown_df)
                
                else:  # Late
                    time_diff = relativedelta(today_date_input, calculation_base)
                    months_late = time_diff.months + (time_diff.years * 12)
                    
                    # Fine formula varies by payment mode
                    if payment_mode == 'Monthly':
                        fine_formula = f"₹{modal_premium:,.2f} × 5% × {months_late} months"
                    else:
                        # For non-monthly, show grace end date and actual months from base
                        grace_end_date = calculation_base + relativedelta(days=29)
                        fine_formula = f"₹{modal_premium:,.2f} × 0.9% × {months_late} months (Grace ended: {grace_end_date.strftime('%d-%m-%Y')})"
                    
                    st.warning(f"""
                    ⚠️ **Policy is Late - Fine Applicable**
                    
                    - Grace period expired: **{days_from_base - grace_period} days ago**
                    - Months late: **{months_late} months**
                    - Fine calculation: {fine_formula} = **₹{result['fine']:,.2f}**
                    - Total amount due: **₹{(modal_premium + result['fine']):,.2f}**
                    """)
                    
                    if result['months_pending'] > 0:
                        st.info(f"📌 **Total pending payments:** {result['months_pending']} payment(s) missed since last premium paid")
                    
                    # Additional breakdown
                    import pandas as pd
                    
                    # Fine label varies by payment mode
                    if payment_mode == 'Monthly':
                        fine_label = 'Fine (5% per month)'
                    else:
                        fine_label = 'Fine (0.9% per month)'
                    
                    st.markdown("#### 💳 Payment Breakdown")
                    breakdown_df = pd.DataFrame({
                        'Component': ['Modal Premium', fine_label, 'Total Payable'],
                        'Amount': [
                            f"₹{modal_premium:,.2f}",
                            f"₹{result['fine']:,.2f}",
                            f"₹{(modal_premium + result['fine']):,.2f}"
                        ]
                    })
                    st.table(breakdown_df)

if __name__ == "__main__":
    main()
