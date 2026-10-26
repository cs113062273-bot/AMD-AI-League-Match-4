"""Recognize observed challenge documents, without executing their scripts."""
import re
from urllib.parse import urlsplit

from .normalize import clean


def interstitial(soup, status):
    # Keep this narrow: an article can discuss CAPTCHA or include a background
    # widget. Only the observed document signatures plus a small text shell
    # qualify; HTTP 202 or a script filename alone is not a challenge.
    if len(clean(soup.get_text(' ', strip=True))) > 500:
        return ''
    if any(clean(article.get_text(' ', strip=True)) for article in soup.find_all('article', limit=20)):
        return ''
    scripts = soup.find_all('script', src=True, limit=100)
    if status == 202 and soup.find(id='challenge-container'):
        for script in scripts:
            try:
                url = urlsplit(script['src'])
                host = (url.hostname or '').lower()
            except ValueError:
                continue
            if (host == 'token.awswaf.com' or host.endswith('.token.awswaf.com')) and url.path.endswith('/challenge.js'):
                return 'aws_waf'
    title = clean(soup.title.get_text(' ')) if soup.title else ''
    base = soup.find('base', href=True)
    if base and re.fullmatch(r'Checking your browser\s*-\s*reCAPTCHA', title, re.I):
        try:
            url = urlsplit(base['href'])
        except ValueError:
            return ''
        if (url.hostname or '').lower() in {'www.google.com', 'google.com'} and url.path.rstrip('/') == '/recaptcha/challengepage':
            return 'recaptcha'
    return ''
