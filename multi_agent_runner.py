# -*- coding: utf-8 -*-
import os
import requests
import json
import logging
import re
from datetime import datetime, timedelta
from typing import TypedDict, Annotated, Optional, Dict, List, Literal
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
import operator
from dotenv import load_dotenv
import asyncio
import schedule
import time
import threading
import smtplib
import ssl
from email.message import EmailMessage
import google.generativeai as genai
from langchain_core.prompts import ChatPromptTemplate

# Import existing modules
from enhanced_rwi import calculate_rwi
from llm_prompts import format_runner_profile_prompt, get_llm_run_plan_summary
from email_formatter import create_email_html

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Initialize LLM for supervisor
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0, max_tokens=4000)
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# Enhanced Risk Assessment Constants
OPTIMAL = 0
GOOD = 1
CAUTION = 2
HIGH_RISK = 3
DANGEROUS = 4

def convert_markdown_to_html(text: str) -> str:
    """Convert markdown-style formatting to HTML."""
    import re
    
    # Remove markdown code blocks
    text = text.replace('```html', '').replace('```', '').strip()
    
    # Convert headers (### -> h4, ## -> h3)
    text = re.sub(r'^###\s+(.+?)$', r'<h4 style="color: #333; margin: 15px 0 8px 0; font-weight: 600;">\1</h4>', text, flags=re.MULTILINE)
    text = re.sub(r'^##\s+(.+?)$', r'<h3 style="color: #007bff; margin: 20px 0 10px 0; font-weight: 600;">\1</h3>', text, flags=re.MULTILINE)
    
    # Convert ALL asterisk patterns to bold (handle triple first, then double)
    # Match ***word:*** or ***word*** patterns
    text = re.sub(r'\*\*\*([^*\n]+?):?\*\*\*', r'<strong>\1:</strong>', text)
    text = re.sub(r'\*\*([^*\n]+?):?\*\*', r'<strong>\1:</strong>', text)
    
    # Process line by line for lists and paragraphs
    lines = text.split('\n')
    html_lines = []
    in_list = False
    
    for line in lines:
        stripped = line.strip()
        
        # Skip empty lines
        if not stripped:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            html_lines.append('<br>')
            continue
        
        # Check for bullet points with * or -
        if re.match(r'^\*\s+', stripped) or re.match(r'^-\s+', stripped):
            if not in_list:
                html_lines.append('<ul style="margin: 10px 0; padding-left: 25px; line-height: 1.8;">')
                in_list = True
            content = re.sub(r'^[\*\-]\s+', '', stripped)
            html_lines.append(f'<li style="margin: 5px 0;">{content}</li>')
        else:
            # Close list if we were in one
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            
            # Wrap in paragraph if not already HTML
            if not stripped.startswith('<'):
                html_lines.append(f'<p style="margin: 8px 0; line-height: 1.6;">{stripped}</p>')
            else:
                html_lines.append(stripped)
    
    # Close list if still open
    if in_list:
        html_lines.append('</ul>')
    
    return '\n'.join(html_lines)

# --- State Definition ---
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    form_data: dict
    location: str
    city: str
    time_windows: dict
    weather_data: Optional[dict]
    aqi_data: Optional[str]
    parsed_weather: Optional[dict]
    scored_hours: Optional[List[dict]]
    profile_data: Optional[dict]
    days_plan: Optional[dict]  # Add this
    final_html: Optional[str]
    final_user_message: Optional[str]
    is_mobile: bool
    card_data: Optional[dict]
    next_agent: Optional[str]
    error: Optional[str]

# --- Tool Definitions ---

@tool
def get_city_from_zipcode(zip_code: str) -> str:
    """Convert a 5-digit US zip code to 'City, State' format."""
    if not re.match(r'^\d{5}$', zip_code):
        return zip_code

    try:
        url = f"https://api.zippopotam.us/us/{zip_code}"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        place_name = data['places'][0]['place name']
        state_abbr = data['places'][0]['state abbreviation']
        city_state = f"{place_name}, {state_abbr}"
        logger.info(f"Converted zip code {zip_code} to '{city_state}'")
        return city_state
    except Exception as e:
        logger.warning(f"Failed to convert zip code {zip_code}: {e}")
        return zip_code

@tool
def get_weather_forecast_from_server(city: str, granularity: str = 'hourly') -> str:
    """Get weather forecast from the MCP server."""
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
    """Get Air Quality Index forecast from the server."""
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
    
    # --- Helper Functions (import from original code) ---

from helper_functions import (
    generate_email_content_from_cards,
    get_score_color,
    clean_html_for_email,
    generate_desktop_aligned_email_content,
    parse_weather_data,
    score_hour_with_scientific_approach,
    generate_enhanced_card_data,
    generate_mobile_card_html,
    generate_compact_html_analysis,
    generate_enhanced_profile_card_data,
    send_email_notification,
    calculate_safe_heart_rate_zones,
    handle_enhanced_forecast_request,
    enhance_forecast_for_email,
    schedule_daily_email_report,
    # ... import all other helper functions
)

# --- Agent Nodes ---

def supervisor_agent(state: AgentState) -> AgentState:
    """Supervisor agent that routes tasks to specialized agents."""
    
    messages = state["messages"]
    form_data = state.get("form_data", {})
    
    # Analyze the request and decide routing
    action = form_data.get('action', ['get_forecast'])[0]
    location = form_data.get('location', [''])[0]
    
    if not location:
        state["error"] = "Location is required"
        state["next_agent"] = "end"
        return state
    
    # Check if we're done - prevent infinite loops
    if state.get("final_html") and (action != 'email_now' or state.get("email_sent")):
        state["next_agent"] = "end"
        return state
    
    # Determine next agent based on workflow stage
    if not state.get("city"):
        state["next_agent"] = "location_agent"
    elif not state.get("weather_data") or not state.get("aqi_data"):
        state["next_agent"] = "data_collection_agent"
    elif not state.get("parsed_weather"):
        state["next_agent"] = "parsing_agent"
    elif not state.get("scored_hours"):
        state["next_agent"] = "scoring_agent"
    elif not state.get("profile_data"):
        state["next_agent"] = "profile_agent"
    elif not state.get("final_html"):
        state["next_agent"] = "presentation_agent"
    elif action == 'email_now' and not state.get("email_sent"):
        state["next_agent"] = "email_agent"
    else:
        state["next_agent"] = "end"
    
    logger.info(f"Supervisor routing to: {state['next_agent']}")
    return state

def location_agent(state: AgentState) -> AgentState:
    """Agent responsible for location resolution."""
    
    location = state["form_data"].get('location', [''])[0]
    
    # Convert zip code if needed
    city = get_city_from_zipcode.invoke({"zip_code": location})
    state["city"] = city
    state["location"] = location
    
    # Extract time windows
    time_windows = {}
    window_names = ['today_1', 'today_2', 'tomorrow_1', 'tomorrow_2']
    
    for window_name in window_names:
        start_key = f'{window_name}_start'
        end_key = f'{window_name}_end'
        start_time = state["form_data"].get(start_key, [''])[0]
        end_time = state["form_data"].get(end_key, [''])[0]
        
        if start_time and end_time:
            time_windows[window_name] = (start_time, end_time)
    
    state["time_windows"] = time_windows
    
    logger.info(f"Location agent resolved: {city}")
    return state

async def data_collection_agent(state: AgentState) -> AgentState:
    """Agent responsible for parallel data collection."""
    
    city = state["city"]
    
    # Run weather and AQI fetching in parallel
    async def fetch_weather():
        return get_weather_forecast_from_server.invoke({"city": city, "granularity": "hourly"})
    
    async def fetch_aqi():
        return get_air_quality_from_server.invoke({"city": city})
    
    # Execute in parallel
    weather_task = asyncio.create_task(fetch_weather())
    aqi_task = asyncio.create_task(fetch_aqi())
    
    weather_data, aqi_data = await asyncio.gather(weather_task, aqi_task)
    
    state["weather_data"] = weather_data
    state["aqi_data"] = aqi_data
    
    logger.info(f"Data collection complete for {city}")
    return state

def parsing_agent(state: AgentState) -> AgentState:
    """Agent responsible for parsing weather data."""
    
    weather_response = state["weather_data"]
    parsed_data = parse_weather_data(weather_response)
    
    state["parsed_weather"] = parsed_data
    
    logger.info(f"Parsing complete: {len(parsed_data.get('today', []))} today, {len(parsed_data.get('tomorrow', []))} tomorrow")
    return state

def scoring_agent(state: AgentState) -> AgentState:
    """Agent responsible for scoring running conditions."""
    
    parsed_weather = state["parsed_weather"]
    time_windows = state["time_windows"]
    aqi_data = state["aqi_data"]
    
    today_data = parsed_weather.get('today', [])
    tomorrow_data = parsed_weather.get('tomorrow', [])
    
    all_scored_hours = []
    seen_hours = set()
    
    def time_to_hour(time_str): 
        return int(time_str.split(':')[0])
    
    # Parse AQI
    aqi_match = re.search(r'\b(\d{1,3})\b', aqi_data)
    today_aqi = int(aqi_match.group(1)) if aqi_match else None
    
    for window_key, times in time_windows.items():
        start_hour, end_hour = time_to_hour(times[0]), time_to_hour(times[1])
        data_source = today_data if 'today' in window_key else tomorrow_data
        
        filtered = [h for h in data_source if h['HourNum'] != "N/A" and start_hour <= h['HourNum'] <= end_hour]
        scored = [score_hour_with_scientific_approach(h, aqi_value=today_aqi) for h in filtered]
        
        for hour in scored:
            hour_key = (hour.get('day_category'), hour.get('HourNum'))
            if hour_key not in seen_hours:
                all_scored_hours.append(hour)
                seen_hours.add(hour_key)
    
    all_scored_hours.sort(key=lambda x: (x.get('day_category', 'z'), x.get('HourNum', 0)))
    state["scored_hours"] = all_scored_hours
    
    logger.info(f"Scoring complete: {len(all_scored_hours)} hours scored")
    return state

def profile_agent(state: AgentState) -> AgentState:
    """Agent responsible for generating runner profile data."""
    
    form_data = state["form_data"]
    
    # Extract dietary and health information
    dietary_restrictions = form_data.get('dietary_restrictions', [''])[0]
    health_conditions = form_data.get('health_conditions', [''])[0]
    
    # Get base profile data
    profile_data = generate_enhanced_profile_card_data(form_data)
    
    # Add restrictions to profile data
    profile_data['dietary_restrictions'] = dietary_restrictions
    profile_data['health_conditions'] = health_conditions
    profile_data['show_nutrition'] = form_data.get('show_nutrition', ['no'])[0] == 'yes'
    profile_data['strength_training_selected'] = form_data.get('strength_training', ['no'])[0] == 'yes'
    profile_data['mindfulness_plan_selected'] = form_data.get('mindfulness_plan', ['no'])[0] == 'yes'
    
    # Generate LLM-powered nutrition, strength, and mindfulness content if selected
    if profile_data['show_nutrition'] or profile_data['strength_training_selected'] or profile_data['mindfulness_plan_selected']:
        try:
            wellness_content = generate_wellness_content_with_llm(form_data, profile_data)
            
            # CRITICAL: Update profile data with LLM-generated content
            if profile_data['show_nutrition'] and wellness_content.get('nutrition'):
                profile_data['nutrition'] = wellness_content['nutrition']
                logger.info(f"Applied LLM nutrition: {wellness_content['nutrition']}")
            
            if profile_data['strength_training_selected'] and wellness_content.get('strength_training'):
                profile_data['strength_training'] = wellness_content['strength_training']
                logger.info(f"Applied LLM strength: {wellness_content['strength_training']}")
            
            if profile_data['mindfulness_plan_selected'] and wellness_content.get('mindfulness'):
                profile_data['mindfulness'] = wellness_content['mindfulness']
                logger.info(f"Applied LLM mindfulness: {wellness_content['mindfulness']}")
                
        except Exception as e:
            logger.error(f"Error generating wellness content with LLM: {e}")
            # Keep default placeholder content if LLM fails
    
    state["profile_data"] = profile_data
    
    logger.info(f"Profile generation complete. Wellness content: nutrition={bool(profile_data.get('nutrition'))}, strength={bool(profile_data.get('strength_training'))}, mindfulness={bool(profile_data.get('mindfulness'))}")
    
    return state

def presentation_agent(state: AgentState) -> AgentState:
    """LLM-powered agent for formatting output based on UI context."""
    
    scored_hours = state["scored_hours"]
    city = state["city"]
    form_data = state["form_data"]
    profile_data = state["profile_data"]
    is_mobile = form_data.get('mobile_view', ['false'])[0] == 'true'
    
    if not scored_hours:
        state["error"] = f"No forecast data available for {city}."
        return state
    
    try:
        if is_mobile:
            # Mobile view - Generate LLM day's plan
            try:
                logger.info("=== MOBILE VIEW: Starting mobile presentation generation ===")
                card_data = generate_mobile_presentation_with_llm(scored_hours, city, form_data, profile_data)
                mobile_html = generate_mobile_card_html(card_data)
        
                # DEBUG LOG
                logger.info(f"Mobile card_data keys: {list(card_data.keys())}")
                if 'days_plan' in card_data:
                    plan_content = card_data['days_plan'].get('content', '')
                    logger.info(f"Days plan EXISTS - Length: {len(plan_content)}")
                    logger.info(f"Days plan content preview: {plan_content[:200]}")
                else:
                    logger.warning("WARNING: 'days_plan' NOT FOUND in card_data")
        
                state["final_html"] = mobile_html
                state["final_user_message"] = f'Mobile forecast generated for {city}.'
                state["is_mobile"] = True
                state["card_data"] = card_data
                
                logger.info("=== MOBILE VIEW: Successfully completed ===")
            except Exception as e:
                logger.error(f"Mobile presentation error: {e}", exc_info=True)
                raise
        else:
            # Desktop view
            logger.info("=== DESKTOP VIEW: Starting desktop presentation generation ===")
            profile_html = ""
            forecast_html = ""  # Initialize here
    
            if any(form_data.get(key, [''])[0] for key in ['first_name', 'age', 'run_plan']):
                try:
                    logger.info("Generating runner profile with LLM...")
                    runner_profile_prompt = format_runner_profile_prompt(form_data)
                    
                    logger.info(f"Profile prompt length: {len(runner_profile_prompt)} characters")
            
                    response = llm.invoke(runner_profile_prompt, config={
                        "max_output_tokens": 8000,
                        "temperature": 0.7
                    })
            
                    response_content = response.content if hasattr(response, 'content') else str(response)
                    
                    # DEBUG: Log before conversion
                    logger.info("=== BEFORE HTML CONVERSION ===")
                    logger.info(f"Response length: {len(response_content)} characters")
                    logger.info(f"First 300 chars: {response_content[:300]}")
                    logger.info(f"Contains triple asterisks: {'***' in response_content}")
                    logger.info(f"Contains double asterisks: {'**' in response_content}")
            
                    # Convert markdown to HTML
                    response_content = convert_markdown_to_html(response_content)
                    
                    # DEBUG: Log after conversion
                    logger.info("=== AFTER HTML CONVERSION ===")
                    logger.info(f"Converted length: {len(response_content)} characters")
                    logger.info(f"First 300 chars: {response_content[:300]}")
                    logger.info(f"Contains <strong> tags: {'<strong>' in response_content}")
                    logger.info(f"Contains <p> tags: {'<p>' in response_content}")
                    logger.info(f"Contains <h3> or <h4>: {'<h3>' in response_content or '<h4>' in response_content}")
            
                    profile_html = f"""
                        <div style="margin: 20px 0; padding: 20px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #007bff;">
                            <h3 style="color: #007bff; margin-top: 0;">Your Personalized Running Plan</h3>
                            {response_content}
                        </div>
                    """
                    
                    logger.info("Profile HTML generated successfully")
                    
                except Exception as e:
                    logger.error(f"Profile generation error: {e}", exc_info=True)
                    profile_html = f"""
                        <div style="margin: 20px 0; padding: 20px; background: #fff3cd; border-radius: 8px; border-left: 4px solid #ffc107;">
                            <h3 style="color: #856404; margin-top: 0;">Training Plan Unavailable</h3>
                            <p>Unable to generate training plan. Error: {str(e)}</p>
                        </div>
                    """
            else:
                logger.info("No profile data provided - skipping profile generation")

            # ALWAYS generate weather forecast - MOVED OUTSIDE profile try-except
            logger.info("Generating weather forecast...")
            logger.info(f"Scored hours count: {len(scored_hours)}")
            if scored_hours:
                logger.info(f"First scored hour sample: {scored_hours[0]}")

            try:
                forecast_html = generate_compact_html_analysis(scored_hours, city)
                logger.info(f"Weather forecast generated successfully - HTML length: {len(forecast_html)}")
                logger.info(f"FORECAST CONTENT PREVIEW: {forecast_html[:500]}")  # <-- NEW LINE
            except Exception as e:
                logger.error(f"Forecast generation error: {e}", exc_info=True)
                forecast_html = f"""
                    <div style='color: red; padding: 20px; background: #ffebee; border-radius: 8px; margin: 20px 0;'>
                        <h3>Weather Forecast Error</h3>
                        <p>Unable to generate weather forecast: {str(e)}</p>
                    </div>
                """
    
            # Combine profile + forecast
            final_combined = profile_html + forecast_html
            logger.info(f"Combined HTML length: {len(final_combined)} (profile: {len(profile_html)}, forecast: {len(forecast_html)})")
            
            state["final_html"] = final_combined
            state["final_user_message"] = f'Forecast generated for {city}.'
            state["is_mobile"] = False
            
            logger.info(f"=== DESKTOP VIEW: Successfully completed ===")
            
    except Exception as e:
        logger.error(f"Presentation agent error: {e}", exc_info=True)
        state["error"] = str(e)
    
    return state

def generate_wellness_content_with_llm(form_data: dict, profile_data: dict) -> dict:
    """Use LLM to generate personalized nutrition, strength, and mindfulness content."""
    
    # Extract relevant data
    dietary_restrictions = form_data.get('dietary_restrictions', [''])[0]
    health_conditions = form_data.get('health_conditions', [''])[0]
    mobility_restrictions = form_data.get('mobility_restrictions', [''])[0]
    
    show_nutrition = form_data.get('show_nutrition', ['no'])[0] == 'yes'
    strength_training = form_data.get('strength_training', ['no'])[0] == 'yes'
    mindfulness_plan = form_data.get('mindfulness_plan', ['no'])[0] == 'yes'
    
    # Get training context
    run_plan = form_data.get('run_plan', [''])[0]
    unified_plan_type = form_data.get('unified_plan_type', [''])[0]
    plan_period = form_data.get('plan_period', [''])[0]
    current_week = plan_period.replace('week_', 'Week ') if plan_period else 'Week 1'
    today_workout = profile_data.get('today_workout', '')
    
    # Build JSON structure dynamically
    json_fields = []
    components_requested = []
    
    if show_nutrition:
        json_fields.append('"nutrition": {"pre_run": "specific pre-run meal/snack", "during": "hydration/fuel during run", "post_run": "recovery nutrition"}')
        components_requested.append("Nutrition")
    
    if strength_training:
        json_fields.append('"strength_training": {"schedule": "when to train", "focus": "key muscle groups", "exercises": "specific exercises", "duration": "session length"}')
        components_requested.append("Strength Training")
    
    if mindfulness_plan:
        json_fields.append('"mindfulness": {"practice": "daily practice", "focus": "mental focus areas", "running": "mindful running tips", "recovery": "recovery mindfulness"}')
        components_requested.append("Mindfulness")
    
    if not json_fields:
        return {}
    
    json_structure = "{\n  " + ",\n  ".join(json_fields) + "\n}"
    
    prompt = f"""You are an expert running coach and wellness advisor. Generate personalized wellness content for a runner.

RUNNER CONTEXT:
- Current Training: {run_plan} - {unified_plan_type}
- Training Week: {current_week}
- Today's Workout: {today_workout}

CRITICAL RESTRICTIONS (MUST FOLLOW):
- Dietary Restrictions: {dietary_restrictions if dietary_restrictions else 'None'}
- Health Conditions: {health_conditions if health_conditions else 'None'}
- Mobility Restrictions: {mobility_restrictions if mobility_restrictions else 'None'}

GENERATE CONTENT FOR: {', '.join(components_requested)}

OUTPUT FORMAT - Return ONLY valid JSON in this exact structure:
{json_structure}

CRITICAL REQUIREMENTS:
1. Nutrition MUST respect dietary restrictions - NEVER recommend restricted foods
2. Strength exercises MUST accommodate mobility restrictions
3. All recommendations MUST be specific, practical, and evidence-based
4. Tailor to their current training week ({current_week}) and today's workout
5. Keep each field concise (1-2 sentences max) for mobile display
6. Return ONLY the JSON object, no markdown formatting, no additional text
7. Ensure all JSON is properly formatted with no trailing commas

Return JSON only:"""

    try:
        response = llm.invoke(prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # Clean response
        response_text = response_text.strip()
        
        # Remove markdown code blocks if present
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        elif response_text.startswith('```'):
            response_text = response_text[3:]
        
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        
        response_text = response_text.strip()
        
        # Log for debugging
        logger.info(f"Wellness LLM raw response: {response_text[:500]}...")
        
        import json
        wellness_data = json.loads(response_text)
        
        logger.info(f"Successfully parsed wellness content: {list(wellness_data.keys())}")
        return wellness_data
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse wellness JSON: {e}")
        logger.error(f"Response was: {response_text}")
        return {}
    except Exception as e:
        logger.error(f"Error generating wellness content: {e}")
        return {}

def generate_mobile_presentation_with_llm(scored_hours: List, city: str, form_data: dict, profile_data: dict) -> dict:
    """Use LLM to generate mobile-optimized card data including Day's Plan."""
    
    # Extract relevant context for LLM
    today = datetime.now()
    date_str = today.strftime("%b %d (%a)")
    
    # Get best weather hours
    best_hours = sorted(scored_hours, key=lambda x: x.get('raw_score', 0), reverse=True)[:3]
    best_times = [f"{h.get('Hour', 'N/A')}" for h in best_hours]
    
    # CRITICAL: Extract restrictions from the CORRECT form fields
    dietary_restrictions = form_data.get('dietary_restrictions', [''])[0]
    health_conditions = form_data.get('health_conditions', [''])[0]
    mobility_restrictions = form_data.get('mobility_restrictions', [''])[0]
    other_details = form_data.get('other_details', [''])[0]
    
    # Get selected options
    show_nutrition = form_data.get('show_nutrition', ['no'])[0] == 'yes'
    strength_training = form_data.get('strength_training', ['no'])[0] == 'yes'
    mindfulness_plan = form_data.get('mindfulness_plan', ['no'])[0] == 'yes'
    
    # Get workout details from profile data
    today_workout = profile_data.get('today_workout', '') if profile_data else ''
    run_plan = form_data.get('run_plan', [''])[0]
    
    # Get the unified plan type
    unified_plan_type = form_data.get('unified_plan_type', [''])[0]
    
    # Extract plan period for week number
    plan_period = form_data.get('plan_period', [''])[0]
    current_week = plan_period.replace('week_', 'Week ') if plan_period else 'Week 1'
    
    # Build conditional components for the output format
    components = ["- Run: [Specific workout details based on their plan and current week]"]
    
    if strength_training:
        components.append("- Strength: [Specific exercises]")
    
    if show_nutrition:
        components.append("- Nutrition: [Pre/during/post run fueling that respects ALL dietary restrictions]")
    
    if mindfulness_plan:
        components.append("- Mindfulness: [Mental training practice]")
    
    components.append(f"- Weather - Best Hours: {', '.join(best_times)}")
    components.append("- Recommendation: [Specific advice based on weather and user's health conditions]")
    
    components_text = '\n'.join(components)
    
    # Build comprehensive context about restrictions
    restrictions_context = []
    if dietary_restrictions:
        restrictions_context.append(f"**DIETARY RESTRICTIONS (MANDATORY)**: {dietary_restrictions}")
        restrictions_context.append("⚠️ CRITICAL: NEVER recommend foods that conflict with these restrictions")
    
    if health_conditions:
        restrictions_context.append(f"**HEALTH CONDITIONS**: {health_conditions}")
        restrictions_context.append("⚠️ Modify workout intensity and exercises accordingly")
    
    if mobility_restrictions:
        restrictions_context.append(f"**MOBILITY RESTRICTIONS**: {mobility_restrictions}")
        restrictions_context.append("⚠️ Adapt exercises and running pace to accommodate these limitations")
    
    if other_details:
        restrictions_context.append(f"**OTHER RELEVANT DETAILS**: {other_details}")
    
    restrictions_text = '\n'.join(restrictions_context) if restrictions_context else 'None specified'
    
    # Map plan types to readable descriptions
    plan_type_descriptions = {
        'individual_daily': 'Individual Daily Fitness',
        'group_daily': 'Group/Family Daily Fitness',
        'starting_fitness': 'Just Starting - Build Base Fitness',
        'weight_loss_fitness': 'Weight Loss Focus',
        'endurance_fitness': 'Improve Endurance',
        'hm_300': 'Sub-3:00 Half Marathon',
        'hm_230': 'Sub-2:30 Half Marathon',
        'hm_200': 'Sub-2:00 Half Marathon',
        'hm_130': 'Sub-1:30 Half Marathon',
        'm_530': 'Sub-5:30 Marathon',
        'm_500': 'Sub-5:00 Marathon',
        'm_430': 'Sub-4:30 Marathon',
        'm_400': 'Sub-4:00 Marathon'
    }
    
    plan_description = plan_type_descriptions.get(unified_plan_type, unified_plan_type or 'General Fitness')
    
    # Build the comprehensive prompt
    prompt_text = f"""You are a running coach AI creating a personalized daily training plan.

CRITICAL USER RESTRICTIONS (MUST BE STRICTLY FOLLOWED):
{restrictions_text}

User's Training Program:
- Run Plan: {run_plan if run_plan else 'General Fitness'}
- Specific Goal: {plan_description}
- Current Training Week: {current_week}
- Today's Scheduled Workout: {today_workout if today_workout else 'To be determined based on training week'}

User's Selected Components (INCLUDE ONLY THESE):
- Include Running Workout: YES (ALWAYS REQUIRED - this is the primary focus)
- Include Nutrition: {'YES - provide pre/during/post-run fueling guidance' if show_nutrition else 'NO - do not mention nutrition'}
- Include Strength: {'YES - provide running-specific strength exercises' if strength_training else 'NO - do not mention strength training'}
- Include Mindfulness: {'YES - provide mental training practices' if mindfulness_plan else 'NO - do not mention mindfulness'}

Weather Information:
- Best Running Hours Today: {', '.join(best_times)}
- Location: {city}

GENERATE TODAY'S TRAINING PLAN IN THIS EXACT FORMAT:

{date_str} – [Workout Name/Type for {current_week}]
{components_text}

OUTPUT REQUIREMENTS:
1. **START WITH RUNNING WORKOUT** - Always begin with specific run details
2. Only add nutrition/strength/mindfulness if user selected them
3. Be specific and actionable
4. Format as plain text with line breaks, not HTML

Generate the plan now:"""

    try:
        response = llm.invoke(prompt_text)
        days_plan_content = response.content if hasattr(response, 'content') else str(response)
        
        logger.info(f"LLM generated day's plan: {days_plan_content[:200]}...")
        
        # CRITICAL FIX: Pass profile_data to preserve LLM wellness content
        base_card_data = generate_enhanced_card_data(scored_hours, city, form_data, profile_data)
        
        # Add the LLM-generated Day's Plan card
        base_card_data['days_plan'] = {
            'content': days_plan_content,
            'date': date_str
        }
        
        return base_card_data
        
    except Exception as e:
        logger.error(f"Error generating day's plan with LLM: {e}")
        raise Exception("Unable to generate training plan. AI service temporarily unavailable. Please try again.")
    
def generate_desktop_presentation_with_llm(scored_hours: List, city: str, form_data: dict, profile_data: dict) -> str:
    """Use LLM to generate desktop-optimized HTML presentation."""
    
    # Generate profile HTML if available
    profile_html = ""
    if any(form_data.get(key, [''])[0] for key in ['first_name', 'age', 'run_plan']):
        try:
            # Get the runner profile prompt with all context
            runner_profile_prompt = format_runner_profile_prompt(form_data)
            
            # Get plan display preference
            plan_display = form_data.get('plan_display', ['full_plan'])[0]
            plan_period = form_data.get('plan_period', [''])[0]
            
            # Determine plan duration
            plan_duration_weeks = 12  # default
            if plan_period:
                week_num = plan_period.replace('week_', '')
                plan_duration_weeks = int(week_num)
            
            # Build specific instructions based on plan_display
            if plan_display == 'full_plan':
                display_instructions = f"""
CRITICAL: Generate a COMPLETE {plan_duration_weeks}-week training plan with the following structure:

1. **Program Overview** - Brief description of the training philosophy and goals
2. **Complete Weekly Breakdown** - Show ALL {plan_duration_weeks} weeks with:
   - Week number and training phase (Base Building/Build/Peak/Taper)
   - 7-day workout schedule for each week
   - Specific workouts with distance/pace/duration/intensity
   - Weekly mileage and key focus areas
3. **Periodization Phases**:
   - Base Building (Weeks 1-{int(plan_duration_weeks*0.4)})
   - Build Phase (Weeks {int(plan_duration_weeks*0.4)+1}-{int(plan_duration_weeks*0.7)})
   - Peak Phase (Weeks {int(plan_duration_weeks*0.7)+1}-{int(plan_duration_weeks*0.85)})
   - Taper (Weeks {int(plan_duration_weeks*0.85)+1}-{plan_duration_weeks})

FORMAT AS HTML TABLE:
- Use <table> with proper headers for Week, Phase, Mon-Sun columns
- Each week in its own row
- Clear visual distinction for current week (if applicable)
- Include rest days and cross-training in the schedule
"""
            elif plan_display == 'one_day':
                display_instructions = """
CRITICAL: Generate ONLY today's detailed workout with:

1. **Workout Name** - Descriptive title
2. **Warm-up** - 10-15 minute warm-up protocol
3. **Main Workout** - Specific distance/pace/intervals/duration
4. **Cool-down** - 5-10 minute cool-down
5. **Additional Notes** - Form cues, effort level, recovery tips

Format with clear HTML sections and bullet points.
"""
            elif plan_display == 'this_week':
                display_instructions = """
CRITICAL: Generate THIS WEEK's complete 7-day plan with:

1. **Week Overview** - Current week number and phase
2. **Daily Breakdown** (Monday-Sunday):
   - Each day with specific workout
   - Rest/recovery days clearly marked
   - Mileage and intensity for each session
3. **Weekly Totals** - Total mileage and key sessions

Format as an HTML table or structured daily cards.
"""
            else:
                display_instructions = f"Generate a {plan_display} training plan."
            
            # Create comprehensive prompt
            desktop_prompt_text = f"""{runner_profile_prompt}

{display_instructions}

ADDITIONAL REQUIREMENTS:
- Start EVERY response with detailed RUNNING workout content
- Use proper HTML formatting (h3, h4, table, ul, li, p tags)
- Make workouts specific and measurable
- Include ONLY components user selected (nutrition/strength/mindfulness)
- Base all recommendations on sports science
- No fictional workouts or unproven methods

CRITICAL REQUIREMENTS:
1. **PRIMARY FOCUS: RUNNING WORKOUTS** - Generate specific running workouts as the main content
2. Based on the user's selected components, also include:
   - Strength training exercises (only if selected)
   - Nutrition guidance (only if selected)
   - Mindfulness practices (only if selected)
3. The running workout MUST be specific, measurable, and based on:
   - Their training week/phase
   - Their specific goal (marathon time, fitness level, etc.)
   - Proper periodization principles
4. Respect ALL dietary restrictions, health conditions, and mobility limitations

Generate the training plan now:"""
            
            response = llm.invoke(
                desktop_prompt_text,
                config={
                    "max_output_tokens": 8000,  # Increased for full plans
                    "temperature": 0.7
                }
            )
            response_content = response.content if hasattr(response, 'content') else str(response)
            
            profile_html = f"""
                <div style="margin: 20px 0; padding: 20px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #007bff;">
                    <h3 style="color: #007bff; margin-top: 0;">Your Personalized Running Plan</h3>
                    {response_content}
                </div>
            """
        except Exception as e:
            logger.error(f"Error generating LLM profile: {e}")
            raise Exception("Unable to generate training plan. LLM service is temporarily unavailable. Please try again in a few moments.")
    
    # Generate forecast HTML
    try:
        forecast_html = generate_compact_html_analysis(scored_hours, city)
        return profile_html + forecast_html
    except Exception as e:
        logger.error(f"Error generating forecast HTML: {e}")
        raise Exception("Unable to generate forecast display. Please try again.")

def email_agent(state: AgentState) -> AgentState:
    """Agent responsible for email delivery with desktop-aligned content."""
    
    email = state["form_data"].get('email', [''])[0]
    city = state["city"]
    final_html = state["final_html"]
    is_mobile = state.get("is_mobile", False)
    
    # Mark email as processed immediately to prevent loops
    state["email_sent"] = True
    
    if not email:
        state["error"] = "Email address is required for email delivery"
        logger.error("Email agent called without email address")
        return state
    
    if not final_html:
        state["error"] = "No content to email"
        logger.error("Email agent called without final HTML content")
        return state
    
    try:
        subject = f"Your Running Forecast for {city}"
        
        # CRITICAL FIX: Always generate desktop-aligned content for email
        # regardless of whether the original request was mobile or desktop
        email_content = generate_desktop_aligned_email_content(state, city)
        
        email_body = create_email_html(email_content, city)
        
        success = send_email_notification(email, subject, email_body, is_html=True)
        
        if success:
            state["final_user_message"] = f'Forecast emailed to {email} successfully.'
            logger.info(f"Email delivery: success={success}")
        else:
            state["error"] = f'Failed to send email to {email}.'
            logger.error(f"Email delivery failed to {email}")
            
    except Exception as e:
        logger.error(f"Error in email agent: {e}")
        state["error"] = f'Error sending email: {str(e)}'
    
    # Force next agent to be 'end' to prevent loops
    state["next_agent"] = "end"
    
    return state

def router(state: AgentState) -> Literal["location_agent", "data_collection_agent", "parsing_agent", "scoring_agent", "profile_agent", "presentation_agent", "email_agent", "end"]:
    """Route to next agent based on supervisor decision."""
    
    next_agent = state.get("next_agent", "end")
    
    # Check for errors - ALWAYS go to end if there's an error
    if state.get("error"):
        return "end"
    
    # Check for email action - but only once
    action = state["form_data"].get('action', ['get_forecast'])[0]
    if action == 'email_now' and state.get("final_html") and not state.get("email_sent"):
        # Mark as email sent to prevent infinite loop
        state["email_sent"] = True
        return "email_agent"
    
    # If we've already processed everything and sent email, end
    if state.get("final_html") and state.get("email_sent"):
        return "end"
    
    # If we have final HTML and no email action needed, end
    if state.get("final_html") and action != 'email_now':
        return "end"
    
    return next_agent

# --- Graph Construction ---

def create_agent_graph():
    """Create the multi-agent workflow graph."""
    
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("supervisor", supervisor_agent)
    workflow.add_node("location_agent", location_agent)
    workflow.add_node("data_collection_agent", lambda state: asyncio.run(data_collection_agent(state)))
    workflow.add_node("parsing_agent", parsing_agent)
    workflow.add_node("scoring_agent", scoring_agent)
    workflow.add_node("profile_agent", profile_agent)
    workflow.add_node("presentation_agent", presentation_agent)
    workflow.add_node("email_agent", email_agent)
    
    # Set entry point
    workflow.set_entry_point("supervisor")
    
    # Add conditional edges from supervisor
    workflow.add_conditional_edges(
        "supervisor",
        router,
        {
            "location_agent": "location_agent",
            "data_collection_agent": "data_collection_agent",
            "parsing_agent": "parsing_agent",
            "scoring_agent": "scoring_agent",
            "profile_agent": "profile_agent",
            "presentation_agent": "presentation_agent",
            "email_agent": "email_agent",
            "end": END
        }
    )
    
    # Each agent returns to supervisor for routing EXCEPT email_agent
    for agent in ["location_agent", "data_collection_agent", "parsing_agent", "scoring_agent", "profile_agent", "presentation_agent"]:
        workflow.add_edge(agent, "supervisor")
    
    # Email agent goes directly to END to prevent loops
    workflow.add_edge("email_agent", END)
    
    # Compile with recursion limit
    return workflow.compile()

# --- Main Workflow Function ---

def run_agent_workflow(form_data: dict) -> dict:
    """
    Main workflow that processes form data through the multi-agent system.
    """
    try:
        # Initialize state
        initial_state = {
            "messages": [],
            "form_data": form_data,
            "location": "",
            "city": "",
            "time_windows": {},
            "weather_data": None,
            "aqi_data": None,
            "parsed_weather": None,
            "scored_hours": None,
            "profile_data": None,
            "days_plan": None,
            "final_html": None,
            "final_user_message": None,
            "is_mobile": False,
            "card_data": None,
            "next_agent": None,
            "error": None
        }
        
        # Create and run the agent graph
        graph = create_agent_graph()
        
        # Execute the workflow
        final_state = graph.invoke(initial_state)
        
        # Check for errors
        if final_state.get("error"):
            return {
                'final_html': f'<div style="color: red;">Error: {final_state["error"]}</div>',
                'final_user_message': f'Error: {final_state["error"]}'
            }
        
        # Return the results
        return {
            'final_html': final_state.get("final_html", ""),
            'final_user_message': final_state.get("final_user_message", ""),
            'is_mobile': final_state.get("is_mobile", False),
            'card_data': final_state.get("card_data")
        }
        
    except Exception as e:
        logger.error(f"Workflow error: {e}", exc_info=True)
        return {
            'final_html': f'<div style="color: red;">Error: {str(e)}</div>',
            'final_user_message': f'An error occurred: {str(e)}'
        }

def generate_desktop_aligned_email_content_from_result(forecast_result: dict, city: str) -> str:
    """
    Generate desktop-aligned email content from forecast result.
    Works for both mobile and desktop forecast results.
    """
    try:
        is_mobile = forecast_result.get('is_mobile', False)
        
        if is_mobile:
            # For mobile results, use the card data to generate email content
            card_data = forecast_result.get('card_data')
            if card_data:
                return generate_email_content_from_cards(card_data, city)
            else:
                # Fallback to HTML cleaning
                return clean_html_for_email(forecast_result.get('final_html', ''))
        else:
            # For desktop results, the HTML is already properly formatted
            return enhance_forecast_for_email(forecast_result.get('final_html', ''))
            
    except Exception as e:
        logger.error(f"Error generating email content: {e}")
        return f"<p>Forecast content for {city} is available but could not be formatted for email.</p>"

# --- Scheduler Functions  ---

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

# --- Main Function ---

def main():
    """Main function for testing the system."""
    print("Multi-Agent Running Forecast System Initialized")
    print("Architecture: LangGraph Supervisor with Specialized Agents")
    print("\nAgents:")
    print("  - Supervisor: Routes tasks dynamically")
    print("  - Location Agent: Resolves zip codes")
    print("  - Data Collection Agent: Parallel weather + AQI fetching")
    print("  - Parsing Agent: Processes weather data")
    print("  - Scoring Agent: Evaluates running conditions")
    print("  - Profile Agent: Generates training plans")
    print("  - Presentation Agent: Formats output")
    print("  - Email Agent: Delivers results")
    
    start_scheduler()
    
    while True:
        try:
            user_input = input("\nEnter command (or 'quit'): ").strip()
            if user_input.lower() in ['quit', 'exit', 'q']:
                break
                
            if user_input:
                print("\nProcessing request through multi-agent workflow...\n")
                result = run_agent_workflow({
                    'location': ['New York, NY'],
                    'action': ['get_forecast'],
                    'today_1_start': ['06:00'],
                    'today_1_end': ['10:00'],
                    'tomorrow_1_start': ['18:00'],
                    'tomorrow_1_end': ['22:00']
                })
                print("Result:")
                print("=" * 50)
                print(result.get('final_user_message', 'No message'))
                print("=" * 50)
            
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()