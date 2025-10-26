#!/usr/bin/env python3

import requests
import time
import random
import statistics
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import subprocess

# Configuration
TOTAL_REQUESTS = 500
WORKERS = 20
TIMEOUT = 10


# Get ingress port from kubectl
def get_ingress_port():
    try:
        result = subprocess.run([
            'kubectl', 'get', 'svc', 'istio-ingressgateway',
            '-n', 'istio-system',
            '-o', 'jsonpath={.spec.ports[?(@.name=="http2")].nodePort}'
        ], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error getting ingress port: {e}")
        sys.exit(1)


INGRESS_PORT = get_ingress_port()
BASE_URL = f"http://localhost:{INGRESS_PORT}/"

HOSTS = ["foo.localhost", "bar.localhost"]


class LoadTestResults:
    def __init__(self):
        self.durations = []
        self.failed_requests = 0
        self.successful_requests = 0
        self.host_stats = {host: {"success": 0, "failed": 0, "durations": []} for host in HOSTS}
        self.start_time = None
        self.end_time = None
        self.errors = []

    def add_result(self, host, duration, success, error=None):
        if success:
            self.successful_requests += 1
            self.durations.append(duration)
            self.host_stats[host]["success"] += 1
            self.host_stats[host]["durations"].append(duration)
        else:
            self.failed_requests += 1
            self.host_stats[host]["failed"] += 1
            if error:
                self.errors.append({"host": host, "error": str(error)})

    def calculate_percentile(self, durations, percentile):
        if not durations:
            return 0
        sorted_durations = sorted(durations)
        index = int(len(sorted_durations) * (percentile / 100.0))
        return sorted_durations[min(index, len(sorted_durations) - 1)]

    def get_summary(self):
        total_duration = (self.end_time - self.start_time)

        summary = {
            "test_info": {
                "total_requests": TOTAL_REQUESTS,
                "concurrent_workers": WORKERS,
                "test_duration_seconds": round(total_duration, 2),
                "timestamp": datetime.now().isoformat()
            },
            "overall_stats": {
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "success_rate_percent": round((self.successful_requests / TOTAL_REQUESTS) * 100, 2),
                "requests_per_second": round(TOTAL_REQUESTS / total_duration, 2)
            },
            "latency_stats": {},
            "host_stats": {}
        }

        # Overall latency statistics
        if self.durations:
            summary["latency_stats"] = {
                "min_ms": round(min(self.durations) * 1000, 2),
                "max_ms": round(max(self.durations) * 1000, 2),
                "mean_ms": round(statistics.mean(self.durations) * 1000, 2),
                "median_ms": round(statistics.median(self.durations) * 1000, 2),
                "p90_ms": round(self.calculate_percentile(self.durations, 90) * 1000, 2),
                "p95_ms": round(self.calculate_percentile(self.durations, 95) * 1000, 2),
                "p99_ms": round(self.calculate_percentile(self.durations, 99) * 1000, 2)
            }

        # Per-host statistics
        for host in HOSTS:
            host_data = self.host_stats[host]
            total_host_requests = host_data["success"] + host_data["failed"]

            host_summary = {
                "total_requests": total_host_requests,
                "successful_requests": host_data["success"],
                "failed_requests": host_data["failed"],
                "success_rate_percent": round((host_data["success"] / total_host_requests) * 100,
                                              2) if total_host_requests > 0 else 0
            }

            if host_data["durations"]:
                host_summary["latency"] = {
                    "mean_ms": round(statistics.mean(host_data["durations"]) * 1000, 2),
                    "median_ms": round(statistics.median(host_data["durations"]) * 1000, 2),
                    "p90_ms": round(self.calculate_percentile(host_data["durations"], 90) * 1000, 2),
                    "p95_ms": round(self.calculate_percentile(host_data["durations"], 95) * 1000, 2)
                }

            summary["host_stats"][host] = host_summary

        # Add error samples (limit to 10)
        if self.errors:
            summary["error_samples"] = self.errors[:10]

        return summary


def make_request(request_id):
    """Make a single HTTP request to a random host"""
    host = random.choice(HOSTS)
    headers = {"Host": host}

    try:
        start_time = time.time()
        response = requests.get(BASE_URL, headers=headers, timeout=TIMEOUT)
        duration = time.time() - start_time

        # Verify response
        expected_response = host.split('.')[0]  # "foo" from "foo.localhost"
        success = (response.status_code == 200 and response.text.strip() == expected_response)

        if not success:
            error = f"Status: {response.status_code}, Body: {response.text[:50]}"
            return host, duration, False, error

        return host, duration, True, None

    except requests.exceptions.Timeout:
        return host, 0, False, "Request timeout"
    except requests.exceptions.RequestException as e:
        return host, 0, False, str(e)


def run_load_test():
    """Run the load test with concurrent workers"""
    print(f"🚀 Starting load test...")
    print(f"   Total requests: {TOTAL_REQUESTS}")
    print(f"   Concurrent workers: {WORKERS}")
    print(f"   Target hosts: {', '.join(HOSTS)}")
    print(f"   Base URL: {BASE_URL}")
    print()

    results = LoadTestResults()
    results.start_time = time.time()

    completed = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        # Submit all requests
        futures = [executor.submit(make_request, i) for i in range(TOTAL_REQUESTS)]

        # Process results as they complete
        for future in as_completed(futures):
            host, duration, success, error = future.result()
            results.add_result(host, duration, success, error)

            completed += 1
            if completed % 50 == 0:
                print(f"   Progress: {completed}/{TOTAL_REQUESTS} requests completed")

    results.end_time = time.time()

    return results


def format_markdown_report(summary):
    """Format results as a markdown report"""
    report = []
    report.append("# 📊 Load Test Results\n")

    # Test Info
    report.append("## Test Configuration")
    report.append(f"- **Total Requests**: {summary['test_info']['total_requests']}")
    report.append(f"- **Concurrent Workers**: {summary['test_info']['concurrent_workers']}")
    report.append(f"- **Test Duration**: {summary['test_info']['test_duration_seconds']}s")
    report.append(f"- **Timestamp**: {summary['test_info']['timestamp']}")
    report.append("")

    # Overall Stats
    report.append("## Overall Statistics")
    overall = summary['overall_stats']
    report.append(f"- **Successful Requests**: {overall['successful_requests']}")
    report.append(f"- **Failed Requests**: {overall['failed_requests']}")
    report.append(f"- **Success Rate**: {overall['success_rate_percent']}%")
    report.append(f"- **Throughput**: {overall['requests_per_second']} req/s")
    report.append("")

    # Latency Stats
    if summary.get('latency_stats'):
        report.append("## Latency Statistics")
        latency = summary['latency_stats']
        report.append(f"- **Min**: {latency['min_ms']} ms")
        report.append(f"- **Max**: {latency['max_ms']} ms")
        report.append(f"- **Mean**: {latency['mean_ms']} ms")
        report.append(f"- **Median**: {latency['median_ms']} ms")
        report.append(f"- **P90**: {latency['p90_ms']} ms")
        report.append(f"- **P95**: {latency['p95_ms']} ms")
        report.append(f"- **P99**: {latency['p99_ms']} ms")
        report.append("")

    # Host-specific Stats
    report.append("## Per-Host Statistics")
    for host, stats in summary['host_stats'].items():
        report.append(f"\n### {host}")
        report.append(f"- **Total Requests**: {stats['total_requests']}")
        report.append(f"- **Successful**: {stats['successful_requests']}")
        report.append(f"- **Failed**: {stats['failed_requests']}")
        report.append(f"- **Success Rate**: {stats['success_rate_percent']}%")

        if 'latency' in stats:
            report.append(f"- **Mean Latency**: {stats['latency']['mean_ms']} ms")
            report.append(f"- **P90 Latency**: {stats['latency']['p90_ms']} ms")
            report.append(f"- **P95 Latency**: {stats['latency']['p95_ms']} ms")

    # Errors
    if summary.get('error_samples'):
        report.append("\n## Error Samples")
        for i, error in enumerate(summary['error_samples'][:5], 1):
            report.append(f"{i}. **{error['host']}**: {error['error']}")

    return "\n".join(report)


if __name__ == "__main__":
    try:
        # Run the load test
        results = run_load_test()

        # Get summary
        summary = results.get_summary()

        # Print results to console
        print("\n" + "=" * 60)
        print("LOAD TEST COMPLETE")
        print("=" * 60)
        print(json.dumps(summary, indent=2))

        # Save JSON results
        with open('loadtest-results.json', 'w') as f:
            json.dump(summary, f, indent=2)
        print("\n✅ JSON results saved to: loadtest-results.json")

        # Generate and save markdown report
        markdown_report = format_markdown_report(summary)
        with open('loadtest-results.md', 'w') as f:
            f.write(markdown_report)
        print("✅ Markdown report saved to: loadtest-results.md")

        # Exit with error code if tests failed
        if summary['overall_stats']['failed_requests'] > 0:
            print(f"\n⚠️  Warning: {summary['overall_stats']['failed_requests']} requests failed")
            sys.exit(1)

        print("\n✅ All requests successful!")
        sys.exit(0)

    except Exception as e:
        print(f"\n❌ Error during load test: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)