# Contributing to Stendly Python SDK

Thank you for considering contributing! This document provides guidelines and information for contributors.

## Getting Started

### Prerequisites

- Python 3.9+
- Poetry (for dependency management)
- Git

### Setup

1. **Clone the repository:**

```bash
git clone https://github.com/stendly/stendly-python.git
cd stendly-python
```

2. **Install dependencies with Poetry:**

```bash
poetry install
```

This installs all dependencies including dev tools (pytest, ruff, mypy, etc.).

3. **Activate the virtual environment:**

```bash
poetry shell
```

Or use `poetry run` prefix for individual commands:

```bash
poetry run pytest
```

4. **Run tests to verify setup:**

```bash
pytest
```

## Development Workflow

### Making Changes

1. Create a new branch for your feature/fix:

```bash
git checkout -b feature/amazing-feature
# or
git checkout -b fix/bug-name
```

2. Make changes to the code. Follow these guidelines:
   - Write type hints for all functions
   - Add docstrings with examples (Google style or NumPy style)
   - Keep changes focused (one change per PR)
   - Update tests alongside code changes

3. **Run linter:**

```bash
ruff check stendly/
```

4. **Format code:**

```bash
ruff format stendly/
```

5. **Run type checker:**

```bash
mypy stendly/
```

6. **Run tests:**

```bash
pytest
```

For full coverage report:

```bash
pytest --cov=stendly --cov-report=html
```

7. **Run all checks:**

```bash
pre-commit run --all-files
```

### Code Style

We follow [PEP 8](https://pep8.org/) with these modifications:
- Line length: 100 characters
- Use double quotes for strings
- 4 spaces indentation
- Type hints required for public methods
- Google-style docstrings (see existing code)

**Example:**

```python
def create_intent(
    self,
    amount_cents: int,
    order_id: str,
    terminal_id: Optional[UUID] = None,
) -> PaymentIntent:
    """
    Create a new payment intent.
    
    Args:
        amount_cents: Amount to charge in cents
        order_id: Unique order reference
        terminal_id: Optional terminal UUID
    
    Returns:
        PaymentIntent object
    
    Raises:
        ValidationError: If parameters are invalid
    """
    ...
```

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): description

[optional body]

[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style (formatting, no logic change)
- `refactor`: Code restructuring
- `test`: Adding tests
- `chore`: Maintenance tasks

Examples:
```
feat(intents): add support for terminal_id
fix(webhooks): correct timestamp validation edge case
docs(client): add FastAPI integration example
```

### Pull Request Process

1. **Update documentation** if you're changing public APIs
   - Update docstrings
   - Update README.md if needed
   - Add examples for new features

2. **Add tests** for new functionality
   - Target >95% coverage
   - Include both unit tests and integration tests (if applicable)

3. **Update CHANGELOG.md** with your changes under `[Unreleased]`

4. **Create a Pull Request** with:
   - Clear title (Conventional Commits format)
   - Description explaining the change
   - Link to any related issues
   - Screenshots if UI/UX changes

5. **Wait for review** - we'll review within 2-3 business days

### Testing Guidelines

#### Unit Tests

- Test all public methods
- Mock external HTTP calls (httpx)
- Cover success and error paths
- Test edge cases and validation

```python
def test_create_intent_success():
    """Successful intent creation."""
    # Arrange
    client = Client(api_key="test")
    
    # Act
    intent = client.intents.create(amount_cents=1000, order_id="test")
    
    # Assert
    assert intent.status == "pending"
```

#### Integration Tests

Integration tests (marked with `@pytest.mark.integration`) require:
- `STENDLY_TEST_KEY` environment variable (devnet key)
- Live API calls to devnet

Run only unit tests:

```bash
pytest -m "not integration"
```

Run integration tests:

```bash
pytest -m integration
```

### Documentation

- Every public method needs a docstring with:
  - Description
  - Args section (with types)
  - Returns section (with type)
  - Raises section (all exceptions)
  - At least one example

- Use reStructuredText or Google style (consistent with existing code)

- Examples must be executable (test with doctest if possible)

### Security

- Never commit secrets (API keys, webhook secrets)
- Use `hmac.compare_digest` for constant-time comparisons
- Validate all inputs
- Sanitize error messages (don't leak internal details)
- Cryptographic operations: use hashlib/hmac only

## Project Structure

```
stendly-python/
├── stendly/
│   ├── __init__.py          # Public API exports
│   ├── client.py            # Client & AsyncClient
│   ├── exceptions.py        # All exceptions
│   ├── models.py            # Pydantic models
│   ├── _http.py             # Internal HTTP client
│   └── namespaces/          # API namespaces
│       ├── intents.py
│       ├── terminals.py
│       ├── webhooks.py
│       └── merchant.py
├── tests/
│   ├── test_sdk.py          # Main test suite
│   └── conftest.py          # Test fixtures
├── docs/                    # Additional documentation
├── pyproject.toml           # Project configuration
├── README.md               # User documentation
├── CHANGELOG.md            # Version history
└── CONTRIBUTING.md         # This file
```

## Common Tasks

### Adding a new API method

1. Add method to appropriate namespace file
2. Add type hints and docstring with example
3. Add request/response models to `models.py` if needed
4. Add tests in `tests/test_sdk.py`
5. Update README if user-facing

### Adding a new exception type

1. Add class to `exceptions.py` (inherit from `StendlyError`)
2. Add detailed docstring
3. Add error handling in `_http.py` (`_handle_error_response`)
4. Add tests

### Updating models

1. Modify Pydantic models in `models.py`
2. Add field validators if needed
3. Update tests
4. Regenerate documentation if API changes

## Questions?

Open an issue or discussion on GitHub:
- Bug reports: [GitHub Issues](https://github.com/stendly/stendly-python/issues)
- Feature requests: [GitHub Discussions](https://github.com/stendly/stendly-python/discussions)
- Questions: support@stendly.com

---

Thank you for contributing to Stendly! 🚀
