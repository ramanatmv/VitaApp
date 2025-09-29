import os
import requests
import json
import pandas as pd
from io import StringIO
from typing import TypedDict, Annotated
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
import operator
from dotenv import load_dotenv
import schedule
import smtplib
import ssl
from email.message import EmailMessage

# Load environment variables from .env file
load_dotenv()

# --- Reusable Email Function ---
def send_email_notification(recipient_email: str, subject: str, body: str):
    """Sends an email using credentials from the .env file."""
    email_user = os.getenv("EMAIL_USER")
    email_password = os.getenv("EMAIL_PASSWORD")
    email_host = os.getenv("EMAIL_HOST")
    email_port = int(os.getenv("EMAIL_PORT", 587))

    if not all([email_user, email_password, email_host]):
        raise ValueError("Email credentials (EMAIL_USER, EMAIL_PASSWORD, EMAIL_HOST) are not set in the .env file.")

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
    print(f"--- Successfully sent email to {recipient_email} ---")


# --- Agent Tools ---

@tool
def get_weather_forecast_from_server(city: str, granularity: str = 'hourly') -> str:
    """Gets the hourly weather forecast (temp, wind, humidity, precip) for a city."""
    server_url = "http://localhost:8000/get_weather"
    payload = {"city": city, "granularity": "hourly"}
    headers = {"Content-Type": "application/json"}
    try:
        print(f"\n--- Calling Weather Server for: {city} ---\n")
        response = requests.post(server_url, data=json.dumps(payload), headers=headers)
        response.raise_for_status()
        return response.json()["forecast"]
    except requests.exceptions.RequestException as e:
        return f"Error contacting weather server: {e}"

@tool
def get_air_quality_from_server(city: str) -> str:
    """Gets the Air Quality Index (AQI) forecast for a city."""
    server_url = "http://localhost:8001/get_air_quality"
    payload = {"city": city}
    headers = {"Content-Type": "application/json"}
    try:
        print(f"\n--- Calling Air Quality Server for: {city} ---\n")
        response = requests.post(server_url, data=json.dumps(payload), headers=headers)
        response.raise_for_status()
        return response.json()["forecast"]
    except requests.exceptions.RequestException as e:
        return f"Error contacting air quality server: {e}"

@tool
def generate_overall_score_and_graph(
    hourly_forecast: str,
    air_quality_forecast: str,
    time_window: str
) -> str:
    """
    Analyzes environmental data (weather and AQI) to generate a 1-5 score
    for each hour and presents a bar graph visualization.
    """
    print(f"\n--- Generating Overall Score and Graph for window: '{time_window}' ---\n")
    try:
        # --- Parse Weather Data ---
        weather_df = pd.read_csv(StringIO("\n".join(hourly_forecast.split('\n')[2:-1])), delim_whitespace=True, header=None,
                                 names=['Num', 'Hour', 'Temp', 'Wind', 'WDir', 'Forecast', 'Precip', 'Humidity'])
        weather_df['Temp'] = weather_df['Temp'].str.replace('°F', '').astype(int)
        weather_df['Precip'] = weather_df['Precip'].str.replace('%', '').astype(int)
        weather_df['Humidity'] = weather_df['Humidity'].str.replace('%', '').astype(int)
        weather_df['Wind'] = pd.to_numeric(weather_df['Wind'], errors='coerce').fillna(0).astype(int)

        # --- Parse Air Quality Data ---
        aqi_df = pd.read_csv(StringIO("\n".join(air_quality_forecast.split('\n')[2:-1])), delim_whitespace=True, header=None,
                             names=['Date', 'AQI', 'Category', 'Pollutant'])
        today_aqi = aqi_df.iloc[0]['AQI'] if not aqi_df.empty else 0

        # --- Scoring Logic ---
        scores = []
        for _, row in weather_df.iterrows():
            score = 100
            if not (50 <= row['Temp'] <= 65): score -= 15
            if row['Wind'] > 15: score -= 20
            if row['Humidity'] > 85: score -= 20
            if row['Precip'] > 30: score -= 40
            if any(w in str(row['Forecast']).lower() for w in ['rain', 'showers', 'thunder']): score -= 30
            if today_aqi > 100: score -= 25
            scores.append(max(0, score))
        
        weather_df['score_100'] = scores
        weather_df['final_score'] = (weather_df['score_100'] / 100 * 4).round() + 1

        # --- Generate Bar Graph ---
        graph = f"Running Conditions for '{time_window}' (1=Worst, 5=Best):\n\n"
        for _, row in weather_df.iterrows():
            bar = '█' * int(row['final_score'])
            graph += f"{row['Hour']:>7}: {bar} ({int(row['final_score'])})\n"

        best_hour = weather_df.loc[weather_df['score_100'].idxmax()]
        recommendation = (
            f"Overall Recommendation:\nThe best time to run is around {best_hour['Hour']}, which has a score of {int(best_hour['final_score'])}/5.\n"
            f"Conditions: {best_hour['Temp']}°F, {best_hour['Precip']}% precip, and an AQI of {today_aqi}.\n\n"
            f"{graph}"
        )
        return recommendation
    except Exception as e:
        return f"Error generating score and graph: {e}."

@tool
def schedule_daily_email_report(city: str, time_window: str, recipient_email: str, scheduled_time: str = "06:00") -> str:
    """Schedules a daily email report for the best running time at a user-specified time."""
    def job():
        print(f"--- Running scheduled job: Generating report for {city} at {scheduled_time} ---")
        try:
            prompt = f"What is the best time to run in {city} during {time_window}?"
            report_content = run_agent_workflow(prompt)
            subject = f"Your Daily Running Forecast for {city}"
            body = f"Good morning!\n\nHere is your daily running forecast for {city}:\n\n{report_content}"
            send_email_notification(recipient_email, subject, body)
        except Exception as e:
            print(f"--- Error in scheduled job: {e} ---")

    schedule.every().day.at(scheduled_time).do(job)
    return f"Success! A daily running report for '{city}' will be sent to '{recipient_email}' at {scheduled_time} every day."

# --- Agent and Graph Definitions ---

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    next: str

# Define the Pydantic model for the supervisor's routing decision
class NextAgent(BaseModel):
    """The next agent to route to or FINISH."""
    next: str = Field(description="Should be one of the members list or FINISH.")

def create_agent(llm, tools, system_message: str):
    """Creates a tool-using agent graph."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_message),
        ("placeholder", "{messages}"),
    ])
    agent_model = llm.bind_tools(tools)
    agent_chain = prompt | agent_model

    def agent_node(state: AgentState):
        result = agent_chain.invoke(state)
        return {"messages": [result]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge("tools", "agent")
    graph.add_conditional_edges("agent", lambda state: "tools" if state["messages"][-1].tool_calls else END)
    graph.set_entry_point("agent")
    return graph.compile()

def run_agent_workflow(user_prompt: str) -> str:
    """
    Sets up and runs the full agent workflow for a given user prompt.
    """
    members = ["WeatherAgent", "AirQualityAgent", "OverallScoreAgent"]
    system_prompt = (
        "You are a supervisor managing a team of expert agents: {members}. "
        "Your primary goal is to help a user find the best time to run. "
        "Delegate tasks in order: Weather, then Air Quality, then Overall Score. "
        "After an agent has finished, review the conversation and decide the next step. "
        "When the OverallScoreAgent has provided the final analysis, the task is complete. Respond with FINISH."
    )
    
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-pro", temperature=0)
    
    weather_agent = create_agent(llm, [get_weather_forecast_from_server], "You are the WeatherAgent. Your job is to get the hourly weather forecast for a city.")
    air_quality_agent = create_agent(llm, [get_air_quality_from_server], "You are the AirQualityAgent. Your job is to get the air quality forecast for a city.")
    score_agent = create_agent(llm, [generate_overall_score_and_graph], "You are the OverallScoreAgent. Your job is to analyze all data (weather, AQI) to create a final score and graph.")

    supervisor_graph = StateGraph(AgentState)
    supervisor_graph.add_node("WeatherAgent", weather_agent)
    supervisor_graph.add_node("AirQualityAgent", air_quality_agent)
    supervisor_graph.add_node("OverallScoreAgent", score_agent)
    
    supervisor_prompt_template = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("placeholder", "{messages}"),
        ("system", "Given the conversation above, who should act next? Or should we FINISH? Select one of: {options}"),
    ])
    supervisor_chain = (
        supervisor_prompt_template | llm.with_structured_output(schema=NextAgent)
    )

    # Define the supervisor node
    def supervisor_node(state: AgentState):
        options = ["FINISH"] + members
        result = supervisor_chain.invoke({
            "messages": state["messages"], 
            "members": ", ".join(members), 
            "options": options
        })
        print(f"--- Supervisor Choice: {result.next} ---")
        return {"next": result.next}

    # Add the supervisor node to the graph
    supervisor_graph.add_node("supervisor", supervisor_node)
    
    # Add edges from each worker agent back to the supervisor
    for member in members:
        supervisor_graph.add_edge(member, "supervisor")

    # Define the conditional routing logic
    routing_map = {agent: agent for agent in members}
    routing_map["FINISH"] = END
    
    def router(state: AgentState):
        # This is the initial routing from the user input
        if not state.get("next"):
            return "supervisor"
        # This is the routing from the supervisor's decision
        return state.get("next")

    # The conditional edge starts from the supervisor and routes to the workers or END
    supervisor_graph.add_conditional_edges("supervisor", router, routing_map)
    
    # Set the entry point of the graph to the supervisor
    supervisor_graph.set_entry_point("supervisor")
    
    app = supervisor_graph.compile()

    inputs = {"messages": [HumanMessage(content=user_prompt)]}
    
    # Stream the graph execution and capture the final state
    final_state = None
    for output in app.stream(inputs, stream_mode="values"):
        final_state = output

    # The final report is in the content of the last ToolMessage in the conversation
    for message in reversed(final_state["messages"]):
        if isinstance(message, ToolMessage):
            return message.content
            
    return "Error: Could not find the final report in the agent's conversation."





