import urllib.parse

PLATFORMS = {
    "Google":      "https://www.google.com/search?q={q}",
    "Twitter/X":   "https://twitter.com/search?q={q}&f=user",
    "Facebook":    "https://www.facebook.com/search/people/?q={q}",
    "Instagram":   "https://www.instagram.com/explore/search/keyword/?q={q}",
    "TikTok":      "https://www.tiktok.com/search/user?q={q}",
    "LinkedIn":    "https://www.linkedin.com/search/results/people/?keywords={q}",
    "Telegram":    "https://t.me/s/{q}",
    "Reddit":      "https://www.reddit.com/search/?q={q}",
    "YouTube":     "https://www.youtube.com/results?search_query={q}",
}

def build_social_links(name: str) -> list[tuple[str,str]]:
    enc = urllib.parse.quote(name.strip())
    return [(k, v.format(q=enc)) for k, v in PLATFORMS.items()]
