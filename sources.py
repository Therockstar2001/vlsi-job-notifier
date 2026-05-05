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

# ---------------- ICIMS ----------------
def _normalize_icims_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _build_icims_search_urls(base_url: str):
    """
    iCIMS usually exposes job listings from one of these entry pages:
      - /jobs/search
      - /jobs/intro
      - /jobs
    We probe the search page first, then fall back.
    """
    base = _normalize_icims_base_url(base_url)

    candidates = []
    if base.endswith("/jobs/intro"):
        root = base[:-len("/intro")]
        candidates.append(root + "/search")
        candidates.append(base)
        candidates.append(root)
    elif base.endswith("/jobs/search"):
        root = base[:-len("/search")]
        candidates.append(base)
        candidates.append(root + "/intro")
        candidates.append(root)
    elif base.endswith("/jobs"):
        candidates.append(base + "/search")
        candidates.append(base + "/intro")
        candidates.append(base)
    else:
        candidates.append(base + "/jobs/search")
        candidates.append(base + "/jobs/intro")
        candidates.append(base + "/jobs")

    deduped = []
    seen = set()
    for url in candidates:
        if url not in seen:
            seen.add(url)
            deduped.append(url)

    return deduped


def _extract_icims_jobs_from_html(html: str, company_name: str):
    soup = BeautifulSoup(html, "lxml")
    jobs = []
    seen = set()

    # iCIMS listing pages usually expose job links containing /jobs/<id>/...
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if "/jobs/" not in href:
            continue

        title = a.get_text(" ", strip=True)
        if not title:
            continue

        if href.startswith("/"):
            # infer host from absolute parsing later in caller if needed
            continue

        key = (title.lower(), href.lower())
        if key in seen:
            continue
        seen.add(key)

        # Try to capture nearby location text from parent container
        location = ""
        parent_text = a.parent.get_text(" ", strip=True) if a.parent else ""
        loc_match = re.search(
            r"(US-[A-Z]{2}-[A-Za-z0-9\- ]+|[A-Za-z ]+,\s?[A-Z]{2}|Remote)",
            parent_text
        )
        if loc_match:
            location = loc_match.group(1).strip()

        jobs.append({
            "company": company_name,
            "title": title,
            "location": location,
            "url": href,
            "description": "",
            "source": "icims"
        })

        if len(jobs) >= MAX_JOBS_PER_COMPANY:
            return jobs

    return jobs


def fetch_icims_jobs(base_url: str, company_name: str):
    search_urls = _build_icims_search_urls(base_url)

    for url in search_urls:
        try:
            response = SESSION.get(url, timeout=20)
            response.raise_for_status()

            html = response.text
            jobs = _extract_icims_jobs_from_html(html, company_name)

            if jobs:
                return jobs
        except Exception:
            continue

    raise RuntimeError(f"No working iCIMS endpoint found for {company_name}: {base_url}")

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

def debug_oracle_site_info(base_url: str):
    from urllib.parse import urlparse

    parsed = urlparse(base_url)
    host = parsed.netloc

    candidates = [
        f"https://{host}/hcmRestApi/resources/latest/recruitingCESites?onlyData=true",
        f"https://{host}/hcmRestApi/resources/latest/recruitingCECandidateExperienceSites?onlyData=true",
        f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&limit=1"
    ]

    for url in candidates:
        try:
            response = SESSION.get(url, timeout=20)
            print(f"ORACLE DEBUG | {url}")
            print(f"ORACLE DEBUG | status={response.status_code}")
            print(f"ORACLE DEBUG | body={response.text[:1000]}")
        except Exception as e:
            print(f"ORACLE DEBUG ERROR | {url} | {e}")

# ---------------- ORACLE CLOUD / TEXAS INSTRUMENTS ----------------
def fetch_oracle_jobs(base_url: str, company_name: str):
    """
    Oracle Cloud Candidate Experience parser for Texas Instruments.

    TI uses:
      /hcmRestApi/resources/latest/recruitingCEJobRequisitions

    The browser returns a search wrapper object, so we extract from nested
    items where requisition/job fields exist.
    """

    from urllib.parse import urlparse

    parsed = urlparse(base_url)
    host = parsed.netloc

    api_url = f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
        "Referer": base_url,
    }

    jobs = []
    seen = set()
    offset = 0
    limit = 100

    while True:
        params = {
            "onlyData": "true",
            "q": "",
            "location": "",
            "sortBy": "relevance",
            "limit": str(limit),
            "offset": str(offset),
        }

        try:
            response = SESSION.get(api_url, params=params, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"{company_name} Oracle API error: {e}")
            return jobs

        items = data.get("items", [])

        if not items:
            break

        batch_count = 0

        def walk(obj):
            nonlocal batch_count

            if isinstance(obj, dict):
                title = (
                    obj.get("Title")
                    or obj.get("title")
                    or obj.get("Name")
                    or obj.get("name")
                    or obj.get("ExternalTitle")
                    or obj.get("RequisitionTitle")
                    or obj.get("JobTitle")
                    or obj.get("jobTitle")
                    or ""
                )

                req_id = (
                    obj.get("Id")
                    or obj.get("id")
                    or obj.get("RequisitionId")
                    or obj.get("requisitionId")
                    or obj.get("RequisitionNumber")
                    or obj.get("requisitionNumber")
                    or obj.get("ReqId")
                    or obj.get("reqId")
                    or obj.get("JobId")
                    or obj.get("jobId")
                    or ""
                )

                location = (
                    obj.get("PrimaryLocation")
                    or obj.get("primaryLocation")
                    or obj.get("PrimaryLocationName")
                    or obj.get("Location")
                    or obj.get("location")
                    or obj.get("WorkLocation")
                    or obj.get("workLocation")
                    or ""
                )

                if title and req_id:
                    title = str(title).strip()
                    req_id = str(req_id).strip()
                    location = str(location).strip()

                    key = (title.lower(), req_id.lower())

                    if key not in seen:
                        seen.add(key)

                        job_url = (
                            f"https://{host}/hcmUI/CandidateExperience/en/sites/CX/"
                            f"requisitions/preview/{req_id}"
                        )

                        jobs.append({
                            "company": company_name,
                            "title": title,
                            "location": location,
                            "url": job_url,
                            "description": (
                                obj.get("ShortDescriptionStr")
                                or obj.get("shortDescriptionStr")
                                or obj.get("Description")
                                or obj.get("description")
                                or ""
                            ),
                            "source": "oracle"
                        })

                        batch_count += 1

                for value in obj.values():
                    walk(value)

            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(items)

        if len(jobs) >= MAX_JOBS_PER_COMPANY:
            return jobs[:MAX_JOBS_PER_COMPANY]

        offset += limit

        if not data.get("hasMore", False):
            break

        if batch_count == 0:
            break

    return jobs[:MAX_JOBS_PER_COMPANY]

# ---------------- GOOGLE CAREERS ----------------
def fetch_google_jobs(base_url: str, company_name: str):
    """
    Google Careers parser.

    Current strategy:
      1. Fetch Google Careers search pages for hardware/silicon keywords.
      2. Debug whether job data exists in HTML, embedded script data, or links.
      3. Return jobs only if real job result URLs are found.

    NOTE:
      Google Careers is heavily client-rendered, so normal BeautifulSoup link
      parsing may return 0 until we reverse the hidden API.
    """
    from urllib.parse import urlencode
    import json

    queries = [
        "silicon",
        "design verification",
        "rtl",
        "asic",
        "firmware",
        "embedded",
        "fpga",
        "hardware"
    ]

    jobs = []
    seen = set()

    for query in queries:
        for page in range(1, 6):
            params = {
                "q": query,
                "location": "United States",
                "employment_type": "FULL_TIME",
                "sort_by": "date",
                "page": str(page)
            }

            url = f"{base_url.rstrip('/')}?{urlencode(params)}"

            try:
                response = SESSION.get(url, timeout=20)
                response.raise_for_status()
            except Exception as e:
                print(f"{company_name} Google fetch error: {e}")
                continue

            html = response.text
            soup = BeautifulSoup(html, "lxml")

            print(f"GOOGLE DEBUG | url: {url}")
            print(f"GOOGLE DEBUG | status: {response.status_code}")
            print(f"GOOGLE DEBUG | html length: {len(html)}")
            print(f"GOOGLE DEBUG | first 300 chars: {html[:300].replace(chr(10), ' ')}")

            # ------------------------------------------------------------
            # Debug embedded script/config data
            # ------------------------------------------------------------
            apollo_matches = re.findall(
                r"window\.__APOLLO_STATE__\s*=\s*({.*?});",
                html,
                flags=re.DOTALL
            )

            ppconfig_matches = re.findall(
                r"window\[['\"]ppConfig['\"]\]\s*=\s*({.*?});",
                html,
                flags=re.DOTALL
            )

            if apollo_matches:
                print(f"GOOGLE DEBUG | APOLLO_STATE matches: {len(apollo_matches)}")

            if ppconfig_matches:
                print(f"GOOGLE DEBUG | ppConfig matches: {len(ppconfig_matches)}")

            for match in apollo_matches[:1]:
                try:
                    data = json.loads(match)
                    print("GOOGLE DEBUG | APOLLO JSON FOUND")
                    print(str(data)[:1000])
                except Exception as e:
                    print(f"GOOGLE DEBUG | APOLLO JSON parse failed: {e}")

            for match in ppconfig_matches[:1]:
                try:
                    # ppConfig may not be strict JSON, but try anyway.
                    data = json.loads(match)
                    print("GOOGLE DEBUG | PPCONFIG JSON FOUND")
                    print(str(data)[:1000])
                except Exception as e:
                    print(f"GOOGLE DEBUG | PPCONFIG JSON parse failed: {e}")
                    print(f"GOOGLE DEBUG | PPCONFIG raw preview: {match[:1000]}")

            # ------------------------------------------------------------
            # Debug links
            # ------------------------------------------------------------
            links = soup.find_all("a", href=True)
            print(f"GOOGLE DEBUG | links found: {len(links)}")

            for a in links[:20]:
                print(
                    "GOOGLE DEBUG LINK:",
                    a.get_text(" ", strip=True),
                    "|",
                    a["href"]
                )

            page_jobs = 0

            # ------------------------------------------------------------
            # Attempt normal link extraction
            # ------------------------------------------------------------
            for a in links:
                href = a["href"].strip()
                title = a.get_text(" ", strip=True)

                if not href or not title:
                    continue

                # Google job detail links usually contain /jobs/results/<id>
                is_job_link = (
                    "/about/careers/applications/jobs/results/" in href
                    or "./jobs/results/" in href
                )

                if not is_job_link:
                    continue

                # Skip generic result/search links
                if href.rstrip("/").endswith("/jobs/results") or "?" in href and "/jobs/results?" in href:
                    continue

                if len(title) < 5:
                    continue

                bad_anchor_text = {
                    "learn more",
                    "copy link",
                    "email a friend",
                    "share",
                    "job search",
                    "recommended jobs",
                    "saved jobs",
                    "job alerts"
                }

                if title.lower() in bad_anchor_text:
                    continue

                if href.startswith("./"):
                    href = "https://www.google.com/about/careers/applications/" + href[2:]
                elif href.startswith("/"):
                    href = f"https://www.google.com{href}"

                href = href.split("?", 1)[0].rstrip("/")

                key = (title.lower(), href.lower())
                if key in seen:
                    continue

                container_text = ""
                parent = a
                for _ in range(5):
                    if parent.parent:
                        parent = parent.parent
                        container_text = parent.get_text(" ", strip=True)
                        if (
                            "Google |" in container_text
                            or "Minimum qualifications" in container_text
                            or "Bachelor's degree" in container_text
                        ):
                            break

                location = ""
                loc_match = re.search(
                    r"Google\s*\|\s*(.*?)(?:\s+bar_chart|\s+Minimum qualifications|\s+Learn more|\s+share)",
                    container_text
                )
                if loc_match:
                    location = loc_match.group(1).strip()

                jobs.append({
                    "company": company_name,
                    "title": title,
                    "location": location,
                    "url": href,
                    "description": container_text,
                    "source": "google"
                })

                seen.add(key)
                page_jobs += 1

                if len(jobs) >= MAX_JOBS_PER_COMPANY:
                    return jobs

            # If this page has no jobs, do not keep paginating this query.
            if page_jobs == 0:
                break

    return jobs

def fetch_amd_jobs(base_url: str, company_name: str):
    jobs = []
    seen = set()

    page = 1

    hw_keywords = [
        "design verification", "verification engineer",
        "rtl", "asic", "soc", "cpu", "gpu",
        "silicon", "pre-silicon", "post-silicon",
        "firmware", "embedded", "fpga", "dft", "emulation"
    ]

    blocked_keywords = [
        "ai & society", "society", "social science",
        "sociotechnical", "alignment", "research intern",
        "principal researcher", "senior researcher",
        "business", "sales", "marketing", "finance",
        "legal", "hr", "recruiter", "product manager"
    ]

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://careers.amd.com/careers-home/jobs"
    }

    while True:
        url = (
            "https://careers.amd.com/api/jobs"
            f"?page={page}"
            f"&sortBy=relevance"
            f"&descending=false"
            f"&internal=false"
        )

        try:
            response = SESSION.get(url, headers=headers, timeout=20, allow_redirects=False)

            if response.status_code in (301, 302, 404):
                break

            response.raise_for_status()
            data = response.json()

        except Exception as e:
            print(f"{company_name} AMD API stop at page {page}: {e}")
            break

        page_jobs = data.get("jobs", [])

        if not page_jobs:
            break

        for job in page_jobs:

            job_data = job.get("data", {})

            title = (job_data.get("title") or "").strip()
            if not title:
                continue

            job_id = str(job_data.get("req_id") or job_data.get("slug") or "").strip()

            city = job_data.get("city") or ""
            state = job_data.get("state") or ""
            country = job_data.get("country") or ""

            location = ", ".join([x for x in [city, state, country] if x])

            job_url = (
                job_data.get("canonical_url")
                or job_data.get("apply_url")
                or f"https://careers.amd.com/jobs/{job_id}"
            )

            key = (title.lower(), job_id)

            if key in seen:
                continue

            seen.add(key)

            jobs.append({
                "company": company_name,
                "title": title,
                "location": location,
                "url": job_url,
                "description": job_data.get("description") or "",
                "source": "amd"
            })

            if len(jobs) >= MAX_JOBS_PER_COMPANY:
                break

        page += 1

    return jobs

# ---------------- QUALCOMM (Eightfold API) ----------------
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

    print("QUALCOMM DEBUG | Qualcomm uses a separate Eightfold-backed careers flow. Returning 0 jobs for now.")
    return []

def fetch_microsoft_jobs(base_url: str, company_name: str):
    jobs = []
    seen = set()

    start = 0
    page_size = 20

    hw_keywords = [
        "design verification",
        "verification engineer",
        "rtl",
        "asic",
        "soc",
        "cpu",
        "gpu",
        "silicon",
        "pre-silicon",
        "post-silicon",
        "firmware",
        "embedded",
        "fpga",
        "dft",
        "emulation"
    ]

    blocked_keywords = [
        "ai & society",
        "society",
        "social science",
        "sociotechnical",
        "socio-technical",
        "alignment center",
        "computational social science",
        "research intern",
        "principal researcher",
        "senior researcher",
        "workflow analysis",
        "business",
        "sales",
        "marketing",
        "finance",
        "legal",
        "hr",
        "recruiter",
        "program manager",
        "product manager",
        "customer success",
        "account manager",
        "consultant"
    ]

    while True:
        url = (
            "https://apply.careers.microsoft.com/api/pcsx/search"
            f"?domain=microsoft.com"
            f"&query="
            f"&location="
            f"&start={start}"
            f"&sort_by=timestamp"
        )

        try:
            response = SESSION.get(url, timeout=20)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"{company_name} Microsoft API error: {e}")
            break

        positions = data.get("data", {}).get("positions", [])

        if not positions:
            break

        for job in positions:
            title = (job.get("name") or "").strip()
            job_id = str(job.get("id") or "").strip()

            if not title:
                continue

            title_l = title.lower()

            if not any(k in title_l for k in hw_keywords):
                continue

            if any(k in title_l for k in blocked_keywords):
                continue

            locations = job.get("locations") or job.get("standardizedLocations") or []
            if isinstance(locations, list):
                location = ", ".join(locations)
            else:
                location = str(locations)

            job_url = (
                job.get("positionUrl")
                or f"https://apply.careers.microsoft.com/careers/job/{job_id}"
            )

            if isinstance(job_url, str) and job_url.startswith("/"):
                job_url = f"https://apply.careers.microsoft.com{job_url}"

            key = (title_l, job_id)

            if key in seen:
                continue

            seen.add(key)

            jobs.append({
                "company": company_name,
                "title": title,
                "location": location,
                "url": job_url,
                "description": "",
                "source": "microsoft"
            })

            if len(jobs) >= MAX_JOBS_PER_COMPANY:
                return jobs

        start += page_size

    return jobs