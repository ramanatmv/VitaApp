from flask import Flask, request, render_template_string, jsonify
import threading
from datetime import datetime, timedelta
import json
import os
from multi_agent_runner import run_agent_workflow, run_scheduler

app = Flask(__name__)

def get_current_and_future_hours():
    """Generate hours for dropdowns in AM/PM format."""
    now = datetime.now()
    today_hours = []
    for hour in range(now.hour, 24):
        time_val = f"{hour:02d}:00"
        dt = datetime.strptime(time_val, "%H:%M")
        display_text = f"{dt.strftime('%-I:%M %p')}"
        today_hours.append((time_val, display_text))

    tomorrow_hours = []
    for hour in range(0, 24):
        time_val = f"{hour:02d}:00"
        dt = datetime.strptime(time_val, "%H:%M")
        display_text = f"{dt.strftime('%-I:%M %p')}"
        tomorrow_hours.append((time_val, display_text))
        
    return today_hours, tomorrow_hours

MOBILE_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="mobile-web-app-capable" content="yes">
    <title>Running Advisor - Mobile</title>
    <style>
        * { 
            box-sizing: border-box; 
            -webkit-tap-highlight-color: transparent;
        }
        
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0; 
            padding: 0;
            color: #333;
            min-height: 100vh;
        }
        
        .mobile-container {
            max-width: 100%;
            margin: 0;
            background: white;
            min-height: 100vh;
        }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px 15px;
            text-align: center;
            position: sticky;
            top: 0;
            z-index: 100;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
        }
        
        .header h1 {
            margin: 0;
            font-size: 22px;
            font-weight: 600;
        }
        
        .header .subtitle {
            font-size: 12px;
            opacity: 0.9;
            margin-top: 5px;
        }
        
        .form-container {
            padding: 15px;
        }
        
        .section-card {
            background: white;
            border-radius: 12px;
            padding: 15px;
            margin-bottom: 15px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 0;
            cursor: pointer;
            user-select: none;
        }
        
        .section-title {
            font-size: 16px;
            font-weight: 600;
            color: #667eea;
        }
        
        .section-icon {
            font-size: 20px;
            transition: transform 0.3s;
        }
        
        .section-icon.expanded {
            transform: rotate(180deg);
        }
        
        .section-content {
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease-out;
        }
        
        .section-content.expanded {
            max-height: 2000px;
            transition: max-height 0.5s ease-in;
        }
        
        .form-group {
            margin-bottom: 15px;
        }
        
        label {
            display: block;
            margin-bottom: 6px;
            font-weight: 500;
            font-size: 14px;
            color: #555;
        }
        
        input[type="text"], 
        input[type="email"], 
        input[type="number"], 
        input[type="date"], 
        select, 
        textarea {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        
        input:focus, select:focus, textarea:focus {
            outline: none;
            border-color: #667eea;
        }
        
        textarea {
            resize: vertical;
            min-height: 80px;
            font-family: inherit;
        }
        
        .input-with-voice {
            display: flex;
            gap: 8px;
            align-items: stretch;
        }
        
        .input-with-voice textarea {
            flex: 1;
        }
        
        .voice-btn {
            background: #2196F3;
            color: white;
            border: none;
            border-radius: 8px;
            padding: 12px;
            cursor: pointer;
            font-size: 20px;
            min-width: 50px;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .voice-btn:active {
            transform: scale(0.95);
        }
        
        .voice-btn.recording {
            background: #F44336;
            animation: pulse 1.5s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }
        
        .row-2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }
        
        .row-3 {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 10px;
        }
        
        .height-input {
            display: flex;
            gap: 8px;
        }
        
        .height-input select {
            flex: 1;
        }
        
        .time-window {
            background: #f8f9fa;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 10px;
        }
        
        .time-row {
            display: flex;
            gap: 8px;
            align-items: center;
            margin-top: 8px;
        }
        
        .time-row select {
            flex: 1;
        }
        
        .time-row span {
            font-size: 14px;
            color: #666;
        }
        
        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 10px;
            padding: 16px;
            font-size: 16px;
            font-weight: 600;
            width: 100%;
            cursor: pointer;
            margin-top: 10px;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        .btn-primary:active {
            transform: scale(0.98);
        }
        
        .btn-secondary {
            background: #4CAF50;
            color: white;
            border: none;
            border-radius: 10px;
            padding: 16px;
            font-size: 16px;
            font-weight: 600;
            width: 100%;
            cursor: pointer;
            margin-top: 10px;
        }
        
        .btn-tertiary {
            background: #FF9800;
            color: white;
            border: none;
            border-radius: 10px;
            padding: 16px;
            font-size: 16px;
            font-weight: 600;
            width: 100%;
            cursor: pointer;
            margin-top: 10px;
        }
        
        .info-box {
            background: #e3f2fd;
            border-left: 4px solid #2196F3;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 15px;
            font-size: 13px;
            line-height: 1.5;
        }
        
        .current-time {
            background: #f8f9fa;
            padding: 10px;
            border-radius: 8px;
            text-align: center;
            margin-bottom: 15px;
            font-size: 14px;
            color: #666;
        }
        
        .message {
            padding: 15px;
            margin: 15px;
            border-radius: 8px;
            text-align: center;
            font-weight: 500;
        }
        
        .message.success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        
        .message.error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        
        .loading {
            text-align: center;
            padding: 20px;
            display: none;
        }
        
        .loading.active {
            display: block;
        }
        
        .spinner {
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .result-container {
            padding: 15px;
        }
        
        /* Hide number input spinners for cleaner mobile look */
        input[type="number"]::-webkit-inner-spin-button,
        input[type="number"]::-webkit-outer-spin-button {
            -webkit-appearance: none;
            margin: 0;
        }
        
        input[type="number"] {
            -moz-appearance: textfield;
        }
    </style>
</head>
<body>
    <div class="mobile-container">
        <div class="header">
            <h1>🏃 Running Advisor</h1>
            <div class="subtitle">Personalized Weather & Training</div>
        </div>
        
        <div class="form-container">
            <div id="current-time" class="current-time">Loading...</div>
            
            <div class="info-box">
                📱 Tip: Use voice input for easier text entry. Tap 🎤 to speak.
            </div>
            
            <form method="post" id="forecast-form">
                <!-- Hidden field for mobile view -->
                <input type="hidden" name="mobile_view" value="true">
                
                <!-- Profile Section -->
                <div class="section-card">
                    <div class="section-header" onclick="toggleSection('profile')">
                        <span class="section-title">👤 Runner Profile</span>
                        <span class="section-icon" id="profile-icon">▼</span>
                    </div>
                    <div class="section-content" id="profile-content">
                        <div class="row-2">
                            <div class="form-group">
                                <label for="first_name">First Name</label>
                                <input type="text" id="first_name" name="first_name">
                            </div>
                            <div class="form-group">
                                <label for="last_name">Last Name</label>
                                <input type="text" id="last_name" name="last_name">
                            </div>
                        </div>
                        
                        <div class="row-3">
                            <div class="form-group">
                                <label for="age">Age</label>
                                <select id="age" name="age">
                                    <option value="">Age</option>
                                    {% for age in range(15, 76) %}
                                    <option value="{{ age }}">{{ age }}</option>
                                    {% endfor %}
                                </select>
                            </div>
                            <div class="form-group">
                                <label for="height">Height</label>
                                <div class="height-input">
                                    <select id="height_feet" name="height_feet">
                                        <option value="">Ft</option>
                                        {% for ft in range(4, 8) %}
                                        <option value="{{ ft }}">{{ ft }}'</option>
                                        {% endfor %}
                                    </select>
                                    <select id="height_inches" name="height_inches">
                                        <option value="">In</option>
                                        {% for inch in range(0, 12) %}
                                        <option value="{{ inch }}">{{ inch }}"</option>
                                        {% endfor %}
                                    </select>
                                </div>
                            </div>
                            <div class="form-group">
                                <label for="weight">Weight</label>
                                <input type="number" id="weight" name="weight" placeholder="lbs">
                            </div>
                        </div>
                        
                        <div class="form-group">
                            <label for="gender">Gender</label>
                            <select id="gender" name="gender">
                                <option value="">Select...</option>
                                <option value="male">Male</option>
                                <option value="female">Female</option>
                                <option value="other">Other</option>
                            </select>
                        </div>
                        
                        <div class="form-group">
                            <label for="mobility_restrictions">Mobility Restrictions</label>
                            <div class="input-with-voice">
                                <textarea id="mobility_restrictions" name="mobility_restrictions" placeholder="Any mobility issues..."></textarea>
                                <button type="button" class="voice-btn" onclick="startVoiceInput('mobility_restrictions')">🎤</button>
                            </div>
                        </div>
                        
                        <div class="form-group">
                            <label for="health_conditions">Health Conditions</label>
                            <div class="input-with-voice">
                                <textarea id="health_conditions" name="health_conditions" placeholder="Diabetes, asthma, etc..."></textarea>
                                <button type="button" class="voice-btn" onclick="startVoiceInput('health_conditions')">🎤</button>
                            </div>
                        </div>
                        
                        <div class="form-group">
                            <label for="dietary_restrictions">Dietary Restrictions</label>
                            <div class="input-with-voice">
                                <textarea id="dietary_restrictions" name="dietary_restrictions" placeholder="Vegan, gluten-free, etc..."></textarea>
                                <button type="button" class="voice-btn" onclick="startVoiceInput('dietary_restrictions')">🎤</button>
                            </div>
                        </div>
                        
                        <div class="form-group">
                            <label for="other_details">Other Details</label>
                            <div class="input-with-voice">
                                <textarea id="other_details" name="other_details" placeholder="Any other info..."></textarea>
                                <button type="button" class="voice-btn" onclick="startVoiceInput('other_details')">🎤</button>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Training Plan Section -->
                <div class="section-card">
                    <div class="section-header" onclick="toggleSection('training')">
                        <span class="section-title">🎯 Training Plan</span>
                        <span class="section-icon" id="training-icon">▼</span>
                    </div>
                    <div class="section-content" id="training-content">
                        <div class="form-group">
                            <label for="run_plan">Run Plan</label>
                            <select id="run_plan" name="run_plan">
                                <option value="">Select plan...</option>
                                <option value="daily_fitness">Daily Fitness</option>
                                <option value="fitness_goal">Fitness Goal</option>
                                <option value="athletic_goal">Athletic Goal</option>
                            </select>
                        </div>
                        
                        <div class="form-group" id="unified-plan-type-group" style="display:none;">
                            <label for="unified_plan_type">Plan Type</label>
                            <select id="unified_plan_type" name="unified_plan_type">
                                <option value="">Select type...</option>
                                <option value="individual_daily" data-parent="daily_fitness">Individual Daily</option>
                                <option value="group_daily" data-parent="daily_fitness">Group Daily</option>
                                <option value="starting_fitness" data-parent="fitness_goal">Build Base</option>
                                <option value="weight_loss_fitness" data-parent="fitness_goal">Weight Loss</option>
                                <option value="endurance_fitness" data-parent="fitness_goal">Endurance</option>
                                <option value="hm_300" data-parent="athletic_goal">HM 3:00</option>
                                <option value="hm_230" data-parent="athletic_goal">HM 2:30</option>
                                <option value="hm_200" data-parent="athletic_goal">HM 2:00</option>
                                <option value="hm_130" data-parent="athletic_goal">HM 1:30</option>
                                <option value="m_530" data-parent="athletic_goal">M 5:30</option>
                                <option value="m_500" data-parent="athletic_goal">M 5:00</option>
                                <option value="m_430" data-parent="athletic_goal">M 4:30</option>
                                <option value="m_400" data-parent="athletic_goal">M 4:00</option>
                            </select>
                        </div>
                        
                        <div class="row-2">
                            <div class="form-group">
                                <label for="plan_period">Week</label>
                                <select id="plan_period" name="plan_period">
                                    <option value="">Week...</option>
                                    {% for i in range(1, 21) %}
                                    <option value="week_{{ i }}">Week {{ i }}</option>
                                    {% endfor %}
                                </select>
                            </div>
                            <div class="form-group">
                                <label for="plan_display">Display</label>
                                <select id="plan_display" name="plan_display">
                                    <option value="full_plan">Full Plan</option>
                                    <option value="one_day">1 Day</option>
                                    <option value="this_week">This Week</option>
                                </select>
                            </div>
                        </div>
                        
                        <div class="row-3">
                            <div class="form-group">
                                <label for="show_nutrition">Nutrition</label>
                                <select id="show_nutrition" name="show_nutrition">
                                    <option value="no">No</option>
                                    <option value="yes">Yes</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label for="strength_training">Strength</label>
                                <select id="strength_training" name="strength_training">
                                    <option value="no">No</option>
                                    <option value="yes">Yes</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label for="mindfulness_plan">Mindfulness</label>
                                <select id="mindfulness_plan" name="mindfulness_plan">
                                    <option value="no">No</option>
                                    <option value="yes">Yes</option>
                                </select>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Location & Time Section -->
                <div class="section-card">
                    <div class="section-header" onclick="toggleSection('location')">
                        <span class="section-title">📍 Location & Time</span>
                        <span class="section-icon expanded" id="location-icon">▼</span>
                    </div>
                    <div class="section-content expanded" id="location-content">
                        <div class="form-group">
                            <label for="location">City or Zip Code</label>
                            <input type="text" id="location" name="location" required placeholder="e.g., Boston, MA">
                        </div>
                        
                        <label style="font-weight: 600; margin-bottom: 10px; display: block;">Today's Windows</label>
                        <div class="time-window">
                            <strong>Window 1</strong>
                            <div class="time-row">
                                <select name="today_1_start">
                                    <option value="">Start</option>
                                    {% for val, disp in today_hours %}<option value="{{ val }}">{{ disp }}</option>{% endfor %}
                                </select>
                                <span>to</span>
                                <select name="today_1_end">
                                    <option value="">End</option>
                                    {% for val, disp in today_hours %}<option value="{{ val }}">{{ disp }}</option>{% endfor %}
                                </select>
                            </div>
                        </div>
                        
                        <div class="time-window">
                            <strong>Window 2</strong>
                            <div class="time-row">
                                <select name="today_2_start">
                                    <option value="">Start</option>
                                    {% for val, disp in today_hours %}<option value="{{ val }}">{{ disp }}</option>{% endfor %}
                                </select>
                                <span>to</span>
                                <select name="today_2_end">
                                    <option value="">End</option>
                                    {% for val, disp in today_hours %}<option value="{{ val }}">{{ disp }}</option>{% endfor %}
                                </select>
                            </div>
                        </div>
                        
                        <label style="font-weight: 600; margin: 15px 0 10px; display: block;">Tomorrow's Windows</label>
                        <div class="time-window">
                            <strong>Window 1</strong>
                            <div class="time-row">
                                <select name="tomorrow_1_start">
                                    <option value="">Start</option>
                                    {% for val, disp in tomorrow_hours %}<option value="{{ val }}">{{ disp }}</option>{% endfor %}
                                </select>
                                <span>to</span>
                                <select name="tomorrow_1_end">
                                    <option value="">End</option>
                                    {% for val, disp in tomorrow_hours %}<option value="{{ val }}">{{ disp }}</option>{% endfor %}
                                </select>
                            </div>
                        </div>
                        
                        <div class="time-window">
                            <strong>Window 2</strong>
                            <div class="time-row">
                                <select name="tomorrow_2_start">
                                    <option value="">Start</option>
                                    {% for val, disp in tomorrow_hours %}<option value="{{ val }}">{{ disp }}</option>{% endfor %}
                                </select>
                                <span>to</span>
                                <select name="tomorrow_2_end">
                                    <option value="">End</option>
                                    {% for val, disp in tomorrow_hours %}<option value="{{ val }}">{{ disp }}</option>{% endfor %}
                                </select>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Email Options Section -->
                <div class="section-card">
                    <div class="section-header" onclick="toggleSection('email')">
                        <span class="section-title">📧 Email Options</span>
                        <span class="section-icon" id="email-icon">▼</span>
                    </div>
                    <div class="section-content" id="email-content">
                        <div class="form-group">
                            <label for="email">Email Address</label>
                            <input type="email" id="email" name="email" placeholder="your@email.com">
                        </div>
                        
                        <div class="form-group">
                            <label for="schedule_time">Daily Time</label>
                            <select id="schedule_time" name="schedule_time">
                                {% for hour in range(24) %}
                                <option value="{{ '%02d:00'|format(hour) }}" {% if hour == 6 %}selected{% endif %}>
                                    {{ (datetime.strptime('%02d:00'|format(hour), '%H:%M')).strftime('%-I:%M %p') }}
                                </option>
                                {% endfor %}
                            </select>
                        </div>
                        
                        <div class="row-2">
                            <div class="form-group">
                                <label for="schedule_start_date">Start Date</label>
                                <input type="date" id="schedule_start_date" name="schedule_start_date">
                            </div>
                            <div class="form-group">
                                <label for="schedule_end_date">End Date</label>
                                <input type="date" id="schedule_end_date" name="schedule_end_date">
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Action Buttons -->
                <button type="submit" name="action" value="get_forecast" class="btn-primary">
                    📊 Generate Forecast
                </button>
                <button type="submit" name="action" value="email_now" class="btn-secondary">
                    📧 Email Now
                </button>
                <button type="submit" name="action" value="schedule" class="btn-tertiary">
                    📅 Schedule Daily Email
                </button>
            </form>
            
            <div class="loading" id="loading">
                <div class="spinner"></div>
                <p style="margin-top: 15px; color: #667eea; font-weight: 500;">Processing your request...</p>
            </div>
            
            {% if message %}
            <div class="message {{ 'success' if 'success' in message.lower() else 'error' }}">
                {{ message }}
            </div>
            {% endif %}
        </div>
        
        {% if report_html %}
        <div class="result-container">
            {{ report_html | safe }}
        </div>
        {% endif %}
    </div>

    <script>
        // Current time display
        function updateCurrentTime() {
            const now = new Date();
            document.getElementById('current-time').textContent = 
                `📅 ${now.toLocaleDateString()} ${now.toLocaleTimeString()}`;
        }
        updateCurrentTime();
        setInterval(updateCurrentTime, 1000);
        
        // Section toggle
        function toggleSection(sectionId) {
            const content = document.getElementById(sectionId + '-content');
            const icon = document.getElementById(sectionId + '-icon');
            
            if (content.classList.contains('expanded')) {
                content.classList.remove('expanded');
                icon.classList.remove('expanded');
            } else {
                content.classList.add('expanded');
                icon.classList.add('expanded');
            }
        }
        
        // Voice Input
        let recognition = null;
        let currentVoiceField = null;
        
        function initVoiceRecognition() {
            if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
                const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
                recognition = new SpeechRecognition();
                recognition.continuous = false;
                recognition.interimResults = false;
                recognition.lang = 'en-US';
                
                recognition.onresult = function(event) {
                    const transcript = event.results[0][0].transcript;
                    if (currentVoiceField) {
                        const field = document.getElementById(currentVoiceField);
                        if (field) {
                            if (field.value.trim()) {
                                field.value += ' ' + transcript;
                            } else {
                                field.value = transcript;
                            }
                        }
                    }
                };
                
                recognition.onerror = function(event) {
                    alert('Voice error: ' + event.error);
                };
                
                recognition.onend = function() {
                    if (currentVoiceField) {
                        const button = document.querySelector(`button[onclick="startVoiceInput('${currentVoiceField}')"]`);
                        if (button) {
                            button.classList.remove('recording');
                        }
                    }
                    currentVoiceField = null;
                };
            }
        }
        
        function startVoiceInput(fieldId) {
            if (!recognition) {
                alert('Voice input not supported. Please use Chrome or Safari.');
                return;
            }
            
            const button = event.target;
            
            if (currentVoiceField === fieldId) {
                recognition.stop();
                button.classList.remove('recording');
                currentVoiceField = null;
                return;
            }
            
            if (currentVoiceField) {
                recognition.stop();
            }
            
            currentVoiceField = fieldId;
            button.classList.add('recording');
            
            try {
                recognition.start();
            } catch (e) {
                button.classList.remove('recording');
                currentVoiceField = null;
            }
        }
        
        // Run plan change handler
function handleRunPlanChange() {
    const plan = document.getElementById('run_plan').value;
    const group = document.getElementById('unified-plan-type-group');
    const select = document.getElementById('unified_plan_type');

    if (plan) {
        group.style.display = 'block';
        const options = select.querySelectorAll('option');

        // Iterate over options and display only those matching the selected plan
        options.forEach(opt => {
            // Always show the default empty option
            if (opt.value === '') {
                opt.style.display = 'block';
            } else {
                // Show/hide based on the data-parent attribute
                opt.style.display = opt.getAttribute('data-parent') === plan ? 'block' : 'none';
            }
        });
        select.value = '';
    } else { // <-- Corrected: Removed the extra closing brace before this line
        group.style.display = 'none';
        select.value = '';
    }
}
        
        document.getElementById('run_plan').addEventListener('change', handleRunPlanChange);
        
        // Form submission with loading indicator
        document.getElementById('forecast-form').addEventListener('submit', function(e) {
            const action = document.activeElement.value;
            const emailInput = document.getElementById('email');
            const startDate = document.getElementById('schedule_start_date');
            const endDate = document.getElementById('schedule_end_date');
            
            emailInput.required = (action === 'email_now' || action === 'schedule');
            startDate.required = (action === 'schedule');
            endDate.required = (action === 'schedule');
            
            // Validate time windows
            const windows = [
                ['today_1_start', 'today_1_end'],
                ['today_2_start', 'today_2_end'],
                ['tomorrow_1_start', 'tomorrow_1_end'],
                ['tomorrow_2_start', 'tomorrow_2_end']
            ];
            
            let hasWindow = false;
            for (const [startName, endName] of windows) {
                const start = document.querySelector(`[name="${startName}"]`).value;
                const end = document.querySelector(`[name="${endName}"]`).value;
                
                if (start && end) {
                    hasWindow = true;
                    if (start >= end) {
                        alert('End time must be after start time.');
                        e.preventDefault();
                        return;
                    }
                } else if (start || end) {
                    alert('Please select both start and end time for each window.');
                    e.preventDefault();
                    return;
                }
            }
            
            if (!hasWindow) {
                alert('Please select at least one time window.');
                e.preventDefault();
                return;
            }
            
            // Show loading indicator
            document.getElementById('loading').classList.add('active');
        });
        
        // Set min dates
        const today = new Date().toISOString().split('T')[0];
        document.getElementById('schedule_start_date').min = today;
        document.getElementById('schedule_end_date').min = today;
        
        document.getElementById('schedule_start_date').addEventListener('change', function() {
            if (this.value) {
                document.getElementById('schedule_end_date').min = this.value;
            }
        });
        
        // Initialize
        window.addEventListener('load', function() {
            initVoiceRecognition();
        });
    </script>
</body>
</html>
"""

@app.route('/mobile', methods=['GET', 'POST'])
def mobile_index():
    message = ""
    report_html = ""
    
    today_hours, tomorrow_hours = get_current_and_future_hours()
    
    if request.method == 'POST':
        form_data = request.form.to_dict(flat=False)
        
        # Process unified plan type
        unified_plan_type = request.form.get('unified_plan_type', '')
        if unified_plan_type:
            if unified_plan_type.endswith('_daily'):
                form_data['plan_type'] = ['individual' if 'individual' in unified_plan_type else 'group']
            elif unified_plan_type.endswith('_fitness'):
                form_data['fitness_goals'] = [unified_plan_type.replace('_fitness', '')]
            elif unified_plan_type.startswith(('hm_', 'm_')):
                form_data['athletic_goal'] = [unified_plan_type]
        
        form_data['action'] = [request.form.get('action')]
        
        try:
            result = run_agent_workflow(form_data=form_data)
            report_html = result.get('final_html', '')
            message = result.get('final_user_message', '')
        except Exception as e:
            message = f"Error: {str(e)}"
    
    return render_template_string(
        MOBILE_HTML_TEMPLATE,
        message=message,
        report_html=report_html,
        today_hours=today_hours,
        tomorrow_hours=tomorrow_hours,
        datetime=datetime,
        range=range
    )

@app.route('/api/mobile-forecast', methods=['POST'])
def api_mobile_forecast():
    """API endpoint for mobile forecast requests."""
    try:
        form_data = request.json
        for key, value in form_data.items():
            if not isinstance(value, list):
                form_data[key] = [value]
        
        result = run_agent_workflow(form_data=form_data)
        
        response = {
            'success': True,
            'message': result.get('final_user_message', ''),
            'html': result.get('final_html', ''),
            'is_mobile': result.get('is_mobile', False)
        }
        
        if 'card_data' in result:
            response['card_data'] = result['card_data']
        
        return jsonify(response)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'message': f'Error: {str(e)}'
        }), 500

# Redirect root to mobile
@app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Running Advisor</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                color: white;
                text-align: center;
                padding: 20px;
            }
            .container {
                max-width: 400px;
            }
            h1 { font-size: 32px; margin-bottom: 20px; }
            .btn {
                display: block;
                background: white;
                color: #667eea;
                text-decoration: none;
                padding: 15px 30px;
                border-radius: 10px;
                font-size: 18px;
                font-weight: 600;
                margin: 10px 0;
                transition: transform 0.2s;
            }
            .btn:hover { transform: scale(1.05); }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🏃 Running Advisor</h1>
            <p>Choose your interface:</p>
            <a href="/mobile" class="btn">📱 Mobile Version</a>
            <a href="http://localhost:5000" class="btn">💻 Desktop Version</a>
        </div>
    </body>
    </html>
    """

if __name__ == '__main__':
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    app.run(debug=True, port=5001, host='0.0.0.0')