# tx2tx Test Suite

Organized test structure for tx2tx project.

## Directory Structure

```
tests/
├── __init__.py
├── conftest.py              # Shared pytest fixtures and configuration
├── README.md                # This file
├── config_multi.yml         # Multi-client integration config fixture
├── unit/                    # Unit tests for individual modules
│   ├── __init__.py
│   ├── test_config.py
│   ├── test_pointer.py
│   ├── test_protocol.py
│   ├── test_settings.py
│   ├── test_types.py
│   └── test_zombie_client.py
├── integration/             # Integration tests
│   ├── __init__.py
│   ├── test_cursor_ops.py
│   ├── test_detailed.py
│   ├── test_multi_client.py
│   ├── test_phase7.py
│   ├── test_simple.py
│   └── test_with_client.py
├── manual/                  # Manual/interactive experiments and scripts
│   ├── check_feasibility.py
│   └── test_*.py
└── tools/                   # Testing and analysis utilities
    ├── __init__.py
    └── analyze.py
```

## Running Tests

### All tests
```bash
pytest
```

### Specific test categories
```bash
pytest tests/unit/              # Unit tests only
pytest tests/integration/       # Integration tests only
```

### Manual scripts (not part of normal pytest run)
```bash
python tests/manual/check_feasibility.py
```

### By marker
```bash
pytest -m unit                  # Tests marked as unit tests
pytest -m integration           # Tests marked as integration tests
pytest -m "not slow"            # Skip slow tests
pytest -m x11                   # Only X11-dependent tests
```

### Specific test file
```bash
pytest tests/unit/test_protocol.py
pytest tests/integration/test_cursor_ops.py
```

### With verbose output
```bash
pytest -v                       # Verbose
pytest -vv                      # Very verbose
pytest -s                       # Show print statements
```

## Test Categories

### Unit Tests (`tests/unit/`)
Tests for individual modules in isolation:
- Configuration loading and validation
- Settings singleton behavior
- Type classes and data structures
- Protocol serialization/parsing
- Zombie-client/name-collision behavior

### Integration Tests (`tests/integration/`)
Tests that verify component interaction:
- Cursor hide/show operations
- Server-client communication
- Screen transition logic
- Full system workflows

### Tools (`tests/tools/`)
Utilities for code quality and analysis:
- `analyze.py` - Static code analyzer for convergence analysis

### Manual (`tests/manual/`)
Ad-hoc and interactive checks for local environments. These may require a real display/session and are not treated as deterministic CI tests.

## Writing New Tests

### Unit Test Template
```python
import pytest
from tx2tx.common.settings import settings

@pytest.mark.unit
def test_something(reset_settings):
    """Test description"""
    # Arrange
    ...
    # Act
    ...
    # Assert
    assert result == expected
```

### Integration Test Template
```python
import pytest
from tx2tx.x11.display import DisplayManager

@pytest.mark.integration
@pytest.mark.x11
def test_system_behavior():
    """Test description"""
    # This test requires X11
    ...
```

## Fixtures

See `conftest.py` for available fixtures:
- `sample_config` - Loads test configuration
- `reset_settings` - Resets settings singleton between tests
- `setup_logging` - Configures logging for tests

## Markers

- `@pytest.mark.unit` - Unit test
- `@pytest.mark.integration` - Integration test
- `@pytest.mark.x11` - Requires X11 display
- `@pytest.mark.slow` - Long-running test
