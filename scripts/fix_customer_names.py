import sqlite3
import re
from pathlib import Path

def get_project_root():
    """Get the project root directory"""
    return Path(__file__).parent.parent

def fix_customer_names():
    """Fix customer names that contain policy numbers"""
    db_path = get_project_root() / "data" / "lic_customers.db"
    
    if not db_path.exists():
        print("❌ Database not found!")
        return
    
    print("🔧 Fixing customer names that contain policy numbers...")
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Find customers whose names are policy numbers or contain mostly digits
        cursor.execute("""
            SELECT customer_id, customer_name 
            FROM customers 
            WHERE customer_name NOT LIKE 'Customer_%'
        """)
        
        customers = cursor.fetchall()
        fixed_count = 0
        
        print(f"📋 Checking {len(customers)} customers...")
        
        for customer_id, customer_name in customers:
            should_fix = False
            
            # Check if name is just a policy number (9 digits)
            if re.match(r'^\d{9}$', customer_name.replace(' ', '')):
                should_fix = True
                reason = "Name is a policy number"
            
            # Check if name contains more digits than letters
            elif len([c for c in customer_name if c.isdigit()]) > len([c for c in customer_name if c.isalpha()]):
                should_fix = True
                reason = "Name contains more digits than letters"
            
            # Check if name is mostly numbers with some spaces/punctuation
            elif re.search(r'\d{6,}', customer_name):
                should_fix = True
                reason = "Name contains long number sequence"
            
            if should_fix:
                # Get the policy number for this customer
                cursor.execute("SELECT policy_number FROM policies WHERE customer_id = ? LIMIT 1", (customer_id,))
                policy_result = cursor.fetchone()
                
                if policy_result:
                    policy_number = policy_result[0]
                    new_name = f"Customer_{policy_number}"
                    
                    # Update the customer name
                    cursor.execute(
                        "UPDATE customers SET customer_name = ? WHERE customer_id = ?", 
                        (new_name, customer_id)
                    )
                    
                    print(f"  🔄 Fixed: '{customer_name}' -> '{new_name}' ({reason})")
                    fixed_count += 1
                else:
                    print(f"  ⚠️  No policy found for customer {customer_id}: {customer_name}")
        
        if fixed_count > 0:
            conn.commit()
            print(f"✅ Fixed {fixed_count} customer names")
        else:
            print("✅ No customer names needed fixing")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    fix_customer_names()
