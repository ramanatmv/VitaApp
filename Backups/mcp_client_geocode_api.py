import requests
import json

def get_weather_forecast(city_name: str, server_url: str = "http://localhost:8000/get_weather"):
    """
    Client function to get weather forecast from the MCP server.
    """
    payload = {"city": city_name}
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(server_url, data=json.dumps(payload), headers=headers)
        response.raise_for_status()  # Raise an exception for bad status codes

        forecast_data = response.json()
        print(forecast_data.get("forecast", "No forecast data received."))

    except requests.exceptions.RequestException as e:
        print(f"Error connecting to the server: {e}")
    except json.JSONDecodeError:
        print("Error decoding server response. Expected JSON.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    print("Weather Forecast Client")
    print("Enter a city name to get the forecast (e.g., 'New York, NY')")
    while True:
        city = input("City: ")
        if city.lower() in ["exit", "quit"]:
            break
        if city:
            get_weather_forecast(city)
        else:
            print("Please enter a city name.")
