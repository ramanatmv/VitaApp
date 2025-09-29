#!/usr/bin/env python3
# Comprehensive emoji fix for helper_functions.py

import re

def fix_all_emojis():
    file_path = '/Users/ramanatumuluri/Desktop/RunApp_GPT/helper_functions.py'
    
    # Read file as bytes first, then decode
    with open(file_path, 'rb') as f:
        content_bytes = f.read()
    
    # Try to decode and fix encoding issues
    try:
        content = content_bytes.decode('utf-8')
    except UnicodeDecodeError:
        content = content_bytes.decode('utf-8', errors='replace')
    
    # Count original issues
    original_issues = 0
    for char in ['ð', 'â', 'Â']:
        original_issues += content.count(char)
    
    print(f"Found {original_issues} corrupted characters to fix...")
    
    # Apply fixes systematically
    fixes = [
        # Calendar/time
        ('ðŸ"', '📅'),
        ('â³', '⏳'),
        ('â­', '⭐'),
        
        # Food/nutrition  
        ('ðŸŽ', '🍎'),
        
        # Fitness/strength
        ('ðŸ‹ï¸â€â™€ï¸', '🏋️'),
        ('ðŸ‹ï¸â€â™‚ï¸', '🏋️'),  
        ('ðŸ'ª', '💪'),
        ('ðŸ†', '🏆'),
        
        # Nature/mindfulness
        ('ðŸŒ¸', '🌸'),
        ('ðŸª·', '🪷'),
        ('ðŸ§˜â€â™€ï¸', '🧘'),
        ('ðŸ§˜â€â™‚ï¸', '🧘'),
        
        # Weather
        ('ðŸŒ¡ï¸', '🌡️'),
        ('ðŸ'¨', '💨'),
        ('ðŸŒ§ï¸', '🌧️'),
        ('ðŸŒ„', '🌄'),
        ('ðŸ'§', '💧'),
        
        # Air quality
        ('ðŸ«', '🫁'),
        
        # Symbols and punctuation
        ('â€¢', '•'),
        ('â€', ''),  # Remove zero-width
        ('Â°', '°'),  # Degree symbol
        ('â„¢', '™'),
        
        # Training plan calendar
        ('ðŸ"…', '📅'),
    ]
    
    changes_made = 0
    for old, new in fixes:
        if old in content:
            count = content.count(old)
            content = content.replace(old, new)
            changes_made += count
            print(f"  Fixed {count} instances of '{old}' -> '{new}'")
    
    # Write back with UTF-8 encoding
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    # Count remaining issues
    remaining_issues = 0
    for char in ['ð', 'â', 'Â']:
        remaining_issues += content.count(char)
    
    print(f"\n✅ BULK FIX COMPLETE!")
    print(f"📊 Fixed: {changes_made} corrupted characters")
    print(f"📊 Remaining: {remaining_issues} characters still need fixing")
    print(f"📊 Success rate: {((original_issues - remaining_issues) / original_issues * 100):.1f}%")
    
    return changes_made > 0

if __name__ == "__main__":
    success = fix_all_emojis()
    if success:
        print("\n🎉 Emoji fix operation completed successfully!")
    else:
        print("\n❌ No changes were made")
