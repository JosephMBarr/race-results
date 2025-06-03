import yaml
from datetime import datetime, date
from parse import extract_results_from_pdf, print_division_rankings, Result
from member import Club, Member
import os

# TODO: becaues of changes in the signup form, there are some members who signed up for multiple years without any indication 
# in the jotform output. I will have to parse the existing membership spreadsheet on a one-time basis,
# as a "base membership" file
# Define a Race class to organize data neatly
class Race:
    def __init__(self, name: str, file: str = None):
        self.name = name
        self.file = file

    def __str__(self):
        return f"Race(name='{self.name}', file='{self.file}')"

def load_gp_data(yaml_path: str):
    races = []

    # Open and read the YAML file
    with open(yaml_path, 'r') as file:
        data = yaml.safe_load(file)

    latest_race = datetime.min
    # Loop through each race entry
    for entry in data.get('races', []):
        race_data = entry.get('race', {})

        # Extract name and file fields
        name = race_data.get('name')

        # Set race time to midnight to convert to datetime
        date = datetime.combine(race_data.get('date'), datetime.min.time())
        if date > latest_race:
            latest_race = date

        file_field = race_data.get('file')  # file might not exist

        if name:  # Only create Race if name exists
            race = Race(name=name, file=file_field)
            races.append(race)

    year = int(data.get('year'))
    return races, year, latest_race

def process_memberships(results: list[Result], club: Club, year: int, last_race_date: date):
    for r in results:
        member = club.get_member(r.name, year, tolerance=0.85)

        r.set_membership(member, last_race_date)

def main():
    yaml_file = "/home/joseph/race-results/2024_races.yml" 
    ingest_location = "/home/joseph/race-results/ingest"
    races, year, latest_race_date = load_gp_data(yaml_file)

    club = Club()
    club.load_from_csv('/home/joseph/race-results/membership/family.csv', family=True)
    club.load_from_csv('/home/joseph/race-results/membership/ind.csv', family=False)

    # Print out the name and file fields
    for race in races:
        if race.file is not None:
            results = extract_results_from_pdf(os.path.join(ingest_location, race.file))
            process_memberships(results, club, year, latest_race_date)
            print_division_rankings(results)

if __name__ == "__main__":
    main()

