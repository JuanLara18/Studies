# University Information Tool

A comprehensive Python-based solution for gathering, organizing, and comparing university information for graduate study decision-making.

## Overview

This tool automates the collection of detailed university information and organizes it into a structured Excel workbook. It's designed for prospective graduate students who need to compare multiple universities and programs across various criteria.

## Features

- Creates a well-structured Excel workbook with dedicated sheets for:
  - University profiles
  - Academic programs
  - Research labs
  - Scholarships
  - Admission requirements
  - Cost of living
  - Career outcomes
  - Personal notes
  - Application timeline

- Automated data collection from university websites (via the `fill_excel.py` script)
- Customizable data fields for comprehensive comparison
- Organized tracking of application deadlines and requirements

## Usage

1. **Create the basic Excel structure:**
   ```
   python create_excel.py
   ```

2. **Fill the Excel with scraped university data (optional):**
   ```
   python fill_excel.py
   ```

3. Open the generated `Information.xlsx` file (or `Information_Filled.xlsx` if you ran the fill script) and use it to track your university research and applications.

## Notes

- The data scraping functionality (`fill_excel.py`) should be used responsibly and in accordance with websites' terms of service.
- Manual verification of scraped data is recommended for critical decision-making information.
- The tool focuses on computer science, data science, and mathematics programs by default, but can be customized for other fields.