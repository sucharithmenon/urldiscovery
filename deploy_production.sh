#!/bin/bash

# Production Deployment Script for URL Discovery Engine
echo "🚀 URL Discovery Engine - Production Deployment"
echo "=================================================="

# Set environment
export PYTHONPATH="/Users/sucharith/url_discovery_engine:$PYTHONPATH"

# Check if we have the data file
if [ ! -f "production_run/input/production_urls.csv" ]; then
    echo "❌ Input file not found!"
    exit 1
fi

# Count URLs
TOTAL_URLS=$(wc -l < production_run/input/production_urls.csv)
echo "📊 Processing $TOTAL_URLS URLs"
echo "⏱️  Estimated time: $((TOTAL_URLS / 20 / 60)) minutes (at 20 URLs/minute)"

# Run production batch
echo "🔄 Starting production run..."
python3 -m src.cli batch \
    production_run/input/production_urls.csv \
    --output production_run/output/production_validated.csv \
    --unresolved production_run/output/production_unresolved.csv \
    --mode strict \
    --method auto \
    --concurrency 8 \
    --progress

# Check results
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Production run completed successfully!"
    
    # Count results
    VALIDATED=$(grep -c "company_ats_name" production_run/output/production_validated.csv 2>/dev/null || echo "0")
    UNRESOLVED=$(grep -c "input_url" production_run/output/production_unresolved.csv 2>/dev/null || echo "0")
    
    echo "📈 Results Summary:"
    echo "   Validated URLs: $VALIDATED"
    echo "   Unresolved URLs: $UNRESOLVED"
    echo "   Success Rate: $(( VALIDATED * 100 / TOTAL_URLS ))%"
    
    echo ""
    echo "📁 Output files:"
    echo "   Validated: production_run/output/production_validated.csv"
    echo "   Unresolved: production_run/output/production_unresolved.csv"
    
else
    echo "❌ Production run failed!"
    exit 1
fi