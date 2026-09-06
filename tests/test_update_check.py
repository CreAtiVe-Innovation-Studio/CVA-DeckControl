"""Tests fuer update_check.py - nur die reine Versions-Vergleichslogik
(_parse_version), kein echter Netzwerkzugriff auf die GitHub-API."""
from streamdeck_driver import update_check


def test_parse_version_simple():
    assert update_check._parse_version("1.2.3") == (1, 2, 3)


def test_parse_version_with_v_prefix():
    assert update_check._parse_version("v1.2.3") == (1, 2, 3)


def test_parse_version_ignores_prerelease_suffix():
    assert update_check._parse_version("1.2.3-beta") == (1, 2, 3)


def test_parse_version_falls_back_for_unparseable_string():
    assert update_check._parse_version("not-a-version") == (0,)


def test_newer_version_compares_greater():
    assert update_check._parse_version("1.3.0") > update_check._parse_version("1.2.9")
    assert update_check._parse_version("2.0.0") > update_check._parse_version("1.99.99")


def test_equal_versions_are_not_greater():
    assert not (update_check._parse_version("1.2.0") > update_check._parse_version("1.2.0"))
