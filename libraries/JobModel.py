"""Robot Framework keyword library: scores job postings with the trained model and writes the report.

The model is the neural network (MLPClassifier) trained in notebooks/train_model.ipynb. It is stored as
plain CSV files in model/ (no pickle), so every number can be opened and checked:

    model/weights/W1.csv, b1.csv   words x 100 one row per vocabulary word
    model/weights/W2.csv, b2.csv   100 x 10
    model/weights/W3.csv, b3.csv    10 x 1
    model/model_info.json          token pattern, threshold

Prediction for one job title (same formula as scikit-learn's MLPClassifier.predict_proba):
    x  = 1 for each vocabulary word in the lowercased title, else 0
    h1 = relu(x  @ W1 + b1)
    h2 = relu(h1 @ W2 + b2)
    p  = sigmoid(h2 @ W3 + b3)
The notebook checks that this gives the same probabilities as scikit-learn.
The model uses the job title only (see the notebook, section 2).
"""

import csv
import html
import json
import os
import re
from datetime import datetime

import numpy as np
from robot.api import logger
from robot.api.deco import keyword, library


def _read_matrix(path):
    """Reads a weight CSV: first column = row label (word or unit number), other columns = numbers."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))[1:]
    labels = [r[0] for r in rows]
    values = np.array([[float(v) for v in r[1:]] for r in rows])
    return labels, values


@library(scope="GLOBAL", auto_keywords=False)
class JobModel:

    def __init__(self, model_dir="model", threshold=None):
        self.model_dir = os.path.abspath(model_dir)
        with open(os.path.join(self.model_dir, "model_info.json"), encoding="utf-8") as f:
            self.info = json.load(f)
        weights = os.path.join(self.model_dir, "weights")
        self.vocabulary, self.W1 = _read_matrix(os.path.join(weights, "W1.csv"))
        _, self.W2 = _read_matrix(os.path.join(weights, "W2.csv"))
        _, self.W3 = _read_matrix(os.path.join(weights, "W3.csv"))
        self.b1, self.b2, self.b3 = (_read_matrix(os.path.join(weights, f"{n}.csv"))[1][:, 0] for n in ("b1", "b2", "b3"))
        self.token_re = re.compile(self.info["token_pattern"])
        self.threshold = float(threshold if threshold is not None else self.info.get("threshold", 0.5))
        self.metrics = {}
        metrics_file = os.path.join(self.model_dir, "metrics.json")
        if os.path.exists(metrics_file):
            with open(metrics_file, encoding="utf-8") as f:
                self.metrics = json.load(f)
        logger.info(f"JobModel: {len(self.vocabulary)} words, layers {self.W1.shape} {self.W2.shape} {self.W3.shape}")

    @keyword("Predict Relevance")
    def predict_relevance(self, title):
        """Returns the probability (0..1) that a job with this title is relevant."""
        tokens = set(self.token_re.findall(str(title).lower()))
        x = np.array([1.0 if word in tokens else 0.0 for word in self.vocabulary])
        h1 = np.maximum(0, x @ self.W1 + self.b1)
        h2 = np.maximum(0, h1 @ self.W2 + self.b2)
        probability = 1 / (1 + np.exp(-(h2 @ self.W3 + self.b3)[0]))
        return round(float(probability), 3)

    @keyword("Save Predictions")
    def save_predictions(self, jobs, csv_path):
        """Appends job_id, title, probability and time to a CSV file (history of all runs)."""
        csv_path = os.path.abspath(csv_path)
        write_header = not os.path.exists(csv_path)
        now = datetime.now().isoformat(timespec="seconds")
        with open(csv_path, "a", newline="", encoding="utf-8-sig" if write_header else "utf-8") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_ALL)
            if write_header:
                writer.writerow(["job_id", "title", "company", "url", "probability", "predicted_at"])
            for job in jobs:
                writer.writerow([job["job_id"], job["title"], job["company"], job["url"], job["probability"], now])

    @keyword("Write Report")
    def write_report(self, jobs, report_path):
        """Writes an HTML page with the jobs sorted by probability. Returns the number of recommended jobs."""
        report_path = os.path.abspath(report_path)
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        jobs = sorted(jobs, key=lambda j: float(j["probability"]), reverse=True)
        recommended = sum(1 for j in jobs if float(j["probability"]) >= self.threshold)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(self._render(jobs, recommended))
        logger.info(f"Report written: {report_path}")
        return recommended

    # ------------------------------------------------------------------ HTML
    def _render(self, jobs, recommended):
        e = html.escape
        test = self.metrics.get("test_metrics", {})
        model_note = ""
        if test:
            model_note = (f" Model quality on the test set: precision {test.get('precision_relevant', 0):.2f}, "
                          f"recall {test.get('recall_relevant', 0):.2f}, F1 {test.get('f1_relevant', 0):.2f}.")
        rows = []
        for rank, j in enumerate(jobs, 1):
            p = float(j["probability"])
            rec = p >= self.threshold
            rows.append(f"""
    <tr{' class="rec"' if rec else ''}>
      <td class="num">{rank}</td>
      <td class="num">{p:.2f}</td>
      <td>{'yes' if rec else ''}</td>
      <td><a href="{e(j['url'])}" target="_blank" rel="noopener">{e(j['title'])}</a></td>
      <td>{e(j['company'])}</td>
      <td>{e(j['location'])}</td>
      <td class="date">{e(j['date_posted'])}</td>
      <td>{e(j['search_query'])}</td>
    </tr>""")
        if not rows:
            rows.append('<tr><td colspan="8">No new jobs found in this run.</td></tr>')
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Job report {datetime.now():%Y-%m-%d %H:%M}</title>
<style>
  body {{ font: 14px/1.45 Helvetica, Arial, sans-serif; color: #000; margin: 32px auto; max-width: 1150px; padding: 0 24px; }}
  h1 {{ font-size: 20px; font-weight: bold; margin: 0 0 4px; }}
  p {{ margin: 0 0 12px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
  th, td {{ text-align: left; vertical-align: top; padding: 5px 8px; border-bottom: 1px solid #ccc; }}
  th {{ border-bottom: 2px solid #000; font-weight: bold; }}
  td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.date {{ white-space: nowrap; }}
  a {{ color: #00339a; }}
  .note {{ color: #444; font-size: 12px; margin-top: 12px; }}
</style>
</head>
<body>
  <h1>New job postings ranked by the model</h1>
  <p>karriere.at, Vienna. Robot run {datetime.now():%d.%m.%Y %H:%M}.</p>
  <p>{len(jobs)} new jobs, {recommended} recommended (probability &ge; {self.threshold:.2f}).</p>
  <table>
    <tr><th class="num">#</th><th class="num">Probability</th><th>Recommended</th><th>Title</th><th>Company</th>
        <th>Location</th><th>Posted</th><th>Query</th></tr>{''.join(rows)}
  </table>
  <p class="note">Recommended: probability of at least {self.threshold:.2f}. The model only reads the job title.{model_note}</p>
</body>
</html>
"""
