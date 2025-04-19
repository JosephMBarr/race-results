from googleapiclient.discovery import build
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from dotenv import load_dotenv
import os
from parse import extract_results_from_pdf

def create_sheet(new_sheet_name, spreadsheet_id, service):
    # Retrieve spreadsheet metadata to list existing sheets
    spreadsheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheets = spreadsheet_metadata.get('sheets', [])

    sheet_names = [sheet['properties']['title'] for sheet in sheets]
    if new_sheet_name in sheet_names:
        print(f"Sheet {new_sheet_name} already exists. No need to create it.")

    else:
        requests = [{
            "addSheet": {
                "properties": {
                    "title": new_sheet_name
                }
            }
        }]

        body = {
            "requests": requests
        }

        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=body
        ).execute()

# Load environment variables from .env
load_dotenv()

# Get the client secret path from the .env file
client_secret_path = os.getenv("CLIENT_SECRET")
if client_secret_path is None:
    raise Exception("Need a client secret file!")

creds_file = os.getenv("CREDS_LOCATION")
if creds_file is None:
    raise Exception("Need a credentials file!")

# Initialize GoogleAuth instance
gauth = GoogleAuth()

# Specify the path to the client secrets file dynamically
gauth.settings["client_config_file"] = client_secret_path

# Check for saved credentials or authenticate and save new ones
if os.path.exists(creds_file):
    gauth.LoadCredentialsFile(creds_file)
    if gauth.access_token_expired:
        gauth.Refresh()
else:
    gauth.LocalWebserverAuth()  # Authenticate and create credentials
    gauth.SaveCredentialsFile(creds_file)  # Save credentials for reuse

# Initialize Google Drive instance with authenticated credentials
drive = GoogleDrive(gauth)
creds = gauth.credentials

# Build the Sheets API service
service = build('sheets', 'v4', credentials=creds)

# Get file from name in .env
grand_prix_filename = os.getenv("GRAND_PRIX_FILENAME")
file_list = drive.ListFile({'q': f"'root' in parents and trashed=false and title = '{grand_prix_filename}'"}).GetList()

if not file_list or len(file_list) == 0:
    raise Exception(f"Could not find file named {grand_prix_filename} in Google Drive")

gp_file = file_list[0]


results_path = "/home/joseph/Downloads/SpringClassic2024Results15k.pdf"
race_name = "2024 Spring Classic"
results = extract_results_from_pdf(results_path)

new_data = [
         ['Name', 'Division', 'Time', 'Age', 'Sex', 'City', 'State'] 
        ]

for r in results:
    new_data.append([
        r.name,
        r.division,
        r.time,
        str(r.age),
        r.sex,
        r.city,
        r.state
        ])



# Create a new sheet for the race
race_condensed_name = race_name.replace(" ", "")
create_sheet(race_condensed_name, gp_file['id'], service)

# Create request to fill out the sheet
range_name = f'{race_condensed_name}!A1'
update_body = {
    'range': range_name,
    'majorDimension': 'ROWS',
    'values': new_data
}

response = service.spreadsheets().values().update(
    spreadsheetId=gp_file['id'],
    range=range_name,
    valueInputOption='RAW',
    body=update_body
).execute()

print(f"Spreadsheet updated! Response: {response}")
