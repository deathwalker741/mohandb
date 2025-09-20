from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import json
import os
import re
from sqlalchemy import create_engine, text

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key')

# --- Database Connection ---
# Railway provides this automatically as an environment variable
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set!")
engine = create_engine(DATABASE_URL)

# --- Define Sheet to Table Mapping and Configurations ---
SHEET_CONFIGS = {
    'asset_schools': {'name': 'ASSET Schools', 'fixed_columns': 8},
    'cares_schools': {'name': 'CARES Schools', 'fixed_columns': 10},
    'mindspark_math_schools': {'name': 'Mindspark Math Schools', 'fixed_columns': 6},
    'mindspark_english_schools': {'name': 'Mindspark English Schools', 'fixed_columns': 6},
    'mindspark_science_schools': {'name': 'Mindspark Science Schools', 'fixed_columns': 6},
    'all_unique_schools': {'name': 'All Unique Schools', 'fixed_columns': 6},
    'summary_data': {'name': 'Summary Data', 'fixed_columns': -1}
}

def load_users():
    """Load users from JSON file"""
    try:
        with open('users.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def authenticate_user(email, password):
    """Authenticate user with email and password"""
    users = load_users()
    for user in users:
        if user['email'] == email and user['password'] == password:
            return user
    return None

def can_edit_school(user, school_data):
    """Check if user can edit a specific school based on division/zone fields.

    Be tolerant to different column names that may come from Excel normalization
    (e.g., 'zone' vs 'division').
    """
    if user.get('division') == 'All Divisions':
        return True
    # Try common variants
    school_division = (
        school_data.get('zone')
        or school_data.get('division')
        or school_data.get('divison')  # common misspelling safeguard
        or ''
    )
    return str(school_division).strip().lower() == str(user.get('division', '')).strip().lower()


def sql_ident(name: str) -> str:
    """Safely quote SQL identifiers for Postgres (handles dots, leading digits, etc.)."""
    return '"' + str(name).replace('"', '""') + '"'


def to_param_key(name: str) -> str:
    """Make a safe SQLAlchemy bind parameter key from an arbitrary column name."""
    safe = re.sub(r"[^0-9a-zA-Z_]", "_", str(name))
    if re.match(r"^\d", safe):
        safe = f"c_{safe}"
    return safe


def fetch_columns(conn, table_name: str):
    """Get ordered column names from information_schema (works even for empty tables)."""
    rs = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :t
            ORDER BY ordinal_position
            """
        ),
        {"t": table_name},
    )
    return [row[0] for row in rs]

@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    # Build dashboard metadata with actual column lists per table (robust)
    dashboard_sheets = {}
    with engine.connect() as conn:
        for table_name, cfg in SHEET_CONFIGS.items():
            columns = fetch_columns(conn, table_name)
            raw_fixed = int(cfg.get('fixed_columns', 0))
            # Clamp to valid range [0, len(columns)]
            fixed_count = max(0, min(raw_fixed, len(columns)))
            fixed_cols = columns[:fixed_count]
            editable_cols = [c for i, c in enumerate(columns) if (i + 1) > fixed_count and c != 'id']

            dashboard_sheets[table_name] = {
                'name': cfg.get('name', table_name),
                'fixed_count': fixed_count,
                'fixed_cols': fixed_cols,
                'editable_cols': editable_cols,
            }

    return render_template('dashboard.html', sheets=dashboard_sheets, user=session['user'])

@app.route('/health')
def health_check():
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


@app.route('/sheet/<table_name>')
def view_sheet(table_name):
    if 'user' not in session:
        return redirect(url_for('login'))
    if table_name not in SHEET_CONFIGS:
        flash('Sheet not found!', 'error')
        return redirect(url_for('index'))

    with engine.connect() as connection:
        # Quote identifiers to be safe
        query = text(f"SELECT * FROM {sql_ident(table_name)} ORDER BY {sql_ident('id')};")
        result = connection.execute(query).mappings().all()
        columns = list(result[0].keys()) if result else []
    
    user = session['user']
    # Create a mutable copy of each school row
    schools_list = [dict(school) for school in result]
    for school in schools_list:
        school['can_edit'] = can_edit_school(user, school)
    # Show only schools the user can edit
    schools_list = [s for s in schools_list if s.get('can_edit')]
        
    config = SHEET_CONFIGS[table_name]
    fixed_cols = config['fixed_columns']
    
    return render_template('sheet_view.html',
                         sheet_name=config['name'],
                         table_name=table_name,
                         schools=schools_list,
                         columns=columns,
                         fixed_col_count=fixed_cols,
                         user=user)

@app.route('/edit/<table_name>/<int:school_id>')
def edit_school(table_name, school_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    if table_name not in SHEET_CONFIGS:
        flash('Sheet not found!', 'error')
        return redirect(url_for('view_sheet', table_name=table_name))

    with engine.connect() as connection:
        query = text(f"SELECT * FROM {table_name} WHERE id = :school_id")
        school = connection.execute(query, {'school_id': school_id}).mappings().first()

    if not school:
        flash('School not found!', 'error')
        return redirect(url_for('view_sheet', table_name=table_name))
    
    if not can_edit_school(session['user'], school):
        flash('You do not have permission to edit this school!', 'error')
        return redirect(url_for('view_sheet', table_name=table_name))

    config = SHEET_CONFIGS[table_name]
    fixed_cols = config['fixed_columns']
    columns = list(school.keys()) if school else []
    
    return render_template('edit_school.html',
                         sheet_name=config['name'],
                         table_name=table_name,
                         school=school,
                         school_id=school_id,
                         columns=columns,
                         fixed_col_count=fixed_cols,
                         user=session['user'])

@app.route('/update/<table_name>/<int:school_id>', methods=['POST'])
def update_school(table_name, school_id):
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    # Get all column names for the table to determine which are editable
    with engine.connect() as connection:
        # Use a no-row result to get column names
        query = text(f"SELECT * FROM {sql_ident(table_name)} WHERE 1=0;")
        columns = list(connection.execute(query).keys())
        school_query = text(f"SELECT * FROM {sql_ident(table_name)} WHERE {sql_ident('id')} = :school_id")
        school = connection.execute(school_query, {'school_id': school_id}).mappings().first()

    if not school:
        return jsonify({'success': False, 'message': 'School not found'})
    if not can_edit_school(session['user'], school):
        return jsonify({'success': False, 'message': 'Permission denied'})

    config = SHEET_CONFIGS[table_name]
    fixed_col_count = config['fixed_columns']
    
    # We skip the 'id' column, so we use index + 1
    editable_columns = [col for idx, col in enumerate(columns) if idx + 1 > fixed_col_count and col != 'id']

    # Build the SQL UPDATE statement securely
    set_clauses = []
    values_to_update = {}
    for column in editable_columns:
        if column in request.form:
            param_key = to_param_key(column)
            set_clauses.append(f"{sql_ident(column)} = :{param_key}")
            values_to_update[param_key] = request.form[column]
    
    if not set_clauses:
        return jsonify({'success': False, 'message': 'No data to update'})

    values_to_update['school_id'] = school_id
    update_statement = f"UPDATE {sql_ident(table_name)} SET {', '.join(set_clauses)} WHERE {sql_ident('id')} = :school_id"

    try:
        with engine.connect() as connection:
            trans = connection.begin()
            connection.execute(text(update_statement), values_to_update)
            trans.commit()
        return jsonify({'success': True, 'message': 'School data updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Database error: {e}'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    app.run(debug=debug_mode, host='0.0.0.0', port=port)
