"""ExamplesChunker — domain-aware chunking of domains/*/examples.md files.

Phase 1A.3 Batch B (★ HIGH-RISK per PLAN §4.4 R-1 / R-2).

Dispatch is decided per H2 (each `## ` heading owns the range up to the next `## `):
  - Nested: the H2 range contains an H4 starting with "Method " (PC
    `## §6.3.5.9.3 ...` → `### Example N` → `#### Method A/B/C/D`) — 1 chunk per H4,
    ending at the next H4 or the end of the H2 range. example_index comes from the
    parent H3 inside the same H2; sub_label from the H4. PC Example 4 has only
    Method A + D, so that H2 yields 14 chunks (not 16).
  - Flat (every other H2, e.g. TA / IS / DS / EX / DM / MB, and PC's `## PC – Examples`
    added in newer KB versions) — 1 chunk per H2, example_index parsed from the H2.
  - cdisc_section_id is taken only from the chunk's own H2 (`§x.y...` prefix), else None.
  - Text before the first H2 is not chunked.
  - chunk_index runs 0.. across the whole file in document order.

Locks honored (per docs/evidence/checkpoints/phase_1a_0_sanity.md §4):
  - L-1 mermaid: status-machine via base.find_mermaid_blocks (0 nesting verified).
  - L-2 GFM pipe-table: simple regex via base.find_table_blocks.
  - L-3 token count: BaseChunker._new_chunk auto-fills via tiktoken cl100k_base.

Headings that fall inside a protected (mermaid/table) block are defensively dropped
(should not happen per 1A.0.b, but cheap insurance).
"""

from __future__ import annotations

import re
from pathlib import Path

from .base import (
    BaseChunker,
    Chunk,
    find_mermaid_blocks,
    find_table_blocks,
    heading_positions,
    is_inside_block,
)

# §-prefix CDISC section id (e.g., "§6.3.5.9.3"). Captures up to the trailing space.
_SECTION_ID_RE = re.compile(r"^(§[\d.]+)\b")

# "Example N" — extracts the trailing index (allows leading prefix text).
_EXAMPLE_INDEX_RE = re.compile(r"\bExample\s+(\d+)\b", re.IGNORECASE)

# "Method X" — captures the letter token (A/B/C/D...).
_METHOD_RE = re.compile(r"\bMethod\s+([A-Z][A-Za-z0-9]*)\b")


def _parse_example_index(text: str) -> int | None:
    m = _EXAMPLE_INDEX_RE.search(text)
    return int(m.group(1)) if m else None


def _parse_sub_label(text: str) -> str | None:
    m = _METHOD_RE.search(text)
    return f"Method {m.group(1)}" if m else None


def _parse_section_id(text: str) -> str | None:
    m = _SECTION_ID_RE.match(text)
    return m.group(1) if m else None


def _range_contains_block(
    start: int, end: int, blocks: list[tuple[int, int]]
) -> bool:
    """True if any block overlaps the [start, end) byte range."""
    for bs, be in blocks:
        if bs < end and be > start:
            return True
    return False


def _filter_protected(
    headings: list[tuple[int, str]],
    blocks: list[tuple[int, int]],
) -> list[tuple[int, str]]:
    """Drop heading positions that fall inside any protected block (defensive)."""
    if not blocks:
        return headings
    return [(pos, txt) for pos, txt in headings if not is_inside_block(pos, blocks)]


class ExamplesChunker(BaseChunker):
    """Chunk a domains/*/examples.md file. Per-H2 dispatch (H2 flat vs H4 nested)."""

    file_type = "examples"

    def chunk(self, file_path: Path) -> list[Chunk]:
        text = file_path.read_text(encoding="utf-8")
        domain = file_path.parent.name  # e.g. "TA" / "PC" / "IS" / "DS"

        mermaid_blocks = find_mermaid_blocks(text)
        table_blocks = find_table_blocks(text)
        protected = mermaid_blocks + table_blocks

        h2s = _filter_protected(heading_positions(text, 2), protected)
        h3s = _filter_protected(heading_positions(text, 3), protected)
        h4s = _filter_protected(heading_positions(text, 4), protected)

        # (start, end, section, cdisc_section_id, example_index, sub_label), doc order.
        spans: list[tuple[int, int, str, str | None, int | None, str | None]] = []
        for i, (h2_start, h2_text) in enumerate(h2s):
            h2_end = h2s[i + 1][0] if i + 1 < len(h2s) else len(text)
            section_id = _parse_section_id(h2_text)
            h4_in = [(p, t) for p, t in h4s if h2_start <= p < h2_end]
            if not any(t.startswith("Method ") for _, t in h4_in):
                spans.append(
                    (h2_start, h2_end, h2_text, section_id,
                     _parse_example_index(h2_text), None)
                )
                continue
            h3_in = [(p, t) for p, t in h3s if h2_start <= p < h2_end]
            for j, (start, heading) in enumerate(h4_in):
                end = h4_in[j + 1][0] if j + 1 < len(h4_in) else h2_end
                parent_h3 = next((t for p, t in reversed(h3_in) if p < start), None)
                example_index = (
                    _parse_example_index(parent_h3) if parent_h3 else None
                )
                spans.append(
                    (start, end, heading, section_id, example_index,
                     _parse_sub_label(heading))
                )

        return [
            self._new_chunk(
                source=str(file_path),
                text=text[start:end],
                chunk_index=idx,
                domain=domain,
                section=heading,
                cdisc_class=None,
                cdisc_section_id=section_id,
                example_index=example_index,
                sub_label=sub_label,
                has_mermaid=_range_contains_block(start, end, mermaid_blocks),
                has_table=_range_contains_block(start, end, table_blocks),
                ct_code=None,
                ct_extensible=None,
                part_index=None,
                table_chunk_idx=None,
            )
            for idx, (start, end, heading, section_id, example_index, sub_label)
            in enumerate(spans)
        ]
