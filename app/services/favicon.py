from urllib.parse import urlparse


def favicon_url_for(link_url: str) -> str:
    parsed = urlparse(link_url if "://" in link_url else f"https://{link_url}")
    domain = parsed.netloc or parsed.path.split("/")[0]
    domain = domain.removeprefix("www.")
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
