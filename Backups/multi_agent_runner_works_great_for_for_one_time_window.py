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
        if is_html:
            # Set HTML content
            msg.set_content(body, subtype='html')
        else:
            # Set plain text content
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
        
        # Header section - Plain text with visual emphasis
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
                    lines.append("")  # Just a blank line
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
        
        lines.append("")
        lines.append("Have a great run! 🏃‍♀️🏃‍♂️")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Error in enhanced analysis function: {e}")
        return f"Error generating analysis: {str(e)}"

# ADD THIS FUNCTION to your multi_agent_runner.py file right after the _generate_filtered_analysis function:

def _generate_filtered_analysis_html(
    today_forecast: str = "", 
    tomorrow_forecast: str = "", 
    air_quality_forecast: str = "", 
    time_window: str = "today", 
    start_hour: int = None, 
    end_hour: int = None
) -> str:
    """
    Enhanced version that generates HTML output with proper formatting.
    """
    city = "Unknown City"
    
    logger.info(f"HTML DEBUG: Generating analysis for window: '{time_window}' with hours {start_hour}-{end_hour}")
    
    try:
        # Parse weather data from both days
        today_data = []
        tomorrow_data = []
        
        if today_forecast and "Error" not in today_forecast:
            today_data = parse_weather_data(today_forecast, "today")
            logger.info(f"HTML DEBUG: Parsed {len(today_data)} hours for today")
        
        if tomorrow_forecast and "Error" not in tomorrow_forecast:
            tomorrow_data = parse_weather_data(tomorrow_forecast, "tomorrow")
            logger.info(f"HTML DEBUG: Parsed {len(tomorrow_data)} hours for tomorrow")
        
        # Combine weather data
        all_weather_data = today_data + tomorrow_data
        logger.info(f"HTML DEBUG: Total weather data points: {len(all_weather_data)}")
        
        if not all_weather_data:
            return "<div style='color: red; font-weight: bold;'>Cannot generate score: No weather data available</div>"
        
        # Determine if we need data from both days based on explicit indicators
        spans_days = False
        if start_hour is not None and end_hour is not None:
            logger.info(f"HTML DEBUG: Time filtering requested - start_hour={start_hour}, end_hour={end_hour}")
            if "today" in time_window.lower() and "tomorrow" in time_window.lower():
                spans_days = True
                logger.info("HTML DEBUG: Cross-day detected from explicit today->tomorrow in time_window")
            elif start_hour > end_hour and len(all_weather_data) > 24:
                spans_days = True
                logger.info("HTML DEBUG: Cross-day detected from time wrap with multi-day data")
            else:
                spans_days = False
                logger.info("HTML DEBUG: Single day scenario detected")
        
        # Filter weather data by time range
        if start_hour is not None and end_hour is not None:
            if not (start_hour == 0 and end_hour == 23):
                logger.info(f"HTML DEBUG: CUSTOM TIME RANGE DETECTED - Filtering weather data by time range {start_hour}:00 to {end_hour}:00, spans_days={spans_days}")
                weather_data = filter_weather_by_time_range(all_weather_data, start_hour, end_hour, spans_days)
                logger.info(f"HTML DEBUG: After filtering - kept {len(weather_data)} hours within time range")
            else:
                logger.info("HTML DEBUG: Default time range (0-23) detected - using all weather data")
                weather_data = all_weather_data
        else:
            logger.info("HTML DEBUG: No time filtering requested (None values) - using all weather data")
            weather_data = all_weather_data
        
        if not weather_data:
            return f"<div style='color: orange; font-weight: bold;'>No weather data found for the requested time window {start_hour}:00-{end_hour}:00</div>"

        # Parse AQI data
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
        
        # Determine AQI category and color
        if today_aqi <= 50:
            aqi_category = "Good"
            aqi_color = "#4CAF50"  # Green
        elif today_aqi <= 100:
            aqi_category = "Moderate" 
            aqi_color = "#FF9800"  # Orange
        elif today_aqi <= 150:
            aqi_category = "Unhealthy for Sensitive"
            aqi_color = "#FF5722"  # Deep Orange
        elif today_aqi <= 200:
            aqi_category = "Unhealthy"
            aqi_color = "#F44336"  # Red
        else:
            aqi_category = "Very Unhealthy"
            aqi_color = "#9C27B0"  # Purple

        # Generate HTML output
        html = f"""
        <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 100%;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 25px; text-align: center; border-radius: 10px 10px 0 0; margin-bottom: 0;">
                <h1 style="margin: 0; font-size: 24px; font-weight: bold;">🏃‍♂️ Good Morning! 🏃‍♀️</h1>
                <p style="margin: 15px 0 0 0; font-size: 18px; font-weight: bold;">Here is your running forecast for {city}</p>
            </div>
            
            <div style="background: white; padding: 20px; border: 2px solid #667eea; border-top: none; border-radius: 0 0 10px 10px;">
        """
        
        # Time display - Convert 24-hour format to 12-hour format in the main display
        def format_time_12hour(hour_24):
            if hour_24 == 0:
                return "12:00 AM"
            elif hour_24 < 12:
                return f"{hour_24}:00 AM"
            elif hour_24 == 12:
                return "12:00 PM"
            else:
                return f"{hour_24 - 12}:00 PM"
        
        # Replace 24-hour times with 12-hour times in the time_window string
        formatted_time_window = time_window.upper()
        if start_hour is not None and end_hour is not None:
            # Replace patterns like "19:00" with "7:00 PM" in the time window string
            # Find and replace 24-hour time patterns
            time_pattern = r'(\d{1,2}):00'
            def replace_time(match):
                hour = int(match.group(1))
                return format_time_12hour(hour)
            
            formatted_time_window = re.sub(time_pattern, replace_time, formatted_time_window)
        
        time_display = f"📅 <strong style='font-size: 18px; color: #667eea;'>{formatted_time_window}</strong>"
        
        html += f"""
                <p style="margin: 10px 0; font-size: 16px;">{time_display}</p>
                <p style="margin: 10px 0; font-size: 16px;">
                    🌬️ <strong>Air Quality:</strong> <span style="color: {aqi_color}; font-weight: bold; background-color: {aqi_color}20; padding: 4px 8px; border-radius: 4px;">{today_aqi} ({aqi_category})</span>
                </p>
        """
        
        # MOVED RECOMMENDATIONS TO THE TOP
        best_hours = sorted(scored_hours, key=lambda x: x['score_100'], reverse=True)[:3]
        worst_hours = sorted(scored_hours, key=lambda x: x['score_100'])[:2]
        
        html += """
                <div style="background: linear-gradient(135deg, #E8F5E8, #C8E6C9); border: 3px solid #4CAF50; border-radius: 12px; padding: 25px; margin: 25px 0;">
                    <h2 style="color: #2E7D32; font-weight: bold; margin: 0 0 20px 0; font-size: 22px; text-align: center; text-transform: uppercase; letter-spacing: 1px;">🎯 RECOMMENDATIONS</h2>
        """
        
        # Best time with humidity included
        best_hour = best_hours[0]
        day_text = f" <span style='color: #666;'>({best_hour['Day']})</span>" if spans_days else ""
        
        html += f"""
            <div style="background: linear-gradient(135deg, #C8E6C9, #A5D6A7); border: 2px solid #4CAF50; border-radius: 10px; padding: 20px; margin: 15px 0; box-shadow: 0 3px 6px rgba(0,0,0,0.1);">
                <h3 style="color: #1B5E20; font-weight: bold; margin: 0 0 12px 0; font-size: 18px;">🥇 BEST TIME TO RUN:</h3>
                <p style="margin: 0; font-weight: bold; color: #2E7D32; font-size: 18px;">
                    {best_hour['Hour']}{day_text} - <span style='color: #1B5E20;'>Perfect conditions!</span>
                </p>
                <p style="margin: 12px 0 0 0; color: #2E7D32; font-size: 16px; font-weight: bold;">
                    🌡️ {best_hour['Temp']}°F • 💨 {best_hour['Wind']}mph wind • 🌧️ {best_hour['Precip']}% rain • 💧 {best_hour['Humidity']}% humidity
                </p>
            </div>
        """
        
        # Other good times
        if len(best_hours) > 1:
            html += """
                <div style="margin: 20px 0;">
                    <h3 style="color: #2E7D32; font-weight: bold; margin: 0 0 12px 0; font-size: 16px;">🥈 Other Great Times:</h3>
            """
            for hour in best_hours[1:]:
                day_text = f" <span style='color: #666;'>({hour['Day']})</span>" if spans_days else ""
                html += f"""
                    <p style="margin: 8px 0; color: #2E7D32; font-size: 15px;">
                        • <strong style='color: #1B5E20;'>{hour['Hour']}{day_text}</strong> <span style='background: #4CAF50; color: white; padding: 2px 6px; border-radius: 4px; font-size: 12px;'>({hour['final_score']}/5 stars)</span>
                    </p>
                """
            html += '</div>'
        
        # Warning for poor conditions
        if worst_hours[0]['final_score'] <= 2:
            html += """
                <div style="background: linear-gradient(135deg, #FFEBEE, #FFCDD2); border: 2px solid #F44336; border-radius: 10px; padding: 20px; margin: 20px 0;">
                    <h3 style="color: #C62828; font-weight: bold; margin: 0 0 12px 0; font-size: 16px;">⚠️ TIMES TO AVOID:</h3>
            """
            
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
                    day_text = f" <span style='color: #666;'>({hour['Day']})</span>" if spans_days else ""
                    html += f"""
                        <p style="margin: 8px 0; color: #C62828; font-size: 15px;">
                            ❌ <strong style='color: #B71C1C;'>{hour['Hour']}{day_text}</strong> - <span style='background: #F44336; color: white; padding: 2px 6px; border-radius: 4px; font-size: 12px;'>{reason_text}</span>
                        </p>
                    """
            
            html += '</div>'
        
        html += '</div>'  # Close recommendations div
        
        # NOW THE HOURLY BREAKDOWN
        html += '<div style="margin-top: 25px;">'
        
        # Hourly breakdown with day labels - COMPACT FORMAT
        current_day = None
        for hour in scored_hours:
            # Add day separator if day changes
            if current_day != hour['Day']:
                if current_day is not None:
                    html += '<div style="margin: 20px 0;"></div>'
                html += f"""
                    <h2 style="background: linear-gradient(90deg, #007bff, #0056b3); color: white; padding: 12px 15px; margin: 20px 0 15px 0; border-radius: 8px; font-weight: bold; font-size: 18px; text-transform: uppercase; letter-spacing: 1px;">
                        📅 {hour['Day']}
                    </h2>
                """
                current_day = hour['Day']
            
            # Create star rating
            filled_stars = "⭐" * int(hour['final_score'])
            empty_stars = "☆" * (5 - int(hour['final_score']))
            stars = filled_stars + empty_stars
            
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
            
            # Temperature context
            if hour['Temp'] >= 75:
                temp_context = f"🌡️ <span style='color: #FF6B35; font-weight: bold;'>{hour['Temp']}°F</span>"
            elif hour['Temp'] <= 45:
                temp_context = f"❄️ <span style='color: #4FC3F7; font-weight: bold;'>{hour['Temp']}°F</span>"
            else:
                temp_context = f"🌤️ <span style='color: #4CAF50; font-weight: bold;'>{hour['Temp']}°F</span>"
            
            # Wind context
            if hour['Wind'] > 15:
                wind_context = f"💨 <span style='color: #FF5722; font-weight: bold;'>{hour['Wind']}mph</span>"
            elif hour['Wind'] <= 5:
                wind_context = f"🍃 <span style='color: #4CAF50; font-weight: bold;'>{hour['Wind']}mph</span>"
            else:
                wind_context = f"<span style='font-weight: bold;'>{hour['Wind']}mph</span>"
            
            # Precipitation context
            if hour['Precip'] > 30:
                precip_context = f"🌧️ <span style='color: #2196F3; font-weight: bold;'>{hour['Precip']}%</span>"
            elif hour['Precip'] > 10:
                precip_context = f"☁️ <span style='color: #607D8B; font-weight: bold;'>{hour['Precip']}%</span>"
            elif hour['Precip'] > 0:
                precip_context = f"🌤️ <span style='color: #FFA726;'>{hour['Precip']}%</span>"
            else:
                precip_context = "☀️ <span style='color: #4CAF50; font-weight: bold;'>0%</span>"
            
            # Humidity context
            if hour['Humidity'] > 80:
                humidity_context = f"💧 <span style='color: #2196F3; font-weight: bold;'>{hour['Humidity']}%</span>"
            elif hour['Humidity'] > 60:
                humidity_context = f"💧 <span style='color: #FF9800; font-weight: bold;'>{hour['Humidity']}%</span>"
            else:
                humidity_context = f"💧 <span style='color: #4CAF50; font-weight: bold;'>{hour['Humidity']}%</span>"
            
            # COMPACT SINGLE-LINE FORMAT
            html += f"""
                <div style="background: {score_bg}; border: 2px solid {score_color}; border-radius: 12px; padding: 16px; margin: 12px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap;">
                        <h3 style="margin: 0; font-size: 20px; color: #333; font-weight: bold;">⏰ {hour['Hour']}</h3>
                        <div style="color: {score_color}; font-weight: bold; font-size: 18px; background: white; padding: 6px 12px; border-radius: 20px; border: 2px solid {score_color};">
                            {stars} ({hour['final_score']}/5)
                        </div>
                    </div>
                    <div style="font-size: 15px; font-weight: bold;">
                        {temp_context} • {wind_context} • {precip_context} rain • {humidity_context} humidity
                    </div>
                </div>
            """

        html += '</div>'  # Close hourly breakdown div
        
        # Footer
        html += """
            <div style="text-align: center; padding: 25px; background: linear-gradient(135deg, #F5F5F5, #E0E0E0); border-radius: 10px; margin-top: 25px; border: 2px solid #667eea;">
                <h3 style="margin: 0; color: #333; font-weight: bold; font-size: 18px;">Have a great run! 🏃‍♀️🏃‍♂️</h3>
            </div>
        </div>
        </div>
        """
        
        return html
        
    except Exception as e:
        logger.error(f"Error in HTML analysis function: {e}")
        return f"<div style='color: red; font-weight: bold; font-size: 16px; padding: 20px; border: 2px solid red; border-radius: 8px;'>Error generating analysis: {str(e)}</div>"

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
    end_hour: str = "23:59",
    output_format: str = "text"
) -> str:
    """
    Analyzes environmental data (weather and AQI) to generate a 1-5 score
    for each hour within a specific time range, supporting cross-day scenarios.
    Now supports both text and HTML output formats.
    """
    # Extract numeric hours from HH:MM format
    start_hour_num = int(start_hour.split(':')[0]) if ':' in start_hour else None
    end_hour_num = int(end_hour.split(':')[0]) if ':' in end_hour else None
    
    if output_format.lower() == "html":
        return _generate_filtered_analysis_html(
            today_forecast=today_forecast,
            tomorrow_forecast=tomorrow_forecast,
            air_quality_forecast=air_quality_forecast, 
            time_window=time_window,
            start_hour=start_hour_num,
            end_hour=end_hour_num
        )
    else:
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
            
            # Wrap content in basic HTML structure for proper email rendering
            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .content {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                </style>
            </head>
            <body>
                <div class="content">
                    <p>Good morning!</p>
                    <p>Here is your daily running forecast for {city}:</p>
                    <div>{report_content.replace(chr(10), '<br>')}</div>
                    <hr>
                    <p><small>This is an automated report. Reply to this email if you need assistance.</small></p>
                </div>
            </body>
            </html>
            """
            
            if send_email_notification(recipient_email, subject, html_body, is_html=True):
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

def run_agent_workflow(user_prompt: str, output_format: str = "html") -> str:  # Changed default to HTML
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
                
                logger.info(f"EMAIL SCHEDULING: Using extracted time parameters from query - start_hour={start_hour_str}, end_hour={end_hour_str}, time_window={time_window}")
                
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
        
        # Get weather data for required days
        today_weather = ""
        tomorrow_weather = ""
        
        if needs_both_days:
            today_weather = get_weather_forecast_from_server.invoke({"city": city, "granularity": "hourly"})
            logger.info("Retrieved today's weather data for cross-day request")
            tomorrow_weather = get_weather_forecast_from_server.invoke({"city": city, "granularity": "hourly"})
            logger.info("Retrieved tomorrow's weather data for cross-day request")
        elif day == "today":
            today_weather = get_weather_forecast_from_server.invoke({"city": city, "granularity": "hourly"})
            logger.info("Retrieved today's weather data")
        elif day == "tomorrow":
            tomorrow_weather = get_weather_forecast_from_server.invoke({"city": city, "granularity": "hourly"})
            logger.info("Retrieved tomorrow's weather data only")
        
        # Get air quality data
        aqi_data = get_air_quality_from_server.invoke({"city": city})
        logger.info("Retrieved air quality data")
        
        # Generate analysis using the new tool
        try:
            logger.info(f"DEBUG: Calling generate_overall_score_and_graph with output_format={output_format}")
            
            analysis = generate_overall_score_and_graph.invoke({
                "today_forecast": today_weather,
                "tomorrow_forecast": tomorrow_weather,
                "air_quality_forecast": aqi_data,
                "time_window": time_window,
                "start_hour": start_hour_str,
                "end_hour": end_hour_str,
                "output_format": output_format  # CRITICAL: Pass the output format
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
