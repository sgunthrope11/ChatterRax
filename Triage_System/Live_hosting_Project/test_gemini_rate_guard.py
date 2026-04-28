"""
Regression tests for the Gemini rate-limit guard.

Run from Live_hosting_Project/:
    python test_gemini_rate_guard.py
"""
import json
import sys
import unittest
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent))

import providers.gemini_provider as gemini_provider


CASE_MESSAGES = [
    ("Outlook", "Outlook keeps asking me to sign in every few minutes."),
    ("Outlook", "My email is stuck in the outbox and will not send."),
    ("Outlook", "The calendar invite never showed up for tomorrow's meeting."),
    ("Outlook", "Search in Outlook is missing messages I know are there."),
    ("Teams", "Teams says my microphone is not detected before a call."),
    ("Teams", "My camera is black when I join a meeting."),
    ("Teams", "Chat messages are not sending to one coworker."),
    ("Teams", "The Join button is missing from my meeting."),
    ("OneDrive", "OneDrive is stuck syncing one file all morning."),
    ("OneDrive", "OneDrive says there is a sync conflict on a spreadsheet."),
    ("OneDrive", "A shared folder is missing from File Explorer."),
    ("OneDrive", "It opens the wrong work tenant after SSO."),
    ("SharePoint", "The SharePoint library link says access denied."),
    ("SharePoint", "A file is locked for editing by me but I closed it."),
    ("SharePoint", "Version history is missing for a document."),
    ("SharePoint", "Conditional access blocked a library link."),
    ("Excel", "Excel formulas are not recalculating."),
    ("Excel", "The pivot table refresh failed."),
    ("Excel", "Excel crashes when I open this workbook."),
    ("Excel", "Autosave is disabled on a workbook in OneDrive."),
    ("Word", "Word changed the formatting after I pasted text."),
    ("Word", "Word keeps freezing when I open a policy document."),
    ("Word", "Track changes is not showing my edits."),
    ("Word", "The printer cuts off the bottom of the document."),
    ("PowerPoint", "The slide deck video is black during presenter view."),
    ("PowerPoint", "PowerPoint crashes when I start the presentation."),
    ("PowerPoint", "The corporate template fonts are missing."),
    ("PowerPoint", "Speaker notes are showing on the projector."),
    ("Windows", "BitLocker is asking for a recovery key."),
    ("Windows", "Bluetooth headphones connect but have no sound."),
    ("Windows", "The second monitor is not detected."),
    ("Windows", "The printer says driver unavailable."),
    ("Windows", "Wi-Fi is connected but Teams and Outlook are offline."),
    ("Microsoft account", "Authenticator codes are not being accepted."),
    ("Microsoft account", "I forgot my password and cannot sign in."),
    ("Microsoft account", "It says my account is locked after too many attempts."),
    ("Microsoft 365", "All Office apps say license not found."),
    ("Microsoft 365", "Several users say Microsoft 365 is down."),
    ("Microsoft 365", "Office install is stuck at 2 percent."),
    ("unknown", "The app says error 0x891 but I do not know which app."),
    ("unknown", "It just says something went wrong."),
    ("unknown", "The blue button disappeared after the update."),
    ("unknown", "I need a human to look at this urgent issue."),
]


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "service": "outlook",
                                        "intent": "sync",
                                        "needs_ticket": False,
                                        "needs_description": False,
                                        "priority": "medium",
                                        "reply": "Try sending again after restarting Outlook.",
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        }
        return json.dumps(payload).encode("utf-8")


class GeminiRateGuardTest(unittest.TestCase):
    def setUp(self):
        self._saved = {
            name: getattr(gemini_provider, name)
            for name in (
                "GEMINI_API_KEY",
                "GEMINI_BYPASS_PROXY",
                "GEMINI_TPM_LIMIT",
                "GEMINI_RPM_LIMIT",
                "GEMINI_MIN_REQUEST_INTERVAL_SECONDS",
                "GEMINI_RATE_LIMIT_MAX_WAIT_SECONDS",
                "GEMINI_RATE_LIMIT_RETRIES",
                "GEMINI_429_COOLDOWN_SECONDS",
                "GEMINI_429_MAX_COOLDOWN_SECONDS",
                "urlopen",
            )
        }
        gemini_provider.GEMINI_API_KEY = "test-key"
        gemini_provider.GEMINI_BYPASS_PROXY = False
        gemini_provider.GEMINI_TPM_LIMIT = 250000
        gemini_provider.GEMINI_RPM_LIMIT = 0
        gemini_provider.GEMINI_MIN_REQUEST_INTERVAL_SECONDS = 0
        gemini_provider.GEMINI_RATE_LIMIT_MAX_WAIT_SECONDS = 0
        gemini_provider.GEMINI_RATE_LIMIT_RETRIES = 0
        gemini_provider.GEMINI_429_COOLDOWN_SECONDS = 8
        gemini_provider.GEMINI_429_MAX_COOLDOWN_SECONDS = 300
        self._clear_limiter()

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(gemini_provider, name, value)
        self._clear_limiter()

    def _clear_limiter(self):
        with gemini_provider._RATE_LIMIT_LOCK:
            gemini_provider._RATE_LIMIT_USAGE.clear()
            gemini_provider._REQUEST_TIMESTAMPS.clear()
            gemini_provider._NEXT_REQUEST_AT = 0.0
            gemini_provider._PAUSE_UNTIL = 0.0
            gemini_provider._CONSECUTIVE_429S = 0

    def test_43_prompt_options_stay_under_250k_tpm(self):
        estimates = []
        for service, message in CASE_MESSAGES:
            prompt = gemini_provider._build_prompt(message, service_hint=service)
            estimates.append(gemini_provider._estimated_request_tokens(prompt))

        total_tokens = sum(estimates)
        print(
            f"\n43-case estimated token budget: {total_tokens} "
            f"(avg {total_tokens // len(estimates)}, max {max(estimates)})"
        )
        self.assertEqual(len(estimates), 43)
        self.assertLess(total_tokens, gemini_provider.GEMINI_TPM_LIMIT)

    def test_guard_skips_call_when_tpm_wait_is_too_long(self):
        gemini_provider.GEMINI_TPM_LIMIT = 2000
        first_wait, first_error = gemini_provider._reserve_gemini_capacity(1500)
        second_wait, second_error = gemini_provider._reserve_gemini_capacity(1500)

        self.assertEqual(first_wait, 0)
        self.assertIsNone(first_error)
        self.assertGreater(second_wait, 0)
        self.assertEqual(second_error, "rate_limited_wait_too_long")

    def test_guard_skips_call_when_rpm_wait_is_too_long(self):
        gemini_provider.GEMINI_RPM_LIMIT = 2
        first_wait, first_error = gemini_provider._reserve_gemini_capacity(10)
        second_wait, second_error = gemini_provider._reserve_gemini_capacity(10)
        third_wait, third_error = gemini_provider._reserve_gemini_capacity(10)

        self.assertEqual(first_wait, 0)
        self.assertIsNone(first_error)
        self.assertEqual(second_wait, 0)
        self.assertIsNone(second_error)
        self.assertGreater(third_wait, 0)
        self.assertEqual(third_error, "rate_limited_wait_too_long")

    def test_429_sets_cooldown_and_returns_rate_limited_error(self):
        def raise_429(*_args, **_kwargs):
            raise HTTPError(
                url="https://example.invalid",
                code=429,
                msg="Too Many Requests",
                hdrs={"Retry-After": "2"},
                fp=None,
            )

        gemini_provider.urlopen = raise_429
        _text, error = gemini_provider._call_gemini_api("hello", estimated_tokens=10)
        status = gemini_provider.get_gemini_rate_limit_status()

        self.assertEqual(error, "rate_limited_429")
        self.assertGreater(status["cooldown_remaining_seconds"], 0)
        self.assertEqual(status["consecutive_429s"], 1)

    def test_429_body_retry_info_and_daily_quota_label(self):
        body = json.dumps(
            {
                "error": {
                    "code": 429,
                    "status": "RESOURCE_EXHAUSTED",
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                            "violations": [
                                {
                                    "quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
                                    "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                                    "quotaValue": "20",
                                }
                            ],
                        },
                        {
                            "@type": "type.googleapis.com/google.rpc.RetryInfo",
                            "retryDelay": "41s",
                        },
                    ],
                }
            }
        )

        self.assertEqual(gemini_provider._parse_retry_delay_from_error_body(body), 41)
        self.assertEqual(gemini_provider._quota_error_label(body), "quota_exhausted_daily")

    def test_consecutive_429s_increase_cooldown(self):
        gemini_provider._record_rate_limit_429()
        first_status = gemini_provider.get_gemini_rate_limit_status()
        gemini_provider._record_rate_limit_429()
        second_status = gemini_provider.get_gemini_rate_limit_status()

        self.assertEqual(second_status["consecutive_429s"], 2)
        self.assertGreater(
            second_status["cooldown_remaining_seconds"],
            first_status["cooldown_remaining_seconds"],
        )

    def test_successful_call_still_returns_text(self):
        gemini_provider.urlopen = lambda *_args, **_kwargs: _FakeResponse()
        text, error = gemini_provider._call_gemini_api("hello", estimated_tokens=10)

        self.assertIsNone(error)
        self.assertIn("Try sending again", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
