# CORRECTED MCP_SERVER.PY - Fixes import and class definition issues

import requests
import texttable
import json
import os
from typing import Optional, Dict, Tuple
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field  # Fixed: Use pydantic v2 directly
from langchain_core.tools import BaseTool
from datetime import datetime, timezone, timedelta, date
import math

# Create logs directory if it doesn't exist
if not os.path.exists("api_logs"):
    os.makedirs("api_logs")

def log_api_response(city: str, api_type: str, response_data: dict, formatted_output: str):
    """Log the complete API response and formatted output to files."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Log raw API response
    raw_log_file = f"api_logs/{api_type}_{city.replace(' ', '_').replace(',', '_')}_{timestamp}_raw.json"
    with open(raw_log_file, 'w') as f:
        json.dump(response_data, f, indent=2, default=str)
    
    # Log formatted output
    formatted_log_file = f"api_logs/{api_type}_{city.replace(' ', '_').replace(',', '_')}_{timestamp}_formatted.txt"
    with open(formatted_log_file, 'w') as f:
        f.write(f"=== API CALL LOG ===\n")
        f.write(f"City: {city}\n")
        f.write(f"API Type: {api_type}\n") 
        f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Current Hour: {datetime.now().hour}\n")
        f.write(f"===================\n\n")
        f.write("FORMATTED OUTPUT:\n")
        f.write(formatted_output)
        f.write(f"\n\n=== RAW PERIODS COUNT ===\n")
        periods = response_data.get("properties", {}).get("periods", [])
        f.write(f"Total periods received: {len(periods)}\n")
        f.write(f"First period: {periods[0] if periods else 'None'}\n")
        f.write(f"Last period: {periods[-1] if periods else 'None'}\n")
    
    print(f"API Response logged to: {raw_log_file} and {formatted_log_file}")

# ==============================================================================
# SUNRISE/SUNSET FUNCTIONS
# ==============================================================================

def get_sunrise_sunset_api(lat: float, lon: float, target_date: date) -> Optional[Dict[str, datetime]]:
    """Get sunrise/sunset times from the free sunrise-sunset.org API."""
    try:
        date_str = target_date.strftime('%Y-%m-%d')
        url = f"https://api.sunrise-sunset.org/json?lat={lat}&lng={lon}&date={date_str}&formatted=0"
        
        headers = {'User-Agent': 'WeatherRunningApp/1.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data['status'] == 'OK':
            return {
                'sunrise': datetime.fromisoformat(data['results']['sunrise'].replace('Z', '+00:00')),
                'sunset': datetime.fromisoformat(data['results']['sunset'].replace('Z', '+00:00')),
                'civil_twilight_begin': datetime.fromisoformat(data['results']['civil_twilight_begin'].replace('Z', '+00:00')),
                'civil_twilight_end': datetime.fromisoformat(data['results']['civil_twilight_end'].replace('Z', '+00:00')),
                'source': 'api'
            }
        else:
            print(f"Sunrise API error: {data.get('status', 'unknown')}")
            return None
            
    except Exception as e:
        print(f"Error fetching sunrise/sunset from API: {e}")
        return None

def calculate_sunrise_sunset_astronomical(lat: float, lon: float, target_date: date) -> Dict[str, datetime]:
    """Fallback astronomical calculation for sunrise/sunset times."""
    try:
        # Simplified solar calculation
        day_of_year = target_date.timetuple().tm_yday
        
        # Solar declination (approximate)
        declination = 23.45 * math.sin(math.radians(360 * (284 + day_of_year) / 365))
        
        # Hour angle
        lat_rad = math.radians(lat)
        decl_rad = math.radians(declination)
        
        try:
            hour_angle = math.acos(-math.tan(lat_rad) * math.tan(decl_rad))
        except ValueError:
            # Handle polar day/night
            hour_angle = math.pi if declination * lat < 0 else 0
        
        # Convert to hours
        hour_angle_hours = math.degrees(hour_angle) / 15
        
        # Solar noon (approximate)
        solar_noon = 12.0 - (lon / 15.0)
        
        sunrise_hour = solar_noon - hour_angle_hours
        sunset_hour = solar_noon + hour_angle_hours
        
        # Create datetime objects
        base_date = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        sunrise_utc = base_date + timedelta(hours=sunrise_hour)
        sunset_utc = base_date + timedelta(hours=sunset_hour)
        
        return {
            'sunrise': sunrise_utc,
            'sunset': sunset_utc,
            'civil_twilight_begin': sunrise_utc - timedelta(minutes=30),
            'civil_twilight_end': sunset_utc + timedelta(minutes=30),
            'source': 'calculation'
        }
        
    except Exception as e:
        print(f"Error in astronomical calculation: {e}")
        # Conservative defaults
        base_date = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        sunrise_default = base_date + timedelta(hours=11)  # 11 UTC ≈ 6-7 AM local
        sunset_default = base_date + timedelta(hours=23)   # 23 UTC ≈ 6-7 PM local
        
        return {
            'sunrise': sunrise_default,
            'sunset': sunset_default,
            'civil_twilight_begin': sunrise_default - timedelta(minutes=30),
            'civil_twilight_end': sunset_default + timedelta(minutes=30),
            'source': 'default'
        }

def get_sun_times_with_fallback(lat: float, lon: float, target_date: date) -> Dict[str, datetime]:
    """Get sunrise/sunset times with API first, astronomical calculation as fallback."""
    sun_times = get_sunrise_sunset_api(lat, lon, target_date)
    if sun_times is None:
        print(f"Using astronomical calculation for {target_date}")
        sun_times = calculate_sunrise_sunset_astronomical(lat, lon, target_date)
    return sun_times

def is_solar_time(dt: datetime, sun_times: Dict[str, datetime], local_tz: timezone) -> Tuple[bool, str]:
    """
    Determine if a given datetime falls within solar hours.
    FIXED: Properly handles timezone conversion and date boundaries.
    """
    # Convert all times to the same timezone
    sunrise_local = sun_times['sunrise'].astimezone(local_tz)
    sunset_local = sun_times['sunset'].astimezone(local_tz)
    civil_begin_local = sun_times['civil_twilight_begin'].astimezone(local_tz)
    civil_end_local = sun_times['civil_twilight_end'].astimezone(local_tz)
    
    # Ensure dt is in local timezone
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=local_tz)
    elif dt.tzinfo != local_tz:
        dt = dt.astimezone(local_tz)
    
    # Debug logging
    print(f"DEBUG SOLAR: Checking {dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"DEBUG SOLAR: Civil begin: {civil_begin_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"DEBUG SOLAR: Sunrise: {sunrise_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"DEBUG SOLAR: Sunset: {sunset_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"DEBUG SOLAR: Civil end: {civil_end_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    # FIXED: Check if we're dealing with cross-day sunset times
    # If sunset is on a different date than sunrise, we need special handling
    if sunset_local.date() > sunrise_local.date():
        # Cross-midnight scenario - sunset is tomorrow
        if dt.date() == sunrise_local.date():
            # Same day as sunrise - check normal pattern
            if dt < civil_begin_local:
                return False, "night"
            elif dt < sunrise_local:
                return False, "civil_twilight_dawn"
            elif dt < sunset_local:
                return True, "daylight"
            elif dt < civil_end_local:
                return False, "civil_twilight_dusk"
            else:
                return False, "night"
        elif dt.date() == sunset_local.date():
            # Same day as sunset - check if before sunset
            if dt < sunset_local:
                return True, "daylight"
            elif dt < civil_end_local:
                return False, "civil_twilight_dusk"
            else:
                return False, "night"
        else:
            # Different day entirely
            return False, "night"
    else:
        # Normal same-day sunrise/sunset
        if dt < civil_begin_local:
            return False, "night"
        elif dt < sunrise_local:
            return False, "civil_twilight_dawn"
        elif dt < sunset_local:
            return True, "daylight"
        elif dt < civil_end_local:
            return False, "civil_twilight_dusk"
        else:
            return False, "night"

def get_solar_adjustment_enhanced(forecast: str, dt: datetime, temperature: float, sun_times: Dict[str, datetime], local_tz: timezone) -> Tuple[float, str]:
    """Enhanced solar adjustment using actual sunrise/sunset times."""
    is_solar, phase = is_solar_time(dt, sun_times, local_tz)
    forecast_lower = str(forecast).lower()
    
    if phase == "night":
        if 'clear' in forecast_lower or 'mostly clear' in forecast_lower:
            return 5.0, "Clear night skies aid radiative cooling"
        elif 'cloudy' in forecast_lower or 'overcast' in forecast_lower:
            return 4.5, "Cloudy night skies trap heat slightly"
        else:
            return 5.0, "Nighttime conditions"
    
    elif phase in ["civil_twilight_dawn", "civil_twilight_dusk"]:
        if 'clear' in forecast_lower:
            return 4.8, "Twilight with clear skies - minimal solar effect"
        else:
            return 5.0, "Twilight conditions"
    
    else:  # daylight
        if 'sunny' in forecast_lower or ('clear' in forecast_lower and 'mostly' not in forecast_lower):
            if temperature > 80:
                solar_penalty = min(1.5, (temperature - 80) * 0.05)
                return max(3.0, 5.0 - solar_penalty), f"Direct sun adds significant heat load at {temperature}°F"
            elif temperature > 70:
                solar_penalty = min(1.0, (temperature - 70) * 0.03)
                return max(3.5, 5.0 - solar_penalty), f"Sunny conditions increase effective temperature"
            else:
                return 4.5, "Sunny but cool conditions"
        
        elif 'partly sunny' in forecast_lower or 'mostly sunny' in forecast_lower:
            if temperature > 75:
                return 4.0, "Mostly sunny conditions with some heat effect"
            else:
                return 4.5, "Mostly sunny conditions"
        
        elif 'partly cloudy' in forecast_lower:
            return 4.8, "Mixed sun and clouds - variable solar effect"
        
        elif 'cloudy' in forecast_lower or 'overcast' in forecast_lower:
            if temperature > 75:
                return 5.0, "Cloud cover provides beneficial relief from direct sun"
            else:
                return 5.0, "Overcast conditions eliminate solar heat gain"
        
        else:
            return 4.5, "Daytime conditions with unknown cloud cover"

# ==============================================================================
# PYDANTIC MODELS - Fixed to use v2 directly
# ==============================================================================

class WeatherRequest(BaseModel):
    """Defines the structure for incoming requests to the server."""
    city: str
    granularity: Optional[str] = 'daily'

class GetWeatherToolInput(BaseModel):  # Fixed: Use pydantic directly
    """Input schema for the GetWeatherTool."""
    city: str = Field(description="The city and state, e.g., 'San Francisco, CA'")
    granularity: str = Field(default='daily', description="The forecast granularity, either 'daily' or 'hourly'")

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def _format_daily_forecast(data: dict) -> str:
    """Formats a daily weather forecast into a clean text table."""
    periods = data.get("properties", {}).get("periods", [])
    if not periods:
        return "No daily forecast data available."

    table = texttable.Texttable()
    table.header(["Day", "Temp", "Wind", "Forecast"])
    table.set_cols_align(["l", "r", "l", "l"])
    table.set_cols_valign(["m", "m", "m", "m"])

    for period in periods:
        table.add_row([
            period.get('name', 'N/A'),
            f"{period.get('temperature', 'N/A')}°{period.get('temperatureUnit', 'F')}",
            f"{period.get('windSpeed', 'N/A')} {period.get('windDirection', '')}".strip(),
            period.get('shortForecast', 'N/A')
        ])
    return table.draw()

def _format_hourly_forecast_with_solar(data: dict, lat: float, lon: float) -> str:
    """Enhanced hourly forecast with solar timing data."""
    periods = data.get("properties", {}).get("periods", [])
    if not periods:
        return "No hourly forecast data available."

    # Get timezone and dates
    try:
        first_period_dt = datetime.fromisoformat(periods[0].get('startTime', '').replace('Z', '+00:00'))
        local_tz = first_period_dt.tzinfo or timezone.utc

        now_in_forecast_tz = datetime.now(local_tz)
        today_local = now_in_forecast_tz.date()
        tomorrow_local = today_local + timedelta(days=1)
        
        print(f"DEBUG: Forecast timezone detected as {local_tz}")
        
        # Get sunrise/sunset data
        today_sun_times = get_sun_times_with_fallback(lat, lon, today_local)
        tomorrow_sun_times = get_sun_times_with_fallback(lat, lon, tomorrow_local)
        
        print(f"DEBUG: Today sunrise: {today_sun_times['sunrise'].astimezone(local_tz).strftime('%H:%M')}")
        print(f"DEBUG: Today sunset: {today_sun_times['sunset'].astimezone(local_tz).strftime('%H:%M')}")

    except (ValueError, IndexError):
        print("DEBUG: Could not determine timezone, using UTC")
        now_utc = datetime.now(timezone.utc)
        today_local = now_utc.date()
        tomorrow_local = today_local + timedelta(days=1)
        local_tz = timezone.utc
        
        today_sun_times = calculate_sunrise_sunset_astronomical(40.0, -75.0, today_local)
        tomorrow_sun_times = calculate_sunrise_sunset_astronomical(40.0, -75.0, tomorrow_local)

    period_analysis = []
    
    for i, period in enumerate(periods[:72]):
        start_time = period.get('startTime', '')
        
        period_info = {
            'index': i + 1,
            'raw_start_time': start_time,
            'temperature': period.get('temperature', 'N/A'),
            'wind_speed': period.get('windSpeed', 'N/A'),
            'forecast': period.get('shortForecast', 'N/A')
        }
        
        if 'T' in start_time:
            try:
                dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                hour_num = dt.hour
                
                forecast_date = dt.date()
                date_str = dt.strftime('%b %d, %A')
                
                # Determine sun times to use
                if forecast_date == today_local:
                    day_category = f"TODAY-{date_str}"
                    sun_times = today_sun_times
                elif forecast_date == tomorrow_local:
                    day_category = f"TOMORROW-{date_str}"
                    sun_times = tomorrow_sun_times
                else:
                    day_category = date_str
                    sun_times = get_sun_times_with_fallback(lat, lon, forecast_date)
                
                period_info['day_category'] = day_category
                period_info['parsed_hour'] = hour_num
                
                hours_from_now = (dt - now_in_forecast_tz).total_seconds() / 3600
                period_info['hours_from_now'] = round(hours_from_now, 1)

                # Add solar phase information
                is_solar, phase = is_solar_time(dt, sun_times, local_tz)
                period_info['is_solar_time'] = is_solar
                period_info['solar_phase'] = phase
                
                # Add enhanced solar score
                temp = period.get('temperature', 70)
                solar_score, solar_explanation = get_solar_adjustment_enhanced(
                    period.get('shortForecast', ''), dt, temp, sun_times, local_tz
                )
                period_info['solar_score'] = round(solar_score, 2)
                period_info['solar_explanation'] = solar_explanation
                
                print(f"DEBUG: Period {i+1:2d}: {hour_num:02d}:00 -> {phase} (solar_score: {solar_score:.1f})")
                
            except ValueError as e:
                print(f"DEBUG: Could not parse time {start_time}: {e}")
                period_info['parse_error'] = str(e)

        # Extract weather data
        precip_data = period.get("probabilityOfPrecipitation", {})
        precip = precip_data.get("value", 0) if precip_data else 0
        precip = precip or 0
        
        humidity_data = period.get("relativeHumidity", {})
        humidity = humidity_data.get("value", 0) if humidity_data else 0
        humidity = humidity or 0

        dewpoint_data = period.get("dewpoint", {})
        dewpoint_c = dewpoint_data.get("value") if dewpoint_data else None
        
        dewpoint_f = None
        if dewpoint_c is not None:
            dewpoint_f = round((dewpoint_c * 9/5) + 32)

        period_info['precipitation'] = precip
        period_info['humidity'] = humidity
        period_info['dewpoint_celsius'] = dewpoint_c
        period_info['dewpoint_fahrenheit'] = dewpoint_f

        period_analysis.append(period_info)
    
    # Enhanced logging with solar data including LOCAL times
    analysis_log_file = f"api_logs/period_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(analysis_log_file, 'w') as f:
        json.dump({
            'current_time_local': now_in_forecast_tz.isoformat(),
            'coordinates': {'lat': lat, 'lon': lon},
            'timezone_info': {
                'local_timezone': str(local_tz),
                'utc_offset_hours': local_tz.utcoffset(datetime.now()).total_seconds() / 3600
            },
            'sun_times_today': {
                'sunrise_utc': today_sun_times['sunrise'].isoformat(),
                'sunset_utc': today_sun_times['sunset'].isoformat(),
                'sunrise_local': today_sun_times['sunrise'].astimezone(local_tz).isoformat(),
                'sunset_local': today_sun_times['sunset'].astimezone(local_tz).isoformat(),
                'civil_twilight_begin_utc': today_sun_times['civil_twilight_begin'].isoformat(),
                'civil_twilight_end_utc': today_sun_times['civil_twilight_end'].isoformat(),
                'civil_twilight_begin_local': today_sun_times['civil_twilight_begin'].astimezone(local_tz).isoformat(),
                'civil_twilight_end_local': today_sun_times['civil_twilight_end'].astimezone(local_tz).isoformat(),
                'source': today_sun_times['source']
            },
            'sun_times_tomorrow': {
                'sunrise_utc': tomorrow_sun_times['sunrise'].isoformat(),
                'sunset_utc': tomorrow_sun_times['sunset'].isoformat(),
                'sunrise_local': tomorrow_sun_times['sunrise'].astimezone(local_tz).isoformat(),
                'sunset_local': tomorrow_sun_times['sunset'].astimezone(local_tz).isoformat(),
                'civil_twilight_begin_utc': tomorrow_sun_times['civil_twilight_begin'].isoformat(),
                'civil_twilight_end_utc': tomorrow_sun_times['civil_twilight_end'].isoformat(),
                'civil_twilight_begin_local': tomorrow_sun_times['civil_twilight_begin'].astimezone(local_tz).isoformat(),
                'civil_twilight_end_local': tomorrow_sun_times['civil_twilight_end'].astimezone(local_tz).isoformat(),
                'source': tomorrow_sun_times['source']
            },
            'total_periods_received': len(periods),
            'processed_periods': len(period_analysis),
            'period_details': period_analysis
        }, f, indent=2)
    
    print(f"Enhanced period analysis with solar data logged to: {analysis_log_file}")
    
    forecast_json = {
        "properties": { "periods": period_analysis }
    }
    return json.dumps(forecast_json, indent=2)

# ==============================================================================
# LANGCHAIN TOOL DEFINITION
# ==============================================================================

class GetWeatherTool(BaseTool):
    """Tool to get the weather forecast."""
    name: str = "get_weather_forecast"
    description: str = "Useful for when you need to get the weather forecast for a specific city. Can provide 'daily' or 'hourly' forecasts."
    args_schema: type[BaseModel] = GetWeatherToolInput  # Fixed: Use BaseModel directly

    def _run(self, city: str, granularity: str = 'daily') -> str:
        """Fetches and returns the weather forecast."""
        print(f"Server received request for city: '{city}', granularity: '{granularity}'")
        try:
            # Geocode the city
            nominatim_url = f"https://nominatim.openstreetmap.org/search?q={city}&format=json&limit=1"
            headers = {'User-Agent': 'LangGraphWeatherApp/1.0'}
            response = requests.get(nominatim_url, headers=headers)
            response.raise_for_status()
            location_data = response.json()

            if not location_data:
                return f"Could not find location: {city}"

            lat = float(location_data[0]['lat'])
            lon = float(location_data[0]['lon'])
            print(f"Found coordinates for {city}: Lat={lat:.4f}, Lon={lon:.4f}")

            # Get weather gridpoint
            points_url = f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
            points_response = requests.get(points_url, headers=headers).json()
            properties = points_response.get("properties", {})

            # Choose formatter based on granularity
            if granularity == 'hourly':
                forecast_url = properties.get("forecastHourly")
                # Use enhanced formatter with solar data
                formatter = lambda data: _format_hourly_forecast_with_solar(data, lat, lon)
            else:
                forecast_url = properties.get("forecast")
                formatter = _format_daily_forecast

            if not forecast_url:
                return f"Could not find '{granularity}' forecast URL for the given coordinates."

            # Fetch forecast
            print(f"DEBUG: Fetching forecast from: {forecast_url}")
            forecast_response = requests.get(forecast_url, headers=headers)
            forecast_data = forecast_response.json()

            periods = forecast_data.get("properties", {}).get("periods", [])
            print(f"DEBUG: Received {len(periods)} forecast periods from weather.gov")
            
            log_api_response(city, granularity, forecast_data, "")

            # Format and return
            formatted_forecast = formatter(forecast_data)
            return formatted_forecast

        except Exception as e:
            error_msg = f"An error occurred: {e}"
            print(f"ERROR: {error_msg}")
            return error_msg

    def _arun(self, city: str, granularity: str = 'daily'):
        raise NotImplementedError("get_weather_forecast does not support async")

# ==============================================================================
# FASTAPI SERVER
# ==============================================================================

app = FastAPI(
    title="Weather Tool MCP Server",
    description="A server that acts as a tool for a LangGraph agent to get weather forecasts.",
)

# Use the corrected tool class
weather_tool = GetWeatherTool()

@app.post("/get_weather")
async def get_weather(request: WeatherRequest):
    """Endpoint to get the weather forecast for a given city."""
    try:
        result = weather_tool.run(tool_input={"city": request.city, "granularity": request.granularity})
        return {"forecast": result}
    except Exception as e:
        error_msg = f"Server error: {str(e)}"
        print(f"ERROR: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)