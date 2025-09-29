import os
import requests
import json
from typing import TypedDict, Annotated
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
# Updated import for Google Gemini
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
# Import ToolNode, the replacement for ToolExecutor
from langgraph.prebuilt import ToolNode
import operator
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Tool Definition ---
# This is the tool that will be called by the agent. It communicates with our MCP server.

@tool
def get_weather_forecast_from_server(city: str) -> str:
    """Gets the weather forecast for a city by calling the MCP server."""
    # Ensure the MCP server is running on http://localhost:8000
    server_url = "http://localhost:8000/get_weather"
    payload = {"city": city}
    headers = {"Content-Type": "application/json"}
    try:
        print(f"\n--- Calling Weather Tool Server for city: {city} ---\n")
        response = requests.post(server_url, data=json.dumps(payload), headers=headers)
        response.raise_for_status()
        # The server returns a dictionary, e.g., {"forecast": "Weather forecast for..."}
        # We extract the 'forecast' value to return to the agent.
        return response.json()["forecast"]
    except requests.exceptions.RequestException as e:
        return f"Error contacting weather server: {e}"
    except json.JSONDecodeError:
        return f"Error decoding JSON from server. Response text: {response.text}"

# --- Agent State ---
# This defines the structure of the data that will be passed between nodes in the graph.

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]

# --- Graph Definition ---

# 1. Setup Tools and Model
tools = [get_weather_forecast_from_server]

# The ToolNode is a more modern way to integrate tools into the graph.
tool_node = ToolNode(tools)

# Make sure to set your GOOGLE_API_KEY environment variable
# It's recommended to use a .env file for this (see updated README)
# We are now using Google's Gemini model
model = ChatGoogleGenerativeAI(model="gemini-2.5-pro", temperature=0, convert_system_message_to_human=True)
model = model.bind_tools(tools)

# 2. Define Nodes
def should_continue(state: AgentState):
    """Conditional edge: decides whether to call a tool or end the conversation."""
    last_message = state["messages"][-1]
    # If there are no tool calls, we stop.
    if not last_message.tool_calls:
        return "end"
    # Otherwise, we continue to call the tool.
    return "continue"

def call_model(state: AgentState):
    """Node: calls the Gemini model to get a response or a tool call."""
    print("--- Calling Model ---")
    response = model.invoke(state["messages"])
    # We return a list, because we want to add it to the existing list
    return {"messages": [response]}

# The call_tool function is now replaced by the ToolNode.

# 3. Build the Graph
workflow = StateGraph(AgentState)

# Add the nodes
workflow.add_node("agent", call_model)
workflow.add_node("action", tool_node) # Use the ToolNode directly

# Set the entry point
workflow.set_entry_point("agent")

# Add the conditional edge
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {
        "continue": "action",
        "end": END,
    },
)

# Add the normal edge
workflow.add_edge("action", "agent")

# Compile the graph into a runnable app
app = workflow.compile()


# --- Main Execution Block ---
if __name__ == "__main__":
    print("LangGraph Weather Agent (using Gemini)")
    print("Ask about the weather in a specific city (e.g., 'what is the weather in Paris, France?')")
    print("Type 'exit' to quit.")

    while True:
        user_input = input("\nYou: ")
        if user_input.lower() == 'exit':
            break
        
        # The input to the graph is a list of messages
        inputs = {"messages": [HumanMessage(content=user_input)]}
        
        # Invoke the graph and stream the output
        for output in app.stream(inputs, stream_mode="values"):
            # The output is the entire state, we only want to print the last message
            last_message = output["messages"][-1]
            
            # Only print the final response from the Assistant (which is an AIMessage without tool calls)
            if isinstance(last_message, AIMessage) and not last_message.tool_calls:
                 # Check if content is a list and join if necessary, otherwise use as is
                if isinstance(last_message.content, list):
                    content = "".join(part.get("text", "") for part in last_message.content if isinstance(part, dict))
                else:
                    content = last_message.content
                print("\nAssistant:", content)

