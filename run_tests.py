#!/usr/bin/env python3
"""Test runner script for ibi recovery toolkit.

This script provides convenient ways to run different test suites
and includes setup for optional dependencies.
"""

import argparse
import subprocess
import sys
from pathlib import Path


def check_dependencies():
    """Check for required and optional test dependencies."""
    required = ["pytest"]
    optional = ["pytest_cov", "pytest_timeout", "pillow", "pre_commit"]

    missing_required = []
    missing_optional = []

    for dep in required:
        try:
            __import__(dep.replace("-", "_"))
        except ImportError:
            missing_required.append(dep)

    for dep in optional:
        try:
            if dep == "pillow":
                __import__("PIL")
            else:
                __import__(dep.replace("-", "_"))
        except ImportError:
            missing_optional.append(dep)

    if missing_required:
        print(f"❌ Missing required dependencies: {', '.join(missing_required)}")
        print("Install with: poetry install --group dev")
        return False

    if missing_optional:
        print(f"⚠️  Missing optional dependencies: {', '.join(missing_optional)}")
        print(
            "Some tests may be skipped. Install with: poetry install --extras metadata"
        )

    return True


def run_tests(test_type="all", verbose=False, coverage=False):
    """Run test suite with specified options."""

    if not check_dependencies():
        return 1

    cmd = [sys.executable, "-m", "pytest"]

    # Base options
    if verbose:
        cmd.append("-v")
    else:
        cmd.append("-q")

    # Coverage options
    if coverage:
        cmd.extend(
            ["--cov=ibirecovery", "--cov-report=html", "--cov-report=term-missing"]
        )

    # Test selection
    if test_type == "unit":
        cmd.extend(["-m", "unit or not slow"])
    elif test_type == "integration":
        cmd.extend(["-m", "integration"])
    elif test_type == "cli":
        cmd.extend(["-m", "cli"])
    elif test_type == "fast":
        cmd.extend(["-m", "not slow"])
    elif test_type == "database":
        cmd.append("tests/test_database_operations.py")
    elif test_type == "export":
        cmd.append("tests/test_export_functionality.py")
    elif test_type == "files":
        cmd.append("tests/test_file_operations.py")
    elif test_type == "reference":
        cmd.append("tests/test_reference_implementation.py")
    elif test_type != "all":
        print(f"Unknown test type: {test_type}")
        return 1

    # Run tests
    print(f"🧪 Running {test_type} tests...")
    print(f"Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, cwd=Path(__file__).parent)
        return result.returncode
    except KeyboardInterrupt:
        print("\n⚠️  Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return 1


def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description="Run ibi recovery toolkit tests")

    parser.add_argument(
        "test_type",
        nargs="?",
        default="all",
        choices=[
            "all",
            "unit",
            "integration",
            "cli",
            "fast",
            "database",
            "export",
            "files",
            "reference",
        ],
        help="Type of tests to run (default: all)",
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    parser.add_argument(
        "-c", "--coverage", action="store_true", help="Run with coverage reporting"
    )

    parser.add_argument(
        "--check-deps", action="store_true", help="Only check dependencies and exit"
    )

    args = parser.parse_args()

    if args.check_deps:
        if check_dependencies():
            print("✅ All dependencies available")
            return 0
        else:
            return 1

    return run_tests(args.test_type, args.verbose, args.coverage)


if __name__ == "__main__":
    sys.exit(main())
