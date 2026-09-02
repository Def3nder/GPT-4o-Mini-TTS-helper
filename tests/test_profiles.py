from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from markdown_tts.profiles import SpeechProfileCatalog, SpeechProfileCatalogError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROFILES_DIRECTORY = PROJECT_ROOT / "speech_profiles"


class SpeechProfileCatalogTests(unittest.TestCase):
    def test_lists_profiles_in_deterministic_order_and_includes_bundled_profiles(
        self,
    ) -> None:
        entries = SpeechProfileCatalog(PROFILES_DIRECTORY).list_entries()
        names = [entry.profile.name for entry in entries]

        self.assertEqual(names, sorted(names, key=str.casefold))
        self.assertTrue(
            {
                "audiobook",
                "coaching",
                "coaching-level1-m",
                "coaching-level1-w",
                "coaching-level2-m",
                "coaching-level2-w",
                "coaching-level3-m",
                "coaching-level3-w",
                "coaching-level4-m",
                "coaching-level4-w",
                "meditation",
                "podcast",
            }.issubset(names)
        )
        self.assertTrue(all(entry.profile.instructions for entry in entries))
        self.assertTrue(all(0.25 <= entry.profile.speed <= 4.0 for entry in entries))

    def test_resolves_profile_name_case_insensitively(self) -> None:
        profile = SpeechProfileCatalog(PROFILES_DIRECTORY).resolve("AudioBook")

        self.assertEqual(profile.name, "audiobook")
        self.assertEqual(profile.voice, "marin")
        self.assertEqual(profile.speed, 0.95)

    def test_coaching_levels_offer_male_and_female_recommended_voices(self) -> None:
        expected = {
            "coaching-level1-m": ("echo", 1.0),
            "coaching-level1-w": ("nova", 1.0),
            "coaching-level2-m": ("cedar", 1.0),
            "coaching-level2-w": ("marin", 1.0),
            "coaching-level3-m": ("onyx", 1.0),
            "coaching-level3-w": ("marin", 1.0),
            "coaching-level4-m": ("onyx", 1.0),
            "coaching-level4-w": ("shimmer", 1.0),
        }
        catalog = SpeechProfileCatalog(PROFILES_DIRECTORY)

        for name, (voice, speed) in expected.items():
            with self.subTest(profile=name):
                profile = catalog.resolve(name)
                self.assertEqual(profile.voice, voice)
                self.assertEqual(profile.speed, speed)
                self.assertTrue(profile.instructions.strip())

    def test_keeps_explicit_profile_file_compatible(self) -> None:
        profile_path = PROFILES_DIRECTORY / "podcast.json"

        profile = SpeechProfileCatalog(PROFILES_DIRECTORY).resolve(profile_path)

        self.assertEqual(profile.name, "podcast")
        self.assertEqual(profile.voice, "coral")

    def test_missing_profile_lists_available_names(self) -> None:
        available_names = ", ".join(
            entry.profile.name
            for entry in SpeechProfileCatalog(PROFILES_DIRECTORY).list_entries()
        )
        with self.assertRaisesRegex(
            SpeechProfileCatalogError,
            available_names,
        ):
            SpeechProfileCatalog(PROFILES_DIRECTORY).resolve("unknown")

    def test_rejects_duplicate_profile_names(self) -> None:
        with TemporaryDirectory(dir=PROJECT_ROOT) as directory:
            root = Path(directory)
            payload = {
                "name": "duplicate",
                "voice": "cedar",
                "speed": 1.0,
                "instructions": "Test",
            }
            (root / "first.json").write_text(json.dumps(payload), encoding="utf-8")
            (root / "second.json").write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(SpeechProfileCatalogError, "mehrfach definiert"):
                SpeechProfileCatalog(root).list_entries()


if __name__ == "__main__":
    unittest.main()
