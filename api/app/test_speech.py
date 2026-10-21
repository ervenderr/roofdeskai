import pytest

from .speech import normalize


@pytest.mark.parametrize("spoken,written", [
    ("my number is three oh three five five five zero one four two", "my number is 303-555-0142"),
    ("its at one twenty three maple street denver", "its at 123 maple street denver"),
    ("forty eight elm avenue", "48 elm avenue"),
    ("fourteen oak street no sorry forty one oak street", "14 oak street no sorry 41 oak street"),
    ("three oh three five five five twenty one forty two", "303-555-2142"),
    ("built in nineteen ninety five", "built in 1995"),
    ("seven two zero five five five zero one one one", "720-555-0111"),
    ("i own it seven aspen way denver", "i own it 7 aspen way denver"),
    ("nine birch lane lakewood", "9 birch lane lakewood"),
    ("kim dot lee at example dot com", "kim.lee@example.com"),
    ("my email is priya at example dot com", "my email is priya@example.com"),
])
def test_spoken_numbers_and_emails_become_text(spoken, written):
    assert normalize(spoken) == written


@pytest.mark.parametrize("plain", [
    "the first one", "the second one no wait the third one", "oh i see", "i have one question",
    "within two months", "one more thing", "the one on main street", "oh one of them", "meet me at noon", "look at this", "303-555-0142 and 123 Maple St",
    "Hi! I need a roof repair.", "",
])
def test_ordinary_text_is_left_alone(plain):
    assert normalize(plain) == plain
