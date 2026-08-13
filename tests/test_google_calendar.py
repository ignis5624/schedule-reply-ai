import unittest
from datetime import datetime

from integrations.google_calendar import (
    GoogleCalendarConfig,
    GoogleCalendarError,
    exchange_authorization_response,
    parse_freebusy_response,
)


class GoogleCalendarIntegrationTests(unittest.TestCase):
    def test_freebusy_response_keeps_only_busy_times(self) -> None:
        response = {
            "calendars": {
                "primary": {
                    "busy": [
                        {
                            "start": "2026-08-20T09:00:00+09:00",
                            "end": "2026-08-20T10:30:00+09:00",
                        },
                        {
                            "start": "2026-08-20T03:00:00Z",
                            "end": "2026-08-20T04:00:00Z",
                        },
                    ]
                }
            }
        }

        intervals = parse_freebusy_response(response, calendar_ids=("primary",))

        self.assertEqual(len(intervals), 2)
        self.assertEqual(intervals[0].start, datetime(2026, 8, 20, 9, 0))
        self.assertEqual(intervals[1].start, datetime(2026, 8, 20, 12, 0))
        self.assertTrue(all(value.source == "google_calendar" for value in intervals))

    def test_calendar_error_is_reported(self) -> None:
        response = {
            "calendars": {
                "primary": {"errors": [{"reason": "notFound"}], "busy": []}
            }
        }
        with self.assertRaises(GoogleCalendarError):
            parse_freebusy_response(response, calendar_ids=("primary",))

    def test_oauth_state_is_checked_before_token_exchange(self) -> None:
        config = GoogleCalendarConfig("id", "secret", "https://example.com/")
        with self.assertRaises(GoogleCalendarError):
            exchange_authorization_response(
                config,
                "https://example.com/?code=test&state=wrong",
                "expected",
            )


if __name__ == "__main__":
    unittest.main()
