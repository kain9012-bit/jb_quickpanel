"""Parameters shared by desktop HWP and the drafting editor."""

SCRIPT_MODES = {"super": (1, 0), "sub": (0, 1), "normal": (0, 0)}
COMPOSE_SHAPES = {"circle": 1, "square": 3, "triangle": 5, "diamond": 8}


def script_parameters(mode):
    if not isinstance(mode, str) or mode not in SCRIPT_MODES:
        raise ValueError("첨자 설정을 확인하세요.")
    superscript, subscript = SCRIPT_MODES[mode]
    return {"SuperScript": superscript, "SubScript": subscript}


def compose_parameters(value, shape):
    if (not isinstance(value, str) or not value.strip() or len(value) > 9
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ValueError("겹칠 글자는 1~9자로 입력하세요.")
    if not isinstance(shape, str) or shape not in COMPOSE_SHAPES:
        raise ValueError("글자 겹치기 모양을 선택하세요.")
    return {
        "Chars": value,
        "CircleType": COMPOSE_SHAPES[shape],
        "CharSize": -3 if len(value) > 1 else 0,
        "CheckCompose": 0,
        "TextDir": 0,
    }


def square_character_groups():
    return [
        {"id": f"builtin:square:{key}", "title": title, "chars": chars,
         "user_item": False, "presentation": "square"}
        for key, title, chars in (
            ("numbers", "네모문자-숫자", [str(number) for number in range(1, 21)]),
        )
    ]
