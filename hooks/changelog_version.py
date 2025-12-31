"""Changelog version bump pre-commit hook.

This hook uses cursor-agent CLI to analyze commitizen-formatted commit messages,
determine semantic version bumps, and update both pyproject.toml and CHANGELOG.md.
"""

import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Literal

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
) -> tuple[str, str | None, bool, str] | None:
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
        return data["project"]["version"]

    # Try Poetry format: [tool.poetry] -> version
    if "tool" in data and "poetry" in data["tool"]:
        if "version" in data["tool"]["poetry"]:
            return data["tool"]["poetry"]["version"]

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


def run_cursor_agent(prompt: str, file_path: Path | None = None) -> str:
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

    try:
        output = run_cursor_agent(prompt, changelog_path)
        # If cursor-agent didn't create the file, write it ourselves
        if not changelog_path.exists() and output:
            changelog_path.write_text(output, encoding="utf-8")
        elif not changelog_path.exists():
            # Fallback: create the file manually if cursor-agent didn't work
            content = f"""{CHANGELOG_HEADER}## [{version}] - {today}

### {section}
- {description}
"""
            if is_breaking:
                content += "\n### Breaking Changes\n- **BREAKING CHANGE**: This is a breaking change.\n"
            changelog_path.write_text(content, encoding="utf-8")
    except RuntimeError as e:
        # Fallback: create the file manually if cursor-agent fails
        print(f"Warning: cursor-agent failed, creating changelog manually: {e}")
        content = f"""{CHANGELOG_HEADER}## [{version}] - {today}

### {section}
- {description}
"""
        if is_breaking:
            content += "\n### Breaking Changes\n- **BREAKING CHANGE**: This is a breaking change.\n"
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

    try:
        output = run_cursor_agent(prompt, changelog_path)
        # If cursor-agent didn't update the file, do it manually
        if output and changelog_path.exists():
            # Read current content
            current_content = changelog_path.read_text(encoding="utf-8")
            # If output contains the new version entry, use it
            if f"[{version}]" in output:
                changelog_path.write_text(output, encoding="utf-8")
            else:
                # Fallback: manually prepend the new version entry
                new_entry = f"""## [{version}] - {today}

### {section}
- {description}
"""
                if is_breaking:
                    new_entry += "\n### Breaking Changes\n- **BREAKING CHANGE**: This is a breaking change.\n"
                new_entry += "\n"
                
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
    except RuntimeError as e:
        # Fallback: update manually if cursor-agent fails
        print(f"Warning: cursor-agent failed, updating changelog manually: {e}")
        current_content = changelog_path.read_text(encoding="utf-8")
        new_entry = f"""## [{version}] - {today}

### {section}
- {description}
"""
        if is_breaking:
            new_entry += "\n### Breaking Changes\n- **BREAKING CHANGE**: This is a breaking change.\n"
        new_entry += "\n"
        
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

    try:
        output = run_cursor_agent(prompt, pyproject_path)
        # Verify the file was updated by checking if it contains the new version
        if pyproject_path.exists():
            content = pyproject_path.read_text(encoding="utf-8")
            if f'version = "{new_version}"' not in content:
                # Fallback: manually update the version
                raise RuntimeError("cursor-agent did not update version correctly")
    except RuntimeError as e:
        # Fallback: manually update the version
        print(f"Warning: cursor-agent failed, updating version manually: {e}")
        content = pyproject_path.read_text(encoding="utf-8")
        
        # Update based on detected format
        if format_type == "poetry":
            # Update [tool.poetry] version
            pattern = r'^(\s*)version = "[^"]+"'
            replacement = f'\\1version = "{new_version}"'
            # Try to match within [tool.poetry] section
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
                elif in_poetry_section and line.strip().startswith("[") and not line.strip().startswith("[tool."):
                    # Left poetry section without finding version
                    break
            new_content = "\n".join(lines)
        else:
            # Update [project] version (PEP 621)
            pattern = r'^(\s*)version = "[^"]+"'
            replacement = f'\\1version = "{new_version}"'
            new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
            
            if new_content == content:
                # If regex didn't match, try a simpler approach
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if line.strip().startswith("version = "):
                        # Extract indentation
                        indent = len(line) - len(line.lstrip())
                        lines[i] = " " * indent + f'version = "{new_version}"'
                        break
                new_content = "\n".join(lines)
        
        pyproject_path.write_text(new_content, encoding="utf-8")


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


def main() -> int:
    """Run the changelog version bump hook.

    Returns:
        Exit code: 0 if successful, 1 if errors occurred.
    """
    # Check if cursor-agent is available
    if not check_cursor_agent_available():
        print("Error: cursor-agent CLI is not installed or not in PATH.")
        print("Install it with: curl https://cursor.com/install -fsS | bash")
        return 1

    try:
        git_root = get_git_root()
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1

    # Read commit message
    try:
        commit_msg = read_commit_message()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    # Parse commitizen format
    commit_info = parse_commitizen_message(commit_msg)
    if commit_info is None:
        print("Info: Commit message is not in commitizen format, skipping.")
        return 0

    commit_type, scope, is_breaking, description = commit_info

    # Skip changelog update for certain types
    if commit_type not in CHANGELOG_TYPES:
        print(f"Info: Commit type '{commit_type}' does not require changelog update.")
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
        print("Error: pyproject.toml not found")
        return 1

    try:
        current_version = get_current_version(pyproject_path)
    except (KeyError, FileNotFoundError) as e:
        print(f"Error reading version: {e}")
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
            print("Error: CHANGELOG.md was not created")
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
                print(f"Error: pyproject.toml version is {updated_version}, expected {new_version}")
                return 1
        except (KeyError, FileNotFoundError) as e:
            print(f"Error: Failed to verify pyproject.toml update: {e}")
            return 1
        files_to_stage.append(pyproject_path)

    except RuntimeError as e:
        print(f"Error with cursor-agent: {e}")
        return 1

    # Stage modified files
    print("Staging modified files...")
    try:
        stage_files(files_to_stage)
    except subprocess.CalledProcessError as e:
        print(f"Error staging files: {e}")
        return 1

    print(f"Successfully updated to version {new_version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
