from pymarc import MARCReader
import sys
import csv
import re
from .oclc_api_helpers import getBriefBib, getToken, getSession

# USAGE: python process_withdrawals.py [Weeding|Withdrawals]/20241029/BIBLIOGRAPHIC_19342001100001401_19342001070001401_1.mrc

filename = sys.argv[1]
data_file = open('data_file.csv', 'w')

fields = ['mmsid', 'title', 'bibno', 'oclcno', 'oclctitle']

csv_writer = csv.DictWriter(data_file, fieldnames = fields, restval='', extrasaction='ignore')
    
with open('oclc-millennium.csv', 'r') as file:
    reader = csv.DictReader(file)
    crosswalk = [row for row in reader]

with open(filename, 'rb') as fh:
    token = getToken()
    session = getSession(token)
    reader = MARCReader(fh, file_encoding='utf-8')
    books = []
    oclcNumbers = []
    for record in reader:
        item = {}
        mmsid = record['001'].format_field()
        title = record.title
        print(title)
        try:
            bibno = re.sub(r"[^\w\s]",'',record['907']['a'])
            oclctag = next((item for item in crosswalk if item["BIBNO"] == bibno), None)
            oclc = oclctag['OCLCNO']
        except:
            bibno = None
            for f in record.get_fields('035'):
                if re.search("OCoLC",f['a']):
                    oclc = re.sub(r"\(OCoLC\)","",f['a'])
        briefBib = getBriefBib(oclc, session)
        item['mmsid'] = mmsid
        item['title'] = title
        item['bibno'] = bibno
        item['oclcno'] = oclc
        item['oclctitle'] = briefBib['title']
        books.append(item)
        oclcNumbers.append(oclc)

csv_writer.writerows(books)

with open('oclcNumbers.txt', 'w+') as f:
    for items in oclcNumbers:
        f.write('%s\n' %items)
     
    print("File written successfully")