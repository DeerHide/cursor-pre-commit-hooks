"""Changelog version bump pre-commit hook.

This hook uses cursor-agent CLI to analyze commitizen-formatted commit messages,
determine semantic version bumps, and update both pyproject.toml and CHANGELOG.md.
"""

import re
import subprocess
import sys
import traceback
from datetime import date
from pathlib import Path
from typing import Any, Literal, Optional

# Try to import tomllib (Python 3.11+) or fall back to tomli
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[import-not-found]


VersionBump = Literal["major", "minor", "patch"]

# Commitizen type to version bump mapping
COMMIT_TYPE_TO_BUMP: dict[str, VersionBump] = {
    "feat": "minor",
    "fix": "patch",
    "docs": "patch",
    "style": "patch",
    "refactor": "patch",
    "perf": "patch",
    "test": "patch",
    "build": "patch",
    "ci": "patch",
    "chore": "patch",
}

# Commit types that should update changelog
CHANGELOG_TYPES: set[str] = {"feat", "fix", "refactor", "perf"}

# Mapping from commit type to Keep a Changelog section
TYPE_TO_SECTION: dict[str, str] = {
    "feat": "Added",
    "fix": "Fixed",
    "refactor": "Changed",
    "perf": "Changed",
}

CHANGELOG_HEADER = """# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

"""


def check_cursor_agent_available() -> bool:
    """Check if cursor-agent CLI is available.

    Returns:
        True if cursor-agent is available, False otherwise.
    """
    try:
        result = subprocess.run(
            ["cursor-agent", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


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


def read_commit_message() -> str:
    """Read the commit message from .git/COMMIT_EDITMSG.

    Returns:
        The commit message content.

    Raises:
        FileNotFoundError: If commit message file doesn't exist.
    """
    git_root = get_git_root()
    commit_msg_file = git_root / ".git" / "COMMIT_EDITMSG"

    if not commit_msg_file.exists():
        raise FileNotFoundError(f"Commit message file not found: {commit_msg_file}")

    return commit_msg_file.read_text(encoding="utf-8").strip()


def parse_commitizen_message(
    message: str,
) -> Optional[tuple[str, Optional[str], bool, str]]:
    """Parse a commitizen-formatted commit message.

    Args:
        message: The commit message to parse.

    Returns:
        Tuple of (type, scope, is_breaking, description) or None if not valid format.
    """
    # Pattern: type(scope)!: description or type!: description or type(scope): description
    pattern = (
        r"^(?P<type>feat|fix|docs|style|refactor|perf|test|build|ci|chore)"
        r"(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?: (?P<description>.+)"
    )

    first_line = message.split("\n")[0]
    match = re.match(pattern, first_line, re.IGNORECASE)

    if not match:
        return None

    commit_type = match.group("type").lower()
    scope = match.group("scope")
    is_breaking = match.group("breaking") == "!" or "BREAKING CHANGE" in message
    description = match.group("description")

    return (commit_type, scope, is_breaking, description)


def get_current_version(pyproject_path: Path) -> str:
    """Read the current version from pyproject.toml.

    Supports both PEP 621 format ([project]) and Poetry format ([tool.poetry]).

    Args:
        pyproject_path: Path to pyproject.toml.

    Returns:
        The current version string.

    Raises:
        KeyError: If version is not found in pyproject.toml.
    """
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


def calculate_new_version(current: str, bump: VersionBump) -> str:
    """Calculate the new version based on the bump type.

    Args:
        current: Current version string (e.g., "1.2.3").
        bump: Type of version bump.

    Returns:
        New version string.
    """
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", current)
    if not match:
        raise ValueError(f"Invalid version format: {current}")

    major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))

    if bump == "major":
        return f"{major + 1}.0.0"
    elif bump == "minor":
        return f"{major}.{minor + 1}.0"
    else:  # patch
        return f"{major}.{minor}.{patch + 1}"


def run_cursor_agent(prompt: str, file_path: Optional[Path] = None) -> str:
    """Run cursor-agent with a prompt.

    Args:
        prompt: The prompt to send to cursor-agent.
        file_path: Optional file path for cursor-agent to work with.

    Returns:
        The output from cursor-agent.

    Raises:
        RuntimeError: If cursor-agent fails.
    """
    cmd = ["cursor-agent", "-p", prompt]

    if file_path:
        cmd.extend(["--file", str(file_path)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            raise RuntimeError(f"cursor-agent failed: {result.stderr}")

        return result.stdout.strip()

    except subprocess.TimeoutExpired as e:
        raise RuntimeError("cursor-agent timed out") from e


def create_changelog(changelog_path: Path, version: str, commit_info: tuple) -> None:
    """Create a new CHANGELOG.md file using cursor-agent.

    Args:
        changelog_path: Path to CHANGELOG.md.
        version: The version to add.
        commit_info: Tuple of (type, scope, is_breaking, description).
    """
    commit_type, scope, is_breaking, description = commit_info
    section = TYPE_TO_SECTION.get(commit_type, "Changed")
    today = date.today().isoformat()

    prompt = f"""Create a new CHANGELOG.md file following the Keep a Changelog format.
The file should start with:
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Then add the first version entry:
## [{version}] - {today}

### {section}
- {description}

{"**BREAKING CHANGE**" if is_breaking else ""}

Write only the markdown content, nothing else."""

    # Always ensure file is created, with cursor-agent as optional enhancement
    content = f"""{CHANGELOG_HEADER}## [{version}] - {today}

### {section}
- {description}
"""
    if is_breaking:
        content += "\n### Breaking Changes\n- **BREAKING CHANGE**: This is a breaking change.\n"

    # Try cursor-agent if available, otherwise use fallback directly
    if check_cursor_agent_available():
        try:
            run_cursor_agent(prompt, changelog_path)
            # If cursor-agent created/updated the file, verify it's correct
            if changelog_path.exists():
                file_content = changelog_path.read_text(encoding="utf-8")
                # Verify it contains the version
                if f"[{version}]" not in file_content:
                    print("Warning: cursor-agent output doesn't contain version, using fallback")
                    changelog_path.write_text(content, encoding="utf-8")
            else:
                # File doesn't exist, create it manually
                changelog_path.write_text(content, encoding="utf-8")
        except RuntimeError as e:
            # Fallback: create the file manually if cursor-agent fails
            print(f"Warning: cursor-agent failed, creating changelog manually: {e}")
            changelog_path.write_text(content, encoding="utf-8")
    else:
        # cursor-agent not available, use fallback directly
        changelog_path.write_text(content, encoding="utf-8")

    # Final verification: ensure file exists
    if not changelog_path.exists():
        changelog_path.write_text(content, encoding="utf-8")


def update_changelog(
    changelog_path: Path, version: str, commit_info: tuple, current_version: str
) -> None:
    """Update existing CHANGELOG.md using cursor-agent.

    Args:
        changelog_path: Path to CHANGELOG.md.
        version: The new version to add.
        commit_info: Tuple of (type, scope, is_breaking, description).
        current_version: The current version before bump.
    """
    commit_type, scope, is_breaking, description = commit_info
    section = TYPE_TO_SECTION.get(commit_type, "Changed")
    today = date.today().isoformat()

    prompt = f"""Update this CHANGELOG.md file by adding a new version entry.
Add it at the top (after the header), before any existing version entries:

## [{version}] - {today}

### {section}
- {description}
{"- **BREAKING CHANGE**: This is a breaking change." if is_breaking else ""}

Keep all existing content intact. Only add the new version section.
The previous version was {current_version}."""

    # Prepare the new entry
    new_entry = f"""## [{version}] - {today}

### {section}
- {description}
"""
    if is_breaking:
        new_entry += "\n### Breaking Changes\n- **BREAKING CHANGE**: This is a breaking change.\n"
    new_entry += "\n"

    # Try cursor-agent if available, otherwise use fallback directly
    if check_cursor_agent_available():
        try:
            run_cursor_agent(prompt, changelog_path)
            # If cursor-agent updated the file, verify it's correct
            if changelog_path.exists():
                file_content = changelog_path.read_text(encoding="utf-8")
                # Verify it contains the new version
                if f"[{version}]" not in file_content:
                    print("Warning: cursor-agent output doesn't contain version, using fallback")
                    # Fallback: manually prepend the new version entry
                    lines = file_content.split("\n")
                    insert_pos = 0
                    for i, line in enumerate(lines):
                        if line.startswith("## ["):
                            insert_pos = i
                            break
                        if i > 20:  # Safety limit
                            insert_pos = len(lines)
                            break
                    lines.insert(insert_pos, new_entry.strip())
                    changelog_path.write_text("\n".join(lines), encoding="utf-8")
            else:
                # File doesn't exist (shouldn't happen for update, but handle it)
                print("Warning: changelog file disappeared, recreating...")
                create_changelog(changelog_path, version, commit_info)
        except RuntimeError as e:
            # Fallback: update manually if cursor-agent fails
            print(f"Warning: cursor-agent failed, updating changelog manually: {e}")
            current_content = changelog_path.read_text(encoding="utf-8")

            # Find where to insert (after header, before first version)
            lines = current_content.split("\n")
            insert_pos = 0
            for i, line in enumerate(lines):
                if line.startswith("## ["):
                    insert_pos = i
                    break
                if i > 20:  # Safety limit
                    insert_pos = len(lines)
                    break

            lines.insert(insert_pos, new_entry.strip())
            changelog_path.write_text("\n".join(lines), encoding="utf-8")
    else:
        # cursor-agent not available, use fallback directly
        current_content = changelog_path.read_text(encoding="utf-8")

        # Find where to insert (after header, before first version)
        lines = current_content.split("\n")
        insert_pos = 0
        for i, line in enumerate(lines):
            if line.startswith("## ["):
                insert_pos = i
                break
            if i > 20:  # Safety limit
                insert_pos = len(lines)
                break

        lines.insert(insert_pos, new_entry.strip())
        changelog_path.write_text("\n".join(lines), encoding="utf-8")

    # Final verification: ensure file exists and contains version
    if not changelog_path.exists():
        print("Error: changelog file was not created")
        raise RuntimeError("Failed to create changelog file")
    if f"[{version}]" not in changelog_path.read_text(encoding="utf-8"):
        print(f"Warning: changelog doesn't contain version {version}, forcing update...")
        current_content = changelog_path.read_text(encoding="utf-8")
        lines = current_content.split("\n")
        insert_pos = 0
        for i, line in enumerate(lines):
            if line.startswith("## ["):
                insert_pos = i
                break
            if i > 20:
                insert_pos = len(lines)
                break
        lines.insert(insert_pos, new_entry.strip())
        changelog_path.write_text("\n".join(lines), encoding="utf-8")


def detect_pyproject_format(pyproject_path: Path) -> str:
    """Detect the format of pyproject.toml (PEP 621 or Poetry).

    Args:
        pyproject_path: Path to pyproject.toml.

    Returns:
        "pep621" if [project] format, "poetry" if [tool.poetry] format, or "unknown".
    """
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    if "project" in data and "version" in data["project"]:
        return "pep621"
    if "tool" in data and "poetry" in data["tool"] and "version" in data["tool"]["poetry"]:
        return "poetry"
    return "unknown"


def update_pyproject_version(pyproject_path: Path, new_version: str) -> None:
    """Update the version in pyproject.toml using cursor-agent.

    Supports both PEP 621 format ([project]) and Poetry format ([tool.poetry]).

    Args:
        pyproject_path: Path to pyproject.toml.
        new_version: The new version to set.
    """
    # Detect format to provide correct prompt
    format_type = detect_pyproject_format(pyproject_path)

    if format_type == "pep621":
        section = "[project]"
    elif format_type == "poetry":
        section = "[tool.poetry]"
    else:
        # Try to detect from file content
        content = pyproject_path.read_text(encoding="utf-8")
        if "[tool.poetry]" in content:
            section = "[tool.poetry]"
            format_type = "poetry"
        else:
            section = "[project]"
            format_type = "pep621"

    prompt = f"""Update the version field in this pyproject.toml file to "{new_version}".
Only change the version = "..." line under {section}.
Keep all other content exactly the same."""

    # Helper function to manually update version
    def _update_version_manually() -> None:
        """Manually update the version in pyproject.toml."""
        content = pyproject_path.read_text(encoding="utf-8")

        # Update based on detected format
        if format_type == "poetry":
            # Update [tool.poetry] version
            lines = content.split("\n")
            in_poetry_section = False
            for i, line in enumerate(lines):
                if line.strip().startswith("[tool.poetry]"):
                    in_poetry_section = True
                elif in_poetry_section and line.strip().startswith("version = "):
                    # Extract indentation
                    indent = len(line) - len(line.lstrip())
                    lines[i] = " " * indent + f'version = "{new_version}"'
                    break
                elif (
                    in_poetry_section
                    and line.strip().startswith("[")
                    and not line.strip().startswith("[tool.")
                ):
                    # Left poetry section without finding version
                    break
            new_content = "\n".join(lines)
        else:
            # Update [project] version (PEP 621)
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if line.strip().startswith("version = "):
                    # Extract indentation
                    indent = len(line) - len(line.lstrip())
                    lines[i] = " " * indent + f'version = "{new_version}"'
                    break
            new_content = "\n".join(lines)

        pyproject_path.write_text(new_content, encoding="utf-8")

    # Try cursor-agent first if available, but always ensure version is updated
    if check_cursor_agent_available():
        try:
            run_cursor_agent(prompt, pyproject_path)
            # Verify the file was updated by checking if it contains the new version
            if pyproject_path.exists():
                content = pyproject_path.read_text(encoding="utf-8")
                if f'version = "{new_version}"' not in content:
                    # Fallback: manually update the version
                    print("Warning: cursor-agent did not update version correctly, using fallback")
                    _update_version_manually()
        except RuntimeError as e:
            # Fallback: manually update the version
            print(f"Warning: cursor-agent failed, updating version manually: {e}")
            _update_version_manually()
    else:
        # cursor-agent not available, use fallback directly
        _update_version_manually()

    # Final verification: ensure version was updated
    try:
        updated_version = get_current_version(pyproject_path)
        if updated_version != new_version:
            print(
                f"Warning: Version verification failed "
                f"({updated_version} != {new_version}), forcing update..."
            )
            _update_version_manually()
            # Verify again
            updated_version = get_current_version(pyproject_path)
            if updated_version != new_version:
                raise RuntimeError(
                    f"Failed to update version: expected {new_version}, got {updated_version}"
                )
    except (KeyError, FileNotFoundError) as e:
        raise RuntimeError(f"Failed to verify version update: {e}") from e


def stage_files(files: list[Path]) -> None:
    """Stage files for commit.

    Args:
        files: List of file paths to stage.
    """
    for file_path in files:
        subprocess.run(
            ["git", "add", str(file_path)],
            check=True,
        )


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


def verify_hook_success(
    git_root: Path,
    expected_version: str,
    changelog_path: Path,
    pyproject_path: Path,
) -> tuple[bool, list[str]]:
    """Verify that the hook completed successfully.

    Args:
        git_root: Git repository root.
        expected_version: Expected version after update.
        changelog_path: Path to CHANGELOG.md.
        pyproject_path: Path to pyproject.toml.

    Returns:
        Tuple of (success: bool, issues: list[str]).
    """
    issues: list[str] = []

    # Check changelog exists
    if not changelog_path.exists():
        issues.append(f"CHANGELOG.md does not exist at {changelog_path}")
    else:
        # Check changelog contains version
        try:
            changelog_content = changelog_path.read_text(encoding="utf-8")
            if f"[{expected_version}]" not in changelog_content:
                issues.append(f"CHANGELOG.md does not contain version {expected_version}")
        except Exception as e:
            issues.append(f"Failed to read CHANGELOG.md: {e}")

    # Check pyproject.toml version
    if not pyproject_path.exists():
        issues.append(f"pyproject.toml does not exist at {pyproject_path}")
    else:
        try:
            actual_version = get_current_version(pyproject_path)
            if actual_version != expected_version:
                issues.append(
                    f"pyproject.toml version mismatch: expected {expected_version}, "
                    f"got {actual_version}"
                )
        except Exception as e:
            issues.append(f"Failed to read version from pyproject.toml: {e}")

    # Check files are staged
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", str(changelog_path), str(pyproject_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        staged_lines = [
            line
            for line in result.stdout.split("\n")
            if line and (line.startswith("A  ") or line.startswith("M  "))
        ]
        if not staged_lines:
            issues.append("Files are not staged in git (should be staged for commit)")
    except subprocess.CalledProcessError as e:
        issues.append(f"Failed to check git status: {e}")

    return len(issues) == 0, issues


def main() -> int:
    """Run the changelog version bump hook.

    Returns:
        Exit code: 0 if successful, 1 if errors occurred.
    """
    try:
        # Check if cursor-agent is available (optional, we have fallbacks)
        cursor_agent_available = check_cursor_agent_available()
        if not cursor_agent_available:
            print("Info: cursor-agent CLI is not available, using manual fallback methods.")
            print("Install it with: curl https://cursor.com/install -fsS | bash")

        try:
            git_root = get_git_root()
        except RuntimeError as e:
            log_error("Failed to get git repository root", e)
            return 1

        # Read commit message
        try:
            commit_msg = read_commit_message()
            print(f"Debug: Commit message: {commit_msg[:100]}...")
        except FileNotFoundError as e:
            log_error("Failed to read commit message", e)
            return 1

        # Parse commitizen format
        commit_info = parse_commitizen_message(commit_msg)
        if commit_info is None:
            print("Info: Commit message is not in commitizen format, skipping.")
            print("Debug: Commit message format should be: type(scope): description")
            return 0

        commit_type, scope, is_breaking, description = commit_info
        print(
            f"Debug: Parsed commit - type: {commit_type}, scope: {scope}, breaking: {is_breaking}"
        )

        # Skip changelog update for certain types
        if commit_type not in CHANGELOG_TYPES:
            print(f"Info: Commit type '{commit_type}' does not require changelog update.")
            print(f"Debug: Changelog types: {CHANGELOG_TYPES}")
            return 0

        # Determine version bump
        if is_breaking:
            bump: VersionBump = "major"
        else:
            bump = COMMIT_TYPE_TO_BUMP.get(commit_type, "patch")

        print(f"Detected commit type: {commit_type}")
        print(f"Breaking change: {is_breaking}")
        print(f"Version bump: {bump}")

        # Get current version
        pyproject_path = git_root / "pyproject.toml"
        if not pyproject_path.exists():
            log_error(f"pyproject.toml not found at {pyproject_path}")
            return 1

        try:
            current_version = get_current_version(pyproject_path)
        except (KeyError, FileNotFoundError) as e:
            log_error("Failed to read current version from pyproject.toml", e)
            return 1

        # Calculate new version
        new_version = calculate_new_version(current_version, bump)
        print(f"Version: {current_version} -> {new_version}")

        # Check/create/update CHANGELOG.md
        changelog_path = git_root / "CHANGELOG.md"
        files_to_stage: list[Path] = []

        try:
            if not changelog_path.exists():
                print("Creating CHANGELOG.md...")
                create_changelog(changelog_path, new_version, commit_info)
            else:
                print("Updating CHANGELOG.md...")
                update_changelog(changelog_path, new_version, commit_info, current_version)

            # Verify changelog was created/updated
            if not changelog_path.exists():
                log_error("CHANGELOG.md was not created after create_changelog() call")
                return 1
            if f"[{new_version}]" not in changelog_path.read_text(encoding="utf-8"):
                print(f"Warning: CHANGELOG.md may not contain version {new_version}")
            files_to_stage.append(changelog_path)

            print("Updating pyproject.toml version...")
            update_pyproject_version(pyproject_path, new_version)

            # Verify pyproject.toml was updated
            try:
                updated_version = get_current_version(pyproject_path)
                if updated_version != new_version:
                    log_error(
                        f"pyproject.toml version mismatch: expected {new_version}, "
                        f"got {updated_version}"
                    )
                    return 1
            except (KeyError, FileNotFoundError) as e:
                log_error("Failed to verify pyproject.toml update", e)
                return 1
            files_to_stage.append(pyproject_path)

        except RuntimeError as e:
            log_error("Error during file creation/update", e)
            return 1
        except Exception as e:
            log_error("Unexpected error during file operations", e)
            return 1

        # Final verification before staging
        print("\n" + "=" * 60)
        print("Pre-staging verification:")
        print("=" * 60)
        for file_path in files_to_stage:
            if not file_path.exists():
                log_error(f"File does not exist: {file_path}")
                return 1
            file_size = file_path.stat().st_size
            print(f"  ✓ {file_path} exists ({file_size} bytes)")

        # Stage modified files
        print(f"\nStaging {len(files_to_stage)} file(s)...")
        try:
            for file_path in files_to_stage:
                print(f"  → Staging: {file_path}")
            stage_files(files_to_stage)
            print("  ✓ Files staged successfully")
        except subprocess.CalledProcessError as e:
            log_error("Failed to stage files", e)
            print(f"Files that should have been staged: {[str(f) for f in files_to_stage]}")
            return 1
        except Exception as e:
            log_error("Unexpected error during file staging", e)
            return 1

        # Self-verification: Final check
        print("\n" + "=" * 60)
        print("Self-verification:")
        print("=" * 60)
        success, issues = verify_hook_success(
            git_root=git_root,
            expected_version=new_version,
            changelog_path=changelog_path,
            pyproject_path=pyproject_path,
        )

        if success:
            print("  ✓ All checks passed!")
            print(f"\n✓ Successfully updated to version {new_version}")
            print(f"✓ Modified files: {[str(f) for f in files_to_stage]}")
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
