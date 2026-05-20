"""
Tests for release filename parsing via packaging.version.Version.

parse_version_from_filename() was removed — release filenames are now parsed
by stripping the .txt extension and calling Version(stem) directly.

Supported formats (PEP 440):
- X.Y.Z.txt        → production release
- X.Y.Z-rc1.txt    → release candidate (packaging normalises -rcN)
- X.Y.Z.postN.txt  → post-release / hotfix
"""

import pytest
from pathlib import Path
from packaging.version import Version, InvalidVersion


def parse(filename: str) -> Version:
    """Strip .txt and parse via packaging.version.Version."""
    return Version(Path(filename).stem)


class TestVersionParsing:

    def test_production_release(self):
        v = parse("1.3.5.txt")
        assert v.major == 1
        assert v.minor == 3
        assert v.micro == 5
        assert not v.is_prerelease
        assert not v.is_postrelease

    def test_rc_release(self):
        v = parse("1.3.5-rc2.txt")
        assert v.major == 1
        assert v.minor == 3
        assert v.micro == 5
        assert v.pre == ("rc", 2)
        assert v.is_prerelease

    def test_rc1_release(self):
        v = parse("2.0.0-rc1.txt")
        assert v.major == 2
        assert v.minor == 0
        assert v.micro == 0
        assert v.pre == ("rc", 1)

    def test_post_release(self):
        v = parse("1.3.5.post1.txt")
        assert v.major == 1
        assert v.minor == 3
        assert v.micro == 5
        assert v.post == 1
        assert v.is_postrelease

    def test_post_release_multiple(self):
        v = parse("1.3.4.post3.txt")
        assert v.post == 3

    def test_large_version_numbers(self):
        v = parse("10.20.30.txt")
        assert (v.major, v.minor, v.micro) == (10, 20, 30)

    def test_zero_version(self):
        v = parse("0.0.1.txt")
        assert (v.major, v.minor, v.micro) == (0, 0, 1)

    def test_ordering_production_greater_than_rc(self):
        assert parse("1.3.5.txt") > parse("1.3.5-rc2.txt")

    def test_ordering_post_greater_than_production(self):
        assert parse("1.3.5.post1.txt") > parse("1.3.5.txt")

    def test_ordering_rc2_greater_than_rc1(self):
        assert parse("1.3.5-rc2.txt") > parse("1.3.5-rc1.txt")

    def test_invalid_unknown_label(self):
        with pytest.raises(InvalidVersion):
            parse("1.3.5-invalid.txt")

    def test_invalid_unknown_stage(self):
        with pytest.raises(InvalidVersion):
            parse("1.3.5-invalid.txt")
