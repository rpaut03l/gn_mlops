# Kubernetes Load Testing Pipeline

Automated CI/CD pipeline for deploying and load testing microservices on a multi-node Kubernetes (using kind) cluster using Istio service mesh.

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
│   ├── health-check.sh            # Health validation
│   ├── load-test.py               # Load testing script
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
- requests library (`pip install requests`)

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
- Timestamp: 2024-10-24T10:30:00

## Overall Statistics
- Successful Requests: 500
- Failed Requests: 0
- Success Rate: 100.0%
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
- Success Rate: 100.0%
- Mean Latency: 44.23 ms
- P90 Latency: 76.54 ms
- P95 Latency: 92.31 ms

### bar.localhost
- Total Requests: 247
- Successful: 247
- Failed: 0
- Success Rate: 100.0%
- Mean Latency: 47.12 ms
- P90 Latency: 81.23 ms
- P95 Latency: 97.89 ms
```

## 🔍 Verification

### Test the endpoints manually

```bash
# Get ingress port
INGRESS_PORT=$(kubectl get svc istio-ingressgateway -n istio-system \
  -o jsonpath='{.spec.ports[?(@.name=="http2")].nodePort}')

# Test foo endpoint
curl -H "Host: foo.localhost" http://localhost:${INGRESS_PORT}/

# Test bar endpoint
curl -H "Host: bar.localhost" http://localhost:${INGRESS_PORT}/
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
```

### Load test failures
```bash
# Check ingress gateway
kubectl get svc -n istio-system istio-ingressgateway

# Test connectivity directly
kubectl port-forward -n default svc/foo-service 8080:80
curl http://localhost:8080
```

## 🔄 CI/CD Workflow

The GitHub Actions workflow automatically:

1. Sets up the environment (Python, kubectl, KinD, Istio)
2. Creates a fresh KinD cluster
3. Deploys Istio and applications
4. Runs health checks
5. Executes load tests
6. Posts results as a PR comment
7. Uploads artifacts
8. Cleans up resources

### Triggering the Workflow

The workflow runs automatically on:
- Pull requests to `main` or `master` branch

### Viewing Results

- **In PR comments**: Results are posted automatically
- **In Actions tab**: View detailed logs and artifacts
- **Download artifacts**: JSON and Markdown results are available

## 📚 Additional Resources

- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Istio Documentation](https://istio.io/latest/docs/)
- [KinD Documentation](https://kind.sigs.k8s.io/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)

## 🧹 Cleanup

```bash
# Delete the cluster
kind delete cluster --name devops-test

# Remove local files
rm -f loadtest-results.*
rm -f github-comment.md
```

## 📝 Notes

- The cluster uses 1 control plane and 2 worker nodes
- Istio is deployed with the demo profile
- Each application runs 2 replicas for high availability
- Load tests use randomized traffic distribution
- Health checks ensure deployments are ready before testing
- Results include detailed latency percentiles and per-host statistics

## 🤝 Contributing

This is a take-home assignment project. For production use, consider:
- Adding proper TLS/SSL configuration
- Implementing monitoring and observability
- Adding security policies
- Setting up proper resource limits
- Implementing auto-scaling

## 📄 License

This project is for educational and evaluation purposes.
