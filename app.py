from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import json
import os
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
    """Check if user can edit a specific school based on division"""
    if user['division'] == 'All Divisions':
        return True
    # Try common variants of the zone/division key
    zone_val = (
        school_data.get('zone') or
        school_data.get('Zone') or
        school_data.get('division') or
        school_data.get('Division') or
        ''
    )
    return str(zone_val).strip() == str(user['division']).strip()

@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    # Build metadata for each sheet for display
    sheets_meta = {}
    with engine.connect() as connection:
        for table_name, cfg in SHEET_CONFIGS.items():
            # Get columns
            col_rs = connection.execute(text(f"SELECT * FROM {table_name} WHERE 1=0;"))
            columns = list(col_rs.keys())
            # Count rows (best-effort)
            try:
                count_rs = connection.execute(text(f"SELECT COUNT(*) AS c FROM {table_name};")).first()
                total_rows = int(count_rs[0]) if count_rs else 0
            except Exception:
                total_rows = 0

            fixed_count = cfg['fixed_columns']
            if fixed_count is not None and fixed_count >= 0:
                fixed_columns = list(columns[:fixed_count])
                editable_columns = [c for i, c in enumerate(columns) if i >= fixed_count and c != 'id']
            else:
                fixed_columns = list(columns)
                editable_columns = []

            sheets_meta[table_name] = {
                'name': cfg['name'],
                'columns': columns,
                'fixed_columns': fixed_columns,
                'editable_columns': editable_columns,
                'total_rows': total_rows,
            }

    return render_template('dashboard.html', sheets=sheets_meta, user=session['user'])

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

    # Parse query params for search/filter/sort
    q = request.args.get('q', '').strip()
    filter_col = request.args.get('filter_col', '').strip()
    filter_val = request.args.get('filter_val', '').strip()
    sort_by = request.args.get('sort_by', '').strip()
    sort_dir = request.args.get('sort_dir', 'asc').strip().lower()

    with engine.connect() as connection:
        # Get columns without fetching data
        col_rs = connection.execute(text(f"SELECT * FROM {table_name} WHERE 1=0;"))
        columns = list(col_rs.keys())

        # Helper to quote identifiers with potential spaces
        def qident(name: str) -> str:
            # Columns coming from DB metadata are trusted identifiers
            return '"' + name.replace('"', '') + '"'

        where_clauses = []
        params = {}

        # Free-text search across all columns except id
        if q:
            like_param = f"%{q}%"
            params['q'] = like_param
            searchables = [c for c in columns if c != 'id']
            if searchables:
                ors = [f"CAST({qident(c)} AS TEXT) ILIKE :q" for c in searchables]
                where_clauses.append('(' + ' OR '.join(ors) + ')')

        # Column-specific filter
        if filter_col and filter_col in columns and filter_val:
            params['filter_val'] = f"%{filter_val}%"
            where_clauses.append(f"CAST({qident(filter_col)} AS TEXT) ILIKE :filter_val")

        where_sql = (' WHERE ' + ' AND '.join(where_clauses)) if where_clauses else ''

        # Sorting
        if sort_by and sort_by in columns:
            sort_ident = qident(sort_by)
        else:
            sort_ident = qident('id') if 'id' in columns else qident(columns[0]) if columns else 'id'
        sort_dir_sql = 'DESC' if sort_dir == 'desc' else 'ASC'

        sql = f"SELECT * FROM {table_name}{where_sql} ORDER BY {sort_ident} {sort_dir_sql};"
        result = connection.execute(text(sql), params).mappings().all()

    user = session['user']
    # Create a mutable copy of each school row
    schools_list = [dict(school) for school in result]
    for school in schools_list:
        school['can_edit'] = can_edit_school(user, school)

    # Build sheet_data expected by templates
    config = SHEET_CONFIGS[table_name]
    fixed_count = config['fixed_columns']
    fixed_columns = []
    editable_columns = []
    if columns:
        if fixed_count is not None and fixed_count >= 0:
            fixed_columns = list(columns[:fixed_count])
            editable_columns = [c for i, c in enumerate(columns) if i >= fixed_count and c != 'id']
        else:
            fixed_columns = list(columns)
            editable_columns = []

    sheet_data = {
        'name': config['name'],
        'columns': columns,
        'fixed_columns': fixed_columns,
        'editable_columns': editable_columns,
        'total_rows': len(schools_list)
    }

    return render_template(
        'sheet_view.html',
        sheet_name=config['name'],
        table_name=table_name,
        schools=schools_list,
        columns=columns,
        fixed_col_count=fixed_count,
        sheet_data=sheet_data,
        # Echo query params for UI state
        q=q,
        filter_col=filter_col,
        filter_val=filter_val,
        sort_by=sort_by,
        sort_dir=sort_dir,
        user=user
    )

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
    columns = list(school.keys())

    # Build sheet_data for template compatibility
    if fixed_cols is not None and fixed_cols >= 0:
        fixed_columns = list(columns[:fixed_cols])
        editable_columns = [c for i, c in enumerate(columns) if i >= fixed_cols and c != 'id']
    else:
        fixed_columns = list(columns)
        editable_columns = []

    sheet_data = {
        'name': config['name'],
        'columns': columns,
        'fixed_columns': fixed_columns,
        'editable_columns': editable_columns
    }

    return render_template(
        'edit_school.html',
        sheet_name=config['name'],
        table_name=table_name,
        school=school,
        school_id=school_id,
        columns=columns,
        fixed_col_count=fixed_cols,
        sheet_data=sheet_data,
        user=session['user']
    )

@app.route('/update/<table_name>/<int:school_id>', methods=['POST'])
def update_school(table_name, school_id):
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    # Get all column names for the table to determine which are editable
    with engine.connect() as connection:
        # Use a placeholder that is unlikely to exist to get columns without fetching data
        query = text(f"SELECT * FROM {table_name} WHERE 1=0;")
        columns = connection.execute(query).keys()
        school_query = text(f"SELECT * FROM {table_name} WHERE id = :school_id")
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
            set_clauses.append(f"{column} = :{column}")
            values_to_update[column] = request.form[column]
    
    if not set_clauses:
        return jsonify({'success': False, 'message': 'No data to update'})

    values_to_update['school_id'] = school_id
    update_statement = f"UPDATE {table_name} SET {', '.join(set_clauses)} WHERE id = :school_id"

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
