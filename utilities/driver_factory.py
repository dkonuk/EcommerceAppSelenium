"""
WebDriver factory for creating and managing browser instances.

"""

import logging
import os
from typing import Optional
from selenium import webdriver
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.edge.service import Service as EdgeService


from config.browser_config import get_browser_options, get_supported_browsers
from config.settings import TestConfig

logger = logging.getLogger(__name__)

DRIVER_REGISTRY = {
    "chrome": (webdriver.Chrome, ChromeService),
    "firefox": (webdriver.Firefox, FirefoxService),
    "edge": (webdriver.Edge, EdgeService),
}

def create_driver(config):
    """
        Create WebDriver instance from configuration.
        Uses Selenium Manager for local execution, or RemoteWebDriver for Docker Grid.
        """
    browser = config.browser.lower()
    logger.info(f"Creating {browser} driver (headless={config.headless})")

    if browser not in DRIVER_REGISTRY:
        raise ValueError(
            f"Browser '{browser}' is not supported. "
            f"Available browsers: {list(DRIVER_REGISTRY.keys())}"
        )

    # Get browser options
    options = get_browser_options(browser, headless=config.headless)
    logger.debug(f"Options configured with {len(options.arguments)} arguments")

    driver_class, service_class = DRIVER_REGISTRY[browser]

    # --- SMART ROUTING LOGIC ---
    if config.remote_execution and config.remote_url:
        # We are inside the Docker container! Shoot commands to the Grid.
        logger.info(f"Connecting to Selenium Grid at {config.remote_url}")
        driver = webdriver.Remote(
            command_executor=config.remote_url,
            options=options
        )
    else:
        # We are on your local Mac! Boot a normal local browser.
        logger.info("Local environment detected. Using Selenium Manager.")
        service = service_class()
        driver = driver_class(options=options, service=service)

    # Apply timeouts
    driver.set_page_load_timeout(config.page_load_timeout)

    logger.info(f"Driver ready: {type(driver).__name__}")
    return driver

def add_driver_config(browser_name, driver_class, service_class):
    """
    Register a new driver configuration

    Args:
        browser_name: Browser name.
        driver_class: WebDriver class.
        service_class: Service class.
    """
    DRIVER_REGISTRY[browser_name.lower()] = (driver_class, service_class)
    logger.info(f"Driver registered: {browser_name}")

__all__ = ["create_driver", "add_driver_config", "DRIVER_REGISTRY"]