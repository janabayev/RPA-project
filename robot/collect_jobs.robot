*** Settings ***
Documentation       Phase 1 - collects job postings from karriere.at and stores them in data/jobs_raw.csv.
...                 For each search query the robot opens the search results, loads more results with the
...                 button "Weitere Jobs anzeigen", opens every job and extracts title, company, location and
...                 full description. The search and scraping keywords are in karriere.resource (shared with
...                 rank_jobs.robot).
...
...                 Run:    robot -d results robot/collect_jobs.robot
...                 Quick test:    robot -d results -v MAX_PAGES:1 -v MAX_JOBS_PER_QUERY:5 robot/collect_jobs.robot

Resource            karriere.resource
Library             ${CURDIR}/../libraries/JobStorage.py    ${OUTPUT_CSV}

Suite Setup         Open Firefox
Suite Teardown      Close All Browsers


*** Variables ***
${OUTPUT_CSV}               ${CURDIR}/../data/jobs_raw.csv
${MAX_TOTAL_JOBS}           350

# Mix of relevant and non-relevant queries, so the labeled data contains both classes.
@{SEARCH_QUERIES}
...                         data-analyst
...                         business-intelligence
...                         data-engineer
...                         data-scientist
...                         reporting
...                         controlling
...                         it-support
...                         marketing
...                         digital
...                         ai
...                         ki


*** Test Cases ***
Collect Job Postings
    Collect Jobs For Queries    ${SEARCH_QUERIES}    ${MAX_TOTAL_JOBS}    Saved Job Count
    ${total}=    Saved Job Count
    Log To Console    \nDone. Jobs stored in total: ${total}
