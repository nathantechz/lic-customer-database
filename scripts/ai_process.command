#!/bin/bash
cd "$(dirname "$0")/.."

# Activate virtual environment
if [ -f ".venv/bin/activate" ]; then
    echo "🐍 Activating virtual environment..."
    source .venv/bin/activate
fi

# Install Gemini AI if needed
echo "📦 Installing Gemini AI..."
pip install google-generativeai

echo "🚀 Starting AI-Powered PDF Processing..."
echo ""
echo "This will use Gemini 2.5 Pro to extract customer names intelligently"
echo ""

# Check if API key exists
if [ ! -f "config/gemini_api_key.txt" ]; then
    echo "🔧 Setting up Gemini API key first..."
    python3 config/setup_gemini.py
    echo ""
fi

cd scripts
python3 gemini_pdf_processor.py
echo ""
echo "Press any key to continue..."
read -n 1 -s
