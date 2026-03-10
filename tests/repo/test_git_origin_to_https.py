"""Tests for _git_origin_to_https URL conversion utility."""

import pytest
from half_orm_dev.repo import _git_origin_to_https


@pytest.mark.parametrize("input_url, expected", [
    # SSH git@ form
    ("git@github.com:user/repo.git",      "https://github.com/user/repo"),
    ("git@github.com:user/repo",          "https://github.com/user/repo"),
    ("git@gitlab.com:org/project.git",    "https://gitlab.com/org/project"),
    ("git@bitbucket.org:user/repo.git",   "https://bitbucket.org/user/repo"),
    ("git@git.example.com:team/proj.git", "https://git.example.com/team/proj"),
    # HTTPS — passthrough
    ("https://github.com/user/repo.git",  "https://github.com/user/repo"),
    ("https://github.com/user/repo",      "https://github.com/user/repo"),
    ("https://git.example.com/u/r.git",   "https://git.example.com/u/r"),
    # git:// protocol
    ("git://github.com/user/repo.git",    "https://github.com/user/repo"),
    ("git://github.com/user/repo",        "https://github.com/user/repo"),
    # ssh:// protocol
    ("ssh://git@github.com/user/repo.git", "https://github.com/user/repo"),
    ("ssh://github.com/user/repo.git",     "https://github.com/user/repo"),
    # Edge cases
    ("",   ""),
    ("   ", ""),
])
def test_git_origin_to_https(input_url, expected):
    assert _git_origin_to_https(input_url) == expected