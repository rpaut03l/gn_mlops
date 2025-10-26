# Kubernetes End-End Deployment, Health Checks, Load Testing, Auto Comment in PR etc usig Native(traditional) CI-CD Pipeline.

Automated CI/CD pipeline for deploying and load testing microservices on a multi-node Kubernetes cluster using Istio service mesh.

## 📋 Overview

This project implements a complete CI/CD workflow that:
1. ✅ Checks for an existing multi-node KinD cluster
2. ✅ Deploys Istio service mesh as ingress controller
3. ✅ Creates two http-echo deployments (foo and bar)
4. ✅ Configures host-based routing via Istio VirtualServices
5. ✅ Validates deployment health
6. ✅ Generates randomized load test traffic
7. ✅ Posts detailed load test results to GitHub PR

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   GitHub Actions CI                      │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│              KinD Cluster (3 nodes)                      │
│  ┌────────────────┐  ┌──────────┐  ┌──────────┐        │
│  │ Control Plane  │  │ Worker 1 │  │ Worker 2 │        │
│  └────────────────┘  └──────────┘  └──────────┘        │
│                                                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │           Istio Ingress Gateway                  │   │
│  └─────────────────────────────────────────────────┘   │
│            ↓ (foo.localhost)    ↓ (bar.localhost)       │
│  ┌──────────────────┐   ┌──────────────────┐          │
│  │  Foo Service     │   │  Bar Service     │          │
│  │  (2 replicas)    │   │  (2 replicas)    │          │
│  └──────────────────┘   └──────────────────┘          │
└─────────────────────────────────────────────────────────┘
```

## 📁 Project Structure

```
.
├── .github/
│   └── workflows/
│       └── ci.yml                 # GitHub Actions workflow
├── k8s/
│   ├── kind-config.yaml           # KinD cluster configuration
│   ├── foo-deployment.yaml        # Foo app deployment
│   ├── bar-deployment.yaml        # Bar app deployment
│   ├── foo-service.yaml           # Foo service
│   ├── bar-service.yaml           # Bar service
│   ├── istio-gateway.yaml         # Istio gateway
│   ├── foo-virtualservice.yaml    # Foo routing rules
│   └── bar-virtualservice.yaml    # Bar routing rules
├── scripts/
│   ├── check-cluster.sh           # Verify KinD cluster
│   ├── deploy-istio.sh            # Install Istio
│   ├── deploy-apps.sh             # Deploy applications
│   ├── health-check.sh            # Health validation (uses kubectl exec)
│   ├── load-test.py               # Load testing script (uses kubectl exec)
│   ├── format-results.sh          # Format results for PR
│   └── run-all.sh                 # Main orchestration script
└── README.md
```

## 🚀 Quick Start

### Prerequisites

- Docker installed and running
- KinD (Kubernetes in Docker)
- kubectl
- Python 3.8+
- Standard Python libraries (subprocess, json, time, statistics)

### Local Setup

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd devops-k8s-load-test
   ```

2. **Create KinD cluster** (if not already created)
   ```bash
   kind create cluster --config k8s/kind-config.yaml
   ```

3. **Run the complete pipeline**
   ```bash
   chmod +x scripts/run-all.sh
   ./scripts/run-all.sh
   ```

   This will:
   - Check cluster existence and health
   - Deploy Istio
   - Deploy foo and bar applications
   - Run health checks
   - Execute load tests
   - Generate results

### Manual Step-by-Step Execution

If you prefer to run each step manually:

```bash
# 1. Check cluster
chmod +x scripts/check-cluster.sh
./scripts/check-cluster.sh

# 2. Deploy Istio
chmod +x scripts/deploy-istio.sh
./scripts/deploy-istio.sh

# 3. Deploy applications
chmod +x scripts/deploy-apps.sh
./scripts/deploy-apps.sh

# 4. Health checks
chmod +x scripts/health-check.sh
./scripts/health-check.sh

# 5. Load test
chmod +x scripts/load-test.py
python3 scripts/load-test.py

# 6. Format results
chmod +x scripts/format-results.sh
./scripts/format-results.sh
```

## 🔧 Configuration

### Cluster Configuration

Edit `k8s/kind-config.yaml` to modify:
- Number of worker nodes
- Port mappings
- Resource allocations

### Load Test Parameters

Edit `scripts/load-test.py`:
```python
TOTAL_REQUESTS = 500      # Total number of requests
WORKERS = 20              # Concurrent workers
TIMEOUT = 10              # Request timeout (seconds)
```

### Application Replicas

Edit deployment files:
```yaml
spec:
  replicas: 2  # Adjust number of pods
```

## 🔑 Important: Kind Networking

### ⚠️ Critical Implementation Detail

**In Kind clusters, `localhost:NodePort` is NOT accessible from the host or GitHub Actions runner.**

This is because Kind runs Kubernetes nodes as Docker containers, and NodePort services are bound to the container's network interface, not the host.

### ✅ Solution: kubectl exec Method

Both `health-check.sh` and `load-test.py` use `kubectl exec` to run curl commands **inside** the Istio ingress gateway pod:

**Health Check Script:**
```bash
# Get ingress gateway pod
INGRESS_POD=$(kubectl get pod -n istio-system -l app=istio-ingressgateway \
    -o jsonpath='{.items[0].metadata.name}')

# Execute curl from inside the pod
kubectl exec -n istio-system "${INGRESS_POD}" -- \
    curl -s -H "Host: foo.localhost" http://localhost:8080/
```

**Load Test Script:**
```python
# Execute curl from inside the ingress gateway pod
result = subprocess.run([
    'kubectl', 'exec',
    '-n', 'istio-system',
    INGRESS_POD,
    '--',
    'curl', '-s', '-m', str(TIMEOUT),
    '-w', '\\n%{http_code}',
    '-H', f'Host: {host}',
    'http://localhost:8080/'
], capture_output=True, text=True, timeout=TIMEOUT + 2)
```

### ❌ What Doesn't Work

```bash
# DON'T USE: Direct curl to localhost:NodePort
INGRESS_PORT=$(kubectl get svc istio-ingressgateway -n istio-system \
    -o jsonpath='{.spec.ports[?(@.name=="http2")].nodePort}')
curl -H "Host: foo.localhost" http://localhost:${INGRESS_PORT}/  # ❌ Fails in Kind
```

```python
# DON'T USE: requests library with localhost:NodePort
import requests
response = requests.get(f"http://localhost:{INGRESS_PORT}/", headers=headers)  # ❌ Fails in Kind
```

### ✅ What Works

```bash
# USE: kubectl exec to run curl inside the cluster
kubectl exec -n istio-system <ingress-pod> -- \
    curl -H "Host: foo.localhost" http://localhost:8080/  # ✅ Works!
```

## 📊 Load Test Results

The load test generates three output files:

1. **loadtest-results.json** - Raw JSON data
2. **loadtest-results.md** - Markdown formatted report
3. **github-comment.md** - Formatted for GitHub PR comments

### Sample Results

```markdown
# 📊 Load Test Results

## Test Configuration
- Total Requests: 500
- Concurrent Workers: 20
- Test Duration: 12.34s
- Method: kubectl_exec
- Timestamp: 2024-10-24T10:30:00

## Overall Statistics
- Successful Requests: 500
- Failed Requests: 0
- Success Rate: ✅ 100.0%
- Throughput: 40.52 req/s

## Latency Statistics
- Min: 12.45 ms
- Max: 234.56 ms
- Mean: 45.67 ms
- Median: 42.34 ms
- P90: 78.90 ms
- P95: 95.12 ms
- P99: 145.67 ms

## Per-Host Statistics

### foo.localhost
- Total Requests: 253
- Successful: 253
- Failed: 0
- Success Rate: ✅ 100.0%
- Mean Latency: 44.23 ms
- Median Latency: 42.50 ms
- P90 Latency: 76.54 ms
- P95 Latency: 92.31 ms

### bar.localhost
- Total Requests: 247
- Successful: 247
- Failed: 0
- Success Rate: ✅ 100.0%
- Mean Latency: 47.12 ms
- Median Latency: 45.80 ms
- P90 Latency: 81.23 ms
- P95 Latency: 97.89 ms
```

## 🔍 Verification

### Test the endpoints manually (Local Development)

For local testing on your machine with Kind:

```bash
# Get ingress gateway pod
INGRESS_POD=$(kubectl get pod -n istio-system -l app=istio-ingressgateway \
    -o jsonpath='{.items[0].metadata.name}')

# Test foo endpoint using kubectl exec
kubectl exec -n istio-system "${INGRESS_POD}" -- \
    curl -s -H "Host: foo.localhost" http://localhost:8080/

# Test bar endpoint using kubectl exec
kubectl exec -n istio-system "${INGRESS_POD}" -- \
    curl -s -H "Host: bar.localhost" http://localhost:8080/
```

### Alternative: Port Forwarding (Local Only)

For interactive testing on your local machine:

```bash
# Start port forward in background
kubectl port-forward -n istio-system svc/istio-ingressgateway 8080:80 &

# Test endpoints
curl -H "Host: foo.localhost" http://localhost:8080/
curl -H "Host: bar.localhost" http://localhost:8080/

# Stop port forward
kill %1
```

### Check cluster resources

```bash
# View all pods
kubectl get pods -A

# View Istio components
kubectl get pods -n istio-system

# View application pods
kubectl get pods -n default

# View services
kubectl get svc -A

# View Istio routing
kubectl get gateway,virtualservice -n default
```

## 🐛 Troubleshooting

### Cluster not found
```bash
# Create the cluster
kind create cluster --config k8s/kind-config.yaml

# Verify creation
kubectl get nodes
```

### Pods not starting
```bash
# Check pod status
kubectl get pods -n default -o wide

# View pod logs
kubectl logs -n default -l app=foo
kubectl logs -n default -l app=bar

# Describe pod for events
kubectl describe pod -n default <pod-name>
```

### Istio issues
```bash
# Check Istio status
kubectl get pods -n istio-system

# View Istio logs
kubectl logs -n istio-system -l app=istiod

# Verify gateway
kubectl get gateway,virtualservice -n default

# Check ingress gateway is ready
kubectl wait --for=condition=ready pod -l app=istio-ingressgateway \
    -n istio-system --timeout=60s
```

### Health check or load test failures

**Error: "CURL_FAILED" or "Connection Refused"**

This means the script is trying to use `localhost:NodePort` instead of `kubectl exec`.

**Solution:** Ensure you're using the fixed versions of:
- `health-check.sh` - Uses kubectl exec for all checks
- `load-test.py` - Uses subprocess with kubectl exec

**Verify ingress pod exists:**
```bash
kubectl get pods -n istio-system -l app=istio-ingressgateway
```

**Test manually:**
```bash
INGRESS_POD=$(kubectl get pod -n istio-system -l app=istio-ingressgateway \
    -o jsonpath='{.items[0].metadata.name}')

kubectl exec -n istio-system "${INGRESS_POD}" -- \
    curl -v -H "Host: foo.localhost" http://localhost:8080/
```

### Service endpoints missing
```bash
# Check if services have endpoints
kubectl get endpoints foo-service bar-service -n default

# If no endpoints, pods might not be ready
kubectl get pods -n default -o wide
```

## 🔄 CI/CD Workflow

The GitHub Actions workflow automatically:

1. Sets up the environment (Python, kubectl, KinD, Istio)
2. Creates a fresh KinD cluster
3. Deploys Istio and applications
4. Waits for all pods to be ready
5. Runs health checks (using kubectl exec)
6. Executes load tests (using kubectl exec)
7. Posts results as a PR comment
8. Uploads artifacts
9. Cleans up resources

### Workflow Permissions

The workflow requires these permissions to post PR comments:

```yaml
permissions:
  contents: read
  pull-requests: write
  issues: write
```

### Triggering the Workflow

The workflow runs automatically on:
- Pull requests to `main` or `master` branch
- Push to `main` or `master` branch

### Viewing Results

- **In PR comments**: Results are posted automatically
- **In Actions tab**: View detailed logs and artifacts
- **Download artifacts**: JSON and Markdown results are available

## 📚 Additional Resources

- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Istio Documentation](https://istio.io/latest/docs/)
- [KinD Documentation](https://kind.sigs.k8s.io/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Kind - Ingress Guide](https://kind.sigs.k8s.io/docs/user/ingress/)

## 🧹 Cleanup

```bash
# Delete the cluster
kind delete cluster --name devops-test

# Remove local files
rm -f loadtest-results.*
rm -f github-comment.md
rm -f cluster-metrics.json
rm -f scaling-results.json
```

## 📝 Notes

- The cluster uses 1 control plane and 2 worker nodes
- Istio is deployed with the demo profile
- Each application runs 2 replicas for high availability
- Load tests use randomized traffic distribution
- Health checks ensure deployments are ready before testing
- Results include detailed latency percentiles and per-host statistics
- **All network calls use kubectl exec to work correctly in Kind**
- No external dependencies required (uses Python standard library)

## 🔧 Technical Details

### Why kubectl exec?

Kind runs Kubernetes nodes as Docker containers. When you access a NodePort service:
- NodePort binds to the **container's** network interface
- The GitHub Actions runner (or your terminal) is **outside** the container
- Direct access to `localhost:NodePort` fails with "Connection Refused"

**kubectl exec** solves this by running curl **inside** the container where the services are accessible.

### Performance Considerations

kubectl exec adds overhead compared to direct HTTP requests:
- Each request spawns a kubectl process
- Recommended concurrent workers: 10-20 (instead of 50+)
- For higher load, consider port-forward with requests library

### Alternative Approaches

1. **Port Forward**: Use `kubectl port-forward` in background, then use standard HTTP libraries
2. **Extra Port Mappings**: Configure Kind to map NodePort to host (requires cluster recreation)
3. **MetalLB**: Install MetalLB for LoadBalancer support in Kind

## Contributing

This is just a learning project. For production use, consider things like:
- Adding proper TLS/SSL configuration
- Implementing monitoring and observability (Prometheus, Grafana)
- Adding security policies (NetworkPolicies, PodSecurityPolicies)
- Setting up proper resource limits and requests
- Implementing HPA (Horizontal Pod Autoscaler)
- Using a proper LoadBalancer or Ingress controller
- Implementing rate limiting and circuit breakers
- Adding distributed tracing (OTel[OpenTelemetry])
- Kyverno + PolicyReporter (UI) for validating resources at an admission controller level itself.
- Chaos Engineering (gremlin or any chaosmesh engineering tools)
- Monitoring, Logging, OnCall process Integrations etc (Prometheus, Grafana, DataDog, PagerDuty etc) to name a few.

## License

This project is for educational and evaluation purposes.

---

**Key Improvement:** All networking issues in Kind clusters are resolved by using `kubectl exec` to run commands inside the cluster instead of trying to access NodePort from outside. This makes the pipeline reliable and production-ready for CI/CD environments..
