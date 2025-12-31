"""Auto-tag hook that creates git tags based on version in pyproject.toml.

This hook reads the version from pyproject.toml (updated by changelog_version hook)
and creates a git tag if one doesn't already exist for that version.
"""

import subprocess
import sys
import traceback
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Optional

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

    Supports both PEP 621 format ([project]) and Poetry format ([tool.poetry]).

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

    # Try PEP 621 format first: [project] -> version
    if "project" in data and "version" in data["project"]:
        version: Any = data["project"]["version"]
        return str(version)

    # Try Poetry format: [tool.poetry] -> version
    if "tool" in data and "poetry" in data["tool"]:
        if "version" in data["tool"]["poetry"]:
            version = data["tool"]["poetry"]["version"]
            return str(version)

    # Neither format found - provide helpful error
    available_keys = ", ".join(data.keys())
    if "project" in data:
        project_keys = ", ".join(data["project"].keys())
        raise KeyError(
            f"'version' field not found in [project] section of pyproject.toml. "
            f"Available keys in [project]: {project_keys}"
        )
    if "tool" in data and "poetry" in data["tool"]:
        poetry_keys = ", ".join(data["tool"]["poetry"].keys())
        raise KeyError(
            f"'version' field not found in [tool.poetry] section of pyproject.toml. "
            f"Available keys in [tool.poetry]: {poetry_keys}"
        )

    raise KeyError(
        f"Neither [project] nor [tool.poetry] section found in pyproject.toml. "
        f"Available top-level sections: {available_keys}"
    )


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


def create_tag(tag_name: str, message: Optional[str] = None) -> None:
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


def log_error(message: str, exception: Optional[Exception] = None) -> None:
    """Log an error with full context.

    Args:
        message: Error message.
        exception: Optional exception to log details from.
    """
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"ERROR: {message}", file=sys.stderr)
    if exception:
        print(f"Exception type: {type(exception).__name__}", file=sys.stderr)
        print(f"Exception message: {str(exception)}", file=sys.stderr)
        print("\nTraceback:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)


def verify_tag_creation(
    tag_name: str,
    expected_version: str,
    pyproject_path: Path,
) -> tuple[bool, list[str]]:
    """Verify that the tag was created successfully.

    Args:
        tag_name: The tag name that should exist.
        expected_version: Expected version in pyproject.toml.
        pyproject_path: Path to pyproject.toml.

    Returns:
        Tuple of (success: bool, issues: list[str]).
    """
    issues: list[str] = []

    # Check tag exists
    if not tag_exists(tag_name):
        issues.append(f"Tag {tag_name} does not exist after creation")

    # Check pyproject.toml version matches
    try:
        actual_version = get_current_version(pyproject_path)
        if actual_version != expected_version:
            issues.append(
                f"pyproject.toml version mismatch: expected {expected_version}, "
                f"got {actual_version}"
            )
    except Exception as e:
        issues.append(f"Failed to read version from pyproject.toml: {e}")

    # Check tag points to HEAD
    try:
        tag_hash_result = subprocess.run(
            ["git", "rev-parse", tag_name],
            capture_output=True,
            text=True,
            check=True,
        )
        tag_hash = tag_hash_result.stdout.strip()

        head_hash_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        head_hash = head_hash_result.stdout.strip()

        if tag_hash != head_hash:
            issues.append(f"Tag {tag_name} points to {tag_hash[:8]}, but HEAD is {head_hash[:8]}")
    except subprocess.CalledProcessError as e:
        issues.append(f"Failed to verify tag points to HEAD: {e}")

    return len(issues) == 0, issues


def main(argv: Optional[Sequence[str]] = None) -> int:
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
    tag_message: Optional[str] = None

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
        try:
            git_root = get_git_root()
        except RuntimeError as e:
            log_error("Failed to get git repository root", e)
            return 1

        # Read version from pyproject.toml
        pyproject_path = git_root / "pyproject.toml"
        if not pyproject_path.exists():
            log_error(f"pyproject.toml not found at {pyproject_path}")
            return 1

        try:
            version = get_current_version(pyproject_path)
            print(f"Read version from pyproject.toml: {version}")
        except (KeyError, FileNotFoundError) as e:
            log_error("Failed to read version from pyproject.toml", e)
            return 1

        # Format tag name
        tag_name = format_tag_name(version, prefix=tag_prefix)
        print(f"Tag name: {tag_name}")

        # Check if tag already exists
        if tag_exists(tag_name):
            if skip_if_exists:
                print(f"Info: Tag {tag_name} already exists, skipping.")
                return 0
            else:
                log_error(f"Tag {tag_name} already exists and --no-skip-if-exists is set")
                return 1

        # Get HEAD commit hash for tag message
        try:
            commit_hash = get_head_commit_hash()
            print(f"HEAD commit: {commit_hash}")
        except RuntimeError as e:
            log_error("Failed to get HEAD commit hash", e)
            return 1

        # Create tag message if not provided
        if tag_message is None:
            tag_message = f"Release {tag_name}\n\nAuto-generated tag from changelog_version hook."

        # Create the tag
        print(f"\nCreating tag: {tag_name}")
        try:
            create_tag(tag_name, tag_message)
            print("  ✓ Tag created successfully")
        except RuntimeError as e:
            log_error("Failed to create tag", e)
            return 1
        except Exception as e:
            log_error("Unexpected error during tag creation", e)
            return 1

        # Self-verification: Final check
        print("\n" + "=" * 60)
        print("Self-verification:")
        print("=" * 60)
        success, issues = verify_tag_creation(
            tag_name=tag_name,
            expected_version=version,
            pyproject_path=pyproject_path,
        )

        if success:
            print("  ✓ All checks passed!")
            print(f"\n✓ Successfully created tag: {tag_name}")
            print(f"✓ Tag points to commit: {commit_hash}")
            print(f"✓ Version: {version}")
            print("=" * 60 + "\n")
            return 0
        else:
            print("  ✗ Issues found:")
            for issue in issues:
                print(f"    - {issue}")
            print("=" * 60 + "\n")
            log_error("Hook self-verification failed", None)
            return 1

    except Exception as e:
        log_error("Unexpected error in main hook execution", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
