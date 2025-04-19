import pdfplumber
import re
from dataclasses import dataclass
from collections import defaultdict

# Data structure for a race result entry
@dataclass
class Result:
    place: int
    division: str
    name: str
    time: str
    pace: str
    age: int
    sex: str
    city: str
    state: str

# Extracts results from the PDF, handling multi-word names and cities
def extract_results_from_pdf(pdf_path: str) -> list[Result]:
    results = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            lines = text.splitlines()

            for line in lines:
                if not line.strip() or not line.strip()[0].isdigit():
                    continue  # Skip header or empty lines

                try:
                    # Split the line on any amount of whitespace
                    parts = re.split(r'\s+', line.strip())

                    # Skip non-result lines
                    if len(parts) < 10:
                        continue

                    # Extract known fixed fields
                    place = int(parts[0])            # Overall race place
                    division = parts[2]              # Age/sex division (e.g., M3039)

                    # Time will be in mm:ss or h:mm:ss format
                    time_index = next(i for i, p in enumerate(parts) if re.match(r'^\d+:\d{2}(:\d{2})?$', p))

                    name = ' '.join(parts[3:time_index])  # Name is between division and time

                    # Extract post-time fields
                    time = parts[time_index]
                    pace = parts[time_index + 1]
                    age = int(parts[time_index + 2])
                    sex = parts[time_index + 3]

                    # State is the last item, city is everything between sex and state
                    state = parts[-1]
                    city = ' '.join(parts[time_index + 4:-1])  # Capture multi-word cities

                    # Build result object
                    results.append(Result(place, division, name, time, pace, age, sex, city, state))

                except Exception as e:
                    print(f"⚠️ Error parsing line:\n{line}")
                    print(f"   Details: {e}\n")

    return results

# Print sorted division rankings
def print_division_rankings(results: list[Result]):
    divisions = defaultdict(list)

    for result in results:
        divisions[result.division].append(result)

    for division, group in sorted(divisions.items()):
        print(f"\n🏁 Division: {division}")
        group.sort(key=lambda r: r.place)

        for i, runner in enumerate(group, 1):
            print(f"{i}. {runner.name} — Time: {runner.time}, Age: {runner.age}, "
                  f"City: {runner.city}, State: {runner.state}")

