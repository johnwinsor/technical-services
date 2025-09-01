#!/usr/bin/env python

# Amazon CSV to Alma PO Line JSON Converter
# Script Version: 2.0
# Last Updated: 2025-08-18

import csv
import json
import sys
import re
from datetime import datetime, timedelta
import pandas as pd

def clean_asin(asin):
    """Clean ASIN field, removing any extra whitespace"""
    if not asin or pd.isna(asin):
        return ""
    return str(asin).strip()

def extract_isbn_from_asin(asin):
    """
    Extract ISBN from ASIN if it's an ISBN format
    Amazon ASINs that are ISBNs usually start with digits
    """
    if not asin:
        return ""
    
    # Remove any non-alphanumeric characters
    clean_asin = re.sub(r'[^0-9X]', '', str(asin).upper())
    
    # Check if it looks like an ISBN (10 or 13 digits, possibly with X)
    if len(clean_asin) == 10 or len(clean_asin) == 13:
        return clean_asin
    
    return ""

def format_currency_amount(amount):
    """Format currency amount to string with 2 decimal places"""
    try:
        if pd.isna(amount) or amount == "":
            return "0.00"
        return f"{float(amount):.2f}"
    except (ValueError, TypeError):
        return "0.00"

def format_date_for_alma(date_str):
    """Format date string to ISO format with Z suffix for Alma API"""
    try:
        if pd.isna(date_str) or date_str == "":
            return ""
        # Try to parse common date formats
        if isinstance(date_str, str):
            # Try common formats
            for fmt in ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"]:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return f"{dt.strftime('%Y-%m-%d')}Z"
                except ValueError:
                    continue
        return ""
    except:
        return ""

def add_days_to_date(date_str, days):
    """Add specified number of days to a date string and return in Alma format"""
    try:
        if pd.isna(date_str) or date_str == "":
            return ""
        # Try to parse common date formats
        if isinstance(date_str, str):
            # Try common formats
            for fmt in ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"]:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    # Add the specified number of days
                    new_date = dt + timedelta(days=days)
                    return f"{new_date.strftime('%Y-%m-%d')}Z"
                except ValueError:
                    continue
        return ""
    except:
        return ""

def create_amazon_po_line_json(row_data, user_id, reporting_code, notify=None, hold=None, receiving_note="", reserve_note=""):
    """Create JSON structure conforming to Alma po_line schema from Amazon CSV data"""
    
    # Extract key fields from CSV row
    title = row_data.get('Title', '').strip()
    asin = clean_asin(row_data.get('ASIN', ''))
    isbn = extract_isbn_from_asin(asin)
    account_group = row_data.get('Account Group', '').strip()
    brand = row_data.get('Brand', '').strip()
    manufacturer = row_data.get('Manufacturer', '').strip()
    order_id = row_data.get('Order ID', '').strip()
    po_number = row_data.get('PO Number', '').strip()
    price = format_currency_amount(row_data.get('Item Net Total', 0))
    quantity = int(row_data.get('Item Quantity', 1)) if row_data.get('Item Quantity') else 1
    item_type = row_data.get('Amazon-Internal Product Category', '').strip()
    order_date = format_date_for_alma(row_data.get('Order Date', ''))
    expected_date = add_days_to_date(row_data.get('Order Date', ''), 7)  # 7 days after order date
    
    # Material type mapping
    item_type_mapping = {
        "Book": "BOOK",
        "DVD": "DVD", 
        "Toy": "GAME"
    }
    
    mapped_material_type = item_type_mapping.get(item_type, "BOOK")  # Default to BOOK
    
    # Use brand or manufacturer as author if available
    author = brand if brand else manufacturer
    
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
            "value": "amazon"
        },
        "vendor_account": "amazon", 
        "acquisition_method": {
            "value": "VENDOR_SYSTEM",
            "desc": "Purchase at Vendor System"
        },
        "material_type": {
            "value": mapped_material_type
        },
        "additional_order_reference": "punchout purchase",
        "no_charge": "false",
        "rush": "false",
        "cancellation_restriction": "false",
        "cancellation_restriction_note": "",
        "price": {
            "sum": price,
            "currency": {
                "value": "USD"
            }
        },
        "vendor_reference_number": order_id,
        "vendor_reference_number_type": {
            "value": "IA"
        },
        "source_type": {
            "value": "API"
        },
        "resource_metadata": {
            "title": title,
            "author": author,
            "isbn": isbn,
            "vendor_title_number": asin
        },
        "fund_distribution": [
            {
                "amount": {
                    "sum": price,
                    "currency": {
                        "value": "USD",
                        "desc": "US Dollar"
                    }
                },
                "fund_code": {
                    "value": "rnlds",
                    "desc": "Flora Elizabeth Reynolds Book Fund"
                }
            }
        ],
        "reporting_code": reporting_code,
        "vendor_note": f"Amazon Order ID: {order_id}",
        "receiving_note": receiving_note,
        "note": [],
        "location": [
            {
                "quantity": str(quantity),
                "library": {
                    "value": "OLIN"
                },
                "shelving_location": "olord",
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
        ]
    }
    
    # Only add interested_user section if user_id is provided
    if user_id:
        # Convert yes/no to true/false for API
        notify_value = "true" if notify and notify.lower() in ['yes', 'y', 'true'] else "false"
        hold_value = "true" if hold and hold.lower() in ['yes', 'y', 'true'] else "false"
        
        po_line["interested_user"] = [
            {
                "primary_id": user_id,
                "notify_receiving_activation": notify_value,
                "hold_item": hold_value,
                "notify_renewal": "false",
                "notify_cancel": "false"
            }
        ]
    
    # Add expected receipt date if available (7 days after order date)
    if expected_date:
        po_line["expected_receipt_date"] = expected_date
    
    # Add notes if available
    notes = []
    if reserve_note:
        notes.append({"note_text": f"Reserve Note: {reserve_note}"})
    if po_number:
        notes.append({"note_text": f"Amazon PO Number: {po_number}"})
    if asin:
        notes.append({"note_text": f"ASIN: {asin}"})
    if account_group:
        notes.append({"note_text": f"Account Group: {account_group}"})
    
    po_line["note"] = notes
    
    return po_line

def main():
    subjects = ['Archives','Architecture','Art','Biology','Book Art','Business','Chemistry','Communications','Computer Science','Cooking','Dance','Data Science','Economics','Education','English Language Studies','Entrepreneurship','Environmental Science','Ethnic Studies','Fiction','Game Design','General','General Science','Graphic Novels','Health Sciences','History','Juvenile','Library Science','Mathematics','Music','Philosophy','Poetry','Political Science','Psychology','Public Policy','Religion','Sociology','Theatre','WGSS']
    
    if len(sys.argv) != 2:
        print("Usage: python amazon_csv_to_json.py <csv_filename>")
        sys.exit(1)
    
    csv_filename = sys.argv[1]
    
    # Configuration - adjust these as needed
    user_id = "002630546"  # Default interested user ID
    reporting_code = "General"
    
    processed_count = 0
    error_count = 0
    
    print(f"Processing Amazon CSV file: {csv_filename}")
    print("-" * 50)
    
    try:
        # Read CSV file
        with open(csv_filename, 'r', encoding='utf-8') as csvfile:
            # Detect delimiter
            sample = csvfile.read(1024)
            csvfile.seek(0)
            sniffer = csv.Sniffer()
            delimiter = sniffer.sniff(sample).delimiter
            
            reader = csv.DictReader(csvfile, delimiter=delimiter)
            
            for i, row in enumerate(reader, 1):
                try:
                    # Skip rows without title or ASIN
                    if not row.get('Title', '').strip() or not row.get('ASIN', '').strip():
                        print(f"⚠ Skipping row {i}: Missing title or ASIN")
                        continue
                    
                    print(f"Processing row {i}: {row.get('Title', 'N/A')[:60]}...")
                    
                    val = input("Enter Valid Subject: ")
                    while val not in subjects:
                        print(f'Try again. Valid Subjects are: {subjects}')
                        val = input("Enter Valid Subject: ")
                    reporting_code = val
                    
                    receiving_note = input("Enter Receiving Note (optional): ").strip()
                    reserve_note = input("Enter Reserve Note (optional): ").strip()
                    
                    user_id = input("Enter Interested User (9 digits, or press Enter for none): ").strip()
                    while user_id and not (user_id.isdigit() and len(user_id) == 9):
                        print("Invalid user ID. Please enter exactly 9 digits or press Enter for none.")
                        user_id = input("Enter Interested User (9 digits, or press Enter for none): ").strip()
                    
                    # Convert empty string to None for cleaner handling
                    user_id = user_id if user_id else None
                    
                    # Initialize notify and hold variables
                    notify = None
                    hold = None
                    
                    if user_id:
                        notify = input("Notify user on receiving activation? (yes/no/true/false): ").strip().lower()
                        while notify not in ['yes', 'no', 'y', 'n', 'true', 'false']:
                            print("Please enter yes, no, true, or false")
                            notify = input("Notify user on receiving activation? (yes/no/true/false): ").strip().lower()
                        
                        hold = input("Hold item for user? (yes/no/true/false): ").strip().lower()
                        while hold not in ['yes', 'no', 'y', 'n', 'true', 'false']:
                            print("Please enter yes, no, true, or false")
                            hold = input("Hold item for user? (yes/no/true/false): ").strip().lower()
                    
                    # Create JSON structure
                    po_line_json = create_amazon_po_line_json(row, user_id, reporting_code, notify, hold, receiving_note, reserve_note)
                    
                    # Create output filename based on ASIN
                    asin = clean_asin(row.get('ASIN', ''))
                    order_id = row.get('Order ID', '').strip().replace(' ', '_')
                    output_filename = f"amazon_{asin}_{order_id}.json"
                    
                    # Write JSON file
                    with open(output_filename, 'w', encoding='utf-8') as json_file:
                        json.dump(po_line_json, json_file, indent=4, ensure_ascii=False)
                    
                    print(f"✓ Created: {output_filename}")
                    print(f"  Title: {row.get('Title', 'N/A')[:60]}...")
                    print(f"  ASIN: {asin}")
                    print(f"  Price: ${format_currency_amount(row.get('Item Net Total', 0))}")
                    processed_count += 1
                    
                except Exception as e:
                    print(f"✗ Error processing row {i}: {str(e)}")
                    error_count += 1
                    continue
                    
    except FileNotFoundError:
        print(f"Error: Could not find file '{csv_filename}'")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading CSV file: {str(e)}")
        sys.exit(1)
    
    print("-" * 50)
    print(f"Processing complete!")
    print(f"Successfully processed: {processed_count} records")
    print(f"Errors encountered: {error_count} records")
    print(f"JSON files created in current directory")

if __name__ == "__main__":
    main()