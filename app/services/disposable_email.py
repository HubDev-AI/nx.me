"""Disposable email domain detection.

Maintains a blocklist of well-known throwaway email providers.
Rejected at registration to prevent trial credit abuse.
"""

_DISPOSABLE_DOMAINS: frozenset[str] = frozenset(
    {
        "mailinator.com",
        "guerrillamail.com",
        "guerrillamail.info",
        "guerrillamail.net",
        "guerrillamail.org",
        "guerrillamail.de",
        "guerrillamailblock.com",
        "spam4.me",
        "yopmail.com",
        "yopmail.fr",
        "cool.fr.nf",
        "jetable.fr.nf",
        "nospam.ze.tc",
        "nomail.xl.cx",
        "mega.zik.dj",
        "speed.1s.fr",
        "courriel.fr.nf",
        "moncourrier.fr.nf",
        "monemail.fr.nf",
        "monmail.fr.nf",
        "trashmail.com",
        "trashmail.at",
        "trashmail.io",
        "trashmail.me",
        "trashmail.net",
        "dispostable.com",
        "throwam.com",
        "throwaway.email",
        "tempmail.com",
        "temp-mail.org",
        "fakeinbox.com",
        "sharklasers.com",
        "guerrillamail.biz",
        "grr.la",
        "spam.la",
        "10minutemail.com",
        "10minutemail.net",
        "10minutemail.org",
        "10minemail.com",
        "minutemailbox.com",
        "discard.email",
        "mailnesia.com",
        "mailnull.com",
        "spamgourmet.com",
        "spamgourmet.net",
        "spamgourmet.org",
        "bccto.me",
        "chacuo.net",
        "dropmail.me",
        "filzmail.com",
        "maildrop.cc",
        "mailnew.com",
        "mailscrap.com",
        "spamtrap.ro",
        "mt2009.com",
        "mt2014.com",
        "mt2015.com",
    }
)


def is_disposable_email(email: str) -> bool:
    """Return True if the email's domain is a known disposable provider."""
    parts = email.lower().rsplit("@", maxsplit=1)
    if len(parts) != 2:
        return False
    domain = parts[1].strip()
    return domain in _DISPOSABLE_DOMAINS
