import pandas as pd
import json
import os
from typing import Dict, List, Any

class ExcelDataParser:
    def __init__(self, excel_file_path: str):
        self.excel_file_path = excel_file_path
        self.sheets_data = {}
        self.sheet_configs = {
            'ASSET': {'fixed_columns': 8, 'name': 'ASSET Schools'},
            'CARES': {'fixed_columns': 10, 'name': 'CARES Schools'},
            'Mindspark-Math': {'fixed_columns': 6, 'name': 'Mindspark Math Schools'},
            'Mindspark-Eng': {'fixed_columns': 6, 'name': 'Mindspark English Schools'},
            'Mindspark-Science': {'fixed_columns': 6, 'name': 'Mindspark Science Schools'},
            'Unique Schools': {'fixed_columns': 6, 'name': 'All Unique Schools'},
            'Sheet1': {'fixed_columns': -1, 'name': 'Summary Data'}  # -1 means all columns are fixed
        }
    
    def parse_excel(self) -> Dict[str, Any]:
        """Parse the Excel file and return structured data"""
        try:
            # Read all sheets
            excel_file = pd.ExcelFile(self.excel_file_path)
            print(f"Available sheets: {excel_file.sheet_names}")
            
            for sheet_name in excel_file.sheet_names:
                # Use the actual sheet name or create a config for it
                if sheet_name in self.sheet_configs:
                    config = self.sheet_configs[sheet_name]
                else:
                    # Create a default config for unknown sheets
                    config = {'fixed_columns': 2, 'name': sheet_name}
                
                df = pd.read_excel(self.excel_file_path, sheet_name=sheet_name)
                
                # Clean the data
                df = df.dropna(how='all')  # Remove completely empty rows
                df = df.fillna('')  # Fill NaN values with empty strings
                
                # Get column configuration
                fixed_cols = config['fixed_columns']
                
                # Determine editable columns
                if fixed_cols == -1:
                    editable_columns = []
                    fixed_columns = list(df.columns)
                else:
                    fixed_columns = list(df.columns[:fixed_cols])
                    editable_columns = list(df.columns[fixed_cols:])
                
                # Convert to records (list of dictionaries)
                records = df.to_dict('records')
                
                self.sheets_data[sheet_name] = {
                    'name': config['name'],
                    'columns': list(df.columns),
                    'fixed_columns': fixed_columns,
                    'editable_columns': editable_columns,
                    'data': records,
                    'total_rows': len(records)
                }
            
            return self.sheets_data
            
        except Exception as e:
            print(f"Error parsing Excel file: {str(e)}")
            return {}
    
    def save_to_json(self, output_file: str = 'schools_data.json'):
        """Save parsed data to JSON file"""
        def json_serializer(obj):
            """Custom JSON serializer for datetime objects"""
            if hasattr(obj, 'isoformat'):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.sheets_data, f, indent=2, ensure_ascii=False, default=json_serializer)
        return output_file
    
    def update_school_data(self, sheet_name: str, school_id: int, updated_data: Dict[str, Any]):
        """Update school data and save back to Excel"""
        try:
            if sheet_name not in self.sheets_data:
                return False
            
            sheet_data = self.sheets_data[sheet_name]
            editable_cols = sheet_data['editable_columns']
            
            # Validate that only editable columns are being updated
            for key in updated_data.keys():
                if key not in editable_cols:
                    return False
            
            # Update the data
            if 0 <= school_id < len(sheet_data['data']):
                sheet_data['data'][school_id].update(updated_data)
                
                # Save back to Excel
                self.save_to_excel()
                return True
            
            return False
            
        except Exception as e:
            print(f"Error updating school data: {str(e)}")
            return False
    
    def save_to_excel(self):
        """Save current data back to Excel file"""
        try:
            with pd.ExcelWriter(self.excel_file_path, engine='openpyxl') as writer:
                for sheet_name, sheet_data in self.sheets_data.items():
                    df = pd.DataFrame(sheet_data['data'])
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
            return True
        except Exception as e:
            print(f"Error saving to Excel: {str(e)}")
            return False

# Example usage
if __name__ == "__main__":
    parser = ExcelDataParser(r"C:\Users\mnage\Downloads\Tracker 2025-26.xlsx")
    data = parser.parse_excel()
    parser.save_to_json()
    print("Excel data parsed and saved successfully!")
