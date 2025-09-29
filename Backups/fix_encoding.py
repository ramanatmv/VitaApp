import os
import re

files_to_fix = [
    'multi_agent_runner.py',
    'helper_functions.py'
]

replacements = {
    'âš ï¸': '⚠️',
    'â€"': '—',
    'ðŸ"‹': '📋', 
    'ðŸ†': '🏆',
    'ðŸƒâ€â™€ï¸ðŸƒâ€â™‚ï¸': '🏃',
    'ðŸƒâ€â™€ï¸': '🏃',
    'ðŸƒâ€â™‚ï¸': '🏃',
    'ðŸ¥—': '🥗',
    'â˜€ï¸': '☀️',
    'ðŸŒ…': '🌅',
    'ðŸ"': '📋',
    'âœ…': '✅',
    'ðŸ"': '📍',
    'â³': '⏳'
}

for filename in files_to_fix:
    if os.path.exists(filename):
        print(f"Fixing encoding in {filename}")
        
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        for old, new in replacements.items():
            content = content.replace(old, new)
        
        if content != original_content:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"  ✅ Fixed {filename}")
        else:
            print(f"  ℹ️ No changes needed for {filename}")

print("Encoding fix completed!")
