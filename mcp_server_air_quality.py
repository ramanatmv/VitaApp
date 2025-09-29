import os
import requests
import texttable
from datetime import date
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_core.tools import BaseTool
from langchain.pydantic_v1 import BaseModel as LangchainBaseModel, Field
from dotenv import load_dotenv

# Load environment variables for the API key
load_dotenv()

# --- Pydantic Models ---

class AirQualityRequest(BaseModel):
    """Defines the structure for incoming requests to the air quality server."""
    city: str

class GetAirQualityToolInput(LangchainBaseModel):
    """Input schema for the GetAirQualityTool."""
    city: str = Field(description="The city and state, e.g., 'San Francisco, CA'")

# --- Helper Function for Formatting ---

def _format_air_quality_forecast(data: list) -> str:
    """Formats an air quality forecast into a clean text table."""
    if not data:
        return "No air quality data found for the location."

    table = texttable.Texttable()
    table.header(["Date", "AQI", "Category", "Pollutant"])
    table.set_cols_align(["l", "r", "l", "c"])
    table.set_cols_valign(["m", "m", "m", "m"])

    for forecast in data:
        category_name = forecast.get("Category", {}).get("Name", "N/A")
        table.add_row([
            forecast.get('DateForecast', 'N/A'),
            forecast.get('AQI', -1),
            category_name,
            forecast.get('ReportingArea', 'N/A')
        ])
    return table.draw()

# --- LangChain Tool Definition ---

class GetAirQualityTool(BaseTool):
    """Tool to get the air quality forecast for a city."""
    name: str = "get_air_quality_forecast"
    description: str = "Useful for getting the Air Quality Index (AQI) forecast for a specific city."
    args_schema: type[LangchainBaseModel] = GetAirQualityToolInput

    def _run(self, city: str) -> str:
        """Fetches and returns the air quality forecast."""
        api_key = os.getenv("AIRNOW_API_KEY")
        if not api_key:
            return "Error: AIRNOW_API_KEY environment variable not set."
        
        print(f"Air Quality Server received request for city: '{city}'")
        try:
            # 1. Geocode city to get latitude and longitude
            nominatim_url = f"https://nominatim.openstreetmap.org/search?q={city}&format=json&limit=1"
            headers = {'User-Agent': 'LangGraphWeatherApp/1.0'}
            geo_response = requests.get(nominatim_url, headers=headers)
            geo_response.raise_for_status()
            location_data = geo_response.json()

            if not location_data:
                return f"Could not find location: {city}"

            lat = location_data[0]['lat']
            lon = location_data[0]['lon']

            # 2. Get Postal Code from coordinates for better AirNow accuracy
            reverse_url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
            reverse_response = requests.get(reverse_url, headers=headers).json()
            postal_code = reverse_response.get("address", {}).get("postcode")

            if not postal_code:
                 return f"Could not determine postal code for {city} to fetch air quality."

            # 3. Fetch Air Quality from AirNow API using the postal code
            today = date.today().strftime("%Y-%m-%d")
            airnow_url = (
                f"https://www.airnowapi.org/aq/forecast/zipCode/?format=application/json"
                f"&zipCode={postal_code}&date={today}&distance=25&API_KEY={api_key}"
            )
            
            air_response = requests.get(airnow_url)
            air_response.raise_for_status()
            air_data = air_response.json()

            return _format_air_quality_forecast(air_data)

        except requests.exceptions.RequestException as e:
            return f"An error occurred with an external API: {e}"
        except (KeyError, IndexError) as e:
            return f"Error processing API data: {e}"

    def _arun(self, city: str):
        raise NotImplementedError("get_air_quality_forecast does not support async")

# --- FastAPI Server ---
app = FastAPI(
    title="Air Quality Tool MCP Server",
    description="A server that acts as a tool to get Air Quality Index (AQI) forecasts.",
)
air_quality_tool = GetAirQualityTool()

@app.post("/get_air_quality")
async def get_air_quality(request: AirQualityRequest):
    """Endpoint to get the air quality for a given city."""
    try:
        result = air_quality_tool.run(tool_input={"city": request.city})
        return {"forecast": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # It's recommended to run with `uvicorn air_quality_server:app --port 8001 --reload`
    uvicorn.run(app, host="0.0.0.0", port=8001)
