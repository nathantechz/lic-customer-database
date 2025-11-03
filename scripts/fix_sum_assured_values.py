"""
Fix sum_assured values in database
Converts values to proper rupee amounts:
- Values between 1-9 → multiply by 100,000 (lacs)
- Values between 10-99 → multiply by 1,000 (thousands)
- Values 100+ → keep as is
"""

from pathlib import Path
from supabase import create_client, Client
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

def normalize_sum_assured(value):
    """
    Normalize sum assured to actual rupee values
    """
    if value is None or value == '':
        return None
    
    try:
        val = float(value)
        
        # If value is between 10 and 99 (like 50), it's in thousands
        if 10 <= val < 100:
            return val * 1000  # 50 → 50,000
        
        # If value is less than 10 (like 1, 2, 5), it's in lacs
        elif 0 < val < 10:
            return val * 100000  # 1 → 1,00,000 (1 lac)
        
        # If value is 100 or more, assume it's already in proper format
        else:
            return val
            
    except (ValueError, TypeError):
        return None

def fix_sum_assured_values():
    """Fix all sum_assured values in the database"""
    print("\n" + "="*60)
    print("🔧 FIX SUM ASSURED VALUES")
    print("="*60)
    
    # Connect to Supabase
    try:
        print("\n🔌 Connecting to Supabase...")
        supabase = get_supabase_client()
        print("✅ Connected to Supabase")
    except Exception as e:
        print(f"❌ Failed to connect to Supabase: {e}")
        return
    
    # Get all policies with sum_assured
    print("\n📊 Fetching all policies with sum_assured...")
    try:
        response = supabase.table('policies').select('policy_number, sum_assured').not_.is_('sum_assured', 'null').execute()
        policies = response.data if response.data else []
        print(f"✅ Found {len(policies)} policies with sum_assured values")
    except Exception as e:
        print(f"❌ Failed to fetch policies: {e}")
        return
    
    if not policies:
        print("\n✅ No policies to update")
        return
    
    # Analyze and show what will be updated
    updates_needed = []
    for policy in policies:
        old_value = policy.get('sum_assured')
        if old_value:
            new_value = normalize_sum_assured(old_value)
            if new_value and new_value != old_value:
                updates_needed.append({
                    'policy_number': policy['policy_number'],
                    'old_value': old_value,
                    'new_value': new_value
                })
    
    print(f"\n📋 Found {len(updates_needed)} policies that need updating")
    
    if not updates_needed:
        print("\n✅ All sum_assured values are already correct!")
        return
    
    # Show preview
    print("\n📋 Preview of changes (first 10):")
    print(f"{'Policy Number':<15} {'Old Value':<15} {'New Value':<15}")
    print("-" * 50)
    for i, update in enumerate(updates_needed[:10], 1):
        old = f"₹{update['old_value']:,.0f}"
        new = f"₹{update['new_value']:,.0f}"
        print(f"{update['policy_number']:<15} {old:<15} {new:<15}")
    
    if len(updates_needed) > 10:
        print(f"... and {len(updates_needed) - 10} more")
    
    # Confirm update
    print(f"\n⚠️  WARNING: This will update {len(updates_needed)} sum_assured values!")
    response = input(f"\nProceed with updates? (yes/no): ").strip().lower()
    
    if response != 'yes':
        print("❌ Update cancelled")
        return
    
    # Update policies
    print(f"\n🔧 Updating {len(updates_needed)} policies...")
    updated_count = 0
    error_count = 0
    
    for update in updates_needed:
        try:
            supabase.table('policies').update({
                'sum_assured': update['new_value']
            }).eq('policy_number', update['policy_number']).execute()
            
            updated_count += 1
            if updated_count % 10 == 0:
                print(f"  ✅ Updated {updated_count}/{len(updates_needed)}")
        except Exception as e:
            print(f"  ❌ Failed to update {update['policy_number']}: {e}")
            error_count += 1
    
    # Summary
    print("\n" + "="*60)
    print("📊 UPDATE SUMMARY")
    print("="*60)
    print(f"✅ Successfully updated: {updated_count} policies")
    if error_count > 0:
        print(f"❌ Failed to update: {error_count} policies")
    print("="*60)

if __name__ == "__main__":
    fix_sum_assured_values()
