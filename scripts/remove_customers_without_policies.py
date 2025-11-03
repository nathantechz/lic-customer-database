#!/usr/bin/env python3
"""
Script to remove customers from Supabase that don't have any policies.
This helps clean up the database by removing empty customer records.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from supabase import create_client, Client
    import streamlit as st
except ImportError:
    print("Installing required packages...")
    os.system("pip install supabase python-dotenv")
    from supabase import create_client, Client

def get_supabase_client() -> Client:
    """Get Supabase client connection"""
    try:
        # Try to get from Streamlit secrets first
        try:
            import streamlit as st
            url = st.secrets["supabase"]["url"]
            key = st.secrets["supabase"]["key"]
        except:
            # Fallback to environment variables
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_KEY")
            
            if not url or not key:
                print("Error: Supabase credentials not found!")
                print("Please set SUPABASE_URL and SUPABASE_KEY environment variables")
                print("Or configure them in .streamlit/secrets.toml")
                sys.exit(1)
        
        return create_client(url, key)
    except Exception as e:
        print(f"❌ Failed to connect to Supabase: {e}")
        sys.exit(1)

def find_customers_without_policies():
    """Find all customers that don't have any policies"""
    supabase = get_supabase_client()
    
    print("🔍 Searching for customers without policies...")
    
    try:
        # Get all customers with their policies
        response = supabase.table('customers').select('customer_id, customer_name, policies(policy_number)').execute()
        
        customers_without_policies = []
        
        for customer in response.data:
            # Check if customer has no policies or empty policies list
            policies = customer.get('policies', [])
            if not policies or len(policies) == 0:
                customers_without_policies.append(customer)
        
        return customers_without_policies
        
    except Exception as e:
        print(f"❌ Error querying database: {e}")
        return []

def remove_customers_without_policies(dry_run=True):
    """Remove customers without policies from the database"""
    supabase = get_supabase_client()
    
    # Find customers without policies
    customers_to_remove = find_customers_without_policies()
    
    if not customers_to_remove:
        print("✅ No customers without policies found. Database is clean!")
        return
    
    print(f"\n📊 Found {len(customers_to_remove)} customers without policies:")
    print("-" * 80)
    
    for customer in customers_to_remove:
        print(f"  • {customer['customer_name']} (ID: {customer['customer_id']})")
    
    print("-" * 80)
    
    if dry_run:
        print("\n⚠️  DRY RUN MODE - No changes will be made")
        print("Run with --execute flag to actually delete these customers")
        return
    
    # Confirm deletion
    print(f"\n⚠️  WARNING: This will permanently delete {len(customers_to_remove)} customers!")
    response = input("Type 'DELETE' to confirm: ")
    
    if response != 'DELETE':
        print("❌ Deletion cancelled")
        return
    
    # Delete customers
    deleted_count = 0
    failed_count = 0
    
    print("\n🗑️  Deleting customers without policies...")
    
    for customer in customers_to_remove:
        try:
            supabase.table('customers').delete().eq('customer_id', customer['customer_id']).execute()
            deleted_count += 1
            print(f"  ✅ Deleted: {customer['customer_name']} (ID: {customer['customer_id']})")
        except Exception as e:
            failed_count += 1
            print(f"  ❌ Failed to delete {customer['customer_name']}: {e}")
    
    print("\n" + "=" * 80)
    print(f"✅ Successfully deleted: {deleted_count} customers")
    if failed_count > 0:
        print(f"❌ Failed to delete: {failed_count} customers")
    print("=" * 80)

def main():
    """Main function"""
    print("=" * 80)
    print("🧹 Customer Cleanup Tool - Remove Customers Without Policies")
    print("=" * 80)
    
    # Check if --execute flag is provided
    dry_run = '--execute' not in sys.argv
    
    remove_customers_without_policies(dry_run=dry_run)
    
    print("\n✅ Done!")

if __name__ == "__main__":
    main()
