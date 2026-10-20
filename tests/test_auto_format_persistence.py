# -*- coding: utf-8 -*-
import os
import tempfile
import unittest
from copy import deepcopy
from unittest.mock import patch

from src.jb_quickpanel.services import app_config


class AutoFormatPersistenceTests(unittest.TestCase):
    def test_auto_format_choices_survive_settings_reload(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"APPDATA": folder}
        ):
            settings = deepcopy(app_config.DEFAULT_SETTINGS)
            settings["auto_format"] = {
                "document_title_template": "auto-title-user:document-example",
                "title_template": "auto-title-user:section-example",
                "roles": {
                    "body": {
                        "font": "함초롬바탕",
                        "size": 12,
                        "bold": True,
                        "marker": "none",
                        "custom_marker": "",
                    }
                },
            }

            app_config.save_settings(settings)
            reloaded = app_config.load_settings()

            self.assertEqual(
                reloaded["auto_format"]["document_title_template"],
                "auto-title-user:document-example",
            )
            self.assertEqual(
                reloaded["auto_format"]["title_template"],
                "auto-title-user:section-example",
            )
            self.assertEqual(
                reloaded["auto_format"]["roles"]["body"]["font"],
                "함초롬바탕",
            )
            self.assertEqual(reloaded["auto_format"]["roles"]["body"]["size"], 12)
            self.assertTrue(reloaded["auto_format"]["roles"]["body"]["bold"])
            self.assertEqual(reloaded["auto_format"]["roles"]["body"]["marker"], "none")


if __name__ == "__main__":
    unittest.main()