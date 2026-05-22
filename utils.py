import math
import os
import re
import base64
import urllib.request
from PIL import Image
import io
import numpy as np
import cv2
import datetime
from zoneinfo import ZoneInfo
from models import AttendanceLog

def get_local_now(timezone_name='Asia/Kolkata'):
    """
    Returns the current timezone-aware localized datetime.
    """
    return datetime.datetime.now(ZoneInfo(timezone_name))

# 1. GPS Distance Calculation (Haversine Formula)
def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great-circle distance between two points 
    on the Earth in meters.
    """
    R = 6371000.0  # Earth's radius in meters
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_phi / 2.0) ** 2) + \
        math.cos(phi1) * math.cos(phi2) * \
        (math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    
    return R * c

# 2. Image Compression and Storage Helper
def save_compressed_image(base64_data, upload_dir, filename):
    """
    Decodes base64 image data, compresses it to 75% quality JPEG, 
    and saves it to the static uploads directory.
    """
    os.makedirs(upload_dir, exist_ok=True)
    image_path = os.path.join(upload_dir, filename)
    
    # Strip headers if present in base64
    if ',' in base64_data:
        base64_data = base64_data.split(',')[1]
        
    img_data = base64.b64decode(base64_data)
    img = Image.open(io.BytesIO(img_data))
    
    # Convert RGBA to RGB if necessary
    if img.mode == 'RGBA':
        img = img.convert('RGB')
        
    # Resize if extremely large to save bandwidth and storage
    max_size = (1280, 720)
    img.thumbnail(max_size, Image.Resampling.LANCZOS)
    
    # Save as JPEG with 75% quality
    img.save(image_path, 'JPEG', quality=75)
    return image_path

# 3. Image Difference Hash (dHash) for Reuse Prevention
def calculate_dhash(image_path, hash_size=8):
    """
    Generates a 64-bit Difference Hash (dHash) of the image.
    This creates a 16-character hexadecimal string representing structural difference.
    """
    try:
        img = Image.open(image_path).convert('L')
        # Resize to (9 x 8) to compare horizontal differences
        img = img.resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
        pixels = np.array(img)
        
        # Compare adjacent columns
        diff = pixels[:, 1:] > pixels[:, :-1]
        
        # Convert boolean array to hex string
        diff_flat = diff.flatten()
        hash_val = 0
        for i, bit in enumerate(diff_flat):
            if bit:
                hash_val |= (1 << i)
        
        return f"{hash_val:016x}"
    except Exception as e:
        print(f"Error calculating image hash: {e}")
        return "0" * 16

def hamming_distance(hash1, hash2):
    """
    Calculate the Hamming distance between two hex hashes.
    A distance of 0 means identical structures; <= 2 means highly suspicious similarity.
    """
    h1 = int(hash1, 16)
    h2 = int(hash2, 16)
    return bin(h1 ^ h2).count('1')

def check_duplicate_image(new_hash, db_session, threshold=2):
    """
    Queries the database for existing image hashes and checks for duplicates.
    Returns (is_duplicate, matched_log_id)
    """
    if not new_hash or new_hash == "0" * 16:
        return False, None
        
    logs = db_session.query(AttendanceLog.id, AttendanceLog.image_hash).all()
    for log_id, old_hash in logs:
        dist = hamming_distance(new_hash, old_hash)
        if dist <= threshold:
            return True, log_id
            
    return False, None

# 4. Human Count Estimation (YOLOv8 ONNX + Haar Cascade Fallback)
YOLO_MODEL_URL = "https://github.com/andrey-yur/yolov8-opencv-cpp-python/raw/main/models/yolov8n.onnx"

def download_yolov8_model():
    """
    Downloads the 12MB YOLOv8n ONNX model if not locally cached.
    """
    model_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, 'yolov8n.onnx')
    
    if not os.path.exists(model_path):
        print(f"Downloading YOLOv8-nano ONNX weights from {YOLO_MODEL_URL}...")
        try:
            # Add headers to avoid bot blockers if any
            req = urllib.request.Request(
                YOLO_MODEL_URL, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req) as response, open(model_path, 'wb') as out_file:
                out_file.write(response.read())
            print("YOLOv8-nano weights cached successfully.")
        except Exception as e:
            print(f"YOLOv8 download failed: {e}. Haar Cascade fallback will be used.")
            if os.path.exists(model_path):
                os.remove(model_path)
            return None
            
    return model_path

def estimate_human_count(image_path):
    """
    Counts human/student presence in classroom image.
    Uses YOLOv8-nano via OpenCV DNN. If model or opencv loader fails, 
    falls back to Haar Cascade frontal faces + upper body detectors.
    Saves an overlay image with detected bounding boxes as `_detected.jpg`.
    """
    img = cv2.imread(image_path)
    if img is None:
        return 0
    
    h_orig, w_orig, _ = img.shape
    model_path = download_yolov8_model()
    
    # Try YOLOv8 first
    if model_path and os.path.exists(model_path):
        try:
            net = cv2.dnn.readNetFromONNX(model_path)
            
            # Prepare input blob (640x640, RGB, scale by 1/255.0)
            blob = cv2.dnn.blobFromImage(img, 1.0 / 255.0, (640, 640), swapRB=True, crop=False)
            net.setInput(blob)
            
            # Run inference
            outputs = net.forward() # shape: (1, 84, 8400)
            
            # Parse outputs
            predictions = np.squeeze(outputs).T # shape: (8400, 84)
            
            boxes = []
            confidences = []
            
            # Class ID 0 in COCO is "person"
            for pred in predictions:
                confidence = float(pred[4]) # Index 4 corresponds to class 0 (person)
                if confidence >= 0.40:
                    x_center, y_center, box_w, box_h = pred[0], pred[1], pred[2], pred[3]
                    
                    # Scale coordinates back to original image
                    x_min = int((x_center - box_w/2) * (w_orig / 640.0))
                    y_min = int((y_center - box_h/2) * (h_orig / 640.0))
                    bw = int(box_w * (w_orig / 640.0))
                    bh = int(box_h * (h_orig / 640.0))
                    
                    boxes.append([x_min, y_min, bw, bh])
                    confidences.append(confidence)
            
            # Apply Non-Maximum Suppression
            indices = cv2.dnn.NMSBoxes(boxes, confidences, score_threshold=0.40, nms_threshold=0.45)
            
            count = len(indices)
            
            # Draw detections
            overlay_img = img.copy()
            if count > 0:
                # NMSBoxes returns flat list of indices in some OpenCV versions, or nested arrays
                flat_indices = np.array(indices).flatten()
                for idx in flat_indices:
                    x, y, w, h = boxes[idx]
                    conf = confidences[idx]
                    # Draw neon green bounding box
                    cv2.rectangle(overlay_img, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    label = f"Student: {conf:.2f}"
                    cv2.putText(overlay_img, label, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            # Save overlays
            detected_path = image_path.replace('.jpg', '_detected.jpg')
            cv2.imwrite(detected_path, overlay_img)
            return count
            
        except Exception as e:
            print(f"YOLOv8 Inference error: {e}. Falling back to Haar Cascade.")
            
    # Fallback: Haar Cascade frontal face + upper body detection
    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Frontal Face Cascade
        face_cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        face_cascade = cv2.CascadeClassifier(face_cascade_path)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(35, 35))
        
        # Upper Body Cascade (useful if students are sitting and facing away or looking down)
        upper_body_cascade_path = cv2.data.haarcascades + 'haarcascade_upperbody.xml'
        upper_body_cascade = cv2.CascadeClassifier(upper_body_cascade_path)
        bodies = upper_body_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=2, minSize=(50, 50))
        
        # Build bounding boxes for visual overlay
        overlay_img = img.copy()
        for (x, y, w, h) in faces:
            cv2.rectangle(overlay_img, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(overlay_img, "Face", (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            
        for (x, y, w, h) in bodies:
            # Avoid duplicating boxes if face is already inside body
            cv2.rectangle(overlay_img, (x, y), (x + w, y + h), (255, 128, 0), 2)
            cv2.putText(overlay_img, "Upper Body", (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 128, 0), 1)
            
        detected_path = image_path.replace('.jpg', '_detected.jpg')
        cv2.imwrite(detected_path, overlay_img)
        
        # Estimate total students: we can approximate by taking maximum or combining with overlap checks.
        # Max of faces and upper bodies detected is a safe, simple approximation.
        count = max(len(faces), len(bodies))
        return count
        
    except Exception as e:
        print(f"Haar Cascade fallback error: {e}")
        # Return 0 if everything fails
        return 0
