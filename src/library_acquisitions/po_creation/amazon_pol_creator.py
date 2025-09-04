#!/usr/bin/env python

# Amazon CSV to Alma PO Line JSON Converter
# Script Version: 3.0
# Last Updated: 2025-09-04
# Enhanced with rich console and questionary UI

import csv
import json
import sys
import re
import os
from datetime import datetime, timedelta
import pandas as pd
import questionary
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import track

console = Console()

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

def get_global_settings():
    """Get global settings that apply to all orders"""
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
    
    console.print(Panel.fit("Global Settings", style="bold blue"))
    console.print("These settings will apply to all orders in the CSV file:", style="cyan")
    
    # Get global reporting code
    reporting_code = questionary.autocomplete(
        "Select reporting code/subject:",
        choices=subjects,
        default="General",
        validate=lambda text: text in subjects or "Please select a valid subject"
    ).ask()
    
    # Get global receiving note
    receiving_note = questionary.text(
        "Default receiving note (press Enter for none):"
    ).ask() or ""
    
    # Get global reserve note
    reserve_note = questionary.text(
        "Default reserve note (press Enter for none):"
    ).ask() or ""
    
    # Ask about interested users
    use_interested_user = questionary.confirm(
        "Add interested user to all orders?",
        default=False
    ).ask()
    
    user_settings = {}
    if use_interested_user:
        user_id = questionary.text(
            "Interested user ID (9 digits):",
            validate=lambda text: (len(text.strip()) == 9 and text.strip().isdigit()) or "Must be exactly 9 digits"
        ).ask()
        
        notify = questionary.confirm(
            "Notify user on receiving activation?",
            default=True
        ).ask()
        
        hold = questionary.confirm(
            "Hold item for user?",
            default=False
        ).ask()
        
        user_settings = {
            'user_id': user_id,
            'notify': notify,
            'hold': hold
        }
    
    return {
        'reporting_code': reporting_code,
        'receiving_note': receiving_note,
        'reserve_note': reserve_note,
        'user_settings': user_settings
    }

def validate_receiving_categories(selected):
    """Validate receiving categories."""
    if not selected:
        return "Please select at least one category"
    if "None" in selected and len(selected) > 1:
        return "Cannot select 'None' with other categories"
    return True

def get_per_item_settings(row_data, global_settings):
    """Get settings for individual items, with option to use globals"""
    title = row_data.get('Title', '').strip()
    asin = clean_asin(row_data.get('ASIN', ''))
    

    
    # Get item-specific settings
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
    
    reporting_code = questionary.autocomplete(
        "Subject for this item:",
        choices=subjects,
        default=global_settings['reporting_code'],
        validate=lambda text: text in subjects or "Please select a valid subject"
    ).ask()
    
    # Receiving categories
    receiving_categories = questionary.checkbox(
        "Receiving note categories:",
        choices=["None", "Note", "Interested User", "Reserve", "Display", "Replacement"],
        validate=lambda selected: validate_receiving_categories(selected)
    ).ask()
    
    receiving_note = " | ".join(receiving_categories) if receiving_categories and "None" not in receiving_categories else "None"
    
    # Additional notes
    additional_note = ""
    if "Note" in receiving_categories:
        additional_note = questionary.text("Additional notes:").ask() or ""
    
    # Reserve note
    reserve_note = ""
    if "Reserve" in receiving_categories:
        reserve_note = questionary.text("Reserve note:").ask() or ""
    
    # Interested user
    user_settings = {}
    if "Interested User" in receiving_categories:
        user_id = questionary.text(
            "Interested user ID (9 digits):",
            validate=lambda text: (len(text.strip()) == 9 and text.strip().isdigit()) or "Must be exactly 9 digits"
        ).ask()
        
        notify = questionary.confirm(
            "Notify user on receiving activation?",
            default=True
        ).ask()
        
        hold = questionary.confirm(
            "Hold item for user?",
            default=False
        ).ask()
        
        user_settings = {
            'user_id': user_id,
            'notify': notify,
            'hold': hold
        }
    
    return {
        'reporting_code': reporting_code,
        'receiving_note': receiving_note,
        'reserve_note': reserve_note,
        'additional_note': additional_note,
        'user_settings': user_settings
    }

def display_item_summary(row_data, settings, output_filename):
    """Display summary for a processed item"""
    table = Table(title="Item Summary", show_header=True, header_style="bold magenta")
    table.add_column("Field", style="cyan", width=20)
    table.add_column("Value", style="white", width=50)
    
    table.add_row("Title", row_data.get('Title', '')[:50] + "..." if len(row_data.get('Title', '')) > 50 else row_data.get('Title', ''))
    table.add_row("ASIN", clean_asin(row_data.get('ASIN', '')))
    table.add_row("Price", f"${format_currency_amount(row_data.get('Item Net Total', 0))}")
    table.add_row("Order ID", row_data.get('Order ID', ''))
    table.add_row("Subject", settings['reporting_code'])
    table.add_row("Receiving Note", settings['receiving_note'])
    
    if settings.get('user_settings') and settings['user_settings'].get('user_id'):
        user_info = settings['user_settings']
        user_text = f"{user_info['user_id']} (notify: {user_info['notify']}, hold: {user_info['hold']})"
        table.add_row("Interested User", user_text)
    
    table.add_row("Output File", output_filename)
    console.print(table)

def create_amazon_po_line_json(row_data, settings):
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
        "reporting_code": settings['reporting_code'],
        "vendor_note": f"Amazon Order ID: {order_id}",
        "receiving_note": settings['receiving_note'],
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
    
    # Add interested_user section if user_id is provided
    user_settings = settings.get('user_settings', {})
    if user_settings.get('user_id'):
        po_line["interested_user"] = [
            {
                "primary_id": user_settings['user_id'],
                "notify_receiving_activation": "true" if user_settings.get('notify') else "false",
                "hold_item": "true" if user_settings.get('hold') else "false",
                "notify_renewal": "false",
                "notify_cancel": "false"
            }
        ]
    
    # Add expected receipt date if available (7 days after order date)
    if expected_date:
        po_line["expected_receipt_date"] = expected_date
    
    # Add notes if available
    notes = []
    if settings.get('reserve_note'):
        notes.append({"note_text": f"Reserve Note: {settings['reserve_note']}"})
    if settings.get('additional_note'):
        notes.append({"note_text": settings['additional_note']})
    if po_number:
        notes.append({"note_text": f"Amazon PO Number: {po_number}"})
    if asin:
        notes.append({"note_text": f"ASIN: {asin}"})
    if account_group:
        notes.append({"note_text": f"Account Group: {account_group}"})
    
    po_line["note"] = notes
    
    return po_line

def process_csv_file(csv_filename):
    """Process the CSV file with enhanced UI"""
    if not os.path.exists(csv_filename):
        console.print(f"[bold red]Error:[/bold red] Could not find file '{csv_filename}'", style="bold red")
        console.print(f"Current working directory: {os.getcwd()}")
        sys.exit(1)
    
    console.print(Panel.fit("Amazon CSV to Alma PO Line Converter", style="bold blue"))
    console.print(f"Processing file: [bold cyan]{csv_filename}[/bold cyan]")
    
    # Get global settings first (these will be used as defaults)
    global_settings = get_global_settings()
    
    processed_count = 0
    error_count = 0
    skipped_count = 0
    
    try:
        # Read and preview CSV file
        with open(csv_filename, 'r', encoding='utf-8') as csvfile:
            # Detect delimiter
            sample = csvfile.read(1024)
            csvfile.seek(0)
            sniffer = csv.Sniffer()
            delimiter = sniffer.sniff(sample).delimiter
            
            reader = csv.DictReader(csvfile, delimiter=delimiter)
            rows = list(reader)
            
        console.print(f"\n[bold green]Found {len(rows)} rows in CSV file[/bold green]")
        console.print(f"[cyan]You'll be able to review and customize each item individually.[/cyan]")
        console.print(f"[cyan]Global settings will be used as defaults, but you can change them for any item.[/cyan]")
        
        # Ask if they want to process all or preview a few
        process_all = questionary.confirm(
            f"Process all {len(rows)} items? (No = preview first 5 items only)",
            default=True
        ).ask()
        
        if not process_all:
            rows = rows[:5]
            console.print(f"[yellow]Processing first 5 items only[/yellow]")
        
        console.print("\n" + "="*60)
        
        for i, row in enumerate(rows, 1):
            try:
                # Skip rows without title or ASIN
                if not row.get('Title', '').strip() or not row.get('ASIN', '').strip():
                    console.print(f"[yellow]⚠  Skipping row {i}: Missing title or ASIN[/yellow]")
                    skipped_count += 1
                    continue
                
                console.print(f"\n[bold blue]═══ Processing Item {i} of {len(rows)} ═══[/bold blue]")
                
                # Display key item information first
                title = row.get('Title', '').strip()
                order_id = row.get('Order ID', '').strip()
                csv_receiving_note = row.get('Receiving note', '').strip()
                
                console.print(f"[bold cyan]Title:[/bold cyan] {title[:60]}...")
                console.print(f"[bold cyan]Order ID:[/bold cyan] {order_id}")
                console.print(f"[bold cyan]CSV Receiving Note:[/bold cyan] {csv_receiving_note or 'None'}")
                
                # Always get individual settings for each item
                item_settings = get_per_item_settings(row, global_settings)
                
                # Create JSON structure
                po_line_json = create_amazon_po_line_json(row, item_settings)
                
                # Create output filename based on ASIN
                asin = clean_asin(row.get('ASIN', ''))
                order_id = row.get('Order ID', '').strip().replace(' ', '_')
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                output_filename = f"amazon_{asin}_{order_id}_{timestamp}.json"
                
                # Show summary for this item
                display_item_summary(row, item_settings, output_filename)
                
                # Confirm before saving (with option to skip)
                save_choice = questionary.select(
                    "What would you like to do with this item?",
                    choices=[
                        questionary.Choice("Save this PO", "save"),
                        questionary.Choice("Skip this item", "skip"),
                        questionary.Choice("Stop processing and exit", "exit")
                    ]
                ).ask()
                
                if save_choice == "save":
                    # Write JSON file
                    with open(output_filename, 'w', encoding='utf-8') as json_file:
                        json.dump(po_line_json, json_file, indent=4, ensure_ascii=False)
                    
                    console.print(f"[bold green]✓ Created:[/bold green] {output_filename}")
                    processed_count += 1
                    
                elif save_choice == "skip":
                    console.print("[yellow]⚠ Skipped by user choice[/yellow]")
                    skipped_count += 1
                    
                else:  # exit
                    console.print(f"[yellow]Processing stopped by user at item {i}[/yellow]")
                    break
                
            except KeyboardInterrupt:
                console.print(f"\n[yellow]Processing interrupted by user[/yellow]")
                break
            except Exception as e:
                console.print(f"[bold red]✗ Error processing row {i}: {str(e)}[/bold red]")
                error_count += 1
                
                # Ask if they want to continue after an error
                if not questionary.confirm("Continue processing remaining items?").ask():
                    break
                continue
                
    except FileNotFoundError:
        console.print(f"[bold red]Error: Could not find file '{csv_filename}'[/bold red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]Error reading CSV file: {str(e)}[/bold red]")
        sys.exit(1)
    
    # Final summary
    console.print("\n" + "="*60)
    summary_table = Table(title="Processing Summary", show_header=True, header_style="bold magenta")
    summary_table.add_column("Status", style="cyan")
    summary_table.add_column("Count", style="white")
    
    summary_table.add_row("Successfully processed", f"[green]{processed_count}[/green]")
    summary_table.add_row("Errors encountered", f"[red]{error_count}[/red]")
    summary_table.add_row("Skipped items", f"[yellow]{skipped_count}[/yellow]")
    summary_table.add_row("Total rows processed", str(len(rows)))
    
    console.print(summary_table)
    console.print(f"\n[bold green]Processing complete![/bold green] JSON files created in current directory.")

def main():
    """Main function with enhanced UI"""
    console.print(Panel.fit("Amazon CSV to Alma PO Line JSON Converter", style="bold blue"))
    
    if len(sys.argv) != 2:
        console.print("[bold red]Usage:[/bold red] python amazon_pol_creator.py <csv_filename>")
        console.print("\n[yellow]Please provide the path to your Amazon CSV file as an argument.[/yellow]")
        
        # Option to browse for file
        if questionary.confirm("Would you like to enter the filename interactively?").ask():
            csv_filename = questionary.path(
                "Enter path to CSV file:",
                validate=lambda path: os.path.exists(path) or f"File '{path}' does not exist"
            ).ask()
        else:
            sys.exit(1)
    else:
        csv_filename = sys.argv[1]
    
    try:
        process_csv_file(csv_filename)
    except KeyboardInterrupt:
        console.print(f"\n[yellow]Program interrupted by user. Goodbye![/yellow]")
    except Exception as e:
        console.print(f"[bold red]Unexpected error: {str(e)}[/bold red]")
        sys.exit(1)

if __name__ == "__main__":
    main()