#!/usr/bin/env python

"""
OCLC WorldCat Metadata API Helper Functions

Provides functions for searching and retrieving bibliographic metadata
from OCLC WorldCat using the bookops_worldcat library.

Requires:
- bookops_worldcat library
- Environment variables: WORLDCAT_API_KEY, WORLDCAT_API_SECRET
"""

import os
import logging
from time import sleep
from typing import Optional, Dict, Any

try:
    from bookops_worldcat import WorldcatAccessToken, MetadataSession
except ImportError:
    raise ImportError(
        "bookops_worldcat is required. Install with: pip install bookops-worldcat"
    )

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging for OCLC operations
logger = logging.getLogger(__name__)

# =============================================================================
# AUTHENTICATION AND SESSION MANAGEMENT
# =============================================================================

def get_worldcat_token() -> Optional[WorldcatAccessToken]:
    """
    Create and return a WorldCat API access token.
    
    Retrieves API credentials from environment variables and creates
    an authenticated token for WorldCat Metadata API access.
    
    Returns:
        WorldcatAccessToken: Authenticated token object
        None: If credentials are missing or invalid
        
    Raises:
        ValueError: If required environment variables are not set
        Exception: If token creation fails
    """
    key = os.getenv('WORLDCAT_API_KEY')
    secret = os.getenv('WORLDCAT_API_SECRET')
    
    if not key or not secret:
        raise ValueError(
            "Missing WorldCat API credentials. Please set WORLDCAT_API_KEY "
            "and WORLDCAT_API_SECRET in your environment variables."
        )
    
    try:
        token = WorldcatAccessToken(
            key=key,
            secret=secret,
            scopes="WorldCatMetadataAPI",
        )
        return token
    except Exception as e:
        logger.error(f"Failed to create WorldCat token: {str(e)}")
        raise

def get_metadata_session(token: WorldcatAccessToken) -> MetadataSession:
    """
    Create a WorldCat Metadata API session.
    
    Args:
        token: Authenticated WorldCat access token
        
    Returns:
        MetadataSession: Session object for making API calls
    """
    return MetadataSession(authorization=token)

# =============================================================================
# BIBLIOGRAPHIC DATA RETRIEVAL
# =============================================================================

def get_brief_bib(oclc_number: str, session: MetadataSession) -> Optional[Dict[Any, Any]]:
    """
    Retrieve brief bibliographic record from WorldCat.
    
    Args:
        oclc_number: OCLC control number (as string)
        session: Authenticated MetadataSession
        
    Returns:
        dict: Brief bibliographic record data
        None: If record not found or error occurred
    """
    if not oclc_number or not oclc_number.strip():
        logger.warning("Empty OCLC number provided")
        return None
    
    # Clean OCLC number (remove any non-digit characters)
    clean_oclc = ''.join(char for char in oclc_number if char.isdigit())
    
    if not clean_oclc:
        logger.warning(f"Invalid OCLC number format: {oclc_number}")
        return None
    
    try:
        # Add small delay to respect API rate limits
        sleep(0.5)
        
        with session:
            response = session.brief_bibs_get(clean_oclc)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                logger.info(f"OCLC record not found: {clean_oclc}")
                return None
            else:
                logger.error(f"WorldCat API error: {response.status_code} - {response.text}")
                return None
                
    except Exception as e:
        logger.error(f"Error retrieving OCLC record {clean_oclc}: {str(e)}")
        return None

# =============================================================================
# DATA EXTRACTION AND MAPPING
# =============================================================================

def extract_bibliographic_data(brief_bib: Dict[Any, Any]) -> Dict[str, str]:
    """
    Extract and map bibliographic data from WorldCat brief record.
    
    Maps WorldCat fields to standard bibliographic fields used
    in library acquisitions workflows.
    
    Args:
        brief_bib: Brief bibliographic record from WorldCat API
        
    Returns:
        dict: Mapped bibliographic data with keys:
            - title, author, isbn, publisher, publication_year, publication_place
    """
    if not brief_bib:
        return {}
    
    extracted_data = {}
    
    try:
        # Extract title
        if 'title' in brief_bib:
            extracted_data['title'] = brief_bib['title'].strip()
        
        # Extract author (creator field in actual response)
        if 'creator' in brief_bib:
            extracted_data['author'] = brief_bib['creator'].strip()
        
        # Extract ISBN (isbns is an array in actual response)
        if 'isbns' in brief_bib and brief_bib['isbns']:
            # Take the first ISBN from the list
            extracted_data['isbn'] = brief_bib['isbns'][0]
        
        # Extract publisher
        if 'publisher' in brief_bib:
            extracted_data['publisher'] = brief_bib['publisher'].strip()
        
        # Extract publication place
        if 'publicationPlace' in brief_bib:
            extracted_data['publication_place'] = brief_bib['publicationPlace'].strip()
        
        # Extract publication year (date field in actual response)
        if 'date' in brief_bib:
            extracted_data['publication_year'] = brief_bib['date'].strip()
        
        logger.info(f"Extracted bibliographic data: {list(extracted_data.keys())}")
        return extracted_data
        
    except Exception as e:
        logger.error(f"Error extracting bibliographic data: {str(e)}")
        return {}

# =============================================================================
# HIGH-LEVEL SEARCH FUNCTIONS
# =============================================================================

def search_oclc_metadata(oclc_number: str) -> Optional[Dict[str, str]]:
    """
    Complete workflow to search OCLC and return bibliographic data.
    
    This is the main function to use for OCLC integration. It handles
    authentication, searching, and data extraction in one call.
    
    Args:
        oclc_number: OCLC control number to search
        
    Returns:
        dict: Extracted bibliographic data ready for use in templates,
              includes the original OCLC number for system control
        None: If search failed or no data found
        
    Example:
        >>> data = search_oclc_metadata('1110469890')
        >>> if data:
        ...     print(f"Title: {data.get('title', 'N/A')}")
        ...     print(f"OCLC: {data.get('oclc_number', 'N/A')}")
    """
    if not oclc_number:
        return None
    
    # Clean OCLC number for consistent formatting
    clean_oclc = ''.join(char for char in oclc_number if char.isdigit())
    
    try:
        # Get authentication token
        token = get_worldcat_token()
        if not token:
            logger.error("Failed to obtain WorldCat token")
            return None
        
        # Create session
        session = get_metadata_session(token)
        
        # Get brief bibliographic record
        brief_bib = get_brief_bib(clean_oclc, session)
        if not brief_bib:
            return None
        
        # Extract and return mapped data
        extracted_data = extract_bibliographic_data(brief_bib)
        
        # Add the OCLC number to the returned data
        if extracted_data:
            extracted_data['oclc_number'] = clean_oclc
        
        return extracted_data
        
    except ValueError as e:
        # Configuration error (missing credentials)
        logger.error(f"Configuration error: {str(e)}")
        return None
    except Exception as e:
        # Unexpected error
        logger.error(f"Unexpected error in OCLC search: {str(e)}")
        return None

def validate_oclc_number(oclc_number: str) -> bool:
    """
    Validate OCLC number format.
    
    Args:
        oclc_number: OCLC number to validate
        
    Returns:
        bool: True if format appears valid, False otherwise
    """
    if not oclc_number:
        return False
    
    # Remove any non-digit characters
    clean_oclc = ''.join(char for char in oclc_number if char.isdigit())
    
    # OCLC numbers are typically 1-12 digits
    return len(clean_oclc) >= 1 and len(clean_oclc) <= 12

# =============================================================================
# UTILITY FUNCTIONS FOR INTEGRATION
# =============================================================================

def is_oclc_available() -> bool:
    """
    Check if OCLC integration is available and configured.
    
    Returns:
        bool: True if OCLC can be used, False otherwise
    """
    try:
        key = os.getenv('WORLDCAT_API_KEY')
        secret = os.getenv('WORLDCAT_API_SECRET')
        return bool(key and secret)
    except Exception:
        return False

def get_oclc_status() -> Dict[str, Any]:
    """
    Get detailed status of OCLC integration setup.
    
    Returns:
        dict: Status information including configuration and connectivity
    """
    status = {
        'configured': False,
        'credentials_present': False,
        'library_available': False,
        'test_connection': False,
        'message': ''
    }
    
    # Check if bookops_worldcat is available
    try:
        import bookops_worldcat
        status['library_available'] = True
    except ImportError:
        status['message'] = 'bookops_worldcat library not installed'
        return status
    
    # Check credentials
    key = os.getenv('WORLDCAT_API_KEY')
    secret = os.getenv('WORLDCAT_API_SECRET')
    
    if key and secret:
        status['credentials_present'] = True
        status['configured'] = True
        status['message'] = 'OCLC integration ready'
    else:
        status['message'] = 'Missing WorldCat API credentials in environment'
    
    return status

# =============================================================================
# MAIN FUNCTION FOR TESTING
# =============================================================================

def main():
    """Test function to verify OCLC integration."""
    # Test with a known OCLC number
    test_oclc = '1110469890'
    
    print("Testing OCLC WorldCat integration...")
    print(f"Status: {get_oclc_status()}")
    
    if is_oclc_available():
        print(f"\nSearching for OCLC: {test_oclc}")
        data = search_oclc_metadata(test_oclc)
        
        if data:
            print("Retrieved data:")
            for key, value in data.items():
                print(f"  {key}: {value}")
        else:
            print("No data retrieved")
    else:
        print("OCLC integration not available")

if __name__ == "__main__":
    main()