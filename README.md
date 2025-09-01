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
├── orders/
    └── amex/
        └── vendor-name_YYYYMMDD
    ├── workday/
        └── vendor-name_YYYYMMDD
├── invoices/
    └── YYYYMMDD_Invoices-To-Key/
    ├── done/
├── JLG/
    └── YYYYMMDD/
├── pyproject.toml
├── uv.lock
├── README.md
├── src/
│   └── library_acquisitions/   # Snake_case for Python package
│       ├── __init__.py
│       ├── .env
│       ├── templates/
│           └── generic_book_template.json
│           ├── generic_films_template.json
│       ├── generic_pol_creator.py
│       ├── oclc_helpers.py
│       ├── alma_create_po_line.py
│       ├── amazon_pol_creator.py
└── docs/
└── weeding/
```

## Running Scripts

1. 