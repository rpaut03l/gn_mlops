#!/usr/bin/env python3
"""
Collect metrics from Kubernetes cluster for ML model input
Gathers load test results, pod metrics, and deployment info
"""

import json
import subprocess
import sys
from datetime import datetime


def get_pod_metrics():
    """Get CPU and memory metrics from pods"""
    try:
        result = subprocess.run([
            'kubectl', 'top', 'pods', '-n', 'default',
            '--no-headers'
        ], capture_output=True, text=True, timeout=10)

        metrics = []
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = line.split()
                if len(parts) >= 3:
                    metrics.append({
                        'pod': parts[0],
                        'cpu': parts[1],
                        'memory': parts[2]
                    })

        print(f"✅ Collected metrics from {len(metrics)} pods")
        return metrics

    except subprocess.TimeoutExpired:
        print("⚠️  Timeout getting pod metrics")
        return []
    except Exception as e:
        print(f"⚠️  Failed to get pod metrics: {e}")
        return []


def get_deployment_replicas():
    """Get current replica counts for deployments"""
    try:
        result = subprocess.run([
            'kubectl', 'get', 'deployments', '-n', 'default',
            '-o', 'json'
        ], capture_output=True, text=True, timeout=10)

        deployments = json.loads(result.stdout)
        replicas = {}

        for deploy in deployments.get('items', []):
            name = deploy['metadata']['name']
            replicas[name] = {
                'desired': deploy['spec']['replicas'],
                'ready': deploy['status'].get('readyReplicas', 0),
                'available': deploy['status'].get('availableReplicas', 0)
            }

        print(f"✅ Collected replica info from {len(replicas)} deployments")
        return replicas

    except Exception as e:
        print(f"⚠️  Failed to get deployment replicas: {e}")
        return {}


def load_test_results():
    """Load results from load test"""
    try:
        with open('loadtest-results.json', 'r') as f:
            data = json.load(f)
        print("✅ Loaded load test results")
        return data
    except FileNotFoundError:
        print("⚠️  Load test results not found")
        return None
    except Exception as e:
        print(f"⚠️  Failed to load test results: {e}")
        return None


def extract_ml_features(load_test_data):
    """Extract features needed for ML model"""
    if not load_test_data:
        return {
            'requests_per_sec': 0,
            'latency_p95_ms': 0,
            'error_rate_percent': 0
        }

    overall = load_test_data.get('overall_stats', {})
    latency = load_test_data.get('latency_stats', {})

    # Calculate error rate
    total_requests = overall.get('successful_requests', 0) + overall.get('failed_requests', 0)
    error_rate = (overall.get('failed_requests', 0) / total_requests * 100) if total_requests > 0 else 0

    features = {
        'requests_per_sec': overall.get('requests_per_second', 0),
        'latency_p95_ms': latency.get('p95_ms', 0),
        'error_rate_percent': error_rate
    }

    return features


def collect_metrics():
    """Main function to collect all metrics"""

    print("\n" + "=" * 60)
    print("📊 COLLECTING CLUSTER METRICS")
    print("=" * 60 + "\n")

    # Load test results
    load_test = load_test_results()

    # Extract ML features
    ml_features = extract_ml_features(load_test)

    print(f"\n🤖 ML Features Extracted:")
    print(f"   • Requests/sec: {ml_features['requests_per_sec']:.2f}")
    print(f"   • P95 Latency: {ml_features['latency_p95_ms']:.2f}ms")
    print(f"   • Error Rate: {ml_features['error_rate_percent']:.2f}%")

    # Get pod metrics
    pod_metrics = get_pod_metrics()

    # Get deployment info
    deployment_replicas = get_deployment_replicas()

    # Compile all metrics
    metrics = {
        'timestamp': datetime.now().isoformat(),
        'ml_features': ml_features,
        'pod_metrics': pod_metrics,
        'deployment_replicas': deployment_replicas,
        'load_test_summary': {
            'total_requests': load_test.get('test_info', {}).get('total_requests', 0) if load_test else 0,
            'success_rate': load_test.get('overall_stats', {}).get('success_rate_percent', 0) if load_test else 0,
            'mean_latency_ms': load_test.get('latency_stats', {}).get('mean_ms', 0) if load_test else 0
        }
    }

    # Save metrics
    with open('cluster-metrics.json', 'w') as f:
        json.dump(metrics, f, indent=2)

    print(f"\n💾 Metrics saved to: cluster-metrics.json")
    print("=" * 60 + "\n")

    return metrics


if __name__ == '__main__':
    try:
        metrics = collect_metrics()

        # Print summary
        if metrics['ml_features']['requests_per_sec'] > 0:
            print("✅ Metrics collection completed successfully!")
        else:
            print("⚠️  Warning: No load test data found, using default values")

        sys.exit(0)

    except Exception as e:
        print(f"\n❌ Metrics collection failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)