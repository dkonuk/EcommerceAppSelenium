from typing import List, Tuple

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement

from typing import TYPE_CHECKING

from pages.base_page import BasePage


class HomePage(BasePage):



    def open(self, path: str = "") -> 'HomePage':

        super().open()
        self.wait_for_page_load()
        return self

    def is_page_loaded(self) -> bool:
        return self.is_element_present((By.ID, "page-title"))

    def get_page_title(self) -> str:
        self.wait_for_page_load()
        return self.driver.title