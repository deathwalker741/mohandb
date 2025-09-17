from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import json
import os
from excel_parser import ExcelDataParser
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key')

# Global variables
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
excel_file_path = os.environ.get('EXCEL_PATH', os.path.join(BASE_DIR, 'data', 'Tracker 2025-26.xlsx'))
parser = None
schools_data = {}

def load_users():
    """Load users from JSON file"""
    try:
        with open('users.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def load_schools_data():
    """Load schools data from Excel file"""
    global parser, schools_data
    try:
        parser = ExcelDataParser(excel_file_path)
        schools_data = parser.parse_excel()
        return True
    except Exception as e:
        print(f"Error loading schools data: {str(e)}")
        return False

def authenticate_user(email, password):
    """Authenticate user with email and password"""
    users = load_users()
    for user in users:
        if user['email'] == email and user['password'] == password:
            return user
    return None

def can_edit_school(user, school_data):
    """Check if user can edit a specific school based on division"""
    if user['division'] == 'All Divisions':
        return True
    
    # Check if school belongs to user's division
    # Look for Zone column (which is the actual column name in the data)
    school_zone = school_data.get('Zone', '')
    user_division = user['division']
    
    # Debug print to see what's happening
    print(f"User: {user['name']} ({user_division}) | School Zone: {school_zone} | Can Edit: {school_zone == user_division}")
    
    return school_zone == user_division

@app.route('/')
def index():
    """Main dashboard page"""
    if 'user' not in session:
        return redirect(url_for('login'))
    
    if not schools_data:
        load_schools_data()
    
    return render_template('dashboard.html', 
                         sheets=schools_data, 
                         user=session['user'])

@app.route('/health')
def health_check():
    """Unauthenticated healthcheck endpoint"""
    return jsonify({"status": "healthy"}), 200

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = authenticate_user(email, password)
        if user:
            session['user'] = user
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid email or password!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout user"""
    session.pop('user', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/sheet/<sheet_name>')
def view_sheet(sheet_name):
    """View specific sheet data"""
    if 'user' not in session:
        return redirect(url_for('login'))
    
    if sheet_name not in schools_data:
        flash('Sheet not found!', 'error')
        return redirect(url_for('index'))
    
    sheet_data = schools_data[sheet_name]
    user = session['user']
    
    # Show all schools, but mark which ones can be edited
    filtered_schools = []
    for school in sheet_data['data']:
        # Add all schools for viewing, but mark edit permissions
        school['can_edit'] = can_edit_school(user, school)
        filtered_schools.append(school)
    
    return render_template('sheet_view.html', 
                         sheet_name=sheet_name,
                         sheet_data=sheet_data,
                         schools=filtered_schools,
                         user=user)

@app.route('/edit/<sheet_name>/<int:school_id>')
def edit_school(sheet_name, school_id):
    """Edit school data"""
    if 'user' not in session:
        return redirect(url_for('login'))
    
    if sheet_name not in schools_data:
        flash('Sheet not found!', 'error')
        return redirect(url_for('index'))
    
    sheet_data = schools_data[sheet_name]
    user = session['user']
    
    if school_id >= len(sheet_data['data']):
        flash('School not found!', 'error')
        return redirect(url_for('view_sheet', sheet_name=sheet_name))
    
    school = sheet_data['data'][school_id]
    
    # Check if user can edit this school
    if not can_edit_school(user, school):
        flash('You do not have permission to edit this school!', 'error')
        return redirect(url_for('view_sheet', sheet_name=sheet_name))
    
    return render_template('edit_school.html',
                         sheet_name=sheet_name,
                         sheet_data=sheet_data,
                         school=school,
                         school_id=school_id,
                         user=user)

@app.route('/update/<sheet_name>/<int:school_id>', methods=['POST'])
def update_school(sheet_name, school_id):
    """Update school data"""
    if 'user' not in session:
        return redirect(url_for('login'))
    
    if sheet_name not in schools_data:
        return jsonify({'success': False, 'message': 'Sheet not found'})
    
    sheet_data = schools_data[sheet_name]
    user = session['user']
    
    if school_id >= len(sheet_data['data']):
        return jsonify({'success': False, 'message': 'School not found'})
    
    school = sheet_data['data'][school_id]
    
    # Check if user can edit this school
    if not can_edit_school(user, school):
        return jsonify({'success': False, 'message': 'Permission denied'})
    
    # Get updated data (only editable columns)
    updated_data = {}
    for column in sheet_data['editable_columns']:
        if column in request.form:
            updated_data[column] = request.form[column]
    
    # Update the data
    if parser and parser.update_school_data(sheet_name, school_id, updated_data):
        # Reload data to reflect changes
        load_schools_data()
        return jsonify({'success': True, 'message': 'School data updated successfully'})
    else:
        return jsonify({'success': False, 'message': 'Failed to update school data'})

@app.route('/api/schools/<sheet_name>')
def api_schools(sheet_name):
    """API endpoint to get schools data"""
    if 'user' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if sheet_name not in schools_data:
        return jsonify({'error': 'Sheet not found'}), 404
    
    sheet_data = schools_data[sheet_name]
    user = session['user']
    
    # Show all schools, but mark which ones can be edited
    filtered_schools = []
    for school in sheet_data['data']:
        # Add all schools for viewing, but mark edit permissions
        school['can_edit'] = can_edit_school(user, school)
        filtered_schools.append(school)
    
    return jsonify({
        'sheet_name': sheet_data['name'],
        'columns': sheet_data['columns'],
        'fixed_columns': sheet_data['fixed_columns'],
        'editable_columns': sheet_data['editable_columns'],
        'schools': filtered_schools
    })

if __name__ == '__main__':
    # Load schools data on startup
    if load_schools_data():
        print("Schools data loaded successfully!")
    else:
        print("Failed to load schools data!")
    
    # Get port from environment variable (for production) or use 5000 for local
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    
    app.run(debug=debug_mode, host='0.0.0.0', port=port)
