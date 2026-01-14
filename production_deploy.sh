#!/bin/bash

# Production Deployment Script
echo "🚀 URL Discovery Engine - Production Deployment"
echo "=================================================="

# Set environment
export PYTHONPATH="/Users/sucharith/url_discovery_engine:$PYTHONPATH"

# Use the clean production data
INPUT_FILE="production_run/input/production_sample.csv"
OUTPUT_FILE="production_run/output/production_validated.csv"
UNRESOLVED_FILE="production_run/output/production_unresolved.csv"

# Check if we have data file
if [ ! -f "$INPUT_FILE" ]; then
    echo "❌ Input file not found!"
    exit 1
fi

# Count URLs
TOTAL_URLS=$(wc -l < "$INPUT_FILE")
echo "📊 Processing $TOTAL_URLS URLs"
echo "⏱️  Estimated time: $((TOTAL_URLS / 20 / 60)) minutes (at 20 URLs/minute)"

# Run production batch
echo "🔄 Starting production run..."
timeout 1800 python3 -m src.cli batch \
    "$INPUT_FILE" \
    --output "$OUTPUT_FILE" \
    --unresolved "$UNRESOLVED_FILE" \
    --mode strict \
    --method auto \
    --concurrency 5 \
    --progress

# Check results
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Production run completed successfully!"
    
    # Count results
    VALIDATED=$(grep -c "company_ats_name" "$OUTPUT_FILE" 2>/dev/null || echo "0")
    UNRESOLVED=$(grep -c "input_url" "$UNRESOLVED_FILE" 2>/dev/null || echo "0")
    
    echo "📈 Results Summary:"
    echo "   Total URLs: $TOTAL_URLS"
    echo "   Validated URLs: $VALIDATED"
    echo "   Unresolved URLs: $UNRESOLVED"
    
    if [ "$TOTAL_URLS" -gt 0 ]; then
        SUCCESS_RATE=$((VALIDATED * 100 / TOTAL_URLS))
        echo "   Success Rate: ${SUCCESS_RATE}%"
    fi
    
    echo ""
    echo "📁 Output files:"
    echo "   Validated: $OUTPUT_FILE"
    echo "   Unresolved: $UNRESOLVED_FILE"
    
else
    echo "❌ Production run failed!"
    exit 1
fi