import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from src.jb_quickpanel.services import user_backup
from src.jb_quickpanel.services.user_backup import (
    BACKUP_APP_ID,
    UserBackupError,
    create_user_backup,
    restore_user_backup,
)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class UserBackupTests(unittest.TestCase):
    def test_text_only_kedufine_form_survives_backup_and_restore(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            target = root / "target"
            backup = root / "transfer.jbhbackup"
            form = {"id": "text1", "title": "내 기안문", "category": "internal", "body": "1. 관련: 예시\n2. 본문"}
            write_json(source / "user_content" / "library.json", {"version": 5, "kedufine_forms": [form]})
            create_user_backup(backup, app_root=source)
            restore_user_backup(backup, app_root=target)
            restored = json.loads((target / "user_content" / "library.json").read_text(encoding="utf-8"))
            self.assertEqual(restored["kedufine_forms"], [form])

    def test_backup_restores_both_style_formats_and_kedufine_form(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            target = root / "target"
            backup = root / "transfer.jbhbackup"
            library = {
                "version": 5,
                "styles": [{"id": "s1", "title": "서식", "file": "styles/s1.hwpx", "kedufine_file": "styles/s1.hwp"}],
                "forms": [],
                "kedufine_forms": [{"id": "k1", "title": "기안문", "document_title": "제목", "file": "kedufine_forms/k1.hwp", "hwpx_file": "kedufine_forms/k1.hwpx"}],
            }
            write_json(source / "user_content" / "library.json", library)
            for relative in ("styles/s1.hwpx", "styles/s1.hwp", "kedufine_forms/k1.hwp", "kedufine_forms/k1.hwpx"):
                path = source / "user_content" / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(relative.encode())
            create_user_backup(backup, app_root=source)
            with zipfile.ZipFile(backup) as archive:
                for relative in ("styles/s1.hwpx", "styles/s1.hwp", "kedufine_forms/k1.hwp", "kedufine_forms/k1.hwpx"):
                    self.assertIn(f"user_content/{relative}", archive.namelist())
            restore_user_backup(backup, app_root=target)
            self.assertEqual(json.loads((target / "user_content" / "library.json").read_text(encoding="utf-8"))["kedufine_forms"][0]["document_title"], "제목")
            for relative in ("styles/s1.hwpx", "styles/s1.hwp", "kedufine_forms/k1.hwp", "kedufine_forms/k1.hwpx"):
                self.assertTrue((target / "user_content" / relative).is_file())

    def test_oversized_backup_is_rejected_before_creating_unrestorable_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "data"
            user_files = root / "user_content" / "styles"
            user_files.mkdir(parents=True)
            (user_files / "large.hwp").write_bytes(b"x" * 4096)
            destination = Path(folder) / "backup.jbhbackup"
            with patch.object(user_backup, "MAX_BACKUP_UNCOMPRESSED_BYTES", 2048):
                with self.assertRaisesRegex(UserBackupError, "백업 한도"):
                    create_user_backup(destination, app_root=root)
            self.assertFalse(destination.exists())

    def test_legacy_auto_format_survives_restore_migration(self):
        settings = user_backup._normalized_settings({
            "version": 9,
            "auto_format": {"roles": {"body": {"font": "함초롬바탕", "size": 11}}},
        })
        self.assertEqual(settings["auto_format_profiles"], [])
        from src.jb_quickpanel.features.auto_format_settings import normalize_auto_format_profile_state

        migrated = normalize_auto_format_profile_state(
            settings["auto_format_profiles"],
            settings["active_auto_format_profile"],
            settings["auto_format"],
        )
        self.assertEqual(migrated["auto_format_profiles"][0]["settings"]["roles"]["body"]["font"], "함초롬바탕")

    def test_backup_and_restore_settings_and_all_user_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            target = root / "target"
            backup = root / "transfer.jbhbackup"

            write_json(
                source / "settings.json",
                {
                    "version": 9,
                    "always_on_top": False,
                    "toggle_hotkey": "Ctrl+Shift+J",
                    "active_auto_format_profile": "plan",
                    "auto_format_profiles": [
                        {
                            "id": "plan",
                            "name": "계획서",
                            "settings": {"roles": {"body": {"font": "맑은 고딕"}}},
                        }
                    ],
                    "last_geometry": "500x820+2200+400",
                    "start_menu_auto_done": True,
                    "start_menu_signature": "old-machine",
                },
            )
            library = {
                "version": 4,
                "styles": [
                    {
                        "id": "style1",
                        "title": "내 서식",
                        "file": "styles/style1.hwp",
                        "thumb": "previews/style1.png",
                    }
                ],
                "forms": [],
                "pages": [{"id": "page1", "title": "내 편집용지", "margins": {}}],
                "auto_title_templates": [],
                "symbol_groups": [{"id": "chars1", "title": "내 문자표", "chars": ["※"]}],
                "picture_symbols": [
                    {
                        "id": "image1",
                        "title": "내 심볼",
                        "file": "picture_symbols/image1.png",
                    }
                ],
            }
            write_json(source / "user_content" / "library.json", library)
            (source / "user_content" / "styles").mkdir(parents=True)
            (source / "user_content" / "styles" / "style1.hwp").write_bytes(b"hwp")
            (source / "user_content" / "previews").mkdir()
            (source / "user_content" / "previews" / "style1.png").write_bytes(b"png")
            (source / "user_content" / "picture_symbols").mkdir()
            (source / "user_content" / "picture_symbols" / "image1.png").write_bytes(b"image")
            (source / "user_content" / "pending").mkdir()
            (source / "user_content" / "pending" / "temporary.hwp").write_bytes(b"temp")

            result = create_user_backup(
                backup,
                app_root=source,
                app_version="v.4.1.5",
                integration={"startup": True, "start_menu": False},
            )
            self.assertEqual(Path(result["path"]), backup.resolve())
            with zipfile.ZipFile(backup) as archive:
                names = set(archive.namelist())
            self.assertIn("settings.json", names)
            self.assertIn("user_content/styles/style1.hwp", names)
            self.assertIn("user_content/picture_symbols/image1.png", names)
            self.assertNotIn("user_content/pending/temporary.hwp", names)

            write_json(target / "settings.json", {"always_on_top": True})
            write_json(
                target / "user_content" / "library.json",
                {
                    "version": 4,
                    "styles": [],
                    "forms": [],
                    "pages": [],
                    "auto_title_templates": [],
                    "symbol_groups": [],
                    "picture_symbols": [],
                },
            )
            restored = restore_user_backup(
                backup,
                app_root=target,
                app_version="v.4.1.5",
                integration={"startup": False, "start_menu": True},
            )

            settings = json.loads((target / "settings.json").read_text(encoding="utf-8"))
            restored_library = json.loads(
                (target / "user_content" / "library.json").read_text(encoding="utf-8")
            )
            self.assertFalse(settings["always_on_top"])
            self.assertEqual(settings["toggle_hotkey"], "Ctrl+Shift+J")
            self.assertEqual(settings["active_auto_format_profile"], "plan")
            self.assertEqual(settings["auto_format_profiles"][0]["name"], "계획서")
            self.assertEqual(settings["last_geometry"], "")
            self.assertFalse(settings["start_menu_auto_done"])
            self.assertEqual(settings["start_menu_signature"], "")
            self.assertEqual(restored_library["styles"][0]["title"], "내 서식")
            self.assertTrue((target / "user_content" / "styles" / "style1.hwp").is_file())
            self.assertTrue((target / "user_content" / "picture_symbols" / "image1.png").is_file())
            self.assertFalse((target / "user_content" / "pending").exists())
            self.assertEqual(restored["integration"], {"startup": True, "start_menu": False})
            self.assertTrue(Path(restored["recovery_path"]).is_file())

    def test_backup_does_not_include_itself_inside_user_content(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_json(root / "settings.json", {"always_on_top": True})
            write_json(
                root / "user_content" / "library.json",
                {
                    "version": 4,
                    "styles": [],
                    "forms": [],
                    "pages": [],
                    "auto_title_templates": [],
                    "symbol_groups": [],
                    "picture_symbols": [],
                },
            )
            backup = root / "user_content" / "portable.jbhbackup"
            create_user_backup(backup, app_root=root)

            with zipfile.ZipFile(backup) as archive:
                names = archive.namelist()
            self.assertFalse(any("portable.jbhbackup" in name for name in names))
            self.assertFalse(any(name.endswith(".tmp") for name in names))

    def test_restore_rolls_back_when_settings_install_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            target = root / "target"
            backup = root / "transfer.jbhbackup"
            write_json(source / "settings.json", {"always_on_top": False})
            write_json(
                source / "user_content" / "library.json",
                {
                    "version": 4,
                    "styles": [],
                    "forms": [],
                    "pages": [{"id": "new", "title": "새 자료", "margins": {}}],
                    "auto_title_templates": [],
                    "symbol_groups": [],
                    "picture_symbols": [],
                },
            )
            create_user_backup(backup, app_root=source)

            old_settings = {"always_on_top": True, "toggle_hotkey": "Ctrl+Alt+H"}
            old_library = {
                "version": 4,
                "styles": [],
                "forms": [],
                "pages": [{"id": "old", "title": "기존 자료", "margins": {}}],
                "auto_title_templates": [],
                "symbol_groups": [],
                "picture_symbols": [],
            }
            write_json(target / "settings.json", old_settings)
            write_json(target / "user_content" / "library.json", old_library)

            real_replace = user_backup.os.replace

            def fail_settings_install(source_path, destination_path):
                if Path(source_path).name.startswith(".settings_restore_"):
                    raise OSError("simulated settings failure")
                return real_replace(source_path, destination_path)

            with patch.object(user_backup.os, "replace", side_effect=fail_settings_install):
                with self.assertRaises(OSError):
                    restore_user_backup(backup, app_root=target)

            self.assertEqual(
                json.loads((target / "settings.json").read_text(encoding="utf-8")),
                old_settings,
            )
            self.assertEqual(
                json.loads(
                    (target / "user_content" / "library.json").read_text(
                        encoding="utf-8"
                    )
                ),
                old_library,
            )
    def test_restore_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            backup = root / "unsafe.jbhbackup"
            with zipfile.ZipFile(backup, "w") as archive:
                archive.writestr(
                    "manifest.json",
                    json.dumps(
                        {
                            "app_id": BACKUP_APP_ID,
                            "format_version": 1,
                            "integration": {},
                        }
                    ),
                )
                archive.writestr("settings.json", "{}")
                archive.writestr(
                    "user_content/library.json",
                    json.dumps(
                        {
                            "version": 4,
                            "styles": [],
                            "forms": [],
                            "pages": [],
                            "auto_title_templates": [],
                            "symbol_groups": [],
                            "picture_symbols": [],
                        }
                    ),
                )
                archive.writestr("../outside.txt", "blocked")

            with self.assertRaises(UserBackupError):
                restore_user_backup(backup, app_root=root / "app")

            self.assertFalse((root / "outside.txt").exists())

    def test_restore_rejects_another_program_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            backup = root / "other.jbhbackup"
            with zipfile.ZipFile(backup, "w") as archive:
                archive.writestr(
                    "manifest.json",
                    json.dumps({"app_id": "OTHER", "format_version": 1}),
                )
                archive.writestr("settings.json", "{}")
                archive.writestr("user_content/library.json", "{}")

            with self.assertRaisesRegex(UserBackupError, "다른 프로그램"):
                restore_user_backup(backup, app_root=root / "app")


if __name__ == "__main__":
    unittest.main()
