#!/bin/bash

# Toy Seller Site - Quick Start Script

echo "🎉 Toy Seller Site Setup"
echo "========================"
echo ""

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
    echo ""
fi

# Activate venv
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "🚀 Starting server..."
echo "   Admin: http://localhost:5001/admin"
echo "   Public: http://localhost:5001"
echo ""
echo "   Default login: admin / admin123"
echo ""

# Run the app
python3 app.py
