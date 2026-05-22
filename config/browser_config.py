"""
Browser configurations for test automation.

Provides browser options through a simple data-driven approach.
All browser settings are defined as data, not code.

Usage:
    options = get_browser_options("chrome", headless=True)
    driver = webdriver.Chrome(options=options)
"""

from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.edge.options import Options as EdgeOptions

# Browser configurations - add new browsers by adding entries here
BROWSER_CONFIGS = {
    "chrome": {
        "options_class": ChromeOptions,
        "common_args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--incognito",
            "--disable-notifications",
            "--disable-blink-features=AutomationControlled",
        ],
        "experimental_options": {
            "excludeSwitches": ["enable-automation"],
            "useAutomationExtension": False,
        },
        "headless_args": ["--headless=new", "--window-size=1920,1080"],
        "normal_args": ["--start-maximized"],
    },

    "firefox": {
        "options_class": FirefoxOptions,
        "common_args": [],
        "preferences": {
            "dom.webnotifications.enabled": False,
            "browser.privatebrowsing.autostart": True,
        },
        "headless_args": ["--headless", "--width=1920", "--height=1080"],
        "normal_args": [],
    },

    "edge": {
        "options_class": EdgeOptions,
        "common_args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--inprivate",
            "--disable-notifications",
            "--disable-blink-features=AutomationControlled",
        ],
        "experimental_options": {
            "excludeSwitches": ["enable-automation"],
            "useAutomationExtension": False,
        },
        "headless_args": ["--headless=new", "--window-size=1920,1080"],
        "normal_args": ["--start-maximized"],
    },
}


def get_browser_options(browser: str, headless: bool = False):
    """
    Get configured browser options.

    Args:
        browser: Browser name (chrome, firefox, edge) - case insensitive
        headless: Run without UI window

    Returns:
        Configured browser options object

    Raises:
        ValueError: If browser not supported

    Example:
        options = get_browser_options("chrome", headless=True)
        driver = webdriver.Chrome(options=options)
    """
    browser = browser.lower()

    if browser not in BROWSER_CONFIGS:
        supported = list(BROWSER_CONFIGS.keys())
        raise ValueError(
            f"Browser '{browser}' not supported. "
            f"Available: {supported}"
        )

    config = BROWSER_CONFIGS[browser]
    options = config["options_class"]()

    # Add common arguments
    for arg in config.get("common_args", []):
        options.add_argument(arg)

    # Add mode-specific arguments
    mode_args = config["headless_args"] if headless else config["normal_args"]
    for arg in mode_args:
        options.add_argument(arg)

    # Add experimental options (Chrome/Edge)
    for key, value in config.get("experimental_options", {}).items():
        options.add_experimental_option(key, value)

    # Add preferences (Firefox)
    for key, value in config.get("preferences", {}).items():
        options.set_preference(key, value)

    return options


def get_supported_browsers():
    """Get list of supported browser names."""
    return list(BROWSER_CONFIGS.keys())


def add_browser_config(browser_name, config):
    """
    Add or override browser configuration.

    Args:
        browser_name: Browser name
        config: Configuration dict with keys:
            - options_class: Options class (required)
            - common_args: List of arguments (optional)
            - headless_args: List of headless arguments (optional)
            - normal_args: List of normal mode arguments (optional)
            - experimental_options: Dict of experimental options (optional)
            - preferences: Dict of preferences (optional)

    Example:
        add_browser_config("safari", {
            "options_class": SafariOptions,
            "common_args": [],
            "headless_args": [],
            "normal_args": [],
        })
    """
    BROWSER_CONFIGS[browser_name.lower()] = config


__all__ = [
    'get_browser_options',
    'get_supported_browsers',
    'add_browser_config',
    'BROWSER_CONFIGS',
]