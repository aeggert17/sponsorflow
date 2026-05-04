import os
import csv
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, SponsorshipRequest
from werkzeug.security import generate_password_hash, check_password_hash
from decimal import Decimal

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sponsorflow.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

with app.app_context():
    db.create_all()
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if not user:
            user = User(email=email, password=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for('dashboard'))
            
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Login Failed. Check your email and password.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    status_filter = request.args.get('status')
    type_filter = request.args.get('type')
    search_query = request.args.get('search')
    
    query = SponsorshipRequest.query
    
    if status_filter:
        query = query.filter_by(status=status_filter)
    if type_filter:
        query = query.filter_by(request_type=type_filter)
    if search_query:
        query = query.filter(SponsorshipRequest.organization.ilike(f'%{search_query}%'))
        
    requests = query.order_by(SponsorshipRequest.date_requested.desc()).all()
    
    total_requested = sum(r.requested_amount for r in requests)
    total_approved = sum(r.approved_amount for r in requests)
    pending_count = sum(1 for r in requests if r.status == 'Pending')
    approved_count = sum(1 for r in requests if r.status == 'Approved')
    
    monthly_data = {}
    for r in requests:
        if r.status == 'Approved' and r.date_requested:
            month = r.date_requested.strftime('%Y-%m')
            monthly_data[month] = monthly_data.get(month, 0) + float(r.approved_amount)
            
    return render_template('dashboard.html', 
                           requests=requests, 
                           total_requested=total_requested,
                           total_approved=total_approved,
                           pending_count=pending_count,
                           approved_count=approved_count,
                           monthly_data=monthly_data)

@app.route('/request/add', methods=['GET', 'POST'])
@login_required
def add_request():
    if request.method == 'POST':
        new_req = SponsorshipRequest(
            organization=request.form.get('organization'),
            request_type=request.form.get('request_type'),
            date_requested=datetime.strptime(request.form.get('date_requested'), '%Y-%m-%d').date() if request.form.get('date_requested') else None,
            event_date=datetime.strptime(request.form.get('event_date'), '%Y-%m-%d').date() if request.form.get('event_date') else None,
            requested_amount=Decimal(request.form.get('requested_amount') or 0),
            approved_amount=Decimal(request.form.get('approved_amount') or 0),
            status=request.form.get('status', 'Pending'),
            requested_by=request.form.get('requested_by'),
            approved_by=request.form.get('approved_by'),
            comments=request.form.get('comments'),
            flyer_link=request.form.get('flyer_link'),
            marketing_follow_up=request.form.get('marketing_follow_up', 'Not Started'),
            submitted_to_accounting=True if request.form.get('submitted_to_accounting') == 'on' else False,
            date_submitted_to_accounting=datetime.strptime(request.form.get('date_submitted_to_accounting'), '%Y-%m-%d').date() if request.form.get('date_submitted_to_accounting') else None
        )
        db.session.add(new_req)
        db.session.commit()
        flash('Request added successfully!')
        return redirect(url_for('dashboard'))
    return render_template('request_form.html', req=None)

@app.route('/request/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_request(id):
    req = SponsorshipRequest.query.get_or_404(id)
    if request.method == 'POST':
        req.organization = request.form.get('organization')
        req.request_type = request.form.get('request_type')
        req.date_requested = datetime.strptime(request.form.get('date_requested'), '%Y-%m-%d').date() if request.form.get('date_requested') else None
        req.event_date = datetime.strptime(request.form.get('event_date'), '%Y-%m-%d').date() if request.form.get('event_date') else None
        req.requested_amount = Decimal(request.form.get('requested_amount') or 0)
        req.approved_amount = Decimal(request.form.get('approved_amount') or 0)
        req.status = request.form.get('status')
        req.requested_by = request.form.get('requested_by')
        req.approved_by = request.form.get('approved_by')
        req.comments = request.form.get('comments')
        req.flyer_link = request.form.get('flyer_link')
        req.marketing_follow_up = request.form.get('marketing_follow_up')
        req.submitted_to_accounting = True if request.form.get('submitted_to_accounting') == 'on' else False
        req.date_submitted_to_accounting = datetime.strptime(request.form.get('date_submitted_to_accounting'), '%Y-%m-%d').date() if request.form.get('date_submitted_to_accounting') else None
        
        db.session.commit()
        flash('Request updated successfully!')
        return redirect(url_for('dashboard'))
    return render_template('request_form.html', req=req)

@app.route('/request/delete/<int:id>', methods=['POST'])
@login_required
def delete_request(id):
    req = SponsorshipRequest.query.get_or_404(id)
    db.session.delete(req)
    db.session.commit()
    flash('Request deleted successfully!')
    return redirect(url_for('dashboard'))

@app.route('/import', methods=['GET', 'POST'])
@login_required
def import_csv():
    if request.method == 'POST':
        file = request.files.get('file')

        if not file:
            flash('No file uploaded')
            return redirect(url_for('import_csv'))

        try:
            stream = file.stream.read().decode("UTF8")
            csv_input = csv.DictReader(stream.splitlines())

            def get(row, *names):
                for name in names:
                    if name in row and row[name]:
                        return row[name].strip()
                return ""

            def money(value):
                if not value:
                    return 0
                return float(value.replace("$", "").replace(",", "").strip() or 0)

            for row in csv_input:
                new_req = SponsorshipRequest(
                    organization=get(row, "Business/Organization", "Organization", "organization") or "Unknown",
                    request_type=get(row, "Type of Request", "Request Type", "request_type") or "Other",
                    date_requested=None,
                    event_date=None,
                    requested_amount=money(get(row, "Suggested Support", "Requested Amount", "requested_amount")),
                    approved_amount=money(get(row, "Actual Support", "Approved Amount", "approved_amount")),
                    status=get(row, "Approval", "Status", "status") or "Pending",
                    requested_by=get(row, "Request Originator", "Requested By", "requested_by"),
                    approved_by=get(row, "Approved by", "Approved By", "approved_by"),
                    comments=get(row, "Comments", "comments"),
                    flyer_link=get(row, "Flyer Link", "flyer_link"),
                    marketing_follow_up=get(row, "Marketing Follow-up", "Marketing Follow-Up", "marketing_follow_up") or "Not Started",
                    submitted_to_accounting=True if get(row, "Submitted to Accounting", "submitted_to_accounting").lower() in ["yes", "y", "true", "1"] else False,
                    date_submitted_to_accounting=None,
                )

                db.session.add(new_req)

            db.session.commit()
            flash('Import successful!')

        except Exception as e:
            flash(f'Error during import: {str(e)}')

        return redirect(url_for('dashboard'))

    return render_template('import.html')
    if request.method == 'POST':
        file = request.files.get('file')

        if not file:
            flash('No file uploaded')
            return redirect(url_for('import_csv'))

        try:
            stream = file.stream.read().decode("UTF8")
            csv_input = csv.DictReader(stream.splitlines())

            for row in csv_input:
                new_req = SponsorshipRequest(
                    organization=row.get('organization', 'Unknown'),
                    request_type=row.get('request_type', 'Other'),
                    requested_amount=float(row.get('requested_amount') or 0),
                    approved_amount=float(row.get('approved_amount') or 0),
                    raw_status = get(row, "Approval", "Status", "status").lower()

if raw_status in ["yes", "approved", "y"]:
    status = "Approved"
elif raw_status in ["no", "denied", "n"]:
    status = "Denied"
else:
    status = "Pending"
                )
                db.session.add(new_req)

            db.session.commit()
            flash('Import successful!')

        except Exception as e:
            flash(f'Error during import: {str(e)}')

        return redirect(url_for('dashboard'))

    return render_template('import.html')
    if request.method == 'POST':
        file = request.files.get('file')
        if not file:
            flash('No file uploaded')
            return redirect(url_for('import_csv'))
            
        filename = 'temp_import.csv'
        file.save(filename)
        
        with open(filename, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            
        return render_template('import_mapping.html', headers=headers, filename=filename)
        
    return render_template('import.html')

@app.route('/import/process', methods=['POST'])
@login_required
def process_import():
    mapping = request.form.to_dict()
    filename = mapping.pop('filename')
    
    try:
        with open(filename, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                def get_val(system_field):
                    csv_col = mapping.get(system_field)
                    return row.get(csv_col) if csv_col else None

                def parse_date(date_str):
                    if not date_str: return None
                    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%d/%m/%Y'):
                        try:
                            return datetime.strptime(date_str, fmt).date()
                        except ValueError:
                            continue
                    return None

                def parse_numeric(val):
                    if not val: return 0
                    val = val.replace('$', '').replace(',', '').strip()
                    try:
                        return Decimal(val)
                    except:
                        return 0

                new_req = SponsorshipRequest(
                    organization=get_val('organization') or 'Unknown',
                    request_type=get_val('request_type') or 'Other',
                    date_requested=parse_date(get_val('date_requested')),
                    event_date=parse_date(get_val('event_date')),
                    requested_amount=parse_numeric(get_val('requested_amount')),
                    approved_amount=parse_numeric(get_val('approved_amount')),
                    status=get_val('status') or 'Pending',
                    requested_by=get_val('requested_by'),
                    approved_by=get_val('approved_by'),
                    comments=get_val('comments'),
                    flyer_link=get_val('flyer_link'),
                    marketing_follow_up=get_val('marketing_follow_up') or 'Not Started',
                    submitted_to_accounting=True if get_val('submitted_to_accounting') in ['Yes', 'yes', 'Y', 'y', 'True', 'true', '1'] else False,
                    date_submitted_to_accounting=parse_date(get_val('date_submitted_to_accounting'))
                )
                db.session.add(new_req)
            db.session.commit()
        os.remove(filename)
        flash('Import successful!')
    except Exception as e:
        flash(f'Error during import: {str(e)}')
        
    return redirect(url_for('dashboard'))
from models import User, SponsorshipRequest



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
