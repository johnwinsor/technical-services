#!/usr/bin/env python

import requests
import json
import os
import sys
import glob
from time import sleep
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def create_po_line(json_data, api_key, base_url):
    """
    Create a PO line in Alma using the API
    
    Args:
        json_data: Dictionary containing the PO line data
        api_key: Alma API key
        base_url: Alma API base URL
    
    Returns:
        tuple: (success, response_data, error_message)
    """
    
    # API endpoint
    url = f"{base_url}/almaws/v1/acq/po-lines"
    
    # Parameters
    params = {
        'requires_manual_review': 'false',
        'apikey': api_key
    }
    
    # Headers
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json'
    }
    
    try:
        # Make the POST request
        response = requests.post(
            url, 
            params=params,
            headers=headers,
            json=json_data,
            timeout=30
        )
        
        # Check if request was successful
        if response.status_code == 200 or response.status_code == 201:
            return True, response.json(), None
        else:
            return False, None, f"HTTP {response.status_code}: {response.text}"
            
    except requests.exceptions.RequestException as e:
        return False, None, f"Request error: {str(e)}"
    except json.JSONDecodeError as e:
        return False, None, f"JSON decode error: {str(e)}"
    except Exception as e:
        return False, None, f"Unexpected error: {str(e)}"

def load_json_file(filepath):
    """Load JSON data from file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        return None, f"Error loading {filepath}: {str(e)}"

def get_config():
    """Load configuration from environment variables"""
    api_key = os.getenv('ALMA_API_KEY')
    base_url = os.getenv('ALMA_BASE_URL', 'https://api-na.hosted.exlibrisgroup.com')
    
    if not api_key:
        print("❌ Error: ALMA_API_KEY environment variable not set!")
        print("Please set ALMA_API_KEY in your .env file or environment")
        sys.exit(1)
    
    return api_key, base_url

def main():
    # Load configuration from environment
    try:
        API_KEY, BASE_URL = get_config()
        print(f"✅ Configuration loaded successfully")
        print(f"   Base URL: {BASE_URL}")
        print(f"   API Key: {API_KEY[:8]}{'*' * (len(API_KEY) - 8)}")  # Mask API key for security
    except SystemExit:
        return  # Exit if config loading failed
    
    # Get JSON files to process
    if len(sys.argv) > 1:
        # If a specific directory or pattern is provided
        json_pattern = sys.argv[1]
    else:
        # Default to all JSON files in current directory
        json_pattern = "*.json"
    
    json_files = glob.glob(json_pattern)
    
    if not json_files:
        print(f"No JSON files found matching pattern: {json_pattern}")
        sys.exit(1)
    
    print(f"Found {len(json_files)} JSON files to process")
    print("=" * 60)
    
    # Process each JSON file
    success_count = 0
    error_count = 0
    created_pol_numbers = []
    
    for json_file in json_files:
        print(f"Processing: {json_file}")
        
        # Load JSON data
        json_data = load_json_file(json_file)
        if isinstance(json_data, tuple):  # Error case
            print(f"  ❌ {json_data[1]}")
            error_count += 1
            continue
        
        # Create PO line
        success, response_data, error_msg = create_po_line(json_data, API_KEY, BASE_URL)
        
        if success:
            # Extract PO line number from response
            pol_number = response_data.get('number', 'Unknown')
            
            # Extract MMS ID from response
            mms_id = 'Unknown'
            resource_metadata = response_data.get('resource_metadata', {})
            if 'mms_id' in resource_metadata and isinstance(resource_metadata['mms_id'], dict):
                mms_id = resource_metadata['mms_id'].get('value', 'Unknown')
            
            created_pol_numbers.append({'pol_number': pol_number, 'mms_id': mms_id, 'filename': json_file})
            
            print(f"  ✅ Success! Created POL: {pol_number}")
            print(f"    MMS ID: {mms_id}")
            
            # Display key info
            title = json_data.get('resource_metadata', {}).get('title', 'N/A')
            vendor_ref = json_data.get('vendor_reference_number', 'N/A')
            print(f"    Title: {title[:50]}...")
            print(f"    Vendor Ref: {vendor_ref}")
            
            success_count += 1
        else:
            print(f"  ❌ Failed: {error_msg}")
            error_count += 1
        
        # Add a small delay to avoid overwhelming the API
        sleep(0.5)
        print()
    
    # Summary
    print("=" * 60)
    print("PROCESSING SUMMARY")
    print(f"Total files processed: {len(json_files)}")
    print(f"Successfully created: {success_count}")
    print(f"Errors encountered: {error_count}")
    
    if created_pol_numbers:
        print(f"\nCreated POL Numbers and MMS IDs:")
        for entry in created_pol_numbers:
            print(f"  - POL: {entry['pol_number']} | MMS ID: {entry['mms_id']}")
    
    # Save results to file
    if created_pol_numbers:
        from datetime import datetime
        
        with open('created_pol_numbers.txt', 'a') as f:
            # Add timestamp for this run
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"\n=== Run completed at {timestamp} ===\n")
            f.write("Filename\tPOL Number\tMMS ID\n")
            f.write("-" * 40 + "\n")
            for entry in created_pol_numbers:
                f.write(f"{entry['filename']}\t{entry['pol_number']}\t{entry['mms_id']}\n")
        print(f"\nResults appended to: created_pol_numbers.txt")

def test_api_connection():
    """Test function to verify API connectivity"""
    try:
        API_KEY, BASE_URL = get_config()
    except SystemExit:
        return False
    
    # Test with a simple GET request to verify API key works
    url = f"{BASE_URL}/almaws/v1/acq/vendors"
    params = {'apikey': API_KEY, 'limit': 1}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            print("✅ API connection successful!")
            return True
        else:
            print(f"❌ API connection failed: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ API connection error: {str(e)}")
        return False

if __name__ == "__main__":
    print("Alma PO Line Creator")
    print("=" * 60)
    
    # Uncomment the next two lines to test API connection first
    # if not test_api_connection():
    #     sys.exit(1)
    
    main()