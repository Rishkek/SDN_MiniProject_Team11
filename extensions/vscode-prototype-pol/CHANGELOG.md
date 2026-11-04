# Change Log

All notable changes to the "Prototype.pol Language Support" extension will be documented in this file.

## [0.1.0] - 2026-11-04

### Added
- Initial release of Prototype.pol VS Code language extension.
- Complete TextMate grammar for `.pol` (topology source) and `.pollib` (library) files.
- Syntax highlighting for keywords (`include`, `define`, `detail`, `macro`, `spawn`, `deploy`, etc.).
- Dedicated highlighting for special topology blocks (`__SPAWNS__`, `__CONNECTIONS__`).
- Support for `@` multipliers (`@kilo`, `@mega`, `@giga`), `@bundle`, and `@`-prefixed macros.
- Support for `&`-prefixed type references (`&sender`, `&switch`, `&ingress`).
- Modifiers recognition (`--unique`, `--common`).
- Data operations (`data.define`, `data.in`, `data.out`, `data.flow`).
- Scope resolution and field access operators (`::ports`, `::field.rate`).
- Number and unit combinations (`100@kilo`, `10@mega`).
- Full editor configuration with bracket matching, auto-closing, and automatic indentation after `:` and `{`.
- Comprehensive code snippets for definitions, details, macros, spawns, and connection tuples.
- Registered extension commands: `Compile Current File` and `Check Current File`.
