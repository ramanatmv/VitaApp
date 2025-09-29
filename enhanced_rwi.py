# Enhanced Running Weather Index - Scientifically-Based Algorithm
import math

def calculate_heat_index(temp_f, humidity_percent):
    """
    Calculate heat index using the National Weather Service formula
    Based on Rothfusz equation - scientifically validated for exercise physiology
    """
    T = temp_f
    R = humidity_percent
    
    # Simple formula for initial approximation
    HI = 0.5 * (T + 61.0 + ((T - 68.0) * 1.2) + (R * 0.094))
    
    # If heat index > 80°F, use more accurate Rothfusz equation
    if HI >= 80:
        HI = (-42.379 + 
              2.04901523 * T + 
              10.14333127 * R - 
              0.22475541 * T * R - 
              6.83783e-3 * T**2 - 
              5.481717e-2 * R**2 + 
              1.22874e-3 * T**2 * R + 
              8.5282e-4 * T * R**2 - 
              1.99e-6 * T**2 * R**2)
    
    return HI

def parse_float(wind_str):
    """Parse wind speed from string like '5 mph'"""
    if isinstance(wind_str, (int, float)):
        return float(wind_str)
    return float(wind_str.split()[0]) if wind_str else 0

def calculate_rwi(temperature, humidity, wind_speed, precipitation, forecast, dewpoint_fahrenheit):
    """
    Calculate Running Weather Index using scientifically-enhanced approach
    
    Args:
        temperature: Temperature in °F
        humidity: Relative humidity in %
        wind_speed: Wind speed (mph or string like "5 mph")
        precipitation: Precipitation chance/intensity (%)
        forecast: Weather condition string (e.g., "Sunny", "Cloudy", "Overcast")
        dewpoint_fahrenheit: Dewpoint in °F
    
    Returns:
        dict: Contains RWI score (1-5), rating, and component scores
    """
    
    # Parse inputs
    T = temperature
    H = humidity
    V = parse_float(wind_speed)
    P = precipitation
    D = dewpoint_fahrenheit
    
    # Calculate heat index (primary thermal comfort metric)
    heat_index = calculate_heat_index(T, H)
    
    # 1. THERMAL COMFORT SCORE (S_H) - Based on Heat Index
    # Optimal running temperature research: 45-60°F actual, but heat index accounts for humidity
    if heat_index <= 65:
        S_H = 5
    elif heat_index <= 75:
        S_H = 4.5 - (heat_index - 65) * 0.05  # Gradual decline
    elif heat_index <= 85:
        S_H = 4 - (heat_index - 75) * 0.2     # Faster decline
    elif heat_index <= 95:
        S_H = 2 - (heat_index - 85) * 0.05    # Moderate decline
    elif heat_index <= 105:
        S_H = 1.5 - (heat_index - 95) * 0.05  # Approaching dangerous
    else:
        S_H = 1  # Dangerous conditions
    
    # Handle cold conditions based on actual temperature
    if T < 20:
        S_H = 1  # Dangerous cold
    elif T < 30:
        S_H = min(S_H, 2)  # Very cold
    elif T < 40:
        S_H = min(S_H, 3)  # Cold but manageable
    
    # 2. SOLAR/CLOUD COVER ADJUSTMENT (S_S)
    # Research shows direct sun adds 10-15°F to effective temperature
    forecast_lower = forecast.lower()
    if any(word in forecast_lower for word in ['sunny', 'clear', 'fair']):
        if heat_index > 70:
            solar_penalty = min(0.8, (heat_index - 70) * 0.02)  # Increase penalty with heat
            S_S = 5 - solar_penalty * 5  # Up to 4.0 reduction
        else:
            S_S = 5  # Sun is fine when cool
    elif any(word in forecast_lower for word in ['partly cloudy', 'partly sunny', 'scattered']):
        S_S = 5  # Mixed conditions
    elif any(word in forecast_lower for word in ['cloudy', 'overcast', 'mostly cloudy']):
        if heat_index > 75:
            S_S = 5 + 0.5  # Bonus for cloud cover when hot (capped at 5)
        else:
            S_S = 5
    else:
        S_S = 5  # Default
    
    S_S = min(5, max(1, S_S))  # Clamp to 1-5
    
    # 3. WIND SCORE (S_W) - Enhanced based on cooling research
    # Wind provides exponential cooling benefit up to ~10 mph
    if V <= 1:
        S_W = 3.5  # Very light wind still provides some cooling
    elif V <= 5:
        S_W = 4.5  # Light wind is good
    elif V <= 12:
        S_W = 5    # Optimal wind for cooling
    elif V <= 20:
        S_W = 4.5  # Strong but manageable
    elif V <= 30:
        S_W = 3    # Getting difficult
    else:
        S_W = 2    # Very windy, potentially unsafe
    
    # 4. PRECIPITATION SCORE (S_P) - Slightly reduced importance
    if P < 5:
        S_P = 5
    elif P < 15:
        S_P = 4.5
    elif P < 30:
        S_P = 4
    elif P < 50:
        S_P = 3
    elif P < 70:
        S_P = 2
    else:
        S_P = 1
    
    # 5. DEW POINT COMFORT (S_D) - Reduced weight, but still relevant
    # Dew point affects perceived humidity and comfort
    if D <= 45:
        S_D = 5      # Very dry and comfortable
    elif D <= 55:
        S_D = 4.5    # Comfortable
    elif D <= 65:
        S_D = 3.5    # Getting humid
    elif D <= 70:
        S_D = 2.5    # Quite humid
    else:
        S_D = 1.5    # Oppressive humidity
    
    # WEIGHTED COMBINATION - Enhanced scientific weighting
    # Heat index is most important (exercise physiology research priority)
    # Solar conditions significantly affect thermal load
    # Wind and other factors are secondary
    RWI = (0.45 * S_H +      # Primary thermal comfort (heat index)
           0.20 * S_S +      # Solar radiation effect
           0.15 * S_W +      # Wind cooling
           0.10 * S_P +      # Precipitation
           0.10 * S_D)       # Additional humidity comfort
    
    # Clamp to 1-5 range
    RWI = max(1.0, min(5.0, RWI))
    
    # Convert to integer rating (1-5 scale)
    if RWI >= 4.5:
        rating = 5
    elif RWI >= 3.5:
        rating = 4
    elif RWI >= 2.5:
        rating = 3
    elif RWI >= 1.5:
        rating = 2
    else:
        rating = 1
    
    return {
        'rwi_score': round(RWI, 2),
        'rating': rating,
        'heat_index': round(heat_index, 1),
        'components': {
            'thermal_comfort': round(S_H, 2),
            'solar_conditions': round(S_S, 2), 
            'wind': round(S_W, 2),
            'precipitation': round(S_P, 2),
            'dewpoint_comfort': round(S_D, 2)
        }
    }

# Example usage with your data
if __name__ == "__main__":
    sample_data = {
        "temperature": 77,
        "wind_speed": "5 mph", 
        "forecast": "Sunny",
        "precipitation": 2,
        "humidity": 54,
        "dewpoint_fahrenheit": 59
    }
    
    result = calculate_rwi(
        sample_data["temperature"],
        sample_data["humidity"], 
        sample_data["wind_speed"],
        sample_data["precipitation"],
        sample_data["forecast"],
        sample_data["dewpoint_fahrenheit"]
    )
    
    print(f"Running Weather Index: {result['rwi_score']} (Rating: {result['rating']}/5)")
    print(f"Heat Index: {result['heat_index']}°F")
    print("Component Scores:")
    for component, score in result['components'].items():
        print(f"  {component.replace('_', ' ').title()}: {score}")