from datetime import datetime, timezone
import pytz
import re
from tzlocal import get_localzone

def convert_dates_to_utc(query_text: str = None, user_timezone: str = str(get_localzone())):
    """
    Converts local date-only filters (YYYY-MM-DD) in WIQL query to UTC datetimes,
    using start_utc for >= and end_utc for <=.
    """
    tz = pytz.timezone(user_timezone)

    # Match operator + date, e.g., ">= '2025-10-05'" or "<= '2025-10-05'"
    pattern = r"([<>]=)\s*'(\d{4}-\d{2}-\d{2})'"

    def replace_date(match):
        operator = match.group(1)
        date_str = match.group(2)
        local_date = datetime.strptime(date_str, "%Y-%m-%d")

        # Localized start and end of day
        local_start = tz.localize(datetime.combine(local_date, datetime.min.time()))
        local_end = tz.localize(datetime.combine(local_date, datetime.max.time()))

        # Convert to UTC
        start_utc = local_start.astimezone(timezone.utc)
        end_utc = local_end.astimezone(timezone.utc)

        # Choose correct UTC depending on operator
        if operator == ">=":
            utc_value = start_utc
        elif operator == "<=":
            utc_value = end_utc
        else:
            utc_value = start_utc

        return f"{operator} '{utc_value.strftime('%Y-%m-%dT%H:%M:%S.000Z')}'"
    
    return re.sub(pattern, replace_date, query_text)