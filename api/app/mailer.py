"""Email transport. Dev sends to Mailpit; production swaps this one function for Resend (see docs/deploy.md)."""
import httpx

from .config import settings


class MailError(Exception):
    pass


def send(to: str, subject: str, body: str) -> None:
    try:
        r = httpx.post(f"{settings.mailpit_url}/api/v1/send", timeout=10, json={
            "From": {"Email": settings.sender_email, "Name": settings.sender_name},
            "To": [{"Email": to}], "Subject": subject, "Text": body,
            "Headers": {"List-Unsubscribe": f"<mailto:{settings.sender_email}?subject=unsubscribe>"},
        })
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise MailError(type(e).__name__) from e
