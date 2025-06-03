import csv
import re
from datetime import datetime, date
from difflib import SequenceMatcher
from collections import defaultdict
import calendar
from fuzzyname import Name


class Member:
    """
    Represents a club member with relevant membership details.
    """
    def __init__(self, submission_date_str, name, birth_date_str,
                 gender, products_str):
        # Parse submission date
        self.submission_date = datetime.strptime(submission_date_str, '%m-%d-%Y %H:%M:%S')

        # Hyphen might sneak in at the end
        self.name = name.rstrip('-')
        # Parse birth date. Some people skip this or don't provide a year
        try:
            self.birth_date = datetime.strptime(birth_date_str, '%B %d %Y').date()
        except:
            self.birth_date = None
        self.gender = gender
        self.products = products_str

        # Determine start year: if submitted in Nov (11) or later, start next calendar year
        year = self.submission_date.year
        if self.submission_date.month >= 11:
            year += 1
        self.start_year = year

        product_phrases = ["Renew 1 Year", "New Individual", "New Family"]

        # Count the number of phrases in the product string. Each indicating a year paid.
        years_paid = sum(1 for phrase in product_phrases if phrase in products_str)


        # Check for "Special Quantity: <number>" to extend membership
        match = re.search(r"Special Quantity:\s*(\d+)", products_str)
        if match:
            years_paid += int(match.group(1))

        self.end_year = self.start_year - 1 + years_paid

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

class Club:
    """
    Manages a collection of Member instances and provides lookup functionality.
    """
    female_markers = ['f', 'female']
    male_markers = ['m', 'male']
    nonbinary_markers = ['n', 'nonbinary', 'nb']
    gender_markers = female_markers + male_markers + nonbinary_markers
    def __init__(self):
        self.members = []

    def normalize_gender_marker(self, text):
        gender = None
        if text.lower() in self.male_markers:
            gender = 'm'
        if text.lower() in self.female_markers:
            gender = 'f'
        if text.lower() in self.nonbinary_markers:
            gender = 'n'
        return gender

    def merge_members(self, other_members, tolerance=0.85):
        """
        Merges members from another list into self.members using fuzzy name matching and exact year match.
        Updates missing gender and birth_date fields.
        Raises ValueError if any member in other_members has no close match in self.members.
        """
        unmatched = []
        for other in other_members:
            best_match = None
            other.display()
            for self_m in self.members:
                if Name(self_m.name) == Name(other.name):
                    best_match = self_m
                    break
            if best_match:
                if not best_match.gender and other.gender:
                    best_match.gender = other.gender
                if not best_match.birth_date and other.birth_date:
                    best_match.birth_date = other.birth_date
            else:
                # Don't report if membership is lapsed
                if other.end_year >= date.today().year:
                    unmatched.append(other.name)
        if len(unmatched) > 0:
            raise Exception(f'Unmatched: {unmatched}')


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
                birthdate = row.get('Birthdate', '')

                # Determine end year from Expires date
                try:
                    exp_date = datetime.strptime(expires, '%m/%d/%Y')
                    end_year = exp_date.year
                except ValueError:
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
                    name = f"{fn} {ln}"
                    m = Member(
                        submission_date_str=f"01-01-{current_year} 00:00:00",
                        name=name,
                        birth_date_str=birthdate,
                        gender='',
                        products_str=''
                    )
                    m.start_year = current_year
                    m.end_year = end_year
                    self.members.append(m)
                    m.display()



    def load_from_csv(self, filepath, family=False, only_active=True):
        """
        Reads a CSV file (individual or family format), parses relevant columns,
        and stores Member instances. Use family=True for family files.
        """
        loaded_members = []
        current_year = date.today().year
        with open(filepath, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Base fields
                products_key = 'My Products: Products' if not family else 'Please select at least one:: Products'
                base_products = row.get(products_key, '')
                primary_name = f"{row['First Name']} {row['Last Name']}"
                # Primary member
                primary = Member(
                    submission_date_str=row['Submission Date'],
                    name=primary_name,
                    birth_date_str=row['Birth Date'],
                    gender=row['Gender'],
                    products_str=base_products
                )
                # Try and filter out null entries
                if len(primary_name.strip()) > 0:
                    if not only_active or (only_active and primary.end_year >= current_year):
                        loaded_members.append(primary)

                # If family signup, parse additional family members
                if family:
                    family_name = row['Last Name']
                    # Identify family member columns
                    fam_keys = [k for k in row.keys() if re.match(r'(Additional Family Member|Family Member)', k)]
                    for key in fam_keys:
                        val = row.get(key, '').strip()
                        if not val:
                            continue
                        for member_info in re.split(r';|\|', val):  # split multiple in one field
                            parsed = self._parse_family_member(member_info, family_name)
                            if parsed:
                                name, bd, gen = parsed
                                m = Member(
                                    submission_date_str=row['Submission Date'],
                                    name=name,
                                    birth_date_str=bd,
                                    gender=gen,
                                    products_str=base_products
                                )
                                if not only_active or (only_active and primary.end_year >= current_year) and len(name.strip()) > 0:
                                    loaded_members.append(m)
        return loaded_members
    def _parse_family_member(self, s, family_name):
        """
        Attempts to extract first name, last name, birth date, and gender from a string.
        Expected separators: commas, slashes, or spaces.
        Formats supported for birth date: 'Month DD YYYY', 'MM-DD-YYYY', 'YYYY-MM-DD'.

        Returns a tuple (name, birth_date_str, gender) or None.
        """
        #parts = re.split(r'[,/\\]+', s)

        parts = re.split(r'[\s,\\/]+', s)
        parts = [p.strip() for p in parts if p.strip()]

        # Easiest to determine is sex. Find it and take it out
        gender = None
        gender_idx = -1
        for idx, p in enumerate(parts):
            if p.lower() in self.gender_markers:
                gender_idx = idx
                gender = self.normalize_gender_marker(p)

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
        name = ' '.join(parts)
        if year is None or month is None or day is None:
            dob = None
            dob_str = ''
        else:
            dob = '/'.join([month, day, year])
            # Normalize DOB to 'Month DD YYYY'
            for fmt in ['%m/%d/%Y','%B/%d/%Y', '%d/%m/%Y']:
                try:
                    dt = datetime.strptime(dob, fmt)
                    dob_str = dt.strftime('%B %d %Y')
                    break
                except ValueError:
                    continue
            else:
                dob_str = ''
        return name, dob_str, gender
    def display_all(self):
        """
        Displays all members in the club.
        """
        for member in self.members:
            member.display()


    def get_member(self, name: str, year: int, tolerance=0.8):
        """
        Checks if a name (fuzzy matching) corresponds to an active member.

        Parameters:
            name (str): The full name to check, e.g., "Jane Doe".
            year (int): The year for which to check activity of membership
            tolerance (float): Fuzzy match threshold between 0 and 1.

        Returns:
            bool: True if an active member matches the name within tolerance.
        """
        today_year = date.today().year
        for member in self.members:
            ratio = SequenceMatcher(None, name.lower(), member.name.lower()).ratio()
            # If name matches and membership is active for year
            if ratio >= tolerance and member.start_year <= year <= member.end_year:
                return member
        return None

if __name__ == '__main__':
    # Example usage:
    club = Club()
    club.load_base_csv('/home/joseph/race-results/membership/base.csv')
    families = club.load_from_csv('/home/joseph/race-results/membership/family.csv', family=True, only_active=True)
    individuals = club.load_from_csv('/home/joseph/race-results/membership/ind.csv', family=False, only_active=True)

    individuals += families

    club.merge_members(individuals)


    print("All Members:\n")
    club.display_all()

    # Check membership status for a name
    name_to_check = input("Enter full name to verify membership: ")
    member = club.get_member(name_to_check, tolerance=0.85)
    if member is not None:
        print(f"{member.name} is an active member until {member.end_year}.")
    else:
        print(f"{name_to_check} is not an active member.")

