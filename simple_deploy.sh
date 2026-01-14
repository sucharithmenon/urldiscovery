#!/bin/bash

# Simple Production Deployment
echo "🚀 URL Discovery Engine - Simple Production Run"
echo "=================================================="

# Create a very small test first
echo "🧪 Creating small test with 5 URLs..."
head -5 production_run/input/production_urls.csv > production_run/input/tiny_test.csv

echo "📊 Processing 5 test URLs..."

# Run with basic settings
export PYTHONPATH="/Users/sucharith/url_discovery_engine:$PYTHONPATH"

python3 -m src.cli batch \
    production_run/input/tiny_test.csv \
    --output production_run/output/tiny_test_validated.csv \
    --unresolved production_run/output/tiny_test_unresolved.csv \
    --mode strict \
    --method auto \
    --concurrency 1 \
    --progress

echo ""
echo "✅ Test run completed!"
echo "📁 Check results:"
echo "   Validated: production_run/output/tiny_test_validated.csv"  
echo "   Unresolved: production_run/output/tiny_test_unresolved.csv"

# Show sample results if files exist
if [ -f "production_run/output/tiny_test_validated.csv" ]; then
    echo ""
    echo "🎯 Sample validated results:"
    head -3 production_run/output/tiny_test_validated.csv
fi

if [ -f "production_run/output/tiny_test_unresolved.csv" ]; then
    echo ""
    echo "❌ Sample unresolved results:"
    head -3 production_run/output/tiny_test_unresolved.csv
fi