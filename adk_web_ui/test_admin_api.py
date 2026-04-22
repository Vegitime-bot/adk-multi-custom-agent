#!/usr/bin/env python3
"""
ADK Web UI Admin API Test Script
Tests for:
- Admin stats API
- Session search/filter API
- User management API
- Session deletion
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8093"
ADMIN_KNOX_ID = "admin_test"  # Change to your admin Knox ID
USER_KNOX_ID = "user_test"     # Change to non-admin Knox ID

# Colors for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

def print_header(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

def print_success(msg):
    print(f"{GREEN}✓{RESET} {msg}")

def print_error(msg):
    print(f"{RED}✗{RESET} {msg}")

def print_warning(msg):
    print(f"{YELLOW}⚠{RESET} {msg}")

def print_info(msg):
    print(f"  {msg}")

def test_endpoint(method, endpoint, headers=None, params=None, json_data=None, expected_status=200):
    """Test a single endpoint"""
    url = f"{BASE_URL}{endpoint}"
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, params=params, timeout=10)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers, timeout=10)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=json_data, timeout=10)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        success = response.status_code == expected_status
        if success:
            print_success(f"{method} {endpoint} - Status {response.status_code}")
        else:
            print_error(f"{method} {endpoint} - Expected {expected_status}, got {response.status_code}")
            print_info(f"Response: {response.text[:100]}")
        
        return success, response.json() if response.ok else None
    except requests.exceptions.ConnectionError:
        print_error(f"{method} {endpoint} - Connection refused. Is server running?")
        return False, None
    except Exception as e:
        print_error(f"{method} {endpoint} - {str(e)}")
        return False, None

def run_tests():
    """Run all admin API tests"""
    print_header("ADK Web UI Admin API Test Suite")
    print_info(f"Server URL: {BASE_URL}")
    print_info(f"Admin Knox ID: {ADMIN_KNOX_ID}")
    print_info(f"Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "tests": []
    }
    
    # Headers
    admin_headers = {"X-Knox-Id": ADMIN_KNOX_ID}
    user_headers = {"X-Knox-Id": USER_KNOX_ID}
    no_headers = {}
    
    # Test cases
    test_cases = [
        # ============ Authentication Tests ============
        ("GET", "/admin/stats", no_headers, None, None, 403, "Stats without auth"),
        ("GET", "/admin/stats", user_headers, None, None, 403, "Stats with non-admin"),
        ("GET", "/admin/stats", admin_headers, None, None, 200, "Stats with admin"),
        
        # ============ Sessions API Tests ============
        ("GET", "/admin/sessions", no_headers, None, None, 403, "Sessions without auth"),
        ("GET", "/admin/sessions", user_headers, None, None, 403, "Sessions with non-admin"),
        ("GET", "/admin/sessions", admin_headers, None, None, 200, "Sessions with admin"),
        
        # ============ Search API Tests ============
        ("GET", "/admin/sessions/search", no_headers, {"q": "test"}, None, 403, "Search without auth"),
        ("GET", "/admin/sessions/search", admin_headers, {"q": "test"}, None, 200, "Search with query"),
        ("GET", "/admin/sessions/search", admin_headers, {"q": "nonexistent"}, None, 200, "Search with no results"),
        
        # ============ Filter Tests ============
        ("GET", "/admin/sessions", admin_headers, {"limit": 5}, None, 200, "Sessions with limit"),
        ("GET", "/admin/sessions", admin_headers, {"offset": 0}, None, 200, "Sessions with offset"),
        ("GET", "/admin/sessions", admin_headers, {"is_active": "true"}, None, 200, "Sessions filter by active"),
        
        # ============ Users API Tests ============
        ("GET", "/admin/users", no_headers, None, None, 403, "Users without auth"),
        ("GET", "/admin/users", user_headers, None, None, 403, "Users with non-admin"),
        ("GET", "/admin/users", admin_headers, None, None, 200, "Users with admin"),
        ("GET", "/admin/users", admin_headers, {"limit": 10}, None, 200, "Users with limit"),
    ]
    
    print_header("Running Tests")
    
    for method, endpoint, headers, params, json_data, expected, description in test_cases:
        results["total"] += 1
        success, response_data = test_endpoint(method, endpoint, headers, params, json_data, expected)
        
        if success:
            results["passed"] += 1
        else:
            results["failed"] += 1
        
        results["tests"].append({
            "description": description,
            "passed": success,
            "endpoint": f"{method} {endpoint}"
        })
    
    # Test stats data structure
    print_header("Validating Stats Response Structure")
    success, stats = test_endpoint("GET", "/admin/stats", admin_headers, None, None, 200)
    if success and stats:
        required_fields = ["total_sessions", "total_messages", "unique_users", 
                          "today_sessions", "today_messages", "active_users_24h",
                          "agent_usage", "daily_activity"]
        for field in required_fields:
            if field in stats:
                print_success(f"Field '{field}' present in stats")
                results["passed"] += 1
            else:
                print_error(f"Field '{field}' missing from stats")
                results["failed"] += 1
        results["total"] += len(required_fields)
    
    # Test sessions data structure
    print_header("Validating Sessions Response Structure")
    success, sessions_data = test_endpoint("GET", "/admin/sessions", admin_headers, {"limit": 1}, None, 200)
    if success and sessions_data:
        if "sessions" in sessions_data:
            print_success("'sessions' array present")
            results["passed"] += 1
        else:
            print_error("'sessions' array missing")
            results["failed"] += 1
        
        if "total" in sessions_data:
            print_success("'total' count present")
            results["passed"] += 1
        else:
            print_error("'total' count missing")
            results["failed"] += 1
        
        if "filters" in sessions_data:
            print_success("'filters' object present")
            results["passed"] += 1
        else:
            print_error("'filters' object missing")
            results["failed"] += 1
        results["total"] += 3
    
    # Test search functionality
    print_header("Testing Search Functionality")
    success, search_data = test_endpoint("GET", "/admin/sessions/search", admin_headers, {"q": "a"}, None, 200)
    if success and search_data:
        if "sessions" in search_data:
            print_success(f"Search returned {len(search_data['sessions'])} results")
            results["passed"] += 1
        else:
            print_error("Search response missing sessions")
            results["failed"] += 1
        
        if "query" in search_data:
            print_success("Search response contains query")
            results["passed"] += 1
        else:
            print_error("Search response missing query")
            results["failed"] += 1
        results["total"] += 2
    
    # Summary
    print_header("Test Summary")
    print_info(f"Total Tests: {results['total']}")
    print_success(f"Passed: {results['passed']}")
    if results['failed'] > 0:
        print_error(f"Failed: {results['failed']}")
    else:
        print_success("Failed: 0")
    
    success_rate = (results['passed'] / results['total'] * 100) if results['total'] > 0 else 0
    print_info(f"Success Rate: {success_rate:.1f}%")
    
    # Print failed tests
    if results['failed'] > 0:
        print_header("Failed Tests")
        for test in results['tests']:
            if not test['passed']:
                print_error(f"{test['endpoint']}: {test['description']}")
    
    return results['failed'] == 0

def generate_report():
    """Generate a detailed test report"""
    print_header("Generating Detailed Report")
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "server_url": BASE_URL,
        "admin_knox_id": ADMIN_KNOX_ID,
        "test_results": []
    }
    
    # Run tests and capture results
    admin_headers = {"X-Knox-Id": ADMIN_KNOX_ID}
    
    endpoints = [
        ("Admin Stats", "GET", "/admin/stats"),
        ("All Sessions", "GET", "/admin/sessions"),
        ("Session Search", "GET", "/admin/sessions/search", {"q": "test"}),
        ("Filtered Sessions", "GET", "/admin/sessions", {"limit": 5, "is_active": "true"}),
        ("Users List", "GET", "/admin/users"),
    ]
    
    for name, method, endpoint, *args in endpoints:
        url = f"{BASE_URL}{endpoint}"
        params = args[0] if args else None
        try:
            response = requests.get(url, headers=admin_headers, params=params, timeout=10)
            report["test_results"].append({
                "name": name,
                "status": response.status_code,
                "success": response.status_code == 200,
                "response_sample": response.json() if response.ok else None
            })
            print_success(f"{name}: {response.status_code}")
        except Exception as e:
            report["test_results"].append({
                "name": name,
                "error": str(e),
                "success": False
            })
            print_error(f"{name}: {str(e)}")
    
    # Save report
    report_file = f"admin_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    print_success(f"Report saved to: {report_file}")
    return report

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="ADK Web UI Admin API Test Suite")
    parser.add_argument("--url", default=BASE_URL, help=f"Server URL (default: {BASE_URL})")
    parser.add_argument("--admin-knox-id", default=ADMIN_KNOX_ID, help="Admin Knox ID")
    parser.add_argument("--report", action="store_true", help="Generate detailed report")
    
    args = parser.parse_args()
    
    BASE_URL = args.url.rstrip('/')
    ADMIN_KNOX_ID = args.admin_knox_id
    
    success = run_tests()
    
    if args.report:
        generate_report()
    
    sys.exit(0 if success else 1)
