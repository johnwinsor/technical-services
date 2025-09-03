import re
import os
import sys
import json
from collections import OrderedDict
from itertools import islice

def read_edi_file(file_path):
    """Read the contents of an EDI file."""
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read()

def parse_edi(edi_content):
    # Split the EDI content into segments
    segments = edi_content.split("'")
    
    parsed_data = OrderedDict()
    current_message_ref = None
    current_line_number = None
    
    for segment in segments:
        # Split each segment into its elements
        elements = re.split(r'\+|:', segment)
        
        # The first element is the segment name
        segment_name = elements[0]
        
        if segment_name == 'UNH':
            # Start of a new message
            current_message_ref = elements[1]
            parsed_data[current_message_ref] = OrderedDict([
                ('invoice_number', None),
                ('lines', OrderedDict()),
                ('totals', OrderedDict())
            ])
        
        elif segment_name == 'DTM':
            # contains invoice date
            if current_message_ref is not None and len(elements) > 2:
                parsed_data[current_message_ref]['invoice_date'] = elements[2]
        
        elif segment_name == 'BGM':
            # Beginning of Message - contains invoice number
            if current_message_ref is not None and len(elements) > 2:
                parsed_data[current_message_ref]['invoice_number'] = elements[2]
        
        elif segment_name == 'LIN':
            # Line item
            current_line_number = elements[1]
            item_number = elements[3] if len(elements) > 3 else None
            parsed_data[current_message_ref]['lines'][f'line_{current_line_number}'] = OrderedDict([
                ('item_number', item_number),
                ('description', []),
                ('quantity', None),
                ('amount', None)
            ])
        
        elif segment_name == 'IMD':
            # Item description
            if current_line_number is not None:
                description = ' '.join(elements[4:]) if len(elements) > 4 else ''
                parsed_data[current_message_ref]['lines'][f'line_{current_line_number}']['description'].append(description.strip())
        
        elif segment_name == 'QTY':
            # Quantity
            if current_line_number is not None:
                quantity = elements[2] if len(elements) > 2 else None
                parsed_data[current_message_ref]['lines'][f'line_{current_line_number}']['quantity'] = quantity
        
        elif segment_name == 'MOA':
            # Monetary amount
            if len(elements) > 2:
                if elements[1] == '203' and current_line_number is not None:
                    # Line item amount
                    parsed_data[current_message_ref]['lines'][f'line_{current_line_number}']['amount'] = elements[2]
                elif elements[1] == '9':
                    # Invoice total amount
                    parsed_data[current_message_ref]['totals']['invoice_total'] = elements[2]
    
    # Join the description list into a single string for each line item
    for message in parsed_data.values():
        for line in message['lines'].values():
            line['description'] = ' '.join(line['description'])
    
    return parsed_data

# Example usage
def main():
    file_in = sys.argv[1]

    try:
        # Read the EDI file
        edi_content = read_edi_file(file_in)
        
        # Parse the EDI content
        parsed_data = parse_edi(edi_content)
        
        # Print the parsed data
        # print(json.dumps(parsed_data, indent=2))
        
        for invoice_id, invoice_data in parsed_data.items():
            print(f"Invoice Number: {invoice_data['invoice_number']}")
            print(f"Invoice Date: {invoice_data['invoice_date']}")
            
            for line_id, line_data in invoice_data['lines'].items():
                print(f"\tISBN: {line_data['item_number']}")
        
    except FileNotFoundError:
        print(f"Error: The file {file_in} was not found.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()