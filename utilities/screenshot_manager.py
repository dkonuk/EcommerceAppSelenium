"""
Failure artifact capture for test debugging.

Captures screenshots, page source, and browser logs when tests fail.
Works automatically via pytest hooks in conftest.py.

Example artifacts for failed test 'test_login':
    - screenshots/test_login_2024-03-02_15-30-45.png
    - screenshots/test_login_2024-03-02_15-30-45.html
    - screenshots/test_login_2024-03-02_15-30-45.log
"""

import os
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def _generate_timestamp():
    """
    Generate timestamp for artifact filenames.

    Returns:
        Timestamp string like '2024-03-02_15-30-45'
    """
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _sanitize_filename(test_name):
    """
    Convert test name to valid filename.

    Args:
        test_name: Test identifier like "tests/test_login.py::TestClass::test_method"

    Returns:
        Safe filename like "test_login_TestClass_test_method"
    """
    # Replace pytest path separators
    safe_name = test_name.replace("::", "_").replace("/", "_").replace("\\", "_")

    # Remove file extension
    safe_name = safe_name.replace(".py", "")

    # Remove problematic characters
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in "._-")

    return safe_name


def capture_failure_artifacts(driver, test_name, screenshot_path="screenshots"):
    """
    Capture all failure artifacts for debugging.

    Creates three files:
        1. Screenshot (.png)
        2. Page source (.html)
        3. Browser logs (.log)

    Args:
        driver: WebDriver instance
        test_name: Test identifier (from pytest)
        screenshot_path: Directory to save artifacts

    Returns:
        dict with artifact paths, or None if capture failed

    Example:
        artifacts = capture_failure_artifacts(
            driver,
            "tests/test_login.py::test_valid_login"
        )
        # Returns:
        # {
        #     'screenshot': 'screenshots/tests_test_login_test_valid_login_2024-03-02_15-30-45.png',
        #     'page_source': 'screenshots/tests_test_login_test_valid_login_2024-03-02_15-30-45.html',
        #     'logs': 'screenshots/tests_test_login_test_valid_login_2024-03-02_15-30-45.log'
        # }
    """
    try:
        # Step 1: Ensure output directory exists
        output_dir = Path(screenshot_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Output directory ready: {output_dir}")

        # Step 2: Generate base filename
        safe_name = _sanitize_filename(test_name)
        timestamp = _generate_timestamp()
        base_filename = f"{safe_name}_{timestamp}"

        logger.info(f"Capturing artifacts for: {test_name}")
        logger.debug(f"Base filename: {base_filename}")

        # Step 3: Capture screenshot
        screenshot_file = output_dir / f"{base_filename}.png"
        driver.save_screenshot(str(screenshot_file))
        logger.debug(f"Screenshot saved: {screenshot_file}")

        # Step 4: Capture page source (HTML)
        html_file = output_dir / f"{base_filename}.html"
        page_source = driver.page_source
        html_file.write_text(page_source, encoding='utf-8')
        logger.debug(f"Page source saved: {html_file}")

        # Step 5: Capture browser logs (console errors, warnings)
        log_file = output_dir / f"{base_filename}.log"
        try:
            logs = driver.get_log('browser')
            log_content = "\n".join([f"[{log['level']}] {log['message']}" for log in logs])
            log_file.write_text(log_content, encoding='utf-8')
            logger.debug(f"Browser logs saved: {log_file}")
        except Exception as e:
            # Some browsers don't support log capture
            logger.debug(f"Could not capture browser logs: {e}")
            log_file.write_text(f"Browser logs not available: {e}", encoding='utf-8')

        # Step 6: Return paths to created artifacts
        artifacts = {
            'screenshot': str(screenshot_file),
            'page_source': str(html_file),
            'logs': str(log_file)
        }

        logger.info(f"Artifacts captured successfully: {len(artifacts)} files")
        return artifacts

    except Exception as e:
        logger.error(f"Failed to capture artifacts for {test_name}: {e}")
        return None


__all__ = ['capture_failure_artifacts']