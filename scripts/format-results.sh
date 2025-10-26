#!/bin/bash
set -e

# Check if results file exists
if [ ! -f "loadtest-results.md" ]; then
    echo "❌ Error: loadtest-results.md not found"
    exit 1
fi

# Read the markdown results
RESULTS=$(cat loadtest-results.md)

# Create GitHub comment body
cat > github-comment.md << 'EOF'
## 🚀 Load Test Results

EOF

# Append the results
cat loadtest-results.md >> github-comment.md

# Add footer
cat >> github-comment.md << 'EOF'

---
*Generated automatically by CI workflow*
EOF

echo "✅ GitHub comment formatted and saved to: github-comment.md"

# Display preview
echo ""
echo "=== Comment Preview ==="
cat github-comment.md
echo ""
echo "======================"