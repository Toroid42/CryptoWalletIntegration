import requests
import json
import sys

def update_token_amounts(json_file_path):
    # Define the URL to query the list of tokens from CoinGecko API
    url = "https://api.coingecko.com/api/v3/coins/list"

    # Query the CoinGecko API
    response = requests.get(url)
    tokens = response.json()

    # Load the existing JSON file
    with open(json_file_path, 'r') as file:
        data = json.load(file)

    # Prepare new token data
    new_token_data = {}
    for token in tokens:
        token_id = token['id']
        token_name = token['name']
        new_token_data[token_id] = f"Amount of {token_name}"

    # Replace the existing token data under "data" key inside "token_amounts"
    data['config']['step']['token_amounts']['data'] = new_token_data

    #Update strings used for options menu
    data['options']['step']['token_amounts']['data'] = new_token_data

    # Save the updated data back to the JSON file
    with open(json_file_path, 'w') as file:
        json.dump(data, file, indent=2)

    print(f"{json_file_path} has been updated with new token data.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python update_tokens.py <path_to_strings.json>")
        sys.exit(1)

    json_file_path = sys.argv[1]
    update_token_amounts(json_file_path)
