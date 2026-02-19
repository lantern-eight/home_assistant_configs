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

# Structure

- [home_assistant_backup](home_assistant_backup): Folder that contains the backup of the
  Home Assistant configuration.
- [home_assistant_backup_comments](home_assistant_backup_comments): Since Home Assistant
  removes comments from the configuration, this folder has the same configurations but
  with comments in the code. It is used to compare the original configuration with the
  one after the redaction.
