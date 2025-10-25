#!/bin/bash
cd "$(dirname "$0")/.."

# Activate virtual environment if it exists
if [ -f ".venv/bin/activate" ]; then
    echo "🐍 Activating virtual environment..."
    source .venv/bin/activate
fi

cd scripts
echo "🚀 Starting LIC Search Application with Streamlit..."
echo ""
echo "📱 Streamlit will open automatically in your browser"
echo "   If not, go to: http://localhost:8501"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""
streamlit run search_app.py --server.port 8501 --server.headless false
echo ""
python3 search_app.py
