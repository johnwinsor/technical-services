import sys
import os
from oclc_api_helpers import holdingsUnset, getToken, getSession
from datetime import datetime
import logging

# USAGE: python unset_holdings.py oclcNumbers.txt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, "logging")
LOG_PATH = os.path.join(LOG_DIR, "oclcHoldingsUnset.log")

def setup_logging():
    now = datetime.now()
    logging.basicConfig(
        filename=LOG_PATH,
        filemode='a',
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%d-%b-%y %H:%M:%S',
        level=logging.INFO
    )
    logging.info("+" * 70)
    logging.info(f"START OF UNSET LOG FOR {now}")
    logging.info("+" * 70)

def main(filename):
    with open(filename, 'r') as file:
        token = getToken()
        session = getSession(token)
        for line in file:
            oclc_number = line.strip()
            unsetResponse = holdingsUnset(oclc_number, session)
            logging.info(f"Response: {unsetResponse}")
        
if __name__ == "__main__":
    filename = sys.argv[1]
    setup_logging()
    main(filename)