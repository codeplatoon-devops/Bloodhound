from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import boto3


@dataclass(frozen=True)
class AwsClients:
    session: boto3.Session

    def client(self, service: str, region: Optional[str] = None):
        if region:
            return self.session.client(service, region_name=region)
        return self.session.client(service)


def create_session(profile: Optional[str] = None, region: Optional[str] = None) -> boto3.Session:
    # In Lambda, profile should be None and the execution role creds will be used.
    if profile:
        return boto3.Session(profile_name=profile, region_name=region)
    return boto3.Session(region_name=region)


def create_clients(profile: Optional[str] = None, region: Optional[str] = None) -> AwsClients:
    return AwsClients(session=create_session(profile=profile, region=region))


