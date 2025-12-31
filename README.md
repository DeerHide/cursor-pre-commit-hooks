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

## Customization

Edit the hook files in `hooks/` directory to add your custom validation logic:

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
│   ├── cursor_check.py      # Basic file checks
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

4. Update `setup.py` or `pyproject.toml` to register the entry point if needed

## License

MIT
