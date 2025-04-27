import requests

def fetch_webpage(url):
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an error for bad responses
        print(response.text)  # Print the HTML content
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")

# Example usage
url = "https://www.mtecresults.com/race/leaderboard/17623/2024_SCHEELS_Healthy_Human_Race-Half_Marathon"  # Replace with the desired URL
fetch_webpage(url)

