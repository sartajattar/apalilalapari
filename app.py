import os
import re
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'AttarLalpari2026Key')

# Render PostgreSQL URL Fix (psycopg सह)
db_url = os.environ.get('DATABASE_URL', 'sqlite:///lalpari.db')
if db_url:
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif db_url.startswith("postgresql://") and "+psycopg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# भारतीय प्रमाणवेळ (IST: UTC + 5:30)
IST = timezone(timedelta(hours=5, minutes=30))

# --- मॉडेल्स ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    identifier = db.Column(db.String(120), unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

class BusSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(80), nullable=False)
    source_en = db.Column(db.String(80), nullable=True)
    destination = db.Column(db.String(80), nullable=False)
    destination_en = db.Column(db.String(80), nullable=True)
    bus_type = db.Column(db.String(50), default="साधी (लालपरी)")
    departure_time = db.Column(db.String(10), nullable=False)
    arrival_time = db.Column(db.String(10), nullable=True)
    via_route = db.Column(db.String(400), default="थेट")
    fare = db.Column(db.Integer, default=200)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# मराठी आणि इंग्रजी नावांचे समानार्थी मॅपिंग
STOP_MAP = {
    "solapur": "सोलापूर", "सोलापूर": "solapur",
    "pune": "पुणे", "पुणे": "pune", "swargate": "स्वारगेट", "स्वारगेट": "swargate",
    "mohol": "मोहोळ", "मोहोळ": "mohol",
    "tembhurni": "टेंभुर्णी", "टेंभुर्णी": "tembhurni",
    "indapur": "इंदापूर", "इंदापूर": "indapur",
    "bhigwan": "भिगवण", "भिगवण": "bhigwan",
    "hadapsar": "हडपसर", "हडपसर": "hadapsar",
    "uruli": "उरुळी", "उरुळी": "uruli", "uruli kanchan": "उरुळी कांचन",
    "barshi": "बार्शी", "बार्शी": "barshi",
    "kurduwadi": "कुर्डूवाडी", "कुर्डूवाडी": "kurduwadi",
    "pandharpur": "पंढरपूर", "पंढरपूर": "pandharpur",
    "sangola": "सांगोला", "सांगोला": "sangola",
    "miraj": "मिरज", "मिरज": "miraj",
    "sangli": "सांगली", "सांगली": "sangli",
    "kolhapur": "कोल्हापूर", "कोल्हापूर": "kolhapur",
    "ratnagiri": "रत्नागिरी", "रत्नागिरी": "ratnagiri"
}

def clean_text(text):
    if not text:
        return ""
    return re.sub(r'\(.*?\)', '', str(text)).strip().lower()

def stop_matches(user_input, stop_in_db):
    u = clean_text(user_input)
    s = clean_text(stop_in_db)
    if u in s or s in u:
        return True
    mapped_u = STOP_MAP.get(u, "")
    if mapped_u and (mapped_u in s or s in mapped_u):
        return True
    mapped_s = STOP_MAP.get(s, "")
    if mapped_s and (u in mapped_s or mapped_s in u):
        return True
    return False

def parse_time_minutes(t_str):
    t_str = t_str.strip().upper()
    try:
        if 'PM' in t_str or 'AM' in t_str:
            t = datetime.strptime(t_str, "%I:%M %p")
            return t.hour * 60 + t.minute
        parts = t_str.split(':')
        h = int(parts[0])
        m = int(parts[1])
        if h in [1, 2, 3, 4, 5, 6, 7] and h != 0:
            h += 12
        return h * 60 + m
    except Exception:
        return 0

# --- राऊट्स ---
@app.route('/')
def index():
    src = request.args.get('from', '').strip()
    dst = request.args.get('to', '').strip()
    req_date = request.args.get('date', '').strip()
    
    now_ist = datetime.now(IST)
    today_date = now_ist.date()
    
    if req_date:
        try:
            chosen_date = datetime.strptime(req_date, "%Y-%m-%d").date()
        except Exception:
            chosen_date = today_date
    else:
        chosen_date = today_date

    selected_date_str = chosen_date.strftime("%Y-%m-%d")
    travel_date_display = chosen_date.strftime("%d-%m-%Y")
    today_str = today_date.strftime("%d-%m-%Y")

    routes = []
    if src and dst:
        all_buses = BusSchedule.query.all()
        current_minutes = now_ist.hour * 60 + now_ist.minute
        
        for b in all_buses:
            stops = [b.source]
            if b.source_en:
                stops.append(b.source_en)
                
            if b.via_route:
                via_stops = [v.strip() for v in re.split(r'[,➔\->|/]', b.via_route) if v.strip()]
                stops.extend(via_stops)
                
            stops.append(b.destination)
            if b.destination_en:
                stops.append(b.destination_en)

            src_idx = -1
            dst_idx = -1

            for idx, stop in enumerate(stops):
                if src_idx == -1 and stop_matches(src, stop):
                    src_idx = idx
                if dst_idx == -1 and stop_matches(dst, stop):
                    dst_idx = idx

            # जर दोन्ही थांबे सापडले आणि योग्य दिशेत (From आधी, To नंतर) असतील
            if src_idx != -1 and dst_idx != -1 and src_idx < dst_idx:
                bus_minutes = parse_time_minutes(b.departure_time)

                # युझर मूळ स्थानकावरून शोधतोय की मधल्या थांब्यावरून?
                is_intermediate = not stop_matches(src, b.source)

                if chosen_date == today_date:
                    diff = bus_minutes - current_minutes
                    if diff >= 0:
                        status_type = "today"
                        is_upcoming = True
                        trip_date_label = f"आज ({chosen_date.strftime('%d %b')})"
                    else:
                        status_type = "passed_today"
                        is_upcoming = False
                        tomorrow = today_date + timedelta(days=1)
                        trip_date_label = f"उद्या ({tomorrow.strftime('%d %b')})"
                elif chosen_date > today_date:
                    diff = 9999
                    status_type = "future"
                    is_upcoming = True
                    trip_date_label = chosen_date.strftime('%d %b %Y')
                else:
                    diff = -9999
                    status_type = "past"
                    is_upcoming = False
                    trip_date_label = chosen_date.strftime('%d %b %Y')

                routes.append({
                    'bus': b,
                    'diff': diff,
                    'is_upcoming': is_upcoming,
                    'status_type': status_type,
                    'trip_date_label': trip_date_label,
                    'is_intermediate': is_intermediate,
                    'user_from': src
                })
        
        # शोधलेल्या वेळेनंतरच्या आगामी बसेस आधी दाखवणे
        routes.sort(key=lambda x: (not x['is_upcoming'], parse_time_minutes(x['bus'].departure_time)))

    available_stops = set()
    for row in BusSchedule.query.all():
        if row.source: available_stops.add(row.source)
        if row.source_en: available_stops.add(row.source_en)
        if row.destination: available_stops.add(row.destination)
        if row.destination_en: available_stops.add(row.destination_en)
        if row.via_route:
            for s in re.split(r'[,➔\->|/]', row.via_route):
                clean_s = s.strip()
                if clean_s and "मार्गे" not in clean_s:
                    available_stops.add(clean_s)
        
    current_time_str = now_ist.strftime("%I:%M %p")
    return render_template('index.html', routes=routes, 
                           sources=sorted(list(available_stops)), 
                           destinations=sorted(list(available_stops)), 
                           src=src, dst=dst, 
                           current_time=current_time_str,
                           today_str=today_str,
                           selected_date_str=selected_date_str,
                           travel_date_display=travel_date_display)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        password = request.form.get('password')
        user = User.query.filter_by(identifier=identifier).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('यशस्वीरीत्या लॉगिन झाले!', 'success')
            return redirect(url_for('index'))
        flash('मोबाईल क्रमांक किंवा पासवर्ड चुकीचा आहे!', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        full_name = request.form.get('full_name', '').strip()
        password = request.form.get('password')
        
        if User.query.filter_by(identifier=identifier).first():
            flash('हा क्रमांक आधीच नोंदणीकृत आहे!', 'warning')
            return redirect(url_for('register'))
            
        hashed_pwd = generate_password_hash(password, method='scrypt')
        new_user = User(identifier=identifier, full_name=full_name, password=hashed_pwd)
        db.session.add(new_user)
        db.session.commit()
        flash('नोंदणी यशस्वी झाली! आता लॉगिन करा.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        password = request.form.get('password')
        user = User.query.filter_by(identifier=identifier, is_admin=True).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('admin_dashboard'))
        flash('ॲडमिन आयडी किंवा पासवर्ड चुकीचा आहे!', 'danger')
    return render_template('admin_login.html')

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('परवानगी नाही!', 'danger')
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        new_bus = BusSchedule(
            source=request.form.get('source').strip(),
            source_en=request.form.get('source_en', '').strip(),
            destination=request.form.get('destination').strip(),
            destination_en=request.form.get('destination_en', '').strip(),
            bus_type=request.form.get('bus_type'),
            departure_time=request.form.get('departure_time').strip(),
            arrival_time=request.form.get('arrival_time', '').strip(),
            via_route=request.form.get('via_route', '').strip(),
            fare=int(request.form.get('fare', 0))
        )
        db.session.add(new_bus)
        db.session.commit()
        flash('नवीन गाडी वेळापत्रकात जोडली!', 'success')
        return redirect(url_for('admin_dashboard'))

    all_buses = BusSchedule.query.order_by(BusSchedule.departure_time.asc()).all()
    return render_template('admin_dashboard.html', buses=all_buses)

@app.route('/admin/edit/<int:bus_id>', methods=['POST'])
@login_required
def edit_bus(bus_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))
    bus = BusSchedule.query.get_or_404(bus_id)
    bus.source = request.form.get('source').strip()
    bus.source_en = request.form.get('source_en', '').strip()
    bus.destination = request.form.get('destination').strip()
    bus.destination_en = request.form.get('destination_en', '').strip()
    bus.bus_type = request.form.get('bus_type')
    bus.departure_time = request.form.get('departure_time').strip()
    bus.arrival_time = request.form.get('arrival_time', '').strip()
    bus.via_route = request.form.get('via_route', '').strip()
    bus.fare = int(request.form.get('fare', 0))
    db.session.commit()
    flash('गाडीचे तपशील अपडेट केले!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete/<int:bus_id>')
@login_required
def delete_bus(bus_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))
    bus = BusSchedule.query.get_or_404(bus_id)
    db.session.delete(bus)
    db.session.commit()
    flash('गाडी हटवली!', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('लॉगआउट झाले.', 'info')
    return redirect(url_for('index'))

with app.app_context():
    db.create_all()
    admin = User.query.filter_by(identifier="apalilalpari").first()
    if not admin:
        admin = User(
            identifier="apalilalpari",
            full_name="Aapli Lalpari Admin",
            password=generate_password_hash("Attar@123", method='scrypt'),
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True, port=5000)