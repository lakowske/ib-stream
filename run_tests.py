#!/usr/bin/env python3
"""
Clean Test Runner for IB-Stream Test Suite
VS Code compatible test execution script.
"""

import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_services():
    """Check if supervisor services are running"""
    try:
        result = subprocess.run(['./supervisor-wrapper.sh', 'status'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            logger.info("✅ Supervisor services are running")
            return True
        else:
            logger.warning("⚠️  Supervisor services may not be running")
            return False
    except Exception as e:
        logger.warning(f"Could not check supervisor status: {e}")
        return False

def run_integration_tests():
    """Run the integration test suite"""
    logger.info("🧪 Running Integration Tests...")
    
    cmd = [sys.executable, '-m', 'pytest', 'tests/test_system_integration.py', '-v']
    result = subprocess.run(cmd, cwd=Path.cwd())
    
    if result.returncode == 0:
        logger.info("✅ Integration tests PASSED")
        return True
    else:
        logger.error("❌ Integration tests FAILED")
        return False

def run_bdd_tests():
    """Run the BDD functional tests"""
    logger.info("🎯 Running BDD Functional Tests...")
    
    cmd = [sys.executable, 'tests/test_mnq_functional.py']
    result = subprocess.run(cmd, cwd=Path.cwd())
    
    if result.returncode == 0:
        logger.info("✅ BDD tests PASSED")
        return True
    else:
        logger.error("❌ BDD tests FAILED")
        return False

def run_all_tests():
    """Run all tests together"""
    logger.info("🚀 Running All Tests Together...")
    
    cmd = [sys.executable, '-m', 'pytest', 
           'tests/test_system_integration.py', 
           'tests/test_mnq_functional.py', 
           '-v']
    result = subprocess.run(cmd, cwd=Path.cwd())
    
    if result.returncode == 0:
        logger.info("✅ All tests PASSED")
        return True
    else:
        logger.error("❌ Some tests FAILED")
        return False

def main():
    """Main test runner"""
    print("=" * 70)
    print("IB-STREAM TEST SUITE")
    print("=" * 70)
    print(f"Started at: {datetime.now().isoformat()}")
    print()
    
    # Check services first
    services_ok = check_services()
    if not services_ok:
        print("\n⚠️  Warning: Services may not be running. Start with: make start-supervisor")
        print("Continuing with tests anyway...\n")
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        test_type = sys.argv[1].lower()
        
        if test_type in ['integration', 'int']:
            success = run_integration_tests()
        elif test_type in ['bdd', 'functional']:
            success = run_bdd_tests()
        elif test_type in ['all', 'full']:
            success = run_all_tests()
        else:
            print(f"Unknown test type: {test_type}")
            print("Usage: python run_tests.py [integration|bdd|all]")
            return 1
    else:
        # Default: run all tests
        success = run_all_tests()
    
    print("\n" + "=" * 70)
    print("TEST SUITE SUMMARY")
    print("=" * 70)
    
    if success:
        print("✅ ALL TESTS PASSED - System is ready for production!")
        return 0
    else:
        print("❌ SOME TESTS FAILED - Check logs above for details")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)