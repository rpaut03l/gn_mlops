#!/bin/bash
set -e

ISTIO_VERSION="1.20.0"

echo "=== Deploying Istio Service Mesh ==="

# Check if istioctl is available
if ! command -v istioctl &> /dev/null; then
    echo "⬇️  Downloading istioctl..."
    curl -L https://istio.io/downloadIstio | ISTIO_VERSION=${ISTIO_VERSION} sh -
    export PATH=$PWD/istio-${ISTIO_VERSION}/bin:$PATH
fi

echo "✅ istioctl version: $(istioctl version --short --remote=false)"

# Check if Istio is already installed
if kubectl get namespace istio-system &> /dev/null; then
    echo "⚠️  Istio namespace already exists, checking installation..."
    if kubectl get deployment -n istio-system istiod &> /dev/null; then
        echo "✅ Istio is already installed"
        return 0
    fi
fi

# Install Istio with demo profile (suitable for testing)
echo "📦 Installing Istio..."
istioctl install --set profile=demo -y

# Wait for Istio to be ready
echo "⏳ Waiting for Istio components to be ready..."
kubectl wait --for=condition=available --timeout=300s \
    deployment/istiod -n istio-system

kubectl wait --for=condition=available --timeout=300s \
    deployment/istio-ingressgateway -n istio-system

# Verify Istio installation
echo ""
echo "=== Istio Components ==="
kubectl get pods -n istio-system

# Get ingress gateway service
echo ""
echo "=== Istio Ingress Gateway Service ==="
kubectl get svc -n istio-system istio-ingressgateway

# Label default namespace for automatic sidecar injection
echo ""
echo "📝 Labeling default namespace for sidecar injection..."
kubectl label namespace default istio-injection=enabled --overwrite

echo ""
echo "✅ Istio deployment complete"