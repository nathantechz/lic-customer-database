"""
Clean up customers without any policies
Removes customers from Supabase AND Local Database that don't have any associated policy records
"""

from pathlib import Path
from supabase import create_client, Client
import sqlite3
import sys

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
    """Get local SQLite database connection"""
    try:
        project_root = Path(__file__).parent.parent
        db_path = project_root / 'data' / 'lic_local_backup.db'
        
        if not db_path.exists():
            print("⚠️  Local database not found")
            return None
        
        conn = sqlite3.connect(str(db_path))
        return conn
    except Exception as e:
        print(f"⚠️  Failed to connect to local database: {e}")
        return None

def cleanup_customers_without_policies():
    """Remove customers that don't have any policies"""
    print("\n" + "="*60)
    print("🧹 CUSTOMER CLEANUP - Remove Customers Without Policies")
    print("="*60)
    
    # Connect to Supabase
    try:
        print("\n🔌 Connecting to Supabase...")
        supabase = get_supabase_client()
        print("✅ Connected to Supabase")
    except Exception as e:
        print(f"❌ Failed to connect to Supabase: {e}")
        return
    
    # Connect to local database
    print("💾 Connecting to Local Database...")
    local_conn = get_local_db_connection()
    if local_conn:
        print("✅ Connected to Local Database")
    else:
        print("⚠️  Local database not available - will only clean Supabase")
    
    # Get all customers
    print("\n👥 Fetching all customers...")
    try:
        customers_result = supabase.table('customers').select('customer_id, customer_name').execute()
        all_customers = customers_result.data if customers_result.data else []
        print(f"✅ Found {len(all_customers)} total customers")
    except Exception as e:
        print(f"❌ Failed to fetch customers: {e}")
        return
    
    # Get all policies with customer IDs
    print("\n📋 Fetching all policies...")
    try:
        policies_result = supabase.table('policies').select('customer_id').execute()
        all_policies = policies_result.data if policies_result.data else []
        print(f"✅ Found {len(all_policies)} total policies")
    except Exception as e:
        print(f"❌ Failed to fetch policies: {e}")
        return
    
    # Get set of customer IDs that have policies
    customer_ids_with_policies = set()
    for policy in all_policies:
        if policy.get('customer_id'):
            customer_ids_with_policies.add(policy['customer_id'])
    
    print(f"\n📊 {len(customer_ids_with_policies)} customers have policies")
    
    # Find customers without policies
    customers_to_delete = []
    for customer in all_customers:
        if customer['customer_id'] not in customer_ids_with_policies:
            customers_to_delete.append(customer)
    
    print(f"🗑️  Found {len(customers_to_delete)} customers WITHOUT policies")
    
    if not customers_to_delete:
        print("\n✅ No customers to delete. All customers have policies!")
        return
    
    # Show preview
    print("\n📋 Preview of customers to be deleted:")
    for i, customer in enumerate(customers_to_delete[:10], 1):
        print(f"  {i}. {customer['customer_name']} (ID: {customer['customer_id']})")
    
    if len(customers_to_delete) > 10:
        print(f"  ... and {len(customers_to_delete) - 10} more")
    
    # Confirm deletion
    print("\n⚠️  WARNING: This will permanently delete these customers from BOTH databases!")
    response = input(f"\nDelete {len(customers_to_delete)} customers? (yes/no): ").strip().lower()
    
    if response != 'yes':
        print("❌ Deletion cancelled")
        if local_conn:
            local_conn.close()
        return
    
    # Delete customers from Supabase
    print(f"\n🗑️  Deleting {len(customers_to_delete)} customers from Supabase...")
    supabase_deleted = 0
    supabase_errors = 0
    
    for customer in customers_to_delete:
        try:
            supabase.table('customers').delete().eq('customer_id', customer['customer_id']).execute()
            supabase_deleted += 1
            if supabase_deleted % 10 == 0:
                print(f"  ✅ Supabase: Deleted {supabase_deleted}/{len(customers_to_delete)}")
        except Exception as e:
            print(f"  ❌ Supabase: Failed to delete {customer['customer_name']}: {e}")
            supabase_errors += 1
    
    # Delete customers from local database
    local_deleted = 0
    local_errors = 0
    
    if local_conn:
        print(f"\n🗑️  Deleting customers from Local Database...")
        cursor = local_conn.cursor()
        
        for customer in customers_to_delete:
            try:
                # Delete by customer_name since local DB might have different IDs
                cursor.execute('DELETE FROM customers WHERE customer_name = ?', 
                             (customer['customer_name'],))
                local_deleted += cursor.rowcount
                if local_deleted % 10 == 0:
                    print(f"  ✅ Local DB: Deleted {local_deleted} customers")
            except Exception as e:
                print(f"  ❌ Local DB: Failed to delete {customer['customer_name']}: {e}")
                local_errors += 1
        
        local_conn.commit()
        local_conn.close()
    
    # Summary
    print("\n" + "="*60)
    print("📊 CLEANUP SUMMARY")
    print("="*60)
    print(f"SUPABASE CLOUD:")
    print(f"  ✅ Successfully deleted: {supabase_deleted} customers")
    if supabase_errors > 0:
        print(f"  ❌ Failed to delete: {supabase_errors} customers")
    
    if local_conn:
        print(f"\nLOCAL DATABASE:")
        print(f"  ✅ Successfully deleted: {local_deleted} customers")
        if local_errors > 0:
            print(f"  ❌ Failed to delete: {local_errors} customers")
    
    print(f"\n📋 Remaining customers in Supabase: {len(all_customers) - supabase_deleted}")
    print("="*60)

if __name__ == "__main__":
    cleanup_customers_without_policies()
