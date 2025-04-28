import pdfplumber
import math
from dataclasses import dataclass
from collections import defaultdict

# Data structure for a race result entry
class Result:
    def __init__(self, place, name, time, pace, age, sex, city, state):
        self.place = place
        self.name = name
        self.time = time
        self.pace = pace
        self.age = int(age)
        self.sex = sex 
        self.city = city
        self.state = state

        self.set_division()

    def set_division(self):
        # Division spans a decade except for <19
        if self.age > 19:
            # Division is formatted like M2029 (males 20-29)
            decade = math.floor(self.age / 10) * 10
            self.division = f"{self.sex.upper()}{decade}{decade+9}"
        else:
            self.division = f"{self.sex.upper()}0119"


class Column:
    def __init__(self, name):
        self.name = name
        self.offset = -1
        self.right_bound = -1
        self.aliases = [name]

    def set_name(self, name):
        self.name = name
        self.aliases.append(name)

    def set_offset(self, offset):
        self.offset = offset

    def set_right_bound(self, offset):
        self.right_bound = offset

    def add_aliases(self, aliases):
        self.aliases.extend(aliases)

    def is_alias(self, alias):
        if any(a.lower() == alias.lower() for a in self.aliases):
            return True
        else:
            return False



# Extracts results from the PDF, handling multi-word names and cities
def extract_results_from_pdf(pdf_path: str) -> list[Result]:
    results = []
    columns = []

    rows = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            current_row = []
            previous_y = None
            y_tolerance = 5
            words = page.extract_words(x_tolerance=2, y_tolerance=2)

            for word in words:
                y0 = word['top']  # The y-coordinate of the top of the word
                text = word['text']
                    
                # If y0 is significantly different from the previous row, start a new row
                if previous_y is None or abs(y0 - previous_y) > y_tolerance:
                    if current_row:
                        rows.append(sorted(current_row, key=lambda w: w['x0']))  # Sort previous row by x-coordinates
                    current_row = [word]
                else:
                    current_row.append(word)
                
                previous_y = y0
            
            # Add the last row
            if current_row:
                rows.append(sorted(current_row, key=lambda w: w['x0']))  # Sort last row by x-coordinates


            
    # We have rows now
    for row in rows:

        # Skip header lines
        if len(row) < 7 or has_text(row, "======="):
            continue

        # TODO: account for possibility that column names are multiple words. Probably use minimum column spacing of 6
        # Map out columns
        if has_text(row, "Place") and has_text(row, "Name") and has_text(row, "Time"):
            offset = 0
            for idx, word in enumerate(row):
                word_text = word['text']
                new_column = Column(word_text.lower())
                # Place, Name, Time, Pace, Age, Sex, City, State

                if word_text.lower() in ["sex", "s", "gender", "m/f"]:
                    new_column.set_name("sex")
                    new_column.add_aliases(["s", "gender", "m/f"])

                if word_text.lower() in ["state", "st"]:
                    new_column.set_name("state")
                    new_column.add_aliases(["state", "st"])

                if word_text.lower() in ["overall place", "place"]:
                    new_column.set_name("place")
                    new_column.add_aliases(["overall place", "place"])

                offset = word['x0']

                if idx > 0:
                    columns[idx - 1].set_right_bound(offset)

                if idx == len(row) - 1:
                    new_column.set_right_bound(math.inf)

                new_column.set_offset(offset)
                columns.append(new_column)

            continue
        # Skip if we haven't found column headers yet
        if len(columns) == 0:
            continue

        # Mandatory values
        time = get_value(row, columns, 'time')
        name = get_value(row, columns, 'name')
        age = get_value(row, columns, 'age')
        sex = get_value(row, columns, 'sex')

        # Optional values
        pace = get_value(row, columns, 'pace')
        place = get_value(row, columns, 'place')
        city = get_value(row, columns, 'city')
        state = get_value(row, columns, 'state')


        if time is None or name is None or age is None or sex is None:
            for c in columns:
                print(c.name)
            raise Exception(f"Failed to extract data from {row} in file {pdf_path}")
        # Build result object
        results.append(Result(place, name, time, pace, age, sex, city, state))


    return results

def has_text(word_list, text):
    for w in word_list:
        if text in w['text']:
            return True
    return False

def get_value(row, columns: list[Column], column_name: str):

    delta = 0.01

    for col in columns:
        if col.is_alias(column_name):

            if col.offset < 0:
                return None

            value = None
            for word in row:

                if word['x0'] >= col.offset - delta and word['x1'] <= col.right_bound + delta:
                    if value is None:
                        value = word['text']
                    else:
                        # Append space + word text
                        value = f"{value} {word['text']}"

            return value

    return None

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

