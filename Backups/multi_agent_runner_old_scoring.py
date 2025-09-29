import os
import requests
import json
import pandas as pd
from io import StringIO
from typing import TypedDict, Annotated, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage, AIMessage
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
import operator
from dotenv import load_dotenv
import schedule
import time
import threading
import smtplib
import ssl
from email.message import EmailMessage
import re
from datetime import datetime, timedelta
import logging
import json
import datetime as dt
from datetime import timedelta

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# --- Reusable Email Function ---
def send_email_notification(recipient_email: str, subject: str, body: str, is_html: bool = True) -> bool:
    """Sends an email using credentials from the .env file."""
    try:
        email_user = os.getenv("EMAIL_USER")
        email_password = os.getenv("EMAIL_PASSWORD")
        email_host = os.getenv("EMAIL_HOST", "smtp.gmail.com")
        email_port = int(os.getenv("EMAIL_PORT", 587))

        if not all([email_user, email_password]):
            raise ValueError("Email credentials (EMAIL_USER, EMAIL_PASSWORD) are not set in the .env file.")

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

def get_formatted_date_display() -> str:
    """Generate a dynamic date display for the current date."""
    from datetime import datetime
    
    now = datetime.now()
    
    # Format: "Mon, Sep 22"
    formatted_date = now.strftime("%a, %b %d")
    
    # Create a styled date display that's more readable
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
    """Generate a dynamic date display for tomorrow's date (current + 1 day)."""
    from datetime import datetime, timedelta
    
    tomorrow = datetime.now() + timedelta(days=1)
    
    # Format: "Tue, Sep 23"
    formatted_date = tomorrow.strftime("%a, %b %d")
    
    # Create a styled date display that's more readable
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
    """Parse weather forecast data - FIXED to properly handle MCP server JSON output."""
    
    logger.info(f"DEBUG: Received forecast_data type: {type(forecast_data)}, length: {len(forecast_data) if forecast_data else 0}")
    
    if not forecast_data or not forecast_data.strip():
        logger.info("DEBUG: parse_weather_data received empty data")
        return {'today': [], 'tomorrow': []}
    
    # Check if this is JSON data (from MCP server)
    forecast_data_stripped = forecast_data.strip()
    if forecast_data_stripped.startswith('{'):
        logger.info("DEBUG: Using JSON parsing method")
        return parse_json_weather_data_corrected(forecast_data_stripped)
    else:
        # Fallback to pipe-delimited parsing
        logger.warning("DEBUG: Using pipe-delimited fallback - data quality may be reduced")
        return parse_pipe_delimited_weather_data(forecast_data_stripped)


def parse_json_weather_data_corrected(forecast_data: str) -> dict:
    """Parse JSON weather data using the MCP server's pre-processed structure."""
    try:
        import json
        import re
        from datetime import datetime, timezone, timedelta
        
        weather_json = json.loads(forecast_data)
        logger.info(f"DEBUG: Successfully parsed JSON weather data")
        
        # The MCP server returns data in this structure:
        # {"properties": {"periods": [{"day_category": "TODAY-Sep 22, Monday", "parsed_hour": 7, ...}]}}
        periods = weather_json.get('properties', {}).get('periods', [])
        
        if not periods:
            logger.info("DEBUG: No periods found in JSON data")
            return {'today': [], 'tomorrow': []}
        
        logger.info(f"DEBUG: Found {len(periods)} periods in JSON data")
        
        today_data = []
        tomorrow_data = []
        
        # Get current time for day categorization
        now = datetime.now()
        today_date = now.date()
        tomorrow_date = today_date + timedelta(days=1)
        
        for i, period in enumerate(periods):
            try:
                # Use the MCP server's pre-processed data
                day_category = period.get('day_category', '')
                parsed_hour = period.get('parsed_hour', 'N/A')
                
                # Skip if essential data is missing
                if parsed_hour == 'N/A':
                    logger.warning(f"DEBUG: Skipping period {i} - no parsed_hour")
                    continue
                
                # Format hour for display
                hour_num = parsed_hour
                if hour_num == 0:
                    formatted_hour = "12:00 AM"
                elif hour_num < 12:
                    formatted_hour = f"{hour_num}:00 AM"
                elif hour_num == 12:
                    formatted_hour = "12:00 PM"
                else:
                    formatted_hour = f"{hour_num - 12}:00 PM"
                
                # Extract weather data
                temp = period.get('temperature', 'N/A')
                
                # Extract wind speed number
                wind_speed_str = str(period.get('wind_speed', '0 mph'))
                wind_match = re.search(r'(\d+)', wind_speed_str)
                wind = int(wind_match.group(1)) if wind_match else 0
                
                # Get precipitation and humidity (already processed by MCP server)
                precip = period.get('precipitation', 0)
                precip = precip if precip is not None else 0
                
                humidity = period.get('humidity', 'N/A')
                
                # Get forecast description
                forecast = period.get('forecast', 'N/A')
                
                # Create weather entry
                weather_entry = {
                    'Hour': formatted_hour,
                    'HourNum': hour_num,
                    'Temp': temp,
                    'Wind': wind,
                    'Precip': precip,
                    'Humidity': humidity,
                    'Forecast': forecast
                }
                
                # Use MCP server's day categorization, but also fall back to time-based logic
                if day_category and 'TODAY' in day_category.upper():
                    weather_entry['Day'] = 'today'
                    today_data.append(weather_entry)
                    logger.info(f"DEBUG: Added to TODAY: {hour_num}:00 (category: {day_category})")
                elif day_category and 'TOMORROW' in day_category.upper():
                    weather_entry['Day'] = 'tomorrow'
                    tomorrow_data.append(weather_entry)
                    logger.info(f"DEBUG: Added to TOMORROW: {hour_num}:00 (category: {day_category})")
                else:
                    # Fallback: use raw_start_time to determine day
                    raw_start_time = period.get('raw_start_time', '')
                    if raw_start_time:
                        try:
                            dt = datetime.fromisoformat(raw_start_time.replace('Z', '+00:00'))
                            forecast_date = dt.date()
                            
                            if forecast_date == today_date:
                                weather_entry['Day'] = 'today'
                                today_data.append(weather_entry)
                                logger.info(f"DEBUG: Added to TODAY (fallback): {hour_num}:00")
                            elif forecast_date == tomorrow_date:
                                weather_entry['Day'] = 'tomorrow'
                                tomorrow_data.append(weather_entry)
                                logger.info(f"DEBUG: Added to TOMORROW (fallback): {hour_num}:00")
                            else:
                                logger.info(f"DEBUG: Skipping period beyond tomorrow: {forecast_date}")
                        except Exception as parse_error:
                            logger.warning(f"DEBUG: Could not parse raw_start_time {raw_start_time}: {parse_error}")
                    else:
                        logger.warning(f"DEBUG: No day category or raw_start_time for period {i}")
                        
            except Exception as e:
                logger.warning(f"Error parsing period {i}: {e}")
                continue
        
        # Sort data by hour number
        today_data.sort(key=lambda x: x['HourNum'] if x['HourNum'] != "N/A" else 0)
        tomorrow_data.sort(key=lambda x: x['HourNum'] if x['HourNum'] != "N/A" else 0)
        
        logger.info(f"DEBUG: JSON parsing returned {len(today_data)} today entries, {len(tomorrow_data)} tomorrow entries")
        
        # Log sample data for debugging
        if today_data:
            logger.info(f"DEBUG: First today entry: Hour={today_data[0]['Hour']}, Temp={today_data[0]['Temp']}, Wind={today_data[0]['Wind']}")
        if tomorrow_data:
            logger.info(f"DEBUG: First tomorrow entry: Hour={tomorrow_data[0]['Hour']}, Temp={tomorrow_data[0]['Temp']}, Wind={tomorrow_data[0]['Wind']}")
            
        return {'today': today_data, 'tomorrow': tomorrow_data}
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON weather data: {e}")
        return {'today': [], 'tomorrow': []}
    except Exception as e:
        logger.error(f"Error parsing JSON weather data: {e}")
        return {'today': [], 'tomorrow': []}

    
def parse_pipe_delimited_weather_data(forecast_data: str) -> dict:
    """Parse pipe-delimited weather data - fallback method only."""
    
    weather_lines = [line.strip() for line in forecast_data.split('\n') if line.strip()]
    
    if not weather_lines:
        logger.info("DEBUG: parse_pipe_delimited found no valid lines")
        return {'today': [], 'tomorrow': []}
    
    # Find data lines (skip headers and separators)
    data_lines = []
    for line in weather_lines:
        if '|' in line and re.search(r'\d+', line) and not line.startswith('+=') and not line.startswith('+--'):
            if not any(header in line.lower() for header in ['num', 'time', 'temp', 'wind', 'forecast', 'precip', 'humidity']):
                data_lines.append(line)
    
    logger.info(f"DEBUG: parse_pipe_delimited found {len(data_lines)} data lines")
    
    today_data = []
    tomorrow_data = []
    
    # FIXED: Sequential assignment instead of time-based logic
    for line_num, line in enumerate(data_lines):
        try:
            if '|' in line:
                parts = [part.strip() for part in line.split('|') if part.strip()]
                if len(parts) >= 8:
                    # Parse all the fields
                    hour_str = parts[1]  # Time column
                    temp_str = parts[2]   # Temperature column
                    wind_str = parts[3]   # Wind speed column
                    forecast_str = parts[5] if len(parts) > 5 else "N/A"  # Forecast column
                    precip_str = parts[6] if len(parts) > 6 else "N/A"    # Precipitation column
                    humidity_str = parts[7] if len(parts) > 7 else "N/A"  # Humidity column
                    
                    # Extract hour number
                    hour_match = re.search(r'(\d{1,2})', hour_str)
                    if hour_match:
                        hour_num = int(hour_match.group(1))
                        # Format hour with AM/PM
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
                        logger.warning(f"Could not parse hour from: {hour_str}")
                    
                    # Extract temperature
                    temp_numbers = re.findall(r'\d+', temp_str)
                    if temp_numbers:
                        temp = int(temp_numbers[0])
                    else:
                        temp = "N/A"
                        logger.warning(f"Could not parse temperature from: {temp_str}")
                    
                    # Extract wind
                    wind_numbers = re.findall(r'\d+', wind_str)
                    if wind_numbers:
                        wind = int(wind_numbers[0])
                    else:
                        wind = "N/A"
                        logger.warning(f"Could not parse wind from: {wind_str}")
                    
                    # Extract precipitation
                    precip_numbers = re.findall(r'\d+', precip_str)
                    if precip_numbers:
                        precip = int(precip_numbers[0])
                    else:
                        precip = "N/A"
                        logger.warning(f"Could not parse precipitation from: {precip_str}")
                    
                    # Extract humidity
                    humidity_numbers = re.findall(r'\d+', humidity_str)
                    if humidity_numbers:
                        humidity = int(humidity_numbers[0])
                    else:
                        humidity = "N/A"
                        logger.warning(f"Could not parse humidity from: {humidity_str}")
                    
                    forecast = forecast_str.strip() if forecast_str.strip() else "N/A"
                    
                    # Create weather entry
                    weather_entry = {
                        'Hour': formatted_hour,
                        'HourNum': hour_num,
                        'Temp': temp,
                        'Wind': wind,
                        'Precip': precip,
                        'Humidity': humidity,
                        'Forecast': forecast
                    }
                    
                    # FIXED: Sequential assignment (first 24 hours = today, next 24 = tomorrow)
                    if line_num < 24:
                        weather_entry['Day'] = 'today'
                        today_data.append(weather_entry)
                    else:
                        weather_entry['Day'] = 'tomorrow'
                        tomorrow_data.append(weather_entry)
                        
        except (ValueError, IndexError) as e:
            logger.warning(f"Error parsing pipe-delimited line {line_num}: {line} - {e}")
            continue
    
    # Sort data by hour number for consistent ordering
    today_data.sort(key=lambda x: x['HourNum'] if x['HourNum'] != "N/A" else 0)
    tomorrow_data.sort(key=lambda x: x['HourNum'] if x['HourNum'] != "N/A" else 0)
    
    logger.info(f"DEBUG: Pipe-delimited parsing returned {len(today_data)} today entries, {len(tomorrow_data)} tomorrow entries")
    return {'today': today_data, 'tomorrow': tomorrow_data}

def filter_weather_by_time_range(weather_data: list, start_hour: int, end_hour: int, spans_days: bool = False) -> list:
    """Filter weather data by hour range, handling cross-day scenarios."""
    filtered_data = []
    
    logger.info(f"DEBUG: Filtering weather data - start_hour={start_hour}, end_hour={end_hour}, spans_days={spans_days}")
    logger.info(f"DEBUG: Input data contains {len(weather_data)} hours")
    
    for hour_data in weather_data:
        hour_num = hour_data['HourNum']
        day = hour_data.get('Day', 'today')
        
        # Skip if hour_num is N/A
        if hour_num == "N/A":
            logger.info(f"DEBUG: Skipping hour with N/A HourNum from {day}")
            continue
        
        logger.info(f"DEBUG: Processing hour {hour_num} ({hour_data['Hour']}) from {day}")
        
        should_include = False
        
        if spans_days:
            # Handle cross-day scenarios (e.g., 4PM today to 11AM tomorrow)
            if day == 'today':
                # Keep hours >= start_hour for today
                if hour_num >= start_hour:
                    should_include = True
                    logger.info(f"DEBUG: KEPT today hour {hour_num} (>= {start_hour}) - CROSS-DAY LOGIC")
                else:
                    logger.info(f"DEBUG: FILTERED OUT today hour {hour_num} (< {start_hour}) - CROSS-DAY LOGIC")
            elif day == 'tomorrow':
                # Keep hours <= end_hour for tomorrow
                if hour_num <= end_hour:
                    should_include = True
                    logger.info(f"DEBUG: KEPT tomorrow hour {hour_num} (<= {end_hour}) - CROSS-DAY LOGIC")
                else:
                    logger.info(f"DEBUG: FILTERED OUT tomorrow hour {hour_num} (> {end_hour}) - CROSS-DAY LOGIC")
        else:
            # Single day scenario
            logger.info(f"DEBUG: Using SINGLE-DAY logic for {day}")
            if start_hour <= end_hour:
                # Normal case: 8 AM to 11 AM (same day)
                if start_hour <= hour_num <= end_hour:
                    should_include = True
                    logger.info(f"DEBUG: KEPT {day} hour {hour_num} (within range {start_hour}-{end_hour}) - SINGLE-DAY LOGIC")
                else:
                    logger.info(f"DEBUG: FILTERED OUT {day} hour {hour_num} (outside range {start_hour}-{end_hour}) - SINGLE-DAY LOGIC")
            else:
                # Cross-midnight case within same day: 10 PM to 6 AM
                if hour_num >= start_hour or hour_num <= end_hour:
                    should_include = True
                    logger.info(f"DEBUG: KEPT {day} hour {hour_num} (cross-midnight range) - SINGLE-DAY LOGIC")
                else:
                    logger.info(f"DEBUG: FILTERED OUT {day} hour {hour_num} (outside cross-midnight range) - SINGLE-DAY LOGIC")
        
        if should_include:
            filtered_data.append(hour_data)
    
    logger.info(f"DEBUG: Filtering complete - kept {len(filtered_data)} hours out of {len(weather_data)}")
    return filtered_data

def extract_dual_query_parameters(city: str, today_start: str, today_end: str, tomorrow_start: str, tomorrow_end: str) -> dict:
    """Extract parameters for dual time window queries."""
    
    def time_to_hour(time_str):
        """Convert HH:MM to hour number"""
        return int(time_str.split(':')[0])
    
    result = {
        'city': city,
        'today_start_hour': time_to_hour(today_start),
        'today_end_hour': time_to_hour(today_end),
        'tomorrow_start_hour': time_to_hour(tomorrow_start),
        'tomorrow_end_hour': time_to_hour(tomorrow_end),
        'today_start': today_start,
        'today_end': today_end,
        'tomorrow_start': tomorrow_start,
        'tomorrow_end': tomorrow_end
    }
    
    logger.info(f"DEBUG: Dual window parameters - {result}")
    return result

def score_hour_with_na_handling(hour_data):
    """Score an hour of weather data, handling 'N/A' values gracefully."""
    score = 100
    
    # Temperature scoring - skip if N/A
    temp = hour_data['Temp']
    if temp != "N/A":
        if temp < 35 or temp > 85:
            score -= 30
        elif temp < 45 or temp > 75:
            score -= 15
        elif 50 <= temp <= 65:
            score += 5
    else:
        # If temperature is N/A, apply moderate penalty since we can't assess
        score -= 20
        logger.info(f"Temperature N/A for {hour_data['Hour']} - applying moderate penalty")
    
    # Wind scoring - skip if N/A
    wind = hour_data['Wind']
    if wind != "N/A":
        if wind > 20:
            score -= 25
        elif wind > 15:
            score -= 15
        elif wind > 10:
            score -= 5
    else:
        # If wind is N/A, apply small penalty for uncertainty
        score -= 10
        logger.info(f"Wind N/A for {hour_data['Hour']} - applying uncertainty penalty")
    
    # Humidity scoring - skip if N/A
    humidity = hour_data['Humidity']
    if humidity != "N/A":
        if humidity > 90:
            score -= 25
        elif humidity > 80:
            score -= 15
        elif humidity > 70:
            score -= 5
    else:
        # If humidity is N/A, apply small penalty for uncertainty
        score -= 5
        logger.info(f"Humidity N/A for {hour_data['Hour']} - applying uncertainty penalty")
    
    # Precipitation scoring - skip if N/A
    precip = hour_data['Precip']
    if precip != "N/A":
        if precip > 50:
            score -= 40
        elif precip > 30:
            score -= 25
        elif precip > 10:
            score -= 10
    else:
        # If precipitation is N/A, apply moderate penalty for uncertainty
        score -= 15
        logger.info(f"Precipitation N/A for {hour_data['Hour']} - applying uncertainty penalty")
    
    # Weather condition penalties - only if not N/A
    forecast = str(hour_data['Forecast']).lower()
    if forecast != "n/a":
        weather_penalties = {
            'thunderstorm': 35, 'thunder': 35, 'storm': 30,
            'rain': 25, 'showers': 20, 'drizzle': 15,
            'snow': 30, 'fog': 10
        }
        
        for condition, penalty in weather_penalties.items():
            if condition in forecast:
                score -= penalty
                break
    
    score = max(0, min(100, score))
    final_score = max(1, min(5, round(score / 20) + 1))
    
    return {**hour_data, 'score_100': score, 'final_score': final_score}

def format_value_with_na(value, unit="", na_display="N/A"):
    """Format a value that might be 'N/A' for display."""
    if value == "N/A":
        return f"<span style='color: #999; font-style: italic;'>{na_display}</span>"
    else:
        return f"<span style='font-weight: bold;'>{value}{unit}</span>"

def format_weather_line_with_na(hour):
    """Format a weather line handling N/A values properly - FIXED VERSION."""
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
    
    # Color coding for wind - FIXED: Added N/A check
    if hour['Wind'] != "N/A":
        if hour['Wind'] > 15:
            wind_context = f"💨 <span style='color: #FF5722;'>{wind_display}</span>"
        elif hour['Wind'] <= 5:
            wind_context = f"🍃 <span style='color: #4CAF50;'>{wind_display}</span>"
        else:
            wind_context = f"💨 {wind_display}"
    else:
        wind_context = f"💨 {wind_display}"
    
    # Color coding for precipitation - FIXED: Added N/A check
    if hour['Precip'] != "N/A":
        if hour['Precip'] > 30:
            precip_context = f"🌧️ <span style='color: #2196F3;'>{precip_display}</span> rain"
        elif hour['Precip'] > 10:
            precip_context = f"☁️ <span style='color: #607D8B;'>{precip_display}</span> rain"
        elif hour['Precip'] > 0:
            precip_context = f"🌤️ <span style='color: #FFA726;'>{precip_display}</span> rain"
        else:
            precip_context = f"☀️ <span style='color: #4CAF50;'>{precip_display}</span> rain"
    else:
        precip_context = f"🌧️ {precip_display} rain"
    
    # Color coding for humidity - FIXED: Added N/A check
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

def _generate_dual_window_analysis_html(
    weather_data: dict,
    air_quality_forecast: str = "", 
    city: str = "Unknown City",
    today_start_hour: int = 6,
    today_end_hour: int = 10,
    tomorrow_start_hour: int = 18,
    tomorrow_end_hour: int = 22
) -> str:
    """Generate HTML analysis for dual time windows (today and tomorrow) - UPDATED."""
    
    logger.info(f"DUAL HTML DEBUG: Generating analysis for {city}")
    logger.info(f"DUAL HTML DEBUG: Today window: {today_start_hour}:00-{today_end_hour}:00")
    logger.info(f"DUAL HTML DEBUG: Tomorrow window: {tomorrow_start_hour}:00-{tomorrow_end_hour}:00")
    
    try:
        # Get today and tomorrow data from the parsed weather data
        today_data = weather_data.get('today', [])
        tomorrow_data = weather_data.get('tomorrow', [])
        
        logger.info(f"DUAL HTML DEBUG: Got {len(today_data)} today hours, {len(tomorrow_data)} tomorrow hours")
        
        if not today_data and not tomorrow_data:
            return "<div style='color: red; font-weight: bold;'>Cannot generate forecast: No weather data available</div>"

        # Filter today's data with detailed logging
        today_filtered = []
        logger.info(f"FILTER DEBUG: Today data has {len(today_data)} hours")
        logger.info(f"FILTER DEBUG: Looking for today hours between {today_start_hour} and {today_end_hour}")
        
        for hour_data in today_data:
            hour_num = hour_data['HourNum']
            logger.info(f"FILTER DEBUG: Today hour {hour_num} ({hour_data.get('Hour', 'Unknown')})")
            if hour_num != "N/A" and today_start_hour <= hour_num <= today_end_hour:
                today_filtered.append(hour_data)
                logger.info(f"FILTER DEBUG: ✓ KEPT today hour {hour_num}")
            else:
                logger.info(f"FILTER DEBUG: ✗ FILTERED OUT today hour {hour_num} (not in range {today_start_hour}-{today_end_hour})")
        
        # Filter tomorrow's data with detailed logging and deduplication
        tomorrow_filtered = []
        seen_hours = set()  # Track seen hours to avoid duplicates
        logger.info(f"FILTER DEBUG: Tomorrow data has {len(tomorrow_data)} hours")
        logger.info(f"FILTER DEBUG: Looking for tomorrow hours between {tomorrow_start_hour} and {tomorrow_end_hour}")
        
        for hour_data in tomorrow_data:
            hour_num = hour_data['HourNum']
            hour_key = f"{hour_num}_{hour_data.get('Temp', 'N/A')}"  # Use hour+temp as unique key
            
            logger.info(f"FILTER DEBUG: Tomorrow hour {hour_num} ({hour_data.get('Hour', 'Unknown')})")
            
            # Skip duplicates
            if hour_key in seen_hours:
                logger.info(f"FILTER DEBUG: ✗ SKIPPED duplicate tomorrow hour {hour_num}")
                continue
                
            if hour_num != "N/A" and tomorrow_start_hour <= hour_num <= tomorrow_end_hour:
                tomorrow_filtered.append(hour_data)
                seen_hours.add(hour_key)
                logger.info(f"FILTER DEBUG: ✓ KEPT tomorrow hour {hour_num}")
            else:
                logger.info(f"FILTER DEBUG: ✗ FILTERED OUT tomorrow hour {hour_num} (not in range {tomorrow_start_hour}-{tomorrow_end_hour})")

        logger.info(f"DUAL HTML DEBUG: Filtered today: {len(today_filtered)} hours, tomorrow: {len(tomorrow_filtered)} hours")

        # Handle missing hours with informative messages
        missing_today_hours = []
        missing_tomorrow_hours = []
        
        # Check for missing hours in today's window
        for hour in range(today_start_hour, today_end_hour + 1):
            if not any(h['HourNum'] == hour for h in today_filtered):
                missing_today_hours.append(hour)
                
        # Check for missing hours in tomorrow's window  
        for hour in range(tomorrow_start_hour, tomorrow_end_hour + 1):
            if not any(h['HourNum'] == hour for h in tomorrow_filtered):
                missing_tomorrow_hours.append(hour)

        # Parse AQI data
        aqi_lines = [line.strip() for line in air_quality_forecast.split('\n') if line.strip()]
        today_aqi = "N/A"
        
        for line in aqi_lines:
            if '|' in line:
                parts = [part.strip() for part in line.split('|') if part.strip()]
                for part in parts:
                    aqi_match = re.search(r'\b(\d{1,3})\b', part)
                    if aqi_match:
                        potential_aqi = int(aqi_match.group(1))
                        if 0 <= potential_aqi <= 500:
                            today_aqi = potential_aqi
                            break
                if today_aqi != "N/A":
                    break

        # Score all hours using updated function
        today_scored = [score_hour_with_na_handling(hour) for hour in today_filtered]
        tomorrow_scored = [score_hour_with_na_handling(hour) for hour in tomorrow_filtered]
        
        # Sort by hour
        today_scored.sort(key=lambda x: x['HourNum'] if x['HourNum'] != "N/A" else 0)
        tomorrow_scored.sort(key=lambda x: x['HourNum'] if x['HourNum'] != "N/A" else 0)

        # Find best hours in each window
        best_today = max(today_scored, key=lambda x: x['score_100']) if today_scored else None
        best_tomorrow = max(tomorrow_scored, key=lambda x: x['score_100']) if tomorrow_scored else None

        # Determine AQI category and color
        if today_aqi == "N/A":
            aqi_category = "N/A"
            aqi_color = "#999"
        elif today_aqi <= 50:
            aqi_category = "Good"
            aqi_color = "#4CAF50"
        elif today_aqi <= 100:
            aqi_category = "Moderate" 
            aqi_color = "#FF9800"
        elif today_aqi <= 150:
            aqi_category = "Unhealthy for Sensitive"
            aqi_color = "#FF5722"
        elif today_aqi <= 200:
            aqi_category = "Unhealthy"
            aqi_color = "#F44336"
        else:
            aqi_category = "Very Unhealthy"
            aqi_color = "#9C27B0"

        # Helper function to format time
        def format_time_12hour(hour_24):
            if hour_24 == 0:
                return "12:00 AM"
            elif hour_24 < 12:
                return f"{hour_24}:00 AM"
            elif hour_24 == 12:
                return "12:00 PM"
            else:
                return f"{hour_24 - 12}:00 PM"

        # Generate HTML output
        html = f"""
        <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 100%;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 25px; text-align: center; border-radius: 10px 10px 0 0; margin-bottom: 0;">
                <h1 style="margin: 0; font-size: 24px; font-weight: bold;">🏃‍♂️ Good Morning! 🏃‍♀️</h1>
                <p style="margin: 15px 0 0 0; font-size: 18px; font-weight: bold;">Here is your running forecast for {city}</p>
            </div>
            
            <div style="background: white; padding: 20px; border: 2px solid #667eea; border-top: none; border-radius: 0 0 10px 10px;">
                <p style="margin: 10px 0; font-size: 16px;">
                    <strong style='font-size: 18px; color: #667eea;'>TODAY {format_time_12hour(today_start_hour)} TO {format_time_12hour(today_end_hour)} | TOMORROW {format_time_12hour(tomorrow_start_hour)} TO {format_time_12hour(tomorrow_end_hour)}</strong>
                </p>
                <p style="margin: 10px 0; font-size: 16px;">
                    🌬️ <strong>Air Quality:</strong> <span style="color: {aqi_color}; font-weight: bold; background-color: {aqi_color}20; padding: 4px 8px; border-radius: 4px;">{today_aqi} ({aqi_category})</span>
                </p>
        """
        
        # Show data availability warnings and smart recommendations
        if missing_today_hours or missing_tomorrow_hours:
            html += """
                <div style="background: #FFF3CD; border: 1px solid #FFEAA7; color: #856404; padding: 15px; margin: 15px 0; border-radius: 8px;">
                    <p style="margin: 0; font-weight: bold;">📋 Data Availability & Recommendations:</p>
            """
            
            if missing_today_hours:
                missing_str = ", ".join([format_time_12hour(h) for h in missing_today_hours])
                html += f"<p style='margin: 8px 0 0 0;'>• <strong>Today:</strong> No forecast data for {missing_str}</p>"
                
            if missing_tomorrow_hours:
                missing_str = ", ".join([format_time_12hour(h) for h in missing_tomorrow_hours])
                html += f"<p style='margin: 8px 0 0 0;'>• <strong>Tomorrow:</strong> No forecast data for {missing_str}</p>"
                
                # Smart recommendations based on what's missing
                if any(h < 10 for h in missing_tomorrow_hours):  # Missing early morning hours
                    html += """
                        <div style="margin-top: 15px; padding: 10px; background: #E8F4FD; border-radius: 5px;">
                            <p style="margin: 0; font-weight: bold; color: #0A4B54;">💡 Pro Tip:</p>
                            <p style="margin: 5px 0 0 0; color: #0C5460;">Early morning forecasts (6-9AM) are best available when requested in the early morning hours. For reliable morning running data, try:</p>
                            <ul style="margin: 5px 0 0 20px; color: #0C5460;">
                                <li>Schedule a daily email for 6:00 AM delivery</li>
                                <li>Check the forecast after 6:00 AM for same-day morning runs</li>
                                <li>Consider afternoon running windows (better data availability)</li>
                            </ul>
                        </div>
                    """
                        
            html += "</div>"
        
        # Alternative time suggestions if too much data is missing
        available_tomorrow_hours = [h['HourNum'] for h in tomorrow_filtered]
        if len(missing_tomorrow_hours) > 3 and len(available_tomorrow_hours) < 2:
            # Suggest alternative time windows with better data availability
            suggested_windows = []
            
            # Check afternoon availability
            afternoon_hours = [h for h in tomorrow_data if 12 <= h['HourNum'] <= 16]
            if len(afternoon_hours) >= 3:
                suggested_windows.append("12:00 PM - 4:00 PM")
                
            # Check evening availability
            evening_hours = [h for h in tomorrow_data if 17 <= h['HourNum'] <= 20]
            if len(evening_hours) >= 3:
                suggested_windows.append("5:00 PM - 8:00 PM")
            
            if suggested_windows:
                html += f"""
                    <div style="background: #E1F5FE; border: 2px solid #2196F3; border-radius: 10px; padding: 20px; margin: 15px 0;">
                        <h3 style="color: #0D47A1; margin: 0 0 15px 0;">🔄 Alternative Time Windows Available:</h3>
                        <p style="margin: 0; color: #1565C0;">Based on current forecast availability, consider these windows with complete data:</p>
                        <ul style="margin: 10px 0 0 20px; color: #1565C0;">
                """
                
                for window in suggested_windows:
                    html += f"<li><strong>{window}</strong></li>"
                
                html += """
                        </ul>
                    </div>
                """
        
        # RECOMMENDATIONS SECTION AT TOP
        html += """
                <div style="background: linear-gradient(135deg, #E8F5E8, #C8E6C9); border: 3px solid #4CAF50; border-radius: 12px; padding: 25px; margin: 25px 0;">
                    <h2 style="color: #2E7D32; font-weight: bold; margin: 0 0 20px 0; font-size: 22px; text-align: center; text-transform: uppercase; letter-spacing: 1px;">🎯 RECOMMENDATIONS</h2>
        """
        
        # Best time for today
        if best_today:
            best_today_weather = format_weather_line_with_na(best_today)
            html += f"""
                <div style="background: linear-gradient(135deg, #C8E6C9, #A5D6A7); border: 2px solid #4CAF50; border-radius: 10px; padding: 20px; margin: 15px 0; box-shadow: 0 3px 6px rgba(0,0,0,0.1);">
                    <h3 style="color: #1B5E20; font-weight: bold; margin: 0 0 12px 0; font-size: 18px;">🥇 BEST TIME TODAY:</h3>
                    <p style="margin: 0; font-weight: bold; color: #2E7D32; font-size: 18px;">
                        {best_today['Hour']} - <span style='color: #1B5E20;'>Perfect conditions!</span>
                    </p>
                    <p style="margin: 12px 0 0 0; color: #2E7D32; font-size: 16px; font-weight: bold;">
                        {best_today_weather}
                    </p>
                </div>
            """
        elif missing_today_hours:
            html += """
                <div style="background: #FFF3CD; border: 2px solid #FFEAA7; border-radius: 10px; padding: 20px; margin: 15px 0;">
                    <h3 style="color: #856404; font-weight: bold; margin: 0 0 12px 0; font-size: 18px;">📋 TODAY:</h3>
                    <p style="margin: 0; color: #856404; font-size: 16px;">Limited forecast data available for your requested time window.</p>
                </div>
            """
        
        # Best time for tomorrow
        if best_tomorrow:
            best_tomorrow_weather = format_weather_line_with_na(best_tomorrow)
            html += f"""
                <div style="background: linear-gradient(135deg, #E1F5FE, #B3E5FC); border: 2px solid #2196F3; border-radius: 10px; padding: 20px; margin: 15px 0; box-shadow: 0 3px 6px rgba(0,0,0,0.1);">
                    <h3 style="color: #0D47A1; font-weight: bold; margin: 0 0 12px 0; font-size: 18px;">🥈 BEST TIME TOMORROW:</h3>
                    <p style="margin: 0; font-weight: bold; color: #1565C0; font-size: 18px;">
                        {best_tomorrow['Hour']} - <span style='color: #0D47A1;'>Great choice!</span>
                    </p>
                    <p style="margin: 12px 0 0 0; color: #1565C0; font-size: 16px; font-weight: bold;">
                        {best_tomorrow_weather}
                    </p>
                </div>
            """
        elif missing_tomorrow_hours:
            html += """
                <div style="background: #FFF3CD; border: 2px solid #FFEAA7; border-radius: 10px; padding: 20px; margin: 15px 0;">
                    <h3 style="color: #856404; font-weight: bold; margin: 0 0 12px 0; font-size: 18px;">📋 TOMORROW:</h3>
                    <p style="margin: 0; color: #856404; font-size: 16px;">Some forecast hours not yet available. Try again later for complete data.</p>
                </div>
            """

        html += '</div>'  # Close recommendations
        
        # Helper function to render hour cards
        def render_hour_card(hour, day_color, day_bg):
            # Score color based on rating
            if hour['final_score'] >= 4:
                score_color = "#4CAF50"
                score_bg = "#E8F5E8"
            elif hour['final_score'] >= 3:
                score_color = "#FF9800"
                score_bg = "#FFF3E0"
            else:
                score_color = "#F44336"
                score_bg = "#FFEBEE"
            
            # Create star rating
            filled_stars = "⭐" * int(hour['final_score'])
            empty_stars = "☆" * (5 - int(hour['final_score']))
            stars = filled_stars + empty_stars
            
            # Use the enhanced weather line formatting
            weather_details = format_weather_line_with_na(hour)
            
            return f"""
                <div style="background: {score_bg}; border: 2px solid {score_color}; border-radius: 12px; padding: 16px; margin: 12px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap;">
                        <h3 style="margin: 0; font-size: 20px; color: #333; font-weight: bold;">⏰ {hour['Hour']}</h3>
                        <div style="color: {score_color}; font-weight: bold; font-size: 18px; background: white; padding: 6px 12px; border-radius: 20px; border: 2px solid {score_color};">
                            {stars} ({hour['final_score']}/5)
                        </div>
                    </div>
                    <div style="font-size: 15px; font-weight: bold;">
                        {weather_details}
                    </div>
                </div>
            """

        # TODAY'S HOURS
        if today_scored:
            date_display = get_formatted_date_display()
            html += f"""
                <div style="margin-top: 25px;">
                    <h2 style="margin: 10px 0; font-size: 16px; display: flex; align-items: center; flex-wrap: wrap;">
                        {date_display}
                       <strong style='font-size: 18px; color: #667eea;'>TODAY {format_time_12hour(today_start_hour)} TO {format_time_12hour(today_end_hour)} </strong> 
                    </h2>
            """
            for hour in today_scored:
                html += render_hour_card(hour, "#4CAF50", "#E8F5E8")
            html += '</div>'

        # TOMORROW'S HOURS
        if tomorrow_scored:
            date_display = get_formatted_tomorrow_date_display()
            html += f"""
                <div style="margin-top: 25px;">
                    <h2 style="margin: 10px 0; font-size: 16px; display: flex; align-items: center; flex-wrap: wrap;">
                        {date_display}
                       <strong style='font-size: 18px; color: #667eea;'> TOMORROW {format_time_12hour(tomorrow_start_hour)} TO {format_time_12hour(tomorrow_end_hour)}</strong> 
                    </h2>
            """
            for hour in tomorrow_scored:
                html += render_hour_card(hour, "#2196F3", "#E1F5FE")
            html += '</div>'
        
        # Footer
        html += """
            <div style="text-align: center; padding: 25px; background: linear-gradient(135deg, #F5F5F5, #E0E0E0); border-radius: 10px; margin-top: 25px; border: 2px solid #667eea;">
                <h3 style="margin: 0; color: #333; font-weight: bold; font-size: 18px;">Have a great run!</h3>
            </div>
        </div>
        </div>
        """
        
        return html
        
    except Exception as e:
        logger.error(f"Error in dual window HTML analysis function: {e}")
        return f"<div style='color: red; font-weight: bold; font-size: 16px; padding: 20px; border: 2px solid red; border-radius: 8px;'>Error generating analysis: {str(e)}</div>"


# --- Additional Helper Functions ---

def _generate_filtered_analysis(
    today_forecast: str = "", 
    tomorrow_forecast: str = "", 
    air_quality_forecast: str = "", 
    time_window: str = "today", 
    start_hour: int = None, 
    end_hour: int = None
) -> str:
    """Enhanced version that handles both today and tomorrow weather data with N/A handling."""
    city = "Unknown City"
    
    try:
        # Parse weather data from both days
        today_data = []
        tomorrow_data = []
        
        if today_forecast and "Error" not in today_forecast:
            parsed_data = parse_weather_data(today_forecast)
            today_data = parsed_data.get('today', [])
        
        if tomorrow_forecast and "Error" not in tomorrow_forecast:
            parsed_data = parse_weather_data(tomorrow_forecast)
            tomorrow_data = parsed_data.get('tomorrow', [])
        
        # Combine weather data
        all_weather_data = today_data + tomorrow_data
        
        if not all_weather_data:
            return "Cannot generate score: No weather data available"
        
        # Filter weather data by time range if specified
        weather_data = all_weather_data
        if start_hour is not None and end_hour is not None:
            weather_data = filter_weather_by_time_range(all_weather_data, start_hour, end_hour)
        
        if not weather_data:
            return f"No weather data found for the requested time window {start_hour}:00-{end_hour}:00"

        # Parse AQI data
        aqi_lines = [line.strip() for line in air_quality_forecast.split('\n') if line.strip()]
        today_aqi = "N/A"
        
        for line in aqi_lines:
            if '|' in line:
                parts = [part.strip() for part in line.split('|') if part.strip()]
                for part in parts:
                    aqi_match = re.search(r'\b(\d{1,3})\b', part)
                    if aqi_match:
                        potential_aqi = int(aqi_match.group(1))
                        if 0 <= potential_aqi <= 500:
                            today_aqi = potential_aqi
                            break
                if today_aqi != "N/A":
                    break

        # Generate scores for filtered data
        scored_hours = [score_hour_with_na_handling(hour_data) for hour_data in weather_data]

        # Sort hours chronologically
        def sort_key(hour_data):
            day_priority = 0 if hour_data['Day'] == 'today' else 1
            hour_num = hour_data['HourNum'] if hour_data['HourNum'] != "N/A" else 0
            return (day_priority, hour_num)
        
        scored_hours.sort(key=sort_key)
        
        # Generate formatted output
        lines = []
        lines.append("RUNNING FORECAST")
        lines.append(f"📍 {city}")
        lines.append(f"🌬️ Air Quality: {today_aqi}")
        lines.append("")
        
        # Hourly breakdown
        for hour in scored_hours:
            stars = "★" * int(hour['final_score']) + "☆" * (5 - int(hour['final_score']))
            temp_display = f"{hour['Temp']}°F" if hour['Temp'] != "N/A" else "N/A"
            wind_display = f"{hour['Wind']}mph" if hour['Wind'] != "N/A" else "N/A"
            precip_display = f"{hour['Precip']}%" if hour['Precip'] != "N/A" else "N/A"
            
            lines.append(f"⏰ {hour['Hour']}")
            lines.append(f"   {stars} ({hour['final_score']}/5)")
            lines.append(f"   {temp_display} • {wind_display} • {precip_display}")
            lines.append("")
        
        lines.append("Have a great run!")
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Error in analysis function: {e}")
        return f"Error generating analysis: {str(e)}"

def _generate_filtered_analysis_html(
    today_forecast: str = "", 
    tomorrow_forecast: str = "", 
    air_quality_forecast: str = "", 
    time_window: str = "today", 
    start_hour: int = None, 
    end_hour: int = None
) -> str:
    """
    Stub for HTML output. Falls back to text output if not implemented.
    """
    return _generate_filtered_analysis(
        today_forecast=today_forecast,
        tomorrow_forecast=tomorrow_forecast,
        air_quality_forecast=air_quality_forecast,
        time_window=time_window,
        start_hour=start_hour,
        end_hour=end_hour
    )

# --- Agent Tools ---

@tool
def get_weather_forecast_from_server(city: str, granularity: str = 'hourly') -> str:
    """Gets the weather forecast (temp, wind, humidity, precip) for a city."""
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
    """Gets the Air Quality Index (AQI) forecast for a city."""
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
    city: str,
    today_start: str,
    today_end: str, 
    tomorrow_start: str,
    tomorrow_end: str,
    recipient_email: str,
    scheduled_time: str = "06:00"
) -> str:
    """Schedules a daily email report for dual time windows."""
    
    # Email validation pattern
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    
    # Capture parameters in closure
    captured_city = city
    captured_today_start = today_start
    captured_today_end = today_end
    captured_tomorrow_start = tomorrow_start
    captured_tomorrow_end = tomorrow_end
    
    logger.info(f"SCHEDULING DUAL: {city}, Today: {today_start}-{today_end}, Tomorrow: {tomorrow_start}-{tomorrow_end}")
    
    def job():
        logger.info(f"Running scheduled dual window job for {captured_city}")
        try:
            # Generate HTML report
            analysis = run_agent_workflow(
                city=captured_city,
                today_start=captured_today_start,
                today_end=captured_today_end,
                tomorrow_start=captured_tomorrow_start,
                tomorrow_end=captured_tomorrow_end,
                output_format="html"
            )
            
            subject = f"Your Daily Running Forecast for {captured_city}"
            
            # Email HTML structure
            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 20px; background-color: #f9f9f9; }}
                    .email-container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                    .email-footer {{ margin-top: 30px; padding: 20px; text-align: center; color: #666; background: #f5f5f5; }}
                </style>
            </head>
            <body>
                <div class="email-container">
                    {analysis}
                    <div class="email-footer">
                        <p style="margin: 0;"><small>This is an automated report. Reply if you need assistance.</small></p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            if send_email_notification(recipient_email, subject, html_body, is_html=True):
                logger.info(f"Successfully sent dual window scheduled report to {recipient_email}")
            else:
                logger.error(f"Failed to send dual window scheduled report to {recipient_email}")
                
        except Exception as e:
            logger.error(f"Error in dual window scheduled job: {e}")

    if not re.match(email_pattern, recipient_email):
        return f"Error: Invalid email address format: {recipient_email}"
    
    try:
        datetime.strptime(scheduled_time, "%H:%M")
    except ValueError:
        return f"Error: Invalid time format. Please use HH:MM format (e.g., '06:00')"
    
    try:
        schedule.every().day.at(scheduled_time).do(job)
        return f"✅ Success! Daily running report for '{city}' scheduled for {scheduled_time} to '{recipient_email}'. Time windows: Today {today_start}-{today_end}, Tomorrow {tomorrow_start}-{tomorrow_end}"
    except Exception as e:
        return f"Error scheduling email report: {e}"

# --- Agent and Graph Definitions ---

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    city: str
    time_window: str
    weather_data: str
    aqi_data: str

def run_agent_workflow(
    city: str,
    today_start: str,
    today_end: str,
    tomorrow_start: str,
    tomorrow_end: str,
    output_format: str = "html"
) -> str:
    """Updated workflow function for dual time windows - CORRECTED."""
    try:
        # Extract parameters for dual windows
        params = extract_dual_query_parameters(city, today_start, today_end, tomorrow_start, tomorrow_end)
        
        logger.info(f"Dual window workflow - City: {city}")
        logger.info(f"Today: {today_start} to {today_end}")
        logger.info(f"Tomorrow: {tomorrow_start} to {tomorrow_end}")
        
        # Get weather data - CORRECTED: Single call that returns 48 hours
        weather_response = get_weather_forecast_from_server.invoke({"city": city, "granularity": "hourly"})
        aqi_data = get_air_quality_from_server.invoke({"city": city})
        
        # Parse the weather data - CORRECTED: Parse once and split into today/tomorrow
        weather_data = parse_weather_data(weather_response)
        
        logger.info(f"Retrieved and parsed weather data: {len(weather_data['today'])} today hours, {len(weather_data['tomorrow'])} tomorrow hours")
        
        # Generate analysis using the dual window function
        if output_format.lower() == "html":
            analysis = _generate_dual_window_analysis_html(
                weather_data=weather_data,
                air_quality_forecast=aqi_data,
                city=city,
                today_start_hour=params['today_start_hour'],
                today_end_hour=params['today_end_hour'],
                tomorrow_start_hour=params['tomorrow_start_hour'],
                tomorrow_end_hour=params['tomorrow_end_hour']
            )
        else:
            # For text format
            analysis = _generate_dual_window_analysis_text(
                weather_data=weather_data,
                air_quality_forecast=aqi_data,
                city=city,
                today_start_hour=params['today_start_hour'],
                today_end_hour=params['today_end_hour'],
                tomorrow_start_hour=params['tomorrow_start_hour'],
                tomorrow_end_hour=params['tomorrow_end_hour']
            )
        
        return analysis
        
    except Exception as e:
        logger.error(f"Dual window workflow error: {e}")
        return f"Error in agent workflow: {str(e)}. Please check your configuration and try again."

def _generate_dual_window_analysis_text(
    weather_data: dict,
    air_quality_forecast: str = "", 
    city: str = "Unknown City",
    today_start_hour: int = 6,
    today_end_hour: int = 10,
    tomorrow_start_hour: int = 18,
    tomorrow_end_hour: int = 22
) -> str:
    """Generate text analysis for dual time windows - CORRECTED."""
    
    try:
        # Get today and tomorrow data from the parsed weather data
        today_data = weather_data.get('today', [])
        tomorrow_data = weather_data.get('tomorrow', [])
        
        if not today_data and not tomorrow_data:
            return "Cannot generate forecast: No weather data available"

        # Filter data for time windows
        today_filtered = [h for h in today_data if h['HourNum'] != "N/A" and today_start_hour <= h['HourNum'] <= today_end_hour]
        tomorrow_filtered = [h for h in tomorrow_data if h['HourNum'] != "N/A" and tomorrow_start_hour <= h['HourNum'] <= tomorrow_end_hour]

        # Score hours
        today_scored = [score_hour_with_na_handling(h) for h in today_filtered]
        tomorrow_scored = [score_hour_with_na_handling(h) for h in tomorrow_filtered]
        
        # Find best hours
        best_today = max(today_scored, key=lambda x: x['score_100']) if today_scored else None
        best_tomorrow = max(tomorrow_scored, key=lambda x: x['score_100']) if tomorrow_scored else None

        # Generate text output
        lines = []
        lines.append("RUNNING FORECAST")
        lines.append(f"Location: {city}")
        lines.append("")
        
        if best_today:
            lines.append("BEST TIME TODAY:")
            lines.append(f"  {best_today['Hour']} - Perfect conditions!")
            temp_str = f"{best_today['Temp']}°F" if best_today['Temp'] != "N/A" else "N/A"
            wind_str = f"{best_today['Wind']}mph" if best_today['Wind'] != "N/A" else "N/A" 
            precip_str = f"{best_today['Precip']}%" if best_today['Precip'] != "N/A" else "N/A"
            humidity_str = f"{best_today['Humidity']}%" if best_today['Humidity'] != "N/A" else "N/A"
            lines.append(f"  {temp_str}, {wind_str} wind, {precip_str} rain, {humidity_str} humidity")
        
        if best_tomorrow:
            lines.append("")
            lines.append("BEST TIME TOMORROW:")
            lines.append(f"  {best_tomorrow['Hour']} - Great choice!")
            temp_str = f"{best_tomorrow['Temp']}°F" if best_tomorrow['Temp'] != "N/A" else "N/A"
            wind_str = f"{best_tomorrow['Wind']}mph" if best_tomorrow['Wind'] != "N/A" else "N/A"
            precip_str = f"{best_tomorrow['Precip']}%" if best_tomorrow['Precip'] != "N/A" else "N/A"
            humidity_str = f"{best_tomorrow['Humidity']}%" if best_tomorrow['Humidity'] != "N/A" else "N/A"
            lines.append(f"  {temp_str}, {wind_str} wind, {precip_str} rain, {humidity_str} humidity")
        
        lines.append("")
        lines.append("Have a great run!")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"Error generating text analysis: {str(e)}"

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

def main():
    """Main function for testing the system."""
    print("Running Forecast System Initialized")
    print("Available commands:")
    print("1. Get running forecast: 'What's the best time to run in [city]?'")
    print("2. Time-specific queries: 'Best time to run between 8AM and 11AM in NYC?'")
    print("3. Cross-day queries: 'Running conditions from 4PM today to 11AM tomorrow in Boston?'")
    print("4. Schedule daily emails: Use the schedule_daily_email_report tool")
    print("5. Type 'quit' to exit")
    
    start_scheduler()
    
    while True:
        try:
            user_input = input("\nEnter your query: ").strip()
            if user_input.lower() in ['quit', 'exit', 'q']:
                break
                
            if user_input:
                print("\nProcessing your request...\n")
                # For testing, use sample dual window parameters
                result = run_agent_workflow(
                    city="New York",
                    today_start="06:00",
                    today_end="10:00", 
                    tomorrow_start="18:00",
                    tomorrow_end="22:00",
                    output_format="text"
                )
                print("Result:")
                print("=" * 50)
                print(result)
                print("=" * 50)
            
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()