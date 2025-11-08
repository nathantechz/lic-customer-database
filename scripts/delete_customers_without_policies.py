#!/usr/bin/env python3
"""
Delete customers from Supabase who don't have any policies
"""

import os
from supabase import create_client, Client
from pathlib import Path

def get_supabase_client() -> Client:
    """Get Supabase client connection"""
    # Try to get credentials from Streamlit secrets first
    secrets_path = Path(__file__).parent.parent / '.streamlit' / 'secrets.toml'
    
    if secrets_path.exists():
        try:
            import toml
            secrets = toml.load(secrets_path)
            url = secrets['supabase']['url']
            key = secrets['supabase']['key']
        except Exception as e:
            print(f"Failed to load secrets.toml: {e}")
            raise
    else:
        # Fallback to environment variables
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        
        if not url or not key:
            raise Exception("Supabase credentials not found. Please set SUPABASE_URL and SUPABASE_KEY environment variables or configure .streamlit/secrets.toml")
    
    print(f"   Using Supabase URL: {url[:30]}...")
    return create_client(url, key)

def delete_customers_without_policies():
    """Delete all customers who don't have any policies"""
    
    print("🔗 Connecting to Supabase...")
    supabase = get_supabase_client()
    
    try:
        # Get all customers
        print("📊 Fetching all customers...")
        customers_response = supabase.table('customers').select('customer_id, customer_name').execute()
        all_customers = customers_response.data
        print(f"   Found {len(all_customers)} total customers")
        
        # Get all customer IDs that have policies
        print("📋 Fetching all policies...")
        policies_response = supabase.table('policies').select('customer_id').execute()
        customer_ids_with_policies = set(policy['customer_id'] for policy in policies_response.data)
        print(f"   Found {len(customer_ids_with_policies)} customers with policies")
        
        # Find customers without policies
        customers_without_policies = [
            customer for customer in all_customers 
            if customer['customer_id'] not in customer_ids_with_policies
        ]
        
        if not customers_without_policies:
            print("✅ No customers found without policies. Database is clean!")
            return
        
        print(f"\n⚠️  Found {len(customers_without_policies)} customers WITHOUT policies:")
        print("-" * 60)
        for customer in customers_without_policies:
            print(f"   • {customer['customer_name']} (ID: {customer['customer_id']})")
        print("-" * 60)
        
        # Ask for confirmation
        response = input(f"\n❓ Do you want to DELETE these {len(customers_without_policies)} customers? (yes/no): ")
        
        if response.lower() not in ['yes', 'y']:
            print("❌ Deletion cancelled.")
            return
        
        # Delete customers
        print("\n🗑️  Deleting customers without policies...")
        deleted_count = 0
        
        for customer in customers_without_policies:
            try:
                supabase.table('customers').delete().eq('customer_id', customer['customer_id']).execute()
                deleted_count += 1
                print(f"   ✓ Deleted: {customer['customer_name']}")
            except Exception as e:
                print(f"   ✗ Failed to delete {customer['customer_name']}: {e}")
        
        print(f"\n✅ Successfully deleted {deleted_count} out of {len(customers_without_policies)} customers")
        print("🎉 Cleanup complete!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        raise

if __name__ == "__main__":
    print("=" * 60)
    print("   🧹 CLEANUP: Delete Customers Without Policies")
    print("=" * 60)
    print()
    
    try:
        delete_customers_without_policies()
    except KeyboardInterrupt:
        print("\n\n❌ Operation cancelled by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        exit(1)
