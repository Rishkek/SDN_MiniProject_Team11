# Prototype.pol Language Support for Visual Studio Code

Official VS Code language support extension for **Prototype.pol**, the declarative Domain-Specific Language (DSL) for software-defined network (SDN) topology synthesis and traffic simulation.

Provides syntax highlighting, automatic indentation, code snippets, and compilation commands for both `.pol` topology sources and `.pollib` library definitions.

---

## Features

- **Rich Syntax Highlighting:**
  - Keywords: `include`, `define`, `detail`, `macro`, `instance`, `spawn`, `alias`, `return`, `deploy`, `unpack`, `connect_multi`, `grid`.
  - Topology Sections: `__SPAWNS__`, `__CONNECTIONS__`.
  - Modifiers: `--unique`, `--common`.
  - Data Operations: `data.define`, `data.in`, `data.out`, `data.flow`, `data`.
  - Type References: `&sender`, `&switch`, `&ingress`, `&egress`, `&cable`.
  - Macro & Unit Identifiers: `@switch_t`, `@bundle`, `@bit`, `@byte`, `@kilo`, `@mega`, `@giga`.
  - Unit Scaled Literals: `100@kilo`, `10@mega`, `1@giga`.
  - Field and Port Resolution: `::ports("in")`, `::field.rate("out")`, `::field.delay`.
  - Comments: `# ...` line comments.
  - Quoted Strings: `"in"`, `"out"`, `"any"`, etc.

- **Smart Editor Support:**
  - Automatic indentation after block headers ending in `:` or `{` (e.g. `detail sender:`, `__SPAWNS__ {`, `connect_multi {`).
  - Bracket pair colorization and matching for `{}`, `[]`, `()`.
  - Auto-closing pairs for braces, brackets, parentheses, and quotes.

- **Productivity Snippets:**
  - `include` — Include library statement.
  - `define` — Define device type reference (`--unique` / `--common`).
  - `detail` — Component detail configuration block.
  - `macro` — Parameterized macro definition.
  - `spawns` — Topology `__SPAWNS__` block.
  - `connections` — Topology `__CONNECTIONS__` block with `unpack bundle;` and `connect_multi`.
  - `spawn` — Spawn an entity alias.
  - `conn` — Connection tuple `(source, cable, destination)`.
  - `deploy` — Layout deploy directive.
  - `data` — Local data variable declaration.
  - `dataop` — Data flow operation (`data.flow`, `data.in`, `data.out`, `data.define`).
  - `detail-cable` — Full multi-speed cable detail block with high, medium, low speed instances.

- **Extension Commands:**
  - `Prototype.pol: Compile Current File` (`Ctrl+Shift+P` -> `prototype.compileCurrentFile`)
  - `Prototype.pol: Check Current File` (`Ctrl+Shift+P` -> `prototype.checkCurrentFile`)

---

## Installation

### Method 1: Install from VS Code GUI
1. Open Visual Studio Code.
2. Open the **Extensions** view (`Ctrl+Shift+X`).
3. Click the **`...`** (More Actions) menu in the top-right corner of the Extensions panel.
4. Select **Install from VSIX...**.
5. Select `prototypelanguage-0.1.0.vsix` from `extensions/vscode-prototype-pol/`.

### Method 2: Command Line (CLI)
From the root workspace directory, run:
```powershell
code --install-extension extensions/vscode-prototype-pol/prototypelanguage-0.1.0.vsix
```

---

## File Association

| Extension | Language Mode | Description |
| :--- | :--- | :--- |
| `.pol` | `Prototype.pol` | Topology definition source file |
| `.pollib` | `Prototype.pol Library` | Reusable component and property library |

---

## Extension Settings

This extension contributes the following settings:

* `prototype.compilerPath`: Absolute or relative path to `polc.py` or the compiler binary. (Defaults to detecting `polc.py` in the workspace root).
* `prototype.outputDirectory`: Relative folder where compiled `.json` topologies will be written (default: `"topology_src"`).

---

## Example Syntax Preview

```text
include lib.machine
include lib.wire
include lib.data

define &sender machine.host.sender
define &ingress machine.switch --unique
define &switch machine.switch --common
define &cable wire --common

grid OFF

detail sender:
    data send_rate;
    data.out(send_rate, 100@kilo);
    sender::field.rate("out") = send_rate;

detail cable:
    instance high_speed
    data rate;
    detail high_speed:
        data.flow(rate, 100@mega);
        high_speed::field.rate("any") = rate;

detail machine.topology.layout:
    machine bundle[16];

    __SPAWNS__ {
        spawn cable.high_speed 4 alias hi;
        spawn ingress alias s1;
        spawn switch alias s2;
        spawn sender alias h1;
    }@bundle #padding=0

    __CONNECTIONS__ {
        unpack bundle;
        connect_multi {
            (h1, hi, s1);
            (s1, hi, s2);
        }
    }

deploy:
    machine.topology.layout;
```

---

## License
MIT
