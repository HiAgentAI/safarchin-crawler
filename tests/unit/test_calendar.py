import pytest
from app.utils.calendar import to_jalali, to_gregorian, normalize_date_pair

def test_gregorian_to_jalali():
    # 2024-03-20 is 1403-01-01 (Nowruz)
    assert to_jalali("2024-03-20") == "1403-01-01"

def test_jalali_to_gregorian():
    # 1403-01-01 is 2024-03-20
    assert to_gregorian("1403-01-01") == "2024-03-20"

def test_normalize_date_pair():
    greg, jal = normalize_date_pair("2024-10-15")
    assert greg == "2024-10-15"
    assert jal == "1403-07-24"

    greg2, jal2 = normalize_date_pair("1403-07-24")
    assert greg2 == "2024-10-15"
    assert jal2 == "1403-07-24"
