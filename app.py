import os
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'AttarLalpari2026Key')

# Render PostgreSQL फिक्स
db_url = os.environ.get('DATABASE_URL', 'sqlite:///lalpari.db')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
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
    via_route = db.Column(db.String(300), default="थेट")
    fare = db.Column(db.Integer, default=200)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def calculate_next_bus_meta(dep_time_str):
    now = datetime.now(IST)
    try:
        dep_hour, dep_min = map(int, dep_time_str.split(':'))
        bus_minutes = dep_hour * 60 + dep_min
        current_minutes = now.hour * 60 + now.minute
        diff = bus_minutes - current_minutes
        return diff
    except Exception:
        return -9999

# --- राऊट्स ---
@app.route('/')
def index():
    src = request.args.get('from', '').strip()
    dst = request.args.get('to', '').strip()
    
    routes = []
    if src and dst:
        query = BusSchedule.query.filter(
            or_(
                BusSchedule.source.ilike(f"%{src}%"),
                BusSchedule.source_en.ilike(f"%{src}%")
            ),
            or_(
                BusSchedule.destination.ilike(f"%{dst}%"),
                BusSchedule.destination_en.ilike(f"%{dst}%")
            )
        ).all()
        
        for b in query:
            diff = calculate_next_bus_meta(b.departure_time)
            routes.append({
                'bus': b,
                'diff': diff,
                'is_upcoming': diff >= 0
            })
        
        routes.sort(key=lambda x: (not x['is_upcoming'], x['bus'].departure_time))

    sources = set()
    destinations = set()
    for row in BusSchedule.query.all():
        if row.source: sources.add(row.source)
        if row.source_en: sources.add(row.source_en)
        if row.destination: destinations.add(row.destination)
        if row.destination_en: destinations.add(row.destination_en)
        
    current_time_str = datetime.now(IST).strftime("%I:%M %p")
    return render_template('index.html', routes=routes, 
                           sources=sorted(list(sources)), 
                           destinations=sorted(list(destinations)), 
                           src=src, dst=dst, current_time=current_time_str)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('identifier').strip()
        password = request.form.get('password')
        user = User.query.filter_by(identifier=identifier).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('यशस्वीरीत्या लॉगिन झाले!', 'success')
            return redirect(url_for('index'))
        flash('मोबाईल/ईमेल किंवा पासवर्ड चुकीचा आहे!', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        identifier = request.form.get('identifier').strip()
        full_name = request.form.get('full_name').strip()
        password = request.form.get('password')
        
        if User.query.filter_by(identifier=identifier).first():
            flash('हा मोबाईल क्रमांक किंवा ईमेल आधीच नोंदणीकृत आहे!', 'warning')
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
        identifier = request.form.get('identifier').strip()
        password = request.form.get('password')
        user = User.query.filter_by(identifier=identifier, is_admin=True).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('admin_dashboard'))
        flash('ॲडमिन युझरनेम किंवा पासवर्ड चुकीचा आहे!', 'danger')
    return render_template('admin_login.html')

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('तुम्हाला या पानावर जाण्याची परवानगी नाही!', 'danger')
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
        flash('नवीन गाडीचे वेळापत्रक यशस्वीपणे जोडले!', 'success')
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
    flash('बसचे वेळापत्रक यशस्वीपणे अपडेट केले!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete/<int:bus_id>')
@login_required
def delete_bus(bus_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))
    bus = BusSchedule.query.get_or_404(bus_id)
    db.session.delete(bus)
    db.session.commit()
    flash('गाडीचे रेकॉर्ड हटवले!', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('लॉगआउट यशस्वी झाले.', 'info')
    return redirect(url_for('index'))

# --- डेटाबेस इनिशिएलायझेशन ---
with app.app_context():
    db.create_all()
    
    # ॲडमिन क्रेडेंशियल्स
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

    VIA_PUNE = "मोहोळ, टेंभुर्णी, इंदापूर, भिगवण, उरुळी कांचन, हडपसर, स्वारगेट"
    VIA_RATNAGIRI = "मोहोळ, पंढरपूर, सांगोला, शिर्ढोण, मिरज, सांगली, कोल्हापूर मार्गे रत्नागिरी"

    # १. सोलापूर ➔ रत्नागिरी बसेस (नवे स्क्रीनशॉट्स)
    ratnagiri_schedules = [
        # (वेळ, पोहोच, प्रकार, तिकीट, रूट माहिती)
        ("07:20", "17:35", "साधी (लालपरी)", 750, VIA_RATNAGIRI),
        ("08:40", "19:00", "साधी (लालपरी)", 760, VIA_RATNAGIRI),
        ("12:55", "23:30", "साधी (लालपरी)", 840, VIA_RATNAGIRI),
        ("19:30", "06:00", "साधी (लालपरी)", 840, VIA_RATNAGIRI),
        ("20:00", "06:30", "साधी (लालपरी)", 760, VIA_RATNAGIRI)
    ]

    for dep, arr, b_type, fare, via in ratnagiri_schedules:
        exists = BusSchedule.query.filter_by(source="सोलापूर", destination="रत्नागिरी", departure_time=dep).first()
        if not exists:
            db.session.add(BusSchedule(
                source="सोलापूर", source_en="Solapur",
                destination="रत्नागिरी", destination_en="Ratnagiri",
                bus_type=b_type, departure_time=dep, arrival_time=arr,
                via_route=via, fare=fare
            ))
        else:
            exists.via_route = VIA_RATNAGIRI
            exists.fare = fare
            exists.arrival_time = arr

    # २. सोलापूर ➔ पुणे (स्वारगेट) वेळापत्रक
    pune_master_schedules = [
        ("00:15", "05:29", "साधी (लालपरी)", 485, VIA_PUNE),
        ("05:00", "10:00", "इ-शिवाई (Electric Shivai)", 680, VIA_PUNE),
        ("05:47", "11:30", "साधी (लालपरी)", 485, VIA_PUNE),
        ("06:00", "11:00", "इ-शिवाई (Electric Shivai)", 680, VIA_PUNE),
        ("06:25", "12:56", "साधी (लालपरी)", 475, VIA_PUNE),
        ("06:56", "13:32", "साधी (लालपरी)", 485, VIA_PUNE),
        ("07:00", "12:00", "इ-शिवाई (Electric Shivai)", 680, VIA_PUNE),
        ("07:00", "13:47", "साधी (लालपरी)", 485, VIA_PUNE),
        ("07:15", "12:29", "साधी (लालपरी)", 485, VIA_PUNE),
        ("08:00", "13:00", "साधी (लालपरी)", 485, VIA_PUNE),
        ("08:00", "13:30", "साधी (लालपरी)", 485, VIA_PUNE),
        ("08:15", "14:15", "साधी (लालपरी)", 485, VIA_PUNE),
        ("08:15", "13:30", "साधी (लालपरी)", 485, VIA_PUNE),
        ("08:33", "14:44", "साधी (लालपरी)", 485, VIA_PUNE),
        ("08:43", "14:15", "साधी (लालपरी)", 485, VIA_PUNE),
        ("08:43", "16:20", "साधी (लालपरी)", 485, VIA_PUNE),
        ("09:00", "14:00", "इ-शिवाई (Electric Shivai)", 680, VIA_PUNE),
        ("09:04", "15:39", "साधी (लालपरी)", 485, VIA_PUNE),
        ("09:05", "15:02", "साधी (लालपरी)", 485, VIA_PUNE),
        ("09:32", "16:02", "साधी (लालपरी)", 485, VIA_PUNE),
        ("09:40", "15:55", "साधी (लालपरी)", 485, VIA_PUNE),
        ("09:47", "16:07", "साधी (लालपरी)", 485, VIA_PUNE),
        ("09:56", "15:01", "साधी (लालपरी)", 485, VIA_PUNE),
        ("10:00", "15:00", "इ-शिवाई (Electric Shivai)", 680, VIA_PUNE),
        ("10:00", "15:49", "साधी (लालपरी)", 485, VIA_PUNE),
        ("10:04", "16:16", "साधी (लालपरी)", 485, VIA_PUNE),
        ("14:45", "20:05", "साधी (लालपरी)", 485, VIA_PUNE),
        ("14:45", "20:15", "साधी (लालपरी)", 485, VIA_PUNE),
        ("14:53", "21:33", "साधी (लालपरी)", 485, VIA_PUNE),
        ("15:00", "20:29", "साधी (लालपरी)", 485, VIA_PUNE),
        ("15:15", "20:29", "साधी (लालपरी)", 485, VIA_PUNE),
        ("15:15", "20:41", "साधी (लालपरी)", 485, VIA_PUNE),
        ("15:45", "21:15", "साधी (लालपरी)", 485, VIA_PUNE),
        ("16:00", "21:00", "इ-शिवाई (Electric Shivai)", 680, VIA_PUNE),
        ("16:02", "21:35", "साधी (लालपरी)", 485, VIA_PUNE),
        ("16:15", "21:45", "साधी (लालपरी)", 485, VIA_PUNE),
        ("16:37", "21:56", "साधी (लालपरी)", 485, VIA_PUNE),
        ("16:42", "22:49", "साधी (लालपरी)", 485, VIA_PUNE),
        ("16:45", "22:15", "साधी (लालपरी)", 485, VIA_PUNE),
        ("17:00", "22:00", "इ-शिवाई (Electric Shivai)", 680, VIA_PUNE),
        ("17:15", "22:29", "साधी (लालपरी)", 485, VIA_PUNE),
        ("17:30", "23:00", "साधी (लालपरी)", 485, VIA_PUNE),
        ("17:52", "23:58", "साधी (लालपरी)", 485, VIA_PUNE),
        ("18:15", "23:45", "साधी (लालपरी)", 485, VIA_PUNE),
        ("20:00", "01:00", "इ-शिवाई (Electric Shivai)", 680, VIA_PUNE),
        ("20:34", "02:34", "साधी (लालपरी)", 485, VIA_PUNE),
        ("21:00", "02:00", "इ-शिवाई (Electric Shivai)", 680, VIA_PUNE),
        ("21:10", "03:14", "साधी (लालपरी)", 485, VIA_PUNE),
        ("22:00", "03:29", "साधी (लालपरी)", 485, VIA_PUNE),
        ("22:19", "04:31", "साधी (लालपरी)", 485, VIA_PUNE),
        ("22:34", "05:09", "निमआराम (एशियाड)", 580, VIA_PUNE),
        ("23:00", "03:59", "इ-शिवाई (Electric Shivai)", 680, VIA_PUNE)
    ]

    for dep, arr, b_type, fare, via in pune_master_schedules:
        exists = BusSchedule.query.filter_by(source="सोलापूर", destination="पुणे (स्वारगेट)", departure_time=dep, bus_type=b_type).first()
        if not exists:
            db.session.add(BusSchedule(
                source="सोलापूर", source_en="Solapur",
                destination="पुणे (स्वारगेट)", destination_en="Pune",
                bus_type=b_type, departure_time=dep, arrival_time=arr,
                via_route=via, fare=fare
            ))
        else:
            exists.via_route = VIA_PUNE
            exists.fare = fare
            exists.arrival_time = arr

    db.session.commit()

if __name__ == '__main__':
    app.run(debug=True, port=5000)