"""
Merge plan_type and plan_name into single plan_name column
Priority: plan_name (PDF extracted) > plan_type (manual entries)
Then remove plan_type column
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

def main():
    print("\n" + "=" * 80)
    print("🔧 MERGE PLAN_TYPE AND PLAN_NAME COLUMNS")
    print("=" * 80 + "\n")
    
    try:
        # Connect to Supabase
        print("Connecting to Supabase...")
        supabase = get_supabase_client()
        print("✅ Connected to Supabase\n")
        
        # Get all policies
        print("Fetching all policies...")
        response = supabase.table('policies').select('policy_number, plan_type, plan_name').execute()
        
        if not response.data:
            print("No policies found.")
            return
        
        print(f"Found {len(response.data)} policies\n")
        
        # Calculate which policies need updating
        updates_needed = []
        for policy in response.data:
            plan_type = policy.get('plan_type')
            plan_name = policy.get('plan_name')
            
            # If plan_name is empty but plan_type has value, copy plan_type to plan_name
            if plan_type and not plan_name:
                updates_needed.append({
                    'policy_number': policy['policy_number'],
                    'current_plan_name': plan_name,
                    'current_plan_type': plan_type,
                    'new_plan_name': plan_type.strip() if plan_type else None,
                    'reason': 'Fill empty plan_name with plan_type'
                })
            # If both exist but different (contradiction), keep plan_name (PDF extracted)
            elif plan_type and plan_name and plan_type.strip() != plan_name.strip():
                # Just log, no update needed since we're keeping plan_name
                pass
        
        if not updates_needed:
            print("✅ All policies already have plan_name values or plan_type is empty")
        else:
            print(f"Found {len(updates_needed)} policies that need plan_name update\n")
            
            # Show preview of first 10 changes
            print("📋 Preview of changes (first 10):")
            print("-" * 80)
            for i, update in enumerate(updates_needed[:10]):
                print(f"{i+1}. Policy {update['policy_number']}: plan_name EMPTY → '{update['new_plan_name']}'")
            
            if len(updates_needed) > 10:
                print(f"... and {len(updates_needed) - 10} more policies")
            
            print("-" * 80)
            
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
                        'plan_name': update['new_plan_name']
                    }).eq('policy_number', update['policy_number']).execute()
                    
                    updated_count += 1
                    if updated_count % 10 == 0:
                        print(f"   Updated {updated_count}/{len(updates_needed)} policies...")
                        
                except Exception as e:
                    error_count += 1
                    print(f"❌ Error updating policy {update['policy_number']}: {e}")
            
            print(f"\n{'=' * 80}")
            print("✅ Update Complete!")
            print(f"   Successfully updated: {updated_count} policies")
            if error_count > 0:
                print(f"   Errors: {error_count} policies")
            print("=" * 80 + "\n")
        
        # Summary statistics
        print("📊 Final Statistics:")
        print("-" * 80)
        
        # Re-fetch to get current state
        final_response = supabase.table('policies').select('plan_type, plan_name').execute()
        
        total = len(final_response.data)
        with_plan_name = sum(1 for p in final_response.data if p.get('plan_name'))
        with_plan_type = sum(1 for p in final_response.data if p.get('plan_type'))
        both_filled = sum(1 for p in final_response.data if p.get('plan_type') and p.get('plan_name'))
        
        print(f"Total Policies: {total}")
        print(f"Policies with plan_name: {with_plan_name} ({with_plan_name/total*100:.1f}%)")
        print(f"Policies with plan_type: {with_plan_type} ({with_plan_type/total*100:.1f}%)")
        print(f"Policies with both: {both_filled}")
        
        print("\n⚠️  Note: plan_type column still exists in database.")
        print("   After verifying the changes, you can manually drop the plan_type column")
        print("   from the Supabase dashboard if no longer needed.")
        print("-" * 80 + "\n")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
