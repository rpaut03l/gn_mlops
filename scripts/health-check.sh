#!/bin/bash
set -e

NAMESPACE="default"
MAX_RETRIES=30
RETRY_DELAY=2

echo "=== Running Health Checks ==="

# Function to check endpoint
check_endpoint() {
    local host=$1
    local expected_response=$2
    local retries=0

    echo "🔍 Checking endpoint: ${host}"

    while [ $retries -lt $MAX_RETRIES ]; do
        # Get ingress gateway NodePort
        INGRESS_PORT=$(kubectl get svc istio-ingressgateway -n istio-system \
            -o jsonpath='{.spec.ports[?(@.name=="http2")].nodePort}')

        # Try to access the endpoint
        response=$(curl -s -H "Host: ${host}" \
            "http://localhost:${INGRESS_PORT}/" 2>/dev/null || echo "")

        if [ "$response" == "$expected_response" ]; then
            echo "✅ ${host} is healthy (response: ${response})"
            return 0
        fi

        retries=$((retries + 1))
        if [ $retries -lt $MAX_RETRIES ]; then
            echo "⏳ Attempt $retries/${MAX_RETRIES}: Waiting for ${host}... (got: ${response})"
            sleep $RETRY_DELAY
        fi
    done

    echo "❌ ${host} health check failed after ${MAX_RETRIES} attempts"
    return 1
}

# Check cluster health
echo ""
echo "=== Cluster Status ==="
kubectl get nodes

# Check Istio components
echo ""
echo "=== Istio Components Health ==="
kubectl get pods -n istio-system

# Verify Istio components are running
ISTIO_READY=$(kubectl get pods -n istio-system -o json | \
    jq -r '.items[] | select(.status.phase != "Running") | .metadata.name' | wc -l)

if [ "$ISTIO_READY" -ne 0 ]; then
    echo "❌ Some Istio pods are not running"
    kubectl get pods -n istio-system
    exit 1
fi

echo "✅ All Istio components are healthy"

# Check application pods
echo ""
echo "=== Application Pods Health ==="
kubectl get pods -n ${NAMESPACE}

# Verify all pods are running
PODS_READY=$(kubectl get pods -n ${NAMESPACE} -o json | \
    jq -r '.items[] | select(.status.phase != "Running") | .metadata.name' | wc -l)

if [ "$PODS_READY" -ne 0 ]; then
    echo "❌ Some application pods are not running"
    kubectl get pods -n ${NAMESPACE} -o wide
    exit 1
fi

echo "✅ All application pods are healthy"

# Check services
echo ""
echo "=== Services ==="
kubectl get svc -n ${NAMESPACE}
kubectl get svc -n istio-system istio-ingressgateway

# Get ingress gateway details
INGRESS_HOST="localhost"
INGRESS_PORT=$(kubectl get svc istio-ingressgateway -n istio-system \
    -o jsonpath='{.spec.ports[?(@.name=="http2")].nodePort}')

echo ""
echo "=== Ingress Gateway ==="
echo "Host: ${INGRESS_HOST}"
echo "Port: ${INGRESS_PORT}"

# Wait a bit for Istio routing to propagate
echo ""
echo "⏳ Waiting for Istio routing to propagate..."
sleep 10

# Check endpoints
echo ""
echo "=== Endpoint Health Checks ==="

if ! check_endpoint "foo.localhost" "foo"; then
    echo ""
    echo "=== Debug Information for foo.localhost ==="
    kubectl logs -n ${NAMESPACE} -l app=foo --tail=50
    kubectl describe virtualservice foo-virtualservice -n ${NAMESPACE}
    exit 1
fi

if ! check_endpoint "bar.localhost" "bar"; then
    echo ""
    echo "=== Debug Information for bar.localhost ==="
    kubectl logs -n ${NAMESPACE} -l app=bar --tail=50
    kubectl describe virtualservice bar-virtualservice -n ${NAMESPACE}
    exit 1
fi

# Final verification with multiple requests
echo ""
echo "=== Final Verification (10 requests each) ==="
for i in {1..10}; do
    foo_response=$(curl -s -H "Host: foo.localhost" "http://localhost:${INGRESS_PORT}/")
    bar_response=$(curl -s -H "Host: bar.localhost" "http://localhost:${INGRESS_PORT}/")

    if [ "$foo_response" != "foo" ] || [ "$bar_response" != "bar" ]; then
        echo "❌ Verification failed on request $i"
        echo "   foo response: $foo_response (expected: foo)"
        echo "   bar response: $bar_response (expected: bar)"
        exit 1
    fi
    echo "✅ Request $i: foo=${foo_response}, bar=${bar_response}"
done

echo ""
echo "✅ All health checks passed successfully!"
echo "✅ Endpoints are ready for load testing"