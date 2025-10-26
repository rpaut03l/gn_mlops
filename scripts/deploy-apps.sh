#!/bin/bash
set -e

NAMESPACE="default"

echo "=== Deploying Foo and Bar Applications ==="

# Create namespace if it doesn't exist
kubectl create namespace ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

# Apply all Kubernetes manifests
echo "📦 Applying application deployments..."
kubectl apply -f k8s/foo-deployment.yaml
kubectl apply -f k8s/bar-deployment.yaml

echo "📦 Applying services..."
kubectl apply -f k8s/foo-service.yaml
kubectl apply -f k8s/bar-service.yaml

# Wait for deployments to be ready
echo "⏳ Waiting for deployments to be ready..."
kubectl wait --for=condition=available --timeout=300s \
    deployment/foo-deployment -n ${NAMESPACE}

kubectl wait --for=condition=available --timeout=300s \
    deployment/bar-deployment -n ${NAMESPACE}

# Apply Istio Gateway and VirtualServices
echo "📦 Applying Istio Gateway..."
kubectl apply -f k8s/istio-gateway.yaml

echo "📦 Applying Istio VirtualServices..."
kubectl apply -f k8s/foo-virtualservice.yaml
kubectl apply -f k8s/bar-virtualservice.yaml

# Wait a bit for Istio to sync
sleep 5

echo ""
echo "=== Deployment Status ==="
kubectl get deployments -n ${NAMESPACE}

echo ""
echo "=== Pods ==="
kubectl get pods -n ${NAMESPACE} -o wide

echo ""
echo "=== Services ==="
kubectl get services -n ${NAMESPACE}

echo ""
echo "=== Istio Gateway ==="
kubectl get gateway -n ${NAMESPACE}

echo ""
echo "=== Istio VirtualServices ==="
kubectl get virtualservice -n ${NAMESPACE}

echo ""
echo "✅ Application deployment complete"