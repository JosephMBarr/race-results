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
    column_indexes = {
            "place": -1,
            "division": -1,
            "name": -1,
            "time": -1,
            "pace": -1,
            "age": -1,
            "sex": -1,
            "city": -1,
            "state":-1
            }
    results = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            lines = text.splitlines()

            for line in lines:
                # Map out columns
                if "Place" in line and "Name" in line and "Time" in line:
                    for idx, col in enumerate(line.split(' ')):
                        if col.lower() in ["place"]:
                            column_indexes["place"] = idx
                        if col.lower() in ["div", "division"]:
                            column_indexes["division"] = idx
                        if col.lower() in ["name"]:
                            column_indexes["name"] = idx
                        if col.lower() in ["time"]:
                            column_indexes["time"] = idx
                        if col.lower() in ["pace"]:
                            column_indexes["pace"] = idx
                        if col.lower() in ["age"]:
                            column_indexes["age"] = idx
                        if col.lower() in ["sex", "s", "gender", "m/f"]:
                            column_indexes["sex"] = idx
                        if col.lower() in ["city"]:
                            column_indexes["city"] = idx
                        if col.lower() in ["state", "st"]:
                            column_indexes["state"] = idx

                if not line.strip() or not line.strip()[0].isdigit():
                    continue  # Skip header or empty lines

                try:
                    # Use regex to capture parts and trailing whitespace
                    parts_with_whitespace = re.findall(r'(\S+)(\s*)', line.strip())

                    # Extract parts and their corresponding trailing whitespace
                    parts = [(part, whitespace) for part, whitespace in parts_with_whitespace]


                    pace = get_part(parts, column_indexes, 'pace')
                    time = get_part(parts, column_indexes, 'time')
                    name = get_part(parts, column_indexes, 'name', variable_words=True)
                    place = get_part(parts, column_indexes, 'place')
                    division = get_part(parts, column_indexes, 'division')
                    age = get_part(parts, column_indexes, 'age')
                    sex = get_part(parts, column_indexes, 'sex')
                    city = get_part(parts, column_indexes, 'city', variable_words=True)
                    state = get_part(parts, column_indexes, 'state')


                    # Build result object
                    results.append(Result(place, division, name, time, pace, age, sex, city, state))

                except Exception as e:
                    print(f"⚠️ Error parsing line:\n{line} in {pdf_path}")
                    print(f"   Details: {e}\n")
                    raise(e)

    return results

#TODO: this is all kinds of broken
# I'm going to have to return the adjusted index from here, and pass it around, once we determine how many 
# columsn by which we have to adjust in order to parse out the next column
def get_part(parts, column_indexes, part_name, variable_words=False):
    if column_indexes[part_name] < 0:
        return None
    first_word = parts[column_indexes[part_name]][0]
    # Some columns (especially name and city) can have more than one word. Bank on there being at least two spaces to separate these
    if variable_words:
        whole_value = parts[first_word_idx]
        for p in parts[first_word_idx:]:
            if len(p[1]) == 1:

    else:
        return parts[first_word_idx]



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

