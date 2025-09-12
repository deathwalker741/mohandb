#!/usr/bin/env python3
"""
Test script for the Excel parser
"""

import sys
import os
from excel_parser import ExcelDataParser

def test_excel_parser():
    """Test the Excel parser functionality"""
    excel_file_path = r"C:\Users\mnage\Downloads\Tracker 2025-26.xlsx"
    
    print("Testing Excel Parser...")
    print(f"Excel file path: {excel_file_path}")
    
    # Check if file exists
    if not os.path.exists(excel_file_path):
        print(f"❌ Excel file not found at: {excel_file_path}")
        print("Please ensure the Excel file is in the correct location.")
        return False
    
    try:
        # Initialize parser
        parser = ExcelDataParser(excel_file_path)
        print("✅ Parser initialized successfully")
        
        # Parse Excel file
        data = parser.parse_excel()
        print("✅ Excel file parsed successfully")
        
        # Display sheet information
        print(f"\n📊 Found {len(data)} sheets:")
        for sheet_name, sheet_data in data.items():
            print(f"  - {sheet_data['name']}: {sheet_data['total_rows']} rows, {len(sheet_data['columns'])} columns")
            print(f"    Fixed columns: {len(sheet_data['fixed_columns'])}")
            print(f"    Editable columns: {len(sheet_data['editable_columns'])}")
        
        # Save to JSON
        json_file = parser.save_to_json()
        print(f"✅ Data saved to: {json_file}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_excel_parser()
    if success:
        print("\n🎉 All tests passed! The Excel parser is working correctly.")
    else:
        print("\n💥 Tests failed. Please check the error messages above.")
        sys.exit(1)
