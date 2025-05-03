import csv
import re
from datetime import datetime, date
from difflib import SequenceMatcher

class Member:
    """
    Represents a club member with relevant membership details.
    """
    def __init__(self, submission_date_str, first_name, last_name, birth_date_str,
                 gender, products_str):
        # Parse submission date
        self.submission_date = datetime.strptime(submission_date_str, '%m-%d-%Y %H:%M:%S')
        self.first_name = first_name
        self.last_name = last_name
        # Parse birth date. Some people skip this or don't provide a year
        try:
            self.birth_date = datetime.strptime(birth_date_str, '%B %d %Y').date()
        except:
            self.birth_date = None
        self.gender = gender
        self.products = products_str

        # Determine start year: if submitted in Sept (9) or later, start next calendar year
        year = self.submission_date.year
        if self.submission_date.month >= 9:
            year += 1
        self.start_year = year

        years_paid = 0
        if "Renew 1 Year" in products_str:
            years_paid += 1

        if "New Individual" in products_str:
            years_paid += 1


        # Check for "Special Quantity: <number>" to extend membership
        match = re.search(r"Special Quantity:\s*(\d+)", products_str)
        if match:
            years_paid += int(match.group(1))

        self.end_year = self.start_year - 1 + years_paid

    def display(self):
        """
        Prints the member's details to the console.
        """
        print(f"Member: {self.first_name} {self.last_name}")
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
    def __init__(self):
        self.members = []
    def load_from_csv(self, filepath, family=False):
        """
        Reads a CSV file (individual or family format), parses relevant columns,
        and stores Member instances. Use family=True for family files.
        """
        with open(filepath, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Base fields
                products_key = 'My Products: Products' if not family else 'Please select at least one:: Products'
                base_products = row.get(products_key, '')
                # Primary member
                primary = Member(
                    submission_date_str=row['Submission Date'],
                    first_name=row['First Name'],
                    last_name=row['Last Name'],
                    birth_date_str=row['Birth Date'],
                    gender=row['Gender'],
                    products_str=base_products
                )
                self.members.append(primary)

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
                                fn, ln, bd, gen = parsed
                                m = Member(
                                    submission_date_str=row['Submission Date'],
                                    first_name=fn,
                                    last_name=ln,
                                    birth_date_str=bd,
                                    gender=gen,
                                    products_str=base_products
                                )
                                self.members.append(m)
    def _parse_family_member(self, s, family_name):
        """
        Attempts to extract first name, last name, birth date, and gender from a string.
        Expected separators: commas, slashes, or spaces.
        Formats supported for birth date: 'Month DD YYYY', 'MM-DD-YYYY', 'YYYY-MM-DD'.

        Returns a tuple (first_name, last_name, birth_date_str, gender) or None.
        """
        #parts = re.split(r'[,/\\]+', s)

        parts = re.split(r'[\s,\\/]+', s)
        parts = [p.strip() for p in parts if p.strip()]

        # Easiest to determine is sex. Find it and take it out
        sex = None
        sex_index = -1
        for idx, p in enumerate(parts):
            if p.lower() in ['m', 'male']:
                sex = 'm'
                sex_index = idx
            if p.lower() in ['f', 'female']:
                sex = 'f'
                sex_index = idx
            if p.lower() in ['n', 'nonbinary']:
                sex = 'n'
                sex_index = idx

        if sex is not None:
            del parts[sex_index]

        # Next easiest is date of birth. This is most reliably indicated by seeing two straight numbers.
        year = None
        month = None
        day = None
        is_numeric = lambda s: s.isdigit()
        for idx, p in enumerate(parts):
            if is_numeric(p):
                if is_numeric(parts[idx + 1]):
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
                        
                    parts.remove(year)
                    parts.remove(month)
                    parts.remove(day)
                    break

        # Clean up 
        parts = [p for p in parts if p not in ['-', ':']]
        
        # In theory should just be name now
        first_name = parts[0]
        if len(parts) > 1:
            last_name = parts[1]
        else:
            last_name = family_name

        #last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
        print(f'aaaa {first_name} {last_name}')
        if year is None or month is None or day is None:
            dob = None
            dob_str = ''
        else:
            dob = '/'.join([month, day, year])
            # Normalize DOB to 'Month DD YYYY'
            for fmt in ('%B/%d/%Y', '%m/%d/%Y', '%d/%m/%Y'):
                try:
                    dt = datetime.strptime(dob, fmt)
                    dob_str = dt.strftime('%B %d %Y')
                    break
                except ValueError:
                    continue
            else:
                dob_str = ''
        return first_name, last_name, dob_str, sex
    def display_all(self):
        """
        Displays all members in the club.
        """
        for member in self.members:
            member.display()


    def get_member(self, name, tolerance=0.8):
        """
        Checks if a name (fuzzy matching) corresponds to an active member.

        Parameters:
            name (str): The full name to check, e.g., "Jane Doe".
            tolerance (float): Fuzzy match threshold between 0 and 1.

        Returns:
            bool: True if an active member matches the name within tolerance.
        """
        today_year = date.today().year
        for member in self.members:
            full_name = f"{member.first_name} {member.last_name}"
            ratio = SequenceMatcher(None, name.lower(), full_name.lower()).ratio()
            # If name matches and membership hasn't ended
            if ratio >= tolerance and member.end_year >= today_year:
                return member
        return None

if __name__ == '__main__':
    # Example usage:
    club = Club()
    club.load_from_csv('/home/joseph/race-results/membership/family.csv', family=True)
    print("All Members:\n")
    club.display_all()

    # Check membership status for a name
    #name_to_check = input("Enter full name to verify membership: ")
    #member = club.get_member(name_to_check, tolerance=0.85)
    #if member is not None:
    #    print(f"{member.first_name} {member.last_name} is an active member until {member.end_year}.")
    #else:
    #    print(f"{name_to_check} is not an active member.")

