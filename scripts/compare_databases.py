import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime
import difflib

def get_project_root():
    """Get the project root directory"""
    return Path(__file__).parent.parent

def get_database_stats(db_path, extraction_method):
    """Get statistics from a database"""
    if not db_path.exists():
        return {"exists": False, "customers": 0, "policies": 0, "real_names": 0, "generic_names": 0}
    
    conn = sqlite3.connect(str(db_path))
    try:
        customer_count = conn.execute('SELECT COUNT(*) FROM customers').fetchone()[0]
        policy_count = conn.execute('SELECT COUNT(*) FROM policies').fetchone()[0]
        generic_names = conn.execute("SELECT COUNT(*) FROM customers WHERE customer_name LIKE 'Customer_%'").fetchone()[0]
        real_names = customer_count - generic_names
        
        return {
            "exists": True,
            "customers": customer_count,
            "policies": policy_count,
            "real_names": real_names,
            "generic_names": generic_names,
            "real_name_percentage": (real_names / customer_count * 100) if customer_count > 0 else 0
        }
    finally:
        conn.close()

def compare_customer_names(gemini_db, regex_db):
    """Compare customer name extraction quality between databases"""
    print("\n🔍 === CUSTOMER NAME COMPARISON ===")
    
    results = {
        "gemini_only": [],
        "regex_only": [],
        "both_same": [],
        "both_different": [],
        "quality_scores": {"gemini": 0, "regex": 0}
    }
    
    # Get all customers from both databases
    gemini_conn = sqlite3.connect(str(gemini_db))
    regex_conn = sqlite3.connect(str(regex_db))
    
    try:
        # Get Gemini customers
        gemini_customers = {}
        gemini_cursor = gemini_conn.execute('''
            SELECT p.policy_number, c.customer_name 
            FROM customers c 
            JOIN policies p ON c.customer_id = p.customer_id
        ''')
        for policy, name in gemini_cursor.fetchall():
            gemini_customers[policy] = name
        
        # Get Regex customers
        regex_customers = {}
        regex_cursor = regex_conn.execute('''
            SELECT p.policy_number, c.customer_name 
            FROM customers c 
            JOIN policies p ON c.customer_id = p.customer_id
        ''')
        for policy, name in regex_cursor.fetchall():
            regex_customers[policy] = name
        
        # Compare policies
        all_policies = set(gemini_customers.keys()) | set(regex_customers.keys())
        
        for policy in all_policies:
            gemini_name = gemini_customers.get(policy)
            regex_name = regex_customers.get(policy)
            
            if gemini_name and regex_name:
                if gemini_name == regex_name:
                    results["both_same"].append({
                        "policy": policy,
                        "name": gemini_name
                    })
                else:
                    similarity = difflib.SequenceMatcher(None, gemini_name, regex_name).ratio()
                    results["both_different"].append({
                        "policy": policy,
                        "gemini_name": gemini_name,
                        "regex_name": regex_name,
                        "similarity": similarity
                    })
            elif gemini_name:
                results["gemini_only"].append({
                    "policy": policy,
                    "name": gemini_name
                })
            elif regex_name:
                results["regex_only"].append({
                    "policy": policy,
                    "name": regex_name
                })
        
        # Calculate quality scores
        gemini_real = sum(1 for name in gemini_customers.values() if not name.startswith('Customer_'))
        regex_real = sum(1 for name in regex_customers.values() if not name.startswith('Customer_'))
        
        results["quality_scores"]["gemini"] = (gemini_real / len(gemini_customers) * 100) if gemini_customers else 0
        results["quality_scores"]["regex"] = (regex_real / len(regex_customers) * 100) if regex_customers else 0
        
        # Print comparison results
        print(f"📊 Policies in Gemini DB only: {len(results['gemini_only'])}")
        print(f"📊 Policies in Regex DB only: {len(results['regex_only'])}")
        print(f"📊 Policies in both (same name): {len(results['both_same'])}")
        print(f"📊 Policies in both (different names): {len(results['both_different'])}")
        print(f"🎯 Gemini real name percentage: {results['quality_scores']['gemini']:.1f}%")
        print(f"🎯 Regex real name percentage: {results['quality_scores']['regex']:.1f}%")
        
        return results
        
    finally:
        gemini_conn.close()
        regex_conn.close()

def create_merged_database(gemini_db, regex_db, final_db):
    """Create final merged database with best data from both sources"""
    print(f"\n🔧 === CREATING MERGED DATABASE ===")
    
    # Create final database
    from database_setup import create_database_at_path
    create_database_at_path(final_db)
    
    final_conn = sqlite3.connect(str(final_db))
    final_cursor = final_conn.cursor()
    
    gemini_conn = sqlite3.connect(str(gemini_db))
    regex_conn = sqlite3.connect(str(regex_db))
    
    try:
        merged_stats = {"customers": 0, "policies": 0, "gemini_preferred": 0, "regex_preferred": 0}
        
        # Get all unique policies from both databases
        all_policies = set()
        
        # Collect from Gemini
        gemini_data = {}
        if gemini_db.exists():
            gemini_cursor = gemini_conn.execute('''
                SELECT p.policy_number, c.customer_name, p.agent_code, c.customer_id
                FROM customers c 
                JOIN policies p ON c.customer_id = p.customer_id
            ''')
            for policy, name, agent, customer_id in gemini_cursor.fetchall():
                gemini_data[policy] = {
                    "name": name,
                    "agent_code": agent,
                    "is_real_name": not name.startswith('Customer_'),
                    "source": "gemini"
                }
                all_policies.add(policy)
        
        # Collect from Regex
        regex_data = {}
        if regex_db.exists():
            regex_cursor = regex_conn.execute('''
                SELECT p.policy_number, c.customer_name, p.agent_code, c.customer_id
                FROM customers c 
                JOIN policies p ON c.customer_id = p.customer_id
            ''')
            for policy, name, agent, customer_id in regex_cursor.fetchall():
                regex_data[policy] = {
                    "name": name,
                    "agent_code": agent,
                    "is_real_name": not name.startswith('Customer_'),
                    "source": "regex"
                }
                all_policies.add(policy)
        
        print(f"📋 Processing {len(all_policies)} unique policies...")
        
        # Merge logic: prefer real names, then Gemini, then Regex
        for policy in all_policies:
            gemini_entry = gemini_data.get(policy)
            regex_entry = regex_data.get(policy)
            
            # Decide which entry to use
            chosen_entry = None
            chosen_source = None
            
            if gemini_entry and regex_entry:
                # Both have the policy
                if gemini_entry["is_real_name"] and not regex_entry["is_real_name"]:
                    chosen_entry = gemini_entry
                    chosen_source = "gemini"
                    merged_stats["gemini_preferred"] += 1
                elif regex_entry["is_real_name"] and not gemini_entry["is_real_name"]:
                    chosen_entry = regex_entry
                    chosen_source = "regex"
                    merged_stats["regex_preferred"] += 1
                elif gemini_entry["is_real_name"] and regex_entry["is_real_name"]:
                    # Both have real names, prefer longer name
                    if len(gemini_entry["name"]) >= len(regex_entry["name"]):
                        chosen_entry = gemini_entry
                        chosen_source = "gemini"
                        merged_stats["gemini_preferred"] += 1
                    else:
                        chosen_entry = regex_entry
                        chosen_source = "regex"
                        merged_stats["regex_preferred"] += 1
                else:
                    # Both generic, prefer Gemini
                    chosen_entry = gemini_entry
                    chosen_source = "gemini"
                    merged_stats["gemini_preferred"] += 1
            
            elif gemini_entry:
                chosen_entry = gemini_entry
                chosen_source = "gemini"
                merged_stats["gemini_preferred"] += 1
            
            elif regex_entry:
                chosen_entry = regex_entry
                chosen_source = "regex"
                merged_stats["regex_preferred"] += 1
            
            # Insert into final database
            if chosen_entry:
                # Insert customer
                final_cursor.execute('''
                    INSERT INTO customers (customer_name, extraction_method) 
                    VALUES (?, ?)
                ''', (chosen_entry["name"], chosen_source))
                customer_id = final_cursor.lastrowid
                merged_stats["customers"] += 1
                
                # Insert policy
                final_cursor.execute('''
                    INSERT INTO policies (policy_number, customer_id, agent_code, status, extraction_method)
                    VALUES (?, ?, ?, ?, ?)
                ''', (policy, customer_id, chosen_entry["agent_code"], 'Active', chosen_source))
                merged_stats["policies"] += 1
        
        final_conn.commit()
        
        print(f"✅ Merged database created successfully!")
        print(f"📊 Total customers: {merged_stats['customers']}")
        print(f"📊 Total policies: {merged_stats['policies']}")
        print(f"🤖 Preferred Gemini entries: {merged_stats['gemini_preferred']}")
        print(f"📝 Preferred Regex entries: {merged_stats['regex_preferred']}")
        print(f"💾 Final database: {final_db}")
        
        return merged_stats
        
    finally:
        gemini_conn.close()
        regex_conn.close()
        final_conn.close()

def generate_comparison_report(gemini_db, regex_db, final_db):
    """Generate comprehensive comparison report"""
    print("\n📊 === GENERATING COMPARISON REPORT ===")
    
    # Get stats from all databases
    gemini_stats = get_database_stats(gemini_db, "gemini")
    regex_stats = get_database_stats(regex_db, "regex")
    final_stats = get_database_stats(final_db, "final")
    
    # Compare customer names
    comparison_results = compare_customer_names(gemini_db, regex_db)
    
    # Create report
    report_path = get_project_root() / "data" / "database_comparison_report.txt"
    
    with open(report_path, 'w') as f:
        f.write("LIC DATABASE COMPARISON REPORT\n")
        f.write("=" * 50 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("DATABASE STATISTICS:\n")
        f.write("-" * 20 + "\n")
        f.write(f"Gemini AI Database:\n")
        f.write(f"  - Customers: {gemini_stats['customers']}\n")
        f.write(f"  - Policies: {gemini_stats['policies']}\n")
        f.write(f"  - Real Names: {gemini_stats['real_names']} ({gemini_stats['real_name_percentage']:.1f}%)\n")
        f.write(f"  - Generic Names: {gemini_stats['generic_names']}\n\n")
        
        f.write(f"Regex Pattern Database:\n")
        f.write(f"  - Customers: {regex_stats['customers']}\n")
        f.write(f"  - Policies: {regex_stats['policies']}\n")
        f.write(f"  - Real Names: {regex_stats['real_names']} ({regex_stats['real_name_percentage']:.1f}%)\n")
        f.write(f"  - Generic Names: {regex_stats['generic_names']}\n\n")
        
        f.write(f"Final Merged Database:\n")
        f.write(f"  - Customers: {final_stats['customers']}\n")
        f.write(f"  - Policies: {final_stats['policies']}\n")
        f.write(f"  - Real Names: {final_stats['real_names']} ({final_stats['real_name_percentage']:.1f}%)\n")
        f.write(f"  - Generic Names: {final_stats['generic_names']}\n\n")
        
        f.write("EXTRACTION QUALITY COMPARISON:\n")
        f.write("-" * 30 + "\n")
        f.write(f"Gemini AI Quality Score: {comparison_results['quality_scores']['gemini']:.1f}%\n")
        f.write(f"Regex Pattern Quality Score: {comparison_results['quality_scores']['regex']:.1f}%\n\n")
        
        f.write("POLICY OVERLAP ANALYSIS:\n")
        f.write("-" * 25 + "\n")
        f.write(f"Policies only in Gemini DB: {len(comparison_results['gemini_only'])}\n")
        f.write(f"Policies only in Regex DB: {len(comparison_results['regex_only'])}\n")
        f.write(f"Policies in both (same name): {len(comparison_results['both_same'])}\n")
        f.write(f"Policies in both (different names): {len(comparison_results['both_different'])}\n")
    
    print(f"📝 Comparison report saved to: {report_path}")
    return report_path

def main():
    """Main comparison function"""
    print("🔄 === DATABASE COMPARISON AND MERGER ===")
    
    project_root = get_project_root()
    gemini_db = project_root / "data" / "lic_customers_gemini.db"
    regex_db = project_root / "data" / "lic_customers_regex.db"
    final_db = project_root / "data" / "lic_customers.db"  # This is what Streamlit will use
    
    print(f"📁 Gemini DB: {gemini_db}")
    print(f"📁 Regex DB: {regex_db}")
    print(f"📁 Final DB: {final_db}")
    
    # Check if source databases exist
    if not gemini_db.exists() and not regex_db.exists():
        print("❌ No source databases found!")
        print("Please run gemini_pdf_processor.py and/or pdf_processor.py first")
        return
    
    # Generate comparison and create merged database
    merged_stats = create_merged_database(gemini_db, regex_db, final_db)
    
    # Generate comprehensive report
    report_path = generate_comparison_report(gemini_db, regex_db, final_db)
    
    print(f"\n🎉 === COMPLETION SUMMARY ===")
    print(f"✅ Final database created for Streamlit: {final_db}")
    print(f"📊 Comparison report: {report_path}")
    print(f"🚀 You can now run the Streamlit app!")

if __name__ == "__main__":
    main()
