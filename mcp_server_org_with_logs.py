import requests
import texttable
import json
import os
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_core.tools import BaseTool
from langchain.pydantic_v1 import BaseModel as LangchainBaseModel, Field
from datetime import datetime, timezone, timedelta

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

# --- Pydantic Models ---

class WeatherRequest(BaseModel):
    """Defines the structure for incoming requests to the server."""
    city: str
    granularity: Optional[str] = 'daily'

class GetWeatherToolInput(LangchainBaseModel):
    """Input schema for the GetWeatherTool."""
    city: str = Field(description="The city and state, e.g., 'San Francisco, CA'")
    granularity: str = Field(default='daily', description="The forecast granularity, either 'daily' or 'hourly'")


# --- Helper Functions for Formatting ---

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

def _format_hourly_forecast(data: dict) -> str:
    """
    CORRECTED: Formats an hourly forecast, providing dew point in both Celsius (raw) and Fahrenheit (converted).
    """
    periods = data.get("properties", {}).get("periods", [])
    if not periods:
        return "No hourly forecast data available."

    table = texttable.Texttable()
    table.header(["Num", "Time", "Temp", "Wind", "WDir", "Forecast", "Precip", "Humidity"])
    table.set_cols_align(["l", "l", "r", "r", "l", "l", "r", "r"])
    table.set_cols_valign(["m", "m", "m", "m", "m", "m", "m", "m"])

    try:
        first_period_dt = datetime.fromisoformat(periods[0].get('startTime', '').replace('Z', '+00:00'))
        local_tz = first_period_dt.tzinfo or timezone.utc

        now_in_forecast_tz = datetime.now(local_tz)
        today_local = now_in_forecast_tz.date()
        tomorrow_local = today_local + timedelta(days=1)
        
        print(f"DEBUG: Forecast timezone detected as {local_tz}")
        print(f"DEBUG: Current time in forecast tz is {now_in_forecast_tz.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"DEBUG: Today's local date: {today_local}, Tomorrow's local date: {tomorrow_local}")

    except (ValueError, IndexError):
        print("DEBUG: Could not determine local timezone from forecast, falling back to UTC.")
        now_utc = datetime.now(timezone.utc)
        today_local = now_utc.date()
        tomorrow_local = today_local + timedelta(days=1)

    print(f"DEBUG: Processing {len(periods)} weather periods")

    period_analysis = []
    
    for i, period in enumerate(periods[:72]):
        start_time = period.get('startTime', '')
        
        time_display = 'N/A'
        hour_num = 'N/A'
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
                time_display = f"{hour_num:02d}:00"
                
                forecast_date = dt.date()
                date_str = dt.strftime('%b %d, %A')
                
                if forecast_date == today_local:
                    day_category = f"TODAY-{date_str}"
                elif forecast_date == tomorrow_local:
                    day_category = f"TOMORROW-{date_str}"
                else:
                    day_category = date_str
                
                period_info['day_category'] = day_category

                hours_from_now = (dt - now_in_forecast_tz).total_seconds() / 3600
                period_info['parsed_hour'] = hour_num
                period_info['hours_from_now'] = round(hours_from_now, 1)

                print(f"DEBUG: Period {i+1:2d}: {start_time} ({forecast_date}) -> Matched as {day_category}")
                
            except ValueError as e:
                print(f"DEBUG: Could not parse time {start_time}: {e}")
                time_display = start_time.split('T')[1].split(':')[0] + ':00' if 'T' in start_time else 'N/A'
                period_info['parse_error'] = str(e)

        # --- MODIFIED SECTION START ---
        # Extract and process values
        precip_data = period.get("probabilityOfPrecipitation", {})
        precip = precip_data.get("value", 0) if precip_data else 0
        precip = precip or 0
        
        humidity_data = period.get("relativeHumidity", {})
        humidity = humidity_data.get("value", 0) if humidity_data else 0
        humidity = humidity or 0

        dewpoint_data = period.get("dewpoint", {})
        dewpoint_c = dewpoint_data.get("value") if dewpoint_data else None
        
        # Convert dew point to Fahrenheit if a value exists
        dewpoint_f = None
        if dewpoint_c is not None:
            dewpoint_f = round((dewpoint_c * 9/5) + 32)

        # Add all values to the JSON object, including both dew point units
        period_info['precipitation'] = precip
        period_info['humidity'] = humidity
        period_info['dewpoint_celsius'] = dewpoint_c
        period_info['dewpoint_fahrenheit'] = dewpoint_f
        # --- MODIFIED SECTION END ---

        period_analysis.append(period_info)
        
        wind_speed_raw = period.get('windSpeed', 'N/A')
        wind_speed_clean = 'N/A'
        if wind_speed_raw != 'N/A':
            import re
            wind_match = re.search(r'(\d+)', str(wind_speed_raw))
            if wind_match:
                wind_match.group(1)

        table.add_row([
            i + 1,
            time_display,
            f"{period.get('temperature', 'N/A')}°{period.get('temperatureUnit', 'F')}",
            wind_speed_clean,
            period.get('windDirection', ''),
            period.get('shortForecast', 'N/A'),
            f"{precip}",
            f"{humidity}"
        ])
    
    analysis_log_file = f"api_logs/period_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(analysis_log_file, 'w') as f:
        json.dump({
            'current_time_local': now_in_forecast_tz.isoformat(),
            'total_periods_received': len(periods),
            'processed_periods': len(period_analysis),
            'period_details': period_analysis
        }, f, indent=2)
    
    print(f"Period analysis logged to: {analysis_log_file}")
    
    forecast_json = {
        "properties": { "periods": period_analysis }
    }
    return json.dumps(forecast_json, indent=2)


# --- LangChain Tool Definition (for server-side logic) ---

class GetWeatherTool(BaseTool):
    """Tool to get the weather forecast."""
    name: str = "get_weather_forecast"
    description: str = "Useful for when you need to get the weather forecast for a specific city. Can provide 'daily' or 'hourly' forecasts."
    args_schema: type[LangchainBaseModel] = GetWeatherToolInput

    def _run(self, city: str, granularity: str = 'daily') -> str:
        """Fetches and returns the weather forecast."""
        print(f"Server received request for city: '{city}', granularity: '{granularity}'")
        try:
            # 1. Geocode the city using OpenStreetMap Nominatim
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

            # 2. Get the weather gridpoint from weather.gov
            points_url = f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
            points_response = requests.get(points_url, headers=headers).json()
            
            properties = points_response.get("properties", {})

            # 3. Choose the correct forecast URL based on granularity
            if granularity == 'hourly':
                forecast_url = properties.get("forecastHourly")
                formatter = _format_hourly_forecast
            else: # Default to daily
                forecast_url = properties.get("forecast")
                formatter = _format_daily_forecast

            if not forecast_url:
                return f"Could not find '{granularity}' forecast URL for the given coordinates."

            # 4. Fetch the actual forecast
            print(f"DEBUG: Fetching forecast from: {forecast_url}")
            forecast_response = requests.get(forecast_url, headers=headers)
            forecast_data = forecast_response.json()

            # DEBUG: Log how many periods we received
            periods = forecast_data.get("properties", {}).get("periods", [])
            print(f"DEBUG: Received {len(periods)} forecast periods from weather.gov")
            
            # Log complete API response for analysis
            log_api_response(city, granularity, forecast_data, "")

            # 5. Format and return the forecast
            formatted_forecast = formatter(forecast_data)
            
            # Update the log file with formatted output
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            formatted_log_file = f"api_logs/{granularity}_{city.replace(' ', '_').replace(',', '_')}_{timestamp}_formatted.txt"
            if os.path.exists(formatted_log_file):
                with open(formatted_log_file, 'a') as f:
                    f.write(f"\n\nFORMATTED TABLE:\n{formatted_forecast}")
            
            return formatted_forecast

        except requests.exceptions.RequestException as e:
            error_msg = f"An error occurred with an external API: {e}"
            print(f"ERROR: {error_msg}")
            return error_msg
        except (KeyError, IndexError, ValueError) as e:
            error_msg = f"Error processing weather data: {e}"
            print(f"ERROR: {error_msg}")
            return error_msg

    def _arun(self, city: str, granularity: str = 'daily'):
        raise NotImplementedError("get_weather_forecast does not support async")

# --- FastAPI Server ---

app = FastAPI(
    title="Weather Tool MCP Server",
    description="A server that acts as a tool for a LangGraph agent to get weather forecasts.",
)
weather_tool = GetWeatherTool()

@app.post("/get_weather")
async def get_weather(request: WeatherRequest):
    """Endpoint to get the weather forecast for a given city."""
    try:
        # Use the tool's run method to handle the logic
        result = weather_tool.run(tool_input={"city": request.city, "granularity": request.granularity})
        return {"forecast": result}
    except Exception as e:
        error_msg = f"Server error: {str(e)}"
        print(f"ERROR: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)

if __name__ == "__main__":
    import uvicorn
    # This block is for direct execution, but it's recommended to run with `uvicorn mcp_server:app --reload`
    uvicorn.run(app, host="0.0.0.0", port=8000)