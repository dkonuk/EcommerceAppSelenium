from api.admin_client import AdminAPIClient

class TestAdminAPI:

    def test_database_reset_and_seed(self, test_config):
        """Verify the admin endpoints can successfully reset and seed the database."""

        # 1. Initialize the client using the URL from your settings
        admin_api = AdminAPIClient(test_config.api_url)

        # 2. Reset the database
        reset_success = admin_api.reset_database()
        assert reset_success is True, "Failed to reset database"

        # 3. Seed the database
        seed_response = admin_api.seed_database(user_count=5, product_count=20, category_count=12)
        print(seed_response)

        # 4. Verify the response contains the backend's hardcoded defaults
        assert seed_response["message"] == "Database seeded successfully"
        assert seed_response["counts"]["users"] == 10
        assert seed_response["counts"]["products"] == 100
        assert seed_response["counts"]["categories"] == 10