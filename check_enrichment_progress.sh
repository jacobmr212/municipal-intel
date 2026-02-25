#!/bin/bash
# Quick script to check nationwide enrichment progress

echo "=================================="
echo "NATIONWIDE ENRICHMENT PROGRESS"
echo "=================================="
echo ""

# Check if process is running
if pgrep -f "batch_enrich.py --all" > /dev/null; then
    PID=$(pgrep -f "batch_enrich.py --all")
    echo "✅ Status: RUNNING (PID: $PID)"
    echo ""

    # Show last 30 lines of log
    echo "Recent Activity:"
    echo "----------------"
    tail -30 enrichment_nationwide.log | grep -E "(ENRICHMENT:|Enriching|✓|✗|completed)"
    echo ""

    # Count progress from log
    echo "Statistics:"
    echo "----------------"
    VERIFIED=$(grep -c "✓ Domain verified" enrichment_nationwide.log)
    DEAD=$(grep -c "✗ Domain dead" enrichment_nationwide.log)
    SOURCES=$(grep -c "✓ Source found" enrichment_nationwide.log)

    echo "Domains Verified: $VERIFIED"
    echo "Domains Dead: $DEAD"
    echo "Sources Found: $SOURCES"
    echo ""

    # Show which states are being processed
    echo "Currently Processing:"
    echo "--------------------"
    tail -100 enrichment_nationwide.log | grep "ENRICHMENT:" | tail -8

else
    echo "❌ Status: NOT RUNNING"
    echo ""
    echo "Check if it completed or crashed:"
    tail -50 enrichment_nationwide.log
fi

echo ""
echo "=================================="
echo "Full log: enrichment_nationwide.log"
echo "=================================="
