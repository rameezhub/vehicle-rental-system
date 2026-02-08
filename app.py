from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
import config

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

def get_db_connection():
    return mysql.connector.connect(
        host=config.DB_HOST,
        user=config.DB_USER,
        password=config.DB_PASS,
        database=config.DB_NAME
    )

import traceback   # put at top of app.py if not already imported

@app.route('/my_reservations')
def my_reservations():
    # 1) require login
    if 'user_id' not in session:
        flash('Please login to view your reservations', 'warning')
        return redirect(url_for('login'))

    uid = session['user_id']
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    sql = """
        SELECT r.reservation_id, r.start_date, r.end_date, r.status, r.total_amount, r.payment_status,
               v.vehicle_id, v.model, v.vehicle_type, v.registration_no, v.rent_rate
        FROM Reservations r
        JOIN Vehicle v ON r.vehicle_id = v.vehicle_id
        WHERE r.user_id = %s
        ORDER BY r.created_at DESC
    """

    try:
        print("MY_RESERVATIONS SQL:", sql, "PARAMS:", (uid,))
        cur.execute(sql, (uid,))
        reservations = cur.fetchall()
        # safety: make sure reservations is a list
        if reservations is None:
            reservations = []
    except Exception as e:
        traceback.print_exc()
        flash('Could not load reservations — check server console for details', 'danger')
        reservations = []
    finally:
        cur.close()
        conn.close()

    return render_template('my_reservations.html', reservations=reservations)


@app.route('/')
def index():
    q = request.args.get('query','').strip()
    category = request.args.get('category','').strip()
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    sql = "SELECT * FROM Vehicle WHERE 1=1"
    params = []
    if q:
        sql += " AND (vehicle_type LIKE %s OR model LIKE %s OR location LIKE %s)"
        qpar = '%' + q + '%'
        params += [qpar, qpar, qpar]
    if category:
        sql += " AND vehicle_type = %s"
        params.append(category)
    cur.execute(sql, params)
    vehicles = cur.fetchall()
    cur.close(); conn.close()
    return render_template('index.html', vehicles=vehicles)

@app.route('/vehicle/<int:vid>')
def vehicle_detail(vid):
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM Vehicle WHERE vehicle_id=%s", (vid,))
    v = cur.fetchone()
    cur.close(); conn.close()
    if not v:
        return "Not found", 404
    return render_template('vehicle_modal.html', v=v)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','')
        full = request.form.get('full_name','').strip()
        email = request.form.get('email','').strip()
        phone = request.form.get('phone','').strip()
        if not username or not password:
            flash('Username and password required','danger'); return render_template('register.html')
        hashed = generate_password_hash(password)
        conn = get_db_connection(); cur = conn.cursor()
        try:
            cur.execute("INSERT INTO Users (username, password, full_name, email, phone) VALUES (%s,%s,%s,%s,%s)",
                        (username, hashed, full, email, phone))
            conn.commit()
            flash('Account created — please login','success')
            return redirect(url_for('login'))
        except mysql.connector.IntegrityError:
            flash('Username already exists','danger')
        except Exception as e:
            print("REGISTER ERROR:", e); flash('Registration failed (check console)','danger')
        finally:
            cur.close(); conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()

        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM Users WHERE username=%s AND password=%s", (username, password))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user:
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash(f"Welcome {user['username']}!", "success")
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials. Please try again.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out','info')
    return redirect(url_for('index'))

@app.route('/reserve/<int:vid>', methods=['GET','POST'])
def reserve(vid):
    if 'user_id' not in session:
        flash('Please login to reserve','warning'); return redirect(url_for('login'))
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM Vehicle WHERE vehicle_id=%s", (vid,))
    vehicle = cur.fetchone()
    if not vehicle:
        cur.close(); conn.close(); flash('Vehicle not found','danger'); return redirect(url_for('index'))
    if request.method=='POST':
        start = request.form.get('start_date'); end = request.form.get('end_date')
        try:
            cur.execute("INSERT INTO Reservations (user_id, vehicle_id, start_date, end_date) VALUES (%s,%s,%s,%s)",
                        (session['user_id'], vid, start, end))
            cur.execute("UPDATE Vehicle SET status='reserved' WHERE vehicle_id=%s", (vid,))
            conn.commit()
            flash('Reservation created','success')
            return redirect(url_for('index'))
        except Exception as e:
            print("RESERVE ERROR:", e); flash('Reservation failed','danger')
    cur.close(); conn.close()
    return render_template('reserve.html', vehicle=vehicle)

# Admin add/manage vehicles (simple)
def admin_required():
    return session.get('role') == 'admin'


@app.route('/add_vehicle', methods=['GET','POST'])
def add_vehicle():
    if session.get('role') != 'admin':
        flash('Admin only','danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        data = (
            request.form['vehicle_type'],
            request.form['model'],
            request.form['rent_rate'],
            request.form['registration_no'],
            request.form.get('fuel_type','Petrol'),
            request.form.get('location','Main Branch'),
            request.form.get('image','car.jpg')
        )
        conn = get_db_connection(); cur = conn.cursor()
        try:
            cur.execute("""INSERT INTO Vehicle
              (vehicle_type,model,rent_rate,registration_no,fuel_type,location,image)
              VALUES (%s,%s,%s,%s,%s,%s,%s)""", data)
            conn.commit()
            flash('Vehicle added','success')
            return redirect(url_for('index'))
        except Exception as e:
             import traceback; traceback.print_exc()
             flash('Error adding vehicle.', 'danger')

        finally:
            cur.close(); conn.close()

    return render_template('add_vehicle.html')

@app.route('/pay/<int:rid>', methods=['GET','POST'])
def pay(rid):
    if 'user_id' not in session:
        flash('Login first','warning')
        return redirect(url_for('login'))

    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT r.*, v.model, v.rent_rate
        FROM Reservations r JOIN Vehicle v ON r.vehicle_id=v.vehicle_id
        WHERE r.reservation_id=%s AND r.user_id=%s
    """, (rid, session['user_id']))
    res = cur.fetchone()
    if not res:
        cur.close(); conn.close()
        flash('Reservation not found','danger')
        return redirect(url_for('my_reservations'))

    if request.method == 'POST':
        amount = request.form.get('amount', res['rent_rate'])
        mode = request.form.get('mode','Cash')
        try:
            cur.execute("""INSERT INTO Payments (reservation_id, amount, mode, status)
                           VALUES (%s,%s,%s,'success')""", (rid, amount, mode))
            cur.execute("""UPDATE Reservations SET payment_status='paid', total_amount=%s WHERE reservation_id=%s""",
                        (amount, rid))
            conn.commit()
            flash('Payment successful','success')
            return redirect(url_for('my_reservations'))
        except Exception as e:
            import traceback; traceback.print_exc()
            flash('Payment failed — check console for details', 'danger')

    cur.close(); conn.close()
    return render_template('pay.html', r=res)

@app.route('/payment_success/<int:rid>')
def payment_success(rid):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT r.*, v.model, v.vehicle_type, p.amount, p.mode, p.status, p.payment_date
        FROM Reservations r
        JOIN Vehicle v ON r.vehicle_id=v.vehicle_id
        JOIN Payments p ON r.reservation_id=p.reservation_id
        WHERE r.reservation_id=%s
        ORDER BY p.payment_date DESC LIMIT 1
    """, (rid,))
    payment = cur.fetchone()
    cur.close(); conn.close()
    return render_template('payment_success.html', p=payment)


@app.route('/admin/add_vehicle', methods=['GET','POST'])
def admin_add_vehicle():
    if not admin_required():
        flash('Admin required','danger'); return redirect(url_for('login'))
    if request.method=='POST':
        data = (
            request.form.get('vehicle_type',''),
            request.form.get('model',''),
            request.form.get('rent_rate',0),
            request.form.get('registration_no',''),
            request.form.get('fuel_type','Petrol'),
            request.form.get('location','Main Branch'),
            request.form.get('image','car.jpg')
        )
        conn = get_db_connection(); cur = conn.cursor()
        try:
            cur.execute("""INSERT INTO Vehicle (vehicle_type, model, rent_rate, registration_no, fuel_type, location, image)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)""", data)
            conn.commit(); flash('Vehicle added','success'); return redirect(url_for('index'))
        except Exception as e:
            print("ADD VEHICLE ERROR:", e); flash('Failed to add vehicle','danger')
        finally:
            cur.close(); conn.close()
    return render_template('add_vehicle.html')

@app.route('/admin/manage_vehicles')
def admin_manage_vehicles():
    if not admin_required():
        flash('Admin required','danger'); return redirect(url_for('login'))
    conn = get_db_connection(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM Vehicle"); vehicles = cur.fetchall()
    cur.close(); conn.close()
    return render_template('manage_vehicles.html', vehicles=vehicles)

if __name__ == '__main__':
    app.run(debug=True)
