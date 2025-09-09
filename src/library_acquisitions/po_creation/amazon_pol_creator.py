#!/usr/bin/env python

"""
Amazon CSV to Alma PO Line JSON Converter
Converts Amazon purchase CSV files to Alma library system PO line JSON format
"""

import csv
import json
import sys
import re
import os
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional, Dict, List, Any

import pandas as pd
import questionary
import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from dotenv import load_dotenv

load_dotenv()
console = Console()

# Configuration and Data Classes
@dataclass
class AlmaConfig:
    api_key: str
    base_url: str
    
    @classmethod
    def from_env(cls):
        api_key = os.getenv('ALMA_API_KEY')
        base_url = os.getenv('ALMA_BASE_URL', 'https://api-na.hosted.exlibrisgroup.com')
        
        if not api_key:
            console.print("Error: ALMA_API_KEY environment variable not set!", style="bold red")
            sys.exit(1)
        
        return cls(api_key=api_key, base_url=base_url)

@dataclass
class POLineData:
    """Data structure for a PO line with both CSV data and user-added metadata"""
    # Core CSV data
    title: str
    order_id: str
    asin: str
    price: float
    quantity: int
    brand: str = ""
    manufacturer: str = ""
    account_group: str = ""
    po_number: str = ""
    order_date: str = ""
    csv_receiving_note: str = ""
    
    # User-added metadata
    subject: str = ""
    receiving_note_categories: List[str] = None
    additional_note: str = ""
    reserve_note: str = ""
    interested_user_id: str = ""
    notify_user: bool = False
    hold_for_user: bool = False
    
    def __post_init__(self):
        if self.receiving_note_categories is None:
            self.receiving_note_categories = []

# Constants
SUBJECTS = [
    'Archives', 'Architecture', 'Art', 'Biology', 'Book Art', 'Business',
    'Chemistry', 'Communications', 'Computer Science', 'Cooking', 'Dance',
    'Data Science', 'Economics', 'Education', 'English Language Studies',
    'Entrepreneurship', 'Environmental Science', 'Ethnic Studies', 'Fiction',
    'Game Design', 'General', 'General Science', 'Graphic Novels',
    'Health Sciences', 'History', 'Juvenile', 'Library Science', 'Mathematics',
    'Music', 'Philosophy', 'Poetry', 'Political Science', 'Psychology',
    'Public Policy', 'Religion', 'Sociology', 'Theatre', 'WGSS'
]

RECEIVING_CATEGORIES = ['None', 'Note', 'Interested User', 'Reserve', 'Display', 'Replacement']

# Utility Functions
def clean_asin(asin) -> str:
    """Clean ASIN field, removing any extra whitespace"""
    if not asin or pd.isna(asin):
        return ""
    return str(asin).strip()

def format_currency_amount(amount) -> str:
    """Format currency amount to string with 2 decimal places"""
    try:
        if pd.isna(amount) or amount == "":
            return "0.00"
        return f"{float(amount):.2f}"
    except (ValueError, TypeError):
        return "0.00"

def extract_isbn_from_asin(asin: str) -> str:
    """Extract ISBN from ASIN if it's an ISBN format"""
    if not asin:
        return ""
    
    clean_asin_val = re.sub(r'[^0-9X]', '', str(asin).upper())
    if len(clean_asin_val) in [10, 13]:
        return clean_asin_val
    return ""

def format_date_for_alma(date_str: str) -> str:
    """Format date string to ISO format with Z suffix for Alma API"""
    if not date_str or pd.isna(date_str):
        return ""
    
    for fmt in ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"]:
        try:
            dt = datetime.strptime(str(date_str), fmt)
            return f"{dt.strftime('%Y-%m-%d')}Z"
        except ValueError:
            continue
    return ""

def add_days_to_date(date_str: str, days: int) -> str:
    """Add specified number of days to a date string and return in Alma format"""
    if not date_str or pd.isna(date_str):
        return ""
    
    for fmt in ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"]:
        try:
            dt = datetime.strptime(str(date_str), fmt)
            new_date = dt + timedelta(days=days)
            return f"{new_date.strftime('%Y-%m-%d')}Z"
        except ValueError:
            continue
    return ""

# Alma API Functions
def validate_user_in_alma(user_id: str, config: AlmaConfig) -> Optional[str]:
    """Validate user ID against Alma API and return full name if found"""
    if not user_id or not config:
        return None
    
    url = f"{config.base_url}/almaws/v1/users/{user_id}"
    params = {'apikey': config.api_key, 'view': 'brief'}
    headers = {'accept': 'application/json', 'Content-Type': 'application/json'}
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        if response.status_code == 200:
            user_data = response.json()
            first_name = user_data.get('first_name', '')
            last_name = user_data.get('last_name', '')
            return f"{first_name} {last_name}".strip()
    except Exception:
        pass
    return None

# Data Processing Functions
def parse_csv_row(row: Dict[str, Any]) -> Optional[POLineData]:
    """Parse a CSV row into POLineData structure"""
    title = str(row.get('Title', '')).strip()
    asin = clean_asin(row.get('ASIN', ''))
    
    if not title or not asin:
        return None
    
    return POLineData(
        title=title,
        order_id=str(row.get('Order ID', '')).strip(),
        asin=asin,
        price=float(format_currency_amount(row.get('Item Net Total', 0))),
        quantity=int(row.get('Item Quantity', 1)) if row.get('Item Quantity') else 1,
        brand=str(row.get('Brand', '')).strip(),
        manufacturer=str(row.get('Manufacturer', '')).strip(),
        account_group=str(row.get('Account Group', '')).strip(),
        po_number=str(row.get('PO Number', '')).strip(),
        order_date=str(row.get('Order Date', '')).strip(),
        csv_receiving_note=str(row.get('Receiving Note', '')).strip()
    )

def create_po_line_json(data: POLineData) -> Dict[str, Any]:
    """Create the complete PO line JSON structure"""
    expected_date = add_days_to_date(data.order_date, 7)
    price_str = f"{data.price:.2f}"
    
    # Material type mapping
    item_type_mapping = {"Book": "BOOK", "DVD": "DVD", "Toy": "GAME"}
    mapped_material_type = "BOOK"  # Default
    
    # Use brand or manufacturer as author
    author = data.brand if data.brand else data.manufacturer
    
    po_line = {
        "owner": {"value": "OLIN", "desc": "F.W. Olin Library"},
        "type": {"value": "PRINTED_BOOK_OT", "desc": "Print Book - One Time"},
        "vendor": {"value": "amazon"},
        "vendor_account": "amazon",
        "acquisition_method": {"value": "VENDOR_SYSTEM", "desc": "Purchase at Vendor System"},
        "material_type": {"value": mapped_material_type},
        "additional_order_reference": "punchout purchase",
        "no_charge": "false",
        "rush": "false",
        "cancellation_restriction": "false",
        "price": {"sum": price_str, "currency": {"value": "USD"}},
        "vendor_reference_number": data.order_id,
        "vendor_reference_number_type": {"value": "IA"},
        "source_type": {"value": "API"},
        "resource_metadata": {
            "title": data.title,
            "author": author,
            "isbn": extract_isbn_from_asin(data.asin),
            "vendor_title_number": data.asin
        },
        "fund_distribution": [{
            "amount": {"sum": price_str, "currency": {"value": "USD", "desc": "US Dollar"}},
            "fund_code": {"value": "rnlds", "desc": "Flora Elizabeth Reynolds Book Fund"}
        }],
        "reporting_code": data.subject,
        "vendor_note": f"Amazon Order ID: {data.order_id}",
        "receiving_note": " | ".join(data.receiving_note_categories) if data.receiving_note_categories and "None" not in data.receiving_note_categories else "None",
        "location": [{
            "quantity": str(data.quantity),
            "library": {"value": "OLIN"},
            "shelving_location": "olord",
            "copy": [{
                "item_policy": {"value": "40"},
                "is_temp_location": "false",
                "permanent_library": {"value": ""},
                "permanent_shelving_location": ""
            }]
        }]
    }
    
    # Add expected receipt date
    if expected_date:
        po_line["expected_receipt_date"] = expected_date
    
    # Add interested user if specified
    if data.interested_user_id:
        po_line["interested_user"] = [{
            "primary_id": data.interested_user_id,
            "notify_receiving_activation": "true" if data.notify_user else "false",
            "hold_item": "true" if data.hold_for_user else "false",
            "notify_renewal": "false",
            "notify_cancel": "false"
        }]
    
    # Add notes
    notes = []
    if data.reserve_note:
        notes.append({"note_text": f"Reserve Note: {data.reserve_note}"})
    if data.additional_note:
        notes.append({"note_text": data.additional_note})
    if data.po_number:
        notes.append({"note_text": f"Amazon PO Number: {data.po_number}"})
    if data.asin:
        notes.append({"note_text": f"ASIN: {data.asin}"})
    if data.account_group:
        notes.append({"note_text": f"Account Group: {data.account_group}"})
    
    if notes:
        po_line["note"] = notes
    
    return po_line

# User Interface Functions
def display_item_info(data: POLineData):
    """Display current item information"""
    table = Table(title="Current Item", show_header=True, header_style="bold magenta")
    table.add_column("Field", style="cyan", width=18)
    table.add_column("Value", style="white", width=62)
    
    table.add_row("Title", data.title[:60] + "..." if len(data.title) > 60 else data.title)
    table.add_row("Order ID", data.order_id)
    table.add_row("CSV Receiving Note", data.csv_receiving_note or "None")
    table.add_row("Price", f"${data.price:.2f}")
    table.add_row("Quantity", str(data.quantity))
    
    console.print(table)

def get_user_metadata(data: POLineData, alma_config: Optional[AlmaConfig]) -> POLineData:
    """Collect user-specified metadata for the item"""
    
    # Subject
    data.subject = questionary.autocomplete(
        "Subject:",
        choices=SUBJECTS,
        default="",
        validate=lambda text: text in SUBJECTS or "Please select a valid subject"
    ).ask()
    
    # Receiving note categories
    data.receiving_note_categories = questionary.checkbox(
        "Receiving note categories:",
        choices=RECEIVING_CATEGORIES
    ).ask()
    
    # Handle None selection
    if not data.receiving_note_categories or "None" in data.receiving_note_categories:
        data.receiving_note_categories = ["None"]
    
    # Additional metadata based on categories
    if "Note" in data.receiving_note_categories:
        data.additional_note = questionary.text("Additional notes:").ask() or ""
    
    if "Reserve" in data.receiving_note_categories:
        data.reserve_note = questionary.text("Reserve note:").ask() or ""
    
    if "Interested User" in data.receiving_note_categories:
        while True:
            user_id = questionary.text(
                "User ID (9 digits):",
                validate=lambda text: len(text.strip()) == 9 and text.strip().isdigit() or "Must be exactly 9 digits"
            ).ask()
            
            # Validate against Alma if possible
            if alma_config:
                console.print("Validating user...", style="yellow")
                user_name = validate_user_in_alma(user_id, alma_config)
                if user_name:
                    if questionary.confirm(f"Found user: {user_name} (ID: {user_id}). Use this user?").ask():
                        data.interested_user_id = user_id
                        break
                    else:
                        continue
                else:
                    console.print("User not found in Alma", style="yellow")
                    if questionary.confirm("Use this user ID anyway?").ask():
                        data.interested_user_id = user_id
                        break
                    else:
                        continue
            else:
                data.interested_user_id = user_id
                break
        
        data.notify_user = questionary.confirm("Notify user on receiving activation?", default=True).ask()
        data.hold_for_user = questionary.confirm("Hold item for user?", default=False).ask()
    
    return data

def display_summary(data: POLineData, filename: str):
    """Display summary of the item to be saved"""
    table = Table(title="Item Summary", show_header=True, header_style="bold magenta")
    table.add_column("Field", style="cyan", width=20)
    table.add_column("Value", style="white", width=50)
    
    table.add_row("Title", data.title[:50] + "..." if len(data.title) > 50 else data.title)
    table.add_row("Subject", data.subject)
    table.add_row("Receiving Note", " | ".join(data.receiving_note_categories))
    
    if data.interested_user_id:
        user_text = f"{data.interested_user_id} (notify: {data.notify_user}, hold: {data.hold_for_user})"
        table.add_row("Interested User", user_text)
    
    table.add_row("Output File", filename)
    console.print(table)

def save_po_line(data: POLineData, csv_path: str) -> str:
    """Save the PO line JSON to a file in the same directory as the CSV"""
    csv_dir = os.path.dirname(os.path.abspath(csv_path))
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"amazon_{data.asin}_{data.order_id.replace(' ', '_')}_{timestamp}.json"
    filepath = os.path.join(csv_dir, filename)
    
    po_json = create_po_line_json(data)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(po_json, f, indent=4, ensure_ascii=False)
    
    return filename

# Main Processing Function
def process_csv_file(csv_path: str):
    """Main processing function"""
    console.print(Panel.fit("Amazon CSV to Alma PO Line Converter", style="bold blue"))
    
    # Initialize Alma config if possible
    alma_config = None
    try:
        alma_config = AlmaConfig.from_env()
        console.print("Alma API configuration loaded", style="green")
    except SystemExit:
        if questionary.confirm("Continue without Alma API integration?").ask():
            console.print("Continuing without user validation", style="yellow")
        else:
            sys.exit(1)
    
    # Read CSV
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            sample = f.read(1024)
            f.seek(0)
            delimiter = csv.Sniffer().sniff(sample).delimiter
            reader = csv.DictReader(f, delimiter=delimiter)
            rows = list(reader)
    except Exception as e:
        console.print(f"[bold red]Error reading CSV: {e}[/bold red]")
        sys.exit(1)
    
    console.print(f"Found {len(rows)} rows in CSV file", style="green")
    
    # Process confirmation
    if not questionary.confirm(f"Process all {len(rows)} items?").ask():
        rows = rows[:5]
        console.print("Processing first 5 items only", style="yellow")
    
    # Process each row
    processed = 0
    skipped = 0
    errors = 0
    
    for i, row in enumerate(rows, 1):
        try:
            console.print(f"\n{'='*60}")
            console.print(f"Processing item {i} of {len(rows)}", style="bold blue")
            
            # Parse CSV data
            po_data = parse_csv_row(row)
            if not po_data:
                console.print("Skipping - missing title or ASIN", style="yellow")
                skipped += 1
                continue
            
            # Display item info
            display_item_info(po_data)
            
            # Get user metadata
            po_data = get_user_metadata(po_data, alma_config)
            
            # Generate filename and show summary
            csv_dir = os.path.dirname(os.path.abspath(csv_path))
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"amazon_{po_data.asin}_{po_data.order_id.replace(' ', '_')}_{timestamp}.json"
            
            display_summary(po_data, filename)
            
            # Save confirmation
            action = questionary.select(
                "What would you like to do?",
                choices=[
                    questionary.Choice("Save this PO", "save"),
                    questionary.Choice("Skip this item", "skip"),
                    questionary.Choice("Stop processing", "stop")
                ]
            ).ask()
            
            if action == "save":
                saved_filename = save_po_line(po_data, csv_path)
                console.print(f"Saved: {saved_filename}", style="green")
                console.print(f"Location: {csv_dir}", style="dim")
                processed += 1
            elif action == "skip":
                console.print("Skipped", style="yellow")
                skipped += 1
            else:
                break
                
        except KeyboardInterrupt:
            console.print("\nInterrupted by user", style="yellow")
            break
        except Exception as e:
            console.print(f"Error processing item {i}: {e}", style="red")
            errors += 1
    
    # Final summary
    console.print(f"\n{'='*60}")
    summary_table = Table(title="Processing Summary")
    summary_table.add_column("Status", style="cyan")
    summary_table.add_column("Count", style="white")
    
    summary_table.add_row("Processed", str(processed))
    summary_table.add_row("Skipped", str(skipped))
    summary_table.add_row("Errors", str(errors))
    
    console.print(summary_table)
    console.print(f"Files saved to: {os.path.dirname(os.path.abspath(csv_path))}", style="green")

def main():
    """Main entry point"""
    if len(sys.argv) != 2:
        console.print("Usage: python amazon_pol_creator.py <csv_filename>", style="bold red")
        
        if questionary.confirm("Enter filename interactively?").ask():
            csv_path = questionary.path(
                "CSV file path:",
                validate=lambda path: os.path.exists(path) or f"File '{path}' does not exist"
            ).ask()
        else:
            sys.exit(1)
    else:
        csv_path = sys.argv[1]
    
    if not os.path.exists(csv_path):
        console.print(f"File not found: {csv_path}", style="bold red")
        sys.exit(1)
    
    try:
        process_csv_file(csv_path)
    except KeyboardInterrupt:
        console.print("\nGoodbye!", style="cyan")

if __name__ == "__main__":
    main()