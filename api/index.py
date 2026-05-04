import os
from flask import Flask, render_template, request, jsonify, session, redirect
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import math

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.config['SECRET_KEY'] = 'hospital_teal_secure_key_2024'
# Replace with your actual database URL in Vercel Environment Variables
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "postgresql://postgres:password@localhost:5432/postgres")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Database Models ---
class Hospital(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20))
    address = db.Column(db.String(255))
    lat = db.Column(db.Float)
    lon = db.Column(db.Float)

class Inventory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospital.id'))
    blood_type = db.Column(db.String(5))
    quantity = db.Column(db.Integer)
    expiry_date = db.Column(db.Date)

class Request(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey('hospital.id'))
    supplier_id = db.Column(db.Integer, db.ForeignKey('hospital.id'))
    blood_type = db.Column(db.String(5))
    status = db.Column(db.String(20), default='Pending') # Pending, Accepted, Rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# --- Helper Logic ---
def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1-a)))

# --- API Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    if Hospital.query.filter_by(email=data['email']).first():
        return jsonify({"error": "Email already exists"}), 400
    
    new_hosp = Hospital(
        name=data['name'], email=data['email'], 
        password=generate_password_hash(data['password']),
        phone=data['phone'], address=data['address'],
        lat=data.get('lat', 0), lon=data.get('lon', 0)
    )
    db.session.add(new_hosp)
    db.session.commit()
    return jsonify({"success": True})

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    hosp = Hospital.query.filter_by(email=data['email']).first()
    if hosp and check_password_hash(hosp.password, data['password']):
        session['user_id'] = hosp.id
        return jsonify({"success": True, "user": {"name": hosp.name}})
    return jsonify({"error": "Invalid credentials"}), 401

@app.route('/api/inventory', methods=['GET', 'POST'])
def handle_inventory():
    user_id = session.get('user_id')
    if not user_id: return jsonify({"error": "Unauthorized"}), 401

    if request.method == 'POST':
        data = request.json
        item = Inventory(
            hospital_id=user_id, blood_type=data['blood_type'],
            quantity=data['quantity'], 
            expiry_date=datetime.strptime(data['expiry_date'], '%Y-%m-%d').date()
        )
        db.session.add(item)
        db.session.commit()
        return jsonify({"success": True})

    items = Inventory.query.filter_by(hospital_id=user_id).all()
    res = []
    for i in items:
        days_left = (i.expiry_date - datetime.now().date()).days
        res.append({
            "id": i.id, "type": i.blood_type, "qty": i.quantity, 
            "expiry": str(i.expiry_date), "urgent": days_left <= 5
        })
    return jsonify(res)

@app.route('/api/search', methods=['GET'])
def search():
    user_id = session.get('user_id')
    if not user_id: return jsonify([]), 401
    me = Hospital.query.get(user_id)
    b_type = request.args.get('type')
    
    results = db.session.query(Inventory, Hospital).join(Hospital).filter(
        Inventory.blood_type == b_type, Inventory.hospital_id != user_id
    ).all()
    
    output = []
    for inv, hosp in results:
        dist = haversine(me.lat, me.lon, hosp.lat, hosp.lon)
        output.append({
            "hosp_id": hosp.id, "hosp_name": hosp.name, "qty": inv.quantity,
            "dist": round(dist, 1), "expiry": str(inv.expiry_date)
        })
    return jsonify(sorted(output, key=lambda x: x['dist']))

@app.route('/api/requests', methods=['GET', 'POST'])
def manage_requests():
    user_id = session.get('user_id')
    if request.method == 'POST':
        data = request.json
        req = Request(requester_id=user_id, supplier_id=data['hosp_id'], blood_type=data['type'])
        db.session.add(req)
        db.session.commit()
        return jsonify({"success": True})
    
    incoming = Request.query.filter_by(supplier_id=user_id).all()
    return jsonify([{"id": r.id, "type": r.blood_type, "status": r.status} for r in incoming])

# Create tables within app context for serverless start
with app.app_context():
    db.create_all()

app_handle = app
