import yaml
from datetime import datetime, date
from parse import extract_results, Result
from member import Club, Member
from collections import defaultdict
import os
import string

# Define a Race class to organize data neatly
class Race:
    def __init__(self, race_data):
        self.name         = race_data['name']
        if 'male_file' in race_data:
            self.gender_files = True
            self.male_file = race_data['male_file']
            self.female_file = race_data['female_file']
        else:
            self.gender_files = False
            self.file         = race_data['file']

        self.date         = race_data['date']
        self.results_type = race_data['results_type']

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

        # Set race time to midnight to convert to datetime
        date = datetime.combine(race_data.get('date'), datetime.min.time())
        if date > latest_race:
            latest_race = date


        race = Race(race_data)
        races.append(race)

    year = int(data.get('year'))
    return races, year, latest_race

# Modifies results in place to set membership status of each finisher
def process_gp_points(results: list[Result], club: Club, race: Race):
    divisions = defaultdict(list)

    # Establish whether each result corresponds to a member
    for r in results:
        member = club.get_member(r.age, r.name, race.date, threshold=85)
        r.set_membership(member, race.date)
        r.set_division()

        # A particular result can have a null division if their age or gender is not present and can't 
        # be inferred by membership
        if r.division is not None:
            divisions[r.division].append(r)


    for division, group in sorted(divisions.items()):
        group.sort(key=lambda r: r.place)

        for i, runner in enumerate(group, 1):
            if runner.is_member:
                runner.points = max(0, 11 - i)
                runner.division = division
                member = club.get_member(runner.age, runner.name, race.date, threshold=85)
                member.add_result(runner)



def main():
    yaml_file = "/home/joseph/race-results/2025_races.yml" 
    ingest_location = "/home/joseph/race-results/ingest"
    races, year, latest_race_date = load_gp_data(yaml_file)

    club = Club()
    club.load_members()
    
    # Print out the name and file fields
    for race_index, race in enumerate(races):
        results = []
        if race.gender_files:
            male_path = os.path.join(ingest_location, race.male_file)
            female_path = os.path.join(ingest_location, race.female_file)
            male_results = extract_results(race, race_index, male_path, gender='Male')
            female_results = extract_results(race, race_index, female_path, gender='Female')
            results = male_results + female_results

        elif race.file is not None:
            file_path = os.path.join(ingest_location, race.file)
            results = extract_results(race, race_index, file_path)

        process_gp_points(results, club, race)
    
    #club.print_gp_results()
    #club.export_gp_results_to_csv(races, 'gp_results_2025.csv')
    club.generate_gp_results_pdf(races, 'gp_results_2025.pdf')



if __name__ == "__main__":
    main()

