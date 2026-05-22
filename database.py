import sqlite3
import os
from models import db, Role, Department, ClassSection, User, TeacherProfile, CampusSetting, Timetable, TimetableUploadLog

def run_migrations(app):
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not db_uri.startswith('sqlite:///'):
        return
    
    db_path = db_uri.replace('sqlite:///', '')
    if not os.path.isabs(db_path):
        db_path = os.path.join(app.root_path if hasattr(app, 'root_path') else os.getcwd(), db_path)
    
    if not os.path.exists(db_path):
        return
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='attendance_logs'")
    table_exists = cursor.fetchone()
    if not table_exists:
        conn.close()
        return
        
    # Check column names
    cursor.execute("PRAGMA table_info(attendance_logs)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'is_archived' not in columns:
        print("Migrating attendance_logs table schema...")
        try:
            conn.execute("BEGIN TRANSACTION")
            
            # Create temporary table matching new models.py schema
            cursor.execute("""
                CREATE TABLE attendance_logs_new (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    teacher_profile_id INTEGER,
                    timetable_id INTEGER,
                    timestamp DATETIME NOT NULL,
                    gps_record_id INTEGER NOT NULL,
                    image_record_id INTEGER NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    suspicious_reason VARCHAR(255),
                    verification_notes TEXT,
                    is_archived BOOLEAN NOT NULL DEFAULT 0,
                    teacher_name VARCHAR(120),
                    subject VARCHAR(100),
                    classroom VARCHAR(50),
                    class_name VARCHAR(100),
                    period VARCHAR(50),
                    FOREIGN KEY(teacher_profile_id) REFERENCES teacher_profiles(id) ON DELETE SET NULL,
                    FOREIGN KEY(timetable_id) REFERENCES timetables(id) ON DELETE SET NULL,
                    FOREIGN KEY(gps_record_id) REFERENCES gps_records(id) ON DELETE CASCADE,
                    FOREIGN KEY(image_record_id) REFERENCES image_records(id) ON DELETE CASCADE,
                    UNIQUE(gps_record_id),
                    UNIQUE(image_record_id)
                )
            """)
            
            # Copy data, joining to populate cached snapshots
            cursor.execute("""
                INSERT INTO attendance_logs_new (
                    id, teacher_profile_id, timetable_id, timestamp, gps_record_id, image_record_id,
                    status, suspicious_reason, verification_notes, is_archived,
                    teacher_name, subject, classroom, class_name, period
                )
                SELECT 
                    a.id, a.teacher_profile_id, a.timetable_id, a.timestamp, a.gps_record_id, a.image_record_id,
                    a.status, a.suspicious_reason, a.verification_notes, 0 as is_archived,
                    tp.name as teacher_name,
                    t.subject as subject,
                    t.classroom as classroom,
                    c.name as class_name,
                    t.period as period
                FROM attendance_logs a
                LEFT JOIN teacher_profiles tp ON a.teacher_profile_id = tp.id
                LEFT JOIN timetables t ON a.timetable_id = t.id
                LEFT JOIN classes c ON t.class_id = c.id
            """)
            
            cursor.execute("DROP TABLE attendance_logs")
            cursor.execute("ALTER TABLE attendance_logs_new RENAME TO attendance_logs")
            
            conn.commit()
            print("Successfully migrated attendance_logs table schema.")
        except Exception as e:
            conn.rollback()
            print(f"Error during database migration: {e}")
            raise e
            
    conn.close()

def init_db(app):
    db.init_app(app)
    # Run SQLite migration before creating tables or seeding
    run_migrations(app)
    with app.app_context():
        db.create_all()
        seed_data()

def seed_data():
    # 1. Seed Roles
    admin_role = Role.query.filter_by(name='admin').first()
    if not admin_role:
        admin_role = Role(name='admin')
        db.session.add(admin_role)
        
    teacher_role = Role.query.filter_by(name='teacher').first()
    if not teacher_role:
        teacher_role = Role(name='teacher')
        db.session.add(teacher_role)
        
    db.session.commit()
    
    # 2. Seed Default Admin User
    admin = User.query.filter_by(role_id=admin_role.id).first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@college.edu',
            role_id=admin_role.id,
            is_active=True,
            needs_password_setup=False
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print("Admin user seeded: admin / admin123")

        
    # 3. Seed Standard Departments
    dept_specs = [
        ("Computer Science & Engineering", "CSE"),
        ("Electronics & Communication Engineering", "ECE"),
        ("Mechanical Engineering", "ME"),
        ("Electrical Engineering", "EE"),
        ("Civil Engineering", "CE")
    ]
    
    for name, code in dept_specs:
        dept = Department.query.filter_by(code=code).first()
        if not dept:
            dept = Department(name=name, code=code)
            db.session.add(dept)
            
    db.session.commit()

    # 3b. Seed Default Classes
    class_specs = [
        "Class 11",
        "Class 12",
        "BSc 1st Year",
        "BCA 2nd Year",
        "MCA"
    ]
    for cname in class_specs:
        csec = ClassSection.query.filter_by(name=cname).first()
        if not csec:
            csec = ClassSection(name=cname)
            db.session.add(csec)
            
    db.session.commit()
    
    # 4. Seed Default Campus Coordinates (Dibrugarh, Assam, India)
    campus = CampusSetting.query.first()
    if not campus:
        campus = CampusSetting(
            campus_name="Dibrugarh College Campus",
            latitude=27.475807921264003,
            longitude=94.55106863579525,
            radius_meters=100.0,
            start_window_before_mins=5,
            end_window_after_mins=15
        )
        db.session.add(campus)
        db.session.commit()
        print("Campus settings seeded.")
        
    # 5. Seed one Pending/First-login Guest Teacher for verification purposes
    guest_user = User.query.filter_by(email='guest@college.edu').first()
    if not guest_user:
        ece_dept = Department.query.filter_by(code='ECE').first()
        
        guest_user = User(
            username='guest',
            email='guest@college.edu',
            role_id=teacher_role.id,
            is_active=False, # Active after setting password
            needs_password_setup=True
        )
        # Note: no password hash is set initially for admin-created first-time users
        db.session.add(guest_user)
        db.session.commit()
        
        guest_profile = TeacherProfile(
            user_id=guest_user.id,
            employee_id='EMP101',
            name='Prof. Rajesh Kumar (Guest)',
            phone='+91 98765 43210',
            department_id=ece_dept.id,
            approval_status='Approved' # Admin created is approved, just needs password setup
        )
        db.session.add(guest_profile)
        db.session.commit()
        print("Guest teacher seeded for first-time password setup verification: email: guest@college.edu, emp_id: EMP101")
        
    print("Database seeding pipeline complete.")
