import os
import unittest
import tempfile
import datetime
from app import app
from models import db, Role, Department, ClassSection, User, TeacherProfile, CampusSetting, Timetable, GPSRecord, ImageRecord, AttendanceLog

class FacultySystemTestCase(unittest.TestCase):
    
    def setUp(self):
        # Configure app for testing with an isolated database
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['DEBUG_MOCK_LOCATION'] = True
        
        self.db_fd, self.db_path = tempfile.mkstemp()
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{self.db_path}'
        self.client = app.test_client()
        
        with app.app_context():
            # Clear any session caching from the import-time seeding
            db.session.remove()
            db.create_all()
            
            # Use the system's native seeding function
            from database import seed_data
            seed_data()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()
        os.close(self.db_fd)
        try:
            os.unlink(self.db_path)
        except PermissionError:
            pass

    def login_client(self, username, password):
        return self.client.post('/login', data={
            'username': username,
            'password': password
        }, follow_redirects=True)

    def logout_client(self):
        return self.client.get('/logout', follow_redirects=True)

    def test_teacher_self_registration_and_admin_approval(self):
        # Fetch department ID for CSE
        with app.app_context():
            cse_dept = Department.query.filter_by(code='CSE').first()
            self.assertIsNotNone(cse_dept)
            cse_dept_id = cse_dept.id

        # 1. Register a new teacher
        response = self.client.post('/register', data={
            'employee_id': 'EMP999',
            'name': 'Prof. Test Teacher',
            'email': 'teacher@college.edu',
            'phone': '1234567890',
            'department_id': str(cse_dept_id),
            'username': 'testteacher',
            'password': 'password123',
            'confirm_password': 'password123'
        }, follow_redirects=True)
        
        self.assertIn(b"Registration submitted successfully", response.data)
        
        # Verify db states
        with app.app_context():
            user = User.query.filter_by(username='testteacher').first()
            self.assertIsNotNone(user)
            self.assertFalse(user.is_active)
            self.assertEqual(user.profile.employee_id, 'EMP999')
            self.assertEqual(user.profile.approval_status, 'Pending')
            
        # 2. Try logging in as teacher before approval - should show pending message
        response = self.login_client('testteacher', 'password123')
        self.assertIn(b"Your account registration is Pending Admin approval", response.data)
        
        # 3. Log in as admin and approve teacher
        self.login_client('admin', 'admin123')
        with app.app_context():
            profile = TeacherProfile.query.filter_by(employee_id='EMP999').first()
            profile_id = profile.id
            
        response = self.client.post('/admin/approvals', data={
            'profile_id': str(profile_id),
            'decision': 'approve'
        }, follow_redirects=True)
        
        self.assertIn(b"Approved registration", response.data)
        
        # Verify db states updated
        with app.app_context():
            user = User.query.filter_by(username='testteacher').first()
            self.assertTrue(user.is_active)
            self.assertEqual(user.profile.approval_status, 'Approved')
            
        # Logout admin
        self.logout_client()
        
        # 4. Log in as teacher now - should succeed
        response = self.login_client('testteacher', 'password123')
        self.assertIn(b"My Classroom Schedules", response.data)

    def test_first_time_login_and_password_setup(self):
        # Fetch department ID for CSE
        with app.app_context():
            cse_dept = Department.query.filter_by(code='CSE').first()
            cse_dept_id = cse_dept.id

        # 1. Admin adds a teacher profile manually without password
        self.login_client('admin', 'admin123')
        response = self.client.post('/admin/teachers', data={
            'action': 'add',
            'name': 'Dr. First Time',
            'username': 'firsttime',
            'email': 'firsttime@college.edu',
            'phone': '9999999999',
            'employee_id': 'EMP123',
            'department_id': str(cse_dept_id),
            'password': '' # Empty triggers needs_password_setup
        }, follow_redirects=True)
        
        self.assertIn(b"Faculty profile created successfully", response.data)
        
        with app.app_context():
            user = User.query.filter_by(username='firsttime').first()
            self.assertIsNotNone(user)
            self.assertTrue(user.needs_password_setup)
            self.assertFalse(user.is_active)
            self.assertEqual(user.profile.approval_status, 'Approved')
            
        self.logout_client()
        
        # 2. Teacher logs in. Should redirect to password setup
        response = self.login_client('firsttime', 'anything')
        self.assertIn(b"First-time login detected. Please establish your credentials.", response.data)
        
        # 3. Setup password
        response = self.client.post('/setup_password', data={
            'employee_id': 'EMP123',
            'email': 'firsttime@college.edu',
            'password': 'newpassword123',
            'confirm_password': 'newpassword123'
        }, follow_redirects=True)
        
        self.assertIn(b"Password established successfully", response.data)
        
        # Verify db states updated
        with app.app_context():
            user = User.query.filter_by(username='firsttime').first()
            self.assertFalse(user.needs_password_setup)
            self.assertTrue(user.is_active)
            
        # 4. Login with new credentials should succeed
        response = self.login_client('firsttime', 'newpassword123')
        self.assertIn(b"My Classroom Schedules", response.data)

    def test_admin_crud_operations(self):
        self.login_client('admin', 'admin123')
        
        # 1. Departments CRUD
        response = self.client.post('/admin/departments', data={
            'action': 'add',
            'name': 'Chemical Engineering',
            'code': 'CH'
        }, follow_redirects=True)
        self.assertIn(b"Department added successfully", response.data)
        
        with app.app_context():
            dept = Department.query.filter_by(code='CH').first()
            self.assertIsNotNone(dept)
            dept_id = dept.id
            
        response = self.client.post('/admin/departments', data={
            'action': 'delete',
            'department_id': str(dept_id)
        }, follow_redirects=True)
        self.assertIn(b"Department deleted successfully", response.data)
        
        with app.app_context():
            dept = Department.query.filter_by(code='CH').first()
            self.assertIsNone(dept)
            
        # 2. Campus Settings Update
        response = self.client.post('/admin/settings', data={
            'campus_name': 'New Campus Name',
            'latitude': '27.5000',
            'longitude': '94.6000',
            'radius_meters': '200.0',
            'start_window_before_mins': '10',
            'end_window_after_mins': '20'
        }, follow_redirects=True)
        self.assertIn(b"Campus Rules and coordinates updated successfully", response.data)
        
        with app.app_context():
            settings = CampusSetting.query.first()
            self.assertEqual(settings.campus_name, 'New Campus Name')
            self.assertEqual(settings.latitude, 27.5)
            self.assertEqual(settings.radius_meters, 200.0)
            self.assertEqual(settings.start_window_before_mins, 10)

        # 3. Timetable CRUD
        # First register/approve a teacher
        with app.app_context():
            cse_dept = Department.query.filter_by(code='CSE').first()
            cse_dept_id = cse_dept.id

        self.logout_client()
        self.client.post('/register', data={
            'employee_id': 'EMP111',
            'name': 'Timetable Teacher',
            'email': 'tt@college.edu',
            'phone': '1234567890',
            'department_id': str(cse_dept_id),
            'username': 'ttteacher',
            'password': 'password123',
            'confirm_password': 'password123'
        })
        with app.app_context():
            profile = TeacherProfile.query.filter_by(employee_id='EMP111').first()
            profile.approval_status = 'Approved'
            profile.user.is_active = True
            db.session.commit()
            profile_id = profile.id
            
            # Fetch a class section seeded in database
            class_sec = ClassSection.query.first()
            class_id = class_sec.id
            
        self.login_client('admin', 'admin123')
        response = self.client.post('/admin/timetable', data={
            'action': 'add',
            'teacher_profile_id': str(profile_id),
            'class_id': str(class_id),
            'subject': 'Software Engineering',
            'classroom': 'Room 303',
            'day_of_week': '1', # Tuesday
            'period': 'Period 1',
            'start_time': '10:00',
            'end_time': '11:00'
        }, follow_redirects=True)
        self.assertIn(b"Schedule mapped successfully", response.data)
        
        with app.app_context():
            tt = Timetable.query.filter_by(teacher_profile_id=profile_id, subject='Software Engineering').first()
            self.assertIsNotNone(tt)
            self.assertEqual(tt.classroom, 'Room 303')
            self.assertEqual(tt.period, 'Period 1')
            self.assertEqual(tt.start_time, datetime.time(10, 0))
            timetable_id = tt.id
            
        response = self.client.post('/admin/timetable', data={
            'action': 'delete',
            'timetable_id': str(timetable_id)
        }, follow_redirects=True)
        self.assertIn(b"Schedule mapping removed", response.data)
        
        with app.app_context():
            tt = Timetable.query.filter_by(teacher_profile_id=profile_id, subject='Software Engineering').first()
            self.assertIsNone(tt)

    def test_class_deletion_cascades_timetable(self):
        self.login_client('admin', 'admin123')
        # 1. Add a Class
        self.client.post('/admin/classes', data={
            'action': 'add',
            'name': 'BTech 4th Year'
        }, follow_redirects=True)
        
        with app.app_context():
            csec = ClassSection.query.filter_by(name='BTech 4th Year').first()
            self.assertIsNotNone(csec)
            class_id = csec.id
            teacher = TeacherProfile.query.first()
            teacher_id = teacher.id

        # 2. Map a Timetable to it
        self.client.post('/admin/timetable', data={
            'action': 'add',
            'teacher_profile_id': str(teacher_id),
            'class_id': str(class_id),
            'subject': 'Compiler Design',
            'classroom': 'Lab 1',
            'day_of_week': '2',
            'period': 'Period 3',
            'start_time': '11:00',
            'end_time': '12:00'
        }, follow_redirects=True)

        with app.app_context():
            tt = Timetable.query.filter_by(class_id=class_id, subject='Compiler Design').first()
            self.assertIsNotNone(tt)
            tt_id = tt.id

        # 3. Delete the Class
        self.client.post('/admin/classes', data={
            'action': 'delete',
            'class_id': str(class_id)
        }, follow_redirects=True)

        # 4. Verify that Class is deleted AND the mapped Timetable slot is also deleted (cascade delete)
        with app.app_context():
            csec_check = ClassSection.query.get(class_id)
            self.assertIsNone(csec_check)
            tt_check = Timetable.query.get(tt_id)
            self.assertIsNone(tt_check)

    def test_admin_profile_credential_update(self):
        # 1. Login as admin
        self.login_client('admin', 'admin123')

        # 2. Update credentials (change username to 'superadmin', set new password 'superpass123')
        response = self.client.post('/admin/settings/profile', data={
            'username': 'superadmin',
            'email': 'superadmin@college.edu',
            'new_password': 'superpass123',
            'confirm_password': 'superpass123'
        }, follow_redirects=True)
        self.assertIn(b"Administrator credentials updated successfully!", response.data)

        # 3. Log out and try old credentials (should fail)
        self.logout_client()
        response_fail = self.login_client('admin', 'admin123')
        self.assertIn(b"Invalid username or password", response_fail.data)

        # 4. Log in with new credentials (should succeed)
        response_success = self.login_client('superadmin', 'superpass123')
        self.assertIn(b"Log Out", response_success.data)


        # 5. Test password mismatch (should fail validation)
        response_mismatch = self.client.post('/admin/settings/profile', data={
            'username': 'superadmin',
            'email': 'superadmin@college.edu',
            'new_password': 'longermismatch',
            'confirm_password': 'mismatch'
        }, follow_redirects=True)
        self.assertIn(b"Passwords do not match", response_mismatch.data)


if __name__ == '__main__':
    unittest.main()

