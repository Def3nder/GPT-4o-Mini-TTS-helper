from pathlib import Path
import unittest

from markdown_tts.cli import (
    _build_argument_parser,
    _normalize_cli_arguments,
    _resolve_single_output_path,
    _select_automatic_synthesis_command,
)


class CliArgumentTests(unittest.TestCase):
    def test_root_help_shows_complete_synthesis_invocations_and_legend(self) -> None:
        help_text = _build_argument_parser().format_help()

        self.assertIn("VOLLSTÄNDIGE AUFRUFE MIT ALLEN OPTIONEN", help_text)
        self.assertIn("ohne Befehl (automatisch):\n  markdown-tts", help_text)
        self.assertIn("synthesize:\n  markdown-tts synthesize", help_text)
        self.assertIn("synthesize-prefill:\n  markdown-tts synthesize-prefill", help_text)
        self.assertIn("Angaben ohne eckige Klammern sind Pflicht", help_text)

    def test_inserts_automatic_command_when_invocation_starts_with_input(self) -> None:
        parser = _build_argument_parser()
        command_names = set(parser._subparsers._group_actions[0].choices)

        normalized = _normalize_cli_arguments(
            ["docs/example.md", "--profile", "audiobook"],
            command_names,
        )
        explicit = _normalize_cli_arguments(
            ["synthesize", "docs/example.md"],
            command_names,
        )

        self.assertEqual(normalized[0], "auto")
        self.assertEqual(explicit[0], "synthesize")
        parsed = parser.parse_args(normalized)
        self.assertEqual(parsed.input, Path("docs/example.md"))
        self.assertEqual(parsed.profile, "audiobook")

    def test_automatic_help_shows_commandless_invocation(self) -> None:
        parser = _build_argument_parser()
        automatic_parser = parser._subparsers._group_actions[0].choices["auto"]

        help_text = automatic_parser.format_help()

        self.assertIn("usage: markdown-tts", help_text)
        self.assertNotIn("usage: markdown-tts auto", help_text)
        self.assertIn("INPUT [OUTPUT]", help_text)

    def test_root_help_lists_every_registered_subcommand_option(self) -> None:
        parser = _build_argument_parser()
        help_text = parser.format_help()
        command_parsers = parser._subparsers._group_actions[0].choices
        command_names = list(command_parsers)

        def section_name(command_name: str) -> str:
            if command_name == "auto":
                return "ohne Befehl (automatisch)"
            return command_name

        for index, command_name in enumerate(command_names):
            section_start = help_text.index(f"\n{section_name(command_name)}:\n")
            section_end = (
                help_text.index(
                    f"\n{section_name(command_names[index + 1])}:\n"
                )
                if index + 1 < len(command_names)
                else len(help_text)
            )
            section = help_text[section_start:section_end]
            for action in command_parsers[command_name]._actions:
                for option in action.option_strings:
                    with self.subTest(command=command_name, option=option):
                        self.assertIn(option, section)

        chunks_section_start = help_text.index("\nsynthesize-chunks:\n")
        chunks_section_end = help_text.index("\ncalibrate-prefill:\n")
        self.assertIn(
            "--keep-chunks",
            help_text[chunks_section_start:chunks_section_end],
        )

    def test_synthesize_help_identifies_required_optional_and_default_profile(self) -> None:
        parser = _build_argument_parser()
        synthesize_parser = parser._subparsers._group_actions[0].choices["synthesize"]
        help_text = synthesize_parser.format_help()

        self.assertIn("usage: markdown-tts synthesize", help_text)
        self.assertIn("INPUT [OUTPUT]", help_text)
        self.assertIn("[Pflicht] Pfad zur Markdown-Datei", help_text)
        self.assertIn("[Optional] Ausgabedatei", help_text)
        self.assertIn("Standard: coaching", help_text)

    def test_output_is_optional_for_all_synthesis_commands(self) -> None:
        parser = _build_argument_parser()

        regular = parser.parse_args(["synthesize", "docs/example.md"])
        prefill = parser.parse_args(["synthesize-prefill", "docs/example.md"])
        chunks = parser.parse_args(["synthesize-chunks", "docs/example.md"])

        self.assertIsNone(regular.output)
        self.assertIsNone(prefill.output)
        self.assertIsNone(chunks.output)

    def test_chunk_synthesis_supports_profile_suffix_and_retention(self) -> None:
        arguments = _build_argument_parser().parse_args(
            [
                "synthesize-chunks",
                "docs/example.md",
                "--profile",
                "audiobook",
                "--append-profile-name",
                "--keep-chunks",
            ]
        )

        self.assertEqual(arguments.profile, "audiobook")
        self.assertTrue(arguments.append_profile_name)
        self.assertTrue(arguments.keep_chunks)

    def test_automatic_synthesis_uses_direct_path_at_limit_and_prefill_above_it(self) -> None:
        self.assertEqual(
            _select_automatic_synthesis_command(3_800, 3_800),
            "synthesize",
        )
        self.assertEqual(
            _select_automatic_synthesis_command(3_801, 3_800),
            "synthesize-prefill",
        )

    def test_default_output_replaces_input_extension_with_mp3(self) -> None:
        output = _resolve_single_output_path(
            Path("docs/example.md"),
            None,
            profile_name="coaching",
            append_profile_name=False,
        )

        self.assertEqual(output, Path("docs/example.mp3"))

    def test_profile_name_can_be_appended_to_default_or_explicit_output(self) -> None:
        default_output = _resolve_single_output_path(
            Path("docs/example.md"),
            None,
            profile_name="coaching-level2-m",
            append_profile_name=True,
        )
        explicit_output = _resolve_single_output_path(
            Path("docs/example.md"),
            Path("audio/result.mp3"),
            profile_name="coaching-level2-m",
            append_profile_name=True,
        )

        self.assertEqual(default_output, Path("docs/example_coaching-level2-m.mp3"))
        self.assertEqual(explicit_output, Path("audio/result_coaching-level2-m.mp3"))


if __name__ == "__main__":
    unittest.main()
