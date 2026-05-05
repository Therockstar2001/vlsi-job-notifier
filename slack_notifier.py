import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_FRESHER = os.getenv("SLACK_WEBHOOK_FRESHER")
WEBHOOK_ALL = os.getenv("SLACK_WEBHOOK_ALL")


def _get_webhook(channel_type: str) -> str:
    if channel_type == "fresher":
        webhook = WEBHOOK_FRESHER
    elif channel_type == "all":
        webhook = WEBHOOK_ALL
    else:
        raise ValueError(f"Unsupported channel_type: {channel_type}")

    if not webhook:
        raise ValueError(f"Missing webhook for channel: {channel_type}")

    return webhook


def _build_payload(job: dict) -> dict:
    return {
        "text": (
            f"*{job['title']}*\n"
            f"Company: {job['company']}\n"
            f"Location: {job['location']}\n"
            f"{job['url']}"
        )
    }


def _post_with_retries(webhook: str, payload: dict, retries: int = 3) -> None:
    last_exception = None

    for attempt in range(1, retries + 1):
        try:
            response = requests.post(webhook, json=payload, timeout=10)

            if response.status_code == 200:
                return

            # Retry on transient Slack/server errors
            if response.status_code in (429, 500, 502, 503, 504):
                print(
                    f"Slack post attempt {attempt}/{retries} failed with "
                    f"status {response.status_code}: {response.text}"
                )
            else:
                raise RuntimeError(
                    f"Slack webhook failed: {response.status_code} {response.text}"
                )

        except requests.exceptions.RequestException as exc:
            last_exception = exc
            print(f"Slack post attempt {attempt}/{retries} exception: {exc}")

        if attempt < retries:
            backoff_seconds = 2 * attempt
            time.sleep(backoff_seconds)

    if last_exception is not None:
        raise RuntimeError(f"Slack webhook failed after {retries} retries: {last_exception}")

    raise RuntimeError(f"Slack webhook failed after {retries} retries.")


def post_job_to_slack(job, channel_type):
    webhook = _get_webhook(channel_type)
    payload = _build_payload(job)
    _post_with_retries(webhook, payload, retries=3)

def post_status_to_slack(message):
    webhook = WEBHOOK_ALL

    if not webhook:
        raise ValueError("Missing SLACK_WEBHOOK_ALL for status message")

    payload = {
        "text": message
    }

    response = requests.post(webhook, json=payload, timeout=20)

    if response.status_code != 200:
        raise RuntimeError(
            f"Slack status message failed: {response.status_code} {response.text}"
        )