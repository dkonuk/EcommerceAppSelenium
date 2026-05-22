"""Usage:
------
    from helpers.factories import UserFactory, ProductFactory

    # Fully random user
    user = UserFactory.create()

    # Override specific fields
    user = UserFactory.create(name="John Doe", country="United States")

    # Fully random product data
    product = ProductFactory.create()

    # Override specific fields
    product = ProductFactory.create(search_term="dress")
"""

import random
import string
from uuid import uuid4

class UserFactory:
    """
    Generates realistic user data for registration and login flows.

    All fields map directly to the automationexercise.com registration form (TC1).
    Every field has a sensible random default but can be overridden individually.
    """

    # Title options available on the registration form
    _TITLES = ["Mr", "Mrs"]

    # Country options available on the registration from dropdown
    _COUNTRIES = [
        "India",
        "United States",
        "Canada",
        "Australia",
        "Israel",
        "New Zealand",
        "Singapore",
    ]

    # Realistic first names for generated data
    _FIRST_NAMES = [
        "James", "Emma", "Oliver", "Sophia", "William",
        "Isabella", "Benjamin", "Mia", "Lucas", "Charlotte"
    ]

    # Realistic last names for generated data
    _LAST_NAMES = [
        "Smith", "Johnson", "Williams", "Brown", "Jones",
        "Garcia", "Miller", "Davis", "Wilson", "Taylor"
    ]

    # Realistic city names for generated data
    _CITIES = [
        "New York", "London", "Sydney", "Toronto", "Mumbai",
        "Berlin", "Paris", "Singapore", "Dubai", "Tokyo"
    ]

    @staticmethod
    def _random_string(length: int = 6) -> str:
        return "".join(random.choices(string.ascii_lowercase, k=length))

    @staticmethod
    def _random_digits(length: int = 10) -> str:
        return "".join(random.choices(string.digits, k=length))

    @classmethod
    def create(cls, **kwargs) -> dict:
        """
        Creates a complete user data dictionary with random defaults.

        Any field can be overridden by passing it as a keyword argument.

        Fields match the automationexercise.com registration form exactly:
        - name:          Full name (used on login page signup form)
        - email:         UUID-based unique email (used on login page signup form)
        - password:      Meets typical password requirements
        - title:         Mr or Mrs (radio button on registration form)
        - first_name:    First name field on registration form
        - last_name:     Last name field on registration form
        - date_of_birth: Dict with day, month, year (separate dropdowns)
        - company:       Optional company field
        - address:       Primary address line
        - address2:      Secondary address line (optional)
        - country:       Country dropdown selection
        - state:         State field
        - city:          City field
        - zipcode:       Zip/postal code
        - mobile_number: Mobile phone number

        Returns:
            dict: Complete user data with all fields populated.

        Examples:
            # Fully random
            user = UserFactory.create()

            # Override name and email for a specific scenario (e.g. TC5 duplicate email)
            user = UserFactory.create(email="already_registered@test.com")
        """
        first_name = random.choice(cls._FIRST_NAMES)
        last_name = random.choice(cls._LAST_NAMES)

        defaults = {
        # --- Registration form fields ---
        "name": f"{first_name} {last_name}",
        "email": f"user_{uuid4().hex[:8]}@testmail.com",
        "password": f"Test@{cls._random_string(4)}123",
        "title": random.choice(cls._TITLES),
        "first_name": first_name,
        "last_name": last_name,
        "date_of_birth": {
            "day": str(random.randint(1, 28)),  # Max 28 avoids month-end edge cases
            "month": str(random.randint(1, 12)),
            "year": str(random.randint(1970, 2000)),
        },

        # --- Address fields ---
        "company": f"{cls._random_string(6).capitalize()} Ltd",
        "address": f"{random.randint(1, 999)} {cls._random_string(8).capitalize()} Street",
        "address2": f"Apt {random.randint(1, 50)}",
        "country": random.choice(cls._COUNTRIES),
        "state": cls._random_string(6).capitalize(),
        "city": random.choice(cls._CITIES),
        "zipcode": cls._random_digits(5),
        "mobile_number": cls._random_digits(10),
        }

        # kwargs override any matching default key.
        # Fields not in defaults but passed via kwargs are also included
        return {**defaults, **kwargs}

class ProductFactory:
    """
    Generates product-related test data for search and review flows.

    Covers TC9 (search), TC21 (product review), and any future product tests.
    """

    # Realistic search terms that exist on automationexercise.com
    _SEARCH_TERMS = [
        "dress", "top", "jeans", "tshirt", "saree",
        "polo", "shirt", "skirt", "blouse", "kurta"
    ]

    # Realistic review texts
    _REVIEW_TEXTS = [
        "Great product, very comfortable and exactly as described.",
        "Good quality for the price. Would recommend.",
        "Fast shipping and product matches the photos perfectly.",
        "Decent quality but sizing runs a bit small.",
        "Excellent value for money. Very happy with my purchase.",
    ]

    @staticmethod
    def _random_string(length: int = 6) -> str:
        """Generates a short random alphabetic string."""
        return "".join(random.choices(string.ascii_lowercase, k=length))

    @classmethod
    def create(cls, **kwargs) -> dict:
        """
        Creates a complete product test data dictionary with random defaults.

        Any field can be overridden by passing it as a keyword argument.

        Fields:
        - search_term:   Keyword to search for on the products page (TC9)
        - review_name:   Name to submit with a product review (TC21)
        - review_email:  Email to submit with a product review (TC21)
        - review_text:   Review body text (TC21)

        Returns:
            dict: Product test data with all fields populated.

        Examples:
            # Fully random
            product = ProductFactory.create()

            # Override search term for a specific test
            product = ProductFactory.create(search_term="dress")
        """
        defaults = {
            "search_term": random.choice(cls._SEARCH_TERMS),
            "review_name": f"Reviewer {cls._random_string(4).capitalize()}",
            "review_email": f"review_{uuid4().hex[:8]}@testmail.com",
            "review_text": random.choice(cls._REVIEW_TEXTS),
        }

        return {**defaults, **kwargs}




