import json
import datetime
import os

from db import init_db, job_exists, save_job
from slack_notifier import post_job_to_slack
from filters import is_relevant_role, get_seniority_bucket, is_us_location
from sources import (
    fetch_greenhouse_jobs,
    fetch_lever_jobs,
    fetch_smartrecruiters_jobs,
    fetch_icims_jobs,
    fetch_workday_jobs,
    fetch_oracle_jobs,
    fetch_apple_jobs,
    fetch_qualcomm_jobs,
)


STATE_FILE = "bot_state.json"


def log(msg):
    with open("run_log.txt", "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now()} | {msg}\n")


def load_companies():
    with open("companies.json", "r", encoding="utf-8") as f:
        return json.load(f)


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"last_new_job_time": None}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_new_job_time": None}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def hours_since(timestamp_str):
    if not timestamp_str:
        return None

    last_time = datetime.datetime.fromisoformat(timestamp_str)
    now = datetime.datetime.now()
    delta = now - last_time
    return delta.total_seconds() / 3600.0


def make_key(job):
    company = job["company"].strip().lower()
    title = job["title"].strip().lower()
    location = job["location"].strip().lower()
    url = job["url"].strip().lower()
    return f"{company}|{title}|{location}|{url}"


def fetch_jobs_for_company(company_record):
    source_type = company_record["source_type"]
    token = company_record["token"]
    company_name = company_record["company"]

    if source_type == "greenhouse":
        return fetch_greenhouse_jobs(token, company_name)

    if source_type == "lever":
        return fetch_lever_jobs(token, company_name)

    if source_type == "smartrecruiters":
        return fetch_smartrecruiters_jobs(token, company_name)
    
    if source_type == "icims":
        return fetch_icims_jobs(token, company_name)

    if source_type == "workday":
        return fetch_workday_jobs(token, company_name)
    
    if source_type == "oracle":
        return fetch_oracle_jobs(token, company_name)

    if source_type == "applejobs":
        return fetch_apple_jobs(token, company_name)

    if source_type == "qualcomm":
        return fetch_qualcomm_jobs(token, company_name) 

    raise ValueError(f"Unsupported source_type: {source_type}")


KEYWORDS = [
    "verification",
    "rtl",
    "asic",
    "soc",
    "embedded",
    "riscv",
    "cpu",
    "emulation",
    "formal"
]


def is_relevant_title_fast(title):
    t = title.lower()
    return any(k in t for k in KEYWORDS)


def main():
    log("=== RUN STARTED ===")

    init_db()
    companies = load_companies()
    state = load_state()

    seen_runtime = set()

    total_fetched = 0
    total_matched = 0
    total_posted = 0
    any_new_jobs = False

    for company_record in companies:
        company_name = company_record["company"]

        try:
            jobs = fetch_jobs_for_company(company_record)
            print(f"{company_name}: {len(jobs)} jobs fetched")
            log(f"{company_name}: fetched={len(jobs)}")
            total_fetched += len(jobs)

            for job in jobs:
                title_lower = job["title"].lower()

                # Fast title filter
                if not is_relevant_title_fast(job["title"]):
                    continue

                # Block weak associate noise unless clearly technical
                if "associate" in title_lower and not any(
                    x in title_lower
                    for x in ["verification", "rtl", "asic", "embedded", "hardware", "soc", "cpu", "formal"]
                ):
                    continue

                role_ok = is_relevant_role(job["title"], job.get("description", ""))
                seniority = get_seniority_bucket(job["title"], job.get("description", ""))
                us_ok = is_us_location(job["location"])

                source_type = job.get("source", "")

                if source_type in ["smartrecruiters", "workday", "applejobs", "qualcomm"]:
                    passes_location = us_ok or job["location"] == ""
                else:
                    passes_location = us_ok

                if not (role_ok and passes_location):
                    continue

                total_matched += 1

                key = make_key(job)
                if job_exists(key):
                    continue

                runtime_key = (
                    job["company"].strip().lower(),
                    job["title"].strip().lower(),
                    job["location"].strip().lower()
                )

                if runtime_key in seen_runtime:
                    continue

                seen_runtime.add(runtime_key)

                if seniority in ["intern", "entry_level"]:
                    print("MATCHED FRESHER:", job["title"], "|", seniority, "|", job["location"])
                    post_job_to_slack(job, channel_type="fresher")
                    log(f"POSTED FRESHER | {job['company']} | {job['title']} | {job['location']}")
                else:
                    print("MATCHED ALL:", job["title"], "|", seniority, "|", job["location"])
                    post_job_to_slack(job, channel_type="all")
                    log(f"POSTED ALL | {job['company']} | {job['title']} | {job['location']}")

                save_job(
                    job["company"],
                    job["title"],
                    job["location"],
                    job["url"],
                    key,
                    job["source"]
                )

                total_posted += 1
                any_new_jobs = True
                print("Posted:", job["title"])

        except Exception as e:
            print(f"{company_name} failed: {e}")
            log(f"ERROR | {company_name} | {e}")

    print("\nRun summary")
    print("-----------")
    print("Total fetched:", total_fetched)
    print("Total matched:", total_matched)
    print("Total posted:", total_posted)

    if total_posted == 0:
        print("No new jobs in this run.")

    if any_new_jobs:
        state["last_new_job_time"] = datetime.datetime.now().isoformat()
        save_state(state)
    else:
        hrs = hours_since(state.get("last_new_job_time"))

        if hrs is not None and hrs >= 6:
            status_job = {
                "company": "SYSTEM",
                "title": "No new relevant jobs found in the last 6 hours",
                "location": "",
                "url": ""
            }

            post_job_to_slack(status_job, channel_type="all")
            post_job_to_slack(status_job, channel_type="fresher")
            log("STATUS | No new relevant jobs found in the last 6 hours")

            # reset timer so it does not notify every hour after threshold
            state["last_new_job_time"] = datetime.datetime.now().isoformat()
            save_state(state)

    log(f"Run finished | fetched={total_fetched} matched={total_matched} posted={total_posted}")


if __name__ == "__main__":
    main()