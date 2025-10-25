from pathlib import Path

def setup_gemini_key():
    """Setup Gemini API key"""
    config_dir = Path(__file__).parent
    key_file = config_dir / "gemini_api_key.txt"
    
    config_dir.mkdir(exist_ok=True)
    
    print("🤖 Setting up Gemini 2.5 Pro API")
    print("\nTo get your API key:")
    print("1. Go to: https://aistudio.google.com/app/apikey")
    print("2. Create a new API key")
    print("3. Copy the key")
    
    if key_file.exists():
        print(f"\n✅ API key file already exists: {key_file}")
        response = input("Replace existing key? (y/N): ")
        if response.lower() != 'y':
            return
    
    api_key = input("\nPaste your Gemini API key: ").strip()
    
    if not api_key:
        print("❌ No API key provided")
        return
    
    try:
        with open(key_file, 'w') as f:
            f.write(api_key)
        
        print(f"✅ API key saved to: {key_file}")
        print("\nNow you can run the AI-powered PDF processor:")
        print("python3 scripts/gemini_pdf_processor.py")
        
    except Exception as e:
        print(f"❌ Error saving API key: {e}")

if __name__ == "__main__":
    setup_gemini_key()
