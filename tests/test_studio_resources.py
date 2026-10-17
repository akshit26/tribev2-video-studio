import unittest
from unittest.mock import patch

from studio_resources import ResourcePressureError, require_memory


class ResourceTests(unittest.TestCase):
    def test_start_threshold_and_runtime_reserve(self):
        with patch("studio_resources.memory_info", return_value={"available_mb": 2800}):
            require_memory()
        with patch("studio_resources.memory_info", return_value={"available_mb": 1400}):
            with self.assertRaisesRegex(ResourcePressureError, "Close unused apps"):
                require_memory()
            require_memory(768)
        with patch("studio_resources.memory_info", return_value={"available_mb": 767}):
            with self.assertRaises(ResourcePressureError):
                require_memory(768)
