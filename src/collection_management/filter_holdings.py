import pandas as pd
import re
import sys
import os

def parse_alma_holdings(excel_file_path):
    """
    Parse Alma export Excel file to find MMSIDs where all holdings 
    are in suppressed locations (matching 'olwdfy' pattern).
    
    Args:
        excel_file_path (str): Path to the Excel file
        
    Returns:
        list: List of MMSIDs where all holdings are in suppressed locations
    """
    
    # Read the Excel file
    df = pd.read_excel(excel_file_path)
    
    # List to store MMSIDs that meet our criteria
    suppressed_only_mmsids = []
    
    for index, row in df.iterrows():
        mms_id = row['MMS ID']
        physical_availability = row['Physical Availability']
        
        # Skip if no physical availability data
        if pd.isna(physical_availability):
            continue
            
        # Parse the physical availability string to extract locations
        locations = extract_locations(physical_availability)
        
        if not locations:
            continue
            
        # Check if ALL locations match the suppressed pattern (olwdfy)
        all_suppressed = all(location.startswith('olwdfy') for location in locations)
        
        if all_suppressed:
            suppressed_only_mmsids.append(mms_id)
            print(f"Found suppressed-only title: {mms_id}")
            print(f"  Locations: {locations}")
            print(f"  Physical Availability: {physical_availability[:100]}...")
            print()
    
    return suppressed_only_mmsids

def extract_locations(physical_availability_text):
    """
    Extract location codes from the Physical Availability text.
    
    Format: "Physical version at [LOCATION]; [LIBRARY]; [CALL_NUMBER]; (X items out of Y available)"
    
    Args:
        physical_availability_text (str): The Physical Availability column text
        
    Returns:
        list: List of location codes found in the text
    """
    locations = []
    
    # Split by newlines to handle multiple holdings
    lines = physical_availability_text.split('\n')
    
    for line in lines:
        line = line.strip()
        if line.startswith('Physical version at '):
            # Use regex to extract the location code after "Physical version at "
            match = re.match(r'Physical version at ([a-zA-Z0-9]+);', line)
            if match:
                location = match.group(1)
                locations.append(location)
    
    return locations

def main():
    """
    Main function to process the Excel file and output results.
    """
    # Check for command line argument
    if len(sys.argv) != 2:
        print("Usage: python alma_holdings_parser.py <excel_file_path>")
        print("Example: python alma_holdings_parser.py 'All titles export 5.xlsx'")
        sys.exit(1)
    
    excel_file = sys.argv[1]
    
    # Check if file exists
    if not os.path.exists(excel_file):
        print(f"Error: File '{excel_file}' not found.")
        print("Please check the file path and try again.")
        sys.exit(1)
    
    print(f"Processing Alma holdings export: {excel_file}")
    print("Looking for titles with ALL holdings in suppressed locations (olwdfy pattern)")
    print("=" * 70)
    
    try:
        suppressed_mmsids = parse_alma_holdings(excel_file)
        
        print("=" * 70)
        print(f"SUMMARY: Found {len(suppressed_mmsids)} titles with all holdings in suppressed locations")
        print("\nMMS IDs to process for OCLC removal:")
        
        for mms_id in suppressed_mmsids:
            print(mms_id)
            
        # Save to a text file with name based on input file
        if suppressed_mmsids:
            base_name = os.path.splitext(os.path.basename(excel_file))[0]
            output_file = f'{base_name}_suppressed_only_mmsids.csv'
            with open(output_file, 'w') as f:
                f.write(f"MMS ID\n")
                for mms_id in suppressed_mmsids:
                    f.write(f"{mms_id}\n")
            print(f"\nResults also saved to: {output_file}")
        else:
            print("\nNo titles found with all holdings in suppressed locations.")
        
    except Exception as e:
        print(f"Error processing file: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()