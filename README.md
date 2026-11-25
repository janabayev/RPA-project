# Job Posting Triage Bot

RPA project (Robot Framework + Machine Learning): a robot collects job postings from karriere.at,
a text classifier decides which postings are relevant, and the result is a ranked report.


> **Data not included.** The collected postings (`data/jobs_raw.csv`, 450 job ads with full texts) are not part of this
> repository, because the texts belong to the employers and to karriere.at. The labels (`data/labels.csv`) and the trained
> model (`model/`) are included, so `rank_jobs.robot` runs without the dataset. To retrain the model, collect your own
> postings with `collect_jobs.robot` and label them in the labeling app.

## Project structure

```
job-triage-bot/
├── robot/
│   ├── collect_jobs.robot      # Phase 1: collects job postings (training data)
│   ├── rank_jobs.robot         # Phase 4: collects new jobs, scores them, writes the report
│   ├── karriere.resource       # keywords shared by both robots (search, load more, scrape)
│   └── js/
│       ├── collect_links.js    # finds job detail links on a search result page
│       ├── load_more.js        # clicks "Weitere Jobs anzeigen" (loads the next 15 results)
│       ├── extract_job.js      # extracts the job data from a detail page
│       └── handle_cookies.js   # closes the cookie banner (best effort)
├── libraries/
│   ├── JobStorage.py           # keyword library: CSV storage + deduplication
│   └── JobModel.py             # keyword library: Predict Relevance, Write Report (loads the model)
├── notebooks/
│   └── train_model.ipynb       # Phase 3: model training and evaluation
├── labeling/
│   ├── label_app.py            # Phase 2: local labeling app (Python standard library only)
│   ├── index.html              # labeling user interface
│   └── criteria.md             # labeling criteria, shown in the app
├── data/
│   ├── jobs_raw.csv            # output of the robot
│   ├── labels.csv              # labels (created by the labeling app)
│   ├── jobs_labeled.csv        # jobs + labels in one file (created by --export)
│   ├── jobs_new.csv            # new jobs collected by rank_jobs.robot
│   └── predictions.csv         # all scores given by rank_jobs.robot (history)
├── model/
│   ├── weights/                # the trained network as plain CSV files:
│   │   ├── W1.csv, b1.csv      #   words x 100 units (one row per word)
│   │   ├── W2.csv, b2.csv      #   100 x 10
│   │   └── W3.csv, b3.csv      #   10 x 1 (output)
│   ├── model_info.json         # token pattern, layers, threshold
│   ├── metrics.json            # test results, baselines, settings
│   ├── confusion_matrix.csv
│   ├── test_predictions.csv    # each test job: my label and the model's probability
│   └── vocabulary.csv          # the words of the model, counted in relevant / not relevant titles
├── results/
│   └── job_report.html         # ranked report (created by rank_jobs.robot)
└── requirements.txt
```

## Setup

1. Python 3.10+ and Firefox must be installed.
2. Install the dependencies:
   ```
   pip install -r requirements.txt
   ```
3. geckodriver (the Firefox driver) does not need to be installed by hand:
   Selenium 4.11+ downloads it automatically on the first run (Selenium Manager).

## Phase 1: collecting job postings

Quick test (first 15-18 results per query only, max. 5 jobs per query):
```
robot -d results -v MAX_PAGES:1 -v MAX_JOBS_PER_QUERY:5 robot/collect_jobs.robot
```

Full run (stops when `data/jobs_raw.csv` holds 350 jobs, takes about 20-30 minutes):
```
robot -d results robot/collect_jobs.robot
```
Different target, e.g. 450 jobs: `robot -d results -v MAX_TOTAL_JOBS:450 robot/collect_jobs.robot`.

Without a visible browser window: add `-v HEADLESS:True`.

Settings (in `*** Variables ***` or via `-v NAME:value`):

| Variable | Default | Meaning |
|---|---|---|
| `LOCATION` | `wien` | location in the search URL |
| `MAX_TOTAL_JOBS` | `350` | the robot stops when the CSV holds this many jobs (jobs from earlier runs count) |
| `MAX_PAGES` | `10` | max. result blocks per query: the first page plus up to 9 clicks on "Weitere Jobs anzeigen" (about 15 jobs each) |
| `MAX_JOBS_PER_QUERY` | `40` | upper limit of new jobs per query |
| `DELAY` | `2s` | pause after each page load (keeps the load on the site low) |
| `SEARCH_QUERIES` | 11 queries | search terms used in the URL |

Output: `data/jobs_raw.csv` (UTF-8, opens correctly in Excel). Running the robot again appends
only new jobs; jobs already in the file are skipped (deduplicated by job ID).

### How it works / non-obvious parts

- **Search by URL, more results by button.** The robot opens the search URL directly
  (`/jobs/<query>/<location>`), which avoids the dynamic search form. karriere.at has no result
  pages in the URL (`?page=2` returns the first page again), so further results are loaded with the
  button "Weitere Jobs anzeigen" (about 15 jobs per click, `load_more.js`). The robot clicks only as
  often as needed: it stops when the page shows enough jobs that are not yet in the CSV
  (keyword `Count Unsaved Jobs`), when the button disappears (all results shown), or after
  `MAX_PAGES` blocks.
- **The first click on "Weitere Jobs anzeigen" is ignored by the site.** After a page load, the
  first click loads nothing (tested in November 2026: same jobs after 6 seconds, also when the
  button is scrolled into view first); the second click works. The keyword `Load More Jobs`
  therefore clicks up to 3 times and waits up to 5 seconds after each click for new links.
- **Job links are found by URL pattern** (`/jobs/<number>`), not by CSS classes. Class names on job
  portals change often; the URL pattern is much more stable.
- **Data extraction uses JSON-LD first.** Job portals embed a machine-readable `JobPosting` block
  (schema.org) for Google Jobs. `extract_job.js` reads title, company, location, date and
  description from it. If the block is missing, the robot falls back to `<h1>` and the text of
  `<main>`. The column `extraction_source` shows which method was used for each job.
- **Query mix.** The queries include non-relevant fields (controlling, marketing, IT support),
  so the labeled data later contains both classes.
- **Even quota per query.** If the robot simply stopped at `MAX_TOTAL_JOBS`, the last queries in
  the list would get no jobs. Instead, before each query the robot computes
  `quota = (MAX_TOTAL_JOBS - jobs already stored) / queries left`. If a query finds fewer jobs
  (few results, or jobs already saved under another query), the following queries get a larger
  quota. If the target is still not reached, run the robot again with a higher `MAX_PAGES`.

### Assumptions

- The search URL format of karriere.at is `/jobs/<query>/<location>`; more results are loaded
  with the button "Weitere Jobs anzeigen" (CSS class `m-loadMoreJobsButton__button`).
- Job detail URLs contain `/jobs/<numeric id>`.
- Only publicly visible postings are collected; no login.

### Troubleshooting

| Problem | What to check |
|---|---|
| `Found 0 job links` | Open the search URL from the log in Firefox. If the URL format changed, adjust `Collect Job Links`. Open a job and check its URL: if it is not `/jobs/<number>`, adjust the regex in `collect_links.js`. |
| Only 15-18 links per query | The "Weitere Jobs anzeigen" button was not found or did not load anything (warning in `log.html`). Check the button's class name in Firefox and adjust `load_more.js`. |
| Fewer jobs than `MAX_TOTAL_JOBS` | The last queries had few results. Run the robot again with a higher `MAX_PAGES`, or add queries. |
| `extraction_source` is `main` for all jobs | The page has no JSON-LD. Data is still saved, but the description may contain menu text. |
| geckodriver error | Update Selenium (`pip install -U selenium`) or install geckodriver manually and add it to PATH. |
| Description is empty | Increase `DELAY` (page not fully loaded). |

## Phase 2: labeling

The labels are my own judgement ("would I apply to this job?"). The rules are in
`labeling/criteria.md` and are shown in the app (button *Criteria*).

Start the labeling app (no extra packages needed):
```
python labeling/label_app.py
```
The browser opens `http://127.0.0.1:8765` and shows one job at a time. One click or key saves the
label and opens the next job:

| Key / button | Action |
|---|---|
| `1` / Relevant | label 1 |
| `0` / Not relevant | label 0 |
| reason chips (too senior, wrong field, ...) | label 0 and store the reason as a note |
| `U` / Unsure | label `?` - excluded from training |
| `←` / Back | previous job (to correct a label, just click another button) |
| `→` / Skip | decide later |
| `N` | type a note, `Enter` to leave the field |

Labels are written to `data/labels.csv` (`job_id, label, note, labeled_at`) after every click.
Stop the app with `Ctrl+C`; on the next start it continues where you stopped.

To get one file with all jobs and their labels (for the model or for Excel):
```
python labeling/label_app.py --export
```
This writes `data/jobs_labeled.csv`.

### Non-obvious parts

- **Labels in a separate file.** The robot appends to `jobs_raw.csv` while it runs. If the app
  rewrote the same file at the same time, freshly scraped rows could be lost. With
  `labels.csv` (joined by `job_id`) labeling can start while the robot is still collecting.
  `labels.csv` is written to a temp file first and then replaced, so it is never half-written.
- **New jobs appear automatically.** The app re-reads `jobs_raw.csv` when it changes (the page
  checks every 20 seconds). A row the robot is writing at that moment has missing columns and
  is skipped until the next read.
- **Mixed order.** Jobs are sorted by a hash of the job ID, so the search queries are mixed
  (labeling all marketing jobs in a row would make the decisions less careful) and the order is
  the same after a restart.
- **Highlighting.** Keywords are colored to speed up decisions: seniority and required years of
  experience, junior/entry level, internship/part-time, skills (SQL, Python, Power BI, ...) and
  salary. The patterns are in `PATTERNS` in `labeling/index.html`. Years are only marked when
  "Erfahrung"/"experience" follows, so "seit 80 Jahren" in a company description is not marked.

## Phase 3: model

`notebooks/train_model.ipynb` trains the model; every step is explained in the notebook. Run it from the
`notebooks` folder (`jupyter notebook notebooks/train_model.ipynb`, or open it in VS Code).
It follows the course unit *ML for RPA on Text Data*: bag-of-words with `CountVectorizer`
(binary, max. 500 words), balanced classes with `groupby().sample()`, `MLPClassifier(hidden_layer_sizes=(100, 10))`,
80/20 train/test split.

**Data:** 450 labeled jobs, 150 relevant (33%), 300 not relevant.

**Decisions:**

- **Balanced classes, as in the course.** A net trained on unbalanced data can learn to predict the more
  frequent class and still reach a high accuracy. As in the course, the same number of jobs is drawn from
  each class (`groupby('y').sample(n=150)`): the model uses **300 jobs, 150 relevant and 150 not relevant**.
  The other 150 not relevant jobs are not used for training; they serve as an extra check (see results).
- **Only the job title is used.** Compared on 10 random splits, title alone gave F1 0.67,
  title + full description 0.57. The descriptions are long and mostly describe the company, benefits and the
  application process, which is similar in all postings; with 300 examples the model cannot learn
  to ignore these words.
- **Stop words:** the English list from scikit-learn plus a short German list (most postings are German).
  As in the course, `not` is kept. Tokens: words with 3+ letters, including umlauts. The 300 titles contain
  399 different words, fewer than `max_features=500`.
- **`max_iter`** is chosen with 5-fold cross-validation on the training set only (result: 100).
  The validation F1 was similar for all values between 5 and 100 (0.61-0.66).
- **Final model:** after the evaluation, the model is trained again on all 300 balanced jobs with the
  same settings; this is the model in `model/weights/`.
- **Model saved as plain files, not pickle.** The course saves model and vectorizer with `pickle`.
  Here the trained network is saved as its weight matrices (`W1.csv` ... `b3.csv`) plus the vocabulary,
  so every number can be opened in Excel and the prediction can be explained:
  `x` = 1 for each vocabulary word in the title, `h1 = relu(x·W1 + b1)`, `h2 = relu(h1·W2 + b2)`,
  `probability = sigmoid(h2·W3 + b3)`. The notebook (section 9) checks that this formula gives the same
  probabilities as scikit-learn (largest difference about 2·10⁻¹⁶).

**Results on the test set** (60 jobs, 30 relevant, never used for training or tuning):

| | accuracy | precision | recall | F1 |
|---|---|---|---|---|
| always "not relevant" | 0.50 | 0.00 | 0.00 | 0.00 |
| keyword rule on title | 0.63 | 0.75 | 0.40 | 0.52 |
| MLP model | 0.67 | 0.62 | 0.83 | 0.71 |

Because the test set is balanced, random guessing gives an accuracy of 0.5 (the course's 1/n check).
The keyword rule is the rule I would write by hand (data/analyst/BI/reporting in the title, no
senior/lead/manager): it is precise but finds only 40% of the relevant jobs. The model finds
83% of them, at the cost of more false alarms.

**Extra check on the 150 unused not relevant jobs** (never seen by the model): the model wrongly
recommends 71 of them
(47%),
similar to the test set (15 of 30). So the model rarely misses a good job, but about every second
not relevant job is also recommended. For a job search this is acceptable: the report is sorted by
probability, and checking an extra job costs less than missing a good one.

**Limitations:**

- The model learns my labels, including inconsistent ones (e.g. some IT-support jobs labeled
  relevant, others not). Errors are listed in the notebook (section 7) and in `model/test_predictions.csv`.
- The test set has only 60 jobs, so the metrics would change by several points with another split.
- Training score about 1.0 vs. test 0.67: the model overfits; more labeled jobs would help.
- Balancing by undersampling uses only 300 of the 450 labeled jobs.
- The share of relevant jobs (33%) reflects the chosen search queries, not the job market.

## Phase 4: complete process (robot + model)

```
robot -d results robot/rank_jobs.robot
```
Quick test with 5 jobs: `robot -d results -v MAX_NEW_JOBS:5 robot/rank_jobs.robot`

1. **Collect new jobs.** Same search as in phase 1 (keywords in `karriere.resource`), with the queries
   in `RANK_QUERIES`. Jobs that are already in `data/jobs_raw.csv` (the training data) are skipped;
   new jobs are saved to `data/jobs_new.csv`. The robot stops after `MAX_NEW_JOBS` (default 40) new jobs.
2. **Score.** For each new job the robot calls the Python keyword `Predict Relevance` (`libraries/JobModel.py`)
   with the job title, similar to `predict_default` in the course's `mytools.py`. The library reads the weight
   files from `model/weights/` once and computes the probability with numpy (formula in phase 3).
3. **Report.** `Write Report` writes `results/job_report.html`: the new jobs sorted by probability,
   recommended jobs (probability >= 0.5) marked in the column *Recommended*, with links to karriere.at. The robot opens the
   report in Firefox and saves a screenshot. All scores are also appended to `data/predictions.csv`.

### Non-obvious parts

- **Shared keywords.** Both robots use the same search and scraping keywords from `karriere.resource`.
  The keyword `Collect Jobs For Queries` gets the keyword that measures progress as an argument:
  `Saved Job Count` (all jobs in the CSV) in phase 1, `New Jobs Count` (jobs of this run) in phase 4.
- **Only new jobs.** `JobStorage.py` gets a second file (`known_csv`): job IDs in it count as already
  seen, but nothing is written to it. So the training data stays unchanged, and the report never
  shows jobs I have already labeled.

## How to extend

- **More training data:** run `collect_jobs.robot` with a higher `MAX_TOTAL_JOBS`, label the new jobs
  in the labeling app, run the notebook again. The robot in phase 4 uses the new weight files automatically.
- **Other searches:** change `SEARCH_QUERIES` / `RANK_QUERIES` or `LOCATION`.
- **Threshold:** `threshold` in `model/model_info.json` (default 0.5).

