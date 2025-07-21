import csv
import re
from datetime import datetime, date
from difflib import SequenceMatcher
from rapidfuzz import fuzz
import unicodedata
from fuzzyname import Name
import dateparser
from parse import Result
from dateutil.relativedelta import relativedelta
import math

from nicknames import NickNamer, default_lookup

lookup = default_lookup()
lookup["linda"].add("lin")
lookup["belinda"].add("lin")
nick_namer = NickNamer(nickname_lookup=lookup)


def normalize_name(name: str) -> str:
    """
    Normalize name by:
      - lowercasing
      - removing accents and punctuation
      - expanding nicknames using nicknames package
    """
    name = name.lower().strip()
    name = unicodedata.normalize('NFKD', name)
    name = re.sub(r'[^\w\s]', '', name)
    parts = name.split()
    if parts:
        first = parts[0][:3]
        #first = parts[0]


        # Arbitrary, but for consistency, take all possible canonicals and nicknames of a name and take first one
        #versions = nick_namer.canonicals_of(first) | nick_namer.nicknames_of(first)
        #versions.add(first)

        #first = (sorted(versions)[0] if versions else first)
        parts[0] = first
    return " ".join(parts)

female_markers = ['f', 'female']
male_markers = ['m', 'male']
nonbinary_markers = ['n', 'nonbinary', 'nb']
gender_markers = female_markers + male_markers + nonbinary_markers
def normalize_gender_marker(text):
    gender = None
    if text.lower() in male_markers:
        gender = 'm'
    if text.lower() in female_markers:
        gender = 'f'
    if text.lower() in nonbinary_markers:
        gender = 'n'
    return gender

class Member:
    """
    Represents a club member with relevant membership details.
    """
    def __init__(self, submission_date_str, first_name, last_name, birth_date,
                 gender, products_str, start_year=None, end_year=None):
        # Parse submission date
        self.submission_date = datetime.strptime(submission_date_str, '%m-%d-%Y %H:%M:%S')

        # Hyphen might sneak in at the end
        self.first_name = first_name
        self.last_name   = last_name
        self.name        = normalize_name(f'{first_name} {last_name}'.rstrip('-'))
        self.birth_date  = birth_date
        if gender:
            self.gender  = normalize_gender_marker(gender)
        else:
            self.gender = None
        self.products = products_str
        self.active   = False

        # Determine start year: if submitted in Nov (11) or later, start next calendar year
        if start_year is None:
            year = self.submission_date.year
            if self.submission_date.month >= 11:
                year += 1
            self.start_year = year
        else:
            self.start_year = start_year

        product_phrases = ["Renew 1 Year", "New Individual", "New Family"]

        if end_year is None:
            # Count the number of phrases in the product string. Each indicating a year paid.
            years_paid = sum(1 for phrase in product_phrases if phrase in products_str)

            # Check for "Special Quantity: <number>" to extend membership
            match = re.search(r"Special Quantity:\s*(\d+)", products_str)
            if match:
                years_paid += int(match.group(1))

            self.end_year = self.start_year - 1 + years_paid
        else:
            self.end_year = end_year

        self.results = []

        self.set_division()
        self.set_active_status()

    def set_active_status(self):
        year = datetime.now().year
        if self.start_year <= year <= self.end_year:
            self.active = True
        else:
            self.active = False

    def add_result(self, result: Result):
        self.results.append(result)

    def display(self):
        """
        Prints the member's details to the console.
        """
        print(f"Member: {self.name}")
        print(f"  Submission Date: {self.submission_date.date()}")
        print(f"  Birth Date: {self.birth_date}")
        print(f"  Gender: {self.gender}")
        print(f"  Products: {self.products}")
        print(f"  Membership Start Year: {self.start_year}")
        print(f"  Membership End Year: {self.end_year}\n")

    def set_division(self):
        # Division spans a decade except for <19
        age = relativedelta(date.today(), self.birth_date).years
        if 'unkin' in self.last_name:
            print('aaaaa')
            print(self.gender)
            print(age)
        if self.gender is None:
            self.division = None
            return

        if age > 19:
            # Division is formatted like M2029 (males 20-29)
            decade = math.floor(age / 10) * 10
            self.division = f"{self.gender.upper()}{decade}{decade+9}"
        else:
            self.division = f"{self.gender.upper()}0119"
        print(self.division)

class Club:
    """
    Manages a collection of Member instances and provides lookup functionality.
    """
    def __init__(self):
        self.members = {}


    def merge_members(self, other_members, threshold=85):
        """
        Merges members from another dict into self.members using fuzzy name matching.
        Updates missing gender and birth_date fields where applicable.

        Parameters:
            other_members (dict): Mapping from raw name to Member object.
            threshold (int): Similarity threshold (0–100) for considering two names the same.
        """
        unmatched = []

        for other in other_members.values():
            if not other.name:
                continue

            best_match_key = None
            best_score = 0

            # Try to find a close-enough match in current members
            for memb_name in self.members:
                score = fuzz.token_sort_ratio(other.name, memb_name)
                # TODO: keep playing around with this line case-by-case and knock out edge cases
                # There is definitely going to have to be some manual intervention. e.g. lin is not
                # registered as a nickname of Linda, but she's in as Linda on the base csv
                niq = 'scott'
                if niq in other.name and niq in memb_name:
                    print('aaaaaa')
                    print(score)
                    print(other.name, memb_name)
                if score > best_score and score >= threshold:
                    best_score = score
                    best_match_key = memb_name

            if best_match_key:
                match = self.members[best_match_key]

                # Fill in missing info if possible
                if not match.gender and other.gender:
                    match.gender = other.gender
                if not match.birth_date and other.birth_date:
                    match.birth_date = other.birth_date
                    match.set_division()

            else:
                # Add as new member only if membership is still current
                if other.end_year >= date.today().year:
                    unmatched.append(other.name)
                self.members[other.name] = other

        if unmatched:
            print(f'Unmatched: {unmatched}')

    def load_base_csv(self, filepath):
        """
        Reads a base CSV with columns: First name, Last name, Expires, and optional Birthdate.
        Handles entries with multiple first/last names separated by '&' indicating multiple members.
        """
        current_year = date.today().year
        with open(filepath, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                raw_first = row['First name']
                raw_last = row['Last name']
                expires = row['Expires']
                birthdate = dateparser.parse(row.get('Birthdate', ''))

                # Determine end year from Expires date
                exp_date = dateparser.parse(expires)
                if exp_date is not None:
                    end_year = exp_date.year
                else:
                    raise ValueError(f"Invalid Expires date format: {expires}")

                # Normalize and split first and last names
                split_delims = re.compile(r'\s*(?:&|,)\s*')
                first_names = split_delims.split(raw_first)
                last_names = split_delims.split(raw_last)
                if len(last_names) == 1:
                    last_names = last_names * len(first_names)
                if len(first_names) != len(last_names):
                    raise ValueError(f"Unmatched first and last names: {raw_first} / {raw_last}")

                for fn, ln in zip(first_names, last_names):
                    m = Member(
                        submission_date_str=f"01-01-{current_year} 00:00:00",
                        first_name=fn,
                        last_name=ln,
                        birth_date=birthdate,
                        gender='',
                        products_str='',
                        start_year = current_year,
                        end_year = end_year,
                    )
                    self.members[m.name] = m



    def load_from_csv(self, filepath, family=False, only_active=True):
        """
        Reads a CSV file (individual or family format), parses relevant columns,
        and stores Member instances. Use family=True for family files.
        """
        loaded_members = {}
        current_year = date.today().year
        with open(filepath, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Base fields
                products_key = 'My Products: Products' if not family else 'Please select at least one:: Products'
                base_products = row.get(products_key, '')
                first_name = row['First Name']
                last_name  = row['Last Name']
                # Primary member
                primary = Member(
                    submission_date_str=row['Submission Date'],
                    first_name=first_name,
                    last_name=last_name,
                    birth_date=dateparser.parse(row['Birth Date']),
                    gender=row['Gender'],
                    products_str=base_products
                )
                # Try and filter out null entries
                if len(primary.name.strip()) > 0:
                    if not only_active or (only_active and primary.end_year >= current_year):
                        loaded_members[primary.name] = primary

                # If family signup, parse additional family members
                if family:
                    family_name = row['Last Name']
                    # Identify family member columns
                    fam_keys = [k for k in row.keys() if re.match(r'(Additional Family Member|Family Member)', k)]
                    for key in fam_keys:
                        val = row.get(key, '').strip()
                        if not val:
                            continue
                        #for member_info in re.split(r';|\|', val):  # split multiple in one field
                        for member_info in re.split(r';|\||\r\n?|\n', val):
                            try:
                                parsed = self._parse_family_member(member_info, family_name)
                            except:
                                print(f'Failed to parse out a family member from {member_info}')
                                continue
                            if parsed:
                                first_name, last_name, bd, gen = parsed
                                m = Member(
                                    submission_date_str=row['Submission Date'],
                                    first_name=first_name,
                                    last_name=last_name,
                                    birth_date=bd,
                                    gender=gen,
                                    products_str=base_products
                                )
                                if not only_active or (only_active and primary.end_year >= current_year) and len(m.name.strip()) > 0:

                                    # If this person had a previous entry, try and grab attributes they might have missed in this newest signup
                                    if m.name in loaded_members:
                                        if m.gender is None:
                                            m.gender = loaded_members[m.name].gender
                                        if m.birth_date is None:
                                            m.birth_date = loaded_members[m.name].birth_date

                                    loaded_members[m.name] = m
        return loaded_members
    def _parse_family_member(self, s, family_name):
        """
        Attempts to extract first name, last name, birth date, and gender from a string.
        Expected separators: commas, slashes, or spaces.
        Formats supported for birth date: 'Month DD YYYY', 'MM-DD-YYYY', 'YYYY-MM-DD'.

        Returns a tuple (name, birth_date, gender) or None.
        """
        #parts = re.split(r'[,/\\]+', s)

        parts = re.split(r'[\s,\\/]+', s)
        parts = [p.strip() for p in parts if p.strip()]

        # Easiest to determine is sex. Find it and take it out
        gender = None
        gender_idx = -1
        for idx, p in enumerate(parts):
            if p.lower() in gender_markers:
                gender_idx = idx
                gender = normalize_gender_marker(p)

        if gender is not None:
            del parts[gender_idx]

        # Next easiest is date of birth. This is most reliably indicated by seeing two straight numbers.
        year = None
        month = None
        day = None
        is_numeric = lambda s: s.isdigit()
        for idx, p in enumerate(parts):
            if is_numeric(p):
                # If this is the first and only number, it must be the year. Assume birthday is January 1st
                if idx == len(parts) - 1:
                    year = parts[idx]
                    month = '01'
                    day = '01'
                    break

                elif is_numeric(parts[idx + 1]):
                    # Two straight numbers. Must be in a date
                    if len(parts) > idx + 2 and is_numeric(parts[idx + 2]):
                        # Third straight number, must be a year
                        year = parts[idx + 2]
                        month = parts[idx + 1]
                        day = parts[idx]
                    else:
                        # Second number was the last number and hence the year
                        year = parts[idx + 1]
                        # Presumably of format %B %d %Y
                        month = parts[idx - 1]
                        day = parts[idx]
                    break
                        
        if year in parts:
            parts.remove(year)
        if month in parts:
            parts.remove(month)
        if day in parts:
            parts.remove(day)

        # Clean up 
        parts = [p for p in parts if p not in ['-', ':', '&', 'DOB']]
        
        # In theory should just be name now
        if len(parts) == 1:
            # add family name
            parts.append(family_name)

        # Sometimes Transaction ID: can get in there
        name = ' '.join(parts).split('Transaction ID')[0]

        # Sometimes people include their emails too
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
        name = re.sub(email_pattern, '', name)

        # Clean up extra whitespace that might be left behind
        name = re.sub(r'\s+', ' ', name).strip()
        whole_name = name.split(' ')

        first_name = whole_name[0]
        last_name  = whole_name[1]

        if year is None or month is None or day is None:
            dob_date = None
        else:
            dob = '/'.join([month, day, year])
            # Normalize DOB to 'Month DD YYYY'
            dob_date = dateparser.parse(dob)
        return first_name, last_name, dob_date, gender

    def display_all(self):
        """
        Displays all members in the club.
        """
        for member in self.members.values():
            member.display()


    def get_member(self, name: str, threshold=80):
        """
        Checks if a name (fuzzy matching) corresponds to an active member.

        Parameters:
            name (str): The full name to check, e.g., "Jane Doe".
            tolerance (float): Fuzzy match threshold between 0 and 1.

        Returns:
            bool: True if an active member matches the name within tolerance.
        """
        norm_input = normalize_name(name)
        for norm_name, member in self.members.items():
            score = fuzz.token_sort_ratio(norm_input, norm_name)
            if score >= threshold:
                return member
        return None

    def load_members(self):
        self.load_base_csv('/home/joseph/race-results/membership/base.csv')
        families = self.load_from_csv('/home/joseph/race-results/membership/family.csv', family=True, only_active=False)
        individuals = self.load_from_csv('/home/joseph/race-results/membership/ind.csv', family=False, only_active=False)

        ind_and_families = {**individuals, **families}

        self.merge_members(ind_and_families)

    def print_gp_results(self):
        """
        Print Grand Prix results organized by age/gender divisions.
        """
        # Create divisions dictionary to group members
        divisions = {}

        for member_name in self.members.keys():
            member = self.members[member_name]
            if hasattr(member, 'results') and member.results:

                if member.division is None:
                    continue

                # Calculate total points for this member
                total_points = sum(result.points for result in member.results)

                division_key = member.division 

                if division_key not in divisions:
                    divisions[division_key] = []

                divisions[division_key].append({
                    'name': f"{member.first_name} {member.last_name}",
                    'points': total_points,
                    'race_count': len(member.results)
                })


        for division in sorted(divisions.keys()):
            print(f"\n=== {division} Division ===")
            print("-" * 50)

            # Sort by points (descending), then by race count (descending) as tiebreaker
            sorted_members = sorted(divisions[division], 
                                  key=lambda x: (-x['points'], -x['race_count']))

            print(f"{'Rank':<4} {'Name':<25} {'Points':<8} {'Races':<6}")
            print("-" * 50)

            for i, member in enumerate(sorted_members, 1):
                print(f"{i:<4} {member['name']:<25} {member['points']:<8} {member['race_count']:<6}")

        print("\n" + "="*60)



if __name__ == '__main__':
    # TODO: may need to do membership expiration validation on the backend, I just changed only_active to False because 
    # it was failing to merge with very old jotform submissions with no indication of expiration with those from Anna's spreadsheet

    # Example usage:
    club = Club()

    club.load_members()


    #club.display_all()

    # Check membership status for a name
    name_to_check = input("Enter full name to verify membership: ")
    member = club.get_member(name_to_check, threshold=85)
    if member is not None and member.active:
        print(f"{member.name} is an active member until {member.end_year}.")
    else:
        print(f"{name_to_check} is not an active member.")

