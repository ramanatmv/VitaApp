#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Emoji Fixer v4 - Uses Unicode escape sequences to avoid syntax errors
"""

import sys
import os

def get_emoji_fixes():
    """Return dictionary of corrupted strings to correct emojis using unicode."""
    return {
        # Running emojis (multiple corruption patterns)
        '\xc3\xb0\xc5\xb8\xc6\x92': '\U0001F3C3',  # 🏃
        '\xc3\x83\xc2\xb0\xc3\x85\xc2\xb8\xc3\x86\xc2\x92': '\U0001F3C3',  # Ã°Å¸ÂÆ
        # Thinking
        '\xc3\xb0\xc5\xb8\xc2\xa4\xe2\x80\x9c': '\U0001F914',  # 🤔
        '\xc3\x83\xc2\xb0\xc3\x85\xc2\xb8\xc3\x82\xc2\xa4\xc3\xa2\xe2\x82\xac\xc2\x9c': '\U0001F914',  # Ã°Å¸Â¤â
        # Signal bars
        '\xc3\xb0\xc5\xb8\xe2\x80\x9c\xc2\xb6': '\U0001F4F6',  # 📶
        # Stop sign / Octagonal sign
        '\xc3\xb0\xc5\xb8\xc5\xa1\xe2\x80\x91': '\U0001F6D1',  # 🛑
        '\xc3\x83\xc2\xb0\xc3\x85\xc2\xb8\xc3\x82\xc2\xba\xc3\xa2\xe2\x80\x9e\xc2\xa2': '\U0001F6D1',  # Ã°Å¸âºâ
        # Star
        '\xc3\xb0\xc5\xb8\xc5\x92\xc5\xb8': '\U0001F31F',  # 🌟
        # Sparkles
        '\xc3\xa2\xc5\x93\xc2\xa8': '\u2728',  # ✨
        # Orange heart
        '\xc3\xb0\xc5\xb8\xc2\xa7\xc2\xa1': '\U0001F9E1',  # 🧡
        # No entry
        '\xc3\xa2\xc5\xa1\xe2\x80\x9d': '\u26D4',  # ⛔
        '\xc3\x83\xc2\xa2\xc3\xa2\xe2\x80\x9a\xc2\xba\xc3\xa2\xe2\x82\xac\xc2\x9d': '\u26D4',  # Ã¢âºâ
        # Prohibited
        '\xc3\xb0\xc5\xb8\xc5\xa1\xc2\xab': '\U0001F6AB',  # 🚫
        # Wind
        '\xc3\xb0\xc5\xb8\xe2\x80\x99\xc2\xa8': '\U0001F4A8',  # 💨
        # Droplet
        '\xc3\xb0\xc5\xb8\xe2\x80\x99\xc2\xa7': '\U0001F4A7',  # 💧
        # Rain
        '\xc3\xb0\xc5\xb8\xc5\x92\xc2\xa7\xc3\xaf\xc2\xb8\xc2\x8f': '\U0001F327\uFE0F',  # 🌧️
        # Partly cloudy
        '\xc3\xb0\xc5\xb8\xc5\x92\xc2\xa4\xc3\xaf\xc2\xb8\xc2\x8f': '\U0001F324\uFE0F',  # 🌤️
        # Thermometer
        '\xc3\xb0\xc5\xb8\xc5\x92\xc2\xa1\xc3\xaf\xc2\xb8\xc2\x8f': '\U0001F321\uFE0F',  # 🌡️
        # Snowflake
        '\xc3\xa2\xc4\x84\xc2\x84\xc3\xaf\xc2\xb8\xc2\x8f': '\u2744\uFE0F',  # ❄️
        # Thunderstorm (multiple patterns)
        '\xc3\xa2\xc5\xa1\xcb\x86\xc3\xaf\xc2\xb8\xc2\x8f': '\u26C8\uFE0F',  # ⛈️
        '\xc3\x83\xc2\xa2\xc3\xa2\xe2\x80\x9a\xc2\xba\xc3\x8b\xc5\xa0\xc3\x8f\xc2\xaf\xc2\xb8\xc2\x8f': '\u26C8\uFE0F',  # Ã¢âºËÃ¯Â¸Â
        # Moon (multiple patterns)
        '\xc3\xb0\xc5\xb8\xc5\x92\xc2\x99': '\U0001F319',  # 🌙
        '\xc3\x83\xc2\xb0\xc3\x85\xc2\xb8\xc3\x85\xc2\x92\xc2\xa2': '\U0001F319',  # Ã°Å¸Åâ¢
        # Sun (multiple patterns)
        '\xe2\x98\x80\xef\xb8\x8f': '☀️',       # sun
        '\xc3\xa2\xc2\x98\xc2\x80\xc3\xaf\xc2\xb8\xc2\x8f': '☀️',  # âï¸Â
        # Sunrise
        '\xc3\xb0\xc5\xb8\xc5\x92\xc2\x85': '\U0001F305',  # 🌅
        '\xc3\xb0': '\U0001F305',  # ð (partial corruption)
        # Sunset/dusk
        '\xc3\x83\xc2\xb0\xc3\x85\xc2\xb8\xc3\x85\xc2\x92\xc2\xa0': '\U0001F320',  # Ã°Å¸Åâ  (shooting star/dusk)
        # Cloud
        '\xc3\xa2\xcb\x9c\xc2\x81\xc3\xaf\xc2\xb8\xc2\x8f': '\u2601\uFE0F',  # ☁️
        # Lightbulb
        '\xc3\xb0\xc5\xb8\xe2\x80\x99\xc2\xa1': '\U0001F4A1',  # 💡
        # Clipboard
        '\xc3\xb0\xc5\xb8\xe2\x80\x9c\xc5\x8b': '\U0001F4CB',  # 📋
        # Calendar
        '\xc3\xb0\xc5\xb8\xe2\x80\x9c\xc2\x85': '\U0001F4C5',  # 📅
        # Pin
        '\xc3\xb0\xc5\xb8\xe2\x80\x9c\xc2\x8d': '\U0001F4CD',  # 📍
        # Arrows
        '\xc3\xb0\xc5\xb8\xe2\x80\x94\xc2\x84': '\U0001F504',  # 🔄
        # Eye
        '\xc3\xb0\xc5\xb8\xe2\x80\x98\xc2\x81\xc3\xaf\xc2\xb8\xc2\x8f': '\U0001F441\uFE0F',  # 👁️
        # Trophy
        '\xc3\xb0\xc5\xb8\xc2\x86': '\U0001F3C6',  # 🏆
        # Muscle
        '\xc3\xb0\xc5\xb8\xe2\x80\x99\xc2\xaa': '\U0001F4AA',  # 💪
        # Salad
        '\xc3\xb0\xc5\xb8\xc2\xa5\xe2\x80\x93': '\U0001F957',  # 🥗
        # Lungs
        '\xc3\xb0\xc5\xb8\xc2\xab\xc2\x81': '\U0001FAC1',  # 🫁
        # Meditation
        '\xc3\xb0\xc5\xb8\xc2\xa7\xcb\x9c': '\U0001F9D8',  # 🧘
        # Lotus
        '\xc3\xb0\xc5\xb8\xc2\xaa\xc2\xb7': '\U0001FAB7',  # 🪷
        # Pointing right
        '\xc3\xb0\xc5\xb8\xe2\x80\x98\xc2\x89': '\U0001F449',  # 👉
        # Sunrise
        '\xc3\xb0\xc5\xb8\xc5\x92\xc2\x85': '\U0001F305',  # 🌅
        # Sunrise mountains
        '\xc3\xb0\xc5\xb8\xc5\x92\xc2\x84': '\U0001F304',  # 🌄
        # Thumbs up
        '\xc3\xb0\xc5\xb8\xe2\x80\x98\xc2\x8d': '\U0001F44D',  # 👍
        # Shocked
        '\xc3\xb0\xc5\xb8\xcb\x9c\xc2\xb1': '\U0001F631',  # 😱
        # Star symbol (multiple patterns)
        '\xc3\xa2\xc2\xad\xc2\x90': '\u2B50',  # ⭐
        '\xc3\x83\xc2\xa2\xc3\xa2\xe2\x82\xac\xc2\xad\xc3\x82\xc2\xa0': '\u2B50',  # â­Â
        # Clock
        '\xc3\xa2\xc2\x8f\xc2\xb0': '\u23F0',  # ⏰
        # Hourglass
        '\xc3\xa2\xc2\x8f\xc2\xb3': '\u23F3',  # ⏳
        # Gear
        '\xc3\xa2\xc5\xa1\xc2\x99\xc3\xaf\xc2\xb8\xc2\x8f': '\u2699\uFE0F',  # ⚙️
        # Warning
        '\xc3\xa2\xc5\xa1\xc2\xa0\xc3\xaf\xc2\xb8\xc2\x8f': '\u26A0\uFE0F',  # ⚠️
        # Lightning
        '\xc3\xa2\xc5\xa1\xc2\xa1': '\u26A1',  # ⚡
        # Degree F
        '\xc2\xb0F': '\u00B0F',  # °F
        # Bullet
        '\xc3\xa2\xe2\x82\xac\xc2\xa2': '\u2022',  # •
    }

def fix_file(input_path, output_path=None):
    """Fix emoji encoding in file."""
    
    if output_path is None:
        output_path = input_path
    
    # Read as bytes to handle any encoding
    try:
        with open(input_path, 'rb') as f:
            content = f.read()
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return 0
    
    # Decode as latin-1 to see the corruption
    content_str = content.decode('latin-1')
    
    fixes = get_emoji_fixes()
    total_fixes = 0
    
    for corrupted, correct in fixes.items():
        if corrupted in content_str:
            count = content_str.count(corrupted)
            content_str = content_str.replace(corrupted, correct)
            total_fixes += count
            # Show a clean display
            corrupt_display = corrupted.encode('latin-1').decode('utf-8', errors='replace')
            print(f"Fixed {count} instance(s): {corrupt_display} -> {correct}")
    
    # Write back as UTF-8
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content_str)
    except Exception as e:
        print(f"❌ Error writing file: {e}")
        return 0
    
    if total_fixes > 0:
        print(f"\n✅ Fixed {total_fixes} corrupted emojis!")
        print(f"📝 Saved to: {output_path}")
    else:
        print("\n✅ No corrupted emojis found!")
    
    return total_fixes

def main():
    if len(sys.argv) < 2:
        print("Usage: python fix_emojis.py <input_file> [output_file]")
        print("\nExample:")
        print("  python fix_emojis.py helper_functions_emoji.py")
        print("  python fix_emojis.py helper_functions_emoji.py fixed.py")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not os.path.exists(input_file):
        print(f"❌ File not found: {input_file}")
        sys.exit(1)
    
    # Backup
    if output_file is None:
        import shutil
        backup = input_file + '.backup'
        shutil.copy2(input_file, backup)
        print(f"📦 Backup created: {backup}\n")
    
    print(f"🔧 Fixing emojis in: {input_file}")
    print("=" * 60)
    
    fix_file(input_file, output_file)

if __name__ == "__main__":
    main()