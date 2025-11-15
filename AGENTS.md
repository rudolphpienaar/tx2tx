# AI Agent Guidelines for Software Development

## Purpose
These guidelines help AI coding assistants work effectively with software projects by emphasizing verification over assumption, architectural thinking over quick fixes, and traceability over convenience.

## Project Structure & Module Organization
Treat the repository as the canonical source of truth for implementation decisions. When primary documentation exists (e.g., architecture docs, design specs), keep it factual, cite verifiable sources, and maintain consistency with code. Organize executable code under `src/` or similar, grouped logically (by language, by feature, or by layer), and ensure any new module includes documentation stating entry points, dependencies, and interfaces.

Before making changes, understand the project's build and test workflows. For Python projects, verify virtual environment usage, dependency management (requirements.txt, pyproject.toml, poetry, etc.), and module execution patterns. For other languages, identify equivalent patterns. Run tests with the project's test runner and understand CI/CD requirements.

## Coding Style & Naming Conventions
Follow the project's established style guide rigorously. Check for:
- Style guide documents (STYLE.md, CONTRIBUTING.md, .editorconfig)
- Linter configurations (.pylintrc, .eslintrc, pyproject.toml)
- Formatter settings (black, prettier, rustfmt)
- Type checking configuration (mypy.ini, tsconfig.json)

When no explicit style guide exists, maintain consistency with existing code patterns. Preserve indentation style, naming conventions, import organization, and documentation formats. Co-locate configuration files with their consumers and annotate them clearly.

## Testing Guidelines
Mirror the project's test structure exactly. If tests live in `tests/` mirroring `src/`, or in `__tests__/` alongside source files, or use a different convention—follow it precisely. Keep tests deterministic by controlling randomness seeds and mocking external dependencies. Store test fixtures in established locations and update them when contracts change. Ensure test suites pass before considering work complete.

## Commit & Pull Request Guidelines
Use the project's commit convention (Conventional Commits, semantic versioning triggers, issue references). Write concise, imperative commit subjects. Reference related issues or design documents in commit bodies. Flag breaking changes explicitly. For pull requests, summarize impact, list verification steps performed, and attach evidence when behavior cannot be captured by automated tests.

## Security & Operational Notes
Never commit sensitive data (credentials, API keys, PII, production data). Use sanitized mocks and test fixtures. Manage secrets through environment variables, vault systems, or secure configuration management. Document required environment variables in example files (.env.example). When adding functionality that handles sensitive data, document security boundaries and validation requirements.
---

# Core Development Principles

## 1. No Hacky Solutions
**Never** implement post-processing scripts to work around architectural problems.

**Bad Example:**
```python
# scripts/fix_generated_paths.py - rewriting paths after build
def fix_paths(output_file):
    content = re.sub(r'build/assets/', r'../assets/', content)
```

**Good Example:**
```makefile
# Run build tools from the correct directory so paths are right from the start
cd $(BUILD_DIR) && $(BUILD_TOOL) --outdir=dist --asset-path=./assets
```

**Rationale:** If you need a script to "fix" generated output, you're solving the problem at the wrong layer. Fix the root cause—where files are generated, what working directory tools run from, or how paths are configured.

---

## 2. No Band-Aid Fixes
Don't make one build target secretly invoke another just to avoid solving the real problem.

**Bad Example:**
```makefile
# Making format-b target just copy format-a output
$(BUILD_DIR)/output-format-b.pdf: $(BUILD_DIR)/output-format-a.pdf
	cp $< $@
```

**Good Example:**
```makefile
# Proper conversion pipeline for format-b target
$(BUILD_DIR)/output-format-b.pdf: $(BUILD_DIR)/intermediate.html
	python3 scripts/convert_to_format_b.py $< $@
```

**Rationale:** Each build target should do what its name says. If you can't implement it properly, either rename it to reflect what it actually does or invest the time to build the real solution.

---

## 3. Reference Files In Place
Don't extract, copy, or scatter files around the build directory. Reference originals directly.

**Bad Example:**
```makefile
# Build tool extracts assets to random hash-named files
build-tool input.xml --extract-media=$(BUILD_DIR) -o output.html
# Result: build/ polluted with 3ecd16f49bec256309630878c0f44a0254506bba.png
```

**Good Example:**
```makefile
# Reference assets directly from their organized location
build-tool input.xml --resource-path=$(BUILD_DIR):$(ASSETS_DIR):. -o output.html
# Assets stay in assets/ and are referenced by meaningful names
```

**Rationale:** Files have canonical locations. Use resource paths, working directories, or relative paths to reference them cleanly. Don't pollute build directories with duplicates or hash-named garbage.

---

## 4. Organize Build Outputs by Variant
Each build variant gets its own subdirectory with all intermediates and outputs contained within.

**Structure:**
```
build/
├── production/             # Production build
│   ├── app.js
│   ├── app.css
│   ├── index.html
│   └── bundle.map
├── development/            # Development build with debug symbols
│   ├── app.js
│   ├── app.css
│   └── index.html
├── staging/                # Staging environment build
└── shared/                 # Shared assets referenced by all variants
    ├── images/
    ├── fonts/
    └── data/
```

**Rationale:** Clean separation allows multiple build variants to coexist. Shared assets live in a dedicated location and are referenced by all variants. Intermediates stay with their variant, not scattered at the build root.

---

## 5. Make Everything Traceable
Every number, parameter, and decision should trace back to an explicit source.

**Example:**
```yaml
# config/parameters.yaml
application:
  rate_limit: 100
  timeout_seconds: 30
  cache_ttl: 3600
```

```python
# src/server.py
from config import load_parameters

params = load_parameters('config/parameters.yaml')
rate_limit = params.application.rate_limit  # Traced to config file
```

```markdown
# docs/configuration.md
All runtime parameters are defined in `config/parameters.yaml`.
Run `app --dry-run` to validate configuration.
```

**Rationale:** Reviewers should be able to trace every value to its source. No magic numbers in code or documentation. Reference the source explicitly, and provide tools to validate configuration.

---

## 6. Modularize for Composition
Break large systems into focused modules that can be composed into different configurations.

**Code Structure:**
```
src/
├── main.py              # Full application: all features
├── minimal.py           # Minimal build: core only
└── modules/
    ├── core.py
    ├── analytics.py
    ├── export.py
    └── ...
```

**Composition Pattern:**
```python
# main.py - Full application
from modules import core, analytics, export

def run():
    core.initialize()
    analytics.start()
    export.enable()

# minimal.py - Minimal build
from modules import core

def run():
    core.initialize()
```

**Rationale:** One source of truth (the modules) composes into multiple delivery configurations. Clean module boundaries enable selective inclusion without duplication.

---

## 7. Architectural Fixes Over Workarounds
When something doesn't work, fix the architecture—don't add duct tape.

**Problem:** Assets not found during build process
**Bad Solution:** Script to rewrite paths after build completion
**Good Solution:** Configure the build tool with correct working directory and resource paths

**Problem:** Feature X not working in output format Y
**Bad Solution:** Copy output from format Z and rename it to format Y
**Good Solution:** Implement proper conversion pipeline or use a tool that supports format Y natively

**Problem:** Tests failing due to environment differences
**Bad Solution:** Disable the failing tests or add environment-specific conditionals
**Good Solution:** Use containerization or environment management to ensure consistent test environments

**Rationale:** Workarounds compound over time and create maintenance debt. Architectural fixes scale cleanly and maintain clarity.

---

## Build System Best Practices

### Make/Build Configuration

1. **Use meaningful variable names:**
   ```makefile
   DIST_DIR := $(BUILD_DIR)/dist
   APP_BASENAME := $(DIST_DIR)/app
   APP_BUNDLE := $(APP_BASENAME).js
   APP_STYLES := $(APP_BASENAME).css
   ```

2. **Declare dependencies explicitly:**
   ```makefile
   SRC_FILES := $(wildcard src/**/*.js)
   $(APP_BUNDLE): $(SRC_FILES) $(CONFIG_FILE) | $(DIST_DIR)
       $(BUNDLER) --input src/main.js --output $@
   ```

3. **Run tools from the correct working directory:**
   ```makefile
   # Build tool needs to find assets/, so run from project root
   cd $(PROJECT_ROOT) && $(BUILD_TOOL) --outdir=dist src/main.js
   ```

4. **Keep phony targets organized:**
   ```makefile
   .PHONY: all build test clean lint format install
   ```

---

## Documentation Standards

### Structure and Cross-References

1. **Keep sections properly separated:**
   ```markdown
   # Section 1

   Content here...

   # Section 2

   Content here...
   ```
   Proper spacing between sections improves readability and prevents rendering issues.

2. **Use cross-references, not hardcoded section numbers:**
   ```markdown
   Bad:  See Section 8 for details.
   Good: See [Configuration](#configuration) for details.
   ```

3. **Define anchors for key sections:**
   ```markdown
   ## Configuration {#configuration}

   Or use heading links:
   [Jump to Configuration](#configuration)
   ```

4. **Keep documentation close to code:**
   - API documentation → docstrings/inline comments
   - Module documentation → README in module directory
   - Architecture decisions → ADR (Architecture Decision Records)
   - User guides → top-level docs/ directory

---

## Code Review Checklist

Before committing, ask:

- [ ] Does this solve the problem architecturally, or am I adding a workaround?
- [ ] Are files being referenced from their canonical location, or am I copying/extracting them unnecessarily?
- [ ] Are build outputs organized by variant in clean subdirectories?
- [ ] Can someone trace this number/parameter back to its source?
- [ ] If I'm writing a "fix_*" script, should I be fixing the root cause instead?
- [ ] Does each build target/task do what its name promises?
- [ ] Are all dependencies declared explicitly in the build configuration?
- [ ] Have I verified implementation details against actual code rather than assuming based on patterns?
- [ ] Are tests passing and does the code follow the project's style guide?
- [ ] Is documentation updated to reflect the changes?

---

## AI Agent Verification Guidelines

### 8. Verify Implementation Before Pattern Matching

**Never** answer questions about implementation details based on assumed conventions or common patterns. Always verify against actual code.

**Bad Example:**
```
User: What's the command to start the server?
AI: Based on typical CLI patterns, try `app server` and `app client`
```

**Good Example:**
```
User: What's the command to start the server?
AI: Let me check the CLI implementation first...
    [Reads cli.py or runs --help]
    The server starts with `app` and the client with `app --server HOST:PORT`
```

**Verification Requirements by Question Type:**

| Question About | Verification Method |
|---------------|-------------------|
| CLI commands | Read CLI parser code or run `--help` |
| Configuration format | Read config files and parsing code |
| State transitions | Read state machine implementation |
| API endpoints | Read route definitions |
| Function behavior | Read function source and tests |
| File locations | Use `find`, `glob`, or directory traversal |
| Class interfaces | Read class definition and type signatures |

**Rationale:** Pattern matching creates technical debt in conversations. A single wrong assumption compounds through follow-up questions and wastes user time on debugging phantom issues. Verification takes seconds and ensures accuracy. Treat code as the source of truth, not your training data.

**Exception:** When explicitly asked for general advice or common patterns (e.g., "What's a typical way to structure a CLI?"), pattern matching is appropriate. The key distinction is whether the question is about **this codebase** (verify) or **general practice** (advise).

---

## Summary

**Clean architecture beats clever workarounds.**

Write code that makes the next person say "this makes sense" rather than "what the hell is this script doing?"
