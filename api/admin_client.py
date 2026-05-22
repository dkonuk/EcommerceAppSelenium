import requests
import logging

logger = logging.getLogger(__name__)

class AdminAPIClient:
    """Client for interacting with the Ecommerce Admin/Testing endpoints."""

    def __init__(self, api_url: str):
        self.api_url = api_url
        self.session = requests.Session()

    def reset_database(self) -> bool:
        """
        Hits POST /api/admin/reset to clear all data
        Returns True if successful
        """
        endpoint = f"{self.api_url}/api/admin/reset"
        logger.info(f"Resetting database via API {endpoint}")

        response = self.session.post(endpoint)
        response.raise_for_status() # Fails the test if it returns 4xx or 5xx
        return True

    def seed_database(self, user_count: int = 10, product_count: int = 100, category_count: int = 10) -> dict:
        """
        Hits POST /api/admin/seed to populate test data.
        Note: The backend currently ignores custom counts and uses static defaults.
        """
        endpoint = f"{self.api_url}/api/admin/seed"
        logger.info("Seeding database with default static test data.")

        # We don't need to pass the json=payload anymore
        response = self.session.post(endpoint)
        response.raise_for_status()
        return response.json()