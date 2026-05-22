import requests
import logging

logger = logging.getLogger(__name__)

class AuthAPIClient:
    def __init__(self, api_url: str):
        self.api_url = api_url.rstrip("/")
        self.login_endpoint = f"{self.api_url}/api/auth/login"
        self.session = requests.Session()

    def get_jwt_token(self, email: str, password: str) -> str:
        """Authenticates via API and returns the JWT token."""
        payload = {"email": email, "password": password}
        response = self.session.post(self.login_endpoint, json=payload)

        if response.status_code != 200:
            logger.error(f"Failed to authenticate {email}. Status: {response.status_code}")
            raise RuntimeError(f"API Login failed: {response.text}")

        data = response.json()
        logger.debug(f"Auth response received for {email}")  # no token in logs
        token = data.get("token")

        if not token:
            raise ValueError("Token not found in authentication response.")

        return token