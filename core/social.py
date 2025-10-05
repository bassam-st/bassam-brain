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

# بحث “تعليقات/نقاشات” عبر جوجل باستعلامات مفلترة
COMMENT_QUERIES = {
    "Twitter/X (نقاشات)":  "site:twitter.com {q}",
    "Reddit (Threads)":    "site:reddit.com {q}",
    "YouTube (تعليقات/ردود)": "site:youtube.com {q}",
    "Facebook (منشورات)":  "site:facebook.com {q}",
}

def build_social_links(name: str) -> list[tuple[str,str]]:
    enc = urllib.parse.quote(name.strip())
    return [(k, v.format(q=enc)) for k, v in PLATFORMS.items()]

def build_comment_links(name: str) -> list[tuple[str,str]]:
    g = "https://www.google.com/search?q="
    links = []
    for label, pattern in COMMENT_QUERIES.items():
        q = urllib.parse.quote(pattern.format(q=name))
        links.append((label, g + q))
    return links
