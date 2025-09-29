import requests
import texttable
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_core.tools import BaseTool
from langchain.pydantic_v1 import BaseModel as LangchainBaseModel, Field
from datetime import datetime, timezone

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
    CORRECTED: Formats an hourly weather forecast for 48 hours (2 days) 
    with proper column mapping for the parsing code.
    """
    periods = data.get("properties", {}).get("periods", [])
    if not periods:
        return "No hourly forecast data available."

    table = texttable.Texttable()
    # Column order matches what the parsing code expects
    table.header(["Num", "Time", "Temp", "Wind", "WDir", "Forecast", "Precip", "Humidity"])
    table.set_cols_align(["l", "l", "r", "r", "l", "l", "r", "r"])
    table.set_cols_valign(["m", "m", "m", "m", "m", "m", "m", "m"])

    # DEBUG: Log current time for reference
    current_time = datetime.now()
    print(f"DEBUG: Current time is {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"DEBUG: Processing {len(periods)} weather periods")

    # CORRECTED: Process 48 hours instead of just 24 to get both today and tomorrow
    # Weather.gov typically returns 156 hours, we'll take first 48 (2 days)
    for i, period in enumerate(periods[:48]):  
        start_time = period.get('startTime', '')
        
        # Enhanced time parsing with better debugging
        time_display = 'N/A'
        hour_num = 'N/A'
        
        if 'T' in start_time:
            try:
                # Parse the ISO timestamp
                dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                hour_num = dt.hour
                time_display = f"{hour_num:02d}:00"
                
                # DEBUG: Show what hour we're processing
                day_label = "TODAY" if i < 24 else "TOMORROW"
                print(f"DEBUG: Period {i+1:2d}: {start_time} -> Hour {hour_num:2d} ({time_display}) - {day_label}")
                
            except ValueError as e:
                print(f"DEBUG: Could not parse time {start_time}: {e}")
                time_display = start_time.split('T')[1].split(':')[0] + ':00' if 'T' in start_time else 'N/A'
        
        # Extract precipitation and humidity with better error handling
        precip_data = period.get("probabilityOfPrecipitation", {})
        precip = precip_data.get("value", 0) if precip_data else 0
        precip = precip or 0  # Handle None values
        
        humidity_data = period.get("relativeHumidity", {})
        humidity = humidity_data.get("value", 0) if humidity_data else 0
        humidity = humidity or 0  # Handle None values

        # Extract wind speed properly - handle cases like "5 mph", "10 to 15 mph"
        wind_speed_raw = period.get('windSpeed', 'N/A')
        wind_speed_clean = 'N/A'
        if wind_speed_raw != 'N/A':
            # Extract first number from wind speed string
            import re
            wind_match = re.search(r'(\d+)', str(wind_speed_raw))
            if wind_match:
                wind_speed_clean = wind_match.group(1)

        table.add_row([
            i + 1,                                # Column 0: Num (sequential number)
            time_display,                         # Column 1: Time ✓
            f"{period.get('temperature', 'N/A')}°{period.get('temperatureUnit', 'F')}", # Column 2: Temp ✓
            wind_speed_clean,                     # Column 3: Wind ✓ (CORRECTED: Just the number)
            period.get('windDirection', ''),      # Column 4: WDir 
            period.get('shortForecast', 'N/A'),   # Column 5: Forecast ✓
            f"{precip}",                          # Column 6: Precip ✓ (CORRECTED: No % symbol)
            f"{humidity}"                         # Column 7: Humidity ✓ (CORRECTED: No % symbol)
        ])
    
    print(f"DEBUG: Formatted {min(48, len(periods))} hours into table")
    return table.draw()


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
            forecast_data = requests.get(forecast_url, headers=headers).json()

            # DEBUG: Log how many periods we received
            periods = forecast_data.get("properties", {}).get("periods", [])
            print(f"DEBUG: Received {len(periods)} forecast periods from weather.gov")

            # 5. Format and return the forecast
            formatted_forecast = formatter(forecast_data)
            return formatted_forecast

        except requests.exceptions.RequestException as e:
            return f"An error occurred with an external API: {e}"
        except (KeyError, IndexError, ValueError) as e:
            return f"Error processing weather data: {e}"

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
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # This block is for direct execution, but it's recommended to run with `uvicorn mcp_server:app --reload`
    uvicorn.run(app, host="0.0.0.0", port=8000)