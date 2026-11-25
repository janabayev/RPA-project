*** Settings ***
Documentation       Shared keywords for both robots (collect_jobs.robot and rank_jobs.robot):
...                 opening Firefox, searching karriere.at, loading more results and scraping job pages.
...                 The suite that uses this resource must import JobStorage.py (keywords Save Job,
...                 Job Already Saved, Count Unsaved Jobs).

Library             SeleniumLibrary    timeout=10s    implicit_wait=0s
Library             Collections


*** Variables ***
${BASE_URL}                 https://www.karriere.at
${LOCATION}                 wien
${MAX_PAGES}                10
${MAX_JOBS_PER_QUERY}       40
${DELAY}                    2s
${HEADLESS}                 False


*** Keywords ***
Collect Jobs For Queries
    [Documentation]    Runs the search for every query until ``target`` is reached. ``count_keyword`` returns
    ...    the current progress (all jobs in the CSV, or new jobs in this run). The quota for each query is
    ...    jobs still missing / queries still left, capped by MAX_JOBS_PER_QUERY. If a query finds fewer
    ...    jobs, the following queries automatically get a larger quota.
    [Arguments]    ${queries}    ${target}    ${count_keyword}=Saved Job Count
    ${n_queries}=    Get Length    ${queries}
    FOR    ${i}    ${query}    IN ENUMERATE    @{queries}
        ${done}=    Run Keyword    ${count_keyword}
        IF    ${done} >= ${target}
            Log To Console    \nTarget of ${target} jobs reached - stopping.
            BREAK
        END
        ${quota}=    Evaluate
        ...    min(int($MAX_JOBS_PER_QUERY), math.ceil((int($target) - $done) / ($n_queries - $i)))
        ...    modules=math
        Collect Jobs For Query    ${query}    ${quota}
    END

Open Firefox
    IF    ${HEADLESS}
        Open Browser    about:blank    firefox    options=add_argument("-headless")
    ELSE
        Open Browser    about:blank    firefox
    END
    Set Window Size    1400    1000
    Go To    ${BASE_URL}
    Accept Or Reject Cookies

Accept Or Reject Cookies
    [Documentation]    Best effort - the only click on the page is "Weitere Jobs anzeigen", which is done
    ...    with JavaScript, so a remaining banner does not block scraping.
    Sleep    2s
    ${clicked}=    Execute Javascript    ${CURDIR}/js/handle_cookies.js
    Log    Cookie banner button clicked: '${clicked}'

Collect Jobs For Query
    [Arguments]    ${query}    ${quota}
    Log To Console    \n=== Query: ${query} (quota: ${quota} new jobs) ===
    ${job_urls}=    Collect Job Links    ${query}    ${quota}
    ${count}=    Get Length    ${job_urls}
    Log To Console    Found ${count} job links
    ${saved}=    Set Variable    ${0}
    FOR    ${url}    IN    @{job_urls}
        IF    ${saved} >= ${quota}    BREAK
        ${exists}=    Job Already Saved    ${url}
        IF    ${exists}    CONTINUE
        ${ok}=    Run Keyword And Return Status    Scrape Job    ${url}    ${query}
        IF    ${ok}
            ${saved}=    Evaluate    ${saved} + 1
        ELSE
            Log    Could not scrape ${url}    WARN
        END
    END
    Log To Console    Saved ${saved} new jobs for '${query}'

Collect Job Links
    [Documentation]    Opens the search results and returns unique job detail URLs.
    ...    karriere.at has no result pages in the URL; more results are loaded into the same page
    ...    with the button "Weitere Jobs anzeigen" (about 15 jobs per click). The robot clicks it until
    ...    enough jobs that are not yet in the CSV are on the page, the button is gone (all results
    ...    shown), or MAX_PAGES result blocks are loaded.
    [Arguments]    ${query}    ${quota}
    Go To    ${BASE_URL}/jobs/${query}/${LOCATION}
    Sleep    ${DELAY}
    ${urls}=    Execute Javascript    ${CURDIR}/js/collect_links.js
    FOR    ${block}    IN RANGE    1    ${MAX_PAGES}
        ${unsaved}=    Count Unsaved Jobs    ${urls}
        IF    ${unsaved} >= ${quota}    BREAK
        ${n_before}=    Get Length    ${urls}
        ${result}=    Load More Jobs    ${n_before}
        IF    '${result}' == 'no button'
            Log    No "Weitere Jobs anzeigen" button - all results for '${query}' are loaded
            BREAK
        ELSE IF    '${result}' == 'nothing loaded'
            Log    "Weitere Jobs anzeigen" loaded no new jobs for '${query}'    WARN
            BREAK
        END
        ${urls}=    Execute Javascript    ${CURDIR}/js/collect_links.js
        Sleep    ${DELAY}
    END
    RETURN    ${urls}

Load More Jobs
    [Documentation]    Clicks "Weitere Jobs anzeigen" and waits until new job links appear.
    ...    karriere.at ignores the first click after a page load (observed November 2026: the page
    ...    still shows the same jobs after 6 seconds, the second click works). So the robot clicks
    ...    up to 3 times. Returns 'loaded', 'no button' or 'nothing loaded'.
    [Arguments]    ${n_before}
    FOR    ${attempt}    IN RANGE    3
        ${clicked}=    Execute Javascript    ${CURDIR}/js/load_more.js
        IF    not ${clicked}    RETURN    no button
        ${loaded}=    Run Keyword And Return Status
        ...    Wait Until Keyword Succeeds    5s    0.5s    More Links Loaded    ${n_before}
        IF    ${loaded}    RETURN    loaded
    END
    RETURN    nothing loaded

More Links Loaded
    [Documentation]    Fails until the page shows more job links than before the click.
    [Arguments]    ${n_before}
    ${urls}=    Execute Javascript    ${CURDIR}/js/collect_links.js
    ${n_now}=    Get Length    ${urls}
    Should Be True    ${n_now} > ${n_before}

Scrape Job
    [Arguments]    ${url}    ${query}
    Go To    ${url}
    Wait Until Page Contains Element    css:h1
    Sleep    ${DELAY}
    ${job}=    Execute Javascript    ${CURDIR}/js/extract_job.js
    Save Job    ${job}    ${url}    ${query}
