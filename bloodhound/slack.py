"""
bloodhound/slack.py

Slack API wrapper with chunked posting for long reports.
"""

from __future__ import annotations

from dataclasses import dataclass

from slack_sdk import WebClient

SLACK_TEXT_LIMIT = 3900


@dataclass(frozen=True)
class SlackNotifier:
    client: WebClient
    scan_channel_id: str
    alert_channel_id: str

    @classmethod
    def from_token(cls, bot_token: str, scan_channel_id: str, alert_channel_id: str) -> "SlackNotifier":
        return cls(
            client=WebClient(token=bot_token),
            scan_channel_id=scan_channel_id,
            alert_channel_id=alert_channel_id,
        )

    def post_scan(self, text: str) -> None:
        self._post_chunked(self.scan_channel_id, text)

    def post_alert(self, text: str) -> None:
        self._post_chunked(self.alert_channel_id, text)

    def _post_chunked(self, channel_id: str, text: str) -> None:
        for chunk in split_slack_text(text):
            self.client.chat_postMessage(channel=channel_id, text=chunk)


def split_slack_text(text: str, limit: int = SLACK_TEXT_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in text.splitlines(keepends=True):
        if len(line) > limit:
            if current:
                chunks.append("".join(current).rstrip())
                current, current_len = [], 0
            for i in range(0, len(line), limit):
                chunks.append(line[i : i + limit].rstrip())
            continue

        if current_len + len(line) > limit:
            chunks.append("".join(current).rstrip())
            current, current_len = [line], len(line)
        else:
            current.append(line)
            current_len += len(line)

    if current:
        chunks.append("".join(current).rstrip())

    total = len(chunks)
    if total <= 1:
        return chunks

    out: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        out.append(f"[{idx}/{total}]\n{chunk}")
    return out
