"""
Lexical analyzer (Tokenizer) for the Prototype.pol language.
"""

import re
from typing import List, NamedTuple, Optional


class Token(NamedTuple):
    type: str
    value: str
    line: int
    column: int


class LexerError(ValueError):
    """Raised when an unrecognized character or malformed token is encountered."""
    pass


KEYWORDS = {
    "include", "define", "detail", "instance", "data", "macro",
    "spawn", "alias", "var", "machine", "bundle", "unpack",
    "connect_multi", "deploy", "grid", "return", "ports",
    "pull", "define_multi", "as", "topology", "spawns", "connections"
}


class Lexer:
    """Tokenizes Prototype.pol and .pollib source code."""

    def __init__(self, source: str, filepath: str = ""):
        self.source = source
        self.filepath = filepath
        self.length = len(source)
        self.pos = 0
        self.line = 1
        self.col = 1

    def tokenize(self) -> List[Token]:
        tokens: List[Token] = []

        while self.pos < self.length:
            ch = self.source[self.pos]

            # Whitespace
            if ch in " \t\r":
                self._advance()
                continue

            if ch == "\n":
                self.line += 1
                self.col = 1
                self.pos += 1
                continue

            # Special directive: #padding=<num>
            if ch == "#" and self.source[self.pos:self.pos + 9] == "#padding=":
                start_line, start_col = self.line, self.col
                self.pos += 9
                self.col += 9
                m = re.match(r"\d+", self.source[self.pos:])
                if m:
                    val = m.group(0)
                    self.pos += len(val)
                    self.col += len(val)
                    tokens.append(Token("PADDING_DIRECTIVE", val, start_line, start_col))
                    continue

            # Comments (# or // or /* ... */)
            if ch == "/" and self.pos + 1 < self.length and self.source[self.pos + 1] == "*":
                self.pos += 2
                self.col += 2
                while self.pos + 1 < self.length and not (self.source[self.pos] == "*" and self.source[self.pos + 1] == "/"):
                    if self.source[self.pos] == "\n":
                        self.line += 1
                        self.col = 1
                    else:
                        self.col += 1
                    self.pos += 1
                if self.pos + 1 < self.length:
                    self.pos += 2
                    self.col += 2
                continue

            if ch == "#" or (ch == "/" and self.pos + 1 < self.length and self.source[self.pos + 1] == "/"):
                while self.pos < self.length and self.source[self.pos] != "\n":
                    self.pos += 1
                continue

            # Double symbols
            if ch == ":" and self.pos + 1 < self.length and self.source[self.pos + 1] == ":":
                tokens.append(Token("DOUBLE_COLON", "::", self.line, self.col))
                self.pos += 2
                self.col += 2
                continue

            # Modifiers (--unique, --common)
            if ch == "-" and self.pos + 1 < self.length and self.source[self.pos + 1] == "-":
                start_line, start_col = self.line, self.col
                self.pos += 2
                self.col += 2
                m = re.match(r"[a-zA-Z_][a-zA-Z0-9_]*", self.source[self.pos:])
                if m:
                    mod_name = m.group(0)
                    self.pos += len(mod_name)
                    self.col += len(mod_name)
                    tokens.append(Token("MODIFIER", f"--{mod_name}", start_line, start_col))
                    continue
                tokens.append(Token("DOUBLE_MINUS", "--", start_line, start_col))
                continue

            # Directives (__SPAWNS__, __CONNECTIONS__)
            if ch == "_" and self.source[self.pos:self.pos + 2] == "__":
                m = re.match(r"__[a-zA-Z0-9_]+__", self.source[self.pos:])
                if m:
                    dir_val = m.group(0)
                    tokens.append(Token("DIRECTIVE", dir_val, self.line, self.col))
                    self._advance(len(dir_val))
                    continue

            # Strings
            if ch in ('"', "'"):
                quote = ch
                start_line, start_col = self.line, self.col
                self.pos += 1
                self.col += 1
                chars = []
                while self.pos < self.length and self.source[self.pos] != quote:
                    if self.source[self.pos] == "\\":
                        self.pos += 1
                        if self.pos < self.length:
                            chars.append(self.source[self.pos])
                    else:
                        chars.append(self.source[self.pos])
                    self.pos += 1
                    self.col += 1
                if self.pos < self.length:
                    self.pos += 1
                    self.col += 1
                tokens.append(Token("STRING", "".join(chars), start_line, start_col))
                continue

            # Numbers (with optional @unit multiplier suffix: 100@kilo, 10@mega)
            if ch.isdigit():
                start_line, start_col = self.line, self.col
                m = re.match(r"\d+(\.\d+)?", self.source[self.pos:])
                num_str = m.group(0)
                self._advance(len(num_str))

                # Check if immediately followed by @unit
                if self.pos < self.length and self.source[self.pos] == "@":
                    self._advance(1)
                    m_unit = re.match(r"[a-zA-Z_][a-zA-Z0-9_]*", self.source[self.pos:])
                    if m_unit:
                        unit_str = m_unit.group(0)
                        self._advance(len(unit_str))
                        tokens.append(Token("NUMBER_WITH_UNIT", f"{num_str}@{unit_str}", start_line, start_col))
                        continue
                    else:
                        tokens.append(Token("NUMBER", num_str, start_line, start_col))
                        tokens.append(Token("AT", "@", self.line, self.col))
                        continue

                tokens.append(Token("NUMBER", num_str, start_line, start_col))
                continue

            # Symbols starting with & (like &sender, &ingress)
            if ch == "&":
                start_line, start_col = self.line, self.col
                self._advance(1)
                m = re.match(r"[a-zA-Z_][a-zA-Z0-9_]*", self.source[self.pos:])
                if m:
                    ident = m.group(0)
                    self._advance(len(ident))
                    tokens.append(Token("AMP_IDENT", f"&{ident}", start_line, start_col))
                    continue
                tokens.append(Token("AMP", "&", start_line, start_col))
                continue

            # Symbols starting with @ (like @switch, @kilo, @bundle)
            if ch == "@":
                start_line, start_col = self.line, self.col
                self._advance(1)
                m = re.match(r"[a-zA-Z_][a-zA-Z0-9_]*", self.source[self.pos:])
                if m:
                    ident = m.group(0)
                    self._advance(len(ident))
                    tokens.append(Token("AT_IDENT", f"@{ident}", start_line, start_col))
                    continue
                tokens.append(Token("AT", "@", start_line, start_col))
                continue

            # Identifiers & dotted compound identifiers (e.g. machine.host.sender, field.rate)
            if ch.isalpha() or ch == "_":
                start_line, start_col = self.line, self.col
                # Match identifier segment possibly separated by single dots
                m = re.match(r"[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*", self.source[self.pos:])
                ident = m.group(0)
                self._advance(len(ident))

                # Check if it's a standalone keyword
                if ident in KEYWORDS:
                    tokens.append(Token(ident.upper(), ident, start_line, start_col))
                else:
                    tokens.append(Token("IDENT", ident, start_line, start_col))
                continue

            # Single-character tokens
            simple_tokens = {
                ":": "COLON",
                ";": "SEMICOLON",
                ",": "COMMA",
                "(": "LPAREN",
                ")": "RPAREN",
                "[": "LBRACKET",
                "]": "RBRACKET",
                "{": "LBRACE",
                "}": "RBRACE",
                "=": "EQUALS",
                "+": "PLUS",
                "-": "MINUS",
                "*": "STAR",
                "/": "SLASH",
                ".": "DOT",
                "<": "LANGLE",
                ">": "RANGLE",
                "!": "BANG",
            }
            if ch in simple_tokens:
                tokens.append(Token(simple_tokens[ch], ch, self.line, self.col))
                self._advance(1)
                continue

            raise LexerError(
                f"Unexpected character '{ch}' at {self.filepath or '<source>'}:{self.line}:{self.col}"
            )

        tokens.append(Token("EOF", "", self.line, self.col))
        return tokens

    def _advance(self, count: int = 1):
        self.pos += count
        self.col += count
