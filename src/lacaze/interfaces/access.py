"""Optional access code for a hosted demo, so strangers cannot spend the API key."""

import base64
import binascii
import secrets

from starlette.types import ASGIApp, Receive, Scope, Send

OPEN_PATHS = frozenset({"/health"})  # the host's health check carries no credentials


class AccessCodeMiddleware:
    """HTTP Basic auth: any user name, the access code as password. The browser asks once."""

    def __init__(self, app: ASGIApp, code: str):
        self.app = app
        self.code = code.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in OPEN_PATHS or self._allowed(scope):
            await self.app(scope, receive, send)
            return
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"www-authenticate", b'Basic realm="LACAZE Advisor", charset="UTF-8"'),
                    (b"content-type", b"text/plain; charset=utf-8"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b"Access code required."})

    def _allowed(self, scope: Scope) -> bool:
        header = dict(scope["headers"]).get(b"authorization", b"")
        scheme, _, encoded = header.partition(b" ")
        if scheme.lower() != b"basic":
            return False
        try:
            _, _, password = base64.b64decode(encoded, validate=True).partition(b":")
        except (binascii.Error, ValueError):
            return False
        return secrets.compare_digest(password, self.code)
