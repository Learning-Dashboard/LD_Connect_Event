from datetime import datetime
from zoneinfo import ZoneInfo


def to_madrid_local(ts: str) -> str:
    """
    Receive date in ISO-8601 then transforms it to Europe/Madrid date.
    """
    if not ts:                           # '', None…
        return ts
    # The date standard only accepts '+00:00', but taiga returns in 'Z' format
    dt_utc = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    # put date to Europe/Madrid timezone
    dt_mad_naive = dt_utc.astimezone(ZoneInfo("Europe/Madrid")).replace(tzinfo=None)
    # format
    return dt_mad_naive.isoformat(timespec="milliseconds")
