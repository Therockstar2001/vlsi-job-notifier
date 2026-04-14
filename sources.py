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
    """
    Build a small set of likely Workday JSON endpoints.

    Supports both common patterns:
      1) https://company.wd1.myworkdayjobs.com/SiteName
      2) https://wd5.myworkdaysite.com/recruiting/tenant/SiteName
    """
    m = re.match(r"^https://([^/]+)/(.*)$", base_url.strip())
    if not m:
        raise ValueError(f"Invalid Workday base URL: {base_url}")

    host = m.group(1)
    site_path = m.group(2).strip("/")
    path_no_locale = _strip_locale_prefix(site_path)
    parts = [p for p in path_no_locale.split("/") if p]

    tenant_candidates = []

    # Standard host-based tenant
    # Example: analogdevices.wd1.myworkdayjobs.com -> analogdevices
    host_tenant = host.split(".")[0]
    if host_tenant:
        tenant_candidates.append(host_tenant)

    # recruiting/<tenant>/<site> pattern
    # Example: wd5.myworkdaysite.com/recruiting/microchiphr/External
    if len(parts) >= 3 and parts[0].lower() == "recruiting":
        tenant_candidates.insert(0, parts[1])

    # Prefer site-only path for recruiting URLs
    site_candidates = [path_no_locale]
    if len(parts) >= 3 and parts[0].lower() == "recruiting":
        site_only = "/".join(parts[2:])
        if site_only:
            site_candidates.insert(0, site_only)

    candidates = []
    for tenant in tenant_candidates:
        for candidate_site_path in site_candidates:
            candidates.append(
                f"https://{host}/wday/cxs/{tenant}/{candidate_site_path}/jobs"
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
        raise RuntimeError(
            f"No working Workday API endpoint found for {company_name}: {base_url}"
        )

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

            absolute_url = (
                f"https://{host}/{site_path}/{external_path}"
                if external_path else base_url
            )

            location = (
                (job.get("locationsText") or "").strip()
                or (job.get("location") or "").strip()
            )

            bullet_fields = job.get("bulletFields") or []
            description_text = (
                " ".join(bullet_fields) if isinstance(bullet_fields, list) else ""
            )

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
    Qualcomm careers is backed by Eightfold and does not expose the simple
    JSON endpoint we previously assumed.

    For now this function:
      1. Tries to fetch the page safely
      2. Prints useful debug info
      3. Returns an empty list instead of crashing the run

    This keeps the notifier stable until a proper Eightfold parser is added.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(base_url, headers=headers, timeout=15)
    except requests.RequestException as exc:
        print(f"Qualcomm request failed: {exc}")
        return []

    content_type = response.headers.get("Content-Type", "")
    print(f"QUALCOMM DEBUG | status: {response.status_code}")
    print(f"QUALCOMM DEBUG | content-type: {content_type}")
    print(f"QUALCOMM DEBUG | final-url: {response.url}")

    body_preview = response.text[:300].replace("\n", " ").replace("\r", " ")
    print(f"QUALCOMM DEBUG | body-preview: {body_preview}")

    # We expected JSON before, but the site is returning HTML / app shell.
    # Do not call response.json() here.
    print("QUALCOMM DEBUG | Qualcomm uses a separate Eightfold-backed careers flow. Returning 0 jobs for now.")

    return []