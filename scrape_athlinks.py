import requests
import json
from math import ceil

def fetch_all_race_results():
    base_url = "https://reignite-api.athlinks.com/event/1108956/race/2590981/results"
    limit = 100
    all_results = []

    # Initial request to get total count
    params = {"correlationId": "", "from": 0, "limit": limit}
    response = requests.get(base_url, params=params)
    response.raise_for_status()

    data = response.json()
    total_athletes = data["division"]["totalAthletes"]

    # Add results from first request
    if "intervals" in data and len(data["intervals"]) > 0:
        all_results.extend(data["intervals"][0]["results"])

    # Calculate additional requests needed
    total_requests = ceil(total_athletes / limit)

    # Make remaining requests
    for i in range(1, total_requests):
        from_param = i * limit
        params = {"correlationId": "", "from": from_param, "limit": limit}

        response = requests.get(base_url, params=params)
        response.raise_for_status()

        data = response.json()
        if "intervals" in data and len(data["intervals"]) > 0:
            all_results.extend(data["intervals"][0]["results"])

        print(f"Fetched batch {i+1}/{total_requests} (from={from_param})")

    # Write combined results to file
    with open("2025_medcity.json", "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"Total results collected: {len(all_results)}")
    print("Results saved to race_results.json")

if __name__ == "__main__":
    fetch_all_race_results()

