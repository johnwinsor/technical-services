## Setup

1. Clone repo
2. `cd technical-services`
3. `uv sync`
4. Activate the environment (if not using direnv)
   - `source .venv/bin/activate`
5. Create .env in src/library_acquisitions
   - Copy .env.local to .env
    ```
    # Alma API Configuration
    # Replace with your actual API key from Ex Libris Developer Network
    ALMA_API_KEY=XXXXXXXXXXXXXXXXXXXXX

    # Alma API Base URL 
    # North America: https://api-na.hosted.exlibrisgroup.com
    # Europe: https://api-eu.hosted.exlibrisgroup.com  
    # Asia Pacific: https://api-ap.hosted.exlibrisgroup.com
    ALMA_BASE_URL=https://api-na.hosted.exlibrisgroup.com

    # WorldCat API Credentials
    WORLDCAT_API_KEY=xxxxxxxxxxxxxxxxxxxxx
    WORLDCAT_API_SECRET=xxxxxxxxxxxxxxxxxx
    ```

## Project Structure

```
technical-services/
├── .venv
├── uv.lock
├── .gitignore
├── .python-version
├── pyproject.toml
├── README.md
├── orders/
    └── amex/
        └── vendor-name_YYYYMMDD
    ├── workday/
        └── vendor-name_YYYYMMDD
├── invoices/
    └── YYYYMMDD_Invoices-To-Key/
    ├── keyed/
    ├── EDI/
        └── loaded
├── JLG/
    └── Delivery-NO_#######/
├── src/
│   └── collection_management/
│       ├── __init__.py
│   └── library_acquisitions/
│       ├── __init__.py
│       ├── .env
│       ├── templates/
│           └── generic_book_template.json
│           ├── generic_films_template.json
│       ├── generic_pol_creator.py
│       ├── oclc_helpers.py
│       ├── alma_create_po_line.py
│       ├── amazon_pol_creator.py
├── withdrawals/
└── weeding/
```

## Running Scripts

1. 