#!/usr/bin/env python3
"""
Alma ILS Title Sets API Client
Creates and populates title sets using MMSIDs via the Alma REST API
"""

import requests
import json
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
            log_filename = f"alma_title_sets_{timestamp}.log"
            log_file_path = log_dir / log_filename
            
            file_handler = logging.FileHandler(log_file_path)
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
            
            logger.info(f"Logging to file: {log_file_path}")
        except Exception as e:
            logger.warning(f"Could not set up file logging: {e}")
    
    return root_logger

class AlmaTitleSetClient:
    """Client for managing Alma ILS title sets via REST API"""
    
    def __init__(self, api_key: str, base_url: str = "https://api-na.hosted.exlibrisgroup.com/almaws/v1"):
        """
        Initialize the Alma Title Sets API client
        
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
        Create a new itemized set for bibliographic records (titles)
        
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
                "value": "IEP"  # Bibliographic records (titles)
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
            logger.info(f"Creating title set: {name}")
            response = self.session.post(url, params=params, json=set_data)
            response.raise_for_status()
            
            set_info = response.json()
            logger.info(f"Title set created successfully with ID: {set_info['id']}")
            return set_info
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create title set: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            return None
    
    def test_mmsid_validity(self, mmsid: str) -> bool:
        """
        Test if a single MMSID can be found in Alma
        This is a diagnostic function to help troubleshoot MMSID issues
        
        Args:
            mmsid: Single MMSID to test
            
        Returns:
            True if MMSID is found, False otherwise
        """
        try:
            # Use the bibs API to search for the MMSID
            url = f"{self.base_url}/bibs/{mmsid}"
            params = {'apikey': self.api_key}
            
            response = self.session.get(url, params=params)
            if response.status_code == 200:
                logger.debug(f"MMSID {mmsid} found in Alma")
                return True
            else:
                logger.warning(f"MMSID {mmsid} not found (status: {response.status_code})")
                return False
                
        except Exception as e:
            logger.warning(f"Error testing MMSID {mmsid}: {e}")
            return False

    def add_titles_to_set(self, set_id: str, mmsids: List[str], 
                         fail_on_invalid_id: bool = True) -> bool:
        """
        Add titles (MMSIDs) to an existing set
        
        Args:
            set_id: ID of the set to populate
            mmsids: List of MMSIDs to add to the set (up to 1000 items)
            fail_on_invalid_id: Whether to fail if an invalid ID is encountered
            
        Returns:
            True if successful, False otherwise
        """
        if len(mmsids) > 1000:
            logger.error("Cannot add more than 1000 titles at once")
            return False
            
        url = f"{self.base_url}/conf/sets/{set_id}"
        params = {
            'id_type': 'SYSTEM_NUMBER',  # Always MMS_ID for bibliographic records
            'op': 'add_members',
            'fail_on_invalid_id': str(fail_on_invalid_id).lower(),
            'apikey': self.api_key
        }
        
        # Set object for bibliographic records (IEP content type)
        set_data = {
            "type": {
                "value": "ITEMIZED"
            },
            "content": {
                "value": "IEP"  # Bibliographic records
            },
            "private": {
                "value": "false"
            },
            "status": {
                "value": "ACTIVE"
            },
            "note": "",
            "query": {
                "value": ""
            },
            "members": {
                "total_record_count": "",
                "member": [{"id": mmsid} for mmsid in mmsids]
            },
            "origin": {
                "value": "UI"
            }
        }
        
        try:
            logger.info(f"Adding {len(mmsids)} titles to set {set_id}")
            logger.debug(f"Request URL: {url}")
            logger.debug(f"Request params: {params}")
            logger.debug(f"Sample MMSIDs to add: {mmsids[:5]}")
            
            response = self.session.post(url, params=params, json=set_data)
            
            # Log the response details regardless of status
            logger.info(f"Response status: {response.status_code}")
            logger.debug(f"Response headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                response_data = response.json()
                logger.info("Titles added successfully")
                logger.debug(f"Response data: {json.dumps(response_data, indent=2)}")
                
                # Check if the response indicates how many titles were actually added
                if 'number_of_members' in response_data:
                    member_count = response_data['number_of_members']['value']
                    logger.info(f"Set now contains {member_count} members")
                    if member_count == 0:
                        logger.warning("Set still shows 0 members - titles may not have been added successfully")
                        logger.warning("This could indicate invalid MMSIDs or permission issues")
                
                return True
            else:
                logger.error(f"HTTP Error {response.status_code}")
                logger.error(f"Response text: {response.text}")
                return False
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to add titles to set: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response text: {e.response.text}")
            return False
    
    def create_and_populate_set(self, name: str, mmsids: List[str], 
                               description: str = "", note: str = "") -> Optional[str]:
        """
        Create a title set and populate it with MMSIDs in one operation
        
        Args:
            name: Name of the set
            mmsids: List of MMSIDs to add to the set (up to 1000 items)
            description: Description of the set
            note: Optional note for the set
            
        Returns:
            Set ID if successful, None otherwise
        """
        # Create the set
        set_info = self.create_set(name, description, note)
        if not set_info:
            return None
        
        set_id = set_info['id']
        
        # Add titles to the set
        if mmsids:
            success = self.add_titles_to_set(set_id, mmsids)
            if not success:
                logger.warning(f"Set {set_id} created but failed to add titles")
        else:
            logger.info("No MMSIDs provided to add to the set")
        
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

def read_mmsids_from_csv(csv_file: str) -> List[str]:
    """
    Read MMSIDs from a simple text file (one MMSID per line)
    
    Args:
        csv_file: Path to the file containing MMSIDs
        
    Returns:
        List of MMSIDs as strings
    """
    mmsids = []
    try:
        with open(csv_file, 'r', encoding='utf-8') as file:
            for line_num, line in enumerate(file, 1):
                line = line.strip()
                if line and not line.startswith('#'):  # Skip empty lines and comments
                    mmsids.append(line)
        
        logger.info(f"Read {len(mmsids)} MMSIDs from {csv_file}")
        if mmsids:
            logger.info(f"Sample MMSIDs: {mmsids[:3]}...")
        return mmsids
        
    except FileNotFoundError:
        logger.error(f"File not found: {csv_file}")
        return []
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        return []

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Create and populate Alma ILS title sets using MMSIDs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Create a title set with MMSIDs (API key from .env file)
  python create_title_set.py --csv-file mmsids.csv

  # Create a title set with API key specified
  python create_title_set.py --api-key YOUR_KEY --csv-file mmsids.csv

  # Create a custom named title set
  python create_title_set.py --csv-file mmsids.csv --name "Special Collection" --description "Titles for special collection"

  # Create set without adding titles (empty set)
  python create_title_set.py --name "Empty Title Set" --description "Set without titles"

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
        help='CSV file containing MMSIDs (one per row, first column used)'
    )
    
    parser.add_argument(
        '--name',
        help='Name for the set (default: Titles-YYYYMMDD)'
    )
    
    parser.add_argument(
        '--description', 
        default='Title Set',
        help='Description for the set (default: "Title Set")'
    )
    
    parser.add_argument(
        '--note',
        default='',
        help='Optional note for the set'
    )
    
    parser.add_argument(
        '--fail-on-invalid',
        action='store_true',
        help='Fail if any invalid MMSIDs are encountered (default: continue with valid MMSIDs)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    return parser.parse_args()

def create_title_set(api_key: str, mmsids: List[str]) -> Optional[str]:
    """
    Convenience function to create a title set with today's date
    
    Args:
        api_key: Your Alma API key
        mmsids: List of MMSIDs to add to the set (up to 1000 items)
        
    Returns:
        Set ID if successful, None otherwise
    """
    client = AlmaTitleSetClient(api_key)
    
    # Generate set name with current date
    today = datetime.now().strftime("%Y%m%d")
    set_name = f"Titles-{today}"
    description = "Title Set"
    
    return client.create_and_populate_set(set_name, mmsids, description)

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
    
    # Read MMSIDs from CSV if provided
    mmsids = []
    if args.csv_file:
        mmsids = read_mmsids_from_csv(args.csv_file)
        if not mmsids:
            print(f"Error: No valid MMSIDs found in {args.csv_file}")
            sys.exit(1)
        
        # Check batch limit
        if len(mmsids) > 1000:
            print(f"Warning: CSV contains {len(mmsids)} MMSIDs, but Alma limits to 1000 per batch.")
            print("Only the first 1000 MMSIDs will be processed.")
            mmsids = mmsids[:1000]
    
    # Create client
    client = AlmaTitleSetClient(api_key)
    
    # Determine set name
    if args.name:
        set_name = args.name
    else:
        # Generate default name with current date
        today = datetime.now().strftime("%Y%m%d")
        set_name = f"Olin-Weeded-Titles-{today}"
    
    print(f"Creating title set: {set_name}")
    if mmsids:
        print(f"Adding {len(mmsids)} titles using MMSIDs")
    
    # Create and populate the set
    set_id = client.create_and_populate_set(
        name=set_name,
        mmsids=mmsids,
        description=args.description,
        note=args.note
    )
    
    if set_id:
        print(f"\n✅ Success! Title set created with ID: {set_id}")
        
        # Get and display set information
        set_info = client.get_set_info(set_id)
        if set_info:
            member_count = set_info['number_of_members']['value']
            print(f"Set Name: {set_info['name']}")
            print(f"Description: {set_info['description']}")
            print(f"Members: {member_count}")
            print(f"Status: {set_info['status']['desc']}")
            print(f"Content Type: {set_info['content']['desc']}")
            print(f"Link: {set_info['link']}")
            
            # If no members were added, provide diagnostic info
            if member_count == 0 and mmsids:
                print(f"\n⚠️  Warning: Set was created but contains 0 members")
                print(f"This suggests the MMSIDs may not be valid or accessible")
                
                # Try adding MMSIDs one by one to identify the problematic ones
                if args.verbose:
                    print(f"\nTrying to add MMSIDs individually to identify issues...")
                    success_count = 0
                    for i, mmsid in enumerate(mmsids[:5]):  # Test first 5
                        success = client.add_titles_to_set(set_id, [mmsid], args.fail_on_invalid)
                        if success:
                            # Check if it actually got added
                            updated_info = client.get_set_info(set_id)
                            current_count = updated_info['number_of_members']['value'] if updated_info else 0
                            if current_count > success_count:
                                success_count = current_count
                                print(f"  ✅ {mmsid}: Added successfully (set now has {current_count} members)")
                            else:
                                print(f"  ⚠️  {mmsid}: API returned success but MMSID not in set")
                        else:
                            print(f"  ❌ {mmsid}: Failed to add")
                    
                    if len(mmsids) > 5:
                        print(f"  ... (showing first 5 of {len(mmsids)} MMSIDs)")
                
                print(f"\nPossible causes:")
                print(f"- MMSIDs don't exist in your Alma instance")
                print(f"- MMSIDs may be suppressed or deleted")
                print(f"- API user lacks permissions to access these bibliographic records")
                print(f"- There may be an issue with your specific Alma configuration")
    else:
        print("\n❌ Failed to create title set")
        sys.exit(1)

def example_usage():
    """Example usage of the Alma Title Sets API client (for testing)"""
    
    # Configuration - replace with your actual API key
    API_KEY = "l7xx44f5015286664d35846a3f80ce29ce84"  # Replace with your actual key
    
    # Example MMSIDs - replace with actual MMSIDs
    MMSIDS = [
        "9952173498401401",
        "9952173499401401", 
        "9952173500401401"
    ]
    
    # Create client
    client = AlmaTitleSetClient(API_KEY)
    
    # Example 1: Create a title set
    print("Creating title set...")
    set_id = create_title_set(API_KEY, MMSIDS)
    if set_id:
        print(f"Successfully created title set with ID: {set_id}")
    else:
        print("Failed to create title set")
        return
    
    # Example 2: Get set information
    print(f"\nRetrieving title set information...")
    set_info = client.get_set_info(set_id)
    if set_info:
        print(f"Set Name: {set_info['name']}")
        print(f"Description: {set_info['description']}")
        print(f"Number of Members: {set_info['number_of_members']['value']}")
        print(f"Content Type: {set_info['content']['desc']}")
        print(f"Status: {set_info['status']['desc']}")

if __name__ == "__main__":
    main()