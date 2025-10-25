import sqlite3
from pathlib import Path
from datetime import datetime

def get_project_root():
    """Get the project root directory"""
    return Path(__file__).parent.parent

def show_database_stats():
    """Show comprehensive statistics for all databases"""
    
    databases = [
        ("Main Database", get_project_root() / "data" / "lic_customers.db"),
        ("Regex Database", get_project_root() / "data" / "lic_customers_regex.db"),
        ("Gemini Database", get_project_root() / "data" / "lic_customers_gemini.db"),
        ("Dual Database", get_project_root() / "data" / "lic_customers_dual.db"),
    ]
    
    print("🎉 === LIC DATABASE STATISTICS ===")
    print(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    for db_name, db_path in databases:
        if not db_path.exists():
            print(f"\n❌ {db_name}: Not found at {db_path}")
            continue
        
        print(f"\n📊 {db_name}")
        print(f"📍 Location: {db_path}")
        print(f"💾 Size: {db_path.stat().st_size:,} bytes")
        print("-" * 40)
        
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            # Get table counts
            tables = ['customers', 'policies', 'agents', 'premium_records', 'documents']
            
            for table in tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    print(f"  📋 {table.title()}: {count:,} records")
                except:
                    pass
            
            # Show recent customers
            try:
                cursor.execute("""
                    SELECT customer_name, created_date 
                    FROM customers 
                    ORDER BY created_date DESC 
                    LIMIT 5
                """)
                recent_customers = cursor.fetchall()
                
                if recent_customers:
                    print(f"\n  👥 Recent Customers:")
                    for name, date in recent_customers:
                        print(f"    • {name} ({date})")
            except:
                pass
            
            # Show agents
            try:
                cursor.execute("SELECT agent_code, agent_name FROM agents")
                agents = cursor.fetchall()
                
                if agents:
                    print(f"\n  👤 Agents:")
                    for code, name in agents:
                        cursor.execute("SELECT COUNT(*) FROM policies WHERE agent_code = ?", (code,))
                        policy_count = cursor.fetchone()[0]
                        print(f"    • {code}: {name} ({policy_count} policies)")
            except:
                pass
            
            # Show policy statistics by agent
            try:
                cursor.execute("""
                    SELECT agent_code, COUNT(*) as policy_count 
                    FROM policies 
                    GROUP BY agent_code 
                    ORDER BY policy_count DESC
                """)
                agent_stats = cursor.fetchall()
                
                if agent_stats:
                    print(f"\n  📈 Policies by Agent:")
                    for agent_code, count in agent_stats:
                        print(f"    • {agent_code}: {count:,} policies")
            except:
                pass
            
            conn.close()
            
        except Exception as e:
            print(f"  ❌ Error reading database: {e}")
    
    print(f"\n" + "=" * 60)
    print("🔍 Need more details? Check individual database files!")

def export_customer_list(db_name="main"):
    """Export customer list to CSV"""
    
    db_paths = {
        "main": get_project_root() / "data" / "lic_customers.db",
        "regex": get_project_root() / "data" / "lic_customers_regex.db", 
        "gemini": get_project_root() / "data" / "lic_customers_gemini.db",
        "dual": get_project_root() / "data" / "lic_customers_dual.db",
    }
    
    db_path = db_paths.get(db_name)
    if not db_path or not db_path.exists():
        print(f"❌ Database '{db_name}' not found")
        return
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Export customer-policy data
        cursor.execute("""
            SELECT 
                c.customer_name,
                p.policy_number,
                p.agent_code,
                p.status,
                c.created_date
            FROM customers c
            JOIN policies p ON c.customer_id = p.customer_id
            ORDER BY c.customer_name, p.policy_number
        """)
        
        results = cursor.fetchall()
        
        if results:
            export_file = get_project_root() / "data" / f"customer_export_{db_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            with open(export_file, 'w', encoding='utf-8') as f:
                # Write header
                f.write("Customer Name,Policy Number,Agent Code,Status,Created Date\n")
                
                # Write data
                for row in results:
                    f.write(f'"{row[0]}","{row[1]}","{row[2]}","{row[3]}","{row[4]}"\n')
            
            print(f"✅ Exported {len(results)} records to: {export_file}")
        else:
            print("❌ No data found to export")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Export error: {e}")

if __name__ == "__main__":
    show_database_stats()
    
    # Uncomment to export customer lists
    # export_customer_list("main")