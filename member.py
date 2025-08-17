import csv
import re
import os
from datetime import datetime, date
from difflib import SequenceMatcher
from rapidfuzz import fuzz
import unicodedata
from fuzzyname import Name
import dateparser
from parse import Result
from dateutil.relativedelta import relativedelta
import math
import requests
from dotenv import load_dotenv
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import ListedColormap
import numpy as np
from datetime import datetime

from nicknames import NickNamer, default_lookup

lookup = default_lookup()
lookup["linda"].add("lin")
lookup["belinda"].add("lin")
nick_namer = NickNamer(nickname_lookup=lookup)

def process_race_name(name, max_width=15):
   words = name.split()
   lines = []
   current_line = ""

   for word in words:
       # If adding the next word would exceed the limit
       if len(current_line) + len(word) + (1 if current_line else 0) > max_width:
           if current_line:
               lines.append(current_line)
               current_line = word
           else:
               # Handle case where a single word exceeds max_width (e.g., very long word)
               # This keeps the word intact, though it exceeds the limit
               lines.append(word)
       else:
           if current_line:
               current_line += " " + word
           else:
               current_line = word

   # Add the last line if non-empty
   if current_line:
       lines.append(current_line)

   return '\n'.join(lines)

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
        first = parts[0][:4]
        #first = parts[0]


        # Arbitrary, but for consistency, take all possible canonicals and nicknames of a name and take first one
        #versions = nick_namer.canonicals_of(first) | nick_namer.nicknames_of(first)
        #versions.add(first)

        #first = (sorted(versions)[0] if versions else first)
        parts[0] = first
    return " ".join(parts)


female_markers = ['f', 'female']
male_markers = ['m', 'male']
nonbinary_markers = ['n', 'nonbinary', 'nb', 'non-binary']
gender_markers = female_markers + male_markers + nonbinary_markers

def normalize_gender_marker(text):
    if not text:
        return None
    gender = None
    text_lower = text.lower().strip()
    if text_lower in male_markers:
        gender = 'Male'
    elif text_lower in female_markers:
        gender = 'Female'
    elif text_lower in nonbinary_markers:
        gender = 'Non-Binary'
    return gender

def parse_airtable_date(date_string):
    """Parse common Airtable date formats"""
    formats = [
        "%Y-%m-%d %H:%M:%S",  # Full datetime
        "%Y-%m-%d",           # Date only
        "%m/%d/%Y",           # US format
        "%m-%d-%Y"            # Alternative format
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_string.strip(), fmt)
        except ValueError:
            continue

    raise ValueError(f"Unable to parse date: {date_string}")


class Member:
    """
    Represents a club member with relevant membership details.
    """
    def __init__(self, submission_date_str, first_name, last_name, birth_date,
                 gender, products_str, email=None, address=None, phone=None, 
                 start_year=None, end_year=None):
        # Parse submission date
        self.submission_date = parse_airtable_date(submission_date_str)

        # Basic member info
        self.first_name = first_name
        self.last_name = last_name
        self.name = normalize_name(f'{first_name} {last_name}'.rstrip('-'))
        self.birth_date = birth_date

        self.email = email
        self.address = address
        self.phone = phone

        if gender:
            self.gender = normalize_gender_marker(gender)
        else:
            self.gender = None
        self.products = products_str
        self.active = False

        # Determine start year: if submitted in Nov (11) or later, start next calendar year
        if start_year is None:
            year = self.submission_date.year
            if self.submission_date.month >= 9:
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
                niq = 'abdullahi'
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

                    match.email = other.email
                    match.address = other.address
                    match.phone = other.phone


                    # Handle products field
                    if other.products and len(other.products.strip()) > 0:
                        match.products = other.products
                    elif not match.products:
                        # Reverse engineer products if both match and other don't have it
                        submission_year = other.submission_date.year
                        end_year = match.end_year

                        products_parts = ["1 Year"]

                        if end_year != submission_year:
                            year_difference = end_year - submission_year
                            if year_difference > 0:
                                products_parts.append(f"Special Quantity: {year_difference}")

                        match.products = ", ".join(products_parts)

                    match.submission_date = other.submission_date
                    break


            else:
                # Add as new member only if membership is still current
                if other.end_year >= date.today().year:
                    unmatched.append(other.name)
                self.members[other.name] = other
                if 'feda' in other.name.lower():
                    print('qqqqq')
                    print(other.products)

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
        Handles uniqueness by email, keeping most recent submission.
        """
        loaded_members = {}
        email_to_member = {}  # Track members by email for uniqueness
        current_year = date.today().year

        with open(filepath, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Extract submission date for comparison
                submission_date_str = row['Submission Date']
                submission_date = datetime.strptime(submission_date_str, '%m-%d-%Y %H:%M:%S')

                # Extract email
                email = row.get('E-mail', '').strip()
                if not email:
                    continue  # Skip entries without email

                # Check if we already have a member with this email
                if email in email_to_member:
                    existing_member = email_to_member[email]
                    if submission_date <= existing_member.submission_date:
                        continue  # Skip this entry as we have a more recent one
                    else:
                        # Remove the older entry
                        if existing_member.name in loaded_members:
                            del loaded_members[existing_member.name]

                # Concatenate address fields
                address_parts = [
                    row.get('Street Address', '').strip(),
                    row.get('Street Address Line 2', '').strip(),
                    row.get('City', '').strip(),
                    row.get('State / Province', '').strip(),
                    row.get('Postal / Zip Code', '').strip(),
                    row.get('Country', '').strip()
                ]
                address = ', '.join([part for part in address_parts if part])

                # Extract phone number
                phone = row.get('Phone Number', '').strip()

                # Base fields
                products_key = 'My Products: Products' if not family else 'Please select at least one:: Products'
                base_products = row.get(products_key, '')
                first_name = row['First Name']
                last_name = row['Last Name']

                # Primary member
                primary = Member(
                    submission_date_str=submission_date_str,
                    first_name=first_name,
                    last_name=last_name,
                    birth_date=dateparser.parse(row['Birth Date']),
                    gender=row['Gender'],
                    products_str=base_products,
                    email=email,
                    address=address,
                    phone=phone
                )


                # Try and filter out null entries
                if len(primary.name.strip()) > 0:
                    if not only_active or (only_active and primary.end_year >= current_year):
                        if "barr" in primary.name.lower():
                            print("ooooooo")
                            primary.display()
                            print(primary.email)
                        loaded_members[primary.name] = primary
                        email_to_member[email] = primary

                # If family signup, parse additional family members
                if family:
                    family_name = row['Last Name']
                    # Identify family member columns
                    fam_keys = [k for k in row.keys() if re.match(r'(Additional Family Member|Family Member)', k)]
                    for key in fam_keys:
                        val = row.get(key, '').strip()
                        if not val:
                            continue
                        for member_info in re.split(r';|\||\r\n?|\n', val):
                            try:
                                parsed = self._parse_family_member(member_info, family_name)
                            except:
                                print(f'Failed to parse out a family member from {member_info}')
                                continue
                            if parsed:
                                first_name, last_name, bd, gen = parsed
                                if "delone" in last_name.lower():
                                    print('hello')
                                    print(email)
                                    print(first_name, last_name)
                                m = Member(
                                    submission_date_str=submission_date_str,
                                    first_name=first_name,
                                    last_name=last_name,
                                    birth_date=bd,
                                    gender=gen,
                                    products_str=base_products,
                                    email=email,  # Family members share same email
                                    address=address,  # Family members share same address
                                    phone=phone  # Family members share same phone
                                )
                                if not only_active or (only_active and primary.end_year >= current_year) and len(m.name.strip()) > 0:
                                    # If this person had a previous entry, try and grab attributes they might have missed
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

    def get_member(self, age: int, name: str, race_date=None, threshold=80):
        """
        Checks if a name (fuzzy matching) corresponds to an active member.

        Parameters:
            name (str): The full name to check, e.g., "Jane Doe".
            age (int): age of the result's person
            race_date (date): date of the race. If None, will use current date.
            threshold (float): Fuzzy match threshold between 0 and 100.

        Returns:
            Member: Best matching member above threshold, or None if no match.
        """
        norm_input = normalize_name(name)
        best_match = None
        best_score = threshold - 1  # Ensure we only return matches above threshold

        if race_date is None:
            race_date = date.today()

        for norm_name, member in self.members.items():
            score = fuzz.token_sort_ratio(norm_input, norm_name)
            if score >= threshold:
                # Skip age check if age is None
                if age is not None:
                    member_age = relativedelta(race_date, member.birth_date).years
                    if abs(member_age - age) > 1:
                        continue

                # Update best match if this score is higher
                if score > best_score:
                    best_score = score
                    best_match = member

        return best_match



    def load_members(self):
        load_dotenv()
        base_id = os.getenv('AIRTABLE_BASE_ID')
        self.load_members_from_airtable(base_id, "Table 1", "Active Members")

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

                # Calculate total points for this member (top 5 results only)
                total_points = sum(result.points for result in sorted(member.results, key=lambda r: r.points, reverse=True)[:5])


                division_key = member.division 

                if division_key not in divisions:
                    divisions[division_key] = []

                divisions[division_key].append({
                    'name': f"{member.first_name} {member.last_name}",
                    'points': total_points,
                    'race_count': len(member.results)
                })
                if len(member.results) > 1:
                    print(member.results[0].time, member.results[1].time)


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

    def _process_division_data(self, races):
        divisions = {}
        for member_name in self.members.keys():
            member = self.members[member_name]
            if hasattr(member, 'results') and member.results:
                if member.division is None:
                    continue

                # Calculate member statistics
                total_points = sum(result.points for result in member.results)
                total_races = len(member.results)
                total_best_5 = sum(result.points for result in sorted(member.results, key=lambda r: r.points, reverse=True)[:5])

                # Create race results array ordered by race_index
                race_results = [''] * len(races)  # Initialize with empty strings
                for result in member.results:
                    if result.race_index is not None and result.race_index < len(race_results):
                        race_results[result.race_index] = result.points

                # Group by division
                if member.division not in divisions:
                    divisions[member.division] = []

                divisions[member.division].append({
                    'name': f"{member.first_name} {member.last_name}",
                    'race_results': race_results,
                    'total_points': total_points,
                    'total_races': total_races,
                    'total_best_5': total_best_5
                })

        # Sort members within each division and assign places
        for division in divisions:
            # Sort by total_best_5 descending (highest to lowest)
            divisions[division].sort(key=lambda x: x['total_best_5'], reverse=True)

            # Assign places with ties allowed
            current_place = 1
            for i, member_data in enumerate(divisions[division]):
                if i > 0 and divisions[division][i-1]['total_best_5'] != member_data['total_best_5']:
                    current_place = i + 1
                member_data['place'] = current_place

        return divisions

    def export_gp_results_to_csv(self, races, filename):
        """
        Export Grand Prix results to CSV format with race columns and division sections.

        Args:
            races: List of Race objects (for column headers and ordering)
            filename: Output CSV filename
        """
        # Create divisions dictionary to group members
        divisions = self._process_division_data(races)


        # Write to CSV file
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)

            # Create header row
            header = ['Name']
            for i in range(len(races)):
                header.append(f'{races[i].name}')
            header.extend(['Total Points', 'Total Races', 'Total Best 5', 'Place'])

            writer.writerow(header)
            # Process each division with section headers
            for division_name in sorted(divisions.keys()):
                # Write division header
                division_name_clean = self._format_division_name(division_name.upper())
                writer.writerow([f'{division_name_clean}'])

                # Write member data for this division
                for member_data in divisions[division_name]:
                    row = [member_data['name']]
                    row.extend([str(points) if points != '' else '' for points in member_data['race_results']])
                    row.extend([
                        member_data['total_points'],
                        member_data['total_races'], 
                        member_data['total_best_5'],
                        member_data['place']
                    ])
                    writer.writerow(row)

                # Add empty row between divisions for readability
                writer.writerow([])

    def _format_division_name(self, division_name):
        """
        Format division name for display (e.g., 'FEMALE2029' -> 'Female 20-29')
        """
        if not division_name:
            return "Unknown Division"

        # Extract gender and age range
        if division_name.startswith('FEMALE'):
            gender = 'Female'
            age_part = division_name[6:]
        elif division_name.startswith('MALE'):
            gender = 'Male'
            age_part = division_name[4:]
        else:
            return division_name

        # Format age range
        if len(age_part) == 4:
            start_age = age_part[:2]
            end_age = age_part[2:]
            return f"{gender} {start_age}-{end_age}"
        else:
            return f"{gender} {age_part}"

    def write_members_to_csv(self, filepath):
        """
        Writes all members to a CSV file with specified columns.

        Parameters:
            filepath (str): Path where the CSV file will be written.
        """
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['Email', 'Last Name', 'First Name', 'Birthday', 'Gender', 
                          'Mailing Address', 'Phone', 'Products', 'Submission Date']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()

            for member in self.members.values():
                # Format dates as YYYY-MM-DD
                birthday_str = member.birth_date.strftime('%Y-%m-%d') if member.birth_date else ''
                submission_date_str = member.submission_date.strftime('%Y-%m-%d') if member.submission_date else ''

                writer.writerow({
                    'Email': member.email or '',
                    'Last Name': member.last_name or '',
                    'First Name': member.first_name or '',
                    'Birthday': birthday_str,
                    'Gender': member.gender or '',
                    'Mailing Address': member.address or '',
                    'Phone': member.phone or '',
                    'Products': member.products or '',
                    'Submission Date': submission_date_str
                })

            print(f"Successfully wrote {len(self.members)} members to {filepath}")

    def generate_gp_results_pdf(self, races, filename):
        """
        Enhanced version with better handling of multiple divisions and improved layout
        """
        # Prepare data (same as above)
        divisions = self._prepare_division_data(races)

        # Calculate dynamic figure height based on actual content
        total_height_units = 0
        division_data = {}

        total_members = 0
        # Pre-calculate table sizes for dynamic figure sizing
        for division_name in divisions:
            members = divisions[division_name]
            num_data_rows = len(members)
            total_members += len(members)
            table_height_units = 10 + (num_data_rows * 4)  # header + data rows
            division_data[division_name] = {
                'members': members,
                'height_units': table_height_units
            }
            total_height_units += table_height_units

        # Create subplots with dynamic height based on content
        num_divisions = len(divisions)
        base_height_per_unit = 0.1  # Increased from previous base_scale
        # Reduce the base height and padding
        total_fig_height = max(8, total_height_units * base_height_per_unit + 2)





        # More accurate height ratios based on actual content
        height_ratios = [max(0.3, len(divisions[division_name]) * 0.12) + 0.35
                for division_name in sorted(divisions.keys())]



        fig, axes = plt.subplots(num_divisions, 1, 
                               height_ratios=height_ratios,
                               figsize=(16, total_fig_height),
                               gridspec_kw={'hspace': 0.3})  # Reduced hspace since we have more control

        # Handle single division case
        if num_divisions == 1:
            axes = [axes]

        # Title
        current_year = datetime.now().year
        fig.suptitle(f'RRC Grand Prix {current_year}', fontsize=24, fontweight='bold', y=0.95)
        # Add top margin control
        plt.subplots_adjust(top=0.93)  # Brings subplots closer to title

        # Medal colors
        medal_colors = {1: '#FFD700', 2: '#C0C0C0', 3: '#CD7F32'}

        # Define consistent row heights for uniform appearance
        header_height_units = 10
        race_header_height_units = 25
        data_row_height_units = 4

        prev_table_height = 0
        for idx, division_name in enumerate(sorted(divisions.keys())):
            ax = axes[idx]
            ax.axis('off')

            members = division_data[division_name]['members']
            table_height_units = division_data[division_name]['height_units']
            clean_division_name = self._format_division_name(division_name)

            # Prepare table data
            table_data = []
            cell_colors = []

            # Header row
            header_row = ['Name']
            for race in races:
                race_name = process_race_name(getattr(race, 'name', 'Race'))
                header_row.append(race_name)
            header_row.extend(['Points', 'Races', 'Best 5', 'Place'])
            table_data.append(header_row)
            cell_colors.append(['white'] * len(header_row))

            # Member rows
            for member_data in members:
                row = [member_data['name']]
                row.extend([str(points) if points != '' else '' for points in member_data['race_results']])
                row.extend([
                    str(member_data['total_points']),
                    str(member_data['total_races']),
                    str(member_data['total_best_5']),
                    str(member_data['place'])
                ])
                table_data.append(row)

                # Apply medal colors
                place = member_data['place']
                row_colors = [medal_colors.get(place, 'white')] * len(row)
                cell_colors.append(row_colors)

            # Calculate this table's proportional height relative to total content
            table_height_proportion = table_height_units / total_height_units


            #table_height = max(0.5, 0.1 * len(members)) + 0.4
            # Ensure table height never exceeds available space
            max_table_height = 0.85  # Leave 10% buffer
            table_height = min(max_table_height, max(0.3, 0.08 * len(members)) + 0.2)
            #y_offset = (1 - table_height) / 2


            #y_offset = prev_table_height 
            table = ax.table(cellText=table_data,
                            cellColours=cell_colors,
                            cellLoc='center',
                            loc='center',
                            bbox=[0, 0, 1, 1])

            # Style table
            table.auto_set_font_size(False)
            table.set_fontsize(9)
            #table.scale(1, 2)

            # Calculate proportional heights for consistent appearance across ALL tables
            num_data_rows = len(table_data) - 1
            total_units_this_table = race_header_height_units + (num_data_rows * data_row_height_units)
            header_height_prop = header_height_units / total_units_this_table
            race_header_height_prop = race_header_height_units / total_units_this_table
            data_row_height_prop = data_row_height_units / total_units_this_table

            # Customize cells
            for (i, j), cell in table.get_celld().items():
                cell.set_edgecolor('black')
                cell.set_linewidth(0.8)

                # Name column
                if j == 0:
                    cell.set_width(0.2)

                if i == 0:  # Header row
                    cell.set_text_props(weight='bold', fontsize=8)
                    # Rotate race headers
                    if 1 <= j <= len(races):
                        cell.set_text_props(rotation=80, x=-10, y=-10, weight='bold')
                        cell.set_height(race_header_height_prop)
                        #cell.get_text().set_y(cell.get_text().get_position()[1] - 0.2)
                    else:
                        cell.set_height(header_height_prop)
                else:
                    cell.set_text_props(fontsize=8)
                    #cell.set_height(data_row_height_prop)

            # Division title
            #title_y_position = 1 - (1 - table_height) / 4  # Position above table
            #title_y_position = y_offset - 0.3
            title_y_position = 0
            #ax.text(0.5,1.0, clean_division_name, transform=ax.transAxes, ha='center', va='bottom',
            #         fontsize=16, fontweight='bold')
            ax.set_title(clean_division_name, pad=10, fontsize=16, fontweight='bold')

            prev_table_height = table_height

        plt.savefig(filename, format='pdf', bbox_inches='tight', dpi=300, pad_inches=0.5)
        plt.close()


    def _prepare_division_data(self, races):
        """
        Helper method to prepare and sort division data
        """
        divisions = {}

        for member_name in self.members.keys():
            member = self.members[member_name]
            if hasattr(member, 'results') and member.results:
                if member.division is None:
                    continue

                # Calculate statistics
                total_points = sum(result.points for result in member.results)
                total_races = len(member.results)
                total_best_5 = sum(result.points for result in sorted(member.results, key=lambda r: r.points, reverse=True)[:5])

                # Race results array
                race_results = [''] * len(races)
                for result in member.results:
                    if result.race_index is not None and result.race_index < len(race_results):
                        race_results[result.race_index] = result.points

                if member.division not in divisions:
                    divisions[member.division] = []

                divisions[member.division].append({
                    'name': f"{member.first_name} {member.last_name}",
                    'race_results': race_results,
                    'total_points': total_points,
                    'total_races': total_races,
                    'total_best_5': total_best_5
                })

        # Sort and assign places
        for division in divisions:
            divisions[division].sort(key=lambda x: x['total_best_5'], reverse=True)
            current_place = 1
            for i, member_data in enumerate(divisions[division]):
                if i > 0 and divisions[division][i-1]['total_best_5'] != member_data['total_best_5']:
                    current_place = i + 1
                member_data['place'] = current_place

        return divisions




    def load_members_from_airtable(self, base_id, table_name, view_name):
        """
        Loads members from an Airtable view, equivalent to load_members but using Airtable API.
        Personal Access Token is loaded from .env file.

        Parameters:
            base_id (str): Airtable base ID
            table_name (str): Name of the table in Airtable
            view_name (str): Name of the view to fetch from
        """
        # Load environment variables from .env file
        load_dotenv()
        access_token = os.getenv('AIRTABLE_ACCESS_TOKEN')

        if not access_token:
            raise ValueError("AIRTABLE_ACCESS_TOKEN not found in .env file")

        url = f"https://api.airtable.com/v0/{base_id}/{table_name}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        params = {
            "view": view_name,
            "maxRecords": 1000  # Adjust as needed
        }

        all_records = []
        offset = None

        # Handle pagination
        while True:
            if offset:
                params["offset"] = offset

            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()

            data = response.json()
            all_records.extend(data.get("records", []))

            offset = data.get("offset")
            if not offset:
                break

        # Process records and create Member objects
        for record in all_records:
            fields = record.get("fields", {})

            # Parse dates
            birth_date = None
            if fields.get("Birthday"):
                try:
                    birth_date = datetime.strptime(fields["Birthday"], "%Y-%m-%d").date()
                except ValueError:
                    pass

            submission_date = None
            if fields.get("Submission Date"):
                try:
                    submission_date = datetime.strptime(fields["Submission Date"], "%Y-%m-%d")
                except ValueError:
                    pass

            # Parse expiration date for start/end years
            end_year = date.today().year
            if fields.get("Membership Expiration Date"):
                try:
                    exp_date = datetime.strptime(fields["Membership Expiration Date"], "%Y-%m-%d").date()
                    end_year = exp_date.year
                except ValueError:
                    pass

            # Create Member object
            member = Member(
                submission_date_str=fields.get("Submission Date", ""),
                first_name=fields.get("First Name", ""),
                last_name=fields.get("Last Name", ""),
                birth_date=birth_date,
                gender=fields.get("Gender", ""),
                products_str=fields.get("Products", ""),
                start_year=date.today().year,
                end_year=end_year,
                email=fields.get("Email", ""),
                address=fields.get("Mailing Address", ""),
                phone=fields.get("Phone", "")
            )

            if member.name:  # Only add if name exists
                self.members[member.name] = member




if __name__ == '__main__':
    # TODO: may need to do membership expiration validation on the backend, I just changed only_active to False because 
    # it was failing to merge with very old jotform submissions with no indication of expiration with those from Anna's spreadsheet

    # Example usage:
    club = Club()

    club.load_members()

    #club.write_members_to_csv('/tmp/output_members.csv')


    club.display_all()

    # Check membership status for a name
    #name_to_check = input("Enter full name to verify membership: ")
    #member = club.get_member(name_to_check, threshold=85)
    #if member is not None and member.active:
    #    print(f"{member.name} is an active member until {member.end_year}.")
    #else:
    #    print(f"{name_to_check} is not an active member.")

