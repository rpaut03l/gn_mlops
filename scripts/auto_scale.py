#!/usr/bin/env python3
"""
Auto-scale Kubernetes deployments based on ML model predictions
Uses trained model to predict optimal configuration and applies it
"""

import json
import subprocess
import pickle
import numpy as np
from datetime import datetime
import sys


def load_model():
    """Load the trained ML model"""
    try:
        with open('k8s_config_model.pkl', 'rb') as f:
            model = pickle.load(f)
        print("✅ Model loaded: k8s_config_model.pkl")
        return model
    except FileNotFoundError:
        print("❌ Model file not found: k8s_config_model.pkl")
        print("   Run train_model.py first!")
        return None
    except Exception as e:
        print(f"❌ Failed to load model: {e}")
        return None


def load_metrics():
    """Load collected metrics"""
    try:
        with open('cluster-metrics.json', 'r') as f:
            metrics = json.load(f)
        print("✅ Metrics loaded: cluster-metrics.json")
        return metrics
    except FileNotFoundError:
        print("❌ Metrics file not found: cluster-metrics.json")
        print("   Run collect_metrics.py first!")
        return None
    except Exception as e:
        print(f"❌ Failed to load metrics: {e}")
        return None


def predict_optimal_config(model, metrics):
    """Use ML model to predict optimal configuration"""

    ml_features = metrics.get('ml_features', {})

    # Prepare input features
    features = np.array([[
        ml_features.get('requests_per_sec', 10),
        ml_features.get('latency_p95_ms', 100),
        ml_features.get('error_rate_percent', 0.5)
    ]])

    print(f"\n🤖 ML Model Input:")
    print(f"   • Requests/sec: {features[0][0]:.2f}")
    print(f"   • P95 Latency: {features[0][1]:.2f}ms")
    print(f"   • Error Rate: {features[0][2]:.2f}%")

    # Predict
    prediction = model.predict(features)[0]

    # Convert to valid configuration
    config = {
        'replicas': max(1, min(10, int(round(prediction[0])))),
        'cpu_millicores': max(100, min(2000, int(round(prediction[1])))),
        'memory_mb': max(128, min(4096, int(round(prediction[2]))))
    }

    print(f"\n🎯 ML Model Prediction:")
    print(f"   • Replicas: {config['replicas']}")
    print(f"   • CPU: {config['cpu_millicores']}m")
    print(f"   • Memory: {config['memory_mb']}Mi")

    return config


def get_current_replicas(deployment_name):
    """Get current replica count for a deployment"""
    try:
        result = subprocess.run([
            'kubectl', 'get', 'deployment', deployment_name,
            '-n', 'default',
            '-o', 'jsonpath={.spec.replicas}'
        ], capture_output=True, text=True, timeout=10)

        return int(result.stdout.strip()) if result.stdout.strip() else 2
    except:
        return 2  # Default


def scale_deployment(deployment_name, replicas):
    """Scale a deployment to specified replica count"""

    current = get_current_replicas(deployment_name)

    if current == replicas:
        print(f"   ➡️  {deployment_name}: Already at {replicas} replicas")
        return True

    try:
        result = subprocess.run([
            'kubectl', 'scale', 'deployment', deployment_name,
            '-n', 'default',
            '--replicas', str(replicas)
        ], capture_output=True, text=True, check=True, timeout=10)

        print(f"   ✅ {deployment_name}: Scaled {current} → {replicas} replicas")
        return True

    except subprocess.CalledProcessError as e:
        print(f"   ❌ {deployment_name}: Failed to scale - {e.stderr}")
        return False
    except Exception as e:
        print(f"   ❌ {deployment_name}: Error - {e}")
        return False


def generate_resource_config(deployment_name, cpu_millicores, memory_mb):
    """Generate resource configuration recommendation"""

    config = {
        'apiVersion': 'apps/v1',
        'kind': 'Deployment',
        'metadata': {
            'name': deployment_name
        },
        'spec': {
            'template': {
                'spec': {
                    'containers': [{
                        'name': deployment_name.replace('-deployment', ''),
                        'resources': {
                            'requests': {
                                'cpu': f'{cpu_millicores}m',
                                'memory': f'{memory_mb}Mi'
                            },
                            'limits': {
                                'cpu': f'{cpu_millicores * 2}m',
                                'memory': f'{memory_mb * 2}Mi'
                            }
                        }
                    }]
                }
            }
        }
    }

    return config


def auto_scale():
    """Main auto-scaling function"""

    print("\n" + "=" * 60)
    print("🔄 ML-BASED AUTO-SCALING")
    print("=" * 60 + "\n")

    # Load model
    model = load_model()
    if not model:
        return False

    # Load metrics
    metrics = load_metrics()
    if not metrics:
        return False

    # Predict optimal configuration
    optimal_config = predict_optimal_config(model, metrics)

    # Target deployments
    deployments = ['foo-deployment', 'bar-deployment']

    print(f"\n🎯 Applying Configuration to Deployments:")
    print("-" * 60)

    scaling_results = []

    for deployment in deployments:
        print(f"\n📦 {deployment}:")

        # Scale replicas
        scaled = scale_deployment(deployment, optimal_config['replicas'])

        # Generate resource config
        resource_config = generate_resource_config(
            deployment,
            optimal_config['cpu_millicores'],
            optimal_config['memory_mb']
        )

        # Print resource recommendations
        resources = resource_config['spec']['template']['spec']['containers'][0]['resources']
        print(f"   📝 Recommended Resources:")
        print(f"      CPU Request: {resources['requests']['cpu']}")
        print(f"      Memory Request: {resources['requests']['memory']}")
        print(f"      CPU Limit: {resources['limits']['cpu']}")
        print(f"      Memory Limit: {resources['limits']['memory']}")

        scaling_results.append({
            'deployment': deployment,
            'scaled': scaled,
            'config': optimal_config.copy(),
            'resource_config': resource_config
        })

    # Save results
    results = {
        'timestamp': datetime.now().isoformat(),
        'predicted_config': optimal_config,
        'input_metrics': metrics.get('ml_features', {}),
        'scaling_results': scaling_results
    }

    with open('scaling-results.json', 'w') as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 60)
    print("💾 Results saved to: scaling-results.json")
    print("=" * 60 + "\n")

    # Summary
    successful = sum(1 for r in scaling_results if r['scaled'])
    print(f"✅ Auto-scaling complete: {successful}/{len(deployments)} deployments scaled")

    return True


if __name__ == '__main__':
    try:
        success = auto_scale()

        if success:
            print("\n✅ Auto-scaling pipeline completed successfully!")
            sys.exit(0)
        else:
            print("\n❌ Auto-scaling pipeline failed!")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Auto-scaling failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)