from datetime import datetime, date
import re

try:
    import jdatetime
    HAS_JDATETIME = True
except ImportError:
    HAS_JDATETIME = False

def is_jalali_year(year: int) -> bool:
    return 1300 <= year <= 1500

def _gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1]
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd

def _jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    jy += 1595
    days = -355668 + (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + jd + ((jm - 1) * 31 if jm < 7 else ((jm - 7) * 30) + 186)
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    sal_a = [0, 31, 29 if ((gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 13 and gd > sal_a[gm]:
        gd -= sal_a[gm]
        gm += 1
    return gy, gm, gd

def to_jalali(date_input: str | date) -> str:
    """
    Convert a Gregorian date (YYYY-MM-DD) or date object to Jalali (YYYY-MM-DD).
    """
    if isinstance(date_input, str):
        parts = [int(p) for p in re.split(r"[-/]", date_input.strip())]
        if is_jalali_year(parts[0]):
            return f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"
        gy, gm, gd = parts[0], parts[1], parts[2]
    else:
        gy, gm, gd = date_input.year, date_input.month, date_input.day

    if HAS_JDATETIME:
        j_date = jdatetime.date.fromgregorian(date=date(gy, gm, gd))
        return f"{j_date.year:04d}-{j_date.month:02d}-{j_date.day:02d}"
    else:
        jy, jm, jd = _gregorian_to_jalali(gy, gm, gd)
        return f"{jy:04d}-{jm:02d}-{jd:02d}"

def to_gregorian(date_input: str) -> str:
    """
    Convert a Jalali date (YYYY-MM-DD) to Gregorian (YYYY-MM-DD).
    If already Gregorian, returns formatted string.
    """
    parts = [int(p) for p in re.split(r"[-/]", date_input.strip())]
    if not is_jalali_year(parts[0]):
        return f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"

    if HAS_JDATETIME:
        j_date = jdatetime.date(parts[0], parts[1], parts[2])
        g_date = j_date.togregorian()
        return f"{g_date.year:04d}-{g_date.month:02d}-{g_date.day:02d}"
    else:
        gy, gm, gd = _jalali_to_gregorian(parts[0], parts[1], parts[2])
        return f"{gy:04d}-{gm:02d}-{gd:02d}"

def normalize_date_pair(date_input: str) -> tuple[str, str]:
    """
    Given any date string (Jalali or Gregorian), returns (gregorian_str, jalali_str).
    """
    parts = [int(p) for p in re.split(r"[-/]", date_input.strip())]
    if is_jalali_year(parts[0]):
        jalali = f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"
        gregorian = to_gregorian(jalali)
    else:
        gregorian = f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"
        jalali = to_jalali(gregorian)
    return gregorian, jalali
