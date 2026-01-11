import re
from typing import List, Set

# link options:
# @username
# t.me/username
# https://t.me/username
# https://telegram.me/username
USERNAME_RE = re.compile(r"@([a-zA-Z0-9_]{5,32})")
LINK_RE = re.compile(r"(?:https?://)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{5,32})")

def extract_channels(text: str) -> List[str]:
    found: Set[str] = set()
    for m in USERNAME_RE.finditer(text):
        found.add("@" + m.group(1))
    for m in LINK_RE.finditer(text):
        found.add("@" + m.group(1))
    return sorted(found)
