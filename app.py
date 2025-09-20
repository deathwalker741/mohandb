from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import json
import os
from sqlalchemy import (
    create_engine,
    text,
    MetaData,
    Table,
    select,
    and_,
    or_,
    asc,
    desc,
    func,
)
from sqlalchemy.types import String, Text

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
    """Check if user can edit a specific school based on division/zone."""
    if user.get('division') == 'All Divisions':
        return True
    user_div = user.get('division')
    # Try common column names
    return (
        str(school_data.get('zone', '')).strip() == str(user_div)
        or str(school_data.get('division', '')).strip() == str(user_div)
    )

@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    # Build enriched sheet metadata for dashboard cards
    metadata = MetaData()
    sheets_info = {}
    for table_name, cfg in SHEET_CONFIGS.items():
        name = cfg.get('name', table_name)
        fixed_cols = int(cfg.get('fixed_columns', 0))
        columns = []
        total_rows = 0
        editable_columns = []
        try:
            table = Table(table_name, metadata, autoload_with=engine)
            columns = [c.name for c in table.columns]
            with engine.connect() as conn:
                total_rows = conn.execute(select(func.count()).select_from(table)).scalar() or 0
            if fixed_cols >= 0:
                editable_columns = [
                    c for idx, c in enumerate(columns)
                    if (idx + 1) > fixed_cols and c != 'id'
                ]
            else:
                editable_columns = []
        except Exception:
            # If table not found or any error, fall back to minimal info
            columns = []
            total_rows = 0
            editable_columns = []

        sheets_info[table_name] = {
            'name': name,
            'fixed_columns': fixed_cols,
            'columns': columns,
            'editable_columns': editable_columns,
            'total_rows': total_rows,
        }

    return render_template('dashboard.html', sheets=sheets_info, user=session['user'])

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

    # Reflect table
    metadata = MetaData()
    table = Table(table_name, metadata, autoload_with=engine)
    all_columns = [c.name for c in table.columns]

    # Preferred filter columns (use if present)
    preferred = {
        'division', 'zone', 'state', 'district', 'block', 'cluster',
        'program', 'board', 'vendor', 'status'
    }
    filterable = [c for c in all_columns if c in preferred]

    # Query params
    q = request.args.get('q', '').strip()
    sort = request.args.get('sort', '').strip()
    direction = request.args.get('dir', 'asc').lower()
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = max(1, min(200, int(request.args.get('per_page', 50))))
    except ValueError:
        page, per_page = 1, 50

    # Build filters from request args
    active_filters = {}
    for col in filterable:
        val = request.args.get(col, '').strip()
        if val:
            active_filters[col] = val

    # Base select
    stmt = select(table)

    # Search across string-like columns
    if q:
        string_cols = [c for c in table.c if isinstance(c.type, (String, Text))]
        if string_cols:
            stmt = stmt.where(or_(*[c.ilike(f"%{q}%") for c in string_cols]))

    # Apply equality filters
    for col, val in active_filters.items():
        stmt = stmt.where(table.c[col] == val)

    # Sorting
    if sort in all_columns:
        stmt = stmt.order_by(asc(table.c[sort]) if direction != 'desc' else desc(table.c[sort]))
    elif 'id' in all_columns:
        stmt = stmt.order_by(asc(table.c['id']))

    # Pagination
    stmt = stmt.limit(per_page).offset((page - 1) * per_page)

    # Execute query and gather filter options
    with engine.connect() as conn:
        rows = conn.execute(stmt).mappings().all()
        filter_options = {}
        for col in filterable:
            opt_stmt = select(table.c[col]).distinct().order_by(table.c[col]).limit(2000)
            vals = [r[0] for r in conn.execute(opt_stmt).all() if r[0] not in (None, '')]
            filter_options[col] = vals

    # Compute editability per row
    user = session['user']
    schools_list = [dict(r) for r in rows]
    for school in schools_list:
        school['can_edit'] = can_edit_school(user, school)

    config = SHEET_CONFIGS[table_name]
    fixed_cols = config['fixed_columns']
    sheet_data = {
        'name': config['name'],
        'columns': all_columns,
        'fixed_columns': max(0, fixed_cols),
        'editable_columns': [c for idx, c in enumerate(all_columns) if (idx + 1) > fixed_cols and c != 'id'] if fixed_cols >= 0 else [],
    }

    return render_template(
        'sheet_view.html',
        sheet_data=sheet_data,
        table_name=table_name,
        columns=all_columns,
        rows=schools_list,  # also provide as rows
        schools=schools_list,  # maintain compatibility
        q=q,
        filterable=filterable,
        filter_options=filter_options,
        active_filters=active_filters,
        sort=sort,
        direction=direction,
        page=page,
        per_page=per_page,
        user=user,
        request=request,
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
    columns = school.keys()
    
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
