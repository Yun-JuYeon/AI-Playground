def get_last_char(word: str) -> str:
    """Get the last character of a Korean word, handling 두음법칙"""
    if not word:
        return ""

    last_char = word[-1]

    # 두음법칙 처리: ㄴ->ㅇ, ㄹ->ㅇ/ㄴ
    # 랴,려,례,료,류,리 -> 야,여,예,요,유,이
    # 라,래,로,뢰,루,르 -> 나,내,노,뇌,누,느
    # 녀,뇨,뉴,니 -> 여,요,유,이
    # 나,너 등은 그대로

    dueum_map = {
        # ㄹ -> ㅇ (ㅣ,ㅑ,ㅕ,ㅛ,ㅠ 모음 앞)
        '랴': '야', '려': '여', '례': '예', '료': '요', '류': '유', '리': '이',
        '량': '양', '력': '역', '련': '연', '렬': '열', '렴': '염', '렵': '엽',
        '령': '영', '륭': '융', '률': '율', '림': '임', '립': '입',
        # ㄹ -> ㄴ (ㅏ,ㅐ,ㅗ,ㅚ,ㅜ,ㅡ 모음 앞)
        '라': '나', '래': '내', '로': '노', '뢰': '뇌', '루': '누', '르': '느',
        '락': '낙', '란': '난', '랄': '날', '람': '남', '랍': '납', '랑': '낭',
        '론': '논', '롱': '농', '뇨': '요',
        # ㄴ -> ㅇ (ㅣ,ㅑ,ㅕ,ㅛ,ㅠ 모음 앞)
        '녀': '여', '뇨': '요', '뉴': '유', '니': '이',
        '녁': '역', '년': '연', '념': '염', '녕': '영',
    }

    return dueum_map.get(last_char, last_char)


def is_valid_korean_format(word: str) -> bool:
    """Check if a word contains only Korean characters and is at least 2 chars"""
    if not word or len(word) < 2:
        return False
    for char in word:
        if not ('가' <= char <= '힣'):
            return False
    return True


# 기존 함수 호환성 유지
def is_valid_korean_word(word: str) -> bool:
    """Check if a word contains only Korean characters and is at least 2 chars"""
    return is_valid_korean_format(word)
