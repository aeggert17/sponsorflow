import os
import csv
from datetime import datetime
from decimal import Decimal

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, User, SponsorshipRequest


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///sponsorflow.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

with app.app_context():
    db.create_all()


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def parse_date(date_str):
    if not date_str:
        return None

    date_str = str(date_str).strip()

    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    return None


def parse_money(value):
    if not value:
        return Decimal("0")

    value = str(value).replace("$", "").replace(",", "").strip()

    try:
        return Decimal(value)
    except Exception:
        return Decimal("0")


def normalize_status(value):
    if not value:
        return "Pending"

    value = str(value).strip().lower()

    if value in ["yes", "approved", "approve", "y"]:
        return "Approved"
    if value in ["no", "denied", "deny", "n"]:
        return "Denied"
    if value in ["pending"]:
        return "Pending"
    if value in ["paid"]:
        return "Paid"
    if value in ["completed", "complete"]:
        return "Completed"
    if value in ["under review", "review"]:
        return "Under Review"

    return "Pending"


def get_csv_value(row, *possible_names):
    for name in possible_names:
        if name in row and row[name]:
            return row[name].strip()
    return ""


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()

        if not user:
            user = User(email=email, password=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for("dashboard"))

        if check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for("dashboard"))

        flash("Login failed. Check your email and password.")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    status_filter = request.args.get("status")
    type_filter = request.args.get("type")
    search_query = request.args.get("search")

    query = SponsorshipRequest.query

    if status_filter:
        query = query.filter_by(status=status_filter)

    if type_filter:
        query = query.filter_by(request_type=type_filter)

    if search_query:
        query = query.filter(SponsorshipRequest.organization.ilike(f"%{search_query}%"))

    requests = query.order_by(SponsorshipRequest.id.desc()).all()

    total_requested = sum((r.requested_amount or 0) for r in requests)
    total_approved = sum((r.approved_amount or 0) for r in requests)
    pending_count = sum(1 for r in requests if r.status == "Pending")
    approved_count = sum(1 for r in requests if r.status == "Approved")

    monthly_data = {}

    return render_template(
        "dashboard.html",
        requests=requests,
        total_requested=total_requested,
        total_approved=total_approved,
        pending_count=pending_count,
        approved_count=approved_count,
        monthly_data=monthly_data,
    )


@app.route("/request/add", methods=["GET", "POST"])
@login_required
def add_request():
    if request.method == "POST":
        new_req = SponsorshipRequest(
            organization=request.form.get("organization"),
            request_type=request.form.get("request_type"),
            date_requested=parse_date(request.form.get("date_requested")),
            event_date=parse_date(request.form.get("event_date")),
            requested_amount=parse_money(request.form.get("requested_amount")),
            approved_amount=parse_money(request.form.get("approved_amount")),
            status=request.form.get("status", "Pending"),
            requested_by=request.form.get("requested_by"),
            approved_by=request.form.get("approved_by"),
            comments=request.form.get("comments"),
            flyer_link=request.form.get("flyer_link"),
            marketing_follow_up=request.form.get("marketing_follow_up", "Not Started"),
            submitted_to_accounting=True if request.form.get("submitted_to_accounting") == "on" else False,
            date_submitted_to_accounting=parse_date(request.form.get("date_submitted_to_accounting")),
        )

        db.session.add(new_req)
        db.session.commit()

        flash("Request added successfully!")
        return redirect(url_for("dashboard"))

    return render_template("request_form.html", req=None)


@app.route("/request/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_request(id):
    req = SponsorshipRequest.query.get_or_404(id)

    if request.method == "POST":
        req.organization = request.form.get("organization")
        req.request_type = request.form.get("request_type")
        req.date_requested = parse_date(request.form.get("date_requested"))
        req.event_date = parse_date(request.form.get("event_date"))
        req.requested_amount = parse_money(request.form.get("requested_amount"))
        req.approved_amount = parse_money(request.form.get("approved_amount"))
        req.status = request.form.get("status")
        req.requested_by = request.form.get("requested_by")
        req.approved_by = request.form.get("approved_by")
        req.comments = request.form.get("comments")
        req.flyer_link = request.form.get("flyer_link")
        req.marketing_follow_up = request.form.get("marketing_follow_up")
        req.submitted_to_accounting = True if request.form.get("submitted_to_accounting") == "on" else False
        req.date_submitted_to_accounting = parse_date(request.form.get("date_submitted_to_accounting"))

        db.session.commit()

        flash("Request updated successfully!")
        return redirect(url_for("dashboard"))

    return render_template("request_form.html", req=req)


@app.route("/request/delete/<int:id>", methods=["POST"])
@login_required
def delete_request(id):
    req = SponsorshipRequest.query.get_or_404(id)
    db.session.delete(req)
    db.session.commit()

    flash("Request deleted successfully!")
    return redirect(url_for("dashboard"))


@app.route("/import", methods=["GET", "POST"])
@login_required
def import_csv():
    if request.method == "POST":
        file = request.files.get("file")

        if not file:
            flash("No file uploaded.")
            return redirect(url_for("import_csv"))

try:
    stream = file.stream.read().decode("utf-8-sig")
    csv_input = csv.DictReader(stream.splitlines())

    count = 0

    for row in csv_input:
        raw_status = get_csv_value(row, "Approval", "Status", "status")

        new_req = SponsorshipRequest(
            organization=get_csv_value(row, "Business/Organization", "Organization", "organization") or "Unknown",
            request_type=get_csv_value(row, "Type of Request", "Request Type", "request_type") or "Other",
            date_requested=parse_date(get_csv_value(row, "Date Requested", "date_requested")),
            event_date=parse_date(get_csv_value(row, "Event Date", "event_date")),
            requested_amount=parse_money(get_csv_value(row, "Suggested Support", "Requested Amount", "requested_amount")),
            approved_amount=parse_money(get_csv_value(row, "Actual Support", "Approved Amount", "approved_amount")),
            status=normalize_status(raw_status),
            requested_by=get_csv_value(row, "Request Originator", "Requested By", "requested_by"),
            approved_by=get_csv_value(row, "Approved by", "Approved By", "approved_by"),
            comments=get_csv_value(row, "Comments", "comments"),
            flyer_link=get_csv_value(row, "Flyer Link", "flyer_link"),
            marketing_follow_up=get_csv_value(row, "Marketing Follow-up", "Marketing Follow-Up", "marketing_follow_up") or "Not Started",
            submitted_to_accounting=True if get_csv_value(row, "Submitted to Accounting", "submitted_to_accounting").lower() in ["yes","y","true","1"] else False,
            date_submitted_to_accounting=parse_date(get_csv_value(row, "Date submitted", "Date Submitted", "date_submitted_to_accounting")),
        )

        db.session.add(new_req)
        count += 1

        if count % 25 == 0:
            db.session.commit()

    db.session.commit()
    flash("Import successful!")

except Exception as e:
    flash(f"Error during import: {str(e)}")

        return redirect(url_for("dashboard"))

    return render_template("import.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
