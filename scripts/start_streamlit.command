#!/bin/bash
cd "$(dirname "$0")/.."

echo "🚀 Starting LIC Streamlit Application..."
echo "📍 Working directory: $(pwd)"

# Check if we're in the right directory
if [ ! -f "setup.command" ]; then
    echo "❌ Error: Not in LIC database directory"
    echo "   Expected to find setup.command file"
    echo "   Please run this from the main LIC database folder"
    echo ""
    echo "Press any key to exit..."
    read -n 1 -s
    exit 1
fi

# Activate virtual environment if it exists
if [ -f ".venv/bin/activate" ]; then
    echo "🐍 Activating virtual environment..."
    source .venv/bin/activate
    echo "✅ Virtual environment activated"
else
    echo "⚠️  No virtual environment found"
    echo "   You may need to run setup.command first"
fi

# Check if Streamlit is installed
if ! command -v streamlit &> /dev/null; then
    echo "❌ Streamlit not found!"
    echo "   Installing Streamlit..."
    pip install streamlit
fi

# Check if database exists
if [ -f "data/lic_customers.db" ]; then
    echo "✅ Database found"
else
    echo "❌ Database not found"
    echo "   The app will show setup instructions"
fi

# Check if streamlit_app.py exists
if [ ! -f "scripts/streamlit_app.py" ]; then
    echo "❌ streamlit_app.py not found!"
    echo "   Please ensure all files are properly set up"
    echo ""
    echo "Press any key to exit..."
    read -n 1 -s
    exit 1
fi

cd scripts
echo ""
echo "📱 The app will open in your default browser"
echo "🌐 Or manually go to: http://localhost:8501"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""
streamlit run streamlit_app.py
