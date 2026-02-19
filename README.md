# home_assistant_configs

# Tests

Run all tests with:

```bash
uv run pytest tests/ -v
```

- **`uv run`** — Executes the command in the project's managed virtual environment,
  ensuring the correct dependencies (including pytest from dev dependencies) are
  available.
- **`pytest tests/`** — Discovers and runs all test modules in the `tests/` directory.
- **`-v`** — Verbose mode; shows each test name and its pass/fail status.
