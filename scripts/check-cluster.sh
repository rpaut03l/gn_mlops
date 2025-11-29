#!/bin/bash
set -e

CLUSTER_NAME="devops-test"
REQUIRED_NODES=3  # 1 control plane + 2 workers

echo "=== Checking for existing KinD cluster ==="

# Check if kind is installed
if ! command -v kind &> /dev/null; then
    echo "❌ Error: kind is not installed"
    exit 1
fi

# Check if kubectl is installed
if ! command -v kubectl &> /dev/null; then
    echo "❌ Error: kubectl is not installed"
    exit 1
fi

# Check if cluster exists
if ! kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    echo "❌ Error: KinD cluster '${CLUSTER_NAME}' does not exist"
    echo "Please create the cluster first using: kind create cluster --config k8s/kind-config.yaml"
    exit 1
fi

echo "✅ KinD cluster '${CLUSTER_NAME}' found"

# Set kubectl context
kubectl config use-context "kind-${CLUSTER_NAME}" > /dev/null 2>&1

# Check cluster connectivity
if ! kubectl cluster-info > /dev/null 2>&1; then
    echo "❌ Error: Cannot connect to cluster"
    exit 1
fi

echo "✅ Successfully connected to cluster"

# Check number of nodes
NODE_COUNT=$(kubectl get nodes --no-headers | wc -l)
if [ "$NODE_COUNT" -lt "$REQUIRED_NODES" ]; then
    echo "❌ Error: Expected at least ${REQUIRED_NODES} nodes, found ${NODE_COUNT}"
    kubectl get nodes
    exit 1
fi

echo "✅ Found ${NODE_COUNT} nodes (required: ${REQUIRED_NODES})"

# Display node information
echo ""
echo "=== Cluster Nodes ==="
kubectl get nodes -o wide

# Check if nodes are ready
NOT_READY=$(kubectl get nodes --no-headers | grep -v " Ready " | wc -l)
if [ "$NOT_READY" -gt 0 ]; then
    echo "❌ Error: ${NOT_READY} node(s) are not ready"
    kubectl get nodes
    exit 1
fi

echo "✅ All nodes are ready"
echo ""
echo "=== Cluster validation complete ==="