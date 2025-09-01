import requests
import pandas as pd
import sys
import os
import time
import json
from urllib.parse import quote
from dotenv import load_dotenv

def get_holdings_from_api(mms_id, api_key, base_url="https://api-na.hosted.exlibrisgroup.com/almaws/v1"):
    """
    Retrieve holdings for a specific MMS ID using the Alma API.
    
    Args:
        mms_id (str): The MMS ID to check
        api_key (str): Your Alma API key
        base_url (str): Base URL for Alma API
        
    Returns:
        dict: API response containing holdings data, or None if error
    """
    url = f"{base_url}/bibs/{mms_id}/holdings"
    
    params = {
        'apikey': api_key,
        'format': 'json'
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            print(f"  Warning: MMS ID {mms_id} not found")
            return None
        elif response.status_code == 429:
            print(f"  Rate limit hit, waiting 5 seconds...")
            time.sleep(5)
            return get_holdings_from_api(mms_id, api_key, base_url)  # Retry
        else:
            print(f"  API Error for {mms_id}: {response.status_code} - {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"  Request error for {mms_id}: {str(e)}")
        return None

def extract_locations_from_holdings(holdings_data):
    """
    Extract location codes from the holdings API response.
    
    Args:
        holdings_data (dict): The JSON response from the holdings API
        
    Returns:
        list: List of location codes found in the holdings
    """
    locations = []
    
    if not holdings_data or 'holding' not in holdings_data:
        return locations
    
    holdings = holdings_data['holding']
    if not isinstance(holdings, list):
        holdings = [holdings]
    
    for holding in holdings:
        # Check for location in the holding record
        if 'location' in holding:
            location_code = holding['location'].get('value', '')
            if location_code:
                locations.append(location_code)
        
        # Also check items within holdings if they exist
        if 'item' in holding:
            items = holding['item']
            if not isinstance(items, list):
                items = [items]
            
            for item in items:
                if 'item_data' in item and 'location' in item['item_data']:
                    location_code = item['item_data']['location'].get('value', '')
                    if location_code and location_code not in locations:
                        locations.append(location_code)
    
    return locations

def process_mms_ids_with_api(csv_file_path, api_key, suppressed_patterns=["olwdfy", "olweed", "oldeleted"]):
    """
    Process MMS IDs from CSV file using Alma API to check holdings.
    
    Args:
        csv_file_path (str): Path to the CSV file with MMS IDs
        api_key (str): Alma API key
        suppressed_patterns (list): List of patterns to match suppressed locations
        
    Returns:
        list: List of MMS IDs where all holdings are in suppressed locations
    """
    # Read the CSV file (tab-separated)
    df = pd.read_csv(csv_file_path, sep='\t', header=None)
    
    # Get MMS IDs from the second column (index 1) and deduplicate
    mms_ids = df.iloc[:, 1].astype(str).str.strip().drop_duplicates().tolist()
    
    print(f"Found {len(df)} total records")
    print(f"Found {len(mms_ids)} unique MMS IDs to process")
    
    suppressed_only_mmsids = []
    
    for index, mms_id in enumerate(mms_ids):
        print(f"[{index + 1}/{len(mms_ids)}] Checking MMS ID: {mms_id}")
        
        # Get holdings from API
        holdings_data = get_holdings_from_api(mms_id, api_key)
        
        if holdings_data is None:
            continue
        
        # Extract locations
        locations = extract_locations_from_holdings(holdings_data)
        
        if not locations:
            print(f"  No locations found")
            continue
        
        print(f"  Locations found: {', '.join(locations)}")
        
        # Check if ALL locations match any of the suppressed patterns
        all_suppressed = all(
            any(location.startswith(pattern) for pattern in suppressed_patterns) 
            for location in locations
        )
        
        if all_suppressed:
            suppressed_only_mmsids.append(mms_id)
            print(f"  ✓ ALL holdings in suppressed locations - ADDED TO LIST")
        else:
            print(f"  ✗ Has active holdings - skipped")
        
        # Be nice to the API - small delay between requests
        time.sleep(0.5)
    
    return suppressed_only_mmsids

def main():
    """
    Main function to process MMS IDs using Alma API.
    """
    # Load environment variables from .env file
    load_dotenv()
    
    if len(sys.argv) != 2:
        print("Usage: python alma_api_holdings_checker.py <csv_file_path>")
        print("Example: python alma_api_holdings_checker.py 'Weededbarcodes.csv'")
        print("\nNote: Make sure ALMA_API_KEY is set in your .env file")
        print("CSV file should be tab-separated with MMS IDs in the second column")
        sys.exit(1)
    
    csv_file = sys.argv[1]
    
    # Get API key from environment variable
    api_key = os.getenv('ALMA_API_KEY')
    if not api_key:
        print("Error: ALMA_API_KEY not found in environment variables.")
        print("Please make sure you have a .env file with:")
        print("ALMA_API_KEY=your_api_key_here")
        sys.exit(1)
    
    # Check if file exists
    if not os.path.exists(csv_file):
        print(f"Error: File '{csv_file}' not found.")
        sys.exit(1)
    
    print(f"Processing CSV file: {csv_file}")
    print("Using Alma API to check holdings for each MMS ID...")
    print("Looking for titles with ALL holdings in suppressed locations (olwdfy, olweed, oldeleted patterns)")
    print("=" * 70)
    
    try:
        suppressed_mmsids = process_mms_ids_with_api(csv_file, api_key)
        
        print("=" * 70)
        print(f"SUMMARY: Found {len(suppressed_mmsids)} titles with all holdings in suppressed locations")
        print("\nMMS IDs to process for OCLC removal:")
        
        for mms_id in suppressed_mmsids:
            print(mms_id)
        
        # Save results
        if suppressed_mmsids:
            base_name = os.path.dirname(csv_file)
            output_file = f'{base_name}/mmsids_all_items_suppressed.txt'
            with open(output_file, 'w') as f:
                for mms_id in suppressed_mmsids:
                    f.write(f"{mms_id}\n")
            print(f"\nResults saved to: {output_file}")
        else:
            print("\nNo titles found with all holdings in suppressed locations.")
    
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()