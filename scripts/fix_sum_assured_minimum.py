"""
Fix sum_assured values in database to ensure minimum ₹50,000
Converts values to proper rupee amounts:
- Values < 50 → multiply by 100,000 (lacs)
- Values 50-999 → multiply by 1,000 (thousands)
- Values >= 1000 → keep as is
- Ensures minimum value of ₹50,000
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
    Normalize sum assured to actual rupee values with minimum ₹50,000
    """
    if value is None or value == '':
        return None
    
    try:
        val = float(value)
        
        # If value is less than 50, it's in lacs
        if 0 < val < 50:
            converted = val * 100000  # 1 → 1,00,000 (1 lac), 5 → 5,00,000
        
        # If value is between 50 and 999, it's in thousands
        elif 50 <= val < 1000:
            converted = val * 1000  # 50 → 50,000, 100 → 1,00,000
        
        # If value is 1000 or more, assume it's already in proper format
        else:
            converted = val
        
        # Ensure minimum sum assured of ₹50,000
        if converted < 50000:
            return 50000
        
        return converted
            
    except (ValueError, TypeError):
        return None

def main():
    print("\n" + "=" * 70)
    print("🔧 FIX SUM ASSURED VALUES - MINIMUM ₹50,000")
    print("=" * 70 + "\n")
    
    try:
        # Connect to Supabase
        print("Connecting to Supabase...")
        supabase = get_supabase_client()
        print("✅ Connected to Supabase\n")
        
        # Get all policies with sum_assured values
        print("Fetching policies with sum_assured values...")
        response = supabase.table('policies').select('policy_number, sum_assured').not_.is_('sum_assured', 'null').execute()
        
        if not response.data:
            print("No policies found with sum_assured values.")
            return
        
        print(f"Found {len(response.data)} policies with sum_assured values\n")
        
        # Calculate which policies need updating
        updates_needed = []
        for policy in response.data:
            current_value = policy['sum_assured']
            if current_value is not None:
                new_value = normalize_sum_assured(current_value)
                if new_value != current_value:
                    updates_needed.append({
                        'policy_number': policy['policy_number'],
                        'old_value': current_value,
                        'new_value': new_value
                    })
        
        if not updates_needed:
            print("✅ All policies already have correct sum_assured values (minimum ₹50,000)")
            return
        
        print(f"Found {len(updates_needed)} policies that need updating\n")
        
        # Show preview of first 10 changes
        print("📋 Preview of changes (first 10):")
        print("-" * 70)
        for i, update in enumerate(updates_needed[:10]):
            print(f"{i+1}. Policy {update['policy_number']}: ₹{update['old_value']:,.2f} → ₹{update['new_value']:,.2f}")
        
        if len(updates_needed) > 10:
            print(f"... and {len(updates_needed) - 10} more policies")
        
        print("-" * 70)
        
        # Confirm before proceeding
        confirm = input(f"\nDo you want to update these {len(updates_needed)} policies? (yes/no): ").strip().lower()
        if confirm != 'yes':
            print("❌ Update cancelled")
            return
        
        # Perform updates
        print(f"\n🔄 Updating {len(updates_needed)} policies...")
        updated_count = 0
        error_count = 0
        
        for update in updates_needed:
            try:
                supabase.table('policies').update({
                    'sum_assured': update['new_value']
                }).eq('policy_number', update['policy_number']).execute()
                
                updated_count += 1
                if updated_count % 10 == 0:
                    print(f"   Updated {updated_count}/{len(updates_needed)} policies...")
                    
            except Exception as e:
                error_count += 1
                print(f"❌ Error updating policy {update['policy_number']}: {e}")
        
        print(f"\n{'=' * 70}")
        print("✅ Update Complete!")
        print(f"   Successfully updated: {updated_count} policies")
        if error_count > 0:
            print(f"   Errors: {error_count} policies")
        print("=" * 70 + "\n")
        
        # Verify no policies below ₹50,000 remain
        print("🔍 Verifying updates...")
        verify_response = supabase.table('policies').select('policy_number, sum_assured').lt('sum_assured', 50000).execute()
        
        if verify_response.data:
            print(f"⚠️  Warning: {len(verify_response.data)} policies still have sum_assured below ₹50,000")
            for policy in verify_response.data[:5]:
                print(f"   Policy {policy['policy_number']}: ₹{policy['sum_assured']:,.2f}")
        else:
            print("✅ All policies now have sum_assured >= ₹50,000")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
