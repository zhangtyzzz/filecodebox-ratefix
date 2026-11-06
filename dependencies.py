import time
from collections import OrderedDict, deque
from ipaddress import ip_address, ip_network
from typing import Deque, Iterable
from fastapi import HTTPException, Request

from core.settings import settings


def _iter_trusted_proxies() -> Iterable[str]:
    trusted_proxies = getattr(settings, "trusted_proxies", [])
    if isinstance(trusted_proxies, str):
        trusted_proxies = [item.strip() for item in trusted_proxies.split(",")]
    return [item for item in trusted_proxies if item]


def _is_trusted_proxy(host: str) -> bool:
    try:
        remote_addr = ip_address(host)
    except ValueError:
        return False

    for proxy in _iter_trusted_proxies():
        try:
            if remote_addr in ip_network(proxy, strict=False):
                return True
        except ValueError:
            continue
    return False


def _get_forwarded_for_ip(header_value: str, fallback_ip: str) -> str:
    forwarded_chain = [
        item.strip() for item in header_value.split(",") if item.strip()
    ]
    if not forwarded_chain:
        return fallback_ip

    for candidate in reversed(forwarded_chain):
        try:
            ip_address(candidate)
        except ValueError:
            return fallback_ip
        if not _is_trusted_proxy(candidate):
            return candidate
    return forwarded_chain[0]


def get_client_ip(request: Request) -> str:
    client_host = request.client.host if request.client else "unknown"
    if not _is_trusted_proxy(client_host):
        return client_host

    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return _get_forwarded_for_ip(forwarded_for, client_host)

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        try:
            ip_address(real_ip)
        except ValueError:
            return client_host
        return real_ip

    return client_host


# Bounded sliding window: preserve upstream capacity control and expire each event.
DEFAULT_MAX_TRACKED_IPS = 10_000


class IPRateLimit:
    def __init__(self, count: int, minutes: int, max_ips: int = DEFAULT_MAX_TRACKED_IPS):
        self.ips: OrderedDict[str, Deque[float]] = OrderedDict()
        self.count = count
        self.minutes = minutes
        self.max_ips = max(1, max_ips)

    def _prune(self, ip: str, now: float):
        events = self.ips.get(ip)
        cutoff = now - float(self.minutes) * 60
        while events and events[0] <= cutoff:
            events.popleft()
        if not events:
            self.ips.pop(ip, None)
            return None
        return events

    def check_ip(self, ip: str) -> bool:
        events = self._prune(ip, time.monotonic())
        return events is None or len(events) < self.count

    def add_ip(self, ip: str) -> int:
        now = time.monotonic()
        events = self._prune(ip, now)
        if events is None:
            events = deque()
            self.ips[ip] = events
        else:
            self.ips.move_to_end(ip)
        events.append(now)
        while len(self.ips) > self.max_ips:
            self.ips.popitem(last=False)
        return len(events)

    async def remove_expired_ip(self) -> None:
        now = time.monotonic()
        for ip in list(self.ips):
            self._prune(ip, now)

    def __call__(self, request: Request) -> str:
        ip = get_client_ip(request)
        if not self.check_ip(ip):
            raise HTTPException(status_code=423, detail="请求次数过多，请稍后再试")
        return ip
