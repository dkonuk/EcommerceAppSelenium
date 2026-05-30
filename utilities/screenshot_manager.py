"""
Failure artifact capture for test debugging.

Captures screenshots, page source, and browser logs when tests fail.
Works automatically via pytest hooks in conftest.py.

Example artifacts for failed test 'test_login':
    - screenshots/test_login_gw0_2024-03-02_15-30-45_a3f2b1.png
    - screenshots/test_login_gw0_2024-03-02_15-30-45_a3f2b1.html
    - screenshots/test_login_gw0_2024-03-02_15-30-45_a3f2b1.log
"""

import os
import time
import uuid
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


def _get_worker_id():
    """
    Get the pytest-xdist worker ID for the current process.

    Returns:
        Worker ID string like 'gw0', 'gw1', or 'master' for sequential runs.
    """
    return os.environ.get("PYTEST_XDIST_WORKER", "master")


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
        dict with artifact paths (may be partial if some steps failed),
        or None if capture failed before producing any artifacts.

    Example:
        artifacts = capture_failure_artifacts(
            driver,
            "tests/test_login.py::test_valid_login"
        )
        # Returns:
        # {
        #     'screenshot': 'screenshots/tests_test_login_test_valid_login_gw0_2024-03-02_15-30-45_a3f2b1.png',
        #     'page_source': 'screenshots/tests_test_login_test_valid_login_gw0_2024-03-02_15-30-45_a3f2b1.html',
        #     'logs': 'screenshots/tests_test_login_test_valid_login_gw0_2024-03-02_15-30-45_a3f2b1.log'
        # }
    """
    artifacts = {}
    current_step = "initializing"
    start_total = time.monotonic()

    try:
        # Step 1: Ensure output directory exists
        current_step = "creating output directory"
        output_dir = Path(screenshot_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Output directory ready: {output_dir}")

        # Step 2: Generate base filename
        current_step = "generating filename"
        safe_name = _sanitize_filename(test_name)
        timestamp = _generate_timestamp()
        worker_id = _get_worker_id()
        unique_id = uuid.uuid4().hex[:6]
        base_filename = f"{safe_name}_{worker_id}_{timestamp}_{unique_id}"

        logger.info(
            "artifact_capture_started",
            extra={
                "test_name": test_name,
                "worker_id": worker_id,
                "base_filename": base_filename,
                "output_dir": str(output_dir),
            }
        )

        # Step 3: Capture screenshot
        current_step = "capturing screenshot"
        screenshot_file = output_dir / f"{base_filename}.png"
        step_start = time.monotonic()
        driver.save_screenshot(str(screenshot_file))
        screenshot_size = screenshot_file.stat().st_size
        if screenshot_size == 0:
            logger.warning(
                f"Screenshot saved but is empty (0 bytes): {screenshot_file}",
                extra={"test_name": test_name, "worker_id": worker_id}
            )
        else:
            logger.debug(
                f"Screenshot saved: {screenshot_file} "
                f"({screenshot_size / 1024:.1f}KB, "
                f"{time.monotonic() - step_start:.2f}s)"
            )
        artifacts['screenshot'] = str(screenshot_file)

        # Step 4: Capture page source (HTML)
        current_step = "capturing page source"
        html_file = output_dir / f"{base_filename}.html"
        step_start = time.monotonic()
        page_source = driver.page_source
        html_file.write_text(page_source, encoding='utf-8')
        html_size = html_file.stat().st_size
        logger.debug(
            f"Page source saved: {html_file} "
            f"({html_size / 1024:.1f}KB, "
            f"{time.monotonic() - step_start:.2f}s)"
        )
        artifacts['page_source'] = str(html_file)

        # Step 5: Capture browser logs (console errors, warnings)
        current_step = "capturing browser logs"
        log_file = output_dir / f"{base_filename}.log"
        step_start = time.monotonic()
        try:
            logs = driver.get_log('browser')
            log_content = "\n".join([f"[{log['level']}] {log['message']}" for log in logs])
            log_file.write_text(log_content, encoding='utf-8')
            logger.debug(
                f"Browser logs saved: {log_file} "
                f"({len(logs)} entries, "
                f"{time.monotonic() - step_start:.2f}s)"
            )
        except Exception as e:
            # Some browsers (Firefox) don't support log capture by default
            logger.warning(
                f"Browser log capture unavailable for {test_name}: {type(e).__name__}: {e}",
                extra={"test_name": test_name, "worker_id": worker_id}
            )
            log_file.write_text(f"Browser logs not available: {e}", encoding='utf-8')
        artifacts['logs'] = str(log_file)

        # Step 6: Return paths to created artifacts
        total_elapsed = time.monotonic() - start_total
        logger.info(
            "artifact_capture_completed",
            extra={
                "test_name": test_name,
                "worker_id": worker_id,
                "artifact_count": len(artifacts),
                "total_elapsed_seconds": round(total_elapsed, 2),
                "artifacts": artifacts,
            }
        )
        return artifacts

    except Exception as e:
        total_elapsed = time.monotonic() - start_total
        logger.error(
            f"Artifact capture failed at step '{current_step}' for {test_name}",
            exc_info=True,
            extra={
                "test_name": test_name,
                "worker_id": _get_worker_id(),
                "failed_step": current_step,
                "error_type": type(e).__name__,
                "elapsed_before_failure_seconds": round(total_elapsed, 2),
                "partial_artifacts": artifacts,
            }
        )
        return artifacts if artifacts else None


__all__ = ['capture_failure_artifacts', '_get_worker_id']