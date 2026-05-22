// Classroom Camera and GPS tracking logic for Teacher Attendance

let cameraStream = null;
let userLatitude = null;
let userLongitude = null;
let mockLocationActive = false;

// Coordinates for Mock Locations
const CAMPUS_PRESETS = {
    inside: { lat: 27.475807921264003, lon: 94.55106863579525, name: "Classroom 202 (Inside campus: 0m)" },
    library: { lat: 27.475580, lon: 94.551250, name: "College Library (Inside campus: ~35m)" },
    outside: { lat: 27.468200, lon: 94.545800, name: "Dibrugarh Town (Outside campus: ~1050m)" }
};

document.addEventListener('DOMContentLoaded', () => {
    const video = document.getElementById('webcamStream');
    const canvas = document.getElementById('canvasPreview');
    const startCamBtn = document.getElementById('btnStartCamera');
    const submitBtn = document.getElementById('btnSubmitAttendance');
    const locationStatus = document.getElementById('locationStatus');
    
    // UI Elements for GPS Mocking (visible if DEBUG_MOCK_LOCATION is enabled in Flask config)
    const chkMock = document.getElementById('enableMockGPS');
    const mockOptions = document.getElementById('mockGPSSelector');
    
    if (chkMock) {
        chkMock.addEventListener('change', (e) => {
            mockLocationActive = e.target.checked;
            mockOptions.style.display = mockLocationActive ? 'block' : 'none';
            if (mockLocationActive) {
                applyMockPreset();
            } else {
                fetchRealLocation();
            }
        });
        
        // Listen to mock preset buttons
        document.querySelectorAll('.btn-mock-preset').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.btn-mock-preset').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                applyMockPreset(btn.dataset.preset);
            });
        });
    }

    // Initialize location acquisition
    if (locationStatus) {
        fetchRealLocation();
    }

    // Start Camera Stream
    if (startCamBtn && video) {
        startCamBtn.addEventListener('click', async () => {
            try {
                startCamBtn.disabled = true;
                startCamBtn.innerText = "Accessing camera...";
                
                // Request environment facing camera (rear camera on mobile devices)
                cameraStream = await navigator.mediaDevices.getUserMedia({
                    video: {
                        facingMode: { ideal: "environment" },
                        width: { ideal: 640 },
                        height: { ideal: 480 }
                    },
                    audio: false
                });
                
                video.srcObject = cameraStream;
                video.style.display = 'block';
                
                // Hide placeholder
                const placeholder = document.querySelector('.camera-placeholder');
                if (placeholder) placeholder.style.display = 'none';
                
                startCamBtn.style.display = 'none';
                if (submitBtn) submitBtn.disabled = false;
                
                showAlert("Live camera stream initialized successfully.", "success");
            } catch (err) {
                console.error("Camera access error:", err);
                startCamBtn.disabled = false;
                startCamBtn.innerText = "Try Accessing Camera Again";
                showAlert("Could not access camera. Please allow camera permissions.", "danger");
            }
        });
    }

    // Submit Attendance Trigger
    const attendanceForm = document.getElementById('attendanceMarkForm');
    const confirmModal = document.getElementById('confirmSubmitModal');
    const btnConfirmSubmit = document.getElementById('btnConfirmSubmit');
    const btnRetakePhoto = document.getElementById('btnRetakePhoto');
    const btnCancelSubmit = document.getElementById('btnCancelSubmit');
    const modalPreviewImg = document.getElementById('modalCapturePreview');

    if (attendanceForm) {
        attendanceForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            if (!cameraStream) {
                showAlert("Please initialize and open the camera first.", "danger");
                return;
            }
            if (userLatitude === null || userLongitude === null) {
                showAlert("GPS Location not acquired. Please wait or enable location services.", "danger");
                return;
            }
            
            // Draw current video frame to hidden canvas
            const ctx = canvas.getContext('2d');
            canvas.width = video.videoWidth || 640;
            canvas.height = video.videoHeight || 480;
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            
            // Extract Base64 JPEG data
            const base64Image = canvas.toDataURL('image/jpeg', 0.75);
            
            // Update preview image in modal
            if (modalPreviewImg) {
                modalPreviewImg.src = base64Image;
            }
            
            // Pause the video stream to freeze preview
            video.pause();
            
            // Open confirmation modal
            if (confirmModal) {
                confirmModal.classList.add('open');
            }
        });
    }

    if (btnConfirmSubmit) {
        btnConfirmSubmit.addEventListener('click', async () => {
            btnConfirmSubmit.disabled = true;
            btnConfirmSubmit.innerText = "Submitting...";
            if (btnRetakePhoto) btnRetakePhoto.disabled = true;
            if (btnCancelSubmit) btnCancelSubmit.disabled = true;
            
            const timetableId = document.getElementById('timetableId').value;
            const base64Image = canvas.toDataURL('image/jpeg', 0.75);
            
            const payload = {
                image: base64Image,
                latitude: userLatitude,
                longitude: userLongitude,
                timetable_id: timetableId
            };
            
            // Stop camera stream to release device hardware
            stopCamera();
            
            try {
                const response = await fetch('/api/submit_attendance', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(payload)
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    showAlert(data.message, "success");
                    if (confirmModal) confirmModal.classList.remove('open');
                    // Wait 2 seconds to let the user see the success alert and then redirect
                    setTimeout(() => {
                        window.location.href = '/teacher/dashboard';
                    }, 2000);
                } else {
                    showAlert(data.message + (data.reason ? ` Reason: ${data.reason}` : ''), "danger");
                    if (confirmModal) confirmModal.classList.remove('open');
                    resetMarkingForm();
                }
            } catch (err) {
                console.error("Submission failed:", err);
                showAlert("Network connection error. Failed to submit attendance.", "danger");
                if (confirmModal) confirmModal.classList.remove('open');
                resetMarkingForm();
            } finally {
                btnConfirmSubmit.disabled = false;
                btnConfirmSubmit.innerText = "Submit Attendance 🚀";
                if (btnRetakePhoto) btnRetakePhoto.disabled = false;
                if (btnCancelSubmit) btnCancelSubmit.disabled = false;
            }
        });
    }

    if (btnRetakePhoto) {
        btnRetakePhoto.addEventListener('click', () => {
            // Close modal
            if (confirmModal) {
                confirmModal.classList.remove('open');
            }
            // Resume live video stream
            if (video) {
                video.play().catch(err => console.error("Error resuming camera stream:", err));
            }
        });
    }

    if (btnCancelSubmit) {
        btnCancelSubmit.addEventListener('click', () => {
            // Close modal
            if (confirmModal) {
                confirmModal.classList.remove('open');
            }
            // Stop camera and reset the marking form
            stopCamera();
            resetMarkingForm();
        });
    }
});

function fetchRealLocation() {
    const locationStatus = document.getElementById('locationStatus');
    const submitBtn = document.getElementById('btnSubmitAttendance');
    
    if (mockLocationActive) return;
    
    if (!navigator.geolocation) {
        locationStatus.className = "status-indicator badge-rejected";
        locationStatus.innerHTML = "❌ Geolocation is not supported by your browser.";
        return;
    }
    
    locationStatus.className = "status-indicator badge-pending";
    locationStatus.innerHTML = "⌛ Querying GPS coordinates...";
    
    navigator.geolocation.getCurrentPosition(
        (position) => {
            if (mockLocationActive) return;
            userLatitude = position.coords.latitude;
            userLongitude = position.coords.longitude;
            
            locationStatus.className = "status-indicator badge-approved";
            locationStatus.innerHTML = `✅ GPS Locked: Lat ${userLatitude.toFixed(6)}, Lon ${userLongitude.toFixed(6)}`;
        },
        (error) => {
            if (mockLocationActive) return;
            console.error("GPS error:", error);
            locationStatus.className = "status-indicator badge-rejected";
            locationStatus.innerHTML = "❌ Failed to acquire GPS. Please allow location permissions.";
            showAlert("GPS coordinates required to mark attendance.", "danger");
        },
        { enableHighAccuracy: true, timeout: 10000 }
    );
}

function applyMockPreset(presetType = 'inside') {
    const coords = CAMPUS_PRESETS[presetType] || CAMPUS_PRESETS['inside'];
    userLatitude = coords.lat;
    userLongitude = coords.lon;
    
    const locationStatus = document.getElementById('locationStatus');
    if (locationStatus) {
        locationStatus.className = "status-indicator badge-approved";
        locationStatus.innerHTML = `⚠️ Mock GPS Active: ${coords.name} (Lat ${userLatitude.toFixed(6)}, Lon ${userLongitude.toFixed(6)})`;
    }
}

function stopCamera() {
    if (cameraStream) {
        cameraStream.getTracks().forEach(track => track.stop());
        cameraStream = null;
    }
}

function resetMarkingForm() {
    const startCamBtn = document.getElementById('btnStartCamera');
    const submitBtn = document.getElementById('btnSubmitAttendance');
    const video = document.getElementById('webcamStream');
    const placeholder = document.querySelector('.camera-placeholder');
    
    if (video) video.style.display = 'none';
    if (placeholder) placeholder.style.display = 'flex';
    if (startCamBtn) {
        startCamBtn.style.display = 'inline-flex';
        startCamBtn.disabled = false;
        startCamBtn.innerText = "Re-open Live Camera";
    }
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerText = "Submit Attendance";
    }
}
