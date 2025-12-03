def get_last_char(word: str) -> str:
    """Get the last character of a Korean word"""
    if not word:
        return ""
    return word[-1]


def is_valid_korean_word(word: str) -> bool:
    """Check if a word contains only Korean characters and is at least 2 chars"""
    if not word or len(word) < 2:
        return False
    for char in word:
        if not ('가' <= char <= '힣'):
            return False
    return True
