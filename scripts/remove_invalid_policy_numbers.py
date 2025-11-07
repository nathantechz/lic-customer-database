#!/usr/bin/env python3
"""
Script to remove customers from Supabase and local SQLite database
whose policy numbers have more than 9 digits
"""

import os
import sys
import sqlite3
from supabase import create_client, Client
import toml

def get_supabase_client() -> Client:
    """Initialize and return Supabase client"""
    supabase_url = None
    supabase_key = None
    
    # Try to read from .streamlit/secrets.toml
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        secrets_path = os.path.join(script_dir, '.streamlit', 'secrets.toml')
        if os.path.exists(secrets_path):
            secrets = toml.load(secrets_path)
            # Check if nested under [supabase]
            if 'supabase' in secrets:
                supabase_url = secrets['supabase'].get('url')
                supabase_key = secrets['supabase'].get('key')
            else:
                supabase_url = secrets.get('SUPABASE_URL')
                supabase_key = secrets.get('SUPABASE_KEY')
    except Exception as e:
        print(f"Warning: Could not read secrets.toml: {e}")
    
    # Fall back to environment variables if not found
    if not supabase_url:
        supabase_url = os.getenv('SUPABASE_URL')
    if not supabase_key:
        supabase_key = os.getenv('SUPABASE_KEY')
    
    if not supabase_url or not supabase_key:
        raise ValueError("Supabase credentials not found in secrets.toml or environment variables")
    
    return create_client(supabase_url, supabase_key)

def find_invalid_policies(supabase: Client):
    """Find all policies with more than 9 digits"""
    print("🔍 Searching for policies with invalid policy numbers (more than 9 digits)...")
    
    # Get all policies
    response = supabase.table('policies').select('policy_number, customer_id').execute()
    
    invalid_policies = []
    for policy in response.data:
        policy_number = str(policy['policy_number']).replace('.', '').replace('-', '').strip()
        # Check if it's all digits and has more than 9 digits
        if policy_number.isdigit() and len(policy_number) > 9:
            invalid_policies.append(policy)
    
    return invalid_policies

def get_customers_to_remove(supabase: Client, invalid_policies: list):
    """Get unique customer IDs from invalid policies"""
    customer_ids = set()
    customer_info = {}
    
    for policy in invalid_policies:
        customer_id = policy['customer_id']
        customer_ids.add(customer_id)
        
        if customer_id not in customer_info:
            # Get customer details
            customer = supabase.table('customers').select('customer_id, customer_name').eq('customer_id', customer_id).execute()
            if customer.data:
                customer_info[customer_id] = {
                    'name': customer.data[0]['customer_name'],
                    'policies': []
                }
        
        customer_info[customer_id]['policies'].append({
            'policy_number': policy['policy_number']
        })
    
    return list(customer_ids), customer_info

def remove_from_supabase(supabase: Client, customer_ids: list, dry_run: bool = True):
    """Remove customers and their policies from Supabase"""
    stats = {
        'policies_deleted': 0,
        'customers_deleted': 0,
        'errors': 0
    }
    
    for customer_id in customer_ids:
        try:
            if not dry_run:
                # Delete policies first (due to foreign key constraint)
                policies_response = supabase.table('policies').delete().eq('customer_id', customer_id).execute()
                stats['policies_deleted'] += len(policies_response.data) if policies_response.data else 0
                
                # Delete customer
                customer_response = supabase.table('customers').delete().eq('customer_id', customer_id).execute()
                stats['customers_deleted'] += 1
        except Exception as e:
            print(f"❌ Error deleting customer {customer_id} from Supabase: {e}")
            stats['errors'] += 1
    
    return stats

def remove_from_sqlite(customer_ids: list, dry_run: bool = True):
    """Remove customers and their policies from local SQLite database"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, 'lic_customers.db')
    
    if not os.path.exists(db_path):
        print(f"⚠️  SQLite database not found at {db_path}")
        return {'policies_deleted': 0, 'customers_deleted': 0, 'errors': 0}
    
    stats = {
        'policies_deleted': 0,
        'customers_deleted': 0,
        'errors': 0
    }
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        for customer_id in customer_ids:
            try:
                if not dry_run:
                    # Delete policies first
                    cursor.execute("DELETE FROM policies WHERE customer_id = ?", (customer_id,))
                    stats['policies_deleted'] += cursor.rowcount
                    
                    # Delete customer
                    cursor.execute("DELETE FROM customers WHERE customer_id = ?", (customer_id,))
                    stats['customers_deleted'] += cursor.rowcount
                else:
                    # Count what would be deleted
                    cursor.execute("SELECT COUNT(*) FROM policies WHERE customer_id = ?", (customer_id,))
                    stats['policies_deleted'] += cursor.fetchone()[0]
                    stats['customers_deleted'] += 1
                    
            except Exception as e:
                print(f"❌ Error deleting customer {customer_id} from SQLite: {e}")
                stats['errors'] += 1
        
        if not dry_run:
            conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error connecting to SQLite database: {e}")
        stats['errors'] += 1
    
    return stats

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Remove customers with invalid policy numbers (more than 9 digits)')
    parser.add_argument('--execute', action='store_true', help='Actually delete from database (default is dry-run)')
    
    args = parser.parse_args()
    
    print("🗑️  Invalid Policy Number Removal Tool")
    print("="*80)
    print("Policy numbers should be exactly 9 digits")
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY RUN'}")
    print("="*80 + "\n")
    
    # Initialize Supabase client
    supabase = get_supabase_client()
    
    # Find invalid policies
    invalid_policies = find_invalid_policies(supabase)
    
    if not invalid_policies:
        print("✅ No invalid policy numbers found!")
        return
    
    print(f"⚠️  Found {len(invalid_policies)} policies with more than 9 digits\n")
    
    # Get customers to remove
    customer_ids, customer_info = get_customers_to_remove(supabase, invalid_policies)
    
    print(f"📋 This affects {len(customer_ids)} customers:\n")
    
    # Display customer information
    for customer_id in customer_ids:
        info = customer_info[customer_id]
        print(f"Customer: {info['name']} (ID: {customer_id})")
        for policy in info['policies']:
            policy_num = str(policy['policy_number'])
            digit_count = len(policy_num.replace('.', '').replace('-', '').strip())
            print(f"  - Policy: {policy_num} ({digit_count} digits)")
        print()
    
    if args.execute:
        confirmation = input(f"⚠️  This will DELETE {len(customer_ids)} customers and their policies from both databases. Continue? (yes/no): ")
        if confirmation.lower() != 'yes':
            print("❌ Cancelled by user")
            sys.exit(0)
        
        print("\n🗑️  Removing from Supabase...")
        supabase_stats = remove_from_supabase(supabase, customer_ids, dry_run=False)
        
        print("🗑️  Removing from SQLite...")
        sqlite_stats = remove_from_sqlite(customer_ids, dry_run=False)
        
        print("\n" + "="*80)
        print("📊 DELETION SUMMARY")
        print("="*80)
        print(f"Supabase:")
        print(f"  - Customers deleted: {supabase_stats['customers_deleted']}")
        print(f"  - Policies deleted: {supabase_stats['policies_deleted']}")
        print(f"  - Errors: {supabase_stats['errors']}")
        print(f"\nSQLite:")
        print(f"  - Customers deleted: {sqlite_stats['customers_deleted']}")
        print(f"  - Policies deleted: {sqlite_stats['policies_deleted']}")
        print(f"  - Errors: {sqlite_stats['errors']}")
        print("\n✅ Deletion complete!")
    else:
        # Dry run - show what would be deleted
        sqlite_stats = remove_from_sqlite(customer_ids, dry_run=True)
        
        print("="*80)
        print("📊 DRY RUN SUMMARY - What would be deleted:")
        print("="*80)
        print(f"Customers: {len(customer_ids)}")
        print(f"Policies (Supabase): {len(invalid_policies)}")
        print(f"Policies (SQLite): {sqlite_stats['policies_deleted']}")
        print("\n⚠️  DRY RUN MODE - No changes were made to the databases")
        print("Run with --execute flag to actually delete the data")

if __name__ == "__main__":
    main()
