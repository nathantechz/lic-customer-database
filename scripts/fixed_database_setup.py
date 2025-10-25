import sqlite3
import os
import json
from pathlib import Path
from datetime import datetime

def get_project_root():
    """Get the project root directory (LIC_Database folder in Dropbox)"""
    return Path(__file__).parent.parent

def create_database():
    """Create the SQLite database with all tables"""
    
    db_path = get_project_root() / "data" / "lic_customers.db"
    
    # Create data directory if it doesn't exist
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"📍 Creating database at: {db_path}")
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Customers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            phone_number TEXT,
            alt_phone_number TEXT,
            email TEXT,
            aadhaar_number TEXT,
            date_of_birth TEXT,
            occupation TEXT,
            full_address TEXT,
            google_maps_link TEXT,
            customer_photo_path TEXT,
            aadhaar_image_path TEXT,
            notes TEXT,
            extraction_method TEXT DEFAULT 'unknown',
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Enhanced Policies table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS policies (
            policy_number TEXT PRIMARY KEY,
            customer_id INTEGER,
            agent_code TEXT,
            agent_name TEXT,
            plan_type TEXT,
            plan_name TEXT,
            date_of_commencement TEXT,
            premium_mode TEXT,
            current_fup_date TEXT,
            sum_assured REAL,
            premium_amount REAL,
            status TEXT DEFAULT 'Active',
            maturity_date TEXT,
            policy_term INTEGER,
            premium_paying_term INTEGER,
            extraction_method TEXT DEFAULT 'unknown',
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
        )
    ''')
    
    # Premium records table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS premium_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            policy_number TEXT,
            due_date TEXT,
            premium_amount REAL,
            gst_amount REAL,
            total_amount REAL,
            estimated_commission REAL,
            status TEXT DEFAULT 'Due',
            agent_code TEXT,
            processed_date TEXT,
            source_pdf TEXT,
            payment_date TEXT,
            payment_notes TEXT,
            updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (policy_number) REFERENCES policies (policy_number)
        )
    ''')
    
    # Agents table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agents (
            agent_code TEXT PRIMARY KEY,
            agent_name TEXT,
            branch_code TEXT,
            relationship TEXT,
            phone TEXT,
            email TEXT,
            active BOOLEAN DEFAULT 1
        )
    ''')
    
    # Documents table for PDF tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            policy_number TEXT,
            document_type TEXT,
            file_name TEXT,
            file_path TEXT,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (policy_number) REFERENCES policies (policy_number)
        )
    ''')
    
    # Insert default agents (we know these from the PDFs)
    default_agents = [
        ('0089174N', 'M. NAGANATHAN', '74N', 'son', '', '', True),
        ('0163674N', 'A. MUTHURAMALINGAM', '74N', 'self', '', '', True),
        ('0009274N', 'V. POTHUMPEN', '74N', 'nephew', '', '', True),
    ]
    
    cursor.executemany('''
        INSERT OR IGNORE INTO agents 
        (agent_code, agent_name, branch_code, relationship, phone, email, active)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', default_agents)
    
    print(f"✓ Loaded {len(default_agents)} default agents")
    
    # Try to load additional agents from config if available
    config_path = get_project_root() / "config" / "agents.json"
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                
            agents_data = []
            agents_list = config.get('agents', [])
            
            # Handle list format from the JSON
            if isinstance(agents_list, list):
                for agent_info in agents_list:
                    agent_code = agent_info.get('agent_code', '')
                    if agent_code and agent_code not in ['0089174N', '0163674N', '0009274N']:  # Don't duplicate defaults
                        agents_data.append((
                            agent_code,
                            agent_info.get('agent_name', ''),
                            agent_info.get('branch', ''),
                            agent_info.get('relationship', ''),
                            agent_info.get('phone', ''),
                            agent_info.get('email', ''),
                            agent_info.get('active', True)
                        ))
            
            if agents_data:
                cursor.executemany('''
                    INSERT OR IGNORE INTO agents 
                    (agent_code, agent_name, branch_code, relationship, phone, email, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', agents_data)
                
                print(f"✓ Loaded {len(agents_data)} additional agents from config")
            
        except Exception as e:
            print(f"⚠️  Could not load additional agents from config: {e}")
    
    conn.commit()
    conn.close()
    
    print(f"✅ Database created successfully at: {db_path}")
    
    # Verify database was created and show table info
    if db_path.exists():
        file_size = db_path.stat().st_size
        print(f"✓ Database file exists and is {file_size} bytes")
        
        # Show table counts
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"✓ Created {len(tables)} tables: {', '.join([t[0] for t in tables])}")
        
        cursor.execute("SELECT COUNT(*) FROM agents")
        agent_count = cursor.fetchone()[0]
        print(f"✓ Initialized {agent_count} agents")
        
        conn.close()
    else:
        print("✗ Database file was not created!")
        return False
    
    return str(db_path)

def create_database_at_path(db_path):
    """Create the SQLite database at specified path"""
    
    # Create data directory if it doesn't exist
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"📍 Creating database at: {db_path}")
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Customers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            phone_number TEXT,
            alt_phone_number TEXT,
            email TEXT,
            aadhaar_number TEXT,
            date_of_birth TEXT,
            occupation TEXT,
            full_address TEXT,
            google_maps_link TEXT,
            customer_photo_path TEXT,
            aadhaar_image_path TEXT,
            notes TEXT,
            extraction_method TEXT DEFAULT 'unknown',
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Enhanced Policies table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS policies (
            policy_number TEXT PRIMARY KEY,
            customer_id INTEGER,
            agent_code TEXT,
            agent_name TEXT,
            plan_type TEXT,
            plan_name TEXT,
            date_of_commencement TEXT,
            premium_mode TEXT,
            current_fup_date TEXT,
            sum_assured REAL,
            premium_amount REAL,
            status TEXT DEFAULT 'Active',
            maturity_date TEXT,
            policy_term INTEGER,
            premium_paying_term INTEGER,
            extraction_method TEXT DEFAULT 'unknown',
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
        )
    ''')
    
    # Premium records table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS premium_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            policy_number TEXT,
            due_date TEXT,
            premium_amount REAL,
            gst_amount REAL,
            total_amount REAL,
            estimated_commission REAL,
            status TEXT DEFAULT 'Due',
            agent_code TEXT,
            processed_date TEXT,
            source_pdf TEXT,
            payment_date TEXT,
            payment_notes TEXT,
            updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (policy_number) REFERENCES policies (policy_number)
        )
    ''')
    
    # Agents table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agents (
            agent_code TEXT PRIMARY KEY,
            agent_name TEXT,
            branch_code TEXT,
            relationship TEXT,
            phone TEXT,
            email TEXT,
            active BOOLEAN DEFAULT 1
        )
    ''')
    
    # Documents table for PDF tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            policy_number TEXT,
            document_type TEXT,
            file_name TEXT,
            file_path TEXT,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (policy_number) REFERENCES policies (policy_number)
        )
    ''')
    
    # Insert default agents
    default_agents = [
        ('0089174N', 'M. NAGANATHAN', '74N', 'son', '', '', True),
        ('0163674N', 'A. MUTHURAMALINGAM', '74N', 'self', '', '', True),
        ('0009274N', 'V. POTHUMPEN', '74N', 'nephew', '', '', True),
    ]
    
    cursor.executemany('''
        INSERT OR IGNORE INTO agents 
        (agent_code, agent_name, branch_code, relationship, phone, email, active)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', default_agents)
    
    print(f"✓ Loaded {len(default_agents)} default agents")
    
    conn.commit()
    conn.close()
    
    print(f"✅ Database created successfully at: {db_path}")
    return str(db_path)

def show_database_info(db_path=None):
    """Show information about the database"""
    if db_path is None:
        db_path = get_project_root() / "data" / "lic_customers.db"
    
    if not Path(db_path).exists():
        print(f"❌ Database not found at: {db_path}")
        return
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    print(f"\n📊 Database Information: {db_path}")
    print("=" * 60)
    
    # Show table info
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    for table in tables:
        table_name = table[0]
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f"📋 {table_name}: {count} records")
    
    # Show recent customers
    cursor.execute("SELECT customer_name, extraction_method FROM customers ORDER BY created_date DESC LIMIT 5")
    recent_customers = cursor.fetchall()
    
    if recent_customers:
        print(f"\n👥 Recent Customers:")
        for customer, method in recent_customers:
            print(f"  • {customer} ({method})")
    
    # Show agents
    cursor.execute("SELECT agent_code, agent_name FROM agents WHERE active = 1")
    agents = cursor.fetchall()
    
    if agents:
        print(f"\n👤 Active Agents:")
        for code, name in agents:
            print(f"  • {code}: {name}")
    
    conn.close()

def backup_database():
    """Create a backup of the current database"""
    source_db = get_project_root() / "data" / "lic_customers.db"
    backup_dir = get_project_root() / "data" / "backups"
    
    if not source_db.exists():
        print("❌ No database found to backup")
        return
    
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"lic_customers_{timestamp}.db"
    
    import shutil
    shutil.copy2(source_db, backup_file)
    
    print(f"✅ Database backed up to: {backup_file}")
    return str(backup_file)

if __name__ == "__main__":
    create_database()
    show_database_info()