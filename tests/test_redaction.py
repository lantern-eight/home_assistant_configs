"""Tests for the pure text-transformation functions: shorten_ids, redact_names_in_text, neutralize_pronouns."""

import pytest

from home_assistant_backup import shorten_ids, redact_names_in_text, neutralize_pronouns


# ---------------------------------------------------------------------------
# shorten_ids
# ---------------------------------------------------------------------------

class TestShortenIds:

    def test_exact_32_char_hex_is_shortened(self):
        hex_id = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
        assert len(hex_id) == 32
        result = shorten_ids(hex_id)
        assert result == "a1...d4"

    def test_uppercase_hex_is_shortened(self):
        hex_id = "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4"
        result = shorten_ids(hex_id)
        assert result == "A1...D4"

    def test_mixed_case_hex_is_shortened(self):
        hex_id = "aAbBcCdDeEfF00112233445566778899"
        result = shorten_ids(hex_id)
        assert result == "aA...99"

    def test_shorter_hex_untouched(self):
        short = "a1b2c3d4e5f6"
        assert shorten_ids(short) == short

    def test_longer_hex_untouched(self):
        long_hex = "a" * 33
        assert shorten_ids(long_hex) == long_hex

    def test_31_char_hex_untouched(self):
        almost = "a" * 31
        assert shorten_ids(almost) == almost

    def test_non_hex_32_chars_untouched(self):
        not_hex = "g1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
        assert shorten_ids(not_hex) == not_hex

    def test_multiple_ids_in_text(self):
        id1 = "11111111111111111111111111111111"
        id2 = "22222222222222222222222222222222"
        text = f"device: {id1}\nentity: {id2}"
        result = shorten_ids(text)
        assert "11...11" in result
        assert "22...22" in result
        assert id1 not in result
        assert id2 not in result

    def test_id_embedded_in_yaml(self):
        yaml_content = "  unique_id: abcdef01234567890abcdef012345678\n  name: Light"
        result = shorten_ids(yaml_content)
        assert result == "  unique_id: ab...78\n  name: Light"

    def test_empty_string(self):
        assert shorten_ids("") == ""

    def test_no_ids_returns_unchanged(self):
        text = "just some regular text with no hex ids"
        assert shorten_ids(text) == text

    def test_id_with_hyphen_separator(self):
        """Hyphens are word boundaries, so IDs next to hyphens are still shortened."""
        hex_id = "abcdef01234567890abcdef012345678"
        text = f"prefix-{hex_id}-suffix"
        result = shorten_ids(text)
        assert result == "prefix-ab...78-suffix"

    def test_id_embedded_in_longer_alnum_not_matched(self):
        """A 32-char hex substring inside a longer alphanumeric token is not matched."""
        hex_id = "abcdef01234567890abcdef012345678"
        text = f"x{hex_id}y"
        result = shorten_ids(text)
        assert result == text


# ---------------------------------------------------------------------------
# redact_names_in_text
# ---------------------------------------------------------------------------

class TestRedactNamesInText:

    def test_simple_name_redaction(self):
        result = redact_names_in_text("Hello Alice", ["Alice"])
        assert result == "Hello <person>"

    def test_case_insensitive(self):
        result = redact_names_in_text("hello alice and ALICE", ["Alice"])
        assert result == "hello <person> and <person>"

    def test_multiple_names(self):
        result = redact_names_in_text("Alice and Bob went home", ["Alice", "Bob"])
        assert result == "<person> and <person> went home"

    def test_name_in_entity_id(self):
        result = redact_names_in_text("person.alice_phone", ["alice"])
        assert result == "person.<person>_phone"

    def test_empty_names_list(self):
        text = "Hello Alice"
        assert redact_names_in_text(text, []) == text

    def test_none_in_names_list(self):
        text = "Hello Alice"
        assert redact_names_in_text(text, [None, "Alice"]) == "Hello <person>"

    def test_whitespace_only_name_skipped(self):
        text = "Hello Alice"
        assert redact_names_in_text(text, ["  ", "Alice"]) == "Hello <person>"

    def test_empty_string_name_skipped(self):
        text = "Hello Alice"
        assert redact_names_in_text(text, ["", "Alice"]) == "Hello <person>"

    def test_name_with_special_regex_chars(self):
        result = redact_names_in_text("User: alice.b", ["alice.b"])
        assert result == "User: <person>"

    def test_preserves_surrounding_text(self):
        result = redact_names_in_text("sensor.alice_room_temp: 22.5", ["Alice"])
        assert result == "sensor.<person>_room_temp: 22.5"

    def test_empty_content(self):
        assert redact_names_in_text("", ["Alice"]) == ""

    def test_no_match_returns_unchanged(self):
        text = "Hello World"
        assert redact_names_in_text(text, ["Alice"]) == text


# ---------------------------------------------------------------------------
# neutralize_pronouns
# ---------------------------------------------------------------------------

class TestNeutralizePronouns:

    @pytest.mark.parametrize("input_text,expected", [
        ("he is home", "they is home"),
        ("He is home", "they is home"),
        ("HE is home", "they is home"),
    ])
    def test_he_to_they(self, input_text, expected):
        assert neutralize_pronouns(input_text) == expected

    @pytest.mark.parametrize("input_text,expected", [
        ("call him now", "call them now"),
        ("call Him now", "call them now"),
    ])
    def test_him_to_them(self, input_text, expected):
        assert neutralize_pronouns(input_text) == expected

    @pytest.mark.parametrize("input_text,expected", [
        ("his room", "their room"),
        ("His room", "their room"),
    ])
    def test_his_to_their(self, input_text, expected):
        assert neutralize_pronouns(input_text) == expected

    @pytest.mark.parametrize("input_text,expected", [
        ("she is home", "they is home"),
        ("She is home", "they is home"),
    ])
    def test_she_to_they(self, input_text, expected):
        assert neutralize_pronouns(input_text) == expected

    @pytest.mark.parametrize("input_text,expected", [
        ("call her now", "call them now"),
        ("Call Her Now", "Call them Now"),
    ])
    def test_her_to_them(self, input_text, expected):
        assert neutralize_pronouns(input_text) == expected

    @pytest.mark.parametrize("input_text,expected", [
        ("that is hers", "that is theirs"),
        ("that is Hers", "that is theirs"),
    ])
    def test_hers_to_theirs(self, input_text, expected):
        assert neutralize_pronouns(input_text) == expected

    def test_word_boundary_the(self):
        """'the' should not be affected (contains 'he')."""
        assert neutralize_pronouns("the dog") == "the dog"

    def test_word_boundary_there(self):
        """'there' should not be affected (starts with 'the' + 're')."""
        assert neutralize_pronouns("over there") == "over there"

    def test_word_boundary_other(self):
        """'other' should not be affected (contains 'her')."""
        assert neutralize_pronouns("the other one") == "the other one"

    def test_word_boundary_this(self):
        """'this' should not be affected (contains 'his')."""
        assert neutralize_pronouns("this is fine") == "this is fine"

    def test_word_boundary_sheer(self):
        """'sheer' should not be affected (starts with 'she')."""
        assert neutralize_pronouns("sheer force") == "sheer force"

    def test_word_boundary_hero(self):
        """'hero' should not be affected (starts with 'her')."""
        assert neutralize_pronouns("a hero") == "a hero"

    def test_word_boundary_sheet(self):
        """'sheet' should not be affected (starts with 'she')."""
        assert neutralize_pronouns("a sheet") == "a sheet"

    def test_empty_string(self):
        assert neutralize_pronouns("") == ""

    def test_no_pronouns(self):
        text = "the cat sat on the mat"
        assert neutralize_pronouns(text) == text

    def test_multiple_pronouns_in_sentence(self):
        result = neutralize_pronouns("he gave his book to her")
        assert result == "they gave their book to them"

    def test_hers_before_her(self):
        """'hers' must be matched; 'her' inside 'hers' should not cause partial match."""
        result = neutralize_pronouns("that bag is hers")
        assert result == "that bag is theirs"
