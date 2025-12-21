from __future__ import annotations

from dataclasses import dataclass

from slack_sdk import WebClient


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
        self.client.chat_postMessage(channel=self.scan_channel_id, text=text)

    def post_alert(self, text: str) -> None:
        self.client.chat_postMessage(channel=self.alert_channel_id, text=text)


