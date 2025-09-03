#!/usr/bin/env python

import fitz  # PyMuPDF
import sys
import re
import glob
import csv
from datetime import date, datetime
import os

today = date.today()
folder = sys.argv[1]

def extract_gobi_data(text, filename):
    """Extract data from GOBI invoice format"""
    pdf = filename.split("/")[-1]  # Get just the filename
    invoice_number = pdf.split("-")[2].strip(r"\.pdf")
    
    pols = re.findall(r'(POL-[0-9]{6}).*[0-9]{13} ([A-Z]+).*([0-9]+\.[0-9]{2})', text)
    total = re.findall(r'Total US.*\$(.*)', text)
    if not total:
        total = re.findall(r'Total USD(.*)', text)
    
    if not total:
        total = ['0']
        print(f"WARNING: No Total Price found for GOBI invoice# {invoice_number}")
    
    pol_list = []
    for pol in pols:
        pol_fund = f"{pol[0]} ({pol[1]})"
        pol_list.append(pol_fund)
    
    pol_string = str.join(" ", pol_list)
    invoice_total = total[0].replace(" ", "")
    invoice_date = pdf.split("-")[1]
    
    try:
        date_object = datetime.strptime(invoice_date, "%m%d%y")
        new_date_string = date_object.strftime("%m/%d/%y")
    except ValueError:
        print(f"WARNING: Could not parse date {invoice_date} for GOBI invoice")
        new_date_string = invoice_date
    
    return {
        'filename': pdf,
        'invoice_number': invoice_number,
        'invoice_date': new_date_string,
        'vendor': 'gobi-mills',
        'pol_fund': pol_string,
        'total': invoice_total
    }

def extract_ebsco_data(text, filename):
    """Extract data from EBSCO invoice/renewal list format"""
    pdf = filename.split("/")[-1]  # Get just the filename
    
    # Determine if this is an invoice or renewal list
    is_renewal_list = 'ANNUAL RENEWAL LIST' in text or 'Renewal List Number' in text
    is_regular_invoice = 'Invoice No.' in text or 'INVOICE' in text
    
    print(f"EBSCO Detection for {pdf}: renewal_list={is_renewal_list}, regular_invoice={is_regular_invoice}")
    
    if is_renewal_list:
        print(f"Processing {pdf} as EBSCO renewal list")
        # Extract renewal list number as invoice number
        renewal_match = re.search(r'Renewal List Number\s+Account No\..*?(\d+)', text)
        if not renewal_match:
            renewal_match = re.search(r'(\d{4})\s+SF-F-\d+-\d+', text)
        invoice_number = renewal_match.group(1) if renewal_match else "Unknown"
        
        # Extract grand total
        total_match = re.search(r'Grand Total is in U S Dollars\s*([\d,]+\.[\d]{2})', text)
        if total_match:
            invoice_total = total_match.group(1).replace(',', '')
        else:
            invoice_total = '0'
            print(f"WARNING: No Grand Total found for EBSCO renewal list# {invoice_number}")
        
        # Extract date from renewal list
        date_match = re.search(r'(\d{2}-\d{2}-\d{4})', text)
        if date_match:
            try:
                date_object = datetime.strptime(date_match.group(1), "%m-%d-%Y")
                invoice_date = date_object.strftime("%m/%d/%y")
            except ValueError:
                invoice_date = date_match.group(1)
        else:
            invoice_date = "Unknown"
            print(f"WARNING: Could not parse date for EBSCO renewal list# {invoice_number}")
        
        # Extract all POL numbers from the renewal list
        pol_matches = re.findall(r'ILS: (POL-\d+)', text)
        if pol_matches:
            # Remove duplicates and sort
            unique_pols = sorted(list(set(pol_matches)))
            pol_string = " ".join(unique_pols)
            print(f"Found {len(unique_pols)} unique POL numbers: {pol_string[:100]}...")
        else:
            pol_string = "No POL Info"
            print(f"WARNING: No POL numbers found in EBSCO renewal list# {invoice_number}")
    
    elif is_regular_invoice:
        print(f"Processing {pdf} as EBSCO regular invoice")
        # Handle regular EBSCO invoice format - try multiple patterns
        
        # Extract invoice number - try multiple patterns
        invoice_match = re.search(r'Invoice No\.\s*(\d+)', text)
        if not invoice_match:
            # Try the REF. CODE field pattern (like 0587093)
            invoice_match = re.search(r'REF\.\s*CODE\s+INVOICE NO\.\s+PAGE NO\.\s+[^\d]*(\d+)', text)
        if not invoice_match:
            # Try to find it in the header area - 7-digit invoice numbers
            invoice_match = re.search(r'(\d{7})', text)
        invoice_number = invoice_match.group(1) if invoice_match else "Unknown"
        
        # Extract total amount - try multiple patterns
        total_match = re.search(r'Net Amount Due in U\.S\. Dollars\s*([\d,]+\.[\d]{2})', text)
        if not total_match:
            # Try the format from the second invoice type: "Net Amount Due in U.S. Dollars"
            total_match = re.search(r'Net Amount Due in U\.S\. Dollars\s+([\d,]+\.[\d]{2})', text)
        if not total_match:
            # Alternative pattern without periods in "U.S."
            total_match = re.search(r'Net Amount Due.*?\$?([\d,]+\.[\d]{2})', text)
        if not total_match:
            # Try simpler "Net Amount Due" pattern with flexible spacing
            total_match = re.search(r'Net Amount Due\s+([\d,]+\.[\d]{2})', text)
        if not total_match:
            # Try pattern that matches the exact format in the second PDF
            total_match = re.search(r'Net Amount Due in U\.S\. Dollars\s*\n?\s*([\d,]+\.[\d]{2})', text, re.MULTILINE)
        
        if total_match:
            invoice_total = total_match.group(1).replace(',', '')
        else:
            invoice_total = '0'
            print(f"WARNING: No Total Price found for EBSCO invoice# {invoice_number}")
        
        # Extract date - try multiple date patterns
        date_match = re.search(r'(\d{2}-\d{2}-\d{4})', text)
        if not date_match:
            # Try MM/DD/YYYY format
            date_match = re.search(r'(\d{2}/\d{2}/\d{4})', text)
        if not date_match:
            # Try the date field pattern from the invoice header
            date_match = re.search(r'DATE\s+REF\.\s*CODE.*?(\d{2}-\d{2}-\d{4})', text)
        
        if date_match:
            try:
                date_str = date_match.group(1)
                if '-' in date_str:
                    date_object = datetime.strptime(date_str, "%m-%d-%Y")
                else:
                    date_object = datetime.strptime(date_str, "%m/%d/%Y")
                invoice_date = date_object.strftime("%m/%d/%y")
            except ValueError:
                invoice_date = date_match.group(1)
        else:
            invoice_date = "Unknown"
            print(f"WARNING: Could not parse date for EBSCO invoice# {invoice_number}")
        
        # For regular invoices, look for POL numbers in multiple patterns
        pol_matches = re.findall(r'ILS: (POL-\d+)', text)
        if not pol_matches:
            # Try alternative POL pattern
            pol_matches = re.findall(r'ILS Number:(POL-\d+)', text)
        if not pol_matches:
            # Try without "ILS:" prefix
            pol_matches = re.findall(r'(POL-\d+)', text)
        
        if pol_matches:
            unique_pols = sorted(list(set(pol_matches)))
            pol_string = " ".join(unique_pols)
            print(f"Found {len(unique_pols)} POL numbers in regular invoice")
        else:
            # Fallback to account/reference info
            account_match = re.search(r'Account No\.\s*([A-Z0-9-]+)', text)
            if not account_match:
                account_match = re.search(r'ACCOUNT NO\.\s+([A-Z0-9-]+)', text)
            
            ref_match = re.search(r'Your Purchase No\.\s*([A-Z0-9\s-]+)', text)
            if not ref_match:
                ref_match = re.search(r'YOUR PURCHASE ORDER NO\.\s*([A-Z0-9\s-]+)', text)
            
            pol_info = []
            if account_match:
                pol_info.append(f"Account: {account_match.group(1).strip()}")
            if ref_match:
                pol_info.append(f"PO: {ref_match.group(1).strip()}")
            
            pol_string = " ".join(pol_info) if pol_info else "No POL Info"
    
    else:
        print(f"WARNING: Could not determine EBSCO document type for {pdf}")
        # Default handling
        invoice_number = "Unknown"
        invoice_total = "0"
        invoice_date = "Unknown"
        pol_string = "No POL Info"
    
    return {
        'filename': pdf,
        'invoice_number': invoice_number,
        'invoice_date': invoice_date,
        'vendor': 'ebsco',
        'pol_fund': pol_string,
        'total': invoice_total
    }

def detect_vendor(text, filename):
    """Detect vendor type based on PDF content"""
    filename_lower = filename.lower()
    text_lower = text.lower()
    
    if 'gobi' in filename_lower:
        return 'gobi'
    elif 'ebsco' in text_lower or 'EBSCO' in text or 'SF-F-' in text:
        return 'ebsco'
    elif 'POL-' in text:  # POL- could be in EBSCO or GOBI, check after specific vendor detection
        # If we see POL- but no clear vendor, try to determine from context
        if 'ILS: POL-' in text:
            return 'ebsco'  # EBSCO format uses "ILS: POL-"
        else:
            return 'gobi'   # GOBI format uses POL- differently
    else:
        print(f"WARNING: Unknown vendor for file {filename}")
        return 'unknown'

def extract_invoice_data(text, filename, vendor_type):
    """Extract invoice data based on vendor type"""
    if vendor_type == 'gobi':
        return extract_gobi_data(text, filename)
    elif vendor_type == 'ebsco':
        return extract_ebsco_data(text, filename)
    else:
        # Default extraction for unknown vendors
        pdf = filename.split("/")[-1]
        return {
            'filename': pdf,
            'invoice_number': 'Unknown',
            'invoice_date': 'Unknown',
            'vendor': 'unknown',
            'pol_fund': 'Unknown',
            'total': '0'
        }

def merge_pdfs_with_pymupdf(input_files, output_path):
    """Merge PDFs using PyMuPDF"""
    merged_doc = fitz.open()
    
    for file_path in input_files:
        try:
            doc = fitz.open(file_path)
            merged_doc.insert_pdf(doc)
            doc.close()
            print(f"Added {file_path} to merged PDF")
        except Exception as e:
            print(f"Error merging {file_path}: {e}")
    
    merged_doc.save(output_path)
    merged_doc.close()
    print(f"Merged PDF saved as: {output_path}")

def main():
    # Get all PDF files
    files = glob.glob(f"{folder}/*.pdf")
    files.sort()
    rows = []

    # Process all files (no batching)
    for file in files:
        print(f"Processing: {file}")
        try:
            # Use PyMuPDF to read PDF
            doc = fitz.open(file)
            
            if len(doc) == 0:
                print(f"WARNING: {file} appears to be empty")
                doc.close()
                continue
            
            # Extract all text from PDF
            text = ''
            for page_num in range(len(doc)):
                page = doc[page_num]
                text += page.get_text()
            
            doc.close()
            
            # Detect vendor and extract data
            vendor_type = detect_vendor(text, file)
            invoice_data = extract_invoice_data(text, file, vendor_type)
            
            # Create row for CSV
            row = [
                invoice_data['filename'],
                invoice_data['invoice_number'],
                invoice_data['invoice_date'],
                invoice_data['vendor'],
                invoice_data['pol_fund'],
                invoice_data['total']
            ]
            
            print(f"Extracted: {row}")
            rows.append(row)
            
        except Exception as e:
            print(f"Error processing {file}: {e}")
            continue

    # Write the full CSV
    fields = ['PDF Filename','Invoice Number','Invoice Date','Vendor','POL (Fund)','Total']
    csv_filename = f'{folder}/Olin-Invoices-{today}.csv'
    with open(csv_filename, 'w') as csvfile:
        csvwriter = csv.writer(csvfile)
        csvwriter.writerow(fields)
        csvwriter.writerows(rows)

    print(f"Full CSV file created: {csv_filename}")

    # Create summary CSV file with just the 4 key columns
    summary_fields = ['Invoice Number', 'Invoice Date', 'Vendor', 'Amount']
    summary_csv_filename = f'{folder}/Olin-Invoices-Summary-{today}.csv'
    with open(summary_csv_filename, 'w') as csvfile:
        csvwriter = csv.writer(csvfile)
        csvwriter.writerow(summary_fields)
        
        # Extract the 4 key columns from each row
        for row in rows:
            summary_row = [
                row[1],  # Invoice Number
                row[2],  # Invoice Date
                row[3],  # Vendor
                row[5]   # Total (Amount)
            ]
            csvwriter.writerow(summary_row)

    print(f"Summary CSV file created: {summary_csv_filename}")
    print(f"Processed {len(rows)} invoices total")

    # Create merged PDF with all invoices in the same order as the summary CSV file
    if rows:  # Only create merged PDF if there are processed invoices
        # Create list of full file paths in the same order as the CSV data
        files_to_merge = []
        for row in rows:
            pdf_filename = row[0]  # First column is PDF Filename
            full_path = os.path.join(folder, pdf_filename)
            if os.path.exists(full_path):
                files_to_merge.append(full_path)
            else:
                print(f"WARNING: Could not find file {full_path} for merging")
        
        if files_to_merge:
            merged_pdf_filename = f'{folder}/All-Invoices-Combined-{today}.pdf'
            merge_pdfs_with_pymupdf(files_to_merge, merged_pdf_filename)
            print(f"All invoices merged into: {merged_pdf_filename}")
        else:
            print("WARNING: No valid PDF files found for merging")
    else:
        print("No invoices were processed - no merged PDF created")
    
if __name__ == "__main__":
    main()