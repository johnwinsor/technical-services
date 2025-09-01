#!/usr/bin/env python3


from pymarc import MARCReader
from pymarc import exceptions as exc
import sys
import csv

filename = sys.argv[1]
recordcount = 0

with open('out.csv', mode='w') as csv_out:
    csv_writer = csv.writer(csv_out, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)

    with open(filename, 'rb') as fh:
        reader = MARCReader(fh)
        for record in reader:
            if record:
                mms = record['001'].format_field()
                title = record['245'].format_field()
                pub = record.publisher
                pubyear = record.pubyear
                # try:
                #     pub = record['260'].format_field()
                # except:
                #     pub = record['264'].format_field()
                try:
                    bibno = record['907']['a']
                except:
                    bibno = "MISSING"
                print(bibno)
                csv_writer.writerow([mms, bibno, title, pub, pubyear])
            elif isinstance(reader.current_exception, exc.FatalReaderError):
                print(reader.current_exception)
                print(reader.current_chunk)
            else:
                print(reader.current_exception)
                print(reader.current_chunk)