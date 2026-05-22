from selenium.webdriver.common.by import By

from pages.home_page import HomePage
import time

class TestSystemCheck:
    def test_system_check(self, driver, test_config):
        home_page = HomePage(driver, test_config)
        home_page.open()
        time.sleep(2)
        assert home_page.get_page_title() == "Ecommerce Test Platform", "System check failed"