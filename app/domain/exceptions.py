class SentinelNotFoundError(Exception):
    """A requested resource does not exist.

    Mapped to a 404 by the app-level handler in `app.main`, which surfaces the
    message passed here - so raise it with one: `SentinelNotFoundError(f"Device {id}")`.
    """
