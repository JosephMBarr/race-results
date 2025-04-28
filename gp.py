import yaml
from parse import extract_results_from_pdf, print_division_rankings
import os

# Define a Race class to organize data neatly
class Race:
    def __init__(self, name: str, file: str = None):
        self.name = name
        self.file = file

    def __str__(self):
        return f"Race(name='{self.name}', file='{self.file}')"

def load_races(yaml_path: str):
    races = []

    # Open and read the YAML file
    with open(yaml_path, 'r') as file:
        data = yaml.safe_load(file)

    # Loop through each race entry
    for entry in data.get('races', []):
        race_data = entry.get('race', {})

        # Extract name and file fields
        name = race_data.get('name')
        file_field = race_data.get('file')  # file might not exist

        if name:  # Only create Race if name exists
            race = Race(name=name, file=file_field)
            races.append(race)

    return races

def main():
    yaml_file = "/home/joseph/race-results/2024_races.yml" 
    ingest_location = "/home/joseph/race-results/ingest"
    races = load_races(yaml_file)

    # Print out the name and file fields
    for race in races:
        if race.file is not None:
            results = extract_results_from_pdf(os.path.join(ingest_location, race.file))
            print_division_rankings(results)

if __name__ == "__main__":
    main()

