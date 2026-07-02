```markdown
# playground Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill teaches the development patterns and conventions used in the `playground` Python repository. It covers file naming, import/export styles, commit patterns, and testing approaches, providing practical examples and command suggestions to streamline your workflow.

## Coding Conventions

### File Naming
- Use **camelCase** for file names.
  - Example: `myModule.py`, `dataProcessor.py`

### Import Style
- Use **relative imports** within the project.
  - Example:
    ```python
    from .utils import helperFunction
    ```

### Export Style
- Use **named exports** by explicitly listing public objects in `__all__`.
  - Example:
    ```python
    __all__ = ['myFunction', 'MyClass']
    ```

### Commit Patterns
- Commit messages are **freeform** (no strict prefixes).
- Average commit message length is ~20 characters.
  - Example:  
    ```
    add new feature to parser
    ```

## Workflows

### Adding a New Module
**Trigger:** When you need to add a new feature or component.
**Command:** `/add-module`

1. Create a new Python file using camelCase naming (e.g., `myFeature.py`).
2. Implement your functions/classes.
3. Use relative imports to reference other modules.
4. Define `__all__` for named exports.
5. Write or update corresponding test files (`myFeature.test.py`).
6. Commit your changes with a concise, descriptive message.

### Running Tests
**Trigger:** When you want to verify your code changes.
**Command:** `/run-tests`

1. Locate test files matching the `*.test.*` pattern.
2. Run tests using your preferred Python test runner (e.g., `pytest`, `unittest`).
   - Example:
     ```bash
     pytest myFeature.test.py
     ```
3. Review test output and fix any failures.

## Testing Patterns

- Test files follow the pattern: `*.test.*` (e.g., `myFeature.test.py`).
- The specific test framework is **unknown**; use standard Python testing tools.
- Place tests alongside or near the modules they test.
- Example test file structure:
  ```python
  import unittest
  from .myFeature import myFunction

  class TestMyFunction(unittest.TestCase):
      def test_basic(self):
          self.assertEqual(myFunction(2), 4)
  ```

## Commands
| Command        | Purpose                                          |
|----------------|--------------------------------------------------|
| /add-module    | Scaffold and add a new module with conventions   |
| /run-tests     | Run all tests matching the `*.test.*` pattern    |
```
