# ChRONOS Python Style Guide

## Language Version
**Python 3.11+** - Use modern Python features including:
- Type union syntax: `str | None` instead of `Optional[str]`
- `from __future__ import annotations` for forward references
- Structural pattern matching where appropriate

---

## Naming Convention: RPN (Reverse Polish Notation) Style

Functions and methods follow a **noun_verb** pattern, placing the subject before the action.

### Pattern
```
<subject>[descriptor]_<action>[modifier]
```

### Examples

**Standard Python (verb-noun):**
```python
def get_user_names() -> list[str]: ...
def is_login_valid() -> bool: ...
def parse_user_data(raw: str) -> dict: ...
```

**ChRONOS RPN (noun-verb):**
```python
def userNames_get() -> list[str]: ...
def login_isValidCheck() -> bool: ...
def dataFromUser_parse(raw: str) -> dict: ...
```

### Real Examples from Codebase

```python
# projections.py
def projection_build(assumptions: ScenarioAssumptions, years: Iterable[int]) -> ProjectionResult:
    """Build projection from assumptions across given years."""
    ...

def siteTrajectory_calculate(assumptions: ScenarioAssumptions, year: int) -> float:
    """Calculate site count trajectory for a given year."""
    ...

def revenueStreams_calculate(
    assumptions: ScenarioAssumptions,
    year: int,
    site_count: float,
    new_sites: float,
) -> dict[str, float]:
    """Calculate all revenue streams for a given year."""
    ...

# assumptions.py
@classmethod
def assumptionBook_load(cls, path: Path) -> "AssumptionBook":
    """Load assumption book from YAML file."""
    ...
```

### Rationale
- **Subject-first thinking:** Makes it clear *what* is being operated on
- **Grouping:** Related operations on the same subject cluster together alphabetically
- **Searchability:** Easy to find all operations on a subject (e.g., grep for `site.*_`)

---

## Type Hints: Pervasive and Explicit

**Every function, method, and variable** that isn't trivially obvious must have type hints.

### Function Signatures
```python
# ✓ GOOD: Complete type hints
def revenueStreams_calculate(
    assumptions: ScenarioAssumptions,
    year: int,
    site_count: float,
    new_sites: float,
) -> dict[str, float]:
    ...

# ✗ BAD: Missing return type
def revenueStreams_calculate(
    assumptions: ScenarioAssumptions,
    year: int,
    site_count: float,
    new_sites: float,
):
    ...
```

### Local Variables
Type hints on local variables when the type isn't obvious from initialization:

```python
# ✓ GOOD: Clear from initialization
revenue_install: float = new_sites * install_fee / 1_000_000.0

# ✓ GOOD: Type hint clarifies intent
projections_map: dict[str, ProjectionResult] = {}

# ✗ BAD: Type unclear
result = {}  # What type is this?
```

### Collections
Be specific about collection contents:

```python
# ✓ GOOD
def columns_get() -> list[str]: ...
def results_map() -> dict[str, ProjectionResult]: ...

# ✗ BAD: Generic types hide information
def columns_get() -> list: ...
def results_map() -> dict: ...
```

---

## Return Types: Models for Non-Primitives

**Any non-primitive return type should be a defined model class.**

### Use dataclass or BaseModel

**dataclass** - Default choice for pure data structures:
```python
from dataclasses import dataclass

@dataclass
class ProjectionResult:
    scenario: str
    columns: list[str]
    rows: list[dict[str, float]]
```

**BaseModel (Pydantic)** - When environment variable injection or validation is needed:
```python
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

class DatabaseConfig(BaseSettings):
    """Config that can load from environment variables."""
    host: str = Field(default="localhost", env="DB_HOST")
    port: int = Field(default=5432, env="DB_PORT")

    class Config:
        env_file = ".env"
```

### When to Use Each

| Use Case | Model Type | Rationale |
|----------|-----------|-----------|
| Pure data structure | `dataclass` | Simpler, native Python, no dependencies |
| Config from env vars | `BaseSettings` (Pydantic) | Automatic environment variable binding |
| API request/response | `BaseModel` (Pydantic) | Validation and serialization |
| Complex validation | `BaseModel` (Pydantic) | Field validators and constraints |

### Examples

```python
# ✓ GOOD: Defined model
@dataclass
class FundingRound:
    year: int
    amount: float
    label: str

def fundingRounds_get() -> list[FundingRound]:
    ...

# ✗ BAD: Returns unstructured dict
def fundingRounds_get() -> list[dict[str, Any]]:
    ...
```

---

## Method Length: Contextual Refactoring

No hard line limit. Refactor based on **multiple factors**:

### Primary Signals
1. **Nesting depth** - More than 3 levels suggests extraction
2. **Responsibility count** - Method doing >1 conceptual task
3. **Readability** - Can you explain it in one sentence?
4. **Repetition** - Same logic appearing multiple times

### Example: Good Length with Clarity

```python
def projection_build(
    assumptions: ScenarioAssumptions, years: Iterable[int]
) -> ProjectionResult:
    """Build complete projection from assumptions across given years."""
    yearly_rows: list[dict[str, float]] = []
    sorted_years: list[int] = sorted({int(year) for year in years})
    previous_sites: float = 0.0

    for year_int in sorted_years:
        site_count_value: float = siteTrajectory_calculate(assumptions, year_int)
        new_sites_value: float = max(site_count_value - previous_sites, 0.0)
        revenue_components = revenueStreams_calculate(
            assumptions, year_int, site_count_value, new_sites_value
        )
        total_revenue_value: float = sum(revenue_components.values())

        variable_expense_value, staffing_cost_value = expensesEnvelope_calculate(
            assumptions, year_int, total_revenue_value, site_count_value
        )
        total_expense_value: float = variable_expense_value + staffing_cost_value
        net_value: float = total_revenue_value - total_expense_value

        funding_value: float = fundingInjection_calculate(assumptions, year_int)
        grant_value: float = grantsReceipt_calculate(assumptions, year_int)
        net_cash_value: float = net_value + funding_value + grant_value

        row: dict[str, float] = {
            "year": float(year_int),
            "sites": site_count_value,
            # ... rest of row construction
        }
        yearly_rows.append(row)
        previous_sites = site_count_value

    return ProjectionResult(scenario=assumptions.name, columns=columns, rows=yearly_rows)
```

**Why this is acceptable length:**
- Single clear responsibility: orchestrate projection building
- Each calculation delegated to focused helper
- Linear flow, no deep nesting
- Well-named variables make intent clear

### When to Extract

```python
# ✗ BAD: Too much nesting and multiple concerns
def config_process(raw_config: dict) -> ProcessedConfig:
    if "database" in raw_config:
        db = raw_config["database"]
        if "host" in db:
            if db["host"].startswith("postgres://"):
                # Parse connection string
                parts = db["host"].split("://")[1].split(":")
                if len(parts) == 2:
                    host, port = parts[0], int(parts[1])
                    # Validate port range
                    if 1024 <= port <= 65535:
                        # ... more logic
```

**Should become:**
```python
def config_process(raw_config: dict) -> ProcessedConfig:
    """Process raw configuration into validated config object."""
    db_config = databaseConfig_extract(raw_config)
    db_validated = databaseConfig_validate(db_config)
    return ProcessedConfig(database=db_validated)

def databaseConfig_extract(raw_config: dict) -> DatabaseRaw:
    """Extract database configuration section."""
    ...

def databaseConfig_validate(config: DatabaseRaw) -> DatabaseValidated:
    """Validate database configuration parameters."""
    ...
```

---

## Code Structure Principles

### 1. Explicit Over Implicit
```python
# ✓ GOOD: Clear intent
revenue_install: float = new_sites * install_fee / 1_000_000.0
revenue_subscription: float = site_count * subscription_fee / 1_000_000.0

# ✗ BAD: Magic number obscured
revenue_install = new_sites * install_fee / 1e6
```

### 2. One Source of Truth
```python
# ✓ GOOD: Configuration drives behavior
assumptions: ScenarioAssumptions = ...
site_count = siteTrajectory_calculate(assumptions, year)

# ✗ BAD: Hardcoded values
site_count = 10 * (1.25 ** year)  # Where did 10 and 1.25 come from?
```

### 3. Type Safety Over Flexibility
```python
# ✓ GOOD: Specific types
def results_merge(
    base: ProjectionResult,
    overlay: ProjectionResult
) -> ProjectionResult:
    ...

# ✗ BAD: Overly generic
def results_merge(base: Any, overlay: Any) -> Any:
    ...
```

---

## Import Organization

```python
"""Module docstring."""
from __future__ import annotations  # Always first

# Standard library
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# Third-party
import yaml
from pydantic import BaseModel

# Local
from fintech.models.assumptions import AssumptionBook
from fintech.utils.conversions import float_safe
```

---

## Documentation

**Documentation Standard: Google-style docstrings**

All Python code uses Google-style docstrings with explicit Args, Returns, Raises, and Attributes sections. Every module, class, and function must be documented.

### Module-Level Docstrings
**Every module** must have a comprehensive module-level docstring explaining:
- Purpose and scope
- Key classes/functions provided
- Usage examples (if applicable)
- Dependencies or assumptions

```python
"""Projection engine for financial forecasting.

This module transforms assumption configurations into multi-year financial projections.
It implements deterministic calculations for revenue streams, expenses, and cash flow
based on site growth trajectories and funding scenarios.

Key components:
    - ProjectionResult: Container for projection output (scenario, columns, rows)
    - projection_build: Main entry point for building single-scenario projections
    - projectionBook_run: Batch processor for multi-scenario projection books
    - siteTrajectory_calculate: Site count growth calculator
    - revenueStreams_calculate: Revenue breakdown by stream type
    - expensesEnvelope_calculate: Variable and staffing expense calculator

Typical usage:
    assumptions = ScenarioAssumptions(...)
    result = projection_build(assumptions, years=range(2026, 2036))

Dependencies:
    - Requires ScenarioAssumptions and AssumptionBook from models.assumptions
    - All monetary values are in USD millions unless otherwise specified
"""
from __future__ import annotations
...
```

### Function/Method Docstrings
Use **explicit Google-style docstrings** with complete parameter and return documentation:

```python
def siteTrajectory_calculate(assumptions: ScenarioAssumptions, year: int) -> float:
    """Calculate projected site count for a given year based on compound growth.

    Applies exponential growth from initial pilot site count starting at the pilot
    start year. Returns zero for years before pilot launch. Growth rate compounds
    annually from the base site count defined in assumptions.

    Args:
        assumptions: Scenario configuration containing pilot_sites parameters including
            start_year (float), initial_sites (float), and annual_growth (float).
        year: Target projection year as integer (e.g., 2027).

    Returns:
        Projected number of active sites as float. Returns 0.0 for years before
        the pilot start year, otherwise returns base_sites * (1 + growth)^years_elapsed.

    Example:
        >>> assumptions = ScenarioAssumptions(
        ...     pilot_sites={"start_year": 2027, "initial_sites": 2.0, "annual_growth": 0.25}
        ... )
        >>> siteTrajectory_calculate(assumptions, 2029)
        3.125  # 2.0 * (1.25^2)
    """
    ...
```

### Complex Docstring Examples

**Multiple return values:**
```python
def expensesEnvelope_calculate(
    assumptions: ScenarioAssumptions,
    year: int,
    revenue: float,
    site_count: float,
) -> tuple[float, float]:
    """Calculate variable expenses and staffing costs for a given year.

    Computes two expense categories: variable expenses (scaling with revenue)
    and staffing costs (scaling with headcount). Variable expenses include
    OPEX and COGS rates applied to total revenue. Staffing costs apply a
    prelaunch fraction if the year is before pilot start.

    Args:
        assumptions: Scenario configuration containing staffing parameters
            (base_headcount, headcount_per_site, avg_salary, prelaunch_fraction)
            and expense rates (opex dict, infrastructure.cogs_rate).
        year: Target projection year as integer.
        revenue: Total revenue for the year in USD millions.
        site_count: Number of active sites for staffing calculation.

    Returns:
        Tuple of (variable_expense, staffing_cost) both as floats in USD millions.
        - variable_expense: Revenue-scaled expenses from OPEX and COGS rates
        - staffing_cost: Headcount-based salary expenses with prelaunch adjustment

    Example:
        >>> assumptions = ScenarioAssumptions(...)
        >>> var_exp, staff_cost = expensesEnvelope_calculate(assumptions, 2027, 10.5, 5.0)
        >>> print(f"Variable: ${var_exp:.2f}M, Staffing: ${staff_cost:.2f}M")
    """
    ...
```

**With raised exceptions:**
```python
def assumptionBook_load(cls, path: Path) -> "AssumptionBook":
    """Load financial assumption book from YAML configuration file.

    Parses a YAML file containing scenario definitions with pilot sites,
    revenue streams, staffing, funding rounds, and other parameters. Converts
    all numeric values to floats for consistent calculation.

    Args:
        path: Filesystem path to YAML configuration file. Must exist and contain
            valid YAML with a 'scenarios' top-level key.

    Returns:
        AssumptionBook instance containing parsed scenario configurations mapped
        by scenario name (e.g., "base", "pessimistic", "high_velocity").

    Raises:
        FileNotFoundError: If the specified path does not exist.
        yaml.YAMLError: If the file contains invalid YAML syntax.
        KeyError: If required configuration keys are missing from scenarios.

    Example:
        >>> book = AssumptionBook.assumptionBook_load(Path("assumptions.yaml"))
        >>> base_scenario = book.scenarios["base"]
    """
    ...
```

**Class/dataclass documentation:**
```python
@dataclass
class ProjectionResult:
    """Container for multi-year financial projection output.

    Stores the results of running a projection calculation for a single scenario
    across multiple years. The rows represent yearly snapshots, and columns define
    the financial metrics tracked (sites, revenues, expenses, cash flows).

    Attributes:
        scenario: Human-readable scenario name (e.g., "base", "high_velocity").
        columns: Ordered list of metric names matching keys in each row dict.
            Typical columns: year, sites, install_revenue, subscription_revenue,
            marketplace_revenue, total_revenue, total_expense, net_profit, net_cash.
        rows: List of yearly financial snapshots, one dict per year. Each dict
            maps column names to float values representing that year's metrics.
            All monetary values are in USD millions.

    Example:
        >>> result = ProjectionResult(
        ...     scenario="base",
        ...     columns=["year", "sites", "total_revenue"],
        ...     rows=[
        ...         {"year": 2027.0, "sites": 2.0, "total_revenue": 0.45},
        ...         {"year": 2028.0, "sites": 2.5, "total_revenue": 1.2},
        ...     ]
        ... )
    """
    scenario: str
    columns: list[str]
    rows: list[dict[str, float]]
```

### Comments
Use sparingly—prefer clear naming. Comments explain **why** unusual decisions were made:

```python
# Convert to millions for readability in financial reports
revenue_install: float = new_sites * install_fee / 1_000_000.0

# Phase 1 grants are amortized equally across phase1_years
if phase1_years > 0 and year < start_year + phase1_years:
    return phase1_amount / max(phase1_years, 1)  # Avoid division by zero
```

---

## Summary Checklist

- [ ] Python 3.11+ features used where appropriate
- [ ] All functions use RPN naming: `subject_action` pattern
- [ ] Pervasive type hints on parameters, returns, and non-obvious variables
- [ ] Non-primitive returns use `dataclass` or `BaseModel` (Pydantic when env vars needed)
- [ ] Methods refactored based on nesting depth, responsibility count, and clarity—not arbitrary line limits
- [ ] Explicit variable names with clear intent
- [ ] One source of truth (config-driven, not hardcoded)
- [ ] Type-safe interfaces preferred over flexible/generic types
- [ ] Imports organized: future, stdlib, third-party, local
- [ ] **Every module has comprehensive module-level docstring** (purpose, key components, usage, dependencies)
- [ ] **Every function/method has complete Google-style docstring:**
  - [ ] Short description of what it does
  - [ ] Args section with each parameter explained (type, purpose, constraints)
  - [ ] Returns section explaining return value structure and meaning
  - [ ] Raises section if exceptions can be raised
  - [ ] Example showing typical usage (when helpful)
- [ ] **Every class/dataclass has docstring with:**
  - [ ] Purpose and use case
  - [ ] Attributes section explaining each field
  - [ ] Example showing construction and usage
- [ ] Comments used sparingly to explain unusual decisions (not what code does)
