import os
import uvicorn
import requests
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain.tools import BaseTool
from typing import Type
from texttable import Texttable

# --- Configuration ---
# Make sure to set your Google Geocoding API key as an environment variable
# export GOOGLE_API_KEY="YOUR_API_KEY"
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("Google API Key not found. Please set the GOOGLE_API_KEY environment variable.")

# --- Pydantic Models for FastAPI ---
class CityInput(BaseModel):
    city: str

class WeatherOutput(BaseModel):
    forecast: str

# --- Pydantic Model for LangChain Tool Input ---
class ToolInput(BaseModel):
    city: str

# --- LangChain Tool Definition ---
class GetWeatherTool(BaseTool):
    """Tool to get the weather forecast for a given city."""
    name: str = "get_weather_forecast"
    description: str = "Useful for when you need to get the weather forecast for a specific city."
    args_schema: Type[BaseModel] = ToolInput

    def _run(self, city: str):
        """Gets the weather forecast for a city."""
        try:
            # 1. Geocode the city to get latitude and longitude
            geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={city}&key={GOOGLE_API_KEY}"
            
            # --- DEBUGGING: Print the URL being called ---
            print(f"\n--- Calling Geocoding API with URL: {geocode_url} ---\n")

            geocode_response = requests.get(geocode_url)
            geocode_response.raise_for_status()
            geocode_data = geocode_response.json()

            # --- DEBUGGING: Print the full JSON response from Google ---
            print("--- Geocoding API Response ---")
            print(json.dumps(geocode_data, indent=2))
            print("----------------------------\n")

            if not geocode_data["results"]:
                # Check for a specific error message from the API
                error_message = geocode_data.get("error_message")
                if error_message:
                    print(f"!!! Google API Error: {error_message} !!!")
                    return f"Error from Geocoding API: {error_message}"
                return f"Could not find location: {city}"

            location = geocode_data["results"][0]["geometry"]["location"]
            latitude = round(location["lat"], 4)
            longitude = round(location["lng"], 4)

            # 2. Get the forecast endpoint from weather.gov
            points_url = f"https://api.weather.gov/points/{latitude},{longitude}"
            headers = {'User-Agent': '(my-weather-app, myemail@example.com)'}
            points_response = requests.get(points_url, headers=headers)
            points_response.raise_for_status()
            points_data = points_response.json()

            forecast_url = points_data["properties"]["forecast"]

            # 3. Get the actual forecast
            forecast_response = requests.get(forecast_url, headers=headers)
            forecast_response.raise_for_status()
            forecast_data = forecast_response.json()

            # 4. Format the forecast into a table
            periods = forecast_data["properties"]["periods"]
            table = Texttable()
            table.set_deco(Texttable.HEADER)
            table.set_cols_dtype(['t', 't', 't', 't']) 
            table.set_cols_align(['l', 'c', 'c', 'l'])
            table.header(["Day", "Temp", "Wind", "Forecast"])

            for period in periods:
                table.add_row([
                    period["name"],
                    f'{period["temperature"]}°{period["temperatureUnit"]}',
                    f'{period["windSpeed"]} {period["windDirection"]}',
                    period["shortForecast"]
                ])

            return f"Weather forecast for {city}:\n{table.draw()}"

        except requests.exceptions.RequestException as e:
            return f"An error occurred with an API request: {e}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    async def _arun(self, city: str):
        raise NotImplementedError("get_weather_forecast does not support async")

# --- FastAPI Application ---
app = FastAPI(
    title="Model Context Protocol Server for Weather",
    description="An API server that provides weather forecasts for a given city.",
    version="1.0.0",
)

weather_tool = GetWeatherTool()

@app.post("/get_weather", response_model=WeatherOutput)
def get_weather(city_input: CityInput):
    try:
        forecast_result = weather_tool._run(city=city_input.city)
        return WeatherOutput(forecast=forecast_result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {"message": "Welcome to the Weather MCP Server. Use the /get_weather endpoint to get forecasts."}

# --- Main entry point to run the server ---
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)


