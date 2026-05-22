import datetime
from models import db, Role, Department, ClassSection, User, TeacherProfile, CampusSetting, Timetable

def init_db(app):
    db.init_app(app)
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
    admin = User.query.filter_by(username='admin').first()
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
