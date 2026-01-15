# Contributing to half-orm-dev

Thank you for considering contributing to half-orm-dev! This guide will help you get started.

> **Note:** half-orm-dev is in **alpha development phase**. While we strive for stability, breaking changes may occur as we refine the architecture. Please report any issues at https://github.com/half-orm/half-orm-dev/issues

---

## Table of Contents

- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Running Tests](#running-tests)
- [Code Style and Conventions](#code-style-and-conventions)
- [Adding New Features](#adding-new-features)
- [Submitting Changes](#submitting-changes)

---

## Getting Started

### Prerequisites

- **Python 3.9+** required
- **PostgreSQL 12+** recommended for integration tests
- **Git** for version control

### Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/half-orm/half-orm-dev.git
cd half-orm-dev

# Create virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode
pip install -e .

# Verify installation
half_orm dev --help
```

---

## Development Workflow

### Basic Commands

```bash
# Run CLI directly (installed entry point)
half_orm dev --help

# Or via Python module
python -m half_orm_dev.cli.main --help

# Run all tests
pytest

# Run with coverage
pytest --cov=half_orm_dev --cov-report=html
```

### Project Structure

```
half-orm-dev/
├── half_orm_dev/          # Main package
│   ├── cli/              # CLI commands
│   │   └── commands/     # Command implementations
│   ├── database.py       # PostgreSQL operations
│   ├── patch_manager.py  # Patch lifecycle
│   ├── release_manager.py # Release management
│   ├── repo.py           # Repository singleton
│   └── version.txt       # Single source of truth for version
├── tests/                # Test suite
│   ├── cli/             # CLI tests
│   ├── patch_manager/   # PatchManager tests
│   └── cli_integration/ # End-to-end tests
└── docs/                # Documentation
    └── ARCHITECTURE.md  # Technical architecture details
```

---

## Running Tests

### Test Categories

```bash
# Run all tests (unit + integration)
pytest

# Run only unit tests (fast, no database required)
pytest -m "not integration"

# Run only integration tests (requires PostgreSQL)
pytest -m integration

# Run specific test file
pytest tests/patch_manager/test_patch_manager_create.py

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=half_orm_dev --cov-report=html
# Open htmlcov/index.html in browser
```

### Test Organization

Tests mirror the source structure:
- `tests/patch_manager/` → `half_orm_dev/patch_manager.py`
- `tests/cli/` → `half_orm_dev/cli/`
- `tests/cli_integration/` → End-to-end workflow tests

**Fixtures** (in `conftest.py`):
- `tmp_repo`: Temporary repository with initialized structure
- `test_db`: PostgreSQL test database (requires `@pytest.mark.integration`)

### Writing Tests

When adding new features, always include tests:

1. **Unit tests** for isolated logic
2. **Integration tests** for database operations
3. **CLI tests** for command-line interface

Example test structure:
```python
import pytest
from half_orm_dev.patch_manager import PatchManager

def test_patch_creation(tmp_repo):
    """Test patch directory creation."""
    patch_mgr, repo, temp_dir, patches_dir = tmp_repo

    # Test logic here
    assert result == expected
```

---

## Code Style and Conventions

### Python Style

- Follow **PEP 8** style guide
- Use **type hints** for function signatures
- Add **docstrings** for public methods (Google style)
- Keep functions **focused and testable**

Example:
```python
def create_patch(self, patch_id: str) -> Path:
    """
    Create a new patch directory and branch.

    Args:
        patch_id: Unique patch identifier (e.g., "456-user-auth")

    Returns:
        Path to created patch directory

    Raises:
        PatchManagerError: If patch already exists
    """
    # Implementation
```

### Patch Naming Conventions

Patch IDs must follow this format: `NUMBER-descriptive-name`

**Examples:**
- `123-add-user-authentication` ✅
- `456-fix-email-validation` ✅
- `add-feature` ❌ (missing required number)

**GitHub/GitLab Integration:**
The number prefix is required and serves to automatically close the corresponding issue when the patch is merged. For example, merging patch `123-feature` will automatically close issue #123 in your repository.

### Key Patterns

#### Error Handling
Custom exceptions inherit from base exceptions:
```python
RepoError → OutdatedHalfORMDevError
PatchManagerError → PatchStructureError, PatchFileError
ReleaseManagerError → ReleaseVersionError, ReleaseFileError
```

#### Version Management
Version is stored in `half_orm_dev/version.txt`:
- Format: `X.Y.Z` or `X.Y.Z-suffix` (e.g., `0.17.3-a1`)
- `setup.py` dynamically calculates half_orm dependency

#### Configuration Files
- `.hop/config`: Repository configuration (hop_version, git_origin, devel)
- `.hop/releases/`: Release files (TOML for dev, TXT for RC/prod)
- `.hop/model/schema.sql`: Production schema (symlink to versioned file)

### Security Considerations

When contributing, keep these principles in mind:

- **No command injection**: Never use `shell=True` with subprocess
- **Validate user input**: Sanitize branch names, patch IDs, versions
- **Minimal privileges**: Design features to work without superuser access
- **No hardcoded credentials**: Always use configuration files
- **SQL injection prevention**: Use parameterized queries

---

## Adding New Features

### Adding a New CLI Command

1. **Create command function** in `half_orm_dev/cli/commands/`

```python
# half_orm_dev/cli/commands/mycommand.py
import click

@click.command()
def my_command():
    """Brief description of what this command does."""
    # Implementation
```

2. **Register command** in `half_orm_dev/cli/commands/__init__.py`

```python
from .mycommand import my_command

ALL_COMMANDS = {
    # ...
    'my-command': my_command,
}
```

3. **Update CLI group** in `cli/main.py` to include command in appropriate context

4. **Add tests** in `tests/cli/test_mycommand.py`

### Modifying Release Workflow

Release logic is centralized in `ReleaseManager`:
- Version calculation: `_calculate_next_version()`
- Release creation: `create_release()`
- Promotion: `promote_stage_to_rc()`, `promote_stage_to_production()`

When modifying, update both `ReleaseManager` and corresponding CLI commands.

### Adding Database Operations

Database operations go in `Database` class (`database.py`):
- Use `psycopg2` for connections
- Always use transactions for schema changes
- Support both production and development modes
- Avoid requiring superuser privileges when possible

Example:
```python
def new_operation(self):
    """New database operation."""
    try:
        self.model.execute_query("""
            -- Your SQL here
        """)
    except Exception as e:
        raise DatabaseError(f"Operation failed: {e}") from e
```

### Repository Migrations

When repository structure changes:

1. Create migration in `half_orm_dev/migrations/X/Y/Z/` (version directory)
2. Migration file is Python module with `apply()` function
3. Update `MigrationManager` to handle new migration path
4. Test migration with `tests/migration_manager/`

---

## Submitting Changes

### Before Submitting

1. **Run tests**: Ensure all tests pass
   ```bash
   pytest
   ```

2. **Check code style**: Follow PEP 8
   ```bash
   # Optional: use linter
   flake8 half_orm_dev/
   ```

3. **Update documentation**:
   - Update `docs/ARCHITECTURE.md` if you changed core components
   - Update README.md if you added user-facing features
   - Update this file if you changed development workflow

4. **Add tests**: All new features must have tests

### Pull Request Process

1. **Fork the repository** and create a branch from `main`

2. **Make your changes** with clear, atomic commits

3. **Push to your fork** and submit a pull request

4. **Fill out the PR template** completely:
   - Description of changes
   - Type of change (bug fix, feature, etc.)
   - Related issue number
   - Testing performed

5. **Wait for review**: Maintainers will review and provide feedback

### Commit Message Guidelines

Use clear, descriptive commit messages:

```
type: brief description (50 chars or less)

More detailed explanatory text, if necessary. Wrap at 72 characters.
Explain what and why, not how.

Fixes #123
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `test`: Adding or updating tests
- `refactor`: Code refactoring
- `chore`: Maintenance tasks

Examples:
```
feat: add support for Docker PostgreSQL containers

fix: recreate public schema after DROP CASCADE

docs: update ARCHITECTURE.md with database security improvements

test: add integration tests for schema restoration
```

---

## Building and Publishing

### Building Package

```bash
# Build package (requires clean repo on main branch)
make build

# This creates dist/ directory with wheel and sdist
```

### Publishing to PyPI

```bash
# Publish to PyPI (runs build first)
# Requires PyPI credentials
make publish
```

**Note:** Only maintainers can publish to PyPI.

---

## Getting Help

- **Issues**: https://github.com/half-orm/half-orm-dev/issues
- **Discussions**: https://github.com/half-orm/half-orm-dev/discussions
- **Documentation**: See `docs/ARCHITECTURE.md` for technical details

---

## Resources

- **Technical Architecture**: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **User Workflow**: [README.md](README.md)
- **half-orm**: https://github.com/half-orm/half-orm

---

Thank you for contributing to half-orm-dev! Your efforts help make database development better for everyone.
