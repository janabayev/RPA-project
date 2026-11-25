"""Robot Framework keyword library: stores scraped job postings in a CSV file.

- One row per job posting, deduplicated by job_id (taken from the URL).
- Appends to an existing file, so the robot can be run several times
  (different queries, different days) without losing earlier data or labels.
- The column "label" is left empty in this file. Labels are stored separately in data/labels.csv
  by the labeling app (labeling/label_app.py), so labeling can run while the robot is still writing.
"""

import csv
import os
import re
from datetime import datetime

from robot.api import logger
from robot.api.deco import keyword, library

FIELDS = [
    "job_id", "url", "title", "company", "location", "date_posted",
    "employment_type", "search_query", "scraped_at", "extraction_source",
    "description", "label",
]

_JOB_ID_RE = re.compile(r"/jobs/(\d+)")


def clean_text(text):
    """Collapse whitespace; keep single line breaks between paragraphs."""
    if not text:
        return ""
    text = str(text).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def job_id_from_url(url):
    match = _JOB_ID_RE.search(url or "")
    return match.group(1) if match else (url or "")


@library(scope="GLOBAL", auto_keywords=False)
class JobStorage:

    def __init__(self, csv_path="data/jobs_raw.csv", known_csv=None):
        """``known_csv`` (optional): jobs in this file count as already seen but are not written to.
        rank_jobs.robot uses it so that only jobs that are not in the training data are collected."""
        self.csv_path = os.path.abspath(csv_path)
        os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
        self._seen = self._load_ids(self.csv_path)
        self._stored = len(self._seen)
        if known_csv:
            self._seen |= self._load_ids(os.path.abspath(known_csv))
        self._this_run = []
        logger.info(f"JobStorage: {self.csv_path} ({self._stored} jobs stored, {len(self._seen)} known)")

    @staticmethod
    def _load_ids(path):
        if not os.path.exists(path):
            return set()
        with open(path, newline="", encoding="utf-8-sig") as f:
            return {row["job_id"] for row in csv.DictReader(f) if row.get("job_id")}

    @keyword("Job Already Saved")
    def job_already_saved(self, url):
        return job_id_from_url(url) in self._seen

    @keyword("Save Job")
    def save_job(self, job, url, search_query):
        """Appends one job to the CSV. ``job`` is the dictionary returned by extract_job.js."""
        job_id = job_id_from_url(url)
        if job_id in self._seen:
            return False
        row = {
            "job_id": job_id,
            "url": url,
            "title": clean_text(job.get("title")),
            "company": clean_text(job.get("company")),
            "location": clean_text(job.get("location")),
            "date_posted": clean_text(job.get("date_posted"))[:10],
            "employment_type": clean_text(job.get("employment_type")),
            "search_query": search_query,
            "scraped_at": datetime.now().isoformat(timespec="seconds"),
            "extraction_source": job.get("source", ""),
            "description": clean_text(job.get("description")),
            "label": "",
        }
        write_header = not os.path.exists(self.csv_path) or os.path.getsize(self.csv_path) == 0
        # utf-8-sig adds a BOM so Excel opens umlauts correctly
        encoding = "utf-8-sig" if write_header else "utf-8"
        with open(self.csv_path, "a", newline="", encoding=encoding) as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS, quoting=csv.QUOTE_ALL)
            if write_header:
                writer.writeheader()
            writer.writerow(row)
        self._seen.add(job_id)
        self._stored += 1
        self._this_run.append({k: v for k, v in row.items() if k not in ("description", "label")})
        logger.info(f"Saved {job_id}: {row['title']} ({row['company']})")
        return True

    @keyword("Count Unsaved Jobs")
    def count_unsaved_jobs(self, urls):
        """Number of job URLs in the list that are not in the CSV yet."""
        return sum(1 for url in urls if job_id_from_url(url) not in self._seen)

    @keyword("Saved Job Count")
    def saved_job_count(self):
        """Number of jobs in the CSV file."""
        return self._stored

    @keyword("New Jobs Count")
    def new_jobs_count(self):
        """Number of jobs saved during this robot run."""
        return len(self._this_run)

    @keyword("Jobs Saved In This Run")
    def jobs_saved_in_this_run(self):
        """List of the jobs saved during this run (dictionaries without the description)."""
        return [dict(job) for job in self._this_run]
