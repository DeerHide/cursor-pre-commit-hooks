"""Setup script for cursor-pre-commit-hooks."""

from setuptools import setup

setup(
    entry_points={
        "console_scripts": [
            "changelog-version=hooks.changelog_version:main",
            "auto-tag=hooks.auto_tag:main",
        ],
    },
)
