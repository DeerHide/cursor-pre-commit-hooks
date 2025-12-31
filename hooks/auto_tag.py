"""Auto-tag hook that creates git tags based on version in pyproject.toml.

This hook reads the version from pyproject.toml (updated by changelog_version hook)
and creates a git tag if one doesn't already exist for that version.
"""

import subprocess
import sys
from pathlib import Path
from typing import Sequence

# Try to import tomllib (Python 3.11+) or fall back to tomli
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[import-not-found]


def get_git_root() -> Path:
    """Get the root directory of the git repository.

    Returns:
        Path to the git repository root.

    Raises:
        RuntimeError: If not in a git repository.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        raise RuntimeError("Not in a git repository") from e


def get_current_version(pyproject_path: Path) -> str:
    """Read the current version from pyproject.toml.

    Args:
        pyproject_path: Path to pyproject.toml.

    Returns:
        The current version string.

    Raises:
        KeyError: If version is not found in pyproject.toml.
        FileNotFoundError: If pyproject.toml doesn't exist.
    """
    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found: {pyproject_path}")

    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    return data["project"]["version"]


def tag_exists(tag_name: str) -> bool:
    """Check if a git tag exists.

    Args:
        tag_name: The tag name to check.

    Returns:
        True if the tag exists, False otherwise.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", f"refs/tags/{tag_name}"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except subprocess.CalledProcessError:
        return False


def get_head_commit_hash() -> str:
    """Get the hash of the HEAD commit.

    Returns:
        The commit hash.

    Raises:
        RuntimeError: If git command fails.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError("Failed to get HEAD commit hash") from e


def create_tag(tag_name: str, message: str | None = None) -> None:
    """Create a git tag.

    Args:
        tag_name: The tag name (e.g., "v1.2.3").
        message: Optional tag message. If None, uses default message.

    Raises:
        RuntimeError: If tag creation fails.
    """
    cmd = ["git", "tag", tag_name]
    if message:
        cmd.extend(["-m", message])
    else:
        cmd.extend(["-m", f"Release {tag_name}"])

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to create tag: {e.stderr}") from e


def format_tag_name(version: str, prefix: str = "v") -> str:
    """Format version string as a tag name.

    Args:
        version: Version string (e.g., "1.2.3").
        prefix: Prefix for the tag (default: "v").

    Returns:
        Formatted tag name (e.g., "v1.2.3").
    """
    return f"{prefix}{version}"


def main(argv: Sequence[str] | None = None) -> int:
    """Run the auto-tag hook.

    This hook reads the version from pyproject.toml and creates a git tag
    if one doesn't already exist for that version.

    Args:
        argv: Command line arguments. Optional arguments:
            --tag-prefix PREFIX: Prefix for tags (default: "v")
            --skip-if-exists: Skip if tag already exists (default: True)
            --message MESSAGE: Custom tag message

    Returns:
        Exit code: 0 if successful, 1 if errors occurred.
    """
    if argv is None:
        argv = sys.argv[1:]

    # Parse arguments
    tag_prefix = "v"
    skip_if_exists = True
    tag_message: str | None = None

    i = 0
    while i < len(argv):
        if argv[i] == "--tag-prefix" and i + 1 < len(argv):
            tag_prefix = argv[i + 1]
            i += 2
        elif argv[i] == "--skip-if-exists":
            skip_if_exists = True
            i += 1
        elif argv[i] == "--no-skip-if-exists":
            skip_if_exists = False
            i += 1
        elif argv[i] == "--message" and i + 1 < len(argv):
            tag_message = argv[i + 1]
            i += 2
        else:
            print(f"Warning: Unknown argument: {argv[i]}")
            i += 1

    try:
        git_root = get_git_root()
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1

    # Read version from pyproject.toml
    pyproject_path = git_root / "pyproject.toml"
    try:
        version = get_current_version(pyproject_path)
    except (KeyError, FileNotFoundError) as e:
        print(f"Error reading version from pyproject.toml: {e}")
        return 1

    # Format tag name
    tag_name = format_tag_name(version, prefix=tag_prefix)

    # Check if tag already exists
    if tag_exists(tag_name):
        if skip_if_exists:
            print(f"Info: Tag {tag_name} already exists, skipping.")
            return 0
        else:
            print(f"Error: Tag {tag_name} already exists.")
            return 1

    # Get HEAD commit hash for tag message
    try:
        commit_hash = get_head_commit_hash()
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1

    # Create tag message if not provided
    if tag_message is None:
        tag_message = f"Release {tag_name}\n\nAuto-generated tag from changelog_version hook."

    # Create the tag
    try:
        create_tag(tag_name, tag_message)
        print(f"Successfully created tag: {tag_name}")
        print(f"Tag points to commit: {commit_hash}")
        return 0
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

