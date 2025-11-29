#!/bin/bash
set -e

NAMESPACE="default"
MAX_RETRIES=30
RETRY_DELAY=3
ROUTING_DELAY=15

echo "=== Running Health Checks ==="

# Get ingress gateway pod (used throughout)
get_ingress_pod() {
    kubectl get pod -n istio-system -l app=istio-ingressgateway \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo ""
}

# Function to check endpoint using kubectl exec
check_endpoint() {
    local host=$1
    local expected_response=$2
    local retries=0

    echo "🔍 Checking endpoint: ${host}"

    INGRESS_POD=$(get_ingress_pod)

    if [ -z "$INGRESS_POD" ]; then
        echo "❌ No ingress gateway pod found"
        return 1
    fi

    echo "Using ingress pod: ${INGRESS_POD}"

    while [ $retries -lt $MAX_RETRIES ]; do
        # Execute curl FROM INSIDE the ingress gateway pod
        response=$(kubectl exec -n istio-system "${INGRESS_POD}" -- \
            curl -s -m 5 -H "Host: ${host}" "http://localhost:8080/" 2>/dev/null || echo "")

        if [ "$response" == "$expected_response" ]; then
            echo "✅ ${host} is healthy (response: ${response})"
            return 0
        fi

        retries=$((retries + 1))
        if [ $retries -lt $MAX_RETRIES ]; then
            echo "⏳ Attempt $retries/${MAX_RETRIES}: Waiting for ${host}... (got: '${response}')"
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
    exit 1
fi
echo "✅ All Istio components are healthy"

# Check application pods
echo ""
echo "=== Application Pods Health ==="
kubectl get pods -n ${NAMESPACE}

# Wait for all pods to be ready
echo "⏳ Waiting for all pods to be ready..."
kubectl wait --for=condition=ready pod --all -n ${NAMESPACE} --timeout=120s || {
    echo "❌ Timeout waiting for pods to be ready"
    kubectl get pods -n ${NAMESPACE} -o wide
    exit 1
}
echo "✅ All application pods are ready"

# Check services
echo ""
echo "=== Services ==="
kubectl get svc -n ${NAMESPACE}
kubectl get svc -n istio-system istio-ingressgateway

# Verify services have endpoints
echo ""
echo "=== Service Endpoints ==="
kubectl get endpoints -n ${NAMESPACE}

FOO_ENDPOINTS=$(kubectl get endpoints foo-service -n ${NAMESPACE} -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null | wc -w)
BAR_ENDPOINTS=$(kubectl get endpoints bar-service -n ${NAMESPACE} -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null | wc -w)

if [ "$FOO_ENDPOINTS" -eq 0 ]; then
    echo "⚠️  Warning: foo-service has no endpoints"
fi

if [ "$BAR_ENDPOINTS" -eq 0 ]; then
    echo "⚠️  Warning: bar-service has no endpoints"
fi

echo "✅ foo-service has ${FOO_ENDPOINTS} endpoint(s)"
echo "✅ bar-service has ${BAR_ENDPOINTS} endpoint(s)"

# Check VirtualServices and Gateways
echo ""
echo "=== Istio Configuration ==="
kubectl get gateway -n ${NAMESPACE} || echo "No gateways found"
kubectl get virtualservice -n ${NAMESPACE} || echo "No virtual services found"

# Verify ingress gateway is ready
echo ""
echo "⏳ Waiting for ingress gateway to be ready..."
kubectl wait --for=condition=ready pod -l app=istio-ingressgateway -n istio-system --timeout=60s || {
    echo "❌ Ingress gateway not ready"
    exit 1
}

INGRESS_POD=$(get_ingress_pod)
echo "✅ Ingress gateway is ready: ${INGRESS_POD}"

# Wait for Istio routing to propagate
echo ""
echo "⏳ Waiting ${ROUTING_DELAY}s for Istio routing to propagate..."
sleep ${ROUTING_DELAY}

# Check endpoints
echo ""
echo "=== Endpoint Health Checks ==="

if ! check_endpoint "foo.localhost" "foo"; then
    echo ""
    echo "=== Debug Information for foo.localhost ==="
    echo "--- Application Logs ---"
    kubectl logs -n ${NAMESPACE} -l app=foo --tail=50 2>/dev/null || echo "No logs available"
    echo ""
    echo "--- VirtualService Details ---"
    kubectl describe virtualservice foo-virtualservice -n ${NAMESPACE} 2>/dev/null || echo "VirtualService not found"
    echo ""
    echo "--- Service Details ---"
    kubectl describe svc foo-service -n ${NAMESPACE} 2>/dev/null || echo "Service not found"
    exit 1
fi

if ! check_endpoint "bar.localhost" "bar"; then
    echo ""
    echo "=== Debug Information for bar.localhost ==="
    echo "--- Application Logs ---"
    kubectl logs -n ${NAMESPACE} -l app=bar --tail=50 2>/dev/null || echo "No logs available"
    echo ""
    echo "--- VirtualService Details ---"
    kubectl describe virtualservice bar-virtualservice -n ${NAMESPACE} 2>/dev/null || echo "VirtualService not found"
    echo ""
    echo "--- Service Details ---"
    kubectl describe svc bar-service -n ${NAMESPACE} 2>/dev/null || echo "Service not found"
    exit 1
fi

# Final verification with multiple requests
echo ""
echo "=== Final Verification (10 requests each) ==="
SUCCESS_COUNT=0
FAIL_COUNT=0

INGRESS_POD=$(get_ingress_pod)

for i in {1..10}; do
    # CRITICAL FIX: Use kubectl exec for final verification too!
    foo_response=$(kubectl exec -n istio-system "${INGRESS_POD}" -- \
        curl -s -m 5 -H "Host: foo.localhost" "http://localhost:8080/" 2>/dev/null || echo "ERROR")
    bar_response=$(kubectl exec -n istio-system "${INGRESS_POD}" -- \
        curl -s -m 5 -H "Host: bar.localhost" "http://localhost:8080/" 2>/dev/null || echo "ERROR")

    if [ "$foo_response" != "foo" ] || [ "$bar_response" != "bar" ]; then
        echo "❌ Verification failed on request $i"
        echo "   foo response: '$foo_response' (expected: 'foo')"
        echo "   bar response: '$bar_response' (expected: 'bar')"
        FAIL_COUNT=$((FAIL_COUNT + 1))

        # Don't exit immediately, collect all failures
        if [ $FAIL_COUNT -ge 3 ]; then
            echo "❌ Too many failures ($FAIL_COUNT), stopping verification"
            echo ""
            echo "=== Additional Debug Info ==="
            echo "--- Ingress Gateway Logs (last 30 lines) ---"
            kubectl logs -n istio-system "${INGRESS_POD}" --tail=30 2>/dev/null || echo "No logs"
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
    echo ""
    echo "=== Final Debug Information ==="
    echo "--- Ingress Pod Status ---"
    kubectl describe pod -n istio-system "${INGRESS_POD}" | tail -50
    exit 1
fi