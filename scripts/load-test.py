#!/usr/bin/env python3

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

HOSTS = ["foo.localhost", "bar.localhost"]


def get_ingress_pod():
    """Get the ingress gateway pod name"""
    try:
        result = subprocess.run([
            'kubectl', 'get', 'pod',
            '-n', 'istio-system',
            '-l', 'app=istio-ingressgateway',
            '-o', 'jsonpath={.items[0].metadata.name}'
        ], capture_output=True, text=True, check=True)
        pod_name = result.stdout.strip()
        if not pod_name:
            raise Exception("No ingress gateway pod found")
        return pod_name
    except subprocess.CalledProcessError as e:
        print(f"Error getting ingress pod: {e}")
        sys.exit(1)


# Get ingress pod once at startup
INGRESS_POD = get_ingress_pod()
print(f"Using ingress gateway pod: {INGRESS_POD}")


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
                "timestamp": datetime.now().isoformat(),
                "method": "kubectl_exec"
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
    """
    Make a single HTTP request using kubectl exec into the ingress gateway pod.
    This works in Kind clusters where localhost:NodePort is not accessible.
    """
    host = random.choice(HOSTS)
    expected_response = host.split('.')[0]  # "foo" from "foo.localhost"

    try:
        start_time = time.time()

        # CRITICAL FIX: Use kubectl exec to run curl inside the ingress gateway pod
        # This is the same approach that fixed the health checks
        result = subprocess.run([
            'kubectl', 'exec',
            '-n', 'istio-system',
            INGRESS_POD,
            '--',
            'curl',
            '-s',  # silent
            '-m', str(TIMEOUT),  # timeout
            '-w', '\\n%{http_code}',  # write HTTP code on new line
            '-H', f'Host: {host}',
            'http://localhost:8080/'
        ], capture_output=True, text=True, timeout=TIMEOUT + 2)

        duration = time.time() - start_time

        # Parse response: body on first line(s), HTTP code on last line
        output = result.stdout.strip()
        if not output:
            return host, duration, False, "Empty response"

        lines = output.split('\n')
        if len(lines) >= 2:
            body = lines[0].strip()
            http_code = lines[-1].strip()
        else:
            body = output.strip()
            http_code = "000"

        # Verify response
        success = (http_code == "200" and body == expected_response)

        if not success:
            error = f"Status: {http_code}, Body: '{body[:50]}', Expected: '{expected_response}'"
            return host, duration, False, error

        return host, duration, True, None

    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return host, duration, False, "Request timeout"
    except subprocess.CalledProcessError as e:
        duration = time.time() - start_time
        error = f"kubectl exec failed: {e.stderr[:100] if e.stderr else 'unknown error'}"
        return host, duration, False, error
    except Exception as e:
        duration = time.time() - start_time
        return host, duration, False, str(e)


def run_load_test():
    """Run the load test with concurrent workers"""
    print(f"🚀 Starting load test...")
    print(f"   Total requests: {TOTAL_REQUESTS}")
    print(f"   Concurrent workers: {WORKERS}")
    print(f"   Target hosts: {', '.join(HOSTS)}")
    print(f"   Method: kubectl exec into {INGRESS_POD}")
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
                success_rate = round((results.successful_requests / completed) * 100, 1)
                print(f"   Progress: {completed}/{TOTAL_REQUESTS} requests completed ({success_rate}% success)")

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
    report.append(f"- **Method**: {summary['test_info']['method']}")
    report.append(f"- **Timestamp**: {summary['test_info']['timestamp']}")
    report.append("")

    # Overall Stats
    report.append("## Overall Statistics")
    overall = summary['overall_stats']

    # Add emoji indicators
    success_emoji = "✅" if overall['success_rate_percent'] >= 95 else "⚠️" if overall[
                                                                                  'success_rate_percent'] >= 80 else "❌"

    report.append(f"- **Successful Requests**: {overall['successful_requests']}")
    report.append(f"- **Failed Requests**: {overall['failed_requests']}")
    report.append(f"- **Success Rate**: {success_emoji} {overall['success_rate_percent']}%")
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

        host_success_emoji = "✅" if stats['success_rate_percent'] >= 95 else "⚠️" if stats[
                                                                                         'success_rate_percent'] >= 80 else "❌"

        report.append(f"- **Total Requests**: {stats['total_requests']}")
        report.append(f"- **Successful**: {stats['successful_requests']}")
        report.append(f"- **Failed**: {stats['failed_requests']}")
        report.append(f"- **Success Rate**: {host_success_emoji} {stats['success_rate_percent']}%")

        if 'latency' in stats:
            report.append(f"- **Mean Latency**: {stats['latency']['mean_ms']} ms")
            report.append(f"- **Median Latency**: {stats['latency']['median_ms']} ms")
            report.append(f"- **P90 Latency**: {stats['latency']['p90_ms']} ms")
            report.append(f"- **P95 Latency**: {stats['latency']['p95_ms']} ms")

    # Errors
    if summary.get('error_samples'):
        report.append("\n## Error Samples")
        for i, error in enumerate(summary['error_samples'][:10], 1):
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

        # Exit with appropriate code
        success_rate = summary['overall_stats']['success_rate_percent']

        if success_rate >= 95:
            print(f"\n✅ Load test passed! Success rate: {success_rate}%")
            sys.exit(0)
        elif success_rate >= 80:
            print(f"\n⚠️  Load test completed with warnings. Success rate: {success_rate}%")
            sys.exit(0)  # Still exit 0 but with warning
        else:
            print(f"\n❌ Load test failed! Success rate: {success_rate}%")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n⚠️  Load test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during load test: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)