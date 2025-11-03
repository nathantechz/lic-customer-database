import streamlit as st
import pandas as pd
from pathlib import Path
import re
from datetime import datetime, date
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

def display_customer_card(customer):
    """Display a customer card"""
    with st.container():
        st.markdown("---")
        
        # Customer header with edit button
        header_col, edit_col = st.columns([4, 1])
        
        with header_col:
            # Customer header with color coding and nickname
            is_generic = customer['customer_name'].startswith('Customer_')
            nickname = customer.get('nickname', '')
            has_duplicates = customer.get('potential_duplicates', [])
            
            # Display customer name with appropriate styling
            if has_duplicates:
                if nickname:
                    st.warning(f"🔄 {customer['customer_name']} - 🏷️ {nickname} (Potential Duplicates Found)")
                else:
                    st.warning(f"🔄 {customer['customer_name']} (Potential Duplicates Found)")
            elif is_generic:
                if nickname:
                    st.error(f"⚠️ {customer['customer_name']} (Generic Name) - 🏷️ {nickname}")
                else:
                    st.error(f"⚠️ {customer['customer_name']} (Generic Name)")
            else:
                if nickname:
                    st.success(f"👤 {customer['customer_name']} - 🏷️ {nickname}")
                else:
                    st.success(f"👤 {customer['customer_name']}")
        
        with edit_col:
            edit_key = f"edit_{customer['customer_id']}"
            if st.button("✏️ Edit", key=edit_key, type="secondary", width="stretch"):
                st.session_state.edit_customer_id = customer['customer_id']
                st.rerun()
        
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
            st.markdown(f"🏷️ **Nickname:** {customer.get('nickname') or 'N/A'}")
            st.markdown(f"📞 **Phone:** {customer.get('phone_number') or 'N/A'}")
            st.markdown(f"📧 **Email:** {customer.get('email') or 'N/A'}")
        
        with col2:
            st.markdown(f"💼 **Occupation:** {customer.get('occupation') or 'N/A'}")
            st.markdown(f"🆔 **Aadhaar:** {customer.get('aadhaar_number') or 'N/A'}")
            st.markdown(f"🎂 **DOB:** {customer.get('date_of_birth') or 'N/A'}")
        
        with col3:
            st.markdown(f"📞 **Alt Phone:** {customer.get('alt_phone_number') or 'N/A'}")
            st.markdown(f"� **Updated:** {customer.get('last_updated') or 'N/A'}")
            
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
        
        # Enhanced Policies section with edit functionality
        if customer['policies']:
            with st.expander(f"📋 Policies ({len(customer['policies'])})", expanded=True):
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
        
        # Add Policy button for this customer
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            add_policy_key = f"add_policy_btn_{customer['customer_id']}"
            if st.button("➕ Add Policy", key=add_policy_key, type="secondary"):
                st.session_state.add_policy_customer_id = customer['customer_id']
                st.session_state.add_policy_customer_name = customer['customer_name']
                st.rerun()
        
        with col2:
            policy_count = len(customer['policies'])
            if policy_count > 0:
                st.info(f"📋 {policy_count} policies")
            else:
                st.warning("No policies yet")

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
        st.markdown("###📁 Project Info")
        
        db_exists, db_info = check_database_exists()
        st.write(f"**Database:** {'✅ Connected' if db_exists else '❌ Disconnected'}")
        
        if db_exists:
            st.success("✅ Supabase Connected!")
            st.info(f"Using: {db_info}")
        else:
            st.error("❌ Connection Failed")
            st.code(str(db_info))
    
    # Main content
    db_exists, _ = check_database_exists()
    
    if not db_exists:
        show_setup_instructions()
        st.stop()
    
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
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
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
                display_customer_card(customer)
                
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
                display_customer_card(customer)
                
                # Add pagination for large results
                if i > 0 and (i + 1) % 10 == 0 and i + 1 < len(customers):
                    if not st.button(f"Show more... ({len(customers) - i - 1} remaining)", key=f"more_{i}"):
                        break
        else:
            if query:
                st.warning(f"🔍 No customers found matching: **{query}**")
            else:
                st.info("📋 No customers in database yet. Process some PDFs first!")

if __name__ == "__main__":
    main()
