#!/usr/bin/env python3
"""
Alma ILS Sets API Client
Creates and populates item sets using the Alma REST API
"""

import requests
import json
import csv
import argparse
import sys
import os
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path
import logging

# Configure logging - will be enhanced later with file output
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_api_key() -> Optional[str]:
    """
    Load API key from environment variable or .env file
    
    Returns:
        API key if found, None otherwise
    """
    # First try environment variable
    api_key = os.getenv('ALMA_API_KEY')
    if api_key:
        return api_key
    
    # Then try .env file in current directory or project root
    env_paths = [
        '.env',
        '../.env',
        '../../.env',
        os.path.expanduser('~/.env')
    ]
    
    for env_path in env_paths:
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('ALMA_API_KEY='):
                            return line.split('=', 1)[1].strip().strip('"\'')
            except Exception as e:
                logger.warning(f"Error reading {env_path}: {e}")
    
    return None

def setup_logging(csv_file: Optional[str] = None, verbose: bool = False):
    """
    Set up logging to both console and file
    
    Args:
        csv_file: Path to CSV file (used to determine log file location)
        verbose: Enable debug logging
    """
    # Set log level
    log_level = logging.DEBUG if verbose else logging.INFO
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # Get the root logger and clear any existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(log_level)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (if CSV file is provided)
    if csv_file:
        try:
            csv_path = Path(csv_file)
            log_dir = csv_path.parent
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f"alma_item_sets_{timestamp}.log"
            log_file_path = log_dir / log_filename
            
            file_handler = logging.FileHandler(log_file_path)
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
            
            logger.info(f"Logging to file: {log_file_path}")
        except Exception as e:
            logger.warning(f"Could not set up file logging: {e}")
    
    return root_logger

class AlmaSetClient:
    """Client for managing Alma ILS item sets via REST API"""
    
    def __init__(self, api_key: str, base_url: str = "https://api-na.hosted.exlibrisgroup.com/almaws/v1"):
        """
        Initialize the Alma Sets API client
        
        Args:
            api_key: Your Alma API key
            base_url: Base URL for Alma API (default: North America)
        """
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
    
    def create_set(self, name: str, description: str = "", note: str = "") -> Optional[Dict]:
        """
        Create a new itemized set for physical items
        
        Args:
            name: Name of the set
            description: Description of the set
            note: Optional note for the set
            
        Returns:
            Dict containing the created set information, or None if failed
        """
        url = f"{self.base_url}/conf/sets"
        params = {
            'combine': 'None',
            'set1': 'None', 
            'set2': 'None',
            'apikey': self.api_key
        }
        
        set_data = {
            "name": name,
            "description": description,
            "type": {
                "value": "ITEMIZED"
            },
            "content": {
                "value": "ITEM"
            },
            "private": {
                "value": "false"
            },
            "status": {
                "value": "ACTIVE"
            },
            "note": note,
            "origin": {
                "value": "UI"
            }
        }
        
        try:
            logger.info(f"Creating set: {name}")
            response = self.session.post(url, params=params, json=set_data)
            response.raise_for_status()
            
            set_info = response.json()
            logger.info(f"Set created successfully with ID: {set_info['id']}")
            return set_info
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create set: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            return None
    
    def test_barcode_validity(self, barcode: str) -> bool:
        """
        Test if a single barcode can be found in Alma
        This is a diagnostic function to help troubleshoot barcode issues
        
        Args:
            barcode: Single barcode to test
            
        Returns:
            True if barcode is found, False otherwise
        """
        try:
            # Use the items API to search for the barcode
            url = f"{self.base_url}/items"
            params = {
                'item_barcode': barcode,
                'apikey': self.api_key
            }
            
            response = self.session.get(url, params=params)
            if response.status_code == 200:
                logger.debug(f"Barcode {barcode} found in Alma")
                return True
            else:
                logger.warning(f"Barcode {barcode} not found (status: {response.status_code})")
                return False
                
        except Exception as e:
            logger.warning(f"Error testing barcode {barcode}: {e}")
            return False

    def add_items_to_set(self, set_id: str, item_ids: List[str], 
                        id_type: str = "BARCODE", fail_on_invalid_id: bool = False) -> bool:
        """
        Add items to an existing set
        
        Args:
            set_id: ID of the set to populate
            item_ids: List of item IDs to add to the set (up to 1000 items)
            id_type: Type of ID being used (BARCODE, MMS_ID, etc.)
            fail_on_invalid_id: Whether to fail if an invalid ID is encountered
            
        Returns:
            True if successful, False otherwise
        """
        if len(item_ids) > 1000:
            logger.error("Cannot add more than 1000 items at once")
            return False
        
        # First, get the current set information to include required fields
        current_set = self.get_set_info(set_id)
        if not current_set:
            logger.error(f"Cannot retrieve set information for set {set_id}")
            return False
            
        url = f"{self.base_url}/conf/sets/{set_id}"
        params = {
            'id_type': id_type,
            'op': 'add_members',
            'fail_on_invalid_id': str(fail_on_invalid_id).lower(),
            'apikey': self.api_key
        }
        
        # Full set object with members to add, including required name and description
        set_data = {
            "name": current_set["name"],
            "description": current_set["description"],
            "type": {
                "value": "ITEMIZED"
            },
            "content": {
                "value": "ITEM"
            },
            "private": {
                "value": "false"
            },
            "status": {
                "value": "ACTIVE"
            },
            "note": current_set.get("note", ""),
            "query": {
                "value": ""
            },
            "members": {
                "total_record_count": "",
                "member": [{"id": item_id} for item_id in item_ids]
            },
            "origin": {
                "value": "UI"
            }
        }
        
        try:
            logger.info(f"Adding {len(item_ids)} items to set {set_id} using {id_type}")
            logger.debug(f"Request URL: {url}")
            logger.debug(f"Request params: {params}")
            logger.debug(f"Sample items to add: {item_ids[:5]}")
            
            response = self.session.post(url, params=params, json=set_data)
            
            # Log the response details regardless of status
            logger.info(f"Response status: {response.status_code}")
            logger.debug(f"Response headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                response_data = response.json()
                logger.info("Items added successfully")
                logger.debug(f"Response data: {json.dumps(response_data, indent=2)}")
                
                # Check if the response indicates how many items were actually added
                if 'number_of_members' in response_data:
                    member_count = response_data['number_of_members']['value']
                    logger.info(f"Set now contains {member_count} members")
                    if member_count == 0:
                        logger.warning("Set still shows 0 members - items may not have been added successfully")
                        logger.warning("This could indicate invalid barcodes or permission issues")
                
                return True
            else:
                logger.error(f"HTTP Error {response.status_code}")
                logger.error(f"Response text: {response.text}")
                return False
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to add items to set: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response text: {e.response.text}")
            return False
    
    def create_and_populate_set(self, name: str, item_ids: List[str], 
                               description: str = "", note: str = "", 
                               id_type: str = "BARCODE") -> Optional[str]:
        """
        Create a set and populate it with items in one operation
        
        Args:
            name: Name of the set
            item_ids: List of item IDs to add to the set (up to 1000 items)
            description: Description of the set
            note: Optional note for the set
            id_type: Type of ID being used (BARCODE, MMS_ID, etc.)
            
        Returns:
            Set ID if successful, None otherwise
        """
        # Create the set
        set_info = self.create_set(name, description, note)
        if not set_info:
            return None
        
        set_id = set_info['id']
        
        # Add items to the set
        if item_ids:
            success = self.add_items_to_set(set_id, item_ids, id_type)
            if not success:
                logger.warning(f"Set {set_id} created but failed to add items")
        else:
            logger.info("No items provided to add to the set")
        
        return set_id
    
    def get_set_info(self, set_id: str) -> Optional[Dict]:
        """
        Get information about an existing set
        
        Args:
            set_id: ID of the set
            
        Returns:
            Dict containing set information, or None if failed
        """
        url = f"{self.base_url}/conf/sets/{set_id}"
        params = {'apikey': self.api_key}
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get set info: {e}")
            return None

def read_barcodes_from_csv(csv_file: str) -> List[str]:
    """
    Read barcodes from a tab-delimited CSV file
    
    Args:
        csv_file: Path to the tab-delimited CSV file containing barcodes in first column
        
    Returns:
        List of barcodes as strings
    """
    barcodes = []
    try:
        with open(csv_file, 'r', encoding='utf-8') as file:
            reader = csv.reader(file, delimiter='\t')
            
            for row in reader:
                if row and row[0].strip():  # Skip empty rows and rows with empty first column
                    barcode = str(row[0]).strip()
                    if barcode:
                        barcodes.append(barcode)
        
        logger.info(f"Read {len(barcodes)} barcodes from {csv_file}")
        if barcodes:
            logger.info(f"Sample barcodes: {barcodes[:3]}...")
        return barcodes
        
    except FileNotFoundError:
        logger.error(f"File not found: {csv_file}")
        return []
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        return []

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Create and populate Alma ILS item sets',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Create a weeded items set with today's date (API key from .env file)
  python create_set.py --csv-file Weededbarcodes.csv

  # Create a weeded items set with API key specified
  python create_set.py --api-key YOUR_KEY --csv-file Weededbarcodes.csv

  # Create a custom named set
  python create_set.py --csv-file barcodes.csv --name "Custom Set" --description "My custom set"

  # Use MMS IDs instead of barcodes
  python create_set.py --csv-file ids.csv --id-type MMS_ID

  # Create set without adding items (empty set)
  python create_set.py --name "Empty Set" --description "Set without items"

Environment Setup:
  Create a .env file in your project root with:
  ALMA_API_KEY=your_api_key_here
        '''
    )
    
    parser.add_argument(
        '--api-key', 
        help='Your Alma API key (or set ALMA_API_KEY environment variable)'
    )
    
    parser.add_argument(
        '--csv-file',
        help='CSV file containing item IDs (one per row, first column used)'
    )
    
    parser.add_argument(
        '--name',
        help='Name for the set (default: Weeded-YYYYMMDD)'
    )
    
    parser.add_argument(
        '--description', 
        default='Oakland Weeded Items',
        help='Description for the set (default: "Oakland Weeded Items")'
    )
    
    parser.add_argument(
        '--note',
        default='',
        help='Optional note for the set'
    )
    
    parser.add_argument(
        '--id-type',
        choices=['BARCODE', 'MMS_ID', 'ITEM_PID', 'ISBN'],
        default='BARCODE',
        help='Type of IDs in the CSV file (default: BARCODE)'
    )
    
    parser.add_argument(
        '--fail-on-invalid',
        action='store_true',
        help='Fail if any invalid IDs are encountered (default: continue with valid IDs)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    return parser.parse_args()
    """
    Convenience function to create a weeded items set with today's date
    
    Args:
        api_key: Your Alma API key
        item_ids: List of item IDs to add to the set (up to 1000 items)
        id_type: Type of ID being used (BARCODE, MMS_ID, etc.)
        
    Returns:
        Set ID if successful, None otherwise
    """
    client = AlmaSetClient(api_key)
    
    # Generate set name with current date
    today = datetime.now().strftime("%Y%m%d")
    set_name = f"Weeded-{today}"
    description = "Oakland Weeded Items"
    
    return client.create_and_populate_set(set_name, item_ids, description, id_type=id_type)

def create_weeded_set(api_key: str, item_ids: List[str], id_type: str = "BARCODE") -> Optional[str]:
    """
    Convenience function to create a weeded items set with today's date
    
    Args:
        api_key: Your Alma API key
        item_ids: List of item IDs to add to the set (up to 1000 items)
        id_type: Type of ID being used (BARCODE, MMS_ID, etc.)
        
    Returns:
        Set ID if successful, None otherwise
    """
    client = AlmaSetClient(api_key)
    
    # Generate set name with current date
    today = datetime.now().strftime("%Y%m%d")
    set_name = f"Weeded-{today}"
    description = "Oakland Weeded Items"
    
    return client.create_and_populate_set(set_name, item_ids, description, id_type=id_type)

def main():
    """Main function for command line interface"""
    args = parse_arguments()
    
    # Get API key from argument, environment, or .env file
    api_key = args.api_key or load_api_key()
    if not api_key:
        print("Error: API key not found. Please provide it via:")
        print("  1. --api-key argument")
        print("  2. ALMA_API_KEY environment variable") 
        print("  3. ALMA_API_KEY=your_key in a .env file")
        sys.exit(1)
    
    # Set up logging (including file logging if CSV provided)
    setup_logging(args.csv_file, args.verbose)
    
    # Read barcodes from CSV if provided
    item_ids = []
    if args.csv_file:
        item_ids = read_barcodes_from_csv(args.csv_file)
        if not item_ids:
            print(f"Error: No valid IDs found in {args.csv_file}")
            sys.exit(1)
        
        # Check batch limit
        if len(item_ids) > 1000:
            print(f"Warning: CSV contains {len(item_ids)} items, but Alma limits to 1000 per batch.")
            print("Only the first 1000 items will be processed.")
            item_ids = item_ids[:1000]
    
    # Create client
    client = AlmaSetClient(api_key)
    
    # Determine set name
    if args.name:
        set_name = args.name
    else:
        # Generate default name with current date
        today = datetime.now().strftime("%Y%m%d")
        set_name = f"Olin-Weeded-Items-{today}"
    
    print(f"Creating set: {set_name}")
    if item_ids:
        print(f"Adding {len(item_ids)} items using {args.id_type}")
    
    # Create and populate the set
    set_id = client.create_and_populate_set(
        name=set_name,
        item_ids=item_ids,
        description=args.description,
        note=args.note,
        id_type=args.id_type
    )
    
    if set_id:
        print(f"\n✅ Success! Set created with ID: {set_id}")
        
        # Get and display set information
        set_info = client.get_set_info(set_id)
        if set_info:
            member_count = set_info['number_of_members']['value']
            print(f"Set Name: {set_info['name']}")
            print(f"Description: {set_info['description']}")
            print(f"Members: {member_count}")
            print(f"Status: {set_info['status']['desc']}")
            print(f"Link: {set_info['link']}")
            
            # If no members were added, provide diagnostic info
            if member_count == 0 and item_ids:
                print(f"\n⚠️  Warning: Set was created but contains 0 members")
                print(f"This suggests the {args.id_type}s may not be valid or accessible")
                
                # Try adding items one by one to identify the problematic ones
                if args.verbose:
                    print(f"\nFirst, let's test with the known working barcodes from your example...")
                    test_barcodes = ["33086000803460", "33086001115971"]
                    test_success = client.add_items_to_set(set_id, test_barcodes, args.id_type, args.fail_on_invalid)
                    if test_success:
                        updated_info = client.get_set_info(set_id)
                        if updated_info and updated_info['number_of_members']['value'] > 0:
                            print(f"  ✅ Known working barcodes added successfully!")
                            print(f"  Set now has {updated_info['number_of_members']['value']} members")
                        else:
                            print(f"  ⚠️  Even known working barcodes failed to be added")
                    
                    print(f"\nNow trying individual items from your file...")
                    success_count = 0
                    for i, item_id in enumerate(item_ids[:5]):  # Test first 5
                        success = client.add_items_to_set(set_id, [item_id], args.id_type, args.fail_on_invalid)
                        if success:
                            # Check if it actually got added
                            updated_info = client.get_set_info(set_id)
                            current_count = updated_info['number_of_members']['value'] if updated_info else 0
                            if current_count > success_count:
                                success_count = current_count
                                print(f"  ✅ {item_id}: Added successfully (set now has {current_count} members)")
                            else:
                                print(f"  ⚠️  {item_id}: API returned success but item not in set")
                        else:
                            print(f"  ❌ {item_id}: Failed to add")
                    
                    if len(item_ids) > 5:
                        print(f"  ... (showing first 5 of {len(item_ids)} items)")
                
                print(f"\nPossible causes:")
                print(f"- Items may be electronic/digital (only physical items can be added to item sets)")
                print(f"- Items may be in a status that prevents set membership (e.g., withdrawn, missing)")
                print(f"- Items may be on loan or have active requests")
                print(f"- API user lacks permissions to modify these items")
                print(f"- There may be an issue with your specific Alma configuration")
                print(f"\nNext steps:")
                print(f"1. Check in Alma UI if these items are physical items")
                print(f"2. Verify the item status allows set membership")
                print(f"3. Try manually adding one of these barcodes to a set in Alma UI")
                print(f"4. Contact your Alma administrator about API permissions for sets")
    else:
        print("\n❌ Failed to create set")
        sys.exit(1)

def example_usage():
    """Example usage of the Alma Sets API client (for testing)"""
    
    # Configuration - replace with your actual API key
    API_KEY = "l7xx44f5015286664d35846a3f80ce29ce84"  # Replace with your actual key
    
    # Example item barcodes - replace with actual barcodes
    ITEM_IDS = [
        "33086000803460",
        "33086001115971", 
        "33086001234567"
    ]
    
    # Create client
    client = AlmaSetClient(API_KEY)
    
    # Example 1: Create a weeded items set
    print("Creating weeded items set...")
    set_id = create_weeded_set(API_KEY, ITEM_IDS)
    if set_id:
        print(f"Successfully created set with ID: {set_id}")
    else:
        print("Failed to create set")
        return
    
    # Example 2: Get set information
    print(f"\nRetrieving set information...")
    set_info = client.get_set_info(set_id)
    if set_info:
        print(f"Set Name: {set_info['name']}")
        print(f"Description: {set_info['description']}")
        print(f"Number of Members: {set_info['number_of_members']['value']}")
        print(f"Status: {set_info['status']['desc']}")
    
    # Example 3: Create a custom set with MMS IDs instead of barcodes
    print(f"\nCreating custom set with MMS IDs...")
    custom_set_id = client.create_and_populate_set(
        name="Custom-Test-Set",
        item_ids=["23456789150001401", "23456789160001401"],
        description="Test set for demonstration",
        note="Created via Python script",
        id_type="MMS_ID"  # Using MMS IDs instead of barcodes
    )
    
    if custom_set_id:
        print(f"Custom set created with ID: {custom_set_id}")

if __name__ == "__main__":
    main()