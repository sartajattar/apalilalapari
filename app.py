import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'lalpari-super-secret-key-1948')

db_url = os.environ.get('DATABASE_URL', 'sqlite:///lalpari.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

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
    via_route = db.Column(db.String(200), default="थेट")
    fare = db.Column(db.Integer, default=200)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def calculate_next_bus_meta(dep_time_str):
    now = datetime.now()
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
        
    current_time_str = datetime.now().strftime("%I:%M %p")
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
    
    # ॲडमिन क्रेडेंशियल्स: apalilalpari / Attar@123
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
    else:
        admin.password = generate_password_hash("Attar@123", method='scrypt')
        db.session.commit()

    # चिठ्ठीतील अचूक गाड्या (डेटाबेस रिकामी असल्यास)
    if BusSchedule.query.count() == 0:
        solapur_kolhapur_times = [
            ("04:45", "10:20"),
            ("10:00", "15:58"),
            ("11:00", "16:58"),
            ("12:30", "18:28"),
            ("13:30", "19:28"),
            ("16:00", "21:58"),
            ("22:00", "04:14")
        ]
        
        for dep, arr in solapur_kolhapur_times:
            # सोलापूर ➔ कोल्हापूर (फक्त याचे तिकीट ₹५००)
            b1 = BusSchedule(
                source="सोलापूर",
                source_en="Solapur",
                destination="कोल्हापूर",
                destination_en="Kolhapur",
                bus_type="साधी (लालपरी)",
                departure_time=dep,
                arrival_time=arr,
                via_route="मोहोळ, पंढरपूर, सांगोला, मिरज, सांगली",
                fare=500
            )
            # मोहोळ ➔ कोल्हापूर (डिफॉल्ट ₹२००, ॲडमिनमधून हवे तेव्हा बदलू शकता)
            b2 = BusSchedule(
                source="मोहोळ",
                source_en="Mohol",
                destination="कोल्हापूर",
                destination_en="Kolhapur",
                bus_type="साधी (लालपरी)",
                departure_time=dep,
                arrival_time=arr,
                via_route="पंढरपूर, सांगोला, मिरज, सांगली",
                fare=200
            )
            db.session.add(b1)
            db.session.add(b2)
        db.session.commit()
    else:
        # आधीपासून असलेल्या डेटाबेसमध्ये फक्त सोलापूर ते कोल्हापूर ₹५०० अपडेट करणे
        solapur_kolhapur_routes = BusSchedule.query.filter(
            or_(BusSchedule.source.ilike("%सोलापूर%"), BusSchedule.source_en.ilike("%Solapur%")),
            or_(BusSchedule.destination.ilike("%कोल्हापूर%"), BusSchedule.destination_en.ilike("%Kolhapur%"))
        ).all()
        for b in solapur_kolhapur_routes:
            b.fare = 500
        db.session.commit()

if __name__ == '__main__':
    app.run(debug=True, port=5000)