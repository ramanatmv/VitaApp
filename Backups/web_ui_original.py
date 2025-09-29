from flask import Flask, request, render_template_string
import threading
from multi_agent_runner import run_agent_workflow, schedule_daily_email_report, run_scheduler, send_email_notification

app = Flask(__name__)

# --- HTML Template ---
# Using the | safe filter is the key to rendering HTML correctly.
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Running Weather Advisor</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #f4f7f6; margin: 0; padding: 20px; color: #333; }
        .container { max-width: 700px; margin: 40px auto; background: #fff; padding: 30px; border-radius: 10px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
        h1 { color: #2c3e50; text-align: center; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; font-weight: bold; color: #555; }
        input[type="text"], input[type="email"], input[type="time"] {
            width: 100%; padding: 12px; border-radius: 5px; border: 1px solid #ccc; box-sizing: border-box;
        }
        .button-group { display: flex; justify-content: space-between; gap: 15px; margin-top: 25px; }
        button {
            flex-grow: 1; background-color: #3498db; color: white; padding: 15px; border: none; border-radius: 5px;
            cursor: pointer; font-size: 16px; transition: background-color 0.3s;
        }
        button[name="action-schedule"] { background-color: #f39c12; }
        button[name="action-email-now"] { background-color: #2ecc71; }
        button:hover { opacity: 0.9; }
        .message {
            padding: 15px; margin-top: 25px; border-radius: 5px; text-align: center; font-weight: bold;
        }
        .message.success { background-color: #d4edda; color: #155724; }
        .message.info { background-color: #d1ecf1; color: #0c5460; }
        hr { border: 0; border-top: 1px solid #eee; margin: 30px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Running Weather Advisor</h1>
        <form method="post">
            <div class="form-group">
                <label for="city">City (e.g., Boston, MA)</label>
                <input type="text" id="city" name="city" required>
            </div>
            <div class="form-group">
                <label for="time_window">Time Window (e.g., tomorrow morning, between 8am and 11am)</label>
                <input type="text" id="time_window" name="time_window" required>
            </div>
            <div class="form-group">
                <label for="email">Your Email Address</label>
                <input type="email" id="email" name="email" required>
            </div>
             <div class="form-group">
                <label for="schedule_time">Daily Email Time</label>
                <input type="time" id="schedule_time" name="schedule_time" value="06:00" required>
            </div>
            <div class="button-group">
                <button type="submit" name="action" value="get_forecast">Get Instant Forecast</button>
                <button type="submit" name="action" value="email_now">Email Forecast Now</button>
                <button type="submit" name="action" value="schedule">Schedule Daily Email</button>
            </div>
        </form>

        {% if message %}
            <div class="message {{ 'success' if 'Success' in message or 'sent' in message else 'info' }}">
                {{ message }}
            </div>
        {% endif %}
        
        {% if report_html %}
            <hr>
            <div>
                {{ report_html | safe }}
            </div>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    message = ""
    report_html = ""
    if request.method == 'POST':
        city = request.form['city']
        time_window = request.form['time_window']
        email = request.form['email']
        action = request.form['action']
        
        prompt = f"What is the best time to run in {city} during {time_window}?"

        if action == 'get_forecast':
            report_html = run_agent_workflow(prompt, output_format="html")
            message = "Forecast generated!"
        
        elif action == 'email_now':
            report_html = run_agent_workflow(f"best time to run in {city}", output_format="html")
            subject = f"Your Instant Running Forecast for {city}"
            send_email_notification(
    email,
    subject,
    report_html,
    is_html=True  # This ensures HTML formatting
)
            message = f"Forecast generated and sent to {email}!"
            
        elif action == 'schedule':
            schedule_time = request.form['schedule_time']
            message = schedule_daily_email_report(city, time_window, email, schedule_time)

    return render_template_string(HTML_TEMPLATE, message=message, report_html=report_html)

if __name__ == '__main__':
    # Start the scheduler in a background thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Run the Flask app
    app.run(debug=True, port=5000)


