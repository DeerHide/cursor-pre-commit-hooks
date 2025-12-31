# cursor-pre-commit-hooks

Custom pre-commit hooks for Python projects using Cursor.

## Installation

### For Local Development

1. Install the package in development mode:

```bash
pip install -e .
```

2. Install pre-commit:

```bash
pip install pre-commit
```

### For Use in Other Projects

Add this repository to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/deerhide/cursor-pre-commit-hooks
    rev: v0.1.0  # Use the tag or branch you want
    hooks:
      - id: cursor-check
      - id: cursor-validate
```

Then install pre-commit hooks:

```bash
pre-commit install
```

## Available Hooks

### changelog-version

Automatically updates version and changelog based on commitizen-formatted commit messages:
- Analyzes commit message format
- Determines semantic version bump (major/minor/patch)
- Updates `pyproject.toml` version
- Updates or creates `CHANGELOG.md`
- Stages modified files

Runs at `commit-msg` stage automatically.

### auto-tag

Creates git tags based on the version in `pyproject.toml` (typically updated by `changelog-version`):
- Reads version from `pyproject.toml`
- Checks if tag already exists
- Creates git tag with format `v{version}` (e.g., `v1.2.3`)
- Skips if tag already exists

Runs automatically at `post-commit` stage when installed via pre-commit.

### cursor-check

Performs basic checks on Python files:
- Verifies files exist
- Checks for empty files
- Custom validation rules (customizable)

### cursor-validate

Validates Python code according to custom rules:
- Type hint validation
- Code structure checks
- Custom validation rules (customizable)

## Setting up auto-tag

The `auto-tag` hook uses pre-commit's built-in support for post-commit hooks. According to the [pre-commit documentation](https://pre-commit.com/#post-commit), you can install it as a post-commit hook:

1. Add the hook to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/deerhide/cursor-pre-commit-hooks
    rev: v0.1.0  # Use the tag or branch you want
    hooks:
      - id: changelog-version
      - id: auto-tag
```

2. Install the post-commit hook:

```bash
pre-commit install --hook-type post-commit
```

Now `auto-tag` will automatically run after every commit when `changelog-version` updates the version.

### Manual Execution

You can also run `auto-tag` manually after commits that trigger version bumps:

```bash
auto-tag
```

### Auto-tag Options

```bash
# Custom tag prefix (default: "v")
auto-tag --tag-prefix "release-"

# Custom tag message
auto-tag --message "Release version {version}"

# Fail if tag already exists (default: skip silently)
auto-tag --no-skip-if-exists
```

## Customization

Edit the hook files in `hooks/` directory to add your custom validation logic:

- `hooks/changelog_version.py` - Version and changelog updates
- `hooks/auto_tag.py` - Git tag creation
- `hooks/cursor_check.py` - Basic file checks
- `hooks/cursor_validate.py` - Code validation rules

## Development

### Setup

```bash
# Install dependencies
pip install -e ".[dev]"

# Install pre-commit hooks for this repo
pre-commit install
```

### Running Hooks Manually

```bash
# Run all hooks
pre-commit run --all-files

# Run specific hook
pre-commit run cursor-check --all-files
pre-commit run cursor-validate --all-files
```

### Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=hooks --cov-report=html
```

## Project Structure

```
cursor-pre-commit-hooks/
├── hooks/
│   ├── __init__.py
│   ├── changelog_version.py  # Version and changelog updates
│   ├── auto_tag.py           # Git tag creation
│   ├── cursor_check.py       # Basic file checks
│   └── cursor_validate.py    # Code validation
├── .pre-commit-hooks.yaml    # Hook definitions for pre-commit
├── pyproject.toml            # Project configuration
├── setup.py                  # Package setup
└── README.md                 # This file
```

## Adding New Hooks

1. Create a new Python file in `hooks/` directory
2. Implement a `main()` function that:
   - Takes `argv: Sequence[str] | None = None`
   - Returns `int` (0 for success, 1 for failure)
3. Add the hook to `.pre-commit-hooks.yaml`:

```yaml
- id: your-hook-id
  name: Your Hook Name
  description: Description of what the hook does
  entry: your-hook-id  # Must match the function name or entry point
  language: python
  types: [python]
  pass_filenames: true
```

4. Update `setup.py` to register the entry point in `entry_points.console_scripts`

## License

MIT
