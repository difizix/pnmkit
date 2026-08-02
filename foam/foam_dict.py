"""Brace-depth-aware OpenFOAM dictionary editing (Phase 1 — Generic core).

Replaces the unsafe sed/regex approaches from foam.bashrc and foam_run.py with
a proper brace-counting block extractor that correctly handles nested sections.

Uses FileKV(file, entry, value) where entry is either:
- "keyword" -> whole-file keyword match (section=None)
- "section.keyword" -> block-scoped keyword match
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FileKV:
    """Represents a single OpenFOAM keyword edit.

    Args:
        file: Relative path to the file within the case directory.
        entry: The keyword, or section.keyword to modify (e.g. "U", "endTime", "Left.value").
        value: The new value (without trailing semicolon; caller adds it).
        optional: If True, do not raise error if section or keyword is not found.
        insert_if_missing: If True and `keyword` isn't present in the (required)
            section block, insert `keyword value;` before the block's closing
            brace instead of raising. Only meaningful with a section.
    """

    file: str
    entry: str
    value: str
    optional: bool = False
    insert_if_missing: bool = False

    def __post_init__(self) -> None:
        assert self.entry.count(".") <= 1, f"entry '{self.entry}' must have at most one dot (section.keyword or keyword)"

def _find_section_block(text: str, section_name: str) -> tuple[int, int] | None:
    """Find the start/end byte offsets of a top-level section block by brace-counting.

    Returns the (start, end) offsets enclosing the entire section block including
    the section name line and the closing brace. Returns None if not found.

    This correctly handles nested braces — the block ends at the matching brace
    for the section's opening brace, not the first `}` encountered.
    """
    # Match section name followed by an opening brace (allow whitespace/newlines between).
    header_re = re.compile(r"^\s*" + re.escape(section_name) + r"\s*\{", re.MULTILINE)
    m = header_re.search(text)
    if not m:
        return None

    brace_start = m.end() - 1  # position of the opening '{'
    depth = 0
    pos = brace_start
    while pos < len(text):
        ch = text[pos]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return (m.start(), pos + 1)
        pos += 1
    return None  # unmatched brace


def _replace_keyword_in_text(text: str, keyword: str, new_value: str, start: int, end: int) -> str:
    """Replace a keyword's value within a given text range [start:end].

    Finds the first occurrence of `keyword` followed by optional whitespace and
    a value ending with `;`, and replaces the value (keeping the keyword and
    semicolon). Raises ValueError if the keyword is not found or found multiple
    times in the range.

    Returns the modified text, or raises on mismatch.
    """
    sub_text = text[start:end]

    # Match: keyword followed by whitespace/colon, then value up to semicolon.
    pattern = re.compile(
        r"^([ \t]*" + re.escape(keyword) + r"[ \t:]+)" + r"(.*?);",
        re.MULTILINE | re.DOTALL,
    )
    matches = list(pattern.finditer(sub_text))

    if len(matches) == 0:
        msg = f"Keyword '{keyword}' not found in specified range"
        raise ValueError(msg)
    if len(matches) > 1:
        # Check if exactly one match is at depth 0 within sub_text (root level)
        depth_0 = []
        depth = 0
        m_idx = 0
        for i, ch in enumerate(sub_text):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            elif m_idx < len(matches) and i == matches[m_idx].start():
                if depth == 0:
                    depth_0.append(matches[m_idx])
                m_idx += 1
        if len(depth_0) == 1:
            matches = depth_0
        else:
            msg = f"Keyword '{keyword}' found {len(matches)} times in specified range; expected exactly one"
            raise ValueError(msg)

    m = matches[0]
    clean_val = new_value.strip().rstrip(";")
    new_sub = sub_text[: m.start(2)] + clean_val + sub_text[m.end(2) :]
    return text[:start] + new_sub + text[end:]


def _insert_or_replace_keyword(text: str, keyword: str, new_value: str, start: int, end: int) -> str:
    """Like _replace_keyword_in_text, but inserts `keyword value;` before the
    block's closing brace if `keyword` isn't present, instead of raising.
    """
    sub_text = text[start:end]
    pattern = re.compile(
        r"^([ \t]*" + re.escape(keyword) + r"[ \t:]+)" + r"(.*?);",
        re.MULTILINE | re.DOTALL,
    )
    if pattern.search(sub_text):
        return _replace_keyword_in_text(text, keyword, new_value, start, end)

    clean_val = new_value.strip().rstrip(";")
    closing_brace = sub_text.rstrip().rfind("}")
    if closing_brace == -1:
        msg = f"No closing brace found to insert '{keyword}' into"
        raise ValueError(msg)
    new_sub = sub_text[:closing_brace] + f"    {keyword} {clean_val};\n" + sub_text[closing_brace:]
    return text[:start] + new_sub + text[end:]


def apply_edits(case_dir: Path, edits: Sequence[FileKV]) -> None:
    """Apply a list of FileKV edits to OpenFOAM dictionary files.

    For each edit:
    - If entry has no dot (section is None/empty): replace keyword anywhere in the file.
    - If entry is "section.keyword": first locate that section block (brace-counting),
      then replace the keyword only within that block.

    Args:
        case_dir: Root directory of the OpenFOAM case.
        edits: Sequence of FileKV edits to apply.

    Raises:
        FileNotFoundError: If the target dictionary file doesn't exist.
        ValueError: If a keyword is not found or found multiple times in scope.
    """
    for param in edits:
        assert param.entry.count(".") <= 1, f"entry '{param.entry}' must have at most one dot (section.keyword or keyword)"
        if "." in param.entry:
            section, keyword = param.entry.split(".", 1)
            section = section if section else None
        else:
            section, keyword = None, param.entry

        abs_path = case_dir / param.file
        if not abs_path.exists():
            msg = f"File {param.file} not found in {case_dir}"
            raise FileNotFoundError(msg)

        text = abs_path.read_text()

        if section:
            # Block-scoped: find the section first, then edit within it.
            block = _find_section_block(text, section)
            if block is None:
                if param.optional:
                    continue
                msg = f"Section '{section}' not found in {param.file}"
                raise ValueError(msg)
            start, end = block
        else:
            # Whole-file scope.
            start, end = 0, len(text)

        try:
            if param.insert_if_missing:
                text = _insert_or_replace_keyword(text, keyword, param.value, start, end)
            else:
                text = _replace_keyword_in_text(text, keyword, param.value, start, end)
        except ValueError:
            if param.optional:
                continue
            raise
        abs_path.write_text(text)
