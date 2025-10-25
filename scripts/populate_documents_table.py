#!/usr/bin/env python3
"""
Populate documents table with existing processed files
"""

import sqlite3
import re
import pdfplumber
import hashlib
from pathlib import Path
from datetime import datetime

def get_project_root():
    """Get the project root directory"""
    return Path(__file__).parent.parent

def extract_policy_numbers_from_filename(filename):
    """Extract policy numbers from filename"""
    policy_numbers = []
    
    # Pattern for policy numbers (usually 9-10 digits)
    policy_pattern = r'\b\d{9,10}\b'
    matches = re.findall(policy_pattern, filename)
    
    if matches:
        policy_numbers.extend(matches)
    
    return policy_numbers

def extract_content_hash(file_path):
    """Extract a content hash from PDF for duplicate detection"""
    try:
        with pdfplumber.open(file_path) as pdf:
            # Extract text from first page (usually contains unique identifiers)
            first_page_text = ""
            if pdf.pages:
                first_page_text = pdf.pages[0].extract_text() or ""
            
            # Create hash from first 1000 characters (contains dates, policy numbers, etc.)
            content_sample = first_page_text[:1000].strip()
            content_hash = hashlib.md5(content_sample.encode()).hexdigest()
            
            return content_hash, content_sample[:200]  # Return hash and sample for logging
            
    except Exception as e:
        print(f"  ⚠️ Error extracting content hash from {file_path.name}: {e}")
        return None, None

def populate_documents_table():
    """Populate documents table with existing processed files"""
    print("📝 Populating Documents Table with Existing Files")
    print("=" * 55)
    
    project_root = get_project_root()
    processed_path = project_root / "data" / "pdfs" / "processed"
    db_path = project_root / "data" / "lic_customers.db"
    
    if not processed_path.exists():
        print("❌ Processed folder not found!")
        return
    
    if not db_path.exists():
        print("❌ Database not found!")
        return
    
    processed_files = list(processed_path.glob("*.pdf"))
    
    if not processed_files:
        print("📄 No processed files found")
        return
    
    print(f"📂 Found {len(processed_files)} processed files")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        added_count = 0
        
        for pdf_file in processed_files:
            filename = pdf_file.name
            file_path = str(pdf_file)
            
            # Determine document type from filename
            document_type = "Unknown"
            if "CM-" in filename or "Commission" in filename:
                document_type = "Commission"
            elif "CLAIM" in filename.upper() or "Claims" in filename:
                document_type = "Claims"  
            elif "PREMDUE" in filename.upper() or "Premium" in filename:
                document_type = "Premium Due"
            
            # Extract content hash for duplicate detection
            content_hash, content_sample = extract_content_hash(pdf_file)
            
            # Extract policy numbers from filename
            policy_numbers = extract_policy_numbers_from_filename(filename)
            
            # Add single entry per file (not per policy number)
            cursor.execute("""
                INSERT OR REPLACE INTO documents 
                (policy_number, document_type, file_name, file_path, content_hash, processed_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (None, document_type, filename, file_path, content_hash, datetime.now()))
            added_count += 1
            
            hash_display = content_hash[:8] if content_hash else "N/A"
            sample_display = content_sample[:50] if content_sample else "N/A"
            print(f"  ✅ {filename} → {document_type} (hash: {hash_display}...)")
            if content_sample and "claims" in document_type.lower():
                print(f"      Content: {sample_display}...")
        
        conn.commit()
        print(f"\n🎉 Successfully added {added_count} document entries")
        
        # Show final count
        cursor.execute("SELECT COUNT(*) FROM documents")
        total_docs = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT file_name) FROM documents")
        unique_files = cursor.fetchone()[0]
        
        print(f"📊 Final statistics:")
        print(f"  📄 Total document entries: {total_docs}")
        print(f"  📁 Unique files tracked: {unique_files}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    populate_documents_table()
    print("\n💡 Now duplicate detection will work for existing files!")
    print("🧪 Run test_duplicate_detection.py again to verify")