#!/usr/bin/env python

"""
Simplified PO Line Creator
Creates Alma PO Line JSON files by collecting all information from user input
"""

import json
import os
import sys
from datetime import datetime, timedelta
import re
import requests
from dataclasses import dataclass
from dotenv import load_dotenv
import questionary
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Try to import OCLC helpers - graceful fallback if not available
try:
    from .oclc_helpers import search_oclc_metadata, is_oclc_available, validate_oclc_number
    OCLC_AVAILABLE = True
    print
except ImportError:
    OCLC_AVAILABLE = False
    print("OCLC WorldCat integration not available. Proceeding without it.")

load_dotenv()
console = Console()

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

# =============================================================================
# USER INPUT COLLECTION
# =============================================================================

def get_order_information(config: AlmaConfig):
    """Collect all order information from user input."""
    
    subjects = [
        'Archives', 'Architecture', 'Art', 'Biology', 'Book Art', 'Business',
        'Chemistry', 'Communications', 'Computer Science', 'Cooking', 'Dance',
        'Data Science', 'Economics', 'Education', 'English Language Studies',
        'Entrepreneurship', 'Environmental Science', 'Ethnic Studies', 'Fiction',
        'Game Design', 'General', 'General Science', 'Graphic Novels',
        'Health Sciences', 'History', 'Juvenile', 'Library Science', 'Mathematics',
        'Music', 'Philosophy', 'Poetry', 'Political Science', 'Psychology',
        'Public Policy', 'Religion', 'Sociology', 'Theatre', 'WGSS'
    ]
    
    console.print(Panel.fit("Order Information", style="bold blue"))
    
    # Basic order info
    
    # Material type
    acquisition_method = questionary.select(
        "Acquisition Method:",
        choices=["VENDOR_SYSTEM", "TECHNICAL"]
    ).ask()
    
    vendor_code = questionary.text(
        "Vendor code:",
        validate=lambda text: len(text.strip()) > 0 or "Vendor code is required"
    ).ask()
    
    vendor_account = questionary.text(
        "Vendor account:",
        validate=lambda text: len(text.strip()) > 0 or "Vendor account is required"
    ).ask()
    
    vendor_ref = questionary.text("Vendor reference/invoice number:").ask()
    
    # Order type
    order_type = questionary.select(
        "Order type:",
        choices=[
            questionary.Choice("Print Book - One Time", "PRINTED_BOOK_OT"),
            questionary.Choice("Print Book - Standing Order", "PRINTED_BOOK_SO"),
            questionary.Choice("Print Journal - Subscription", "PRINTED_JOURNAL_CO"),
            questionary.Choice("Manuscript", "MANUSCRIPT"),
            questionary.Choice("Mixed Material", "MIXED"),
            questionary.Choice("Musical Score", "SCORE_OT"),
            questionary.Choice("Visual Material", "VISUAL_MTL_OT")
        ],
        default="PRINTED_BOOK_OT"
    ).ask()
    
    # Material type
    material_type = questionary.select(
        "Material type:",
        choices=["BOOK", "RARE", "DVD", "JOURNAL", "OTHER"]
    ).ask()
    
    # OCLC search option
    oclc_data = {}
    used_oclc_number = None
    
    if OCLC_AVAILABLE and is_oclc_available():
        use_oclc = questionary.confirm("Search OCLC WorldCat for bibliographic data?").ask()
        
        if use_oclc:
            oclc_number = questionary.text(
                "Enter OCLC number:",
                validate=lambda text: validate_oclc_number(text) if text.strip() else "OCLC number is required"
            ).ask()
            
            if oclc_number:
                console.print("Searching OCLC WorldCat...", style="yellow")
                oclc_data = search_oclc_metadata(oclc_number)
                used_oclc_number = oclc_data.get('oclc_number') if oclc_data else None
                
                if oclc_data:
                    console.print("Found bibliographic data from OCLC!", style="green")
                else:
                    console.print("No data found for that OCLC number", style="yellow")
    
    # Bibliographic information
    title = questionary.text(
        "Title:",
        default=oclc_data.get('title', ''),
        validate=lambda text: len(text.strip()) > 0 or "Title is required"
    ).ask()
    
    author = questionary.text(
        "Author:",
        default=oclc_data.get('author', '')
    ).ask()
    
    isbn = questionary.text(
        "ISBN:",
        default=oclc_data.get('isbn', '')
    ).ask()
    
    publisher = questionary.text(
        "Publisher:",
        default=oclc_data.get('publisher', '')
    ).ask()
    
    publication_year = questionary.text(
        "Publication year:",
        default=oclc_data.get('publication_year', '')
    ).ask()
    
    # Order details
    price = questionary.text(
        "Price:",
        validate=lambda text: validate_price(text)
    ).ask()
    
    quantity = questionary.text(
        "Quantity:",
        default="1",
        validate=lambda text: text.isdigit() and int(text) > 0 or "Must be a positive number"
    ).ask()
    
    # Additional order reference
    additional_order_ref_initial = questionary.select(
        "Additional order reference:",
        choices=[
            questionary.Choice("None", ""),
            questionary.Choice("pcard purchase", "pcard purchase"),
            questionary.Choice("punchout purchase", "punchout purchase"),
            questionary.Separator(), # Adds a visual separator
            questionary.Choice("Other (please specify)", "other")
        ]
    ).ask()
    
    # An empty response can happen if the user hits Ctrl+C
    if additional_order_ref_initial is None:
        additional_order_ref = ""
    # Step 2: If 'Other' was chosen, ask for custom text input
    elif additional_order_ref_initial == "other":
        additional_order_ref = questionary.text("Please specify the reference:").ask()
    # Otherwise, use the choice they selected
    else:
        additional_order_ref = additional_order_ref_initial
    
    # Fund
    fund_code = questionary.text(
        "Fund code:",
        default="rnlds",
        validate=lambda text: len(text.strip()) > 0 or "Fund code is required"
    ).ask()
    
    reporting_code = questionary.autocomplete(
        "Reporting code:",
        choices=subjects,
        validate=lambda text: text in subjects or "Please select a valid subject"
    ).ask()
    
    # Receiving categories
    receiving_categories = questionary.checkbox(
        "Receiving note categories:",
        choices=["None", "Note", "Interested User", "Reserve", "Display", "Replacement"],
        validate=lambda selected: validate_receiving_categories(selected)
    ).ask()
    
    # Handle conditional data
    conditional_data = {}
    
    if "Interested User" in receiving_categories:
        interested_users = collect_interested_users(config)
        if interested_users:
            conditional_data['interested_users'] = interested_users
    
    if "Note" in receiving_categories:
        additional_notes = questionary.text("Additional notes:").ask()
        conditional_data['additional_notes'] = additional_notes or ''
    
    if "Reserve" in receiving_categories:
        reserve_note = questionary.text("Reserve note:").ask()
        conditional_data['reserve_note'] = reserve_note or ''
    
    return {
        'acquisition_method': acquisition_method,
        'vendor_code': vendor_code,
        'vendor_account': vendor_account,
        'vendor_reference_number': vendor_ref,
        'order_type': order_type,
        'material_type': material_type,
        'title': title,
        'author': author,
        'isbn': isbn,
        'publisher': publisher,
        'publication_year': publication_year,
        'price': price,
        'quantity': int(quantity),
        'additional_order_reference': additional_order_ref,
        'fund_code': fund_code,
        'reporting_code': reporting_code,
        'receiving_categories': " | ".join(receiving_categories) if receiving_categories and "None" not in receiving_categories else "None",
        'oclc_number': used_oclc_number,
        'conditional_data': conditional_data
    }

def collect_interested_users(config: AlmaConfig):
    """Collect multiple interested users."""
    users = []
    
    while True:
        console.print(f"\nAdding interested user #{len(users) + 1}:", style="cyan bold")
        
        user_id = get_validated_user_id(config)
        if not user_id:
            break
            
        notify = questionary.confirm("Notify user on receiving activation?").ask()
        hold = questionary.confirm("Hold item for user?").ask()
        
        users.append({
            'user_id': user_id,
            'notify': notify,
            'hold': hold
        })
        
        if not questionary.confirm("Add another interested user?").ask():
            break
    
    return users

def get_validated_user_id(config: AlmaConfig):
    """Get and validate a user ID against Alma API."""
    while True:
        user_id = questionary.text(
            "User ID (9 digits):",
            validate=lambda text: (len(text.strip()) == 9 and text.strip().isdigit()) or "Must be exactly 9 digits"
        ).ask()
        
        if not user_id:
            return None
            
        console.print("Looking up user...", style="yellow")
        success, user_data, error = get_user(user_id, config.api_key, config.base_url)
        
        if success:
            first_name = user_data.get('first_name', '')
            last_name = user_data.get('last_name', '')
            full_name = f"{first_name} {last_name}".strip()
            
            if questionary.confirm(f"Found user: {full_name} (ID: {user_id}). Is this correct?").ask():
                return user_id
        else:
            console.print(f"User not found: {error}", style="yellow")
            if not questionary.confirm("Try a different user ID?").ask():
                return None

# =============================================================================
# JSON GENERATION
# =============================================================================

def create_po_json(data):
    """Create the complete PO line JSON structure."""
    price_str = f"{float(data['price']):.2f}"
    expected_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    
    # Map order type codes to descriptions
    type_descriptions = {
        "MANUSCRIPT": "Manuscript",
        "MIXED": "Mixed Material",
        "PRINTED_BOOK_OT": "Print Book - One Time",
        "PRINTED_BOOK_SO": "Print Book - Standing Order",
        "PRINTED_JOURNAL_CO": "Print Journal - Subscription",
        "SCORE_OT": "Musical Score",
        "VISUAL_MTL_OT": "Visual Material"
    }
    
    # Map acquisition method codes to descriptions
    acquisition_method_descriptions = {
        "VENDOR_SYSTEM": "Purchase at Vendor System",
        "TECHNICAL": "Technical"
    }
    
    po_line = {
        "owner": {"value": "OLIN", "desc": "F.W. Olin Library"},
        "type": {
            "value": data['order_type'],
            "desc": type_descriptions.get(data['order_type'], data['order_type'])
        },
        "vendor": {"value": data['vendor_code']},
        "vendor_account": data['vendor_account'],
        "acquisition_method": {
            "value": data['acquisition_method'],
            "desc": acquisition_method_descriptions.get(data['acquisition_method'], data['acquisition_method'])
        },
        "acquisition_method": {"value": "VENDOR_SYSTEM", "desc": "Purchase at Vendor System"},
        "no_charge": False,
        "rush": False,
        "cancellation_restriction": False,
        "price": {"sum": price_str, "currency": {"value": "USD"}},
        "vendor_reference_number": data['vendor_reference_number'],
        "vendor_reference_number_type": {"value": "IA"},
        "source_type": {"value": "API"},
        "additional_order_reference": data['additional_order_reference'],
        "resource_metadata": {
            "title": data['title'],
            "author": data['author'] or "",
            "isbn": data['isbn'] or "",
            "publisher": data['publisher'] or "",
            "publication_year": data['publication_year'] or ""
        },
        "fund_distribution": [{
            "fund_code": {"value": data['fund_code']},
            "amount": {"sum": price_str, "currency": {"value": "USD"}}
        }],
        "reporting_code": data['reporting_code'],
        "receiving_note": data['receiving_categories'],
        "material_type": {"value": data['material_type']},
        "location": [{
            "quantity": data['quantity'],
            "library": {"value": "OLIN"},
            "shelving_location": "olord",
            "copy": [{
                "item_policy": {"value": "40"},
                "is_temp_location": False,
                "permanent_library": {"value": ""},
                "permanent_shelving_location": ""
            }]
        }],
        "expected_receipt_date": expected_date
    }
    
    # Add OCLC number if available
    if data.get('oclc_number'):
        po_line['resource_metadata']['system_control_number'] = [data['oclc_number']]
    
    # Add conditional data
    conditional_data = data.get('conditional_data', {})
    
    # Add notes
    notes = []
    if conditional_data.get('additional_notes'):
        notes.append({"note_text": conditional_data['additional_notes']})
    if conditional_data.get('reserve_note'):
        notes.append({"note_text": f"Reserve Note: {conditional_data['reserve_note']}"})
    if notes:
        po_line['note'] = notes
    
    # Add interested users
    if conditional_data.get('interested_users'):
        users_list = []
        for user_info in conditional_data['interested_users']:
            users_list.append({
                "primary_id": user_info['user_id'],
                "notify_receiving_activation": user_info['notify'],
                "hold_item": user_info['hold'],
                "notify_renewal": False,
                "notify_cancel": False
            })
        po_line['interested_user'] = users_list
    
    return po_line

# =============================================================================
# UTILITIES
# =============================================================================

def get_user(uid, api_key, base_url):
    """Get user information from Alma API."""
    url = f"{base_url}/almaws/v1/users/{uid}"
    params = {'apikey': api_key, 'view': 'brief'}
    headers = {'accept': 'application/json', 'Content-Type': 'application/json'}
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        if response.status_code == 200:
            return True, response.json(), None
        else:
            return False, None, f"HTTP {response.status_code}"
    except Exception as e:
        return False, None, str(e)

def validate_price(text):
    """Validate price format."""
    if not text.strip():
        return "Price is required"
    try:
        price = float(text.strip())
        return price > 0 or "Price must be greater than 0"
    except ValueError:
        return "Please enter a valid price"

def validate_receiving_categories(selected):
    """Validate receiving categories."""
    if not selected:
        return "Please select at least one category"
    if "None" in selected and len(selected) > 1:
        return "Cannot select 'None' with other categories"
    return True

def generate_filename(data):
    """Generate filename for JSON output."""
    clean_title = re.sub(r'[^\w\s-]', '', data['title'])
    clean_title = re.sub(r'\s+', '_', clean_title.strip())[:30]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    vendor_ref = re.sub(r'[^\w-]', '', data.get('vendor_reference_number', 'noref'))[:15]
    return f"po_{clean_title}_{vendor_ref}_{timestamp}.json"

def display_summary(data, filename):
    """Display order summary."""
    table = Table(title="Order Summary", show_header=True, header_style="bold magenta")
    table.add_column("Field", style="cyan", width=20)
    table.add_column("Value", style="white", width=50)
    
    table.add_row("Title", data['title'])
    table.add_row("Author", data['author'] or "Not specified")
    table.add_row("Price", f"${data['price']}")
    table.add_row("Vendor", data['vendor_code'])
    table.add_row("Acquisition Method", data['acquisition_method'])
    table.add_row("Quantity", str(data['quantity']))
    table.add_row("Fund", data['fund_code'])
    table.add_row("Subject", data['reporting_code'])
    table.add_row("Material Type", data['material_type'])
    table.add_row("Receiving Note", data['receiving_categories'])
    
    if data.get('oclc_number'):
        table.add_row("OCLC Number", data['oclc_number'])
    
    conditional_data = data.get('conditional_data', {})
    if conditional_data.get('interested_users'):
        users_info = conditional_data['interested_users']
        if len(users_info) == 1:
            user_info = users_info[0]
            user_text = f"{user_info['user_id']} (notify: {user_info['notify']}, hold: {user_info['hold']})"
            table.add_row("Interested User", user_text)
        else:
            users_text_lines = []
            for i, user_info in enumerate(users_info, 1):
                user_line = f"{i}. {user_info['user_id']} (notify: {user_info['notify']}, hold: {user_info['hold']})"
                users_text_lines.append(user_line)
            table.add_row("Interested Users", "\n".join(users_text_lines))
    
    table.add_row("File", filename)
    console.print(table)

# =============================================================================
# MAIN
# =============================================================================

def main():
    config = AlmaConfig.from_env()
    console.print("Configuration loaded successfully", style="green")
    console.print(Panel.fit("PO Line Creator", style="bold blue"))
    
    while True:
        # Collect all information
        data = get_order_information(config)
        if not data:
            continue
        
        # Generate JSON
        po_json = create_po_json(data)
        filename = generate_filename(data)
        
        # Show summary
        display_summary(data, filename)
        
        # Confirm and save
        if questionary.confirm(f"Save this PO to {filename}?").ask():
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(po_json, f, indent=4, ensure_ascii=False)
                console.print(f"Successfully created: {filename}", style="bold green")
            except Exception as e:
                console.print(f"Error saving file: {str(e)}", style="bold red")
        else:
            console.print("File not saved", style="yellow")
        
        if not questionary.confirm("Create another PO?").ask():
            console.print("Goodbye!", style="bold cyan")
            break

if __name__ == "__main__":
    main()