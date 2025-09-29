from flask import Flask, request, render_template_string, jsonify
import threading
from datetime import datetime, timedelta
import json
import os
# Updated import: Only the main workflow and scheduler functions are needed now.
from multi_agent_runner import run_agent_workflow, run_scheduler

app = Flask(__name__)

def get_current_and_future_hours():
    """Generate hours for dropdowns in AM/PM format."""
    now = datetime.now()
    today_hours = []
    for hour in range(now.hour, 24):
        time_val = f"{hour:02d}:00"
        dt = datetime.strptime(time_val, "%H:%M")
        display_text = f"{dt.strftime('%-I:%M %p')} (Today)"
        today_hours.append((time_val, display_text))

    tomorrow_hours = []
    for hour in range(0, 24):
        time_val = f"{hour:02d}:00"
        dt = datetime.strptime(time_val, "%H:%M")
        display_text = f"{dt.strftime('%-I:%M %p')} (Tomorrow)"
        tomorrow_hours.append((time_val, display_text))
        
    return today_hours, tomorrow_hours

# --- HTML Template with updated fields and layout ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Running Weather Advisor</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #f4f7f6; margin: 0; padding: 20px; color: #333; }
        .container { max-width: 800px; margin: 40px auto; background: #fff; padding: 30px; border-radius: 10px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
        h1 { color: #2c3e50; text-align: center; }
        h3 { margin-top: 30px; color: #34495e; border-bottom: 2px solid #ecf0f1; padding-bottom: 5px;}
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; font-weight: bold; color: #555; }
        input[type="text"], input[type="email"], input[type="number"], input[type="date"], select, textarea {
            width: 100%; padding: 12px; border-radius: 5px; border: 1px solid #ccc; box-sizing: border-box; font-size: 16px;
        }
        textarea { resize: vertical; }
        .button-group { display: flex; justify-content: space-between; gap: 15px; margin-top: 25px; }
        button {
            flex-grow: 1; background-color: #3498db; color: white; padding: 15px; border: none; border-radius: 5px;
            cursor: pointer; font-size: 16px; transition: background-color 0.3s;
        }
        button[name="action-email-now"] { background-color: #2ecc71; }
        button[name="action-schedule"] { background-color: #f39c12; }
        button:hover { opacity: 0.9; }
        details {
            border: 2px solid #3498db; border-radius: 8px; margin-bottom: 15px;
            background: #f8f9fa; overflow: hidden;
        }
        summary {
            font-weight: bold; font-size: 18px; padding: 15px; cursor: pointer;
            background-color: #f8f9fa; color: #3498db; outline: none;
        }
        details[open] > summary { border-bottom: 2px solid #3498db; }
        .window-content { padding: 20px; background: #fff; }
        .time-input-group, .schedule-options { display: flex; gap: 15px; align-items: center; }
        .schedule-options > div { flex-grow: 1; }
        .info-box { background: #e8f4fd; border: 1px solid #bee5eb; color: #0c5460; padding: 15px; margin: 15px 0; border-radius: 8px; }
        .info-box h4 { margin: 0 0 10px 0; color: #0a4b54; }
        .current-time { text-align: center; padding: 10px; background: #f8f9fa; border-radius: 5px; margin-bottom: 20px; color: #495057; font-weight: bold; font-size: 16px; }
        hr { border: 0; border-top: 1px solid #eee; margin: 30px 0; }
        .message { padding: 15px; margin-top: 25px; border-radius: 5px; text-align: center; font-weight: bold; background-color: #d1ecf1; color: #0c5460;}
        .form-row { display: flex; gap: 15px; }
        .form-row > .form-group { flex-grow: 1; width: 50%; }
        .form-row-3 { display: flex; gap: 15px; }
        .form-row-3 > .form-group { flex-grow: 1; width: 33.33%; }
        .checkbox-group label, .radio-group label { display: inline-block; margin-right: 15px; font-weight: normal; }
        .plan-options { display: flex; flex-wrap: wrap; gap: 15px; }
        .plan-options > .form-group { flex: 1; min-width: 200px; }
        .conditional-field { display: none; }
        
        /* Mobile View Toggle */
        .view-toggle { 
            text-align: center; 
            margin-bottom: 20px; 
            padding: 15px; 
            background: #e8f4fd; 
            border-radius: 8px; 
        }
        .view-toggle label { 
            display: inline-block; 
            margin-right: 15px; 
            font-weight: normal; 
            cursor: pointer;
        }
        .view-toggle input[type="radio"] { 
            margin-right: 5px; 
            width: auto; 
        }
        
        @media (max-width: 768px) {
            body { padding: 10px; }
            .container { margin: 10px auto; padding: 15px; }
            .button-group { flex-direction: column; }
            .form-row, .form-row-3 { flex-direction: column; }
            .time-input-group, .schedule-options { flex-direction: column; align-items: stretch; }
        }
    </style>
</head>
<body>
<div class="container">
    <h1>Running Weather Advisor</h1>
    <div id="current-time" class="current-time">Loading...</div>
    
    <div class="view-toggle">
        <h4>Choose Your View:</h4>
        <label><input type="radio" name="view_mode" value="desktop" checked> Desktop View (Full Details)</label>
        <label><input type="radio" name="view_mode" value="mobile"> Mobile Cards (Phone Optimized)</label>
    </div>
    
    <div class="info-box">
        <h4>How It Works:</h4>
        <p>Fill out your profile and select one or more future time windows. Choose between desktop view (comprehensive) or mobile cards (swipeable, phone-friendly).</p>
    </div>
    
    <form method="post" id="forecast-form">
        <!-- Hidden field to track view mode -->
        <input type="hidden" id="mobile_view" name="mobile_view" value="false">
        
        <details>
            <summary>Runner Profile (Optional)</summary>
            <div class="window-content">
                <div class="form-row">
                    <div class="form-group"><label for="first_name">First Name</label><input type="text" id="first_name" name="first_name"></div>
                    <div class="form-group"><label for="last_name">Last Name</label><input type="text" id="last_name" name="last_name"></div>
                </div>
                <div class="form-row-3">
    <div class="form-group">
        <label for="age">Age</label>
        <select id="age" name="age">
            <option value="">Select age...</option>
            {% for age in range(15, 76) %}
            <option value="{{ age }}">{{ age }}</option>
            {% endfor %}
        </select>
    </div>
    <div class="form-group">
        <label for="height">Height</label>
        <div style="display: flex; gap: 8px;">
            <select id="height_feet" name="height_feet" style="flex: 1;">
                <option value="">Feet</option>
                {% for ft in range(4, 8) %}
                <option value="{{ ft }}">{{ ft }} ft</option>
                {% endfor %}
            </select>
            <select id="height_inches" name="height_inches" style="flex: 1;">
                <option value="">Inches</option>
                {% for inch in range(0, 12) %}
                <option value="{{ inch }}">{{ inch }} in</option>
                {% endfor %}
            </select>
        </div>
    </div>
    <div class="form-group">
        <label for="weight">Weight (lbs)</label>
        <input type="number" id="weight" name="weight" min="80" max="400" placeholder="lbs">
    </div>
</div>
<div class="form-row">
    <div class="form-group"><label for="gender">Gender</label><select id="gender" name="gender"><option value="">Select...</option><option value="male">Male</option><option value="female">Female</option><option value="other">Other</option></select></div>
</div>
                # Find and replace the section after gender (around line 180):

<div class="form-group">
    <label for="mobility_restrictions">Mobility Restrictions</label>
    <div style="display: flex; gap: 8px; align-items: center;">
        <textarea id="mobility_restrictions" name="mobility_restrictions" rows="3" placeholder="Describe any mobility issues or physical limitations..." style="flex: 1;"></textarea>
        <button type="button" onclick="startVoiceInput('mobility_restrictions')" style="padding: 8px 12px; background: #2196F3; color: white; border: none; border-radius: 5px; cursor: pointer; height: fit-content;">
            🎤 Voice
        </button>
    </div>
</div>

<div class="form-group">
    <label for="health_conditions">Health Conditions</label>
    <div style="display: flex; gap: 8px; align-items: center;">
        <textarea id="health_conditions" name="health_conditions" rows="3" placeholder="E.g., No health concerns, Diabetes, Back pain, Asthma, Heart condition..."></textarea>
        <button type="button" onclick="startVoiceInput('health_conditions')" style="padding: 8px 12px; background: #2196F3; color: white; border: none; border-radius: 5px; cursor: pointer; height: fit-content;">
            🎤 Voice
        </button>
    </div>
</div>

<div class="form-group">
    <label for="dietary_restrictions">Dietary Restrictions</label>
    <div style="display: flex; gap: 8px; align-items: center;">
        <textarea id="dietary_restrictions" name="dietary_restrictions" rows="3" placeholder="E.g., Vegan, Gluten-free, Dairy-free, Nut allergies..."></textarea>
        <button type="button" onclick="startVoiceInput('dietary_restrictions')" style="padding: 8px 12px; background: #2196F3; color: white; border: none; border-radius: 5px; cursor: pointer; height: fit-content;">
            🎤 Voice
        </button>
    </div>
</div>

<div class="form-group">
    <label for="other_details">Other Relevant Details</label>
    <div style="display: flex; gap: 8px; align-items: center;">
        <textarea id="other_details" name="other_details" rows="3" placeholder="Any other information that would help personalize your training plan..."></textarea>
        <button type="button" onclick="startVoiceInput('other_details')" style="padding: 8px 12px; background: #2196F3; color: white; border: none; border-radius: 5px; cursor: pointer; height: fit-content;">
            🎤 Voice
        </button>
    </div>
</div>
                
                <!-- Updated Run Plan with Unified Plan Type -->
                <div class="form-row">
                    <div class="form-group">
                        <label for="run_plan">Run Plan</label>
                        <select id="run_plan" name="run_plan">
                            <option value="">Select a plan...</option>
                            <option value="daily_fitness">1. Daily fitness run</option>
                            <option value="fitness_goal">2. Run with Fitness Goal</option>
                            <option value="athletic_goal">3. Athletic achievement goal</option>
                        </select>
                    </div>
                    <div class="form-group" id="unified-plan-type-group" style="display:none;">
                        <label for="unified_plan_type">Plan Type</label>
                        <select id="unified_plan_type" name="unified_plan_type">
                            <option value="">Select type...</option>
                            <!-- Daily Fitness Options -->
                            <option value="individual_daily" data-parent="daily_fitness">Individual Daily Fitness</option>
                            <option value="group_daily" data-parent="daily_fitness">Group Daily Fitness (family/friends)</option>
                            <!-- Fitness Goal Options -->
                            <option value="starting_fitness" data-parent="fitness_goal">Just Starting - Build Base Fitness</option>
                            <option value="weight_loss_fitness" data-parent="fitness_goal">Weight Loss Focus</option>
                            <option value="endurance_fitness" data-parent="fitness_goal">Improve Endurance</option>
                            <!-- Athletic Goal Options -->
                            <option value="hm_300" data-parent="athletic_goal">3:00 Hr Half Marathon</option>
                            <option value="hm_230" data-parent="athletic_goal">2:30 Hr Half Marathon</option>
                            <option value="hm_200" data-parent="athletic_goal">2:00 Hr Half Marathon</option>
                            <option value="hm_130" data-parent="athletic_goal">1:30 Hr Half Marathon</option>
                            <option value="m_530" data-parent="athletic_goal">5:30 Hr Marathon</option>
                            <option value="m_500" data-parent="athletic_goal">5:00 Hr Marathon</option>
                            <option value="m_430" data-parent="athletic_goal">4:30 Hr Marathon</option>
                            <option value="m_400" data-parent="athletic_goal">4:00 Hr Marathon</option>
                        </select>
                    </div>
                </div>
                
                <!-- Plan Period and Plan Display Options on same row -->
                <div class="form-row">
                    <div class="form-group">
                        <label for="plan_period">Plan Period</label>
                        <select id="plan_period" name="plan_period">
                            <option value="">Select week...</option>
                            {% for i in range(1, 21) %}<option value="week_{{ i }}">Week {{ i }}</option>{% endfor %}
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="plan_display">Plan Display Options</label>
                        <select id="plan_display" name="plan_display">
                            <option value="full_plan">Show Full Plan</option>
                            <option value="one_day">Show 1 Day Plan at a Time</option>
                            <option value="this_week">Show This Week's Plan</option>
                        </select>
                    </div>
                </div>
                
                <!-- Conditional start date field -->
                <div class="form-group conditional-field" id="start-date-group">
                    <label for="plan_start_date">Plan Start Date</label>
                    <input type="date" id="plan_start_date" name="plan_start_date">
                </div>
                
                <!-- Updated nutrition/strength/mindfulness row -->
                <div class="form-row-3">
                    <div class="form-group">
                        <label for="show_nutrition">Include Nutrition Plan</label>
                        <select id="show_nutrition" name="show_nutrition">
                            <option value="no">No</option>
                            <option value="yes">Yes</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="strength_training">Add Strength Training</label>
                        <select id="strength_training" name="strength_training">
                            <option value="no">No</option>
                            <option value="yes">Yes</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="mindfulness_plan">Add Mindfulness Plan</label>
                        <select id="mindfulness_plan" name="mindfulness_plan">
                            <option value="no">No</option>
                            <option value="yes">Yes</option>
                        </select>
                    </div>
                </div>
                

                
                <!-- Updated Additional Details with enhanced placeholder -->
                <div class="form-group">
                    <label for="additional_details">Additional Details</label>
                    <textarea id="additional_details" name="additional_details" rows="8" placeholder="Specify dietary restrictions, other preferences, other health conditions, or anything else we should know to personalize your plan."></textarea>
                </div>
            </div>
        </details>
        <h3>Forecast Options</h3>
        <div class="form-group"><label for="location">City or Zip Code</label><input type="text" id="location" name="location" required placeholder="e.g., Boston, MA or 02101"></div>
        <h3>Today's Windows</h3>
        <details open><summary>My Availability Time Window 1 (Today)</summary><div class="window-content"><div class="time-input-group"><select name="today_1_start" class="start-time" data-day="today"><option value="">Start</option>{% for val, disp in today_hours %}<option value="{{ val }}">{{ disp }}</option>{% endfor %}</select><span>to</span><select name="today_1_end" class="end-time" data-day="today"><option value="">End</option>{% for val, disp in today_hours %}<option value="{{ val }}">{{ disp }}</option>{% endfor %}</select></div></div></details>
        <details><summary>My Availability Time Window 2 (Today)</summary><div class="window-content"><div class="time-input-group"><select name="today_2_start" class="start-time" data-day="today"><option value="">Start</option>{% for val, disp in today_hours %}<option value="{{ val }}">{{ disp }}</option>{% endfor %}</select><span>to</span><select name="today_2_end" class="end-time" data-day="today"><option value="">End</option>{% for val, disp in today_hours %}<option value="{{ val }}">{{ disp }}</option>{% endfor %}</select></div></div></details>
        <h3>Tomorrow's Windows</h3>
        <details><summary>My Availability Time Window 1 (Tomorrow)</summary><div class="window-content"><div class="time-input-group"><select name="tomorrow_1_start" class="start-time" data-day="tomorrow"><option value="">Start</option>{% for val, disp in tomorrow_hours %}<option value="{{ val }}">{{ disp }}</option>{% endfor %}</select><span>to</span><select name="tomorrow_1_end" class="end-time" data-day="tomorrow"><option value="">End</option>{% for val, disp in tomorrow_hours %}<option value="{{ val }}">{{ disp }}</option>{% endfor %}</select></div></div></details>
        <details><summary>My Availability Time Window 2 (Tomorrow)</summary><div class="window-content"><div class="time-input-group"><select name="tomorrow_2_start" class="start-time" data-day="tomorrow"><option value="">Start</option>{% for val, disp in tomorrow_hours %}<option value="{{ val }}">{{ disp }}</option>{% endfor %}</select><span>to</span><select name="tomorrow_2_end" class="end-time" data-day="tomorrow"><option value="">End</option>{% for val, disp in tomorrow_hours %}<option value="{{ val }}">{{ disp }}</option>{% endfor %}</select></div></div></details>
        <h3>Scheduling Options</h3>
        <div class="form-group"><label for="email">Your Email Address</label><input type="email" id="email" name="email" placeholder="Required for email actions"></div>
        <div class="schedule-options">
            <div><label for="schedule_time">Daily Email Time</label><select id="schedule_time" name="schedule_time">{% for hour in range(24) %}<option value="{{ '%02d:00'|format(hour) }}" {% if hour == 6 %}selected{% endif %}>{{ (datetime.strptime('%02d:00'|format(hour), '%H:%M')).strftime('%-I:%M %p') }}</option>{% endfor %}</select></div>
            <div><label for="schedule_start_date">Start Date</label><input type="date" id="schedule_start_date" name="schedule_start_date"></div>
            <div><label for="schedule_end_date">End Date</label><input type="date" id="schedule_end_date" name="schedule_end_date"></div>
        </div>
        <div class="button-group">
            <button type="submit" name="action" value="get_forecast">Generate Instant Plan</button>
            <button type="submit" name="action" value="email_now">Email Generated Plan Now</button>
            <button type="submit" name="action" value="schedule">Schedule Generated Plan Send Email</button>
        </div>
    </form>
    {% if message %}<div class="message">{{ message }}</div>{% endif %}
    {% if report_html %}<hr><div class="report-container">{{ report_html | safe }}</div>{% endif %}
</div>
<script>
    const allTodayHours = {{ today_hours|tojson }};
    const allTomorrowHours = {{ tomorrow_hours|tojson }};
    
    // Voice Input Functionality
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
                console.error('Speech recognition error:', event.error);
                alert('Voice input error: ' + event.error + '. Please try again or type manually.');
            };
            
            recognition.onend = function() {
                // Reset all voice buttons
                const buttons = document.querySelectorAll('button[data-voice-field]');
                buttons.forEach(btn => {
                    btn.textContent = '🎤 Voice';
                    btn.style.background = '#2196F3';
                });
                currentVoiceField = null;
            };
        } else {
            console.warn('Speech recognition not supported in this browser');
        }
    }
    
    function startVoiceInput(fieldId) {
        if (!recognition) {
            alert('Voice input is not supported in your browser. Please use Chrome, Edge, or Safari.');
            return;
        }
        
        // Get the button that was clicked
        const button = event.target;
        
        // If already recording this field, stop it
        if (currentVoiceField === fieldId) {
            recognition.stop();
            button.textContent = '🎤 Voice';
            button.style.background = '#2196F3';
            currentVoiceField = null;
            return;
        }
        
        // If recording another field, stop that first
        if (currentVoiceField) {
            recognition.stop();
        }
        
        // Start recording for new field
        currentVoiceField = fieldId;
        button.textContent = '⏹️ Stop';
        button.style.background = '#F44336';
        
        try {
            recognition.start();
        } catch (e) {
            console.error('Error starting recognition:', e);
            button.textContent = '🎤 Voice';
            button.style.background = '#2196F3';
            currentVoiceField = null;
            alert('Could not start voice input. Please try again.');
        }
    }
    
    function updateEndTimeOptions(startSelect) {
        const selectedStartTime = startSelect.value;
        const endSelect = startSelect.closest('.time-input-group').querySelector('.end-time');
        const hoursData = (startSelect.dataset.day === 'today') ? allTodayHours : allTomorrowHours;
        const currentEndValue = endSelect.value;
        endSelect.innerHTML = '<option value="">End</option>';
        if (selectedStartTime) {
            for (const [val, disp] of hoursData) { 
                if (val > selectedStartTime) { 
                    endSelect.add(new Option(disp, val)); 
                }
            }
        }
        if (endSelect.querySelector(`option[value="${currentEndValue}"]`)) { 
            endSelect.value = currentEndValue; 
        }
    }
    
    function updateCurrentTime() {
        const now = new Date();
        document.getElementById('current-time').innerHTML = `Current Time: ${now.toLocaleDateString()} ${now.toLocaleTimeString()}`;
    }
    
    function handleRunPlanChange() {
        const plan = document.getElementById('run_plan').value;
        const unifiedPlanTypeGroup = document.getElementById('unified-plan-type-group');
        const unifiedPlanTypeSelect = document.getElementById('unified_plan_type');
        
        if (plan) {
            unifiedPlanTypeGroup.style.display = 'block';
            
            // Filter options based on selected run plan
            const allOptions = unifiedPlanTypeSelect.querySelectorAll('option');
            allOptions.forEach(option => {
                if (option.value === '') {
                    option.style.display = 'block';
                } else {
                    const parent = option.getAttribute('data-parent');
                    option.style.display = (parent === plan) ? 'block' : 'none';
                }
            });
            
            unifiedPlanTypeSelect.value = '';
        } else {
            unifiedPlanTypeGroup.style.display = 'none';
            unifiedPlanTypeSelect.value = '';
        }
    }
    
    function handlePlanDisplayChange() {
        const planDisplay = document.getElementById('plan_display').value;
        const startDateGroup = document.getElementById('start-date-group');
        const planStartDate = document.getElementById('plan_start_date');
        
        if (planDisplay === 'one_day' || planDisplay === 'this_week') {
            startDateGroup.style.display = 'block';
            startDateGroup.classList.remove('conditional-field');
            planStartDate.required = true;
        } else {
            startDateGroup.style.display = 'none';
            startDateGroup.classList.add('conditional-field');
            planStartDate.required = false;
        }
    }
    
    function handleViewModeChange() {
        const mobileView = document.querySelector('input[name="view_mode"]:checked').value === 'mobile';
        document.getElementById('mobile_view').value = mobileView ? 'true' : 'false';
    }
    
    // Form submission handler
    document.getElementById('forecast-form').addEventListener('submit', function(event) {
        const action = document.activeElement.value;
        const emailInput = document.getElementById('email');
        const startDate = document.getElementById('schedule_start_date');
        const endDate = document.getElementById('schedule_end_date');
        const planDisplay = document.getElementById('plan_display').value;
        const planStartDate = document.getElementById('plan_start_date');
        
        emailInput.required = (action === 'email_now' || action === 'schedule');
        startDate.required = (action === 'schedule');
        endDate.required = (action === 'schedule');
        
        handleViewModeChange();
        
        if ((planDisplay === 'one_day' || planDisplay === 'this_week') && !planStartDate.value) {
            alert('Error: Start date is required for the selected plan display option.');
            event.preventDefault(); 
            return;
        }
        
        if (action === 'schedule' && startDate.value && endDate.value && startDate.value > endDate.value) {
            alert('Error: Schedule end date cannot be before the start date.');
            event.preventDefault(); 
            return;
        }
        
        const windows = [
            ['today_1_start', 'today_1_end'],
            ['today_2_start', 'today_2_end'],
            ['tomorrow_1_start', 'tomorrow_1_end'],
            ['tomorrow_2_start', 'tomorrow_2_end']
        ];
        
        let hasOneWindow = false;
        for (const [startId, endId] of windows) {
            const start = document.querySelector(`[name="${startId}"]`).value;
            const end = document.querySelector(`[name="${endId}"]`).value;
            if (start && end) {
                hasOneWindow = true;
                if (start >= end) {
                    alert('Error: End time must be after start time.');
                    event.preventDefault(); 
                    return;
                }
            } else if (start || end) {
                alert('Error: Please select both a start and end time for any window you use.');
                event.preventDefault(); 
                return;
            }
        }
        
        if (!hasOneWindow) {
            alert('Error: Please select a time for at least one window.');
            event.preventDefault();
        }
    });
    
    // Initialize everything when page loads
    window.onload = function() {
        updateCurrentTime();
        setInterval(updateCurrentTime, 1000);
        
        document.querySelectorAll('.start-time').forEach(select => { 
            select.addEventListener('change', () => updateEndTimeOptions(select)); 
        });
        
        document.getElementById('run_plan').addEventListener('change', handleRunPlanChange);
        document.getElementById('plan_display').addEventListener('change', handlePlanDisplayChange);
        
        document.querySelectorAll('input[name="view_mode"]').forEach(radio => {
            radio.addEventListener('change', handleViewModeChange);
        });
        
        const startDateInput = document.getElementById('schedule_start_date');
        const endDateInput = document.getElementById('schedule_end_date');
        const planStartDateInput = document.getElementById('plan_start_date');
        const today = new Date().toISOString().split('T')[0];
        
        startDateInput.min = today;
        endDateInput.min = today;
        planStartDateInput.min = today;
        
        startDateInput.addEventListener('change', () => {
            if (startDateInput.value) {
                endDateInput.min = startDateInput.value;
                if (endDateInput.value < startDateInput.value) { 
                    endDateInput.value = ''; 
                }
            }
        });
        
        // Initialize functions
        handlePlanDisplayChange();
        handleRunPlanChange();
        
        // Initialize voice recognition
        initVoiceRecognition();
    };
</script>
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    message = ""
    report_html = ""
    from datetime import datetime

    today_hours, tomorrow_hours = get_current_and_future_hours()
    
    if request.method == 'POST':
        # Collect all form data into a dictionary that the supervisor can use.
        form_data = request.form.to_dict(flat=False)
        
        # Process the unified plan type field
        unified_plan_type = request.form.get('unified_plan_type', '')
        if unified_plan_type:
            # Map unified plan type back to original fields for backward compatibility
            if unified_plan_type.endswith('_daily'):
                form_data['plan_type'] = ['individual' if 'individual' in unified_plan_type else 'group']
            elif unified_plan_type.endswith('_fitness'):
                form_data['fitness_goals'] = [unified_plan_type.replace('_fitness', '')]
            elif unified_plan_type.startswith(('hm_', 'm_')):
                form_data['athletic_goal'] = [unified_plan_type]
        else:
            form_data['fitness_goals'] = []
        
        # Add the button action to the form data so the supervisor knows what to do.
        form_data['action'] = [request.form.get('action')]

        try:
            # A single, simple call to the agent workflow.
            result = run_agent_workflow(form_data=form_data)
            report_html = result.get('final_html', '')
            message = result.get('final_user_message', '')

        except Exception as e:
            message = f"Error: {str(e)}"
    
    return render_template_string(
        HTML_TEMPLATE, message=message, report_html=report_html,
        today_hours=today_hours, tomorrow_hours=tomorrow_hours,
        datetime=datetime, range=range
    )

@app.route('/api/forecast', methods=['POST'])
def api_forecast():
    """API endpoint for getting forecast data in JSON format."""
    try:
        form_data = request.json
        # Convert single values to lists for compatibility
        for key, value in form_data.items():
            if not isinstance(value, list):
                form_data[key] = [value]
        
        result = run_agent_workflow(form_data=form_data)
        
        # Return JSON response with card data if available
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
            'message': f'Error generating forecast: {str(e)}'
        }), 500

@app.route('/mobile')
def mobile_view():
    """Dedicated mobile view route."""
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Running Forecast - Mobile</title>
        <style>
            body { margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
            .mobile-container { min-height: 100vh; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
            .coming-soon { 
                display: flex; 
                flex-direction: column; 
                justify-content: center; 
                align-items: center; 
                min-height: 100vh; 
                text-align: center; 
                padding: 20px; 
                color: white;
            }
                                  
        </style>
    </head>
    <body>
        <div class="mobile-container">
            <div class="coming-soon">
                <h1>Mobile Cards Interface</h1>
                <p>Use the main form and select "Mobile Cards" view mode to see the swipeable card interface.</p>
                <a href="/" style="color: white; text-decoration: underline;">← Back to Main Form</a>
            </div>
        </div>
    </body>
    </html>
    """)

if __name__ == '__main__':
    # Start the background scheduler thread when the web server starts.
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    app.run(debug=True, port=5000)



