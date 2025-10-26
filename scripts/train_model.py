#!/usr/bin/env python3
"""
ML Model Training for K8s Configuration Optimization
Trains a model to predict optimal replicas, CPU, and memory based on load metrics..
"""

import json
import pickle
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
from datetime import datetime
import sys

# Training data: [requests/sec, latency_p95, error_rate] -> [replicas, cpu, memory]
training_data = {
    'features': [
        [10, 50, 0.1],  # Low load
        [20, 60, 0.2],
        [30, 80, 0.3],
        [50, 100, 0.5],  # Medium load
        [60, 120, 0.6],
        [80, 150, 0.8],
        [100, 200, 1.0],  # High load
        [120, 250, 1.5],
        [150, 300, 2.0],  # Very high load
        [200, 400, 3.0],
    ],
    'targets': [
        [2, 100, 256],  # [replicas, cpu_millicores, memory_mb]
        [2, 150, 384],
        [2, 120, 320],
        [3, 200, 512],
        [3, 300, 640],
        [4, 400, 768],
        [5, 500, 1024],
        [6, 750, 1536],
        [8, 1000, 2048],
        [10, 1500, 3072],
    ]
}


def train_model(n_estimators=100, max_depth=10, random_state=42):
    """Train the ML model"""

    print("🤖 Training ML model for K8s configuration optimization...")
    print(f"   Parameters: n_estimators={n_estimators}, max_depth={max_depth}")

    # Prepare data
    X = np.array(training_data['features'])
    y = np.array(training_data['targets'])

    print(f"   Training samples: {len(X)}")

    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=random_state
    )

    # Train model
    model = RandomForestRegressor(
        n_estimators=n_estimators,
        max_depth=max_depth,
        random_state=random_state
    )

    model.fit(X_train, y_train)

    # Evaluate
    y_pred = model.predict(X_test)
    r2 = r2_score(y_test, y_pred)
    mse = mean_squared_error(y_test, y_pred)
    mae = mean_absolute_error(y_test, y_pred)

    print(f"\n✅ Model Training Complete!")
    print(f"   R² Score: {r2:.3f}")
    print(f"   MSE: {mse:.3f}")
    print(f"   MAE: {mae:.3f}")

    # Feature importance
    feature_names = ['requests_per_sec', 'latency_p95_ms', 'error_rate_percent']
    target_names = ['replicas', 'cpu_millicores', 'memory_mb']

    print(f"\n📊 Feature Importance:")
    for i, feature in enumerate(feature_names):
        print(f"   {feature}: {model.feature_importances_[i]:.3f}")

    # Save model
    with open('k8s_config_model.pkl', 'wb') as f:
        pickle.dump(model, f)

    # Save metadata
    metadata = {
        'trained_at': datetime.now().isoformat(),
        'test_r2_score': float(r2),
        'test_mse': float(mse),
        'test_mae': float(mae),
        'n_estimators': n_estimators,
        'max_depth': max_depth,
        'features': feature_names,
        'targets': target_names,
        'training_samples': len(X),
        'test_samples': len(X_test)
    }

    with open('model_metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"\n💾 Saved:")
    print(f"   Model: k8s_config_model.pkl")
    print(f"   Metadata: model_metadata.json")

    return model, metadata


def test_prediction(model):
    """Test the model with sample predictions"""

    print(f"\n🧪 Testing Predictions:")

    test_cases = [
        {'rps': 25, 'latency': 70, 'error': 0.3, 'desc': 'Light load'},
        {'rps': 75, 'latency': 180, 'error': 1.2, 'desc': 'Medium load'},
        {'rps': 180, 'latency': 350, 'error': 2.5, 'desc': 'Heavy load'},
    ]

    for test in test_cases:
        features = np.array([[test['rps'], test['latency'], test['error']]])
        prediction = model.predict(features)[0]

        config = {
            'replicas': max(1, int(round(prediction[0]))),
            'cpu_millicores': max(100, int(round(prediction[1]))),
            'memory_mb': max(128, int(round(prediction[2])))
        }

        print(f"\n   {test['desc']}:")
        print(f"      Input: {test['rps']} req/s, {test['latency']}ms latency, {test['error']}% errors")
        print(
            f"      Predicted: {config['replicas']} replicas, {config['cpu_millicores']}m CPU, {config['memory_mb']}Mi RAM")


if __name__ == '__main__':
    try:
        # Train model
        model, metadata = train_model()

        # Test predictions
        test_prediction(model)

        print("\n✅ Training pipeline completed successfully!")
        sys.exit(0)

    except Exception as e:
        print(f"\n❌ Training failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)