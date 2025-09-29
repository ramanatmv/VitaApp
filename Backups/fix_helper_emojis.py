import re

# Read the file
with open('helper_functions.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix specific lines with corrupted emojis
fixes = [
    # Line 252: Current Goal
    ('ðŸƒâ€â™€ï¸ Current Goal', '🏃 Current Goal'),
    # Line 287: Today indicator
    ('ðŸ" Today', '📍 Today'),
    # Line 321: Nutrition
    ('ðŸŽ Nutrition Focus', '🍎 Nutrition Focus'),
    # Line 334: Strength training emoji
    ('ðŸ‹ï¸â€â™€ï¸', '🏋️'),
    # Line 335: Strength training text
    ('ðŸ'ª Strength Training', '💪 Strength Training'),
    # Line 348: Mindfulness flower
    ('ðŸŒ¸', '🌸'),
    # Line 349: Mindfulness lotus
    ('ðŸª· Mindfulness Plan', '🧘 Mindfulness Plan'),
    # Line 565: Heat stress
    ('ðŸŒ¡ï¸ Heat Stress Analysis', '🌡️ Heat Stress Analysis'),
    # Line 576: Wind
    ('ðŸ'¨ Wind Patterns', '💨 Wind Patterns'),
    # Line 587: Precipitation
    ('ðŸŒ§ï¸ Precipitation', '��️ Precipitation'),
    # Line 598: Air Quality
    ('ðŸ« Air Quality', '🫁 Air Quality'),
    # Line 615: Summary
    ('ðŸ"Š Today\'s Running Summary', '📊 Today\'s Running Summary'),
]

# Apply fixes
for old, new in fixes:
    content = content.replace(old, new)

# Write back
with open('helper_functions.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed all corrupted emojis in helper_functions.py")
