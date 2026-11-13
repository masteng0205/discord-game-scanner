"""Minimal parser for Valve's text KeyValues (VDF/ACF) format."""

from __future__ import annotations

_ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"'}


def _tokens(text: str):
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c == "/" and text.startswith("//", i):
            i = text.find("\n", i)
            if i == -1:
                return
        elif c in "{}":
            yield c
            i += 1
        elif c == '"':
            i += 1
            buf = []
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    buf.append(_ESCAPES.get(text[i + 1], text[i + 1]))
                    i += 2
                else:
                    buf.append(text[i])
                    i += 1
            i += 1  # closing quote
            yield "".join(buf)
        else:  # unquoted token
            j = i
            while j < n and not text[j].isspace() and text[j] not in '{}"':
                j += 1
            yield text[i:j]
            i = j


def loads(text: str) -> dict:
    """Parse VDF text into nested dicts. Keys are kept as-is (case preserved)."""
    root: dict = {}
    stack = [root]
    key: str | None = None
    for tok in _tokens(text):
        if tok == "{":
            child: dict = {}
            stack[-1][key if key is not None else ""] = child
            stack.append(child)
            key = None
        elif tok == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
        elif key is None:
            key = tok
        else:
            stack[-1][key] = tok
            key = None
    return root


def get_ci(d: dict, *path: str):
    """Case-insensitive nested lookup; returns None if any step is missing."""
    cur = d
    for part in path:
        if not isinstance(cur, dict):
            return None
        lowered = part.lower()
        cur = next((v for k, v in cur.items() if k.lower() == lowered), None)
        if cur is None:
            return None
    return cur
