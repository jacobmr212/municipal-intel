#!/bin/bash
cd ~/Desktop/municipal-intel
source venv/bin/activate
echo "======================================"
echo "Municipal Intel - Starting..."
echo "======================================"
echo ""
echo "App will open at: http://localhost:8501"
echo ""
echo "To share on your local network:"
echo "1. Find your IP: ifconfig | grep 'inet '"
echo "2. Share: http://YOUR-IP:8501"
echo ""
echo "Press Ctrl+C to stop"
echo "======================================"
streamlit run app.py --server.address=0.0.0.0
