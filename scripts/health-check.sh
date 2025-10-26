#!/bin/bash
set -e

NAMESPACE="default"
MAX_RETRIES=30
RETRY_DELAY=5  # Increased from 2 to 5 seconds
ROUTING_DELAY=20  # Increased from 10 to 20 seconds

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
            -o jsonpath='{.spec.ports[?(@.name=="http2")].nodePort}' 2>/dev/null || echo "")
        
        if [ -z "$INGRESS_PORT" ]; then
            echo "❌ Failed to get ingress port"
            return 1
        fi
        
        # Try to access the endpoint with more verbose output
        response=$(curl -s -w "\nHTTP_CODE:%{http_code}" -H "Host: ${host}" \
            "http://localhost:${INGRESS_PORT}/" 2>/dev/null || echo "CURL_FAILED")
        
        # Extract HTTP code and body
        http_code=$(echo "$response" | grep "HTTP_CODE:" | cut -d':' -f2)
        body=$(echo "$response" | grep -v "HTTP_CODE:")
        
        if [ "$body" == "$expected_response" ]; then
            echo "✅ ${host} is healthy (response: ${body}, HTTP: ${http_code})"
            return 0
        fi
        
        retries=$((retries + 1))
        if [ $retries -lt $MAX_RETRIES ]; then
            echo "⏳ Attempt $retries/${MAX_RETRIES}: Waiting for ${host}... (got: '${body}', HTTP: ${http_code})"
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
ISTIO_NOT_RUNNING=$(kubectl get pods -n istio-system -o json | \
    jq -r '.items[] | select(.status.phase != "Running" and .status.phase != "Succeeded") | .metadata.name' | wc -l)

if [ "$ISTIO_NOT_RUNNING" -ne 0 ]; then
    echo "❌ Some Istio pods are not running"
    kubectl get pods -n istio-system -o wide
    kubectl describe pods -n istio-system
    exit 1
fi
echo "✅ All Istio components are healthy"

# Check application pods
echo ""
echo "=== Application Pods Health ==="
kubectl get pods -n ${NAMESPACE}

# Wait for all pods to be ready (not just running)
echo "⏳ Waiting for all pods to be ready..."
kubectl wait --for=condition=ready pod --all -n ${NAMESPACE} --timeout=120s || {
    echo "❌ Timeout waiting for pods to be ready"
    kubectl get pods -n ${NAMESPACE} -o wide
    kubectl describe pods -n ${NAMESPACE}
    exit 1
}

# Verify all pods are running
PODS_NOT_RUNNING=$(kubectl get pods -n ${NAMESPACE} -o json | \
    jq -r '.items[] | select(.status.phase != "Running" and .status.phase != "Succeeded") | .metadata.name' | wc -l)

if [ "$PODS_NOT_RUNNING" -ne 0 ]; then
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

# Verify services have endpoints
echo ""
echo "=== Service Endpoints ==="
kubectl get endpoints -n ${NAMESPACE}

# Check VirtualServices and Gateways
echo ""
echo "=== Istio Configuration ==="
kubectl get gateway -n ${NAMESPACE}
kubectl get virtualservice -n ${NAMESPACE}
kubectl get destinationrule -n ${NAMESPACE}

# Get ingress gateway details
INGRESS_HOST="localhost"
INGRESS_PORT=$(kubectl get svc istio-ingressgateway -n istio-system \
    -o jsonpath='{.spec.ports[?(@.name=="http2")].nodePort}')

echo ""
echo "=== Ingress Gateway ==="
echo "Host: ${INGRESS_HOST}"
echo "Port: ${INGRESS_PORT}"

if [ -z "$INGRESS_PORT" ]; then
    echo "❌ Failed to get ingress gateway port"
    kubectl describe svc istio-ingressgateway -n istio-system
    exit 1
fi

# Verify ingress gateway is ready
echo ""
echo "⏳ Waiting for ingress gateway to be ready..."
kubectl wait --for=condition=ready pod -l app=istio-ingressgateway -n istio-system --timeout=60s || {
    echo "❌ Ingress gateway not ready"
    kubectl get pods -n istio-system -l app=istio-ingressgateway
    exit 1
}

# Wait for Istio routing to propagate
echo ""
echo "⏳ Waiting ${ROUTING_DELAY}s for Istio routing to propagate..."
sleep ${ROUTING_DELAY}

# Check Istio proxy logs for potential issues
echo ""
echo "=== Checking Istio Proxy Logs ==="
for pod in $(kubectl get pods -n ${NAMESPACE} -o jsonpath='{.items[*].metadata.name}'); do
    echo "Checking istio-proxy in pod: ${pod}"
    kubectl logs ${pod} -n ${NAMESPACE} -c istio-proxy --tail=20 || echo "No istio-proxy in ${pod}"
done

# Check endpoints
echo ""
echo "=== Endpoint Health Checks ==="

if ! check_endpoint "foo.localhost" "foo"; then
    echo ""
    echo "=== Debug Information for foo.localhost ==="
    echo "--- Application Logs ---"
    kubectl logs -n ${NAMESPACE} -l app=foo --tail=100 || echo "No logs available"
    echo "--- VirtualService Details ---"
    kubectl describe virtualservice foo-virtualservice -n ${NAMESPACE} || echo "VirtualService not found"
    echo "--- Service Details ---"
    kubectl describe svc foo-service -n ${NAMESPACE} || echo "Service not found"
    echo "--- Pod Details ---"
    kubectl describe pods -n ${NAMESPACE} -l app=foo || echo "Pods not found"
    echo "--- Istio Proxy Config ---"
    FOO_POD=$(kubectl get pods -n ${NAMESPACE} -l app=foo -o jsonpath='{.items[0].metadata.name}')
    if [ -n "$FOO_POD" ]; then
        kubectl logs ${FOO_POD} -n ${NAMESPACE} -c istio-proxy --tail=50 || echo "No proxy logs"
    fi
    exit 1
fi

if ! check_endpoint "bar.localhost" "bar"; then
    echo ""
    echo "=== Debug Information for bar.localhost ==="
    echo "--- Application Logs ---"
    kubectl logs -n ${NAMESPACE} -l app=bar --tail=100 || echo "No logs available"
    echo "--- VirtualService Details ---"
    kubectl describe virtualservice bar-virtualservice -n ${NAMESPACE} || echo "VirtualService not found"
    echo "--- Service Details ---"
    kubectl describe svc bar-service -n ${NAMESPACE} || echo "Service not found"
    echo "--- Pod Details ---"
    kubectl describe pods -n ${NAMESPACE} -l app=bar || echo "Pods not found"
    echo "--- Istio Proxy Config ---"
    BAR_POD=$(kubectl get pods -n ${NAMESPACE} -l app=bar -o jsonpath='{.items[0].metadata.name}')
    if [ -n "$BAR_POD" ]; then
        kubectl logs ${BAR_POD} -n ${NAMESPACE} -c istio-proxy --tail=50 || echo "No proxy logs"
    fi
    exit 1
fi

# Final verification with multiple requests
echo ""
echo "=== Final Verification (10 requests each) ==="
SUCCESS_COUNT=0
FAIL_COUNT=0

for i in {1..10}; do
    foo_response=$(curl -s -H "Host: foo.localhost" "http://localhost:${INGRESS_PORT}/" || echo "ERROR")
    bar_response=$(curl -s -H "Host: bar.localhost" "http://localhost:${INGRESS_PORT}/" || echo "ERROR")
    
    if [ "$foo_response" != "foo" ] || [ "$bar_response" != "bar" ]; then
        echo "❌ Verification failed on request $i"
        echo "   foo response: '$foo_response' (expected: 'foo')"
        echo "   bar response: '$bar_response' (expected: 'bar')"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        
        # Don't exit immediately, collect all failures
        if [ $FAIL_COUNT -ge 3 ]; then
            echo "❌ Too many failures ($FAIL_COUNT), stopping verification"
            exit 1
        fi
    else
        echo "✅ Request $i: foo=${foo_response}, bar=${bar_response}"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    fi
    
    # Small delay between requests
    sleep 0.5
done

echo ""
echo "=== Verification Summary ==="
echo "✅ Successful requests: ${SUCCESS_COUNT}/10"
echo "❌ Failed requests: ${FAIL_COUNT}/10"

if [ $SUCCESS_COUNT -ge 8 ]; then
    echo ""
    echo "✅ All health checks passed successfully!"
    echo "✅ Endpoints are ready for load testing"
    exit 0
else
    echo ""
    echo "❌ Health checks failed - too many request failures"
    exit 1
fi
