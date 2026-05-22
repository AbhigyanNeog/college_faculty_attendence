import os
import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from config import Config
from models import db, Role, Department, User, TeacherProfile, Timetable, GPSRecord, ImageRecord, AttendanceLog, CampusSetting
from database import init_db
import utils

app = Flask(__name__)
app.config.from_object(Config)

# Initialize Database
init_db(app)

# Ensure upload directory exists
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'classroom_photos'), exist_ok=True)

# ----------------- SESSION AUTH DECORATOR / HELPERS -----------------
def is_logged_in():
    return 'user_id' in session

def get_current_user():
    if not is_logged_in():
        return None
    return User.query.get(session['user_id'])

# ----------------- CONTROLLER ROUTES -----------------

@app.route('/')
def index():
    if is_logged_in():
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('teacher_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if is_logged_in():
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        # Match by username OR email
        user = User.query.filter(
            (db.func.lower(User.username) == db.func.lower(username)) | 
            (db.func.lower(User.email) == db.func.lower(username))
        ).first()
        
        if user:
            # Check if account requires first-time password setup
            if user.needs_password_setup:
                session['setup_password_user_id'] = user.id
                flash("First-time login detected. Please establish your credentials.", "warning")
                return redirect(url_for('setup_password'))
                
            if user.check_password(password):
                # Check teacher approval status first
                if user.role.name == 'teacher' and user.profile:
                    status = user.profile.approval_status
                    if status == 'Pending':
                        flash("Your account registration is Pending Admin approval.", "warning")
                        return render_template('login.html')
                    elif status == 'Rejected':
                        flash("Your registration request was Rejected. Contact Admin.", "danger")
                        return render_template('login.html')
                
                # Check if account has been deactivated
                if not user.is_active:
                    flash("This account has been deactivated. Contact Admin.", "danger")
                    return render_template('login.html')
                
                session['user_id'] = user.id
                session['username'] = user.username
                session['role'] = user.role.name
                if user.role.name == 'admin':
                    session['name'] = 'System Admin'
                else:
                    session['name'] = user.profile.name if user.profile else 'Faculty Member'
                
                flash(f"Welcome back, {session['name']}!", "success")
                return redirect(url_for('index'))
            else:
                flash("Invalid username or password.", "danger")
        else:
            flash("Invalid username or password.", "danger")
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if is_logged_in():
        return redirect(url_for('index'))
        
    departments = Department.query.order_by(Department.name).all()
    
    if request.method == 'POST':
        employee_id = request.form.get('employee_id', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        department_id = request.form.get('department_id')
        username = request.form.get('username', '').strip()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validation checks
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template('register.html', departments=departments)
            
        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "danger")
            return render_template('register.html', departments=departments)
            
        # Check uniqueness in DB
        existing_user = User.query.filter(
            (db.func.lower(User.username) == db.func.lower(username)) |
            (db.func.lower(User.email) == db.func.lower(email))
        ).first()
        if existing_user:
            flash("Username or Email already registered.", "danger")
            return render_template('register.html', departments=departments)
            
        existing_profile = TeacherProfile.query.filter_by(employee_id=employee_id).first()
        if existing_profile:
            flash("Employee ID already registered.", "danger")
            return render_template('register.html', departments=departments)
            
        # Create User & TeacherProfile
        teacher_role = Role.query.filter_by(name='teacher').first()
        new_user = User(
            username=username,
            email=email,
            role_id=teacher_role.id,
            is_active=False, # Wait until approved
            needs_password_setup=False
        )
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        
        new_profile = TeacherProfile(
            user_id=new_user.id,
            employee_id=employee_id,
            name=name,
            phone=phone,
            department_id=int(department_id) if department_id else None,
            approval_status='Pending'
        )
        db.session.add(new_profile)
        db.session.commit()
        
        flash("Registration submitted successfully! Your profile is pending Admin approval.", "success")
        return redirect(url_for('login'))
        
    return render_template('register.html', departments=departments)

@app.route('/setup_password', methods=['GET', 'POST'])
def setup_password():
    user_id = session.get('setup_password_user_id')
    if not user_id:
        flash("Unauthorized password setup attempt.", "danger")
        return redirect(url_for('login'))
        
    user = User.query.get(user_id)
    if not user or not user.needs_password_setup:
        session.pop('setup_password_user_id', None)
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        employee_id = request.form.get('employee_id', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Verify identity matches seeded user email and teacher profile's employee ID
        profile = TeacherProfile.query.filter_by(user_id=user.id).first()
        
        if not profile or user.email.strip().lower() != email.lower() or profile.employee_id.strip().lower() != employee_id.lower():
            flash("Verification failed: Employee ID and Email do not match our records.", "danger")
            return render_template('setup_password.html', user_id=user_id, prefilled_email=user.email)
            
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template('setup_password.html', user_id=user_id, prefilled_email=user.email)
            
        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "danger")
            return render_template('setup_password.html', user_id=user_id, prefilled_email=user.email)
            
        # Complete setup
        user.set_password(password)
        user.needs_password_setup = False
        user.is_active = True # Now fully activated
        
        # Mark profile as Approved since admin set it up
        if profile:
            profile.approval_status = 'Approved'
            
        db.session.commit()
        session.pop('setup_password_user_id', None)
        
        flash("Password established successfully! You can now log in.", "success")
        return redirect(url_for('login'))
        
    return render_template('setup_password.html', user_id=user_id, prefilled_email=user.email)

@app.route('/logout')
def logout():
    session.clear()
    flash("You have successfully signed out.", "success")
    return redirect(url_for('login'))

# ----------------- TEACHER PORTAL -----------------

@app.route('/teacher/dashboard')
def teacher_dashboard():
    if not is_logged_in() or session.get('role') != 'teacher':
        flash("Access Denied.", "danger")
        return redirect(url_for('login'))
        
    user = get_current_user()
    if not user or not user.profile:
        flash("Teacher profile not found.", "danger")
        return redirect(url_for('login'))
        
    teacher = user.profile
    now = datetime.datetime.now()
    current_day = now.weekday() # 0 = Monday, ..., 6 = Sunday
    
    # Fetch campus settings to get allowed window size
    settings = CampusSetting.query.first()
    start_before = settings.start_window_before_mins if settings else 5
    end_after = settings.end_window_after_mins if settings else 15
    
    # Query timetables for this teacher for today
    timetables = Timetable.query.filter_by(teacher_profile_id=teacher.id, day_of_week=current_day).order_by(Timetable.start_time).all()
    
    schedules = []
    active_class_to_mark = None
    window_start_str = ""
    window_end_str = ""
    
    selected_mark_id = request.args.get('mark_id')
    
    for tt in timetables:
        # Check if already marked for today
        log = AttendanceLog.query.filter(
            AttendanceLog.timetable_id == tt.id,
            db.func.date(AttendanceLog.timestamp) == now.date()
        ).first()
        
        state = 'upcoming'
        marked_time = ""
        
        # Calculate allowed timing window
        dt_start = datetime.datetime.combine(now.date(), tt.start_time)
        dt_end = datetime.datetime.combine(now.date(), tt.end_time)
        allowed_start = dt_start - datetime.timedelta(minutes=start_before)
        allowed_end = dt_start + datetime.timedelta(minutes=end_after)
        
        if log:
            state = 'marked'
            marked_time = log.timestamp.strftime('%I:%M %p')
        elif allowed_start <= now <= allowed_end:
            state = 'active'
            if selected_mark_id and str(tt.id) == selected_mark_id:
                active_class_to_mark = tt
                window_start_str = allowed_start.strftime('%I:%M %p')
                window_end_str = allowed_end.strftime('%I:%M %p')
        elif now > allowed_end:
            state = 'missed'
        else:
            state = 'upcoming'
            
        schedules.append({
            'id': tt.id,
            'subject': tt.subject,
            'classroom': tt.classroom,
            'start_time': tt.start_time,
            'end_time': tt.end_time,
            'state': state,
            'marked_time': marked_time,
            'window_start': allowed_start.strftime('%I:%M %p')
        })
        
    # Auto-select the first active class if none is selected
    if not active_class_to_mark:
        for item, tt in zip(schedules, timetables):
            if item['state'] == 'active':
                active_class_to_mark = tt
                # Recalculate window times
                dt_start = datetime.datetime.combine(now.date(), tt.start_time)
                allowed_start = dt_start - datetime.timedelta(minutes=start_before)
                allowed_end = dt_start + datetime.timedelta(minutes=end_after)
                window_start_str = allowed_start.strftime('%I:%M %p')
                window_end_str = allowed_end.strftime('%I:%M %p')
                break

    return render_template('teacher_dashboard.html', 
                           schedules=schedules,
                           active_class_to_mark=active_class_to_mark,
                           window_start_str=window_start_str,
                           window_end_str=window_end_str,
                           current_date=now.strftime('%A, %B %d, %Y'),
                           debug_mock_gps=app.config['DEBUG_MOCK_LOCATION'])

# ----------------- BACKEND VERIFICATION API -----------------

@app.route('/api/submit_attendance', methods=['POST'])
def submit_attendance():
    if not is_logged_in() or session.get('role') != 'teacher':
        return jsonify({'message': 'Access Denied: Authentication required.'}), 401
        
    user = get_current_user()
    if not user or not user.profile:
        return jsonify({'message': 'Access Denied: Faculty profile required.'}), 401
        
    teacher = user.profile
    data = request.get_json()
    
    if not data or 'image' not in data or 'latitude' not in data or 'longitude' not in data or 'timetable_id' not in data:
        return jsonify({'message': 'Bad Request: Missing required parameters.'}), 400
        
    image_base64 = data['image']
    lat = float(data['latitude'])
    lon = float(data['longitude'])
    timetable_id = int(data['timetable_id'])
    
    now = datetime.datetime.now()
    
    # 1. Fetch Timetable slot
    tt = Timetable.query.get(timetable_id)
    if not tt or tt.teacher_profile_id != teacher.id:
        return jsonify({'message': 'Timetable record not found or unauthorized.'}), 404
        
    # 2. Check if already marked for today
    existing_log = AttendanceLog.query.filter(
        AttendanceLog.timetable_id == tt.id,
        db.func.date(AttendanceLog.timestamp) == now.date()
    ).first()
    if existing_log:
        return jsonify({'message': 'Attendance already marked for this class today.'}), 400
        
    # 3. Validate Time Window
    settings = CampusSetting.query.first()
    start_before = settings.start_window_before_mins if settings else 5
    end_after = settings.end_window_after_mins if settings else 15
    
    dt_start = datetime.datetime.combine(now.date(), tt.start_time)
    allowed_start = dt_start - datetime.timedelta(minutes=start_before)
    allowed_end = dt_start + datetime.timedelta(minutes=end_after)
    
    if not (allowed_start <= now <= allowed_end):
        return jsonify({
            'message': 'Attendance submission blocked.',
            'reason': 'Outside allowed timing window.'
        }), 400
        
    # 4. GPS Verification
    campus_lat = settings.latitude if settings else app.config['CAMPUS_LATITUDE']
    campus_lon = settings.longitude if settings else app.config['CAMPUS_LONGITUDE']
    allowed_radius = settings.radius_meters if settings else app.config['CAMPUS_RADIUS_METERS']
    
    distance = utils.calculate_distance(lat, lon, campus_lat, campus_lon)
    
    if distance > allowed_radius:
        return jsonify({
            'message': 'Attendance rejected.',
            'reason': f'Located outside allowed campus boundary. Distance: {round(distance, 1)} meters.'
        }), 400

    # 5. Save and Compress Captured Photo
    timestamp_slug = now.strftime('%Y%m%d_%H%M%S')
    filename = f"teacher_{teacher.id}_slot_{tt.id}_{timestamp_slug}.jpg"
    image_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'classroom_photos')
    
    try:
        saved_path = utils.save_compressed_image(image_base64, image_dir, filename)
        # Relative path for storage
        relative_path = os.path.join('static', 'uploads', 'classroom_photos', filename).replace('\\', '/')
    except Exception as e:
        print(f"Image Save Error: {e}")
        return jsonify({'message': 'Error saving classroom photo on server.'}), 500
        
    # 6. Prevent Reused/Old Images (dHash Analysis)
    img_hash = utils.calculate_dhash(saved_path)
    
    # Query all old image records to look for matches
    is_duplicate = False
    duplicate_log_id = None
    
    old_images = ImageRecord.query.all()
    for old_img in old_images:
        # Avoid matching with the current file itself in case of DB conflicts
        if old_img.image_path == relative_path:
            continue
        dist = utils.hamming_distance(img_hash, old_img.image_hash)
        if dist <= 2:
            is_duplicate = True
            # Find the attendance log associated with this image record
            matching_log = AttendanceLog.query.filter_by(image_record_id=old_img.id).first()
            if matching_log:
                duplicate_log_id = matching_log.id
            break
    
    status = 'Approved'
    suspicious_reason = None
    
    if is_duplicate:
        status = 'Suspicious'
        suspicious_reason = 'Duplicate Image'
        
    # 7. AI Count Verification
    student_count = utils.estimate_human_count(saved_path)
    
    # If extremely low student count (< 3) in a class, mark suspicious
    if student_count < 3 and not is_duplicate:
        status = 'Suspicious'
        suspicious_reason = 'Low Student Count'
        
    # 8. Create GPS and Image Records (Normalized Tables)
    gps_rec = GPSRecord(
        latitude=lat,
        longitude=lon,
        distance_meters=distance,
        is_within_boundary=(distance <= allowed_radius)
    )
    db.session.add(gps_rec)
    db.session.flush()
    
    img_rec = ImageRecord(
        image_path=relative_path,
        image_hash=img_hash,
        student_count=student_count
    )
    db.session.add(img_rec)
    db.session.flush()
    
    # Insert Database Attendance Log
    log = AttendanceLog(
        teacher_profile_id=teacher.id,
        timetable_id=tt.id,
        timestamp=now,
        gps_record_id=gps_rec.id,
        image_record_id=img_rec.id,
        status=status,
        suspicious_reason=suspicious_reason
    )
    
    db.session.add(log)
    db.session.commit()
    
    if status == 'Suspicious':
        return jsonify({
            'message': 'Attendance received, but marked SUSPICIOUS. Administrative review is required.',
            'reason': suspicious_reason
        }), 200
        
    return jsonify({
        'message': 'Class presence verified successfully! Attendance marked.'
    }), 200

# ----------------- ADMIN PORTAL -----------------

@app.route('/admin/dashboard')
def admin_dashboard():
    if not is_logged_in() or session.get('role') != 'admin':
        flash("Access Denied.", "danger")
        return redirect(url_for('login'))
        
    now = datetime.datetime.now()
    today_start = datetime.datetime.combine(now.date(), datetime.time.min)
    today_end = datetime.datetime.combine(now.date(), datetime.time.max)
    
    # Metrics computations for Today
    scheduled_count = Timetable.query.filter_by(day_of_week=now.weekday()).count()
    completed_logs = AttendanceLog.query.filter(AttendanceLog.timestamp.between(today_start, today_end)).all()
    completed_count = len(completed_logs)
    
    compliance_rate = 0
    if scheduled_count > 0:
        compliance_rate = round((completed_count / scheduled_count) * 100)
        
    suspicious_count = AttendanceLog.query.filter(
        AttendanceLog.timestamp.between(today_start, today_end),
        AttendanceLog.status == 'Suspicious'
    ).count()
    
    # Registrations pending approval
    pending_count = TeacherProfile.query.filter_by(approval_status='Pending').count()
    
    stats = {
        'scheduled': scheduled_count,
        'completed': completed_count,
        'compliance_rate': min(compliance_rate, 100),
        'suspicious': suspicious_count,
        'pending_registrations': pending_count
    }
    
    # Recent log entries
    recent_logs = []
    for log in completed_logs[-5:]:  # Last 5 submissions
        recent_logs.append(log.to_dict())
    recent_logs.reverse()
    
    # Flagged entries for warning list
    suspicious_logs = []
    suspicious_entries = AttendanceLog.query.filter(
        AttendanceLog.timestamp.between(today_start, today_end),
        AttendanceLog.status == 'Suspicious'
    ).all()
    for log in suspicious_entries:
        suspicious_logs.append(log.to_dict())
        
    return render_template('admin_dashboard.html', 
                           stats=stats,
                           recent_logs=recent_logs,
                           suspicious_logs=suspicious_logs)

@app.route('/admin/teachers', methods=['GET', 'POST'])
def admin_teachers():
    if not is_logged_in() or session.get('role') != 'admin':
        flash("Access Denied.", "danger")
        return redirect(url_for('login'))
        
    departments = Department.query.order_by(Department.name).all()
    teacher_role = Role.query.filter_by(name='teacher').first()
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            name = request.form.get('name', '').strip()
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            phone = request.form.get('phone', '').strip()
            employee_id = request.form.get('employee_id', '').strip()
            department_id = request.form.get('department_id')
            password = request.form.get('password')
            
            # Checks
            existing_user = User.query.filter(
                (db.func.lower(User.username) == db.func.lower(username)) |
                (db.func.lower(User.email) == db.func.lower(email))
            ).first()
            if existing_user:
                flash("Username or Email already registered.", "danger")
            else:
                existing_profile = TeacherProfile.query.filter_by(employee_id=employee_id).first()
                if existing_profile:
                    flash("Employee ID already exists.", "danger")
                else:
                    # Create user
                    needs_pw = not bool(password)
                    new_user = User(
                        username=username,
                        email=email,
                        role_id=teacher_role.id,
                        is_active=not needs_pw, # If no password, inactive until setup
                        needs_password_setup=needs_pw
                    )
                    if password:
                        new_user.set_password(password)
                    db.session.add(new_user)
                    db.session.commit()
                    
                    # Create profile
                    new_profile = TeacherProfile(
                        user_id=new_user.id,
                        employee_id=employee_id,
                        name=name,
                        phone=phone,
                        department_id=int(department_id) if department_id else None,
                        approval_status='Approved' # Admin added profiles are auto-approved
                    )
                    db.session.add(new_profile)
                    db.session.commit()
                    flash(f"Faculty profile created successfully! Password Setup required: {needs_pw}", "success")
                
        elif action == 'edit':
            profile_id = int(request.form.get('profile_id'))
            profile = TeacherProfile.query.get(profile_id)
            if profile:
                profile.name = request.form.get('name', '').strip()
                profile.phone = request.form.get('phone', '').strip()
                profile.department_id = int(request.form.get('department_id')) if request.form.get('department_id') else None
                
                user = profile.user
                if user:
                    user.email = request.form.get('email', '').strip()
                    
                    new_pwd = request.form.get('password')
                    if new_pwd:
                        user.set_password(new_pwd)
                        user.needs_password_setup = False
                        user.is_active = True
                        
                db.session.commit()
                flash("Faculty profile updated successfully!", "success")
                
        elif action == 'toggle':
            profile_id = int(request.form.get('profile_id'))
            profile = TeacherProfile.query.get(profile_id)
            if profile and profile.user:
                profile.user.is_active = not profile.user.is_active
                db.session.commit()
                state_str = "activated" if profile.user.is_active else "deactivated"
                flash(f"Faculty profile {state_str}!", "success")
                
        elif action == 'reset':
            profile_id = int(request.form.get('profile_id'))
            profile = TeacherProfile.query.get(profile_id)
            if profile and profile.user:
                profile.user.needs_password_setup = True
                profile.user.password_hash = None
                profile.user.is_active = False # Deactivate until setup again
                db.session.commit()
                flash("Faculty credentials reset. They must set up a new password on their next login.", "warning")
                
        elif action == 'delete':
            profile_id = int(request.form.get('profile_id'))
            profile = TeacherProfile.query.get(profile_id)
            if profile:
                user = profile.user
                db.session.delete(profile)
                if user:
                    db.session.delete(user)
                db.session.commit()
                flash("Faculty profile and account deleted.", "success")
                
        return redirect(url_for('admin_teachers'))
        
    profiles = TeacherProfile.query.order_by(TeacherProfile.name).all()
    edit_profile = None
    edit_id = request.args.get('edit_id')
    if edit_id:
        edit_profile = TeacherProfile.query.get(int(edit_id))
        
    return render_template('admin_teachers.html', 
                           teachers=profiles, 
                           departments=departments,
                           edit_teacher=edit_profile)

@app.route('/admin/approvals', methods=['GET', 'POST'])
def admin_approvals():
    if not is_logged_in() or session.get('role') != 'admin':
        flash("Access Denied.", "danger")
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        profile_id = int(request.form.get('profile_id'))
        decision = request.form.get('decision') # 'approve' or 'reject'
        
        profile = TeacherProfile.query.get(profile_id)
        if profile and profile.user:
            if decision == 'approve':
                profile.approval_status = 'Approved'
                profile.user.is_active = True
                profile.approved_by_id = session.get('user_id')
                profile.approved_at = datetime.datetime.utcnow()
                flash(f"Approved registration for {profile.name}!", "success")
            elif decision == 'reject':
                profile.approval_status = 'Rejected'
                profile.user.is_active = False
                flash(f"Rejected registration for {profile.name}.", "warning")
                
            db.session.commit()
            
        return redirect(url_for('admin_approvals'))
        
    pending = TeacherProfile.query.filter_by(approval_status='Pending').join(TeacherProfile.user).order_by(User.created_at).all()
    past_approvals = TeacherProfile.query.filter(TeacherProfile.approval_status != 'Pending').order_by(TeacherProfile.approved_at.desc()).all()
    
    return render_template('admin_approvals.html', pending=pending, past_approvals=past_approvals)

@app.route('/admin/departments', methods=['GET', 'POST'])
def admin_departments():
    if not is_logged_in() or session.get('role') != 'admin':
        flash("Access Denied.", "danger")
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            name = request.form.get('name', '').strip()
            code = request.form.get('code', '').strip().upper()
            
            existing = Department.query.filter(
                (Department.code == code) | (Department.name == name)
            ).first()
            if existing:
                flash("Department name or code already exists.", "danger")
            else:
                new_dept = Department(name=name, code=code)
                db.session.add(new_dept)
                db.session.commit()
                flash("Department added successfully!", "success")
                
        elif action == 'delete':
            dept_id = int(request.form.get('department_id'))
            dept = Department.query.get(dept_id)
            if dept:
                # Any linked teachers will have their department_id set to NULL due to ON DELETE SET NULL
                db.session.delete(dept)
                db.session.commit()
                flash("Department deleted successfully.", "success")
                
        return redirect(url_for('admin_departments'))
        
    departments = Department.query.order_by(Department.name).all()
    return render_template('admin_departments.html', departments=departments)

@app.route('/admin/timetable', methods=['GET', 'POST'])
def admin_timetable():
    if not is_logged_in() or session.get('role') != 'admin':
        flash("Access Denied.", "danger")
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            profile_id = int(request.form.get('teacher_profile_id'))
            subject = request.form.get('subject', '').strip()
            classroom = request.form.get('classroom', '').strip()
            day_of_week = int(request.form.get('day_of_week'))
            
            start_str = request.form.get('start_time')
            end_str = request.form.get('end_time')
            
            # Parse times
            start_time = datetime.datetime.strptime(start_str, '%H:%M').time()
            end_time = datetime.datetime.strptime(end_str, '%H:%M').time()
            
            tt = Timetable(
                teacher_profile_id=profile_id,
                subject=subject,
                classroom=classroom,
                day_of_week=day_of_week,
                start_time=start_time,
                end_time=end_time
            )
            db.session.add(tt)
            db.session.commit()
            flash("Schedule mapped successfully!", "success")
            
        elif action == 'delete':
            tt_id = int(request.form.get('timetable_id'))
            tt = Timetable.query.get(tt_id)
            if tt:
                db.session.delete(tt)
                db.session.commit()
                flash("Schedule mapping removed.", "success")
                
        return redirect(url_for('admin_timetable'))
        
    teachers = TeacherProfile.query.filter_by(approval_status='Approved').join(TeacherProfile.user).filter(User.is_active == True).order_by(TeacherProfile.name).all()
    timetables_raw = Timetable.query.join(TeacherProfile).order_by(Timetable.day_of_week, Timetable.start_time).all()
    
    timetables = [tt.to_dict() for tt in timetables_raw]
    return render_template('admin_timetable.html', 
                           teachers=teachers, 
                           timetables=timetables)

@app.route('/admin/attendance')
def admin_attendance():
    if not is_logged_in() or session.get('role') != 'admin':
        flash("Access Denied.", "danger")
        return redirect(url_for('login'))
        
    # Filters parameters
    profile_id = request.args.get('profile_id')
    status = request.args.get('status')
    date_str = request.args.get('date')
    reason = request.args.get('reason')
    
    query = AttendanceLog.query
    
    if profile_id:
        query = query.filter(AttendanceLog.teacher_profile_id == int(profile_id))
    if status:
        query = query.filter(AttendanceLog.status == status)
    if date_str:
        target_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        query = query.filter(db.func.date(AttendanceLog.timestamp) == target_date)
    if reason:
        query = query.filter(AttendanceLog.suspicious_reason == reason)
        
    logs_raw = query.order_by(AttendanceLog.timestamp.desc()).all()
    logs = [log.to_dict() for log in logs_raw]
    
    teachers = TeacherProfile.query.order_by(TeacherProfile.name).all()
    
    return render_template('admin_attendance.html',
                           logs=logs,
                           teachers=teachers,
                           selected_profile_id=profile_id,
                           selected_status=status,
                           selected_date=date_str,
                           selected_reason=reason)

@app.route('/admin/verify_action', methods=['POST'])
def admin_verify_action():
    if not is_logged_in() or session.get('role') != 'admin':
        flash("Access Denied.", "danger")
        return redirect(url_for('login'))
        
    log_id = int(request.form.get('log_id'))
    status = request.form.get('status')
    notes = request.form.get('notes')
    
    log = AttendanceLog.query.get(log_id)
    if log:
        log.status = status
        log.verification_notes = notes
        db.session.commit()
        flash("Attendance verification log updated successfully.", "success")
    else:
        flash("Log record not found.", "danger")
        
    return redirect(url_for('admin_attendance'))

@app.route('/admin/settings', methods=['GET', 'POST'])
def admin_settings():
    if not is_logged_in() or session.get('role') != 'admin':
        flash("Access Denied.", "danger")
        return redirect(url_for('login'))
        
    settings = CampusSetting.query.first()
    
    if request.method == 'POST':
        campus_name = request.form.get('campus_name', '').strip()
        latitude = float(request.form.get('latitude'))
        longitude = float(request.form.get('longitude'))
        radius_meters = float(request.form.get('radius_meters'))
        start_window_before_mins = int(request.form.get('start_window_before_mins'))
        end_window_after_mins = int(request.form.get('end_window_after_mins'))
        
        if not settings:
            settings = CampusSetting()
            db.session.add(settings)
            
        settings.campus_name = campus_name
        settings.latitude = latitude
        settings.longitude = longitude
        settings.radius_meters = radius_meters
        settings.start_window_before_mins = start_window_before_mins
        settings.end_window_after_mins = end_window_after_mins
        
        db.session.commit()
        flash("Campus Rules and coordinates updated successfully!", "success")
        return redirect(url_for('admin_settings'))
        
    return render_template('admin_settings.html', settings=settings)

@app.route('/admin/reports')
def admin_reports():
    if not is_logged_in() or session.get('role') != 'admin':
        flash("Access Denied.", "danger")
        return redirect(url_for('login'))
        
    # All-time counters
    total_scheduled = Timetable.query.count()
    total_logs = AttendanceLog.query.count()
    total_suspicious = AttendanceLog.query.filter_by(status='Suspicious').count()
    
    # Specific flag incident counts
    duplicate_images = AttendanceLog.query.filter(AttendanceLog.suspicious_reason == 'Duplicate Image').count()
    outside_campus = AttendanceLog.query.filter(AttendanceLog.suspicious_reason == 'Outside Campus').count()
    low_students = AttendanceLog.query.filter(AttendanceLog.suspicious_reason == 'Low Student Count').count()
    
    incidents = {
        'duplicate_images': duplicate_images,
        'outside_campus': outside_campus,
        'low_students': low_students
    }
    
    # Teacher statistics compiling
    teachers = TeacherProfile.query.all()
    teacher_stats = []
    
    for t in teachers:
        marked_count = AttendanceLog.query.filter_by(teacher_profile_id=t.id).count()
        susp_count = AttendanceLog.query.filter_by(teacher_profile_id=t.id, status='Suspicious').count()
        slots_count = Timetable.query.filter_by(teacher_profile_id=t.id).count()
        
        rate = 100
        if slots_count > 0:
            period_opportunities = slots_count * 5  # 5 days
            rate = round((marked_count / period_opportunities) * 100)
            rate = min(rate, 100)
        else:
            rate = 0
            
        teacher_stats.append({
            'name': t.name,
            'department': t.department.name if t.department else 'N/A',
            'marked_count': marked_count,
            'suspicious_count': susp_count,
            'rate': rate
        })
        
    return render_template('admin_reports.html',
                           total_scheduled_all_time=total_scheduled,
                           total_logs_all_time=total_logs,
                           total_suspicious_all_time=total_suspicious,
                           teacher_stats=teacher_stats,
                           incidents=incidents)

# Start Application
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
