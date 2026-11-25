*** Settings ***
Documentation       Phase 4 - the complete process: the robot collects NEW job postings from karriere.at,
...                 scores each one with the trained model and writes a ranked HTML report.
...
...                 1. Collect: same search as collect_jobs.robot (keywords in karriere.resource), but jobs that are
...                    already in data/jobs_raw.csv (the training data) are skipped. New jobs go to data/jobs_new.csv.
...                 2. Score: for every new job the Python keyword Predict Relevance (libraries/JobModel.py) returns
...                    the probability that the job is relevant, computed from the weight files in model/.
...                 3. Report: results/job_report.html, sorted by probability, opened in Firefox at the end.
...
...                 Run:    robot -d results robot/rank_jobs.robot
...                 Quick test:    robot -d results -v MAX_NEW_JOBS:5 robot/rank_jobs.robot

Resource            karriere.resource
Library             OperatingSystem
Library             ${CURDIR}/../libraries/JobStorage.py    ${NEW_CSV}    ${KNOWN_CSV}
Library             ${CURDIR}/../libraries/JobModel.py    ${MODEL_DIR}

Suite Setup         Open Firefox
Suite Teardown      Close All Browsers


*** Variables ***
${KNOWN_CSV}                ${CURDIR}/../data/jobs_raw.csv
${NEW_CSV}                  ${CURDIR}/../data/jobs_new.csv
${PREDICTIONS_CSV}          ${CURDIR}/../data/predictions.csv
${MODEL_DIR}                ${CURDIR}/../model
${REPORT_FILE}              ${CURDIR}/../results/job_report.html
${MAX_NEW_JOBS}             40
${MAX_JOBS_PER_QUERY}       10

# Queries for the job search itself: the fields where most of my labeled jobs were relevant,
# plus two queries that were not used for the training data (business-analyst, power-bi).
@{RANK_QUERIES}
...                         data-analyst
...                         business-intelligence
...                         data-engineer
...                         data-scientist
...                         ai
...                         digital
...                         it-support
...                         business-analyst
...                         power-bi


*** Test Cases ***
Collect New Job Postings
    Collect Jobs For Queries    ${RANK_QUERIES}    ${MAX_NEW_JOBS}    New Jobs Count
    ${n}=    New Jobs Count
    Log To Console    \nNew jobs collected: ${n}

Rank Jobs And Write Report
    @{jobs}=    Jobs Saved In This Run
    FOR    ${job}    IN    @{jobs}
        ${probability}=    Predict Relevance    ${job}[title]
        Set To Dictionary    ${job}    probability=${probability}
        Log    ${probability} ${job}[title]
    END
    Save Predictions    ${jobs}    ${PREDICTIONS_CSV}
    ${recommended}=    Write Report    ${jobs}    ${REPORT_FILE}
    ${n}=    Get Length    ${jobs}
    ${path}=    Normalize Path    ${REPORT_FILE}
    Log To Console    \nScored ${n} jobs, ${recommended} recommended. Report: ${path}
    Open Report In Browser    ${path}


*** Keywords ***
Open Report In Browser
    [Arguments]    ${path}
    Go To    file://${path}
    Sleep    3s
    Capture Page Screenshot    job_report.png
