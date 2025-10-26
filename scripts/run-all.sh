#!/bin/bash
set -e

echo "=========================================="
echo "  K8s Load Testing Pipeline"
echo "=========================================="
echo ""

# Store script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Function to run a script and handle errors
run_step() {
    local step_name=$1
    local script_path=$2

    echo ""
    echo "==================== STEP: $step_name ===================="
    echo ""

    if [ ! -f "$script_path" ]; then
        echo "❌ Error: Script not found: $script_path"
        exit 1
    fi

    chmod +x "$script_path"

    if ! bash "$script_path"; then
        echo ""
        echo "❌ Step failed: $step_name"
        exit 1
    fi

    echo ""
    echo "✅ Step completed: $step_name"
    echo ""
}

# Step 1: Check for existing cluster
run_step "Check KinD Cluster" "$SCRIPT_DIR/check-cluster.sh"

# Step 2: Deploy Istio
run_step "Deploy Istio" "$SCRIPT_DIR/deploy-istio.sh"

# Step 3: Deploy applications
run_step "Deploy Applications" "$SCRIPT_DIR/deploy-apps.sh"

# Step 4: Health checks
run_step "Health Checks" "$SCRIPT_DIR/health-check.sh"

# Step 5: Load testing
echo ""
echo "==================== STEP: Load Testing ===================="
echo ""
chmod +x "$SCRIPT_DIR/load-test.py"
if ! python3 "$SCRIPT_DIR/load-test.py"; then
    echo "❌ Load testing failed"
    exit 1
fi
echo "✅ Step completed: Load Testing"
echo ""

# Step 6: Format results
run_step "Format Results" "$SCRIPT_DIR/format-results.sh"

echo ""
echo "=========================================="
echo "  ✅ ALL STEPS COMPLETED SUCCESSFULLY"
echo "=========================================="
echo ""
echo "📊 Results available in:"
echo "   - loadtest-results.json"
echo "   - loadtest-results.md"
echo "   - github-comment.md"
echo ""