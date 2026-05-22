import re
import difflib
import datetime
import pandas as pd
import pdfplumber
import pytesseract
import os
import json

# Setup pytesseract path for common Windows locations just in case it is installed but not in PATH
TESSERACT_COMMON_PATHS = [
    r'C:\Program Files\Tesseract-OCR\tesseract.exe',
    r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    r'D:\Program Files\Tesseract-OCR\tesseract.exe'
]
for path in TESSERACT_COMMON_PATHS:
    if os.path.exists(path):
        pytesseract.pytesseract.tesseract_cmd = path
        break

# Default Period to Times mapping
PERIOD_DEFAULT_TIMES = {
    "period 1": (datetime.time(9, 0), datetime.time(10, 0)),
    "period 2": (datetime.time(10, 0), datetime.time(11, 0)),
    "period 3": (datetime.time(11, 0), datetime.time(12, 0)),
    "period 4": (datetime.time(12, 0), datetime.time(13, 0)),
    "period 5": (datetime.time(13, 0), datetime.time(14, 0)),
    "period 6": (datetime.time(14, 0), datetime.time(15, 0)),
    "period 7": (datetime.time(15, 0), datetime.time(16, 0)),
    "period 8": (datetime.time(16, 0), datetime.time(17, 0)),
    "p1": (datetime.time(9, 0), datetime.time(10, 0)),
    "p2": (datetime.time(10, 0), datetime.time(11, 0)),
    "p3": (datetime.time(11, 0), datetime.time(12, 0)),
    "p4": (datetime.time(12, 0), datetime.time(13, 0)),
    "p5": (datetime.time(13, 0), datetime.time(14, 0)),
    "p6": (datetime.time(14, 0), datetime.time(15, 0)),
    "p7": (datetime.time(15, 0), datetime.time(16, 0)),
    "p8": (datetime.time(16, 0), datetime.time(17, 0)),
}

DAYS_MAP = {
    "monday": 0, "mon": 0, "m": 0,
    "tuesday": 1, "tue": 1, "t": 1,
    "wednesday": 2, "wed": 2, "w": 2,
    "thursday": 3, "thu": 3, "th": 3,
    "friday": 4, "fri": 4, "f": 4,
    "saturday": 5, "sat": 5, "s": 5,
    "sunday": 6, "sun": 6, "su": 6
}

def clean_name(name):
    """Remove titles and punctuation to clean teacher names."""
    if not name:
        return ""
    # Remove academic prefixes
    name = re.sub(r'^(dr\.|prof\.|mr\.|mrs\.|ms\.|prof|dr|er\.)\s+', '', name, flags=re.IGNORECASE)
    # Remove punctuation
    name = re.sub(r'[^a-zA-Z0-9\s]', '', name)
    return name.strip().lower()

def find_best_teacher_match(extracted_name, database_teachers):
    """
    Fuzzy match extracted teacher name to database TeacherProfile records.
    Returns: (TeacherProfile_dict, score) or (None, 0.0)
    """
    cleaned_extracted = clean_name(extracted_name)
    if not cleaned_extracted or len(cleaned_extracted) < 2:
        return None, 0.0
        
    best_match = None
    best_score = 0.0
    
    for teacher in database_teachers:
        cleaned_db = clean_name(teacher['name'])
        
        # 1. Exact match on cleaned names
        if cleaned_extracted == cleaned_db:
            return teacher, 1.0
            
        # 2. Token subset match
        extracted_tokens = set(cleaned_extracted.split())
        db_tokens = set(cleaned_db.split())
        if extracted_tokens and db_tokens:
            overlap = extracted_tokens.intersection(db_tokens)
            if overlap == extracted_tokens or overlap == db_tokens:
                # Calculate ratio based on overlapping tokens
                score = len(overlap) / max(len(extracted_tokens), len(db_tokens))
                score = 0.8 + 0.15 * score # boost token overlap
                if score > best_score:
                    best_score = score
                    best_match = teacher
                    
        # 3. Sequence comparison
        ratio = difflib.SequenceMatcher(None, cleaned_extracted, cleaned_db).ratio()
        if ratio > best_score:
            best_score = ratio
            best_match = teacher
            
    return best_match, best_score

def parse_time_range(text):
    """
    Parse a start and end time from a text block, e.g. '09:30 - 10:30' or 'Period 1'.
    Returns: (start_time, end_time, period_name)
    """
    text_lower = text.strip().lower()
    
    # Check for periods first
    for p_key, times in PERIOD_DEFAULT_TIMES.items():
        if p_key in text_lower:
            return times[0], times[1], p_key.title()
            
    # Try to find explicit times using Regex
    time_pattern = r'(\d{1,2})[:.](\d{2})\s*(am|pm)?'
    matches = list(re.finditer(time_pattern, text_lower))
    
    if len(matches) >= 2:
        m1, m2 = matches[0], matches[1]
        
        h1, m1_val = int(m1.group(1)), int(m1.group(2))
        ampm1 = m1.group(3)
        
        h2, m2_val = int(m2.group(1)), int(m2.group(2))
        ampm2 = m2.group(3)
        
        # Convert to 24h
        if ampm1 == 'pm' and h1 < 12:
            h1 += 12
        elif ampm1 == 'am' and h1 == 12:
            h1 = 0
            
        if ampm2 == 'pm' and h2 < 12:
            h2 += 12
        elif ampm2 == 'am' and h2 == 12:
            h2 = 0
            
        if not ampm1 and ampm2:
            if ampm2 == 'pm' and h1 < h2 and h2 >= 12:
                if h1 < 12 and (h2 - 12) > h1:
                    pass
                elif h1 < 12:
                    h1 += 12
                    
        start_t = datetime.time(h1, m1_val)
        end_t = datetime.time(h2, m2_val)
        
        # Infer period name based on timing
        period_name = "Custom Slot"
        for p_key, times in PERIOD_DEFAULT_TIMES.items():
            if abs((times[0].hour * 60 + times[0].minute) - (start_t.hour * 60 + start_t.minute)) < 15:
                period_name = p_key.title()
                break
        return start_t, end_t, period_name
        
    return datetime.time(9, 0), datetime.time(10, 0), "Period 1"

def parse_day(text):
    """Parse day string and return integer day of week (0=Mon, ..., 6=Sun)."""
    text_clean = re.sub(r'[^a-zA-Z]', '', text.strip().lower())
    for d_name, d_val in DAYS_MAP.items():
        if d_name in text_clean:
            return d_val
    return 0 # Default to Monday

def parse_cell_contents(cell_text, database_teachers):
    """
    Parse a grid cell's contents (e.g. 'DBMS\nRahul Sharma\nRoom 202')
    Returns: (subject, teacher_profile_id, teacher_name, classroom, confidence)
    """
    if not cell_text or not str(cell_text).strip():
        return None
        
    cell_text = str(cell_text).strip()
    
    # Split by newlines, dashes, slashes, or commas
    parts = [p.strip() for p in re.split(r'[\n\-\/,]', cell_text) if p.strip()]
    if not parts:
        return None
        
    teacher_id = None
    teacher_name = None
    classroom = "Room"
    subject = ""
    best_conf = 0.0
    
    room_pattern = r'(?i)\b(?:room|rm|lab|hall|class|r|lh|block)\b[- ]*\w+|\b(?:room|lab|lh)\w+|\b\d{3}\b'
    
    identified_teacher_idx = -1
    identified_room_idx = -1
    
    # First pass: identify teacher name and classroom
    for idx, part in enumerate(parts):
        # 1. Check if it's a teacher
        teacher, score = find_best_teacher_match(part, database_teachers)
        if score >= 0.6 and score > best_conf:
            best_conf = score
            teacher_id = teacher['id']
            teacher_name = teacher['name']
            identified_teacher_idx = idx
            
        # 2. Check if it's a room
        if identified_room_idx == -1 and re.search(room_pattern, part):
            classroom = part
            identified_room_idx = idx
            
    # Second pass: construct subject from remaining parts
    subject_parts = []
    for idx, part in enumerate(parts):
        if idx == identified_teacher_idx or idx == identified_room_idx:
            continue
        # Skip if it is just a duplicate or too short
        if len(part) >= 2:
            subject_parts.append(part)
            
    if subject_parts:
        subject = " - ".join(subject_parts)
    else:
        # Fallback: if we only had teacher/room, use the teacher name or a generic label
        subject = parts[0] if parts else "Academic Class"
        
    return {
        'subject': subject,
        'teacher_profile_id': teacher_id,
        'teacher_name': teacher_name or (parts[identified_teacher_idx] if identified_teacher_idx != -1 else "Unassigned"),
        'classroom': classroom,
        'confidence': best_conf
    }

def parse_pandas_dataframe(df, database_teachers):
    """
    Parse a DataFrame containing timetable data.
    Supports:
    1. Flat Table List format (columns: Day, Time/Period, Subject, Teacher, Room)
    2. Grid format (days as rows, periods as columns OR periods as rows, days as columns)
    """
    # Clean up empty rows/cols
    df = df.dropna(how='all').dropna(axis=1, how='all')
    if df.empty:
        return []
        
    # Standardize headers
    cols = [str(c).strip().lower() for c in df.columns]
    
    # Check if this is a flat list format
    day_col_idx = -1
    subject_col_idx = -1
    teacher_col_idx = -1
    room_col_idx = -1
    period_col_idx = -1
    start_time_col_idx = -1
    end_time_col_idx = -1
    
    for idx, col in enumerate(cols):
        if any(k in col for k in ['day', 'days']):
            day_col_idx = idx
        elif any(k in col for k in ['subject', 'course', 'paper', 'class name']):
            subject_col_idx = idx
        elif any(k in col for k in ['teacher', 'faculty', 'instructor', 'name', 'prof']):
            teacher_col_idx = idx
        elif any(k in col for k in ['room', 'classroom', 'location', 'rm']):
            room_col_idx = idx
        elif any(k in col for k in ['period', 'slot', 'session']):
            period_col_idx = idx
        elif 'start' in col:
            start_time_col_idx = idx
        elif 'end' in col:
            end_time_col_idx = idx
            
    # If we found at least day, subject, and teacher, parse it as a flat table
    if day_col_idx != -1 and subject_col_idx != -1 and teacher_col_idx != -1:
        entries = []
        for _, row in df.iterrows():
            row_vals = [str(val).strip() if pd.notna(val) else "" for val in row]
            
            day_str = row_vals[day_col_idx]
            sub_str = row_vals[subject_col_idx]
            teach_str = row_vals[teacher_col_idx]
            
            if not day_str or not sub_str:
                continue
                
            day_val = parse_day(day_str)
            
            room_str = row_vals[room_col_idx] if room_col_idx != -1 else "Room"
            
            # Times
            p_name = "Period 1"
            s_time = datetime.time(9, 0)
            e_time = datetime.time(10, 0)
            
            if start_time_col_idx != -1 and end_time_col_idx != -1:
                s_str = row_vals[start_time_col_idx]
                e_str = row_vals[end_time_col_idx]
                s_time, e_time, p_name = parse_time_range(f"{s_str} - {e_str}")
            elif period_col_idx != -1:
                p_str = row_vals[period_col_idx]
                s_time, e_time, p_name = parse_time_range(p_str)
                
            teacher_match, score = find_best_teacher_match(teach_str, database_teachers)
            
            entries.append({
                'day_of_week': day_val,
                'period': p_name,
                'subject': sub_str,
                'classroom': room_str,
                'start_time': s_time.strftime('%H:%M'),
                'end_time': e_time.strftime('%H:%M'),
                'teacher_profile_id': teacher_match['id'] if teacher_match else None,
                'teacher_name': teacher_match['name'] if teacher_match else teach_str,
                'confidence': score
            })
        return entries
        
    # Grid Format: check if first column contains Day names
    first_col_vals = [str(val).strip().lower() for val in df.iloc[:, 0]]
    days_in_first_col = sum(any(d in str(val) for d in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']) for val in first_col_vals)
    
    entries = []
    
    if days_in_first_col >= 2:
        # Rows = Days, Columns = Periods/Times
        # Header columns are times/periods
        headers = [str(c).strip() for c in df.columns]
        
        for row_idx, row in df.iterrows():
            row_vals = [str(val).strip() if pd.notna(val) else "" for val in row]
            day_str = row_vals[0]
            if not any(d in day_str.lower() for d in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']):
                continue
                
            day_val = parse_day(day_str)
            
            for col_idx in range(1, len(row_vals)):
                cell_val = row_vals[col_idx]
                if not cell_val:
                    continue
                    
                header_val = headers[col_idx]
                s_time, e_time, p_name = parse_time_range(header_val)
                
                parsed_cell = parse_cell_contents(cell_val, database_teachers)
                if parsed_cell:
                    entries.append({
                        'day_of_week': day_val,
                        'period': p_name,
                        'subject': parsed_cell['subject'],
                        'classroom': parsed_cell['classroom'],
                        'start_time': s_time.strftime('%H:%M'),
                        'end_time': e_time.strftime('%H:%M'),
                        'teacher_profile_id': parsed_cell['teacher_profile_id'],
                        'teacher_name': parsed_cell['teacher_name'],
                        'confidence': parsed_cell['confidence']
                    })
        return entries
        
    # Grid Format: Column headers are days, Row labels are periods/times
    days_in_headers = sum(any(d in str(col).lower() for d in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']) for col in df.columns)
    if days_in_headers >= 2:
        # Rows = Periods, Columns = Days
        headers = [str(c).strip() for c in df.columns]
        for row_idx, row in df.iterrows():
            row_vals = [str(val).strip() if pd.notna(val) else "" for val in row]
            time_str = row_vals[0] # first col is time
            s_time, e_time, p_name = parse_time_range(time_str)
            
            for col_idx in range(1, len(row_vals)):
                cell_val = row_vals[col_idx]
                if not cell_val:
                    continue
                    
                day_val = parse_day(headers[col_idx])
                
                parsed_cell = parse_cell_contents(cell_val, database_teachers)
                if parsed_cell:
                    entries.append({
                        'day_of_week': day_val,
                        'period': p_name,
                        'subject': parsed_cell['subject'],
                        'classroom': parsed_cell['classroom'],
                        'start_time': s_time.strftime('%H:%M'),
                        'end_time': e_time.strftime('%H:%M'),
                        'teacher_profile_id': parsed_cell['teacher_profile_id'],
                        'teacher_name': parsed_cell['teacher_name'],
                        'confidence': parsed_cell['confidence']
                    })
        return entries

    # Fallback: Just parse any cell that has a teacher name in it
    # We scan all cells
    for row_idx, row in df.iterrows():
        for col_idx, val in enumerate(row):
            val_str = str(val).strip()
            if not val_str or len(val_str) < 10:
                continue
            parsed_cell = parse_cell_contents(val_str, database_teachers)
            if parsed_cell and parsed_cell['teacher_profile_id']:
                # Guess a day and time based on row/col
                day_val = (row_idx % 5)
                s_time = datetime.time(9 + (col_idx % 6), 0)
                e_time = datetime.time(10 + (col_idx % 6), 0)
                entries.append({
                    'day_of_week': day_val,
                    'period': f"Period {col_idx}",
                    'subject': parsed_cell['subject'],
                    'classroom': parsed_cell['classroom'],
                    'start_time': s_time.strftime('%H:%M'),
                    'end_time': e_time.strftime('%H:%M'),
                    'teacher_profile_id': parsed_cell['teacher_profile_id'],
                    'teacher_name': parsed_cell['teacher_name'],
                    'confidence': parsed_cell['confidence']
                })
    return entries

def parse_timetable_file(file_path, file_extension, database_teachers):
    """
    Primary interface for parsing timetable files.
    Returns: a list of dictionaries with extracted slots:
    [
       {
          'day_of_week': int (0-6),
          'period': str,
          'subject': str,
          'classroom': str,
          'start_time': str ('HH:MM'),
          'end_time': str ('HH:MM'),
          'teacher_profile_id': int or None,
          'teacher_name': str,
          'confidence': float
       }
    ]
    """
    ext = file_extension.lower().replace('.', '')
    
    # 1. Parse Excel / CSV
    if ext in ['xlsx', 'xls', 'csv']:
        try:
            if ext == 'csv':
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)
            return parse_pandas_dataframe(df, database_teachers)
        except Exception as e:
            print(f"Excel/CSV parse error: {e}")
            return []
            
    # 2. Parse PDF
    elif ext == 'pdf':
        entries = []
        try:
            with pdfplumber.open(file_path) as pdf:
                # First try extracting tables from text-based PDF
                has_extracted_tables = False
                for page in pdf.pages:
                    tables = page.extract_tables()
                    if tables:
                        for table in tables:
                            # Convert list of lists to DataFrame
                            if not table or len(table) < 2:
                                continue
                            df = pd.DataFrame(table[1:], columns=table[0])
                            page_entries = parse_pandas_dataframe(df, database_teachers)
                            if page_entries:
                                entries.extend(page_entries)
                                has_extracted_tables = True
                                
                if has_extracted_tables and entries:
                    return entries
                    
                # If table extraction failed, try raw text matching (unstructured/OCR)
                print("Table extraction empty, falling back to text regex matching...")
                for page in pdf.pages:
                    text = page.extract_text()
                    if text and text.strip():
                        page_entries = parse_text_lines(text, database_teachers)
                        if page_entries:
                            entries.extend(page_entries)
                            
                if entries:
                    return entries
                    
                # Scanned PDF OCR Fallback
                print("No text extracted, falling back to Tesseract OCR...")
                for page in pdf.pages:
                    try:
                        # Render page to image
                        img = page.to_image(resolution=200).original
                        ocr_text = pytesseract.image_to_string(img)
                        if ocr_text and ocr_text.strip():
                            page_entries = parse_text_lines(ocr_text, database_teachers)
                            if page_entries:
                                entries.extend(page_entries)
                    except pytesseract.pytesseract.TesseractNotFoundError:
                        raise Exception("OCR failed: Tesseract-OCR engine is not installed or not in PATH on this server. Please upload a text-based PDF or an Excel/CSV file.")
                    except Exception as e:
                        print(f"Page OCR error: {e}")
                        
        except Exception as e:
            # Raise the exception so app.py can display the specific error (e.g. Tesseract missing)
            raise e
            
        return entries
        
    return []

def parse_text_lines(text, database_teachers):
    """
    Extract schedule lines from unstructured text (e.g., PDF lines or OCR text).
    Looks for day names, teacher names, and classrooms in proximity.
    """
    entries = []
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    current_day = 0 # Default Monday
    
    # Regexes for extracting details
    room_pattern = r'(?i)\b(?:room|rm|lab|hall|class|r|lh|block)\b[- ]*\w+|\b(?:room|lab|lh)\w+|\b\d{3}\b'
    time_pattern = r'(\d{1,2})[:.](\d{2})\s*(am|pm)?'
    
    for line in lines:
        line_lower = line.lower()
        
        # Track day of the week
        for day_name, day_val in DAYS_MAP.items():
            if day_name in line_lower and len(day_name) > 3: # avoid single character conflicts
                current_day = day_val
                break
                
        # Search for teacher names in this line
        matched_teacher = None
        teacher_score = 0.0
        matched_part = ""
        
        # Split line by spaces to find fuzzy matching chunks
        parts = [p.strip() for p in re.split(r'[,;\-\t]', line) if p.strip()]
        for part in parts:
            teacher, score = find_best_teacher_match(part, database_teachers)
            if score >= 0.7 and score > teacher_score:
                teacher_score = score
                matched_teacher = teacher
                matched_part = part
                
        if matched_teacher:
            # We found a teacher! Let's extract other details from this line or surrounding line
            # Classroom
            room_match = re.search(room_pattern, line)
            classroom = room_match.group(0) if room_match else "Room"
            
            # Times
            s_time, e_time, p_name = parse_time_range(line)
            
            # Subject: remove teacher name, room, and times from the line
            sub_clean = line
            if matched_part:
                sub_clean = sub_clean.replace(matched_part, "")
            if room_match:
                sub_clean = sub_clean.replace(room_match.group(0), "")
                
            # Remove time matching substrings
            sub_clean = re.sub(time_pattern, "", sub_clean)
            sub_clean = re.sub(r'(?i)\b(?:to|and|at|period\s*\d)\b', "", sub_clean)
            sub_clean = re.sub(r'[^a-zA-Z0-9\s:]', '', sub_clean)
            sub_clean = re.sub(r'\s+', ' ', sub_clean).strip()
            
            # Limit length of parsed subject
            subject = sub_clean if (sub_clean and len(sub_clean) > 2) else "Academic Class"
            if len(subject) > 60:
                subject = subject[:60] + "..."
                
            entries.append({
                'day_of_week': current_day,
                'period': p_name,
                'subject': subject,
                'classroom': classroom,
                'start_time': s_time.strftime('%H:%M'),
                'end_time': e_time.strftime('%H:%M'),
                'teacher_profile_id': matched_teacher['id'],
                'teacher_name': matched_teacher['name'],
                'confidence': teacher_score
            })
            
    return entries
