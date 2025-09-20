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

# Tables that are view-only (no edits allowed)
# Note: all_unique_schools is editable only by Mohan; not globally read-only.
READ_ONLY_TABLES = {
    'summary_data',
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
    email = str(user.get('email', '')).strip().lower()
    # Only this EI email has edit access globally
    if email == 'mohan.kumar@ei.study':
        return True
    # EI email-only login users (is_ei flag) are view-only
    if user.get('is_ei'):
        return False
    # Division-scoped users
    if str(user.get('division', '')).strip() == 'All Divisions':
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

def is_super_editor(user) -> bool:
    """Return True if this user can edit all columns (overrides fixed columns).

    Currently, this is restricted to Mohan's EI email.
    """
    email = str(user.get('email', '')).strip().lower()
    return email == 'mohan.kumar@ei.study'

def is_ei_user(user) -> bool:
    """True only for EI email-only login (is_ei flag). Division users from users.json are not EI here."""
    return bool(user.get('is_ei'))

def get_school_division(row: dict) -> str:
    """Best-effort to get a row's division/zone string."""
    return str(
        row.get('zone')
        or row.get('division')
        or row.get('divison')
        or ''
    )

def matches_user_division(user, row: dict) -> bool:
    """For division users, ensure row is in user's division; EI users always match."""
    if is_ei_user(user):
        return True
    udiv = str(user.get('division', '')).strip().lower()
    if not udiv or udiv == 'all divisions':
        return True
    rdiv = get_school_division(row).strip().lower()
    return rdiv == udiv

# Common key variants for School Number across sheets
SCHOOL_NO_KEYS = [
    'school_no', 'school_number', 'schoolcode', 'school_code',
    'udise_code', 'udise', 'serial_no', 'sr_no', 's_no'
]

def normalize_school_no(val):
    """Return canonical string for school_no, or None if empty/invalid."""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ('nan', 'none', 'null'):
        return None
    return s

def find_school_no_column(columns):
    """Return the first matching school number column name present in columns."""
    colset = {str(c).lower() for c in columns}
    for key in SCHOOL_NO_KEYS:
        if key in colset:
            return key
    return None

def get_school_no_from_row(row: dict):
    """Return school number value from a row dict using known keys."""
    for key in SCHOOL_NO_KEYS:
        if key in row and row[key]:
            return normalize_school_no(row[key])
    return None


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
            # Hide Summary Data from dashboard cards
            if table_name == 'summary_data':
                continue
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

@app.route('/login-ei', methods=['POST'])
def login_ei():
    """EI email-only login; any @ei.study email gets All Divisions access."""
    email = request.form.get('email', '').strip()
    if not email:
        flash('Email is required for EI login.', 'error')
        return redirect(url_for('login'))
    if not email.lower().endswith('@ei.study'):
        flash('Only @ei.study emails are allowed for EI login.', 'error')
        return redirect(url_for('login'))

    # Grant full access user session
    session['user'] = {
        'name': email.split('@')[0].replace('.', ' ').title(),
        'email': email,
        'division': 'All Divisions',
        'is_ei': True
    }
    flash('Logged in with EI access (All Divisions).', 'success')
    return redirect(url_for('index'))

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
    allow_actions = table_name not in READ_ONLY_TABLES
    # Create a mutable copy of each school row
    schools_list = [dict(school) for school in result]
    for school in schools_list:
        # Default permission
        can_edit = can_edit_school(user, school)
        # Special-case: only Mohan can edit all_unique_schools
        if table_name == 'all_unique_schools':
            email = str(user.get('email','')).strip().lower()
            can_edit = (email == 'mohan.kumar@ei.study')
        school['can_edit'] = can_edit
        # Compute safe integer edit_id; some tables may have non-integer or composite id strings
        edit_id = None
        try:
            if 'id' in school and school['id'] is not None:
                s = str(school['id']).strip()
                if s.isdigit():
                    edit_id = int(s)
        except Exception:
            edit_id = None
        school['edit_id'] = edit_id
        if not allow_actions:
            # Force no edit button on read-only sheets
            school['can_edit'] = False
    # If viewing all_unique_schools, merge optional columns from related sheets using school_no
    ext_columns = {}
    if table_name == 'all_unique_schools' and schools_list:
        try:
            with engine.connect() as conn:
                aus_cols = columns
                aus_sno_col = find_school_no_column(aus_cols)
                # Build list of school_no values present
                aus_snos = []
                seen = set()
                for r in schools_list:
                    sno = get_school_no_from_row(r)
                    if sno is not None and sno not in seen:
                        aus_snos.append(sno)
                        seen.add(sno)

                def fetch_map_for_table(tname: str):
                    cols = fetch_columns(conn, tname)
                    sno_col = find_school_no_column(cols)
                    if not sno_col or not aus_snos:
                        return cols, sno_col, {}
                    # Build IN clause safely with enumerated params
                    param_names = []
                    params = {}
                    for i, val in enumerate(aus_snos):
                        pname = f"v{i}"
                        param_names.append(f":{pname}")
                        params[pname] = str(val)
                    in_list = ", ".join(param_names)
                    sql = text(
                        f"SELECT * FROM {sql_ident(tname)} WHERE {sql_ident(sno_col)}::text IN ({in_list})"
                    )
                    rows = conn.execute(sql, params).mappings().all()
                    m = {}
                    for row in rows:
                        try:
                            key = normalize_school_no(row.get(sno_col))
                        except Exception:
                            key = None
                        if key is not None and key not in m:
                            m[key] = dict(row)
                    return cols, sno_col, m

                related = [
                    ("asset", "asset_schools"),
                    ("cares", "cares_schools"),
                    ("mm", "mindspark_math_schools"),
                    ("me", "mindspark_english_schools"),
                    ("ms", "mindspark_science_schools"),
                ]
                for prefix, tname in related:
                    rel_cols, rel_sno_col, rel_map = fetch_map_for_table(tname)
                    if not rel_cols or not rel_sno_col:
                        continue
                    # Determine displayable columns (exclude id and school_no)
                    disp_cols = [c for c in rel_cols if c not in ('id', rel_sno_col)]
                    namespaced_cols = []
                    for c in disp_cols:
                        ns = f"{prefix}__{c}"
                        namespaced_cols.append(ns)
                    # Merge into each school row
                    if namespaced_cols:
                        for s in schools_list:
                            sno = get_school_no_from_row(s)
                            if sno is None:
                                continue
                            ext_row = rel_map.get(sno)
                            if not ext_row:
                                continue
                            for c in disp_cols:
                                s[f"{prefix}__{c}"] = ext_row.get(c)
                        ext_columns[prefix] = namespaced_cols
                        # Also extend columns so template logic can include them if needed (treated as editable side)
                        columns.extend(namespaced_cols)
        except Exception as merge_err:
            try:
                app.logger.warning(f"AUS merge columns skipped: {merge_err}")
            except Exception:
                pass
    # Division users should only see schools from their zone/division on all tables
    if not is_ei_user(user):
        schools_list = [s for s in schools_list if matches_user_division(user, s)]
        
    config = SHEET_CONFIGS[table_name]
    fixed_cols = config['fixed_columns']
    
    return render_template('sheet_view.html',
                         sheet_name=config['name'],
                         table_name=table_name,
                         schools=schools_list,
                         columns=columns,
                         fixed_col_count=fixed_cols,
                         user=user,
                         allow_actions=allow_actions,
                         ext_columns=ext_columns)

@app.route('/edit/<table_name>/<int:school_id>')
def edit_school(table_name, school_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    if table_name not in SHEET_CONFIGS:
        flash('Sheet not found!', 'error')
        return redirect(url_for('view_sheet', table_name=table_name))

    # Special-case: only Mohan can edit All Unique Schools
    if table_name == 'all_unique_schools':
        email = str(session['user'].get('email', '')).strip().lower()
        if email != 'mohan.kumar@ei.study':
            flash('You do not have permission to edit this sheet.', 'error')
            return redirect(url_for('view_sheet', table_name=table_name))

    with engine.connect() as connection:
        # Cast id to text and bind the parameter as string to avoid type mismatches
        query = text(f"SELECT * FROM {sql_ident(table_name)} WHERE {sql_ident('id')}::text = :school_id")
        school = connection.execute(query, {'school_id': str(school_id)}).mappings().first()

    if not school:
        flash('School not found!', 'error')
        return redirect(url_for('view_sheet', table_name=table_name))
    
    if not can_edit_school(session['user'], school):
        flash('You do not have permission to edit this school!', 'error')
        return redirect(url_for('view_sheet', table_name=table_name))

    config = SHEET_CONFIGS[table_name]
    fixed_cols = config['fixed_columns']
    # Super editor can edit all columns (no fixed columns)
    if is_super_editor(session['user']):
        fixed_cols = 0
    columns = list(school.keys()) if school else []
    
    return render_template('edit_school.html',
                         sheet_name=config['name'],
                         table_name=table_name,
                         school=school,
                         school_id=school_id,
                         columns=columns,
                         fixed_col_count=fixed_cols,
                         user=session['user'])

@app.route('/school/<table_name>/s/<school_no>')
def view_school_detail(table_name, school_no):
    if 'user' not in session:
        return redirect(url_for('login'))
    if table_name not in SHEET_CONFIGS:
        flash('Sheet not found!', 'error')
        return redirect(url_for('index'))

    config = SHEET_CONFIGS[table_name]
    with engine.connect() as conn:
        cols = fetch_columns(conn, table_name)
        school_no_col = find_school_no_column(cols)
        if not school_no_col:
            flash('School number column not found in this sheet.', 'error')
            return redirect(url_for('view_sheet', table_name=table_name))
        # Cast school_no column to text for robust matching
        sel = text(
            f"SELECT * FROM {sql_ident(table_name)} WHERE {sql_ident(school_no_col)}::text = :sno LIMIT 1"
        )
        row = conn.execute(sel, {"sno": str(school_no)}).mappings().first()
        if not row:
            flash('School not found in this sheet.', 'error')
            return redirect(url_for('view_sheet', table_name=table_name))

    school = dict(row)
    user = session['user']
    allow_actions = table_name not in READ_ONLY_TABLES
    # Division user access gate: only their division/zone rows are visible
    if not is_ei_user(user):
        if not matches_user_division(user, school):
            flash('You do not have access to this school (different division/zone).', 'error')
            return redirect(url_for('view_sheet', table_name=table_name))
    # Only Mohan can edit all_unique_schools
    if table_name == 'all_unique_schools':
        can_edit_row = bool(allow_actions and str(user.get('email','')).strip().lower() == 'mohan.kumar@ei.study')
    else:
        can_edit_row = bool(allow_actions and can_edit_school(user, school))
    # Provide an edit_id if convertible to int
    edit_id = None
    try:
        if 'id' in school and school['id'] is not None:
            edit_id = int(str(school['id']))
    except Exception:
        edit_id = None

    # Build external sections (only for all_unique_schools view)
    ext_sections = {}
    if table_name == 'all_unique_schools':
        try:
            with engine.connect() as conn:
                # Resolve school number value from the current row if possible
                cols_here = list(school.keys())
                sno_key_here = find_school_no_column(cols_here)
                sno_val = normalize_school_no(school.get(sno_key_here) if sno_key_here else school_no)

                def fetch_one_by_sno(tname: str):
                    cols = fetch_columns(conn, tname)
                    sno_col = find_school_no_column(cols)
                    if not sno_col:
                        return {}
                    rs = conn.execute(
                        text(f"SELECT * FROM {sql_ident(tname)} WHERE {sql_ident(sno_col)}::text = :s LIMIT 1"),
                        {"s": str(sno_val) if sno_val is not None else None},
                    ).mappings().first()
                    if not rs:
                        return {}
                    d = dict(rs)
                    # drop id and school number col
                    for drop in ['id', sno_col]:
                        if drop in d:
                            d.pop(drop, None)
                    return d

                related = {
                    'asset': 'asset_schools',
                    'cares': 'cares_schools',
                    'mm': 'mindspark_math_schools',
                    'me': 'mindspark_english_schools',
                    'ms': 'mindspark_science_schools',
                }
                for key, tname in related.items():
                    ext_sections[key] = fetch_one_by_sno(tname)
        except Exception as e:
            try:
                app.logger.warning(f"view_school_detail ext fetch failed: {e}")
            except Exception:
                pass

    ext_labels = {
        'current': 'Current Info',
        'asset': 'ASSET',
        'cares': 'CARES',
        'mm': 'MS Math',
        'me': 'MS English',
        'ms': 'MS Science',
    }

    return render_template(
        'view_school.html',
        sheet_name=config['name'],
        table_name=table_name,
        school=school,
        columns=list(school.keys()),
        fixed_col_count=config.get('fixed_columns', 0),
        user=user,
        can_edit_row=can_edit_row and (edit_id is not None),
        edit_id=edit_id,
        ext_sections=ext_sections,
        ext_labels=ext_labels,
    )

@app.route('/update/<table_name>/<int:school_id>', methods=['POST'])
def update_school(table_name, school_id):
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    # Special-case: only Mohan can update All Unique Schools
    if table_name == 'all_unique_schools':
        email = str(session['user'].get('email', '')).strip().lower()
        if email != 'mohan.kumar@ei.study':
            return jsonify({'success': False, 'message': 'Permission denied'}), 403
    
    # Get all column names for the table to determine which are editable
    with engine.connect() as connection:
        # Use a no-row result to get column names
        query = text(f"SELECT * FROM {sql_ident(table_name)} WHERE 1=0;")
        columns = list(connection.execute(query).keys())
        school_query = text(f"SELECT * FROM {sql_ident(table_name)} WHERE {sql_ident('id')}::text = :school_id")
        school = connection.execute(school_query, {'school_id': str(school_id)}).mappings().first()

    if not school:
        return jsonify({'success': False, 'message': 'School not found'})
    if not can_edit_school(session['user'], school):
        return jsonify({'success': False, 'message': 'Permission denied'})

    config = SHEET_CONFIGS[table_name]
    fixed_col_count = config['fixed_columns']
    # Super editor can edit all columns (except id)
    if is_super_editor(session['user']):
        fixed_col_count = 0
    
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

    values_to_update['school_id'] = str(school_id)
    update_statement = f"UPDATE {sql_ident(table_name)} SET {', '.join(set_clauses)} WHERE {sql_ident('id')}::text = :school_id"

    try:
        with engine.connect() as connection:
            trans = connection.begin()
            # 1) Update the original sheet's row
            connection.execute(text(update_statement), values_to_update)

            # 2) Sync to all_unique_schools using school_no as identifier
            try:
                # Determine school_no value after update
                merged_row = dict(school)
                for column in editable_columns:
                    if column in request.form:
                        merged_row[column] = request.form[column]

                school_no_value = get_school_no_from_row(merged_row)
                # If school_no was updated via form but under a different alias, also try form keys
                if not school_no_value:
                    for key in SCHOOL_NO_KEYS:
                        if key in request.form and request.form[key]:
                            school_no_value = request.form[key]
                            break

                if school_no_value:
                    # Fetch columns of all_unique_schools
                    aus_cols = fetch_columns(connection, 'all_unique_schools')
                    aus_school_no_col = find_school_no_column(aus_cols)
                    if aus_school_no_col:
                        # Prepare UPDATE set clauses for intersection of columns
                        set_clauses_aus = []
                        aus_values = {}
                        for col in aus_cols:
                            if col == 'id' or col == aus_school_no_col:
                                continue
                            if col in merged_row:
                                p = to_param_key(f"aus_{col}")
                                set_clauses_aus.append(f"{sql_ident(col)} = :{p}")
                                aus_values[p] = merged_row[col]
                        aus_values['aus_school_no'] = school_no_value

                        if set_clauses_aus:
                            update_aus_sql = (
                                f"UPDATE {sql_ident('all_unique_schools')} "
                                f"SET {', '.join(set_clauses_aus)} "
                                f"WHERE {sql_ident(aus_school_no_col)}::text = :aus_school_no"
                            )
                            result = connection.execute(text(update_aus_sql), aus_values)

                            if result.rowcount == 0:
                                # Row doesn't exist; attempt INSERT with available columns
                                insert_cols = []
                                insert_params = []
                                insert_values = {}
                                # Ensure school_no is included
                                insert_cols.append(sql_ident(aus_school_no_col))
                                insert_params.append(':aus_school_no')
                                insert_values['aus_school_no'] = school_no_value
                                for col in aus_cols:
                                    if col in ('id', aus_school_no_col):
                                        continue
                                    if col in merged_row:
                                        insert_cols.append(sql_ident(col))
                                        p = to_param_key(f"aus_{col}")
                                        insert_params.append(f":{p}")
                                        insert_values[p] = merged_row[col]
                                if insert_cols:
                                    insert_sql = (
                                        f"INSERT INTO {sql_ident('all_unique_schools')} ("
                                        f"{', '.join(insert_cols)}) VALUES ({', '.join(insert_params)})"
                                    )
                                    connection.execute(text(insert_sql), insert_values)
                # else: no school_no; skip sync silently
            except Exception as sync_err:
                # Non-fatal; keep original update result but log server-side
                try:
                    app.logger.warning(f"AUS sync skipped/failed: {sync_err}")
                except Exception:
                    pass

            trans.commit()
        return jsonify({'success': True, 'message': 'School data updated successfully and synced'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Database error: {e}'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    app.run(debug=debug_mode, host='0.0.0.0', port=port)
