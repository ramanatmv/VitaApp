# -*- coding: utf-8 -*-
"""
Email formatting utilities that exactly match desktop appearance.
"""
from datetime import datetime

def create_email_html(content: str, city: str) -> str:
    """Create properly styled HTML email that matches desktop appearance exactly."""
    
    email_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Running Forecast for {city}</title>
        <style>
            /* Email client reset and base styles */
            * {{ 
                margin: 0; 
                padding: 0; 
                box-sizing: border-box; 
            }}
            
            body {{ 
                font-family: Arial, sans-serif !important; 
                margin: 0; 
                padding: 20px; 
                background-color: #f5f5f5; 
                line-height: 1.6;
                color: #333;
            }}
            
            .email-container {{ 
                max-width: 700px; 
                margin: 0 auto; 
                background-color: white; 
                border-radius: 10px; 
                overflow: hidden; 
                box-shadow: 0 4px 8px rgba(0,0,0,0.1); 
            }}
            
            .email-header {{ 
                background: linear-gradient(135deg, #4169E1, #6A5ACD); 
                color: white; 
                padding: 30px 20px; 
                text-align: center; 
            }}
            
            .email-header h1 {{ 
                margin: 0; 
                font-size: 28px; 
                font-weight: bold;
            }}
            
            .email-header p {{ 
                margin: 10px 0 0 0; 
                font-size: 16px; 
                opacity: 0.9; 
            }}
            
            .email-content {{ 
                padding: 20px; 
            }}
            
            /* Desktop forecast styling - EXACT MATCH */
            .email-content h2 {{
                color: #333 !important;
                font-size: 24px !important;
                margin-bottom: 5px !important;
            }}
            
            .email-content h3 {{
                color: #333 !important;
                font-size: 18px !important;
                margin: 25px 0 15px 0 !important;
                padding: 10px !important;
                background: rgba(255,255,255,0.8) !important;
                border-radius: 8px !important;
                display: flex !important;
                justify-content: space-between !important;
                align-items: center !important;
            }}
            
            .email-content strong {{
                color: #FF6B35 !important;
                font-weight: bold !important;
                font-size: 16px !important;
            }}
            
            /* Forecast block styling - match desktop exactly */
            .email-content > div {{
                border-radius: 8px !important;
                padding: 12px !important;
                margin: 10px 0 !important;
                font-family: Arial, sans-serif !important;
                font-size: 15px !important;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1) !important;
            }}
            
            /* Date and time styling */
            .email-content div div:first-child {{
                display: flex !important;
                justify-content: space-between !important;
                align-items: center !important;
                font-weight: bold !important;
                margin-bottom: 6px !important;
            }}
            
            /* Weather details line */
            .email-content div div:nth-child(2) {{
                margin-top: 6px !important;
                color: #555 !important;
                font-size: 0.9em !important;
            }}
            
            /* Forecast conditions section */
            .email-content div div[style*="background: rgba(33, 150, 243, 0.1)"] {{
                margin-top: 10px !important;
                padding: 10px !important;
                background: rgba(33, 150, 243, 0.1) !important;
                border-left: 4px solid #2196F3 !important;
                border-radius: 6px !important;
                font-size: 0.95em !important;
            }}
            
            /* Recommendations section */
            .email-content div div:last-child {{
                margin-top: 12px !important;
                font-size: 0.95em !important;
            }}
            
            .email-content ul {{
                margin: 5px 0 0 20px !important;
                padding: 0 !important;
            }}
            
            .email-content li {{
                margin: 0 !important;
                padding: 0 !important;
            }}
            
            /* Profile section styling - match desktop */
            .profile-section {{
                margin: 20px 0 !important;
                padding: 20px !important;
                background: #f8f9fa !important;
                border-radius: 8px !important;
                border-left: 4px solid #007bff !important;
            }}
            
            .profile-section h3 {{
                color: #007bff !important;
                margin-top: 0 !important;
                font-size: 20px !important;
            }}
            
            /* Global message styling */
            .global-message {{
                font-weight: bold !important;
                color: #FF6600 !important;
                margin-bottom: 20px !important;
            }}
            
            .footer {{ 
                background: #f5f5f5; 
                padding: 20px; 
                text-align: center; 
                color: #666; 
                font-size: 14px; 
                border-top: 1px solid #eee;
            }}
            
            .emoji {{ 
                font-size: 18px; 
            }}
            
            /* Temperature highlighting - exact match */
            span[style*="color: #FF6B35"] {{
                color: #FF6B35 !important;
                font-weight: bold !important;
                font-size: 18px !important;
            }}
            
            /* Score highlighting */
            span[style*="color: #4CAF50"] {{
                color: #4CAF50 !important;
                font-weight: bold !important;
            }}
            
            span[style*="color: #2196F3"] {{
                color: #2196F3 !important;
            }}
            
            /* Mobile responsiveness */
            @media only screen and (max-width: 600px) {{
                .email-container {{
                    margin: 0 !important;
                    border-radius: 0 !important;
                }}
                
                .email-content {{
                    padding: 15px !important;
                }}
                
                .email-header h1 {{
                    font-size: 24px !important;
                }}
                
                .email-content h2 {{
                    font-size: 20px !important;
                }}
                
                .email-content h3 {{
                    font-size: 16px !important;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="email-container">
            <div class="email-header">
                <h1><span class="emoji">🏃</span> Running Forecast <span class="emoji">🏃</span></h1>
                <p>Your personalized running conditions for {city}</p>
            </div>
            <div class="email-content">
                {content}
            </div>
            <div class="footer">
                <p><strong>💡 Tips:</strong> Stay hydrated and listen to your body!</p>
                <p><strong>⏰ Generated:</strong> {datetime.now().strftime('%A, %B %d, %Y at %I:%M %p')}</p>
                <p style="margin-top: 15px; font-size: 12px; color: #999;">
                    This is an automated weather forecast. Conditions can change rapidly - always check current conditions before heading out.
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return email_template

def enhance_forecast_for_email(html_content: str) -> str:
    """Enhance forecast HTML to exactly match desktop styling in emails."""
    import re
    
    # Ensure temperature displays are prominent and match desktop
    html_content = re.sub(
        r'(\d+)°F',
        r'<span style="color: #FF6B35; font-weight: bold; font-size: 18px;">\1°F</span>',
        html_content
    )
    
    # Enhance score displays to match desktop
    html_content = re.sub(
        r'(\d+\.\d+)/5',
        r'<span style="color: #4CAF50; font-weight: bold;">\1/5</span>',
        html_content
    )
    
    # Ensure forecast sections have proper styling
    html_content = re.sub(
        r'<strong>🌤️ Conditions:</strong>',
        r'<strong>🌤️ Conditions:</strong>',
        html_content
    )
    
    return html_content