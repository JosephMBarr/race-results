import pdfplumber
import math
import json
import os
from dataclasses import dataclass
import csv

# Data structure for a race result entry
class Result:
    def __init__(self, place, name, time, pace, age, gender, city, state):
        self.place = int(place)
        self.name = name
        self.time = time
        self.pace = pace
        
        if age is None:
            self.age = None
        else:
            self.age = int(age)
        self.gender = gender 
        self.city = city
        self.state = state
        self.is_member = False
        self.points = 0
        self.division = None

    def set_membership(self, member, race_date):
        if member is not None:
            # Override gender in case it got missed
            if self.gender is None:
                self.gender = member.gender

            if member.birth_date is not None:
                # Override age based on date of birth and race date
                age = race_date.year - member.birth_date.year
                # Adjust if the race is before their birthday that year
                if (race_date.month, race_date.day) < (member.birth_date.month, member.birth_date.day):
                    age -= 1
                if age > 0:
                    self.age = age
            self.is_member = member.active

    def set_division(self):

        # There are cases where one or neither of these can be known
        if self.gender is None or self.age is None:
            return

        # Division spans a decade except for <19
        if self.age > 19:
            # Division is formatted like M2029 (males 20-29)
            decade = math.floor(self.age / 10) * 10
            self.division = f"{self.gender.upper()}{decade}{decade+9}"
        else:
            self.division = f"{self.gender.upper()}0119"


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


def convert_milliseconds_to_time_string(milliseconds):
    """
    Convert milliseconds to a readable time format (HH:MM:SS or MM:SS).

    Args:
        milliseconds (int): Time in milliseconds

    Returns:
        str: Formatted time string
    """
    if milliseconds is None:
        return "00:00"

    # Convert milliseconds to total seconds
    total_seconds = milliseconds // 1000

    # Calculate hours, minutes, and seconds
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    # Format based on whether hours are present
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"


def calculate_pace_from_time(time_ms, distance_miles=None):
    """
    Calculate pace per mile from finish time.

    Args:
        time_ms (int): Finish time in milliseconds
        distance_miles (float): Race distance in miles (defaults to common race distances)

    Returns:
        str: Pace in MM:SS format per mile, or None if cannot calculate
    """
    if time_ms is None:
        return None

    # If distance not provided, assume common race distances
    # This is a limitation - ideally distance would be provided
    if distance_miles is None:
        # Default to 5K (3.1 miles) - this should be configurable
        distance_miles = 3.1

    total_seconds = time_ms // 1000
    pace_seconds_per_mile = total_seconds / distance_miles

    pace_minutes = int(pace_seconds_per_mile // 60)
    pace_seconds = int(pace_seconds_per_mile % 60)

    return f"{pace_minutes:02d}:{pace_seconds:02d}"


def extract_location_info(location_data):
    """
    Extract city and state from location object.

    Args:
        location_data (dict): Location object from JSON

    Returns:
        tuple: (city, state) strings
    """
    if not location_data:
        return None, None

    # Extract locality (city) and region (state)
    city = location_data.get('locality')
    state = location_data.get('region')

    return city, state

def extract_results(race, file_path, gender=None):
    """
    Extract race results from a file, automatically detecting the file format.

    This function determines the file format based on the file extension and 
    calls the appropriate extraction function. Currently supports PDF and JSON formats.

    Parameters:
        file_path : str
            The full path to the results file to be processed.

    Returns:
        results : object
            The extracted race results data structure. The exact type depends on 
            the implementation of the underlying extraction functions.

    Raises
        Exception
            If the file format is not supported (neither .pdf nor .json).

    """

    if race.results_type == 'pdf':
        results = extract_results_from_pdf(file_path, gender)
    elif race.results_type == 'athlinks':
        results = extract_results_from_athlinks(file_path, gender)
    elif race.results_type == 'raceresult':
        results = extract_results_from_raceresult(file_path, gender)
    elif race.results_type == 'csv':
        results = extract_results_from_csv(file_path, gender)
    else:
        raise Exception(f"Unsupported file format: {race.results_type} for file {file_path}")
    return results

def extract_results_from_raceresult(json_path: str, file_gender = None) -> list[Result]:
    """
    Extract race results from raceresult JSON file and convert to Result objects.

    This method reads a JSON file from raceresult.com and converts each entry 
    to a Result object matching the format used by other parsers.

    Args:
        json_path (str): Path to the JSON file containing race results

    Returns:
        list[Result]: List of Result objects extracted from the JSON data

    Raises:
        FileNotFoundError: If the JSON file cannot be found
        json.JSONDecodeError: If the JSON file is malformed
        KeyError: If required fields are missing from the JSON data
    """
    results = []

    try:
        # Load JSON data from file
        with open(json_path, 'r') as file:
            json_data = json.load(file)

        # Get the data fields mapping and race data
        data_fields = json_data.get('DataFields', [])
        race_data = json_data.get('data', [])

        # Create a mapping from field name to index
        field_mapping = {field: idx for idx, field in enumerate(data_fields)}

        # Process each racer entry
        for entry in race_data:
            try:
                # Extract data using the field mapping
                # Place - remove the period from "1.", "2.", etc.
                place_raw = entry[field_mapping['WithStatus([AUTORANK.p])']]
                place = int(place_raw.rstrip('.')) if place_raw and place_raw != '' else 0

                # Name
                name = entry[field_mapping['FLNAME']] or 'Unknown'

                # Time
                time = entry[field_mapping['Finish.GUN']] or '0:00'

                # Pace
                pace = entry[field_mapping['PACE']] or '0:00'

                # Age - handle empty strings
                age_raw = entry[field_mapping['AGE']]
                age = int(age_raw) if age_raw and age_raw != '' else None

                # gender - not available in raceresult data
                gender = file_gender

                # City and State
                city = entry[field_mapping['CITY']] or ''
                state = entry[field_mapping['STATE2']] or ''

                # Create Result object
                result = Result(place, name, time, pace, age, gender, city, state)
                results.append(result)

            except (KeyError, ValueError, TypeError, IndexError) as e:
                # Log error and continue processing other entries
                print(f"Warning: Skipping racer entry due to error: {e}")
                print(f"Problematic entry: {entry}")
                continue

    except FileNotFoundError:
        print(f"Error: JSON file '{json_path}' not found.")
        raise
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON format in '{json_path}': {e}")
        raise
    except Exception as e:
        print(f"Unexpected error processing JSON file: {e}")
        raise

    return results

def extract_results_from_athlinks(json_path: str, race_distance_miles: float = 3.1, file_gender = None) -> list[Result]:
    """
    Extract race results from JSON file and convert to Result objects.

    This method reads a JSON file containing race data (similar to the athlinks API format)
    and converts each entry to a Result object matching the format used by the PDF parser.

    Args:
        json_path (str): Path to the JSON file containing race results
        race_distance_miles (float): Distance of the race in miles (used for pace calculation)

    Returns:
        list[Result]: List of Result objects extracted from the JSON data

    Raises:
        FileNotFoundError: If the JSON file cannot be found
        json.JSONDecodeError: If the JSON file is malformed
        KeyError: If required fields are missing from the JSON data
    """
    results = []

    try:
        # Load JSON data from file
        with open(json_path, 'r') as file:
            json_data = json.load(file)

        # Handle both single object and array formats
        if isinstance(json_data, dict):
            # If it's a single object, look for results array
            if 'results' in json_data:
                racers = json_data['results']
            else:
                # Assume the object itself contains racer data
                racers = [json_data]
        else:
            # If it's already an array, use it directly
            racers = json_data

        # Process each racer entry
        for racer in racers:
            try:
                # Extract required fields with error handling
                # Overall place from rankings
                place = racer.get('rankings', {}).get('overall', 0)
                if place == 0:
                    place = len(results) + 1  # Fallback to sequential numbering

                # Display name
                name = racer.get('displayName', 'Unknown')

                # Convert chip time from milliseconds to readable format
                race_time_ms = racer.get('chipTimeInMillis')
                time = convert_milliseconds_to_time_string(race_time_ms)

                # Calculate pace per mile
                pace = calculate_pace_from_time(race_time_ms, race_distance_miles)

                # Age (direct from JSON)
                age = racer.get('age', 0)

                # Gender (convert to single character format)
                gender = racer.get('gender', file_gender)  # U for Unknown
                gender = gender[0].upper() if gender else 'U'

                # Extract location information
                location = racer.get('location', {})
                city, state = extract_location_info(location)

                # Create Result object
                result = Result(place, name, time, pace, age, gender, city, state)
                results.append(result)

            except (KeyError, ValueError, TypeError) as e:
                # Log error and continue processing other entries
                print(f"Warning: Skipping racer entry due to error: {e}")
                print(f"Problematic entry: {racer}")
                continue

    except FileNotFoundError:
        print(f"Error: JSON file '{json_path}' not found.")
        raise
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON format in '{json_path}': {e}")
        raise
    except Exception as e:
        print(f"Unexpected error processing JSON file: {e}")
        raise

    return results

def extract_results_from_csv(csv_path: str, file_gender=None) -> list[Result]:
    """
    Extract race results from CSV file and convert to Result objects.

    This method reads a CSV file with race results and converts each entry 
    to a Result object matching the format used by other parsers.

    The CSV format is expected to have sections like "All females" and "All males"
    with columns: Place, (empty), Time, Name, Age, Gender
    Note: Column placement can be inconsistent - place may be in column 0 or 1.

    Args:
        csv_path (str): Path to the CSV file containing race results

    Returns:
        list[Result]: List of Result objects extracted from the CSV data

    Raises:
        FileNotFoundError: If the CSV file cannot be found
        csv.Error: If the CSV file is malformed
    """
    results = []

    try:
        with open(csv_path, 'r', newline='', encoding='utf-8') as file:
            csv_reader = csv.reader(file)

            in_results_section = False
            overall_place = 1  # Track overall place across both gender sections

            for row_num, row in enumerate(csv_reader, 1):
                try:
                    # Skip empty rows
                    if not row or all(cell.strip() == '' for cell in row):
                        continue

                    # Check for section headers
                    first_cell = row[0].strip().lower() if row[0] else ''

                    # Start processing when we hit "All females" or "All males"
                    if first_cell in ['all females', 'all males']:
                        in_results_section = True
                        continue

                    # Stop processing when we hit age group sections
                    if any(keyword in first_cell for keyword in ['female, ages', 'male, ages']):
                        in_results_section = False
                        continue

                    # Skip header rows within sections
                    if 'place' in first_cell and 'time' in ' '.join(row).lower():
                        continue

                    # Only process rows when we're in a results section
                    if not in_results_section:
                        continue

                    # Determine column structure - place can be in column 0 or 1
                    place_col = 0
                    time_col = 2
                    name_col = 3
                    age_col = 4
                    gender_col = 5

                    # Check if place is in column 1 instead (when column 0 is empty)
                    if row[0].strip() == '' and len(row) > 1 and row[1].strip().isdigit():
                        place_col = 1

                    # Ensure we have enough columns
                    if len(row) < 6:
                        continue

                    # Extract place
                    place_str = row[place_col].strip()
                    if not place_str or not place_str.isdigit():
                        continue
                    place = int(place_str)

                    # Extract other fields
                    time = row[time_col].strip() if len(row) > time_col else ''
                    name = row[name_col].strip() if len(row) > name_col else 'Unknown'
                    age_str = row[age_col].strip() if len(row) > age_col else ''
                    gender_str = row[gender_col].strip().lower() if len(row) > gender_col else ''

                    # Validate required fields
                    if not time or not name:
                        continue

                    # Clean up time format (remove trailing .0 if present)
                    if time.endswith('.0'):
                        time = time[:-2]

                    # Parse age
                    age = None
                    if age_str and age_str.isdigit():
                        age = int(age_str)

                    if file_gender is None:
                        # Convert gender to single character
                        if gender_str.startswith('f'):
                            gender = 'F'
                        elif gender_str.startswith('m'):
                            gender = 'M'
                        else:
                            gender = 'U'

                    # Set defaults for missing data (CSV doesn't have pace, city, state)
                    pace = '0:00'  # Default pace since it's not in CSV
                    city = ''      # No city data in CSV
                    state = ''     # No state data in CSV

                    # Use overall place instead of gender-specific place
                    result = Result(overall_place, name, time, pace, age, gender, city, state)
                    results.append(result)
                    overall_place += 1

                except (ValueError, IndexError, AttributeError) as e:
                    # Log error and continue processing other entries
                    print(f"Warning: Skipping row {row_num} due to error: {e}")
                    print(f"Problematic row: {row}")
                    continue

    except FileNotFoundError:
        print(f"Error: CSV file '{csv_path}' not found.")
        raise
    except csv.Error as e:
        print(f"Error: Invalid CSV format in '{csv_path}': {e}")
        raise
    except Exception as e:
        print(f"Unexpected error processing CSV file: {e}")
        raise

    return results


# Extracts results from the PDF, handling multi-word names and cities
def extract_results_from_pdf(pdf_path: str, file_gender) -> list[Result]:
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
                # Place, Name, Time, Pace, Age, gender, City, State

                if word_text.lower() in ["gender", "s", "gender", "m/f"]:
                    new_column.set_name("gender")
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
        gender = get_value(row, columns, 'gender')
        if gender is None:
            gender = file_gender

        # Optional values
        pace = get_value(row, columns, 'pace')
        place = get_value(row, columns, 'place')
        city = get_value(row, columns, 'city')
        state = get_value(row, columns, 'state')


        if time is None or name is None or age is None or gender is None:
            for c in columns:
                print(c.name)
            raise Exception(f"Failed to extract data from {row} in file {pdf_path}")
        # Build result object
        results.append(Result(place, name, time, pace, age, gender, city, state))


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



# Example usage function to demonstrate both PDF and JSON parsing
def main():
    """
    Example usage of both PDF and JSON parsing methods.
    """
    # Example: Parse from PDF
    try:
        pdf_results = extract_results_from_pdf("race_results.pdf")
        print(f"Extracted {len(pdf_results)} results from PDF")
        print_division_rankings(pdf_results)
    except Exception as e:
        print(f"PDF parsing failed: {e}")

    # Example: Parse from JSON
    try:
        json_results = extract_results_from_json("ingest/2025_medcity.json", race_distance_miles=26.2)
        print(f"Extracted {len(json_results)} results from JSON")
        print_division_rankings(json_results)
    except Exception as e:
        print(f"JSON parsing failed: {e}")


if __name__ == "__main__":
    main()

