// Main JavaScript Helpers for theme control, alerts, and navigation

document.addEventListener('DOMContentLoaded', () => {
    // 1. Theme Toggle Management
    const themeToggleBtn = document.getElementById('themeToggle');
    if (themeToggleBtn) {
        // Load initial theme
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
        updateThemeIcon(themeToggleBtn, savedTheme);
        
        themeToggleBtn.addEventListener('click', () => {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcon(themeToggleBtn, newTheme);
        });
    }
});

function updateThemeIcon(btn, theme) {
    if (theme === 'dark') {
        btn.innerHTML = '☀️'; // Sun icon for light option
        btn.title = 'Switch to Light Mode';
    } else {
        btn.innerHTML = '🌙'; // Moon icon for dark option
        btn.title = 'Switch to Dark Mode';
    }
}

// 2. Dynamic Banner Alerts Display
function showAlert(message, type = 'success') {
    // Remove existing alerts
    const existingAlerts = document.querySelectorAll('.alert-box');
    existingAlerts.forEach(el => el.remove());
    
    const container = document.querySelector('.app-container');
    if (!container) return;
    
    const alertBox = document.createElement('div');
    alertBox.className = `alert-box alert-${type === 'success' ? 'success' : 'danger'}`;
    
    const icon = type === 'success' ? '✅' : '❌';
    alertBox.innerHTML = `<span>${icon} &nbsp; ${message}</span>`;
    
    // Insert after header
    const header = document.querySelector('.app-header');
    if (header && header.nextSibling) {
        container.insertBefore(alertBox, header.nextSibling);
    } else {
        container.prepend(alertBox);
    }
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        alertBox.style.opacity = '0';
        alertBox.style.transition = 'opacity 0.5s ease';
        setTimeout(() => alertBox.remove(), 500);
    }, 5000);
}
