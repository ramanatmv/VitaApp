import os
import requests
import json
import pandas as pd
from io import StringIO
from typing import TypedDict, Annotated, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage, AIMessage
from pydantic import BaseModel, Field  # Updated import
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

def parse_weather_data(forecast_data: str, day_label: str = "") -> list:
    """Parse weather forecast data into structured format with day labeling."""
    
    # Check for empty or invalid input
    if not forecast_data or not forecast_data.strip():
        logger.info(f"DEBUG: parse_weather_data received empty data for {day_label}")
        return []
        
    weather_lines = [line.strip() for line in forecast_data.split('\n') if line.strip()]
    
    if not weather_lines:
        logger.info(f"DEBUG: parse_weather_data found no valid lines for {day_label}")
        return []
    
    data_lines = []
    for line in weather_lines:
        if '|' in line and re.search(r'\d+', line) and not line.startswith('+=') and not line.startswith('+--'):
            if not any(header in line.lower() for header in ['num', 'time', 'temp', 'wind', 'forecast', 'precip', 'humidity']):
                data_lines.append(line)
    
    logger.info(f"DEBUG: parse_weather_data found {len(data_lines)} data lines for {day_label}")
    
    weather_data = []
    for line_num, line in enumerate(data_lines, 1):
        try:
            if '|' in line:
                parts = [part.strip() for part in line.split('|') if part.strip()]
                if len(parts) >= 7:
                    hour_str = parts[1]  # Time column
                    temp_str = parts[2]
                    wind_str = parts[3] 
                    forecast_str = parts[5] if len(parts) > 5 else "Clear"
                    precip_str = parts[6] if len(parts) > 6 else "0%"
                    humidity_str = parts[7] if len(parts) > 7 else "50%"
                    
                    # Extract hour number
                    hour_match = re.search(r'(\d{1,2})', hour_str)
                    if hour_match:
                        hour_num = int(hour_match.group(1))
                    else:
                        hour_num = 0
                    
                    # Format hour with AM/PM
                    if hour_num == 0:
                        formatted_hour = "12:00 AM"
                    elif hour_num < 12:
                        formatted_hour = f"{hour_num}:00 AM"
                    elif hour_num == 12:
                        formatted_hour = "12:00 PM"
                    else:
                        formatted_hour = f"{hour_num - 12}:00 PM"
                    
                    # Extract numeric values
                    temp = int(re.findall(r'\d+', temp_str)[0]) if re.findall(r'\d+', temp_str) else 70
                    wind = int(re.findall(r'\d+', wind_str)[0]) if re.findall(r'\d+', wind_str) else 0
                    precip = int(re.findall(r'\d+', precip_str)[0]) if re.findall(r'\d+', precip_str) else 0
                    humidity = int(re.findall(r'\d+', humidity_str)[0]) if re.findall(r'\d+', humidity_str) else 50
                    forecast = forecast_str.strip()
                    
                    weather_data.append({
                        'Hour': formatted_hour,
                        'HourNum': hour_num,
                        'Day': day_label,
                        'Temp': temp,
                        'Wind': wind,
                        'Precip': precip,
                        'Humidity': humidity,
                        'Forecast': forecast
                    })
                    
        except (ValueError, IndexError) as e:
            logger.warning(f"Error parsing weather line {line_num} for {day_label}: {line} - {e}")
            continue
    
    logger.info(f"DEBUG: parse_weather_data returning {len(weather_data)} weather entries for {day_label}")
    return weather_data

def filter_weather_by_time_range(weather_data: list, start_hour: int, end_hour: int, spans_days: bool = False) -> list:
    """Filter weather data by hour range, handling cross-day scenarios."""
    filtered_data = []
    
    logger.info(f"DEBUG: Filtering weather data - start_hour={start_hour}, end_hour={end_hour}, spans_days={spans_days}")
    logger.info(f"DEBUG: Input data contains {len(weather_data)} hours")
    
    for hour_data in weather_data:
        hour_num = hour_data['HourNum']
        day = hour_data.get('Day', 'today')
        
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
            # Single day scenario - FIXED LOGIC
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

def _generate_filtered_analysis(
    today_forecast: str = "", 
    tomorrow_forecast: str = "", 
    air_quality_forecast: str = "", 
    time_window: str = "today", 
    start_hour: int = None, 
    end_hour: int = None
) -> str:
    """
    Enhanced version that handles both today and tomorrow weather data.
    """
    city = "Unknown City"
    
    logger.info(f"EMAIL DEBUG: Generating analysis for window: '{time_window}' with hours {start_hour}-{end_hour}")
    
    try:
        # Parse weather data from both days
        today_data = []
        tomorrow_data = []
        
        if today_forecast and "Error" not in today_forecast:
            today_data = parse_weather_data(today_forecast, "today")
            logger.info(f"EMAIL DEBUG: Parsed {len(today_data)} hours for today")
        
        if tomorrow_forecast and "Error" not in tomorrow_forecast:
            tomorrow_data = parse_weather_data(tomorrow_forecast, "tomorrow")
            logger.info(f"EMAIL DEBUG: Parsed {len(tomorrow_data)} hours for tomorrow")
        
        # Combine weather data
        all_weather_data = today_data + tomorrow_data
        logger.info(f"EMAIL DEBUG: Total weather data points: {len(all_weather_data)}")
        
        if not all_weather_data:
            return "Cannot generate score: No weather data available"
        
        # FIXED: Determine if we need data from both days based on explicit indicators
        spans_days = False
        if start_hour is not None and end_hour is not None:
            logger.info(f"EMAIL DEBUG: Time filtering requested - start_hour={start_hour}, end_hour={end_hour}")
            # Only set spans_days=True if we have explicit cross-day patterns in time_window
            if "today" in time_window.lower() and "tomorrow" in time_window.lower():
                # Explicit cross-day like "today 16:00 to tomorrow 11:00"
                spans_days = True
                logger.info("EMAIL DEBUG: Cross-day detected from explicit today->tomorrow in time_window")
            elif start_hour > end_hour and len(all_weather_data) > 24:
                # Time wraps around and we have data from multiple days
                spans_days = True
                logger.info("EMAIL DEBUG: Cross-day detected from time wrap with multi-day data")
            else:
                # Single day scenario
                spans_days = False
                logger.info("EMAIL DEBUG: Single day scenario detected")
        
        # Filter weather data by time range
        if start_hour is not None and end_hour is not None:
            # Check if this is actually a custom time range (not the default 0-23)
            if not (start_hour == 0 and end_hour == 23):
                logger.info(f"EMAIL DEBUG: CUSTOM TIME RANGE DETECTED - Filtering weather data by time range {start_hour}:00 to {end_hour}:00, spans_days={spans_days}")
                weather_data = filter_weather_by_time_range(all_weather_data, start_hour, end_hour, spans_days)
                logger.info(f"EMAIL DEBUG: After filtering - kept {len(weather_data)} hours within time range")
            else:
                logger.info("EMAIL DEBUG: Default time range (0-23) detected - using all weather data")
                weather_data = all_weather_data
        else:
            logger.info("EMAIL DEBUG: No time filtering requested (None values) - using all weather data")
            weather_data = all_weather_data
        
        if not weather_data:
            return f"No weather data found for the requested time window {start_hour}:00-{end_hour}:00"

        # Parse AQI data (same as before)
        aqi_lines = [line.strip() for line in air_quality_forecast.split('\n') if line.strip()]
        today_aqi = 50
        
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
                if today_aqi != 50:
                    break

        # Generate scores for filtered data
        scored_hours = []
        for hour_data in weather_data:
            score = 100
            
            # Temperature scoring
            temp = hour_data['Temp']
            if temp < 35 or temp > 85:
                score -= 30
            elif temp < 45 or temp > 75:
                score -= 15
            elif 50 <= temp <= 65:
                score += 5
            
            # Wind scoring
            wind = hour_data['Wind']
            if wind > 20:
                score -= 25
            elif wind > 15:
                score -= 15
            elif wind > 10:
                score -= 5
            
            # Humidity scoring
            humidity = hour_data['Humidity']
            if humidity > 90:
                score -= 25
            elif humidity > 80:
                score -= 15
            elif humidity > 70:
                score -= 5
            
            # Precipitation scoring
            precip = hour_data['Precip']
            if precip > 50:
                score -= 40
            elif precip > 30:
                score -= 25
            elif precip > 10:
                score -= 10
            
            # Weather condition penalties
            forecast = str(hour_data['Forecast']).lower()
            weather_penalties = {
                'thunderstorm': 35, 'thunder': 35, 'storm': 30,
                'rain': 25, 'showers': 20, 'drizzle': 15,
                'snow': 30, 'fog': 10
            }
            
            for condition, penalty in weather_penalties.items():
                if condition in forecast:
                    score -= penalty
                    break
            
            # AQI penalty
            if today_aqi > 150:
                score -= 35
            elif today_aqi > 100:
                score -= 25
            elif today_aqi > 50:
                score -= 10
            
            score = max(0, min(100, score))
            final_score = max(1, min(5, round(score / 20) + 1))
            
            scored_hours.append({
                **hour_data,
                'score_100': score,
                'final_score': final_score
            })

        # Sort hours chronologically (today first, then tomorrow)
        def sort_key(hour_data):
            day_priority = 0 if hour_data['Day'] == 'today' else 1
            return (day_priority, hour_data['HourNum'])
        
        scored_hours.sort(key=sort_key)
        
        # Determine AQI category
        if today_aqi <= 50:
            aqi_category = "Good"
            aqi_emoji = "🟢"
        elif today_aqi <= 100:
            aqi_category = "Moderate" 
            aqi_emoji = "🟡"
        elif today_aqi <= 150:
            aqi_category = "Unhealthy for Sensitive"
            aqi_emoji = "🟠"
        elif today_aqi <= 200:
            aqi_category = "Unhealthy"
            aqi_emoji = "🔴"
        else:
            aqi_category = "Very Unhealthy"
            aqi_emoji = "🟣"

        # Generate formatted output
        lines = []
        
        # Header section
        lines.append("")
        lines.append("🏃‍♂️ RUNNING FORECAST 🏃‍♀️")
        lines.append(f"📍 {city}")
        
        # Time display
        time_display = f"📅 {time_window.upper()}"
        if start_hour is not None and end_hour is not None:
            start_display = f"{start_hour % 12 if start_hour % 12 != 0 else 12}:00 {'AM' if start_hour < 12 else 'PM'}"
            end_display = f"{end_hour % 12 if end_hour % 12 != 0 else 12}:00 {'AM' if end_hour < 12 else 'PM'}"
            time_display += f" ({start_display} - {end_display})"
        
        lines.append(time_display)
        lines.append(f"🌬️ Air Quality: {aqi_emoji} {today_aqi} ({aqi_category})")
        lines.append("")
        
        # Hourly breakdown with day labels
        current_day = None
        for hour in scored_hours:
            # Add day separator if day changes
            if current_day != hour['Day']:
                if current_day is not None:
                    lines.append("─" * 40)
                lines.append(f"📅 {hour['Day'].upper()}")
                lines.append("")
                current_day = hour['Day']
            
            # Create star rating
            stars = "★" * int(hour['final_score']) + "☆" * (5 - int(hour['final_score']))
            
            # Temperature context
            if hour['Temp'] >= 75:
                temp_context = "🌡️ Warm"
            elif hour['Temp'] <= 45:
                temp_context = "❄️ Cold"
            else:
                temp_context = "🌤️ Nice"
            
            # Wind context
            if hour['Wind'] > 15:
                wind_context = "💨 Windy"
            elif hour['Wind'] <= 5:
                wind_context = "🍃 Calm"
            else:
                wind_context = f"{hour['Wind']}mph"
            
            # Precipitation context
            if hour['Precip'] > 30:
                precip_context = f"🌧️ {hour['Precip']}% rain risk"
            elif hour['Precip'] > 10:
                precip_context = f"☁ {hour['Precip']}% rain risk"
            elif hour['Precip'] > 0:
                precip_context = f"☀️ {hour['Precip']}% rain risk"
            else:
                precip_context = "☀️ No rain expected"
            
            lines.append(f"⏰ {hour['Hour']}")
            lines.append(f"   {stars} ({hour['final_score']}/5)")
            lines.append(f"   {temp_context} {hour['Temp']}°F • {wind_context} • {precip_context}")
            lines.append("")

        # Recommendations
        best_hours = sorted(scored_hours, key=lambda x: x['score_100'], reverse=True)[:3]
        worst_hours = sorted(scored_hours, key=lambda x: x['score_100'])[:2]
        
        lines.append("═" * 50)
        lines.append("")
        lines.append("🎯 RECOMMENDATIONS:")
        lines.append("")
        lines.append("🥇 BEST TIME TO RUN:")
        lines.append("")
        best_hour = best_hours[0]
        day_text = f" ({best_hour['Day']})" if spans_days else ""
        lines.append(f"   {best_hour['Hour']}{day_text} - Perfect conditions!")
        lines.append("")
        lines.append(f"   {best_hour['Temp']}°F, {best_hour['Wind']}mph wind, {best_hour['Precip']}% rain chance")
        lines.append("")
        
        if len(best_hours) > 1:
            lines.append("🥈 Other Great Times:")
            lines.append("")
            for hour in best_hours[1:]:
                day_text = f" ({hour['Day']})" if spans_days else ""
                lines.append(f"   • {hour['Hour']}{day_text} ({hour['final_score']}/5 stars)")
            lines.append("")
        
        # Warning for poor conditions
        if worst_hours[0]['final_score'] <= 2:
            lines.append("⚠️ Times to Avoid:")
            lines.append("")
            for hour in worst_hours:
                if hour['final_score'] <= 2:
                    reasons = []
                    if hour['Temp'] < 35 or hour['Temp'] > 85:
                        reasons.append("extreme temperature")
                    if hour['Wind'] > 20:
                        reasons.append("high winds") 
                    if hour['Precip'] > 50:
                        reasons.append("heavy rain risk")
                    
                    reason_text = ", ".join(reasons) if reasons else "poor conditions"
                    day_text = f" ({hour['Day']})" if spans_days else ""
                    lines.append(f"   ❌ {hour['Hour']}{day_text} - {reason_text}")
            lines.append("")
        
        lines.append("═" * 50)
        lines.append("")
        lines.append("Have a great run! 🏃‍♀️🏃‍♂️")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Error in enhanced analysis function: {e}")
        return f"Error generating analysis: {str(e)}"

# --- Agent Tools ---

@tool
def get_weather_forecast_from_server(city: str, granularity: str = 'hourly') -> str:
    """Gets the hourly weather forecast (temp, wind, humidity, precip) for a city."""
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
def generate_overall_score_and_graph(
    today_forecast: str = "",
    tomorrow_forecast: str = "",
    air_quality_forecast: str = "",
    time_window: str = "today",
    start_hour: str = "00:00",
    end_hour: str = "23:59"
) -> str:
    """
    Analyzes environmental data (weather and AQI) to generate a 1-5 score
    for each hour within a specific time range, supporting cross-day scenarios.
    
    Args:
        today_forecast: Today's weather forecast data
        tomorrow_forecast: Tomorrow's weather forecast data
        air_quality_forecast: Air quality forecast data  
        time_window: Description of time period (e.g., "tomorrow", "today")
        start_hour: Start time in HH:MM format (e.g., "08:00")
        end_hour: End time in HH:MM format (e.g., "11:00")
    """
    # Extract numeric hours from HH:MM format
    start_hour_num = int(start_hour.split(':')[0]) if ':' in start_hour else None
    end_hour_num = int(end_hour.split(':')[0]) if ':' in end_hour else None
    
    return _generate_filtered_analysis(
        today_forecast=today_forecast,
        tomorrow_forecast=tomorrow_forecast,
        air_quality_forecast=air_quality_forecast, 
        time_window=time_window,
        start_hour=start_hour_num,
        end_hour=end_hour_num
    )

@tool
def schedule_daily_email_report(
    city: str, 
    time_window: str, 
    recipient_email: str, 
    scheduled_time: str = "06:00",
    start_hour: str = "00:00",
    end_hour: str = "23:59"
) -> str:
    """Schedules a daily email report for the best running time at a user-specified time."""
    
    # Email validation pattern
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    # Capture the parameters in the closure and validate them
    captured_start_hour = start_hour
    captured_end_hour = end_hour
    captured_time_window = time_window
    
    # Log the received parameters for debugging
    logger.info(f"SCHEDULING: Received parameters:")
    logger.info(f"  - city: {city}")
    logger.info(f"  - time_window: {time_window}")
    logger.info(f"  - start_hour: {start_hour}")
    logger.info(f"  - end_hour: {end_hour}")
    logger.info(f"  - recipient_email: {recipient_email}")
    logger.info(f"  - scheduled_time: {scheduled_time}")
    
    # Validate the time format and convert if needed
    if start_hour != "00:00" or end_hour != "23:59":
        logger.info(f"EMAIL SCHEDULING: Custom time window detected - {start_hour} to {end_hour}")
        
        # Ensure the time parameters are in the correct format
        try:
            start_parts = start_hour.split(':')
            end_parts = end_hour.split(':')
            if len(start_parts) == 2 and len(end_parts) == 2:
                start_hour_num = int(start_parts[0])
                end_hour_num = int(end_parts[0])
                logger.info(f"EMAIL SCHEDULING: Validated time range - {start_hour_num}:00 to {end_hour_num}:00")
                
                # Additional validation: ensure this isn't the default range
                if start_hour_num == 0 and end_hour_num == 23:
                    logger.warning("EMAIL SCHEDULING: Detected default time range even though custom times were expected!")
                else:
                    logger.info(f"EMAIL SCHEDULING: Confirmed custom time range - {start_hour_num} to {end_hour_num}")
            else:
                logger.warning(f"EMAIL SCHEDULING: Invalid time format - start_hour={start_hour}, end_hour={end_hour}")
        except ValueError as e:
            logger.error(f"EMAIL SCHEDULING: Error parsing time parameters: {e}")
    else:
        logger.warning("EMAIL SCHEDULING: Using default time range 00:00-23:59 - this will show all hours!")
    
    def job():
        logger.info(f"Running scheduled job: Generating report for {city} at {scheduled_time}")
        logger.info(f"Email job parameters: time_window={captured_time_window}, start_hour={captured_start_hour}, end_hour={captured_end_hour}")
        try:
            # Use the passed parameters directly instead of trying to re-parse them
            needs_both_days = "today" in captured_time_window.lower() and "tomorrow" in captured_time_window.lower()
            
            # Determine which day's data we need
            if "tomorrow" in captured_time_window.lower() and not needs_both_days:
                day = "tomorrow"
            else:
                day = "today"
            
            logger.info(f"Email job determined: day={day}, needs_both_days={needs_both_days}")
            
            # Get weather data for required days
            today_weather = ""
            tomorrow_weather = ""
            
            if needs_both_days:
                # Cross-day scenario: need both today and tomorrow data
                today_weather = get_weather_forecast_from_server.invoke({"city": city, "granularity": "hourly"})
                tomorrow_weather = get_weather_forecast_from_server.invoke({"city": city, "granularity": "hourly"})
                logger.info("Email job: Retrieved both today and tomorrow weather data")
            elif day == "today":
                # Today only
                today_weather = get_weather_forecast_from_server.invoke({"city": city, "granularity": "hourly"})
                logger.info("Email job: Retrieved today's weather data")
            elif day == "tomorrow":
                # Tomorrow only
                tomorrow_weather = get_weather_forecast_from_server.invoke({"city": city, "granularity": "hourly"})
                logger.info("Email job: Retrieved tomorrow's weather data")
            
            # Get air quality data
            aqi_data = get_air_quality_from_server.invoke({"city": city})
            logger.info("Email job: Retrieved air quality data")
            
            # Generate analysis using the same logic as the main workflow
            logger.info(f"Email job calling analysis with: start_hour={captured_start_hour}, end_hour={captured_end_hour}, time_window={captured_time_window}")
            
            # Ensure we're using the captured time parameters for filtering
            analysis = generate_overall_score_and_graph.invoke({
                "today_forecast": today_weather,
                "tomorrow_forecast": tomorrow_weather,
                "air_quality_forecast": aqi_data,
                "time_window": captured_time_window,
                "start_hour": captured_start_hour,
                "end_hour": captured_end_hour
            })
            
            # Debug log to verify the analysis contains filtered hours
            logger.info(f"Email job: Generated analysis length: {len(analysis)} characters")
            
            # Replace placeholder city with actual city
            report_content = analysis.replace("Unknown City", city)
            
            subject = f"🏃 Your Daily Running Forecast for {city}"
            body = f"""Good morning!

Here is your daily running forecast for {city}:

{report_content}

---
This is an automated report. Reply to this email if you need assistance.
"""
            
            if send_email_notification(recipient_email, subject, body):
                logger.info(f"Successfully sent scheduled report to {recipient_email}")
            else:
                logger.error(f"Failed to send scheduled report to {recipient_email}")
                
        except Exception as e:
            logger.error(f"Error in scheduled job: {e}")

    if not re.match(email_pattern, recipient_email):
        return f"Error: Invalid email address format: {recipient_email}"
    
    try:
        datetime.strptime(scheduled_time, "%H:%M")
    except ValueError:
        return f"Error: Invalid time format. Please use HH:MM format (e.g., '06:00')"
    
    try:
        schedule.every().day.at(scheduled_time).do(job)
        return f"✅ Success! Daily running report for '{city}' scheduled for {scheduled_time} to '{recipient_email}'. Time range: {start_hour}-{end_hour}"
    except Exception as e:
        return f"Error scheduling email report: {e}"

# --- Agent and Graph Definitions ---

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    city: str
    time_window: str
    weather_data: str
    aqi_data: str

def extract_query_parameters(prompt: str) -> dict:
    """Extract city, day, and time range from user prompt."""
    result = {
        'city': 'New York',
        'day': 'today',
        'start_hour': '00:00',
        'end_hour': '23:59',
        'time_window': 'today',
        'needs_both_days': False
    }
    
    logger.info(f"DEBUG: extract_query_parameters called with prompt: '{prompt}'")
    
    prompt_lower = prompt.lower()
    
    # First determine the base day context
    day_context = 'today'  # default
    if 'tomorrow' in prompt_lower:
        day_context = 'tomorrow'
        result['day'] = 'tomorrow'
        result['time_window'] = 'tomorrow'
    elif 'today' in prompt_lower:
        day_context = 'today'
        result['day'] = 'today'
        result['time_window'] = 'today'
    
    # Extract city
    city_patterns = [
        r'in\s+([A-Za-z\s,\.]+?)(?:\s+tomorrow|\s+today|\s+between|\s+from|\s+during|\s+for|\s+at|\?|\s*$)',
        r'for\s+([A-Za-z\s,\.]+?)(?:\s+tomorrow|\s+today|\s+between|\s+from|\s+during|\s+for|\s+at|\?|\s*$)',
        r'at\s+([A-Za-z\s,\.]+?)(?:\s+tomorrow|\s+today|\s+between|\s+from|\s+during|\s+for|\s+at|\?|\s*$)',
        r'weather\s+(?:in|for|at)\s+([A-Za-z\s,\.]+?)(?:\s+tomorrow|\s+today|\s+between|\s+from|\s+during|\?|\s*$)',
        r'run\s+(?:in|at)\s+([A-Za-z\s,\.]+?)(?:\s+tomorrow|\s+today|\s+between|\s+from|\s+during|\?|\s*$)',
    ]
    
    for pattern in city_patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            city = match.group(1).strip()
            exclude_words = {'the', 'best', 'time', 'between', 'from', 'during', 'and', 'or'}
            city_words = []
            for word in city.split():
                if word.lower() not in exclude_words:
                    city_words.append(word)
            if city_words:
                result['city'] = ' '.join(city_words)
                logger.info(f"DEBUG: extract_query_parameters found city: '{result['city']}'")
                break
    
    # Extract time patterns - add more patterns for cross-day scenarios
    time_patterns = [
        r'between\s+(\d{1,2})\s*(am|pm)\s*(?:and|to|-)\s*(\d{1,2})\s*(am|pm)',
        r'from\s+(\d{1,2})\s*(am|pm)\s*(?:to|until|-)\s*(\d{1,2})\s*(am|pm)',
        r'(\d{1,2})\s*(am|pm)\s*(?:to|-)\s*(\d{1,2})\s*(am|pm)',
        r'between\s+(\d{1,2})\s*(?:and|to|-)\s*(\d{1,2})\s*(am|pm)',
        # Additional patterns for cross-day scenarios
        r'(\d{1,2})\s*(am|pm)\s+.*?to\s+.*?(\d{1,2})\s*(am|pm)',  # "7PM today to 4PM tomorrow"
        r'(\d{1,2})\s*(am|pm)\s+to\s+.*?(\d{1,2})\s*(am|pm)',     # "7PM to tomorrow 4PM"
    ]
    
    # Check for explicit cross-day patterns first
    cross_day_patterns = [
        r'from.*today.*to.*tomorrow',
        r'today.*to.*tomorrow', 
        r'tonight.*to.*tomorrow',
        r'(\d{1,2})\s*(pm|am).*today.*to.*(\d{1,2})\s*(am|pm).*tomorrow',
        r'(\d{1,2})\s*(pm|am).*to.*tomorrow.*(\d{1,2})\s*(am|pm)',  # "7PM to tomorrow 4PM"
    ]
    
    explicit_cross_day = False
    cross_day_times = None
    
    for pattern in cross_day_patterns:
        match = re.search(pattern, prompt_lower)
        if match:
            explicit_cross_day = True
            logger.info(f"DEBUG: Found explicit cross-day pattern: {pattern}")
            
            # Try to extract times from cross-day patterns
            if len(match.groups()) >= 4:  # Pattern with times
                try:
                    start_hour_val = int(match.group(1))
                    start_ampm = match.group(2)
                    end_hour_val = int(match.group(3))
                    end_ampm = match.group(4)
                    
                    # Convert to 24-hour
                    if start_ampm == 'pm' and start_hour_val != 12:
                        start_hour_val += 12
                    elif start_ampm == 'am' and start_hour_val == 12:
                        start_hour_val = 0
                        
                    if end_ampm == 'pm' and end_hour_val != 12:
                        end_hour_val += 12
                    elif end_ampm == 'am' and end_hour_val == 12:
                        end_hour_val = 0
                    
                    cross_day_times = (start_hour_val, end_hour_val)
                    logger.info(f"DEBUG: Extracted cross-day times: {start_hour_val} to {end_hour_val}")
                except:
                    pass
            break
    
    for pattern_idx, pattern in enumerate(time_patterns):
        match = re.search(pattern, prompt_lower)
        if match:
            groups = match.groups()
            logger.info(f"DEBUG: Time pattern {pattern_idx} matched: {groups}")
            
            start_hour_val = None
            end_hour_val = None
            
            # Use cross-day times if we found them earlier
            if cross_day_times:
                start_hour_val, end_hour_val = cross_day_times
                logger.info(f"DEBUG: Using pre-extracted cross-day times: {start_hour_val} to {end_hour_val}")
            else:
                # Original parsing logic
                if len(groups) >= 4 and groups[1] and groups[3]:
                    start_hour_val = int(groups[0])
                    start_ampm = groups[1]
                    end_hour_val = int(groups[2])
                    end_ampm = groups[3]
                    
                    # Convert to 24-hour format
                    if start_ampm == 'pm' and start_hour_val != 12:
                        start_hour_val += 12
                    elif start_ampm == 'am' and start_hour_val == 12:
                        start_hour_val = 0
                    
                    if end_ampm == 'pm' and end_hour_val != 12:
                        end_hour_val += 12
                    elif end_ampm == 'am' and end_hour_val == 12:
                        end_hour_val = 0
                        
                elif len(groups) >= 3:
                    start_hour_val = int(groups[0])
                    end_hour_val = int(groups[1 if not groups[1] else 2])
                    end_ampm = groups[-1]
                    
                    if end_ampm == 'pm':
                        if start_hour_val != 12 and start_hour_val < 12:
                            start_hour_val += 12
                        if end_hour_val != 12 and end_hour_val < 12:
                            end_hour_val += 12
                    elif end_ampm == 'am':
                        if start_hour_val == 12:
                            start_hour_val = 0
                        if end_hour_val == 12:
                            end_hour_val = 0
            
            if start_hour_val is not None and end_hour_val is not None:
                result['start_hour'] = f"{start_hour_val:02d}:00"
                result['end_hour'] = f"{end_hour_val:02d}:00"
                
                # Determine if we need both days - CORRECTED LOGIC
                if explicit_cross_day:
                    # Explicitly mentioned cross-day scenario
                    result['needs_both_days'] = True
                    result['time_window'] = f"today {result['start_hour']} to tomorrow {result['end_hour']}"
                    logger.info("DEBUG: Explicit cross-day request detected")
                elif start_hour_val > end_hour_val:
                    # Time range wraps around (e.g., 10PM to 6AM) 
                    if day_context == 'today':
                        # 10PM today to 6AM tomorrow
                        result['needs_both_days'] = True
                        result['time_window'] = f"today {result['start_hour']} to tomorrow {result['end_hour']}"
                        logger.info("DEBUG: Time wrap detected - spans to tomorrow")
                    else:
                        # This is just within tomorrow (shouldn't happen with proper input)
                        result['needs_both_days'] = False
                        result['time_window'] = f"{day_context} {result['start_hour']}-{result['end_hour']}"
                        logger.info("DEBUG: Time wrap within same day")
                else:
                    # Normal time range within single day
                    result['needs_both_days'] = False
                    result['time_window'] = f"{day_context} {result['start_hour']}-{result['end_hour']}"
                    logger.info(f"DEBUG: Single day request for {day_context}")
                
                logger.info(f"DEBUG: Final time extraction - start: {start_hour_val}, end: {end_hour_val}, day_context: {day_context}, spans_days: {result['needs_both_days']}")
                break
    
    logger.info(f"DEBUG: extract_query_parameters returning: {result}")
    return result

def run_agent_workflow(user_prompt: str, output_format: str = "text") -> str:
    """Sets up and runs the full agent workflow for a given user prompt."""
    try:
        query_params = extract_query_parameters(user_prompt)
        city = query_params['city']
        time_window = query_params['time_window']
        needs_both_days = query_params['needs_both_days']
        day = query_params['day']
        start_hour_str = query_params.get('start_hour', '00:00')
        end_hour_str = query_params.get('end_hour', '23:59')
        
        logger.info(f"Extracted parameters: city={city}, time_window={time_window}, day={day}, needs_both_days={needs_both_days}")
        logger.info(f"Time range: {start_hour_str} to {end_hour_str}")
        
        # Check if this is an email scheduling request
        if "schedule" in user_prompt.lower() and "email" in user_prompt.lower():
            # Extract email and time from the prompt
            email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', user_prompt)
            time_match = re.search(r'at\s+(\d{1,2}:\d{2})', user_prompt)
            
            if email_match:
                recipient_email = email_match.group(1)
                scheduled_time = time_match.group(1) if time_match else "06:00"
                
                # IMPORTANT: For email scheduling, we need to use the time parameters we already extracted
                # from the query_params, not default values
                logger.info(f"EMAIL SCHEDULING: Using extracted time parameters from query - start_hour={start_hour_str}, end_hour={end_hour_str}, time_window={time_window}")
                
                # Call the email scheduling function with the extracted time parameters
                result = schedule_daily_email_report.invoke({
                    "city": city,
                    "time_window": time_window,
                    "recipient_email": recipient_email,
                    "scheduled_time": scheduled_time,
                    "start_hour": start_hour_str,
                    "end_hour": end_hour_str
                })
                return result
        
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            return "Error: GOOGLE_API_KEY not found in environment variables"
        
        # Initialize LLM
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash", 
            temperature=0,
            google_api_key=api_key,
            convert_system_message_to_human=True
        )
        
        tools = [
            get_weather_forecast_from_server,
            get_air_quality_from_server,
            generate_overall_score_and_graph,
            schedule_daily_email_report
        ]

        # Get weather data for required days
        today_weather = ""
        tomorrow_weather = ""
        
        if needs_both_days:
            # Cross-day scenario: need both today and tomorrow data
            today_weather = get_weather_forecast_from_server.invoke({"city": city, "granularity": "hourly"})
            logger.info("Retrieved today's weather data for cross-day request")
            
            # For tomorrow's weather, you might need to modify your weather API call
            # This is a placeholder - adjust based on your actual API
            tomorrow_weather = get_weather_forecast_from_server.invoke({"city": city, "granularity": "hourly"})
            logger.info("Retrieved tomorrow's weather data for cross-day request")
            
        elif day == "today":
            # Today only
            today_weather = get_weather_forecast_from_server.invoke({"city": city, "granularity": "hourly"})
            logger.info("Retrieved today's weather data")
            
        elif day == "tomorrow":
            # Tomorrow only - this is the fix for your issue
            # You need to pass a parameter to your weather API to get tomorrow's data
            # The exact implementation depends on your weather API
            tomorrow_weather = get_weather_forecast_from_server.invoke({"city": city, "granularity": "hourly"})
            logger.info("Retrieved tomorrow's weather data only")
        
        # Get air quality data
        aqi_data = get_air_quality_from_server.invoke({"city": city})
        logger.info("Retrieved air quality data")
        
        # Generate analysis using the new tool
        try:
            logger.info(f"DEBUG: Calling generate_overall_score_and_graph with:")
            logger.info(f"  - today_forecast: {'Yes' if today_weather else 'No'}")
            logger.info(f"  - tomorrow_forecast: {'Yes' if tomorrow_weather else 'No'}")
            logger.info(f"  - time_window: {time_window}")
            logger.info(f"  - start_hour: {start_hour_str}, end_hour: {end_hour_str}")
            
            analysis = generate_overall_score_and_graph.invoke({
                "today_forecast": today_weather,
                "tomorrow_forecast": tomorrow_weather,
                "air_quality_forecast": aqi_data,
                "time_window": time_window,
                "start_hour": start_hour_str,
                "end_hour": end_hour_str
            })
            
            # Replace placeholder city with actual city
            analysis = analysis.replace("Unknown City", city)
            return analysis
            
        except Exception as e:
            logger.error(f"Error generating analysis: {e}")
            return f"Error generating analysis: {str(e)}"
        
    except Exception as e:
        logger.error(f"Workflow error: {e}")
        return f"Error in agent workflow: {str(e)}. Please check your configuration and try again."

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
    print("🏃 Running Forecast System Initialized 🏃")
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
                print("\n📊 Processing your request...\n")
                result = run_agent_workflow(user_input)
                print("📊 Result:")
                print("=" * 50)
                print(result)
                print("=" * 50)
            
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()