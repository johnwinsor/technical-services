#!/usr/bin/env python

from pymarc import MARCReader
from pymarc import exceptions as exc
import sys
import json
import re
from datetime import datetime

def clean_isbn(isbn_field):
    """Extract clean ISBN from field, removing any extra text"""
    if not isbn_field:
        return ""
    # Extract just digits and hyphens/X from ISBN
    isbn_clean = re.findall(r'[\d\-Xx]+', isbn_field)
    return isbn_clean[0] if isbn_clean else ""

def format_date(date_str):
    """Format date string to ISO format with Z suffix for Alma API"""
    try:
        # If date_str is in YYYYMMDD format, convert to ISO
        if len(date_str) == 8 and date_str.isdigit():
            year = date_str[:4]
            month = date_str[4:6]
            day = date_str[6:8]
            return f"{year}-{month}-{day}Z"
        return date_str
    except:
        return date_str

def extract_marc_data(record):
    """Extract relevant data from MARC record"""
    data = {}
    
    # Control number (001)
    if record['001']:
        data['control_number'] = str(record['001'].format_field()).strip()
    
    # ISBN (020$a)
    if record['020'] and record['020']['a']:
        data['isbn'] = clean_isbn(record['020']['a'])
    
    # Title (245$a) - use pymarc's built-in title method
    data['title'] = record.title if record.title else ""
    
    # Main author (100$a)
    if record['100'] and record['100']['a']:
        data['author'] = record['100']['a'].strip()
    
    # Age/Grade level (521$a)
    if record['521'] and record['521']['a']:
        data['age_grade'] = record['521']['a'].strip()
    
    return data

def create_po_line_json(marc_data, jlg_month, expected_date, user_id, pol_number):
    """Create JSON structure conforming to Alma po_line schema"""
    
    po_line = {
        "link": "",
        "owner": {
            "value": "OLIN",
            "desc": "F.W. Olin Library"
        },
        "type": {
            "value": "PRINTED_BOOK_OT",
            "desc": "Print Book - One Time"
        },
        "vendor": {
            "value": "jlg-m"
        },
        "vendor_account": "jlg-m",
        "acquisition_method": {
            "value": "TECHNICAL"
        },
        "no_charge": "false",
        "rush": "false",
        "cancellation_restriction": "false",
        "cancellation_restriction_note": "",
        "price": {
            "sum": "0.00",
            "currency": {
                "value": "USD"
            }
        },
        "vendor_reference_number": marc_data.get('control_number', ''),
        "vendor_reference_number_type": {
            "value": "SCO"
        },
        "source_type": {
            "value": "API"
        },
        "additional_order_reference": pol_number,
        "resource_metadata": {
            "title": marc_data.get('title', ''),
            "author": marc_data.get('author', ''),
            "issn": "",
            "isbn": marc_data.get('isbn', '')
        },
        "reporting_code": "Juvenile",
        "vendor_note": "",
        "receiving_note": "JLG",
        "note": [],
        "location": [
            {
                "quantity": "1",
                "library": {
                    "value": "OLIN"
                },
                "shelving_location": "oljuv",
                "copy": [
                    {
                        "item_policy": {
                            "value": "40"
                        },
                        "is_temp_location": "false",
                        "permanent_library": {
                            "value": ""
                        },
                        "permanent_shelving_location": ""
                    }
                ]
            }
        ],
        "interested_user": [
            {
                "primary_id": user_id,
                "notify_receiving_activation": "false",
                "hold_item": "false",
                "notify_renewal": "false",
                "notify_cancel": "false"
            }
        ],
        "material_type": {
            "value": "BOOK"
        },
        "expected_receipt_date": format_date(expected_date)
    }
    
    # Add notes if available
    notes = []
    if marc_data.get('age_grade'):
        notes.append({"note_text": marc_data['age_grade']})
    if jlg_month:
        notes.append({"note_text": jlg_month})
    
    po_line["note"] = notes
    
    return po_line

def main():
    if len(sys.argv) != 2:
        print("Usage: python script.py <marc_filename>")
        sys.exit(1)
    
    filename = sys.argv[1]
    
    # Get input parameters
    jlg_month = input("Enter JLG Shipment Month (Mon YYYY): ")
    expected_date = input("Enter Expected Receiving Date (YYYYMMDD): ")
    
    # Default values (can be made configurable)
    user_id = "002630546"  # Maura's user ID
    base_pol_number = "POL-139866"  # JLG subscription POL number
    
    processed_count = 0
    error_count = 0
    
    print(f"Processing MARC file: {filename}")
    print("-" * 50)
    
    try:
        with open(filename, 'rb') as fh:
            reader = MARCReader(fh)
            
            for i, record in enumerate(reader, 1):
                try:
                    if record:
                        # Extract data from MARC record
                        marc_data = extract_marc_data(record)
                        
                        # Generate unique POL number (you might want to modify this logic)
                        pol_number = f"{base_pol_number}"
                        
                        # Create JSON structure
                        po_line_json = create_po_line_json(
                            marc_data, jlg_month, expected_date, user_id, pol_number
                        )
                        
                        # Create output filename based on control number or sequence
                        control_num = marc_data.get('control_number', f'record_{i:04d}')
                        output_filename = f"{control_num}.json"
                        
                        # Write JSON file
                        with open(output_filename, 'w', encoding='utf-8') as json_file:
                            json.dump(po_line_json, json_file, indent=4, ensure_ascii=False)
                        
                        print(f"✓ Created: {output_filename}")
                        print(f"  Title: {marc_data.get('title', 'N/A')[:60]}...")
                        print(f"  Control#: {marc_data.get('control_number', 'N/A')}")
                        processed_count += 1
                        
                    else:
                        # Handle reader errors
                        if isinstance(reader.current_exception, exc.FatalReaderError):
                            print(f"✗ Fatal error in record {i}: {reader.current_exception}")
                            error_count += 1
                        else:
                            print(f"✗ Error in record {i}: {reader.current_exception}")
                            error_count += 1
                            
                except Exception as e:
                    print(f"✗ Error processing record {i}: {str(e)}")
                    error_count += 1
                    continue
                    
    except FileNotFoundError:
        print(f"Error: Could not find file '{filename}'")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading MARC file: {str(e)}")
        sys.exit(1)
    
    print("-" * 50)
    print(f"Processing complete!")
    print(f"Successfully processed: {processed_count} records")
    print(f"Errors encountered: {error_count} records")
    print(f"JSON files created in current directory")

if __name__ == "__main__":
    main()