## Fetch ECB series defined in config.yaml and return one tidy dataFrame.
## Run from the project root: python src/data.py


import io
import time
from pathlib import Path

import pandas as pd
import requests           # downloads from the web
import yaml               # reads the config.yaml file

BASE_URL = "https://data-api.ecb.europa.eu/service/data"
CACHE_DIR = Path("data/raw")


def load_config(path="config.yaml"):
    # Opens config.yaml and turns it into a Python dictionary
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_series(dataset, key, start=None, timeout=30):
    # Downloads one ECB series as a DataFrame with columns: date, value

    # Build the URL from the dataset and key
    url = f"{BASE_URL}/{dataset}/{key}"
    params = {"format": "csvdata"}
    if start:
        params["startPeriod"] = start
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()   # stops with an error if the request failed

    df = pd.read_csv(io.StringIO(response.text))
    # Keeps only the TIME_PERIOD and OBS_VALUE and renames them
    df = df[["TIME_PERIOD", "OBS_VALUE"]].rename(
        columns={"TIME_PERIOD": "date", "OBS_VALUE": "value"}
    )
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def fetch_with_cache(dataset, key, max_age_hours=24, start=None):
    # A wrapper around fetch_series that avoids re-downloading
  
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{dataset}_{key}.csv"

    # If the file exists and is less than 24hrs old, it reads the saved copy and returns it
    if cache_file.exists():
        age_hours = (time.time() - cache_file.stat().st_mtime) / 3600
        if age_hours < max_age_hours:
            cached = pd.read_csv(cache_file, parse_dates=["date"])
            return cached

    # Otherwise, downloads fresh and saves it to CSV.
    df = fetch_series(dataset, key, start=start)
    df.to_csv(cache_file, index=False)
    return df


def fetch_all(config, start=None):
    # Fetch every indicator for every country. Returns date, country, indicator, value.
    
    frames = []
    failures = []

    for indicator, spec in config["indicators"].items():
        key_template = spec["key"]

        if "{country}" in key_template:
            countries = [c["code"] for c in config["countries"]]
        else:
            countries = ["U2"]  # series is already fixed to the euro area

        for country in countries:
            key = key_template.format(country=country)
            # Every fetch is in a try/except so that one bad series doesn't stop the rest. 
            # Failures are collected and printed at the end. 
            try:
                df = fetch_with_cache(spec["dataset"], key, start=start)
            except Exception as exc:
                failures.append((indicator, country, key, str(exc)))
                continue
            df = df.assign(country=country, indicator=indicator)
            frames.append(df[["date", "country", "indicator", "value"]])

    if failures:
        print("\nSeries that failed to download:")
        for indicator, country, key, error in failures:
            print(f"  {indicator} / {country} / {key}: {error}")

    if not frames:
        raise RuntimeError("No series could be downloaded. Check keys and connection.")

  # Stacks all series into one long table with columns date, country, indicator and value
  return pd.concat(frames, ignore_index=True)


if __name__ == "__main__":
    config = load_config()
    data = fetch_all(config, start="2015-01")

    print("\nRows downloaded:", len(data))
    print("\nFirst rows:")
    print(data.head())
    print("\nLatest observation per series:")
    latest = (
        data.dropna(subset=["value"])
        .sort_values("date")
        .groupby(["indicator", "country"])
        .tail(1)
        .sort_values(["indicator", "country"])
    )
    print(latest.to_string(index=False))

