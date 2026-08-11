"""
bloodhound/report_format.py

Local markdown reports and Slack mrkdwn conversion.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")

_MD_BOLD = re.compile(r"\*\*([^*\n]+)\*\*")
_MD_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_FENCE = re.compile(r"```[\s\S]*?```")


def markdown_to_slack(text: str) -> str:
    """Convert markdown report bodies to Slack mrkdwn."""
    text = _wrap_tables_for_slack(text)
    placeholders: dict[str, str] = {}

    def _stash_fence(match: re.Match[str]) -> str:
        key = f"@@FENCE{len(placeholders)}@@"
        placeholders[key] = match.group(0)
        return key

    protected = _FENCE.sub(_stash_fence, text)
    converted = _MD_BOLD.sub(r"*\1*", protected)
    converted = _MD_ITALIC.sub(r"_\1_", converted)
    for key, value in placeholders.items():
        converted = converted.replace(key, value)
    return converted


def _wrap_tables_for_slack(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            block: list[str] = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append(lines[i])
                i += 1
            if out and out[-1] != "":
                out.append("")
            out.append("```")
            out.extend(block)
            out.append("```")
            out.append("")
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out).strip()


def format_report_section(title: str, body: str, *, output_format: str) -> str:
    if output_format == "markdown":
        return f"## {title}\n\n{body}\n"
    return f"\n{'=' * 72}\n{title}\n{'=' * 72}\n{body}\n"


class LocalReportWriter:
    def __init__(
        self,
        *,
        enabled: bool,
        output_format: str = "markdown",
        report_dir: str | Path | None = None,
        mode: str = "seek",
    ) -> None:
        self.enabled = enabled
        self.output_format = output_format if output_format in {"markdown", "plain"} else "markdown"
        self.report_dir = Path(report_dir or "reports")
        self.mode = mode
        self._sections: list[str] = []

    def add(self, title: str, body: str) -> str:
        section = format_report_section(title, body, output_format=self.output_format)
        if self.enabled:
            self._sections.append(section)
        return section

    def flush(self) -> Path | None:
        if not self.enabled or not self._sections:
            return None

        self.report_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(_ET).strftime("%Y-%m-%d_%H%M%S")
        suffix = "md" if self.output_format == "markdown" else "txt"
        path = self.report_dir / f"bloodhound-{self.mode}-{ts}.{suffix}"

        if self.output_format == "markdown":
            header = (
                f"# Bloodhound v2 — local dry run (`{self.mode}`)\n\n"
                f"- Generated: {datetime.now(_ET).strftime('%Y-%m-%d %I:%M %p ET')}\n\n"
                "---\n\n"
            )
            content = header + "\n---\n\n".join(self._sections)
        else:
            content = "\n".join(self._sections)

        path.write_text(content, encoding="utf-8")
        return path
