from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import werkzeug.security as security

db = SQLAlchemy()

class Role(db.Model):
    __tablename__ = 'roles'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False) # 'admin', 'teacher'
    
    users = db.relationship('User', backref='role', lazy=True)

    def __repr__(self):
        return f"<Role {self.name}>"

class Department(db.Model):
    __tablename__ = 'departments'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False) # e.g. 'CSE', 'ECE'
    
    # Relationships
    teachers = db.relationship('TeacherProfile', backref='department', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'teacher_count': len(self.teachers)
        }

class ClassSection(db.Model):
    __tablename__ = 'classes'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    
    # Relationships
    timetables = db.relationship('Timetable', backref='class_section', cascade="all, delete-orphan", lazy=True)
    upload_logs = db.relationship('TimetableUploadLog', backref='class_section', cascade="all, delete-orphan", lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'timetable_count': len(self.timetables)
        }

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=True) # Nullable for first-time password setup
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True)
    needs_password_setup = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # One-to-one relationship with TeacherProfile
    profile = db.relationship('TeacherProfile', foreign_keys='TeacherProfile.user_id', back_populates='user', uselist=False, cascade="all, delete-orphan", lazy=True)

    def set_password(self, password):
        self.password_hash = security.generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return security.check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role.name if self.role else 'Unknown',
            'is_active': self.is_active,
            'needs_password_setup': self.needs_password_setup,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }

class TeacherProfile(db.Model):
    __tablename__ = 'teacher_profiles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False)
    employee_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id', ondelete='SET NULL'), nullable=True)
    approval_status = db.Column(db.String(20), default='Pending', nullable=False) # 'Pending', 'Approved', 'Rejected'
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], back_populates='profile', lazy=True)
    approver = db.relationship('User', foreign_keys=[approved_by_id], lazy=True)
    timetables = db.relationship('Timetable', backref='teacher_profile', cascade="all, delete-orphan", lazy=True)
    attendance_logs = db.relationship('AttendanceLog', backref='teacher_profile', cascade="all, delete-orphan", lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.user.username if self.user else 'Unknown',
            'employee_id': self.employee_id,
            'name': self.name,
            'phone': self.phone,
            'department_id': self.department_id,
            'department_name': self.department.name if self.department else 'Not Assigned',
            'department_code': self.department.code if self.department else 'N/A',
            'approval_status': self.approval_status,
            'is_active': self.user.is_active if self.user else False,
            'needs_password_setup': self.user.needs_password_setup if self.user else False
        }

class Timetable(db.Model):
    __tablename__ = 'timetables'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_profile_id = db.Column(db.Integer, db.ForeignKey('teacher_profiles.id', ondelete='CASCADE'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id', ondelete='CASCADE'), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    classroom = db.Column(db.String(50), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False) # 0 = Monday, ..., 6 = Sunday
    period = db.Column(db.String(50), nullable=False, default="Period 1")
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    
    attendance_logs = db.relationship('AttendanceLog', backref='timetable', cascade="all, delete-orphan", lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'teacher_profile_id': self.teacher_profile_id,
            'teacher_name': self.teacher_profile.name if self.teacher_profile else 'Unknown',
            'class_id': self.class_id,
            'class_name': self.class_section.name if self.class_section else 'N/A',
            'subject': self.subject,
            'classroom': self.classroom,
            'day_of_week': self.day_of_week,
            'period': self.period,
            'start_time': self.start_time.strftime('%H:%M'),
            'end_time': self.end_time.strftime('%H:%M')
        }

class GPSRecord(db.Model):
    __tablename__ = 'gps_records'
    
    id = db.Column(db.Integer, primary_key=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    distance_meters = db.Column(db.Float, nullable=False)
    is_within_boundary = db.Column(db.Boolean, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'distance_meters': round(self.distance_meters, 2),
            'is_within_boundary': self.is_within_boundary
        }

class ImageRecord(db.Model):
    __tablename__ = 'image_records'
    
    id = db.Column(db.Integer, primary_key=True)
    image_path = db.Column(db.String(255), nullable=False)
    image_hash = db.Column(db.String(64), nullable=False)
    student_count = db.Column(db.Integer, nullable=False, default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'image_path': self.image_path,
            'image_hash': self.image_hash,
            'student_count': self.student_count
        }

class AttendanceLog(db.Model):
    __tablename__ = 'attendance_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_profile_id = db.Column(db.Integer, db.ForeignKey('teacher_profiles.id', ondelete='CASCADE'), nullable=False)
    timetable_id = db.Column(db.Integer, db.ForeignKey('timetables.id', ondelete='CASCADE'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships with GPS and Image records
    gps_record_id = db.Column(db.Integer, db.ForeignKey('gps_records.id', ondelete='CASCADE'), unique=True, nullable=False)
    image_record_id = db.Column(db.Integer, db.ForeignKey('image_records.id', ondelete='CASCADE'), unique=True, nullable=False)
    
    status = db.Column(db.String(20), nullable=False, default='Pending') # 'Approved', 'Suspicious', 'Rejected'
    suspicious_reason = db.Column(db.String(255), nullable=True)
    verification_notes = db.Column(db.Text, nullable=True)

    gps_record = db.relationship('GPSRecord', backref=db.backref('attendance_log', uselist=False), lazy=True)
    image_record = db.relationship('ImageRecord', backref=db.backref('attendance_log', uselist=False), lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'teacher_profile_id': self.teacher_profile_id,
            'teacher_name': self.teacher_profile.name if self.teacher_profile else 'Unknown',
            'timetable_id': self.timetable_id,
            'subject': self.timetable.subject if self.timetable else 'Deleted Class',
            'classroom': self.timetable.classroom if self.timetable else 'N/A',
            'class_name': self.timetable.class_section.name if (self.timetable and self.timetable.class_section) else 'N/A',
            'period': self.timetable.period if self.timetable else 'N/A',
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'latitude': self.gps_record.latitude if self.gps_record else 0.0,
            'longitude': self.gps_record.longitude if self.gps_record else 0.0,
            'distance_meters': round(self.gps_record.distance_meters, 2) if self.gps_record else 0.0,
            'image_path': self.image_record.image_path if self.image_record else '',
            'image_hash': self.image_record.image_hash if self.image_record else '',
            'student_count': self.image_record.student_count if self.image_record else 0,
            'status': self.status,
            'suspicious_reason': self.suspicious_reason,
            'verification_notes': self.verification_notes
        }

class CampusSetting(db.Model):
    __tablename__ = 'campus_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    campus_name = db.Column(db.String(100), nullable=False, default="Main College Campus")
    latitude = db.Column(db.Float, nullable=False, default=27.475807921264003)
    longitude = db.Column(db.Float, nullable=False, default=94.55106863579525)
    radius_meters = db.Column(db.Float, nullable=False, default=100.0)
    start_window_before_mins = db.Column(db.Integer, nullable=False, default=5)
    end_window_after_mins = db.Column(db.Integer, nullable=False, default=15)

    def to_dict(self):
        return {
            'id': self.id,
            'campus_name': self.campus_name,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'radius_meters': self.radius_meters,
            'start_window_before_mins': self.start_window_before_mins,
            'end_window_after_mins': self.end_window_after_mins
        }

class TimetableUploadLog(db.Model):
    __tablename__ = 'timetable_upload_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id', ondelete='CASCADE'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), nullable=False, default="Draft") # "Draft", "Completed", "Failed"
    import_summary = db.Column(db.String(255), nullable=True)
    validation_errors = db.Column(db.Text, nullable=True) # JSON serialized list of strings/dicts
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'class_id': self.class_id,
            'class_name': self.class_section.name if self.class_section else 'N/A',
            'filename': self.filename,
            'filepath': self.filepath,
            'status': self.status,
            'import_summary': self.import_summary,
            'validation_errors': self.validation_errors,
            'uploaded_at': self.uploaded_at.strftime('%Y-%m-%d %H:%M:%S')
        }
