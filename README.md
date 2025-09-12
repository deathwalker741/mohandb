# School Management Dashboard

A comprehensive web-based dashboard for managing school data with role-based access control and Excel integration.

## Features

- **Multi-sheet Excel Integration**: Supports 6 different sheets with configurable editable/fixed columns
- **Role-based Access Control**: Users can only edit schools in their assigned division
- **Modern UI**: Responsive design with Bootstrap 5 and Font Awesome icons
- **Real-time Updates**: Changes are immediately saved back to the Excel file
- **Secure Authentication**: 6-digit password system for each user

## Sheet Configuration

- **Sheet 1**: First 8 columns fixed, rest editable
- **Sheet 2**: First 10 columns fixed, rest editable  
- **Sheet 3**: First 6 columns fixed, rest editable
- **Sheet 4**: First 6 columns fixed, rest editable
- **Sheet 5**: First 6 columns fixed, rest editable
- **Sheet 6**: All columns fixed (system data)

## User Access Levels

- **All Divisions**: Can edit all schools across all divisions
- **Division-specific**: Can edit schools only in their assigned division (East, North, South, West)
- **View-only**: Can view schools from other divisions but cannot edit

## Setup Instructions

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Place Excel File**:
   - Ensure your Excel file is located at: `C:\Users\mnage\Downloads\Tracker 2025-26.xlsx`
   - Or update the path in `app.py` (line 12)

3. **Run the Application**:
   ```bash
   python app.py
   ```

4. **Access the Dashboard**:
   - Open your browser and go to: `http://localhost:5000`
   - Login with any user credentials from `users.json`

## User Credentials

The system includes 27 pre-configured users with 6-digit passwords. Each user is assigned to a specific division:

- **East Division**: 5 users
- **North Division**: 6 users  
- **South Division**: 6 users
- **West Division**: 6 users
- **All Divisions**: 2 users (full access)

## File Structure

```
mohandb/
├── app.py                 # Main Flask application
├── excel_parser.py        # Excel file processing
├── users.json            # User credentials and divisions
├── requirements.txt      # Python dependencies
├── templates/            # HTML templates
│   ├── base.html        # Base template
│   ├── login.html       # Login page
│   ├── dashboard.html   # Main dashboard
│   ├── sheet_view.html  # Sheet data view
│   └── edit_school.html # School editing interface
└── README.md            # This file
```

## Usage

1. **Login**: Use your assigned email and 6-digit password
2. **Dashboard**: View all available sheets and their information
3. **Sheet View**: Click on any sheet to see the list of schools
4. **Edit School**: Click "Edit" on any school you have permission to modify
5. **Save Changes**: Only editable columns can be modified; changes are saved immediately

## Security Features

- Session-based authentication
- Division-based access control
- Fixed column protection
- Input validation
- Secure password system

## Technical Details

- **Backend**: Flask (Python)
- **Frontend**: Bootstrap 5, jQuery, Font Awesome
- **Data Storage**: Excel file integration with pandas/openpyxl
- **Authentication**: Session-based with JSON user storage
- **Responsive Design**: Mobile-friendly interface

## Troubleshooting

- Ensure the Excel file path is correct
- Check that all dependencies are installed
- Verify user credentials in `users.json`
- Check console for any error messages

## Support

For technical support or feature requests, please contact the development team.
