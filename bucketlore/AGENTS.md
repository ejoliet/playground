@/Users/ejoliet/.codex/RTK.md

## Python environment policy

- Use `uv` for Python execution and dependency management, with a project-local `.venv`.
- Never invoke `python3` or Python aliases. Use `uv run --project <project-path> python`.
- Never install Python libraries globally or into the user site. Install dependencies only in the project's local environment using `uv`.
