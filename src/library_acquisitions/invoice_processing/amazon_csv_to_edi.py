#!/usr/bin/env python3
"""
Amazon CSV to EDIFACT EDI Converter
Converts Amazon Business CSV invoice data to EDIFACT INVOIC format for Alma
"""

import csv
import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import re


@dataclass
class EDIFACTConfig:
    """Configuration for EDIFACT generation"""
    sender_id: str = "1694510101"  # Amazon vendor ID in your system
    sender_qualifier: str = "31B"
    receiver_id: str = "3333159"  # From your sample  
    receiver_qualifier: str = "31B"
    interchange_ref: str = None  # Will be generated
    currency: str = "USD"
    vendor_account: str = "amazon"  # Always "amazon" for Amazon Business orders


class EDIFACTInvoiceGenerator:
    """Generates EDIFACT INVOIC messages from Amazon CSV data"""
    
    def __init__(self, config: EDIFACTConfig):
        self.config = config
        if not self.config.interchange_ref:
            self.config.interchange_ref = datetime.datetime.now().strftime("%m%d%H%M%S%f")[:-3]
    
    def generate_una_unb_headers(self) -> str:
        """Generate UNA and UNB headers"""
        now = datetime.datetime.now()
        date_str = now.strftime("%y%m%d")
        time_str = now.strftime("%H%M")
        
        una = "UNA:+.? '"
        unb = (f"UNB+UNOC:2+{self.config.sender_id}:{self.config.sender_qualifier}+"
               f"{self.config.receiver_id}:{self.config.receiver_qualifier}+"
               f"{date_str}:{time_str}+{self.config.interchange_ref}'")
        
        return una + unb
    
    def generate_invoice_segments(self, invoice_data: Dict[str, Any]) -> List[str]:
        """Generate all segments for a single invoice"""
        segments = []
        
        # UNH - Message Header
        msg_ref = invoice_data.get('invoice_number', '1')
        segments.append(f"UNH+{msg_ref}+INVOIC:D:96A:UN:EAN008'")
        
        # BGM - Beginning of Message
        invoice_num = invoice_data.get('invoice_number', '491150')
        segments.append(f"BGM+380+{invoice_num}'")
        
        # DTM - Date/Time (Invoice Date)
        invoice_date = invoice_data.get('invoice_date', datetime.datetime.now().strftime("%Y%m%d"))
        segments.append(f"DTM+137:{invoice_date}:102'")
        
        # DTM - Date/Time (Due Date) - if available
        due_date = invoice_data.get('due_date', '')
        if due_date and due_date != invoice_date:  # Only add if different from invoice date
            segments.append(f"DTM+13:{due_date}:102'")
        
        # RFF - Reference (API reference from your sample)
        api_ref = invoice_data.get('api_ref', '7015-10')
        segments.append(f"RFF+API:{api_ref}'")
        
        # RFF - Vendor Account Reference (from config)
        segments.append(f"RFF+VA:{self.config.vendor_account}'")
        
        # CUX - Currencies
        segments.append(f"CUX+2:{self.config.currency}:4'")
        
        # Calculate charges
        line_items = invoice_data.get('line_items', [])
        shipping_total = sum(item.get('shipping', 0) for item in line_items)
        
        # ALC - Allowance or Charge (Freight)
        if shipping_total > 0:
            segments.append("ALC+C++++DL::28:Freight Charges'")
            segments.append(f"MOA+8:{shipping_total:.2f}'")
        
        # Line items
        for i, item in enumerate(line_items, 1):
            segments.extend(self.generate_line_item_segments(item, i))
        
        # UNS - Section Control
        segments.append("UNS+S'")
        
        # CNT - Control Total
        total_lines = len(line_items)
        total_qty = sum(int(item.get('quantity', 1) or 1) for item in line_items)
        segments.append(f"CNT+1:{total_qty}'")
        segments.append(f"CNT+2:{total_lines}'")
        
        # MOA - Monetary Amount
        gross_total = sum(item.get('unit_price', 0) * int(item.get('quantity', 1) or 1) 
                         for item in line_items) + shipping_total
        discounts_total = sum(item.get('discounts', 0) for item in line_items)
        total_tax = sum(item.get('tax_amount', 0) for item in line_items)
        net_total = gross_total + discounts_total + total_tax  # Add tax to net total
        
        segments.append(f"MOA+9:{gross_total:.2f}'")
        segments.append(f"MOA+79:{net_total:.2f}'")
        
        # Add total tax amount if there's any tax
        if total_tax > 0:
            segments.append(f"MOA+176:{total_tax:.2f}'")
        
        # UNT - Message Trailer
        segment_count = len(segments) + 1  # +1 for the UNT segment itself
        segments.append(f"UNT+{segment_count}+{msg_ref}'")
        
        return segments
    
    def generate_line_item_segments(self, item: Dict[str, Any], line_num: int) -> List[str]:
        """Generate segments for a single line item"""
        segments = []
        
        # LIN - Line Item
        asin = item.get('asin', '')
        segments.append(f"LIN+{line_num}++{asin}:EN'")
        
        # IMD - Item Description - Author
        author = item.get('author', '').upper()
        if author:
            segments.append(f"IMD+L+010+:::{author}'")
        
        # IMD - Item Description - Title (may need multiple segments if long)
        title = item.get('title', '').upper()
        title_segments = self.split_title_for_imd(title)
        for title_seg in title_segments:
            segments.append(f"IMD+L+050+:::{title_seg}'")
        
        # QTY - Quantity
        quantity = item.get('quantity', '1') or '1'
        segments.append(f"QTY+47:{quantity}'")
        
        # MOA - Monetary Amount (line total)
        unit_price = item.get('unit_price', 0)
        line_total = unit_price * int(quantity)
        segments.append(f"MOA+203:{line_total:.2f}'")
        
        # PRI - Price Details
        list_price = item.get('list_price', unit_price)
        segments.append(f"PRI+AAB:{list_price:.2f}'")
        segments.append(f"PRI+AAA:{unit_price:.2f}'")
        
        # TAX - Duty/tax/fee details (if tax information available)
        tax_rate = item.get('tax_rate', '')
        tax_amount = item.get('tax_amount', 0)
        if tax_rate and tax_rate != '0':
            # TAX segment: TAX+7+VAT+++:::tax_rate
            segments.append(f"TAX+7+VAT+++:::{tax_rate}'")
            if tax_amount > 0:
                # MOA segment for tax amount: MOA+124:tax_amount
                segments.append(f"MOA+124:{tax_amount:.2f}'")
        
        # RFF - References
        pol = item.get('pol', '')
        if pol:
            segments.append(f"RFF+LI:{pol}'")
        
        sli_ref = item.get('sli_ref', '0')
        segments.append(f"RFF+SLI:{sli_ref}'")
        
        return segments
    
    def split_title_for_imd(self, title: str, max_length: int = 35) -> List[str]:
        """Split long titles into multiple IMD segments"""
        if len(title) <= max_length:
            return [title]
        
        # Try to split on word boundaries
        words = title.split()
        segments = []
        current_segment = ""
        
        for word in words:
            if len(current_segment + " " + word) <= max_length:
                if current_segment:
                    current_segment += " " + word
                else:
                    current_segment = word
            else:
                if current_segment:
                    segments.append(current_segment)
                    current_segment = word
                else:
                    # Word is longer than max_length, force split
                    segments.append(word[:max_length])
                    current_segment = word[max_length:]
        
        if current_segment:
            segments.append(current_segment)
        
        return segments
    
    def generate_unz_trailer(self, message_count: int) -> str:
        """Generate UNZ trailer"""
        return f"UNZ+{message_count}+{self.config.interchange_ref}'"


def parse_amazon_csv(csv_file_path: str) -> List[Dict[str, Any]]:
    """Parse Amazon Business CSV and group by invoice"""
    invoices = {}
    
    with open(csv_file_path, 'r', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        
        for row in reader:
            # Group by Order ID (which becomes our invoice number)
            order_id = row.get('Order ID', '')
            
            if order_id not in invoices:
                invoices[order_id] = {
                    'invoice_number': order_id,
                    'invoice_date': parse_date(row.get('Order date', '')),
                    'due_date': parse_date(row.get('Invoice due date', '')),
                    'api_ref': row.get('Family', '7015-10'),  # Use Family column for EAN/API reference
                    'line_items': []
                }
            
            # Extract author from title (simple heuristic)
            title = row.get('Title', '')
            author = extract_author_from_title(title)
            
            # Helper function to safely convert to float
            def safe_float(value, default=0.0):
                if value is None or value == '' or value == 'nan':
                    return default
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return default
            
            line_item = {
                'asin': row.get('ASIN', ''),
                'title': clean_title(title, author),
                'author': author,
                'quantity': row.get('Shipment Quantity', '1') or '1',
                'unit_price': safe_float(row.get('Unit price excl. tax')),
                'list_price': safe_float(row.get('Unit price excl. tax')),  # Amazon doesn't separate list price
                'shipping': safe_float(row.get('Shipping and handling excl. tax')),
                'discounts': safe_float(row.get('Promotions and discounts excl. tax')),
                'tax_rate': row.get('Tax rate', '').replace('%', ''),  # Remove % symbol if present
                'tax_amount': safe_float(row.get('Total tax amount')),
                'pol': row.get('POL', ''),  # This is what you need to add to your CSV
                'sli_ref': row.get('PO line item ID', '0') or '0'
            }
            
            invoices[order_id]['line_items'].append(line_item)
    
    return list(invoices.values())


def extract_author_from_title(title: str) -> str:
    """Extract author name from title using common patterns"""
    # This is a simple heuristic - you might need to adjust based on your data
    # Look for patterns like "Author Name - Title" or "Title by Author Name"
    
    if ' by ' in title.lower():
        parts = title.split(' by ')
        if len(parts) > 1:
            return parts[-1].strip()
    
    if ' - ' in title:
        parts = title.split(' - ')
        # First part might be author if it's all caps or title case
        if len(parts) > 1 and parts[0].isupper():
            return parts[0].strip()
    
    return ""  # Return empty if no author pattern found


def clean_title(title: str, author: str) -> str:
    """Remove author name from title if it was extracted"""
    if author and author in title:
        title = title.replace(f" by {author}", "").replace(f"{author} - ", "").strip()
    return title


def parse_date(date_str: str) -> str:
    """Parse various date formats to YYYYMMDD"""
    if not date_str:
        return datetime.datetime.now().strftime("%Y%m%d")
    
    # Try common formats
    formats = ['%m/%d/%Y', '%Y-%m-%d', '%m-%d-%Y', '%Y/%m/%d']
    
    for fmt in formats:
        try:
            date_obj = datetime.datetime.strptime(date_str, fmt)
            return date_obj.strftime("%Y%m%d")
        except ValueError:
            continue
    
    # If all else fails, return current date
    return datetime.datetime.now().strftime("%Y%m%d")


def convert_amazon_csv_to_edifact(csv_file_path: str, edi_file_path: str, config: EDIFACTConfig = None):
    """Convert Amazon CSV to EDIFACT EDI format"""
    if config is None:
        config = EDIFACTConfig()
    
    # Parse CSV
    invoices = parse_amazon_csv(csv_file_path)
    
    if not invoices:
        raise ValueError("No invoice data found in CSV file")
    
    # Print summary of what will be created
    print(f"\n📋 Processing {len(invoices)} invoice(s):")
    print("=" * 50)
    
    total_line_items = 0
    for invoice in invoices:
        line_count = len(invoice['line_items'])
        total_line_items += line_count
        print(f"Invoice: {invoice['invoice_number']} → {line_count} line item(s)")
    
    print("=" * 50)
    print(f"📊 Total: {len(invoices)} invoices, {total_line_items} line items")
    print()
    
    # Generate EDI
    generator = EDIFACTInvoiceGenerator(config)
    
    with open(edi_file_path, 'w', newline='', encoding='utf-8') as edi_file:
        # Write headers
        edi_file.write(generator.generate_una_unb_headers())
        
        # Write each invoice
        for invoice in invoices:
            segments = generator.generate_invoice_segments(invoice)
            for segment in segments:
                edi_file.write(segment)
        
        # Write trailer
        edi_file.write(generator.generate_unz_trailer(len(invoices)))


def main():
    """Main function with command line argument support"""
    import sys
    import os
    
    # Check for command line argument
    if len(sys.argv) != 2:
        print("Usage: python script.py <csv_file_path>")
        print("Example: python script.py /path/to/amazon_invoices.csv")
        sys.exit(1)
    
    csv_file_path = sys.argv[1]
    
    # Check if CSV file exists
    if not os.path.exists(csv_file_path):
        print(f"Error: CSV file '{csv_file_path}' not found.")
        sys.exit(1)
    
    # Generate EDI file path in same directory as CSV
    csv_dir = os.path.dirname(csv_file_path)
    csv_filename = os.path.basename(csv_file_path)
    csv_name, _ = os.path.splitext(csv_filename)
    edi_file_path = os.path.join(csv_dir, f"{csv_name}.edi")
    
    # Configuration - uses defaults from EDIFACTConfig class
    config = EDIFACTConfig()
    
    try:
        convert_amazon_csv_to_edifact(csv_file_path, edi_file_path, config)
        print(f"✅ Successfully converted '{csv_file_path}' to EDIFACT EDI format!")
        print(f"📁 Output file: '{edi_file_path}'")
        print("💡 Note: Make sure you've added POL numbers to your CSV for Alma integration")
    except FileNotFoundError:
        print("❌ Error: CSV file not found. Please check the file path.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error during conversion: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()