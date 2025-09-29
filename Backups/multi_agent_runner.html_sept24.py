import os
import requests
import json
import logging
import re
from datetime import datetime, timedelta
from typing import TypedDict, Annotated, Optional, Dict, List
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage
import operator
from dotenv import load_dotenv
import schedule
import time
import threading
import smtplib
import ssl
from email.message import EmailMessage

# Import our custom modules
from enhanced_rwi import calculate_rwi
from llm_prompts import format_runner_profile_prompt, get_llm_run_plan_summary

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Enhanced Risk Assessment Constants
OPTIMAL = 0
GOOD = 1
CAUTION = 2
HIGH_RISK = 3
DANGEROUS = 4

# --- Email Function ---
def send_email_notification(recipient_email: str, subject: str, body: str, is_html: bool = True) -> bool:
    """Sends an email using credentials from the .env file."""
    try:
        email_user = os.getenv("EMAIL_USER")
        email_password = os.getenv("EMAIL_PASSWORD")
        email_host = os.getenv("EMAIL_HOST", "smtp.gmail.com")
        email_port = int(os.getenv("EMAIL_PORT", 587))

        if not all([email_user, email_password]):
            raise ValueError("Email credentials not set in .env file.")

        msg = EmailMessage()
        if is_html:
            msg.set_content(body, subtype='html')
        else:
            msg.set_content(body)
            
        msg['Subject'] = subject
        msg['From'] = email_user
        msg['To'] = recipient_email

        context = ssl.create_default_context()
        with smtplib.SMTP(email_host, email_port) as server:
            server.starttls(context=context)
            server.login(email_user, email_password)
            server.send_message(msg)
        
        logger.info(f"Successfully sent email to {recipient_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {recipient_email}: {e}")
        return False

# --- Helper Functions ---

def generate_card_data(scored_data: List, city: str, form_data: dict) -> dict:
    """Generate structured data for mobile card interface."""
    if not scored_data:
        return {"error": f"No weather data available for {city}."}

    # Separate today and tomorrow data
    today_hours = [h for h in scored_data if h.get('Day') == 'today']
    tomorrow_hours = [h for h in scored_data if h.get('Day') == 'tomorrow']
    
    # Generate summary statistics
    all_scores = [h.get('raw_score', 0) for h in scored_data]
    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
    best_hours = len([s for s in all_scores if s >= 4.0])
    
    # Find best and worst times
    best_hour = max(scored_data, key=lambda x: x.get('raw_score', 0))
    worst_hour = min(scored_data, key=lambda x: x.get('raw_score', 0))
    
    # Calculate averages
    all_temps = [h.get('Temp') for h in scored_data if h.get('Temp') != 'N/A']
    avg_temp = sum(all_temps) / len(all_temps) if all_temps else 70
    
    # Get air quality (assuming first hour has representative AQI)
    aqi_category = scored_data[0].get('aqi_category', 'Unknown') if scored_data else 'Unknown'

    card_data = {
        'location': city,
        'date': datetime.now().strftime("%b %d, %Y"),
        
        'summary': {
            'best_hours': best_hours,
            'avg_score': round(avg_score, 1),
            'avg_temp': round(avg_temp),
            'air_quality': aqi_category,
            'best_time': {
                'time': best_hour.get('Hour', 'N/A'),
                'day': 'Today' if best_hour.get('Day') == 'today' else 'Tomorrow',
                'score': round(best_hour.get('raw_score', 0), 1),
                'temp': best_hour.get('Temp', 'N/A'),
                'reason': extract_main_reason(best_hour.get('running_recommendation', ''))
            },
            'worst_time': {
                'time': worst_hour.get('Hour', 'N/A'),
                'day': 'Today' if worst_hour.get('Day') == 'today' else 'Tomorrow',
                'score': round(worst_hour.get('raw_score', 0), 1),
                'temp': worst_hour.get('Temp', 'N/A'),
                'reason': extract_main_reason(worst_hour.get('running_recommendation', ''))
            }
        },
        
        'profile': generate_profile_card_data(form_data),
        
        'today': [format_hour_for_card(hour) for hour in today_hours[:6]],  # Limit to 6 hours
        'tomorrow': [format_hour_for_card(hour) for hour in tomorrow_hours[:6]],
        
        'details': {
            'heat_stress': calculate_heat_stress_summary(scored_data),
            'wind_patterns': calculate_wind_summary(scored_data),
            'precipitation': calculate_precip_summary(scored_data),
            'air_quality': {
                'aqi': extract_aqi_number(scored_data),
                'category': aqi_category,
                'restrictions': get_aqi_restrictions(aqi_category)
            }
        }
    }
    
    return card_data

def extract_main_reason(recommendation: str) -> str:
    """Extract the main reason from a recommendation string."""
    if ': ' in recommendation:
        parts = recommendation.split(': ', 1)
        if len(parts) > 1:
            # Get first bullet point or sentence
            first_reason = parts[1].split(' • ')[0].strip()
            return first_reason[:100] + '...' if len(first_reason) > 100 else first_reason
    return recommendation[:100] + '...' if len(recommendation) > 100 else recommendation

def format_hour_for_card(hour_data: dict) -> dict:
    """Format hour data for card display."""
    return {
        'time': hour_data.get('Hour', 'N/A'),
        'score': round(hour_data.get('raw_score', 0), 1),
        'score_text': get_score_text(hour_data.get('raw_score', 0)),
        'temp': hour_data.get('Temp', 'N/A'),
        'wind': hour_data.get('Wind', 'N/A'),
        'humidity': hour_data.get('Humidity', 'N/A'),
        'precip': hour_data.get('Precip', 'N/A'),
        'recommendation': extract_main_reason(hour_data.get('running_recommendation', '')),
        'heat_stress': hour_data.get('heat_stress_level', 'Unknown')
    }

def get_score_text(score: float) -> str:
    """Convert numeric score to text description."""
    if score >= 4.5:
        return "Perfect"
    elif score >= 4.0:
        return "Excellent" 
    elif score >= 3.5:
        return "Great"
    elif score >= 3.0:
        return "Good"
    elif score >= 2.0:
        return "Fair"
    else:
        return "Poor"

def generate_profile_card_data(form_data: dict) -> dict:
    """Generate profile card data from form data."""
    profile_data = {
        'has_profile': False,
        'plan': None,
        'week': None,
        'today_workout': None,
        'weekly_plan': [],
        'nutrition': None
    }
    
    # Check if any profile data exists
    profile_fields = ['first_name', 'age', 'run_plan', 'plan_period']
    has_profile_data = any(form_data.get(field, [''])[0] for field in profile_fields)
    
    if not has_profile_data:
        return profile_data
        
    profile_data['has_profile'] = True
    
    # Extract plan information
    run_plan = form_data.get('run_plan', [''])[0]
    plan_period = form_data.get('plan_period', [''])[0]
    
    if run_plan and plan_period:
        plan_names = {
            'daily_fitness': 'Daily Fitness Running',
            'fitness_goal': 'Fitness Goal Training', 
            'athletic_goal': 'Athletic Achievement Training'
        }
        
        profile_data['plan'] = plan_names.get(run_plan, run_plan)
        profile_data['week'] = plan_period.replace('week_', 'Week ')
        
        # Generate sample workout data (in real implementation, this would come from LLM)
        profile_data['today_workout'] = generate_sample_workout(run_plan, plan_period)
        profile_data['weekly_plan'] = generate_sample_weekly_plan(run_plan)
    
    # Add nutrition if requested
    show_nutrition = form_data.get('show_nutrition', [''])[0]
    if show_nutrition == 'yes':
        profile_data['nutrition'] = generate_sample_nutrition()
    
    return profile_data

def generate_sample_workout(plan_type: str, week: str) -> str:
    """Generate sample workout for today."""
    workouts = {
        'daily_fitness': "30-minute easy pace run",
        'fitness_goal': "4-mile tempo run", 
        'athletic_goal': "6-mile tempo run with 3x1mile intervals"
    }
    return workouts.get(plan_type, "Easy run")

def generate_sample_weekly_plan() -> list:
    """Generate sample weekly plan."""
    return [
        {'day': 'Mon', 'workout': 'Rest day', 'completed': True},
        {'day': 'Tue', 'workout': '4-mile easy run', 'completed': True},
        {'day': 'Wed', 'workout': '6-mile tempo', 'completed': False},
        {'day': 'Thu', 'workout': '3-mile recovery', 'completed': False},
        {'day': 'Fri', 'workout': 'Rest', 'completed': False},
        {'day': 'Sat', 'workout': '10-mile long run', 'completed': False},
        {'day': 'Sun', 'workout': 'Cross training', 'completed': False}
    ]

def generate_sample_nutrition() -> dict:
    """Generate sample nutrition guidance."""
    return {
        'pre_run': 'Banana + coffee (30min before)',
        'during': 'Water every 2 miles',
        'post_run': 'Protein shake within 30min'
    }

def calculate_heat_stress_summary(scored_data: List) -> dict:
    """Calculate heat stress summary."""
    all_temps = [h.get('Temp') for h in scored_data if h.get('Temp') != 'N/A']
    all_dewpoints = [h.get('dewpoint_fahrenheit') for h in scored_data if h.get('dewpoint_fahrenheit') != 'N/A']
    
    return {
        'peak_heat_index': f"{max(all_temps)}°F" if all_temps else "N/A",
        'dewpoint_range': f"{min(all_dewpoints)}°F - {max(all_dewpoints)}°F" if all_dewpoints else "N/A",
        'uv_index': "6 (High)"  # This would come from weather API in real implementation
    }

def calculate_wind_summary(scored_data: List) -> dict:
    """Calculate wind summary."""
    morning_winds = [h.get('Wind') for h in scored_data if h.get('HourNum', 24) < 12 and h.get('Wind') != 'N/A']
    afternoon_winds = [h.get('Wind') for h in scored_data if h.get('HourNum', 0) >= 12 and h.get('Wind') != 'N/A']
    
    morning_avg = sum(morning_winds) / len(morning_winds) if morning_winds else 0
    afternoon_avg = sum(afternoon_winds) / len(afternoon_winds) if afternoon_winds else 0
    
    return {
        'morning': f"{morning_avg:.0f} mph (favorable)" if morning_avg < 10 else f"{morning_avg:.0f} mph (strong)",
        'afternoon': f"{afternoon_avg:.0f} mph (variable)",
        'direction': "SW (tailwind on usual route)"  # This would come from weather API
    }

def calculate_precip_summary(scored_data: List) -> dict:
    """Calculate precipitation summary."""
    today_precip = max([h.get('Precip', 0) for h in scored_data if h.get('Day') == 'today'], default=0)
    tomorrow_precip = max([h.get('Precip', 0) for h in scored_data if h.get('Day') == 'tomorrow'], default=0)
    
    return {
        'today': f"{today_precip}% chance" + (" (2-4 PM)" if today_precip > 0 else ""),
        'tomorrow': f"{tomorrow_precip}% chance all day", 
        'type': "Scattered light showers" if max(today_precip, tomorrow_precip) > 0 else "No precipitation expected"
    }

def extract_aqi_number(scored_data: List) -> int:
    """Extract AQI number from scored data."""
    # This would extract from the actual AQI data
    # For now, return a sample value
    return 45

def get_aqi_restrictions(category: str) -> str:
    """Get AQI restrictions based on category."""
    restrictions = {
        'Good': 'No restrictions',
        'Moderate': 'Sensitive individuals may experience minor issues',
        'Unhealthy for Sensitive': 'Sensitive groups should limit outdoor activity',
        'Unhealthy': 'Everyone should limit outdoor activity',
        'Very Unhealthy': 'Avoid outdoor activity',
        'Hazardous': 'Emergency conditions - avoid all outdoor activity'
    }
    return restrictions.get(category, 'No information available')

def generate_mobile_card_html(card_data: dict) -> str:
    """Generate HTML for mobile card interface."""
    location = card_data.get('location', 'Unknown')
    date_str = card_data.get('date', '')
    summary = card_data.get('summary', {})
    
    # Generate the mobile HTML template with dynamic data
    html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Running Forecast Cards</title>
        <link rel="stylesheet" href="/static/mobile-cards.css">
    </head>
    <body>
        <div class="app-container">
            <div class="header">
                <h1>Running Forecast</h1>
                <div class="location-info">
                    <span>{location}</span>
                    <span>{date_str}</span>
                </div>
            </div>
            
            <div class="card-controls">
                <div class="section-selector">
                    <button class="section-btn active" data-section="summary">Summary</button>
                    {"<button class='section-btn' data-section='profile'>Profile</button>" if card_data.get('profile', {}).get('has_profile') else ""}
                    <button class="section-btn" data-section="today">Today</button>
                    <button class="section-btn" data-section="tomorrow">Tomorrow</button>
                    <button class="section-btn" data-section="details">Details</button>
                </div>
                <div class="sequence-controls">
                    <div class="sequence-info">Card <span id="current-card">1</span> of <span id="total-cards">5</span></div>
                    <button class="reorder-btn" onclick="openReorderModal()">Reorder</button>
                </div>
            </div>
            
            <div class="card-container" id="card-container">
                <!-- Cards will be dynamically inserted here -->
            </div>
            
            <div class="navigation">
                <button class="nav-btn" id="prev-btn" onclick="previousCard()">←</button>
                <button class="nav-btn" id="next-btn" onclick="nextCard()">→</button>
            </div>
        </div>
        
        <script>
            // Inject card data into JavaScript
            window.cardData = {json.dumps(card_data)};
            
            // Initialize the mobile card interface
            initializeMobileCards();
        </script>
        <script src="/static/mobile-cards.js"></script>
    </body>
    </html>
    """
    
    return html_template

def get_formatted_date_display() -> str:
    """Generate a dynamic date display for the current date."""
    now = datetime.now()
    formatted_date = now.strftime("%a, %b %d")
    
    date_display = f"""
    <div style="
        display: inline-block; 
        background: linear-gradient(135deg, #4CAF50, #2E7D32); 
        color: white; 
        padding: 8px 16px; 
        border-radius: 8px; 
        font-weight: bold; 
        font-size: 16px; 
        text-align: center; 
        margin-right: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    ">
        {formatted_date}
    </div>"""
    
    return date_display

def get_formatted_tomorrow_date_display() -> str:
    """Generate a dynamic date display for tomorrow's date."""
    tomorrow = datetime.now() + timedelta(days=1)
    formatted_date = tomorrow.strftime("%a, %b %d")
    
    date_display = f"""
    <div style="
        display: inline-block; 
        background: linear-gradient(135deg, #2196F3, #1565C0); 
        color: white; 
        padding: 8px 16px; 
        border-radius: 8px; 
        font-weight: bold; 
        font-size: 16px; 
        text-align: center; 
        margin-right: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    ">
        {formatted_date}
    </div>"""

    return date_display

def parse_weather_data(forecast_data: str) -> dict:
    """Parse weather forecast data from MCP server JSON output."""
    
    logger.info(f"Parsing forecast data, length: {len(forecast_data) if forecast_data else 0}")
    
    if not forecast_data or not forecast_data.strip():
        logger.info("Received empty forecast data")
        return {'today': [], 'tomorrow': []}
    
    forecast_data_stripped = forecast_data.strip()
    if forecast_data_stripped.startswith('{'):
        return parse_json_weather_data(forecast_data_stripped)
    else:
        logger.warning("Using pipe-delimited fallback")
        return parse_pipe_delimited_weather_data(forecast_data_stripped)

def parse_json_weather_data(forecast_data: str) -> dict:
    """Parse JSON weather data from the MCP server."""
    try:
        weather_json = json.loads(forecast_data)
        periods = weather_json.get('properties', {}).get('periods', [])
        
        if not periods:
            return {'today': [], 'tomorrow': []}
        
        today_data, tomorrow_data = [], []
        now = datetime.now()
        today_date, tomorrow_date = now.date(), now.date() + timedelta(days=1)
        
        for period in periods:
            try:
                day_category = period.get('day_category', '')
                parsed_hour = period.get('parsed_hour', 'N/A')
                
                if parsed_hour == 'N/A': 
                    continue
                
                hour_num = parsed_hour
                if hour_num == 0: 
                    formatted_hour = "12:00 AM"
                elif hour_num < 12: 
                    formatted_hour = f"{hour_num}:00 AM"
                elif hour_num == 12: 
                    formatted_hour = "12:00 PM"
                else: 
                    formatted_hour = f"{hour_num - 12}:00 PM"
                
                temp = period.get('temperature', 'N/A')
                wind_speed_str = str(period.get('wind_speed', '0 mph'))
                wind_match = re.search(r'(\d+)', wind_speed_str)
                wind = int(wind_match.group(1)) if wind_match else 0
                precip = period.get('precipitation', 0)
                humidity = period.get('humidity', 'N/A')
                forecast = period.get('forecast', 'N/A')
                dewpoint = period.get('dewpoint_fahrenheit', 'N/A')

                weather_entry = {
                    'Hour': formatted_hour, 
                    'HourNum': hour_num, 
                    'Temp': temp,
                    'Wind': wind, 
                    'Precip': precip, 
                    'Humidity': humidity,
                    'Forecast': forecast, 
                    'dewpoint_fahrenheit': dewpoint,
                    'solar_phase': period.get('solar_phase', 'unknown'),
                    'is_solar_time': period.get('is_solar_time', False),
                    'solar_score': period.get('solar_score', 'N/A'),
                    'day_category': day_category
                }
                
                if 'TODAY' in day_category.upper():
                    weather_entry['Day'] = 'today'
                    today_data.append(weather_entry)
                elif 'TOMORROW' in day_category.upper():
                    weather_entry['Day'] = 'tomorrow'
                    tomorrow_data.append(weather_entry)
                        
            except Exception as e:
                logger.warning(f"Error parsing period: {e}")
                continue
        
        today_data.sort(key=lambda x: x.get('HourNum', 0))
        tomorrow_data.sort(key=lambda x: x.get('HourNum', 0))
        
        return {'today': today_data, 'tomorrow': tomorrow_data}
        
    except Exception as e:
        logger.error(f"Error in parse_json_weather_data: {e}")
        return {'today': [], 'tomorrow': []}

def parse_pipe_delimited_weather_data(forecast_data: str) -> dict:
    """Fallback parser for pipe-delimited weather data."""
    weather_lines = [line.strip() for line in forecast_data.split('\n') if line.strip()]
    
    if not weather_lines:
        return {'today': [], 'tomorrow': []}
    
    data_lines = []
    for line in weather_lines:
        if '|' in line and re.search(r'\d+', line) and not line.startswith('+=') and not line.startswith('+--'):
            if not any(header in line.lower() for header in ['num', 'time', 'temp', 'wind', 'forecast', 'precip', 'humidity']):
                data_lines.append(line)
    
    today_data = []
    tomorrow_data = []
    
    for line_num, line in enumerate(data_lines):
        try:
            if '|' in line:
                parts = [part.strip() for part in line.split('|') if part.strip()]
                if len(parts) >= 8:
                    hour_str = parts[1]
                    temp_str = parts[2]
                    wind_str = parts[3]
                    forecast_str = parts[5] if len(parts) > 5 else "N/A"
                    precip_str = parts[6] if len(parts) > 6 else "N/A"
                    humidity_str = parts[7] if len(parts) > 7 else "N/A"
                    
                    # Extract hour number
                    hour_match = re.search(r'(\d{1,2})', hour_str)
                    if hour_match:
                        hour_num = int(hour_match.group(1))
                        if hour_num == 0:
                            formatted_hour = "12:00 AM"
                        elif hour_num < 12:
                            formatted_hour = f"{hour_num}:00 AM"
                        elif hour_num == 12:
                            formatted_hour = "12:00 PM"
                        else:
                            formatted_hour = f"{hour_num - 12}:00 PM"
                    else:
                        hour_num = "N/A"
                        formatted_hour = "N/A"
                    
                    # Extract numeric values
                    temp_numbers = re.findall(r'\d+', temp_str)
                    temp = int(temp_numbers[0]) if temp_numbers else "N/A"
                    
                    wind_numbers = re.findall(r'\d+', wind_str)
                    wind = int(wind_numbers[0]) if wind_numbers else "N/A"
                    
                    precip_numbers = re.findall(r'\d+', precip_str)
                    precip = int(precip_numbers[0]) if precip_numbers else "N/A"
                    
                    humidity_numbers = re.findall(r'\d+', humidity_str)
                    humidity = int(humidity_numbers[0]) if humidity_numbers else "N/A"
                    
                    forecast = forecast_str.strip() if forecast_str.strip() else "N/A"
                    
                    weather_entry = {
                        'Hour': formatted_hour,
                        'HourNum': hour_num,
                        'Temp': temp,
                        'Wind': wind,
                        'Precip': precip,
                        'Humidity': humidity,
                        'Forecast': forecast
                    }
                    
                    # Sequential assignment (first 24 hours = today, next 24 = tomorrow)
                    if line_num < 24:
                        weather_entry['Day'] = 'today'
                        today_data.append(weather_entry)
                    else:
                        weather_entry['Day'] = 'tomorrow'
                        tomorrow_data.append(weather_entry)
                        
        except (ValueError, IndexError) as e:
            logger.warning(f"Error parsing line {line_num}: {e}")
            continue
    
    today_data.sort(key=lambda x: x['HourNum'] if x['HourNum'] != "N/A" else 0)
    tomorrow_data.sort(key=lambda x: x['HourNum'] if x['HourNum'] != "N/A" else 0)
    
    return {'today': today_data, 'tomorrow': tomorrow_data}

def calculate_rwi_score(temperature, humidity, wind_speed, precipitation, forecast, dewpoint_fahrenheit, hour_data=None):
    """Calculate RWI using enhanced solar data when available."""
    try:
        # Parse inputs
        if isinstance(wind_speed, str):
            wind_match = re.search(r'(\d+)', str(wind_speed))
            wind_speed = int(wind_match.group(1)) if wind_match else 0
        
        temp = float(temperature) if temperature != "N/A" else 70
        humid = float(humidity) if humidity != "N/A" else 50
        wind = float(wind_speed) if wind_speed != "N/A" else 0
        precip = float(precipitation) if precipitation != "N/A" else 0
        dewpoint = float(dewpoint_fahrenheit) if dewpoint_fahrenheit != "N/A" else temp - 15
        
        # Use enhanced RWI calculation
        result = calculate_rwi(temp, humid, wind, precip, forecast, dewpoint)
        
        # Add solar enhancement if available
        if hour_data and 'solar_score' in hour_data:
            solar_score = float(hour_data['solar_score'])
            # Adjust the solar component in the result
            result['components']['solar_conditions'] = solar_score
            logger.info(f"Using enhanced solar score {solar_score} from server")
        
        return result
        
    except Exception as e:
        logger.warning(f"RWI calculation failed: {e}")
        return {
            'rwi_score': 3.0, 
            'rating': 3, 
            'heat_index': float(temperature) if temperature != "N/A" else 70.0,
            'components': {
                'thermal_comfort': 3.0, 
                'solar_conditions': 3.0, 
                'wind': 3.0, 
                'precipitation': 3.0, 
                'dewpoint_comfort': 3.0
            }
        }

def score_hour_with_scientific_approach(hour_data, aqi_value=None):
    """Enhanced scoring with solar-aware RWI integration."""
    # Extract basic weather data
    temp = hour_data.get('temperature', hour_data.get('Temp', 'N/A'))
    wind = hour_data.get('wind_speed', hour_data.get('Wind', 'N/A'))
    humidity = hour_data.get('humidity', hour_data.get('Humidity', 'N/A'))
    precip = hour_data.get('precipitation', hour_data.get('Precip', 'N/A'))
    dewpoint = hour_data.get('dewpoint_fahrenheit', 'N/A')
    forecast = str(hour_data.get('forecast', hour_data.get('Forecast', 'N/A')))
    
    # Parse wind speed
    if isinstance(wind, str) and wind != "N/A":
        wind_match = re.search(r'(\d+)', wind)
        wind = int(wind_match.group(1)) if wind_match else 0
    
    # Handle missing data
    if temp == "N/A": temp = 70
    if humidity == "N/A": humidity = 50
    if wind == "N/A": wind = 0
    if precip == "N/A": precip = 0
    if dewpoint == "N/A": dewpoint = temp - 15
    
    # Use RWI for scoring
    rwi_result = calculate_rwi_score(temp, humidity, wind, precip, forecast, dewpoint, hour_data)
    final_score = rwi_result['rating'] 
    raw_score = rwi_result['rwi_score'] 
    heat_index = rwi_result['heat_index']
    rwi_components = rwi_result['components']
    
    # Temperature safety overrides
    if temp >= 90:
        final_score = 1
        raw_score = 1.0
    elif temp >= 85:
        final_score = 2
        raw_score = 2.0
    
    # Enhanced heat stress calculation
    heat_stress_level = calculate_enhanced_heat_stress(temp, dewpoint, hour_data)
    
    # Generate recommendations
    recommendation = generate_solar_aware_recommendation(temp, dewpoint, wind, forecast, final_score, raw_score, hour_data)
    
    return {
        **hour_data,
        'raw_score': raw_score, 
        'score_100': final_score * 20,
        'final_score': final_score, 
        'heat_stress_level': heat_stress_level,
        'aqi_category': get_aqi_category(aqi_value),
        'running_recommendation': recommendation,
        'heat_index': heat_index,
        'rwi_components': rwi_components
    }

def calculate_enhanced_heat_stress(temp, dewpoint, hour_data):
    """Calculate heat stress considering solar phase."""
    if temp == "N/A" or dewpoint == "N/A":
        return "Unknown"
    
    solar_phase = hour_data.get('solar_phase', 'unknown')
    is_solar_time = hour_data.get('is_solar_time', None)
    
    # More accurate nighttime detection
    is_nighttime = (solar_phase == 'night') or (is_solar_time is False and solar_phase in ['civil_twilight_dawn', 'civil_twilight_dusk'])
    
    if is_nighttime:
        # Nighttime thresholds - higher since no solar load
        if temp <= 75 and dewpoint <= 68:
            return "Minimal"
        elif temp <= 80 and dewpoint <= 72:
            return "Low"
        elif temp <= 85 and dewpoint <= 75:
            return "Moderate"
        elif temp <= 90 and dewpoint <= 78:
            return "High"
        else:
            return "Extreme"
    else:
        # Daytime thresholds
        if dewpoint <= 55 and temp <= 70:
            return "Minimal"
        elif dewpoint <= 60 and temp <= 75:
            return "Low"
        elif dewpoint <= 65 and temp <= 80:
            return "Moderate"
        elif dewpoint <= 70 and temp <= 85:
            return "High"
        else:
            return "Extreme"

def generate_solar_aware_recommendation(temp, dewpoint, wind, forecast, final_score, raw_score, hour_data):
    """Generate recommendations using enhanced solar data."""
    recommendations = []
    
    # Temperature assessment
    if temp >= 90:
        recommendations.append("Dangerous heat conditions - avoid outdoor running")
    elif temp >= 85:
        recommendations.append("High heat stress - easy pace only with frequent breaks")
    elif temp >= 80:
        recommendations.append("Hot conditions - reduce intensity and increase hydration")
    elif temp >= 75:
        recommendations.append("Warm conditions requiring attention to hydration")
    elif temp >= 65:
        recommendations.append("Comfortable temperature for running")
    elif temp >= 50:
        recommendations.append("Cool but comfortable - allow extra warm-up time")
    elif temp >= 40:
        recommendations.append("Cold conditions - extend warm-up and dress in layers")
    else:
        recommendations.append("Very cold conditions - take precautions against frostbite")

    # Enhanced solar guidance
    solar_phase = hour_data.get('solar_phase', 'unknown')
    solar_explanation = hour_data.get('solar_explanation', '')
    is_solar_time = hour_data.get('is_solar_time', None)
    
    if solar_explanation:
        recommendations.append(solar_explanation)
    elif solar_phase == 'night':
        if 'clear' in forecast.lower():
            recommendations.append("Clear night skies aid natural cooling")
    elif solar_phase == 'daylight' and is_solar_time:
        if 'sunny' in forecast.lower() and temp > 70:
            recommendations.append("Direct sunlight increases effective temperature")
    
    # Humidity and wind
    if dewpoint >= 65:
        recommendations.append(f"High humidity (dewpoint {dewpoint}°F) affects cooling significantly")
    elif dewpoint >= 60:
        recommendations.append(f"Noticeable humidity (dewpoint {dewpoint}°F)")
    
    if wind == 0:
        recommendations.append("No wind reduces natural cooling effectiveness")
    elif wind <= 3:
        recommendations.append("Minimal wind - heat retention may increase during exercise")
    
    # Overall assessment header
    if final_score >= 4:
        if temp >= 75 or raw_score < 4.0:
            header = "Good Conditions"
        else:
            header = "Good to Excellent Conditions"
    elif final_score == 3:
        header = "Fair Conditions"
    else:
        header = "Challenging Conditions"

    rec_list = " • ".join(recommendations)
    return f"{header}: {rec_list}"

def get_aqi_category(aqi_value):
    """Get AQI health category."""
    if aqi_value is None or aqi_value == "N/A":
        return "Unknown"
    elif aqi_value <= 50:
        return "Good"
    elif aqi_value <= 100:
        return "Moderate"
    elif aqi_value <= 150:
        return "Unhealthy for Sensitive"
    elif aqi_value <= 200:
        return "Unhealthy"
    elif aqi_value <= 300:
        return "Very Unhealthy"
    else:
        return "Hazardous"

def render_hour_card(hour, day_color, day_bg):
    """Enhanced hour card rendering with raw score display."""
    final_score = hour['final_score']
    
    score_colors = {
        5: ("#4CAF50", "#E8F5E8"),
        4: ("#8BC34A", "#F1F8E9"),
        3: ("#FF9800", "#FFF3E0"),
        2: ("#FF5722", "#FFF3E0"),
        1: ("#F44336", "#FFEBEE")
    }
    score_color, score_bg = score_colors.get(final_score, score_colors[1])
    
    raw_score = hour.get('raw_score', 0.0)
    score_display = f"{raw_score:.2f}/5"

    weather_details = format_weather_line_with_na(hour)
    heat_stress = hour.get('heat_stress_level', 'Unknown')
    aqi_category = hour.get('aqi_category', 'Unknown')
    recommendation = hour.get('running_recommendation', 'No specific recommendation')
    
    # Solar information
    solar_info = ""
    if 'solar_phase' in hour:
        solar_phase = hour['solar_phase']
        solar_score = hour.get('solar_score', 'N/A')
        is_solar = hour.get('is_solar_time', False)
        
        phase_icons = {
            'night': '🌙',
            'civil_twilight_dawn': '🌅', 
            'daylight': '☀️',
            'civil_twilight_dusk': '🌆'
        }
        
        solar_icon = phase_icons.get(solar_phase, '🌤️')
        solar_status = "Solar" if is_solar else "Non-solar"
        
        solar_info = f"""
            <div style="margin-top: 8px; font-size: 14px; background: rgba(255,255,255,0.7); padding: 6px; border-radius: 6px;">
                {solar_icon} <strong>Solar:</strong> {solar_phase.replace('_', ' ').title()} ({solar_status}, score: {solar_score})
            </div>
        """
    
    # Dewpoint information
    dewpoint_info = ""
    if hour.get('dewpoint_fahrenheit', 'N/A') != 'N/A':
        dewpoint = hour['dewpoint_fahrenheit']
        if dewpoint <= 55:
            dewpoint_color = "#4CAF50"
            dewpoint_desc = "Comfortable"
        elif dewpoint <= 65:
            dewpoint_color = "#FF9800"
            dewpoint_desc = "Noticeable"
        else:
            dewpoint_color = "#F44336"
            dewpoint_desc = "Oppressive"
        
        dewpoint_info = f"""
            <div style="margin-top: 8px; font-size: 14px;">
                💧 <strong>Dew Point:</strong> <span style="color: {dewpoint_color}; font-weight: bold;">{dewpoint}°F ({dewpoint_desc})</span>
            </div>
        """
    
    heat_stress_colors = {
        'Minimal': '#4CAF50', 'Low': '#8BC34A', 'Moderate': '#FF9800',
        'High': '#FF5722', 'Extreme': '#F44336', 'Unknown': '#999'
    }
    heat_stress_color = heat_stress_colors.get(heat_stress, '#999')
    
    aqi_colors = {
        'Good': '#4CAF50', 'Moderate': '#FF9800', 'Unhealthy for Sensitive': '#FF5722',
        'Unhealthy': '#F44336', 'Very Unhealthy': '#9C27B0', 'Hazardous': '#7B1FA2', 'Unknown': '#999'
    }
    aqi_color = aqi_colors.get(aqi_category, '#999')
    
    return f"""
        <div style="background: {score_bg}; border: 2px solid {score_color}; border-radius: 12px; padding: 16px; margin: 12px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap;">
                <h3 style="margin: 0; font-size: 20px; color: #333; font-weight: bold;">⏰ {hour['Hour']}</h3>
                <div style="color: {score_color}; font-weight: bold; font-size: 18px; background: white; padding: 6px 12px; border-radius: 20px; border: 2px solid {score_color};">
                    {score_display}
                </div>
            </div>
            <div style="font-size: 15px; font-weight: bold; margin-bottom: 8px;">
                {weather_details}
            </div>
            {dewpoint_info}
            {solar_info}
            <div style="margin-top: 10px; display: flex; flex-wrap: wrap; gap: 10px; font-size: 13px;">
                <div style="background: {heat_stress_color}20; color: {heat_stress_color}; padding: 4px 8px; border-radius: 6px; font-weight: bold; border: 1px solid {heat_stress_color};">
                    🌡️ Heat Stress: {heat_stress}
                </div>
                <div style="background: {aqi_color}20; color: {aqi_color}; padding: 4px 8px; border-radius: 6px; font-weight: bold; border: 1px solid {aqi_color};">
                    🌬️ Air Quality: {aqi_category}
                </div>
            </div>
            <div style="margin-top: 12px; padding: 10px; background: rgba(255,255,255,0.7); border-radius: 8px; font-size: 14px; font-style: italic; color: #555;">
                💡 {recommendation}
            </div>
        </div>
    """

def format_weather_line_with_na(hour):
    """Format a weather line handling N/A values."""
    def format_value_with_na(value, unit="", na_display="N/A"):
        if value == "N/A":
            return f"<span style='color: #999; font-style: italic;'>{na_display}</span>"
        else:
            return f"<span style='font-weight: bold;'>{value}{unit}</span>"

    temp_display = format_value_with_na(hour['Temp'], "°F")
    wind_display = format_value_with_na(hour['Wind'], "mph")
    precip_display = format_value_with_na(hour['Precip'], "%")
    humidity_display = format_value_with_na(hour['Humidity'], "%")
    
    # Color coding for temperature
    if hour['Temp'] != "N/A":
        if hour['Temp'] >= 75:
            temp_context = f"🌡️ <span style='color: #FF6B35;'>{temp_display}</span>"
        elif hour['Temp'] <= 45:
            temp_context = f"❄️ <span style='color: #4FC3F7;'>{temp_display}</span>"
        else:
            temp_context = f"🌤️ <span style='color: #4CAF50;'>{temp_display}</span>"
    else:
        temp_context = f"🌡️ {temp_display}"
    
    # Color coding for wind
    if hour['Wind'] != "N/A":
        if hour['Wind'] > 15:
            wind_context = f"💨 <span style='color: #FF5722;'>{wind_display}</span>"
        elif hour['Wind'] <= 5:
            wind_context = f"🍃 <span style='color: #4CAF50;'>{wind_display}</span>"
        else:
            wind_context = f"💨 {wind_display}"
    else:
        wind_context = f"💨 {wind_display}"
    
    # Color coding for precipitation
    if hour['Precip'] != "N/A":
        if hour['Precip'] > 30:
            precip_context = f"🌧️ <span style='color: #2196F3;'>{precip_display}</span> rain"
        elif hour['Precip'] > 10:
            precip_context = f"☁️ <span style='color: #607D8B;'>{precip_display}</span> rain"
        elif hour['Precip'] > 0:
            precip_context = f"🌤️ <span style='color: #FFA726;'>{precip_display}</span> rain"
        else:
            # Check solar phase for appropriate icon
            if hour.get('solar_phase') == 'night':
                precip_context = f"🌙 <span style='color: #4CAF50;'>{precip_display}</span> rain"
            else:
                precip_context = f"☀️ <span style='color: #4CAF50;'>{precip_display}</span> rain"
    else:
        precip_context = f"🌧️ {precip_display} rain"
    
    # Color coding for humidity
    if hour['Humidity'] != "N/A":
        if hour['Humidity'] > 80:
            humidity_context = f"💧 <span style='color: #2196F3;'>{humidity_display}</span> humidity"
        elif hour['Humidity'] > 60:
            humidity_context = f"💧 <span style='color: #FF9800;'>{humidity_display}</span> humidity"
        else:
            humidity_context = f"💧 <span style='color: #4CAF50;'>{humidity_display}</span> humidity"
    else:
        humidity_context = f"💧 {humidity_display} humidity"
    
    return f"{temp_context} • {wind_context} • {precip_context} • {humidity_context}"

# --- Generation Functions ---

def generate_compact_html_analysis(scored_data: List, city: str) -> str:
    """Generate a compact HTML forecast with final styling."""
    if not scored_data:
        return f"<div style='color: red;'>No weather data available for {city}.</div>"

    # Header with global message
    header_line = f"<h2 style='color: #333; margin-bottom: 5px;'>Running Forecast for {city}</h2>"
    monitor_line = "<div style='font-weight: bold; color: #FF6600; margin-bottom: 20px;'>👉 Monitor your body's response and adjust as needed.</div>"
    html_parts = [header_line, monitor_line]
    
    for hour in scored_data:
        # Date logic and color selection
        clean_date_for_line = ""
        date_color = "#4169E1"  # Default/Today color
        try:
            day_category = hour.get('day_category', 'Date Unknown')
            if 'TOMORROW' in day_category.upper():
                date_color = "#9932CC"  # Tomorrow color

            date_part = day_category.split('-')[1]
            day_of_week = date_part.split(', ')[1][:3]
            month_day = date_part.split(', ')[0]
            clean_date_for_line = f"{day_of_week}, {month_day}"

        except (IndexError, AttributeError):
            clean_date_for_line = ""

        # Data extraction
        time_str = hour.get('Hour', 'N/A').replace(':00', '')
        temp = hour.get('Temp', 'N/A')
        dew_point = hour.get('dewpoint_fahrenheit', 'N/A')
        wind = hour.get('Wind', 'N/A')
        humidity = hour.get('Humidity', 'N/A')
        precip = hour.get('Precip', 'N/A')
        raw_score = hour.get('raw_score', 0.0)
        final_score = hour.get('final_score', 0)
        full_recommendation = hour.get('running_recommendation', 'No recommendation available.')
        forecast_str = hour.get('Forecast', '').lower()
        solar_phase = hour.get('solar_phase', 'daylight')

        # Weather icon logic
        weather_icon = '🌤️'
        if temp != 'N/A' and temp >= 90: 
            weather_icon = '🌡️'
        elif 'thunder' in forecast_str: 
            weather_icon = '⛈️'
        elif solar_phase == 'night': 
            weather_icon = '🌙'
        elif 'sunny' in forecast_str or 'clear' in forecast_str: 
            weather_icon = '☀️'
        elif 'partly' in forecast_str: 
            weather_icon = '🌤️'
        elif 'cloudy' in forecast_str: 
            weather_icon = '☁️'
        elif 'rain' in forecast_str: 
            weather_icon = '🌧️'
        
        # Color coding
        score_colors = {
            5: ("#4CAF50", "#E8F5E8"), 4: ("#8BC34A", "#F1F8E9"),
            3: ("#FF9800", "#FFF3E0"), 2: ("#FF5722", "#FFF3E0"),
            1: ("#F44336", "#FFEBEE"), 0: ("#9E9E9E", "#F5F5F5")
        }
        score_color, score_bg = score_colors.get(final_score, score_colors[0])
        
        # Score emoji logic
        if raw_score >= 4.5: 
            score_emoji = "🏃🏃🏃"
        elif raw_score >= 4.0: 
            score_emoji = "🏃🏃"
        elif raw_score >= 3.5: 
            score_emoji = "🏃"
        elif raw_score >= 3.0: 
            score_emoji = "🤔🏃"
        elif raw_score >= 2.0: 
            score_emoji = "🔶"
        else: 
            score_emoji = "🛑"

        # Status display
        if raw_score >= 4.5:
            status_display = "⭐ EXCELLENT"
        elif raw_score >= 4.0:
            status_display = "🌟 FAVORABLE"
        elif raw_score >= 3.5:
            status_display = "✨ PLEASANT"
        elif raw_score >= 3.0:
            status_display = "🧡 MODERATE"
        elif raw_score >= 2.0:
            status_display = "⛔ STRESSFUL"
        else:
            status_display = "🚫 UNSAFE"
        
        # Weather details
        score_display = f"{score_emoji} {raw_score:.2f}/5"
        weather_details = f"{weather_icon}{temp}°F | DewPt {dew_point}°F | 💨{wind}mph | 💧{humidity}% | 🌧️{precip}% | {status_display}"
        weather_line_html = (
            f"<div style='display: flex; justify-content: space-between; align-items: center; font-weight: bold;'>"
            f"  <span style='color: {date_color};'>{clean_date_for_line} . {time_str}</span>"
            f"  <span style='color: {score_color};'>{score_display}</span>"
            f"</div>"
            f"<div style='margin-top: 6px; color: #555; font-size: 0.9em;'>{weather_details}</div>"
        )

        # Recommendation formatting
        rec_points_html = ""
        if ": " in full_recommendation:
            parts = full_recommendation.split(": ", 1)
            rec_points = [f"<li>{point.strip()}</li>" for point in parts[1].split(" • ")]
            rec_points_html = f"<ul style='margin: 5px 0 0 20px; padding: 0;'>{''.join(rec_points)}</ul>"
        else:
            rec_points_html = f"<ul style='margin: 5px 0 0 20px; padding: 0;'><li>{full_recommendation}</li></ul>"
        recommendation_html = f"<div style='margin-top: 12px; font-size: 0.95em;'>{rec_points_html}</div>"

        # HTML block assembly
        hour_block = (
            f"<div style='background: {score_bg}; border-left: 5px solid {score_color}; border-radius: 8px; "
            f"padding: 12px; margin: 10px 0; font-family: Arial, sans-serif; font-size: 15px;'>"
            f"  {weather_line_html}"
            f"  {recommendation_html}"
            f"</div>"
        )
        html_parts.append(hour_block)

    return "".join(html_parts)

# --- Tools ---

@tool
def get_city_from_zipcode(zip_code: str) -> str:
    """Convert a 5-digit US zip code to 'City, State' format."""
    if not re.match(r'^\d{5}$', zip_code):
        return zip_code

    try:
        url = f"https://api.zippopotam.us/us/{zip_code}"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        place_name = data['places'][0]['place name']
        state_abbr = data['places'][0]['state abbreviation']
        city_state = f"{place_name}, {state_abbr}"
        logger.info(f"Converted zip code {zip_code} to '{city_state}'")
        return city_state
    except Exception as e:
        logger.warning(f"Failed to convert zip code {zip_code}: {e}")
        return zip_code

@tool
def get_weather_forecast_from_server(city: str, granularity: str = 'hourly') -> str:
    """Get weather forecast from the MCP server."""
    server_url = os.getenv("WEATHER_SERVER_URL", "http://localhost:8000/get_weather")
    payload = {"city": city, "granularity": granularity}
    headers = {"Content-Type": "application/json"}
    
    try:
        logger.info(f"Calling Weather Server for: {city} ({granularity})")
        response = requests.post(server_url, data=json.dumps(payload), headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        if "forecast" in result:
            return result["forecast"]
        else:
            return f"Weather data received but no forecast found for {city}"
            
    except requests.exceptions.Timeout:
        return f"Timeout error: Weather server took too long to respond for {city}"
    except requests.exceptions.ConnectionError:
        return f"Connection error: Could not connect to weather server for {city}"
    except requests.exceptions.RequestException as e:
        return f"Error contacting weather server for {city}: {e}"
    except json.JSONDecodeError:
        return f"Error: Invalid JSON response from weather server for {city}"

@tool
def get_air_quality_from_server(city: str) -> str:
    """Get Air Quality Index forecast from the server."""
    server_url = os.getenv("AQI_SERVER_URL", "http://localhost:8001/get_air_quality")
    payload = {"city": city}
    headers = {"Content-Type": "application/json"}
    
    try:
        logger.info(f"Calling Air Quality Server for: {city}")
        response = requests.post(server_url, data=json.dumps(payload), headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        if "forecast" in result:
            return result["forecast"]
        else:
            return f"Air quality data received but no forecast found for {city}"
            
    except requests.exceptions.Timeout:
        return f"Timeout error: Air quality server took too long to respond for {city}"
    except requests.exceptions.ConnectionError:
        return f"Connection error: Could not connect to air quality server for {city}"
    except requests.exceptions.RequestException as e:
        return f"Error contacting air quality server for {city}: {e}"
    except json.JSONDecodeError:
        return f"Error: Invalid JSON response from air quality server for {city}"

@tool
def schedule_daily_email_report(
    location: str,
    time_windows: dict,
    recipient_email: str,
    scheduled_time: str,
    start_date: str,
    end_date: str
) -> str:
    """Schedule a daily email report for a specific time and date range."""
    
    def job():
        # Date range check
        today = datetime.now().date()
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()

        if not (start_date_obj <= today <= end_date_obj):
            logger.info(f"Skipping scheduled job for {location}. Today ({today}) is outside the range {start_date} to {end_date}.")
            return
        
        logger.info(f"Running scheduled job for {location} (date range valid)")
        try:
            analysis_html = run_agent_workflow(
                form_data={
                    'location': [location],
                    'action': ['get_forecast'],
                    **{f'{window}_start': [times[0]] for window, times in time_windows.items()},
                    **{f'{window}_end': [times[1]] for window, times in time_windows.items()}
                }
            )
            subject = f"Your Daily Running Forecast for {location}"
            email_body = f"<!DOCTYPE html><html><body>{analysis_html.get('final_html', '')}</body></html>"
            send_email_notification(recipient_email, subject, email_body, is_html=True)
        except Exception as e:
            logger.error(f"Error in scheduled job: {e}")

    schedule.every().day.at(scheduled_time).do(job)
    return f"✅ Success! Daily report for '{location}' scheduled for {scheduled_time} from {start_date} to {end_date} to '{recipient_email}'."

# --- Main Workflow Function ---

def run_agent_workflow(form_data: dict) -> dict:
    """
    Main workflow that processes form data and generates running forecasts.
    Now aligned with web_ui.py expectations and handles new UI fields.
    """
    try:
        # Extract form data
        location = form_data.get('location', [''])[0]
        action = form_data.get('action', ['get_forecast'])[0]
        email = form_data.get('email', [''])[0]
        
        if not location:
            return {
                'final_html': '<div style="color: red;">Error: Location is required.</div>',
                'final_user_message': 'Please provide a location.'
            }

        # Convert location if it's a zip code
        city = get_city_from_zipcode.invoke({"zip_code": location})

        # Extract time windows
        time_windows = {}
        window_names = ['today_1', 'today_2', 'tomorrow_1', 'tomorrow_2']
        
        for window_name in window_names:
            start_key = f'{window_name}_start'
            end_key = f'{window_name}_end'
            start_time = form_data.get(start_key, [''])[0]
            end_time = form_data.get(end_key, [''])[0]
            
            if start_time and end_time:
                time_windows[window_name] = (start_time, end_time)

        if not time_windows:
            return {
                'final_html': '<div style="color: red;">Error: At least one time window is required.</div>',
                'final_user_message': 'Please select at least one time window.'
            }

        # Handle different actions
        if action == 'get_forecast':
            return handle_forecast_request(city, time_windows, form_data)
        elif action == 'email_now':
            return handle_email_now_request(city, time_windows, form_data, email)
        elif action == 'schedule':
            return handle_schedule_request(city, time_windows, form_data, email)
        else:
            return {
                'final_html': f'<div style="color: red;">Error: Unknown action "{action}".</div>',
                'final_user_message': 'Invalid action requested.'
            }

    except Exception as e:
        logger.error(f"Workflow error: {e}")
        return {
            'final_html': f'<div style="color: red;">Error: {str(e)}</div>',
            'final_user_message': f'An error occurred: {str(e)}'
        }

def handle_forecast_request(city: str, time_windows: dict, form_data: dict) -> dict:
    """Handle instant forecast request with enhanced profile processing."""
    try:
        # Fetch weather and air quality data
        weather_response = get_weather_forecast_from_server.invoke({"city": city, "granularity": "hourly"})
        aqi_data = get_air_quality_from_server.invoke({"city": city})
        
        # Parse weather data
        weather_data = parse_weather_data(weather_response)
        today_data = weather_data.get('today', [])
        tomorrow_data = weather_data.get('tomorrow', [])

        # Process time windows and score hours
        all_scored_hours = []
        seen_hours = set()

        def time_to_hour(time_str): 
            return int(time_str.split(':')[0])

        for window_key, times in time_windows.items():
            start_hour, end_hour = time_to_hour(times[0]), time_to_hour(times[1])
            data_source = today_data if 'today' in window_key else tomorrow_data
            
            filtered = [h for h in data_source if h['HourNum'] != "N/A" and start_hour <= h['HourNum'] <= end_hour]
            
            # Parse AQI
            today_aqi_match = re.search(r'\b(\d{1,3})\b', aqi_data)
            today_aqi = int(today_aqi_match.group(1)) if today_aqi_match else "N/A"

            scored = [score_hour_with_scientific_approach(h, aqi_value=today_aqi) for h in filtered]
            
            for hour in scored:
                hour_key = (hour.get('day_category'), hour.get('HourNum'))
                if hour_key not in seen_hours:
                    all_scored_hours.append(hour)
                    seen_hours.add(hour_key)

        # Sort and generate output
        if not all_scored_hours:
            return {
                'final_html': f"<div style='color: #F44336;'>No data available for the selected time windows in {city}.</div>",
                'final_user_message': f'No forecast data available for {city}.'
            }

        all_scored_hours.sort(key=lambda x: (x.get('day_category', 'z'), x.get('HourNum', 0)))
        
        # Generate runner profile HTML if profile data exists
        profile_html = ""
        if any(form_data.get(key, [''])[0] for key in ['first_name', 'age', 'run_plan']):
            try:
                runner_profile_prompt = format_runner_profile_prompt(form_data)
                profile_html = get_llm_run_plan_summary.invoke({"runner_profile_prompt": runner_profile_prompt})
                profile_html = f"""
                    <div style="margin: 20px 0; padding: 20px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #007bff;">
                        <h3 style="color: #007bff; margin-top: 0;">Your Personalized Running Plan</h3>
                        {profile_html}
                    </div>
                """
            except Exception as e:
                logger.error(f"Error generating runner profile: {e}")
                profile_html = ""

        forecast_html = generate_compact_html_analysis(all_scored_hours, city)
        
        return {
            'final_html': profile_html + forecast_html,
            'final_user_message': f'Forecast generated successfully for {city}.'
        }

    except Exception as e:
        logger.error(f"Error in forecast request: {e}")
        return {
            'final_html': f'<div style="color: red;">Error generating forecast: {str(e)}</div>',
            'final_user_message': f'Error generating forecast: {str(e)}'
        }

def handle_email_now_request(city: str, time_windows: dict, form_data: dict, email: str) -> dict:
    """Handle immediate email request."""
    if not email:
        return {
            'final_html': '<div style="color: red;">Error: Email address is required.</div>',
            'final_user_message': 'Please provide an email address.'
        }

    try:
        # Generate forecast
        forecast_result = handle_forecast_request(city, time_windows, form_data)
        
        if 'Error' in forecast_result['final_html']:
            return forecast_result

        # Send email
        subject = f"Your Running Forecast for {city}"
        email_body = f"<!DOCTYPE html><html><body>{forecast_result['final_html']}</body></html>"
        
        success = send_email_notification(email, subject, email_body, is_html=True)
        
        if success:
            return {
                'final_html': f'<div style="color: green; font-weight: bold;">✅ Email sent successfully to {email}!</div>' + forecast_result['final_html'],
                'final_user_message': f'Forecast emailed to {email} successfully.'
            }
        else:
            return {
                'final_html': f'<div style="color: red;">❌ Failed to send email to {email}.</div>' + forecast_result['final_html'],
                'final_user_message': f'Failed to send email to {email}.'
            }

    except Exception as e:
        logger.error(f"Error in email request: {e}")
        return {
            'final_html': f'<div style="color: red;">Error sending email: {str(e)}</div>',
            'final_user_message': f'Error sending email: {str(e)}'
        }

def handle_schedule_request(city: str, time_windows: dict, form_data: dict, email: str) -> dict:
    """Handle schedule request."""
    if not email:
        return {
            'final_html': '<div style="color: red;">Error: Email address is required for scheduling.</div>',
            'final_user_message': 'Please provide an email address for scheduling.'
        }

    try:
        scheduled_time = form_data.get('schedule_time', ['06:00'])[0]
        start_date = form_data.get('schedule_start_date', [''])[0]
        end_date = form_data.get('schedule_end_date', [''])[0]

        if not start_date or not end_date:
            return {
                'final_html': '<div style="color: red;">Error: Start and end dates are required for scheduling.</div>',
                'final_user_message': 'Please provide start and end dates for scheduling.'
            }

        # Schedule the job
        result_message = schedule_daily_email_report.invoke({
            "location": city,
            "time_windows": time_windows,
            "recipient_email": email,
            "scheduled_time": scheduled_time,
            "start_date": start_date,
            "end_date": end_date
        })

        return {
            'final_html': f'<div style="color: green; font-weight: bold;">{result_message}</div>',
            'final_user_message': result_message
        }

    except Exception as e:
        logger.error(f"Error in schedule request: {e}")
        return {
            'final_html': f'<div style="color: red;">Error scheduling email: {str(e)}</div>',
            'final_user_message': f'Error scheduling email: {str(e)}'
        }

# --- Scheduler Functions ---

def run_scheduler():
    """Run the email scheduler in a separate thread."""
    while True:
        schedule.run_pending()
        time.sleep(60)

def start_scheduler():
    """Start the email scheduler in background."""
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("Email scheduler started")

# --- Main Function ---

def main():
    """Main function for testing the system."""
    print("Running Forecast System Initialized")
    print("Available commands:")
    print("1. Get running forecast")
    print("2. Schedule daily emails")
    print("3. Type 'quit' to exit")
    
    start_scheduler()
    
    while True:
        try:
            user_input = input("\nEnter your query: ").strip()
            if user_input.lower() in ['quit', 'exit', 'q']:
                break
                
            if user_input:
                print("\nProcessing your request...\n")
                # Test with sample data
                result = run_agent_workflow({
                    'location': ['New York, NY'],
                    'action': ['get_forecast'],
                    'today_1_start': ['06:00'],
                    'today_1_end': ['10:00'],
                    'tomorrow_1_start': ['18:00'],
                    'tomorrow_1_end': ['22:00']
                })
                print("Result:")
                print("=" * 50)
                print(result.get('final_user_message', 'No message'))
                print("=" * 50)
            
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()