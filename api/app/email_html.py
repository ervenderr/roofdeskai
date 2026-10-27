"""HTML version of an outreach email. Inline styles only, no images or tracking; the plain-text part is always sent too."""
from html import escape
from urllib.parse import quote

from .config import settings

INK, MUTED, BG = "#1f2937", "#6b7280", "#f3f4f6"
ON_BRAND = "#14120B"  # text on the yellow brand colour: white would fail contrast


def _paragraphs(body: str) -> str:
    return "".join(f'<p style="margin:0 0 14px;font-size:15px;line-height:1.6;color:{INK}">{escape(p).replace(chr(10), "<br>")}</p>'
                   for p in body.strip().split("\n\n") if p.strip())


def _services(points: list[str], color: str) -> str:
    rows = "".join(f'<tr><td style="padding:5px 10px 5px 0;color:{ON_BRAND};font-weight:bold;vertical-align:top">&#10003;</td>'
                   f'<td style="padding:5px 0;font-size:14px;line-height:1.5;color:{INK}">{escape(pt)}</td></tr>' for pt in points)
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:18px 0;background:{BG};'
            f'border-left:4px solid {color};border-radius:6px"><tr><td style="padding:14px 18px">'
            f'<div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:{MUTED};margin-bottom:6px">What it does</div>'
            f'<table role="presentation" cellpadding="0" cellspacing="0">{rows}</table></td></tr></table>')


def _button(subject: str, color: str) -> str:
    href = f"mailto:{settings.sender_email}?subject={quote('Re: ' + subject)}&body={quote('Yes, show me how it works.')}"
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:6px 0 22px"><tr><td style="background:{color};'
            f'border-radius:6px"><a href="{escape(href)}" style="display:inline-block;padding:11px 22px;font-size:15px;'
            f'font-weight:bold;color:{ON_BRAND};text-decoration:none">Reply &ldquo;yes&rdquo; for a quick walkthrough</a></td></tr></table>')


def render(body: str, subject: str, step: int, points: list[str]) -> str:
    color = settings.brand_color
    unsub = f"mailto:{settings.sender_email}?subject=unsubscribe"
    paras = [x for x in body.strip().split("\n\n") if x.strip()]
    if step == 1 and points and len(paras) > 1:  # services before the closing question, button after it
        content = _paragraphs("\n\n".join(paras[:-1])) + _services(points, color) + _paragraphs(paras[-1]) + _button(subject, color)
    else:
        content = _paragraphs(body) + (_services(points, color) + _button(subject, color) if step == 1 and points else "")
    return (f'<!doctype html><html><body style="margin:0;padding:0;background:{BG}">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG};padding:24px 12px"><tr><td align="center">'
            f'<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;'
            f'border-radius:10px;overflow:hidden;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif">'
            f'<tr><td style="background:{color};padding:16px 28px;font-size:17px;font-weight:bold;color:{ON_BRAND}">{escape(settings.sender_name)}</td></tr>'
            f'<tr><td style="padding:26px 28px 8px">{content}</td></tr>'
            f'<tr><td style="padding:16px 28px 22px;border-top:1px solid #e5e7eb;font-size:12px;line-height:1.6;color:{MUTED}">'
            f'<strong>{escape(settings.sender_name)}</strong><br>{escape(settings.sender_address)}<br>'
            f'Not interested? Reply &ldquo;unsubscribe&rdquo; or <a href="{escape(unsub)}" style="color:{MUTED}">click here</a> and I won&rsquo;t contact you again.'
            f'</td></tr></table></td></tr></table></body></html>')
