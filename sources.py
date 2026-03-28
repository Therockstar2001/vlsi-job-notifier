import re
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


MAX_JOBS_PER_COMPANY = 300


def _build_session() -> requests.Session:
    session = requests.Session()

    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )

    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VLSIJobBot/2.2",
        "Accept": "application/json, text/plain, */*",
    })

    return session


SESSION = _build_session()


def _slugify_title(title: str) -> str:
    title = title.strip().lower()
    title = re.sub(r"[^a-z0-9]+", "-", title)
    title = re.sub(r"-+", "-", title).strip("-")
    return title


def _normalize_smartrecruiters_url(job: dict, company_slug: str) -> str:
    posting_url = (job.get("postingUrl") or "").strip()
    apply_url = (job.get("applyUrl") or "").strip()
    ref_url = (job.get("ref") or "").strip()

    if posting_url and "jobs.smartrecruiters.com" in posting_url:
        return posting_url

    if apply_url and "jobs.smartrecruiters.com" in apply_url:
        return apply_url

    if ref_url:
        job_id = str(job.get("id", "")).strip()
        title = (job.get("name") or "").strip()
        if job_id and title:
            return f"https://jobs.smartrecruiters.com/{company_slug}/{job_id}-{_slugify_title(title)}"

    return posting_url or apply_url or ref_url


# ---------------- GREENHOUSE ----------------
def fetch_greenhouse_jobs(board_token: str, company_name: str):
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
    response = SESSION.get(url, timeout=20)
    response.raise_for_status()

    data = response.json()
    jobs = []

    for job in data.get("jobs", []):
        title = job.get("title", "").strip()
        absolute_url = job.get("absolute_url", "").strip()

        location_obj = job.get("location", {})
        location = ""
        if isinstance(location_obj, dict):
            location = location_obj.get("name", "").strip()

        jobs.append({
            "company": company_name,
            "title": title,
            "location": location,
            "url": absolute_url,
            "description": "",
            "source": "greenhouse"
        })

    return jobs


# ---------------- LEVER ----------------
def fetch_lever_jobs(company_token: str, company_name: str):
    url = f"https://api.lever.co/v0/postings/{company_token}?mode=json"
    response = SESSION.get(url, timeout=20)
    response.raise_for_status()

    data = response.json()
    jobs = []

    for job in data:
        title = job.get("text", "").strip()
        absolute_url = job.get("hostedUrl", "").strip()

        categories = job.get("categories", {}) or {}
        location = categories.get("location", "").strip()

        description = (
            job.get("descriptionPlain", "") or
            job.get("description", "") or
            ""
        )

        jobs.append({
            "company": company_name,
            "title": title,
            "location": location,
            "url": absolute_url,
            "description": description,
            "source": "lever"
        })

    return jobs


# ---------------- SMARTRECRUITERS ----------------
def fetch_smartrecruiters_jobs(company_slug: str, company_name: str):
    jobs = []
    offset = 0
    limit = 100

    while True:
        url = f"https://api.smartrecruiters.com/v1/companies/{company_slug}/postings?limit={limit}&offset={offset}"
        response = SESSION.get(url, timeout=20)
        response.raise_for_status()

        data = response.json()
        postings = data.get("content", [])

        if not postings:
            break

        for job in postings:
            title = (job.get("name") or "").strip()
            absolute_url = _normalize_smartrecruiters_url(job, company_slug)

            location = ""
            loc = job.get("location")
            if isinstance(loc, dict):
                location = ", ".join(filter(None, [
                    loc.get("city"),
                    loc.get("region"),
                    loc.get("country")
                ]))

            description = ""
            job_description = job.get("jobDescription")
            if isinstance(job_description, dict):
                description = job_description.get("text", "") or ""

            jobs.append({
                "company": company_name,
                "title": title,
                "location": location,
                "url": absolute_url,
                "description": description,
                "source": "smartrecruiters"
            })

            if len(jobs) >= MAX_JOBS_PER_COMPANY:
                return jobs

        offset += limit

        if len(postings) < limit:
            break

    return jobs


# ---------------- WORKDAY HELPERS ----------------
def _strip_locale_prefix(path: str) -> str:
    parts = [p for p in path.strip("/").split("/") if p]
    if len(parts) >= 2 and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", parts[0]):
        return "/".join(parts[1:])
    return "/".join(parts)


def _candidate_workday_api_urls(base_url: str):
    m = re.match(r"^https://([^/]+)/(.*)$", base_url.strip())
    if not m:
        raise ValueError(f"Invalid Workday base URL: {base_url}")

    host = m.group(1)
    site_path = m.group(2).strip("/")
    tenant = host.split(".")[0]

    stripped_site_path = _strip_locale_prefix(site_path)

    candidates = [
        f"https://{host}/wday/cxs/{tenant}/{site_path}/jobs",
    ]

    if stripped_site_path != site_path:
        candidates.append(
            f"https://{host}/wday/cxs/{tenant}/{stripped_site_path}/jobs"
        )

    deduped = []
    seen = set()
    for url in candidates:
        if url not in seen:
            seen.add(url)
            deduped.append(url)

    return host, site_path, deduped


def _post_workday_json(api_url: str, base_url: str, payload: dict):
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": re.match(r"^(https://[^/]+)", base_url).group(1),
        "Referer": base_url.rstrip("/") + "/",
    }

    response = SESSION.post(api_url, json=payload, headers=headers, timeout=20)
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "").lower()
    if "json" not in content_type:
        return None

    try:
        return response.json()
    except ValueError:
        return None


# ---------------- WORKDAY ----------------
def fetch_workday_jobs(base_url: str, company_name: str):
    host, site_path, api_candidates = _candidate_workday_api_urls(base_url)

    jobs = []
    offset = 0
    limit = 20
    working_api_url = None

    payload_probe = {
        "appliedFacets": {},
        "limit": 1,
        "offset": 0,
        "searchText": ""
    }

    for candidate in api_candidates:
        try:
            data = _post_workday_json(candidate, base_url, payload_probe)
            if isinstance(data, dict) and "jobPostings" in data:
                working_api_url = candidate
                break
        except Exception:
            continue

    if not working_api_url:
        raise RuntimeError(f"No working Workday API endpoint found for {company_name}: {base_url}")

    while True:
        payload = {
            "appliedFacets": {},
            "limit": limit,
            "offset": offset,
            "searchText": ""
        }

        data = _post_workday_json(working_api_url, base_url, payload)
        if not isinstance(data, dict):
            break

        postings = data.get("jobPostings", [])
        if not postings:
            break

        for job in postings:
            title = (job.get("title") or "").strip()
            external_path = (job.get("externalPath") or "").strip()

            if external_path.startswith("/"):
                external_path = external_path[1:]

            absolute_url = f"https://{host}/{site_path}/{external_path}" if external_path else base_url

            location = (
                (job.get("locationsText") or "").strip()
                or (job.get("location") or "").strip()
            )

            bullet_fields = job.get("bulletFields") or []
            description_text = " ".join(bullet_fields) if isinstance(bullet_fields, list) else ""

            jobs.append({
                "company": company_name,
                "title": title,
                "location": location,
                "url": absolute_url,
                "description": description_text,
                "source": "workday"
            })

            if len(jobs) >= MAX_JOBS_PER_COMPANY:
                return jobs

        offset += limit

        if len(postings) < limit:
            break

    return jobs


# ---------------- APPLE JOBS ----------------
def fetch_apple_jobs(search_url: str, company_name: str):
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

    jobs = []
    seen = set()

    parsed = urlparse(search_url)
    base_query = parse_qs(parsed.query)

    for page_num in range(1, 31):
        query = dict(base_query)
        query["page"] = [str(page_num)]

        paged_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query, doseq=True),
            parsed.fragment
        ))

        response = SESSION.get(paged_url, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")
        cards = soup.find_all("h3")

        page_count = 0

        for h3 in cards:
            a = h3.find("a", href=True)
            if not a:
                continue

            title = a.get_text(" ", strip=True)
            href = a["href"].strip()

            if not title:
                continue

            if href.startswith("/"):
                href = f"https://jobs.apple.com{href}"

            location = ""
            parent_text = h3.parent.get_text(" ", strip=True) if h3.parent else ""
            loc_match = re.search(r"Location\s*([A-Za-z0-9 ,\-/]+)", parent_text)
            if loc_match:
                location = loc_match.group(1).strip()

            key = (title.lower(), href.lower())
            if key in seen:
                continue

            seen.add(key)
            page_count += 1

            jobs.append({
                "company": company_name,
                "title": title,
                "location": location,
                "url": href,
                "description": "",
                "source": "applejobs"
            })

            if len(jobs) >= MAX_JOBS_PER_COMPANY:
                return jobs

        if page_count == 0:
            break

    return jobs


# ---------------- QUALCOMM (Eightfold/Qualcomm Careers) ----------------
def fetch_qualcomm_jobs(base_url: str, company_name: str):
    """
    Best-effort Qualcomm careers scraper.
    """
    jobs = []
    seen = set()

    seed_urls = [
        base_url,
        f"{base_url}&seniority=Entry&seniority=Intern",
        f"{base_url}&sort_by=relevance",
        f"{base_url}&location=any",
    ]

    pid_pattern = re.compile(
        r"https://careers\.qualcomm\.com/careers\?[^\"'\s>]*pid=(\d+)[^\"'\s>]*",
        re.IGNORECASE
    )

    for seed in seed_urls:
        try:
            response = SESSION.get(seed, timeout=20)
            response.raise_for_status()
            html = response.text

            print("QUALCOMM DEBUG | seed:", seed)
            print("QUALCOMM DEBUG | html length:", len(html))

        except Exception as e:
            print("QUALCOMM DEBUG | seed failed:", seed, "|", e)
            continue

        pid_links = pid_pattern.findall(html)
        print("QUALCOMM DEBUG | pid links found:", len(pid_links))

        candidate_urls = []
        for pid in pid_links:
            candidate_urls.append(
                f"https://careers.qualcomm.com/careers?domain=qualcomm.com&pid={pid}"
            )

        candidate_urls = list(dict.fromkeys(candidate_urls))

        for job_url in candidate_urls:
            if job_url in seen:
                continue
            seen.add(job_url)

            try:
                r = SESSION.get(job_url, timeout=20)
                r.raise_for_status()
                page_html = r.text
            except Exception:
                continue

            soup = BeautifulSoup(page_html, "lxml")

            title = ""
            if soup.title and soup.title.string:
                title = soup.title.string.strip()

            if "|" in title:
                title = title.split("|")[0].strip()
            if title.lower().startswith("qualcomm careers"):
                title = ""

            if not title:
                for tag_name in ["h1", "h2", "h3"]:
                    tag = soup.find(tag_name)
                    if tag and tag.get_text(" ", strip=True):
                        title = tag.get_text(" ", strip=True)
                        break

            if not title:
                continue

            page_text = soup.get_text(" ", strip=True)

            location = ""
            loc_match = re.search(r"Location[:\s]+([A-Za-z0-9,\- /]+)", page_text)
            if loc_match:
                location = loc_match.group(1).strip()

            jobs.append({
                "company": company_name,
                "title": title,
                "location": location,
                "url": job_url,
                "description": page_text[:4000],
                "source": "qualcomm"
            })

            if len(jobs) >= MAX_JOBS_PER_COMPANY:
                print("QUALCOMM DEBUG | final jobs:", len(jobs))
                return jobs

    print("QUALCOMM DEBUG | final jobs:", len(jobs))
    return jobs