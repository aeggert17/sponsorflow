from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
@property
def is_active(self):
    return True
    
class SponsorshipRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    organization = db.Column(db.String(200), nullable=False)
    request_type = db.Column(db.String(50), default='Sponsorship')
    date_requested = db.Column(db.Date, nullable=True)
    event_date = db.Column(db.Date, nullable=True)
    requested_amount = db.Column(db.Numeric(10, 2), default=0)
    approved_amount = db.Column(db.Numeric(10, 2), default=0)
    status = db.Column(db.String(50), default='Pending')
    requested_by = db.Column(db.String(100), nullable=True)
    approved_by = db.Column(db.String(100), nullable=True)
    comments = db.Column(db.Text, nullable=True)
    flyer_link = db.Column(db.String(500), nullable=True)
    marketing_follow_up = db.Column(db.String(50), default='Not Started')
    submitted_to_accounting = db.Column(db.Boolean, default=False)
    date_submitted_to_accounting = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
