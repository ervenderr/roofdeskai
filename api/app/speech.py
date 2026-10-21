"""Turn what a speech recogniser writes ("three oh three five five five...") into what a form expects ("303-555-...").
Runs of number words become digits; a lone "one" or "two" is left alone ("the first one", "two months")."""
import re

_DIGITS = {"zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4",
           "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9"}
_TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
          "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_NUM = "|".join([*_DIGITS, *_TEENS, *_TENS])
_RUN = re.compile(rf"\b(?:{_NUM})(?:[\s-]+(?:{_NUM}))*\b", re.I)
_EMAIL = re.compile(r"\b((?:\w+ dot )*\w+) at ((?:\w+ dot )+\w+)\b", re.I)
_STREET = re.compile(rf"\b({'|'.join(k for k in _DIGITS if k != 'oh')})(?=\s+(?!(?:on|at|in|of|to|by|the|a|an|and|is|my)\b)[a-z]+(?:\s+[a-z]+)?\s+"
                     r"(?:street|st|avenue|ave|road|rd|lane|ln|drive|dr|court|ct|way|blvd|boulevard|circle|place|pl)\b)", re.I)
PHONE_DIGITS = 10
MIN_WORDS_WITH_OH = 4  # "oh one of them" is speech, not digits


def _run_to_digits(words: list[str]) -> str:
    out, i = "", 0
    while i < len(words):
        w = words[i]
        if w in _TENS and i + 1 < len(words) and words[i + 1] in _DIGITS and words[i + 1] not in ("zero", "oh"):
            out += str(_TENS[w] + int(_DIGITS[words[i + 1]]))
            i += 2
            continue
        out += _DIGITS[w] if w in _DIGITS else str(_TEENS.get(w) or _TENS[w])
        i += 1
    return out


def _replace_run(m: re.Match) -> str:
    words = re.split(r"[\s-]+", m.group(0).lower())
    if len(words) == 1 and words[0] in _DIGITS:
        return m.group(0)
    if "oh" in words and len(words) < MIN_WORDS_WITH_OH:
        return m.group(0)
    digits = _run_to_digits(words)
    if len(digits) == PHONE_DIGITS:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return digits


def normalize(text: str) -> str:
    text = _EMAIL.sub(lambda m: f"{m.group(1).replace(' dot ', '.')}@{m.group(2).replace(' dot ', '.')}", text)
    text = _RUN.sub(_replace_run, text)
    return _STREET.sub(lambda m: _DIGITS[m.group(1).lower()], text)  # a lone "seven" before a street name
