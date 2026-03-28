import os
import requests
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_FRESHER = os.getenv("SLACK_WEBHOOK_FRESHER")
WEBHOOK_ALL = os.getenv("SLACK_WEBHOOK_ALL")


def post_job_to_slack(job, channel_type):
    if channel_type == "fresher":
        webhook = WEBHOOK_FRESHER
    elif channel_type == "all":
        webhook = WEBHOOK_ALL
    else:
        raise ValueError(f"Unsupported channel_type: {channel_type}")

    if not webhook:
        raise ValueError(f"Missing webhook for channel: {channel_type}")

    payload = {
        "text": (
            f"*{job['title']}*\n"
            f"Company: {job['company']}\n"
            f"Location: {job['location']}\n"
            f"{job['url']}"
        )
    }

    response = requests.post(webhook, json=payload, timeout=20)

    if response.status_code != 200:
        raise RuntimeError(
            f"Slack webhook failed for {channel_type}: "
            f"{response.status_code} {response.text}"
        )