import google.generativeai as genai
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional

# Configure Gemini API
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

logger = logging.getLogger(__name__)

def get_llm_run_plan_summary(runner_profile_prompt: str) -> str:
    """
    Generate running plan summary using Gemini 2.0 Flash.
    """
    try:
        # Initialize the model
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Enhanced system prompt for running coaching
        system_prompt = """You are an expert certified running coach and wellness advisor with 15+ years of experience. Generate personalized, safe, and effective training plans based STRICTLY on the runner's profile and selections. 

CRITICAL REQUIREMENTS - NEVER DEVIATE:

1. EVIDENCE-BASED ONLY: All recommendations must be based on established sports science, peer-reviewed research, and proven coaching methodologies. NO speculation or unproven methods.

2. STRICT USER ADHERENCE: Only provide guidance for options the user specifically selected:
   - If nutrition is NOT selected, do NOT include nutrition advice
   - If strength training is NOT selected, do NOT include strength exercises  
   - If mindfulness is NOT selected, do NOT include mental training
   - Only address the specific plan type, goals, and preferences they chose

3. SAFETY FIRST: Injury prevention and gradual progression based on established training principles
4. INDIVIDUALIZATION: Adapt to runner's exact experience level, stated goals, and specific limitations
5. REALISTIC EXPECTATIONS: Only achievable goals with scientifically-backed timelines

SCIENTIFIC GROUNDING REQUIRED:
- Base all training intensities on established heart rate zones and RPE scales
- Use proven periodization principles (base building, build, peak, recovery)
- Apply evidence-based progression rates (10% rule, etc.)
- Recommend only scientifically-validated recovery methods
- Cite established training methodologies when relevant

CONTENT RESTRICTIONS:
- NO fictional or made-up workout names or methods
- NO unproven supplements or nutrition claims
- NO medical advice beyond basic exercise science
- NO recommendations outside user's selected preferences
- NO generic advice - everything must be specific to their profile

FORMAT REQUIREMENTS:
- Use clear HTML formatting with proper headings (h3, h4)
- Include specific, measurable workout details (distance, pace, time, intensity zones)
- Provide actionable daily guidance based on their selections only
- Keep recommendations practical and scientifically sound
- Use bullet points and numbered lists for clarity
- Include realistic, evidence-based language

PERIODIZATION REQUIREMENTS:
- Create scientifically-based periodized plans with distinct phases
- Base Building Phase (weeks 1-40%): Aerobic development, injury prevention, habit formation
- Build Phase (weeks 40-70%): Increased intensity, sport-specific training, strength integration
- Peak Phase (weeks 70-85%): Race preparation, lactate threshold work, speed development  
- Taper Phase (weeks 85-100%): Recovery emphasis, maintain fitness, mental preparation
- Use evidence-based plan durations: 8 weeks (fitness), 12 weeks (general fitness goals), 16 weeks (half marathon), 20 weeks (marathon)

MANDATORY SAFETY NOTES:
- Always recommend proper warm-up and cool-down protocols
- Emphasize listening to body signals and signs of overtraining
- Include rest day importance based on recovery science
- Mention when to seek medical advice for injuries or health concerns
- Promote gradual progression principles backed by sports science (10% rule, easy/hard day alternation)"""

        # Combine system prompt with user profile
        full_prompt = f"{system_prompt}\n\n{runner_profile_prompt}\n\nGenerate a complete training plan with running workouts as the primary focus."
        
        # Generate response
        response = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=4000,
                top_p=0.8,
                top_k=40
            )
        )
        
        if response.text:
            logger.info(f"LLM generated plan summary: {response.text[:200]}...")
            return response.text
        else:
            logger.warning("Empty response from Gemini API")
            raise Exception("Empty response from AI service")
            
    except Exception as e:
        logger.error(f"Error calling Gemini API: {e}")
        raise Exception(f"AI service error: {str(e)}")

def generate_llm_enhanced_workout_details(plan_type: str, day: str, week: int, additional_context: str = "") -> Dict:
    """
    Generate detailed workout information using Gemini 2.0 Flash for mobile cards.
    """
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Construct detailed prompt for workout generation
        workout_prompt = f"""As an expert running coach, generate a detailed workout plan for:

PARAMETERS:
- Plan Type: {plan_type}
- Day of Week: {day}
- Training Week: {week}
- Additional Context: {additional_context}

GENERATE A SPECIFIC WORKOUT WITH:
1. Workout Name (descriptive, motivating)
2. Total Duration (realistic time estimate)
3. Intensity Level (Easy/Moderate/Hard/Very Hard)
4. Detailed Instructions (step-by-step workout structure)
5. Recovery Notes (post-workout care and preparation for next session)

CONSIDERATIONS:
- Week {week} progression level
- Day-of-week typical energy levels
- Appropriate intensity distribution
- Injury prevention focus
- Practical time constraints

FORMAT: Respond with ONLY a JSON object containing exactly these keys:
{{"name": "workout name", "duration": "time estimate", "intensity": "intensity level", "instructions": "detailed workout steps", "recovery": "recovery and preparation notes"}}

No additional text or formatting outside the JSON."""

        response = model.generate_content(
            workout_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.6,
                max_output_tokens=800,
                top_p=0.8,
                top_k=20
            )
        )
        
        if response.text:
            try:
                # Clean the response and parse JSON
                response_text = response.text.strip()
                
                # Remove markdown formatting if present
                if response_text.startswith('```json'):
                    response_text = response_text[7:]
                if response_text.endswith('```'):
                    response_text = response_text[:-3]
                response_text = response_text.strip()
                
                import json
                workout_data = json.loads(response_text)
                
                # Validate required keys
                required_keys = ['name', 'duration', 'intensity', 'instructions', 'recovery']
                if all(key in workout_data for key in required_keys):
                    return workout_data
                else:
                    logger.warning(f"Missing required keys in workout data: {workout_data}")
                    return {
                        'name': 'Service Temporarily Unavailable',
                        'duration': 'N/A',
                        'intensity': 'N/A',
                        'instructions': 'Unable to generate workout details. Please try again in a few minutes.',
                        'recovery': 'AI coaching system is temporarily unavailable.'
                    }
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from Gemini response: {e}")
                logger.debug(f"Response text: {response.text}")
                return {
                    'name': 'Service Temporarily Unavailable',
                    'duration': 'N/A',
                    'intensity': 'N/A',
                    'instructions': 'Unable to generate workout details. Please try again in a few minutes.',
                    'recovery': 'AI coaching system is temporarily unavailable.'
                }
        else:
            logger.warning("Empty response from Gemini API for workout details")
            return {
                'name': 'Service Temporarily Unavailable',
                'duration': 'N/A',
                'intensity': 'N/A',
                'instructions': 'Unable to generate workout details. Please try again in a few minutes.',
                'recovery': 'AI coaching system is temporarily unavailable.'
            }
            
    except Exception as e:
        logger.error(f"Error calling Gemini API for workout details: {e}")
        return {
            'name': 'Service Temporarily Unavailable',
            'duration': 'N/A',
            'intensity': 'N/A',
            'instructions': 'Unable to generate workout details. Please try again in a few minutes.',
            'recovery': 'AI coaching system is temporarily unavailable.'
        }

def format_runner_profile_prompt(form_data: dict) -> str:
    """Enhanced runner profile prompt with new UI fields."""
    
    # Basic profile information
    vita_avatar = form_data.get('vita_avatar', [''])[0]
    vita_description = form_data.get('vita_description', [''])[0]
    age = form_data.get('age', [''])[0]
    gender = form_data.get('gender', [''])[0]
    mobility_restrictions = form_data.get('mobility_restrictions', [''])[0]
    
    # Enhanced plan information
    run_plan = form_data.get('run_plan', [''])[0]
    plan_type = form_data.get('plan_type', [''])[0]
    plan_period = form_data.get('plan_period', [''])[0]
    plan_display = form_data.get('plan_display', [''])[0]
    plan_start_date = form_data.get('plan_start_date', [''])[0]
    
    # New wellness fields
    show_nutrition = form_data.get('show_nutrition', [''])[0]
    strength_training = form_data.get('strength_training', [''])[0]
    mindfulness_plan = form_data.get('mindfulness_plan', [''])[0]
    
    # Goal-specific information
    fitness_goals = form_data.get('fitness_goals', [])
    athletic_goal = form_data.get('athletic_goal', [''])[0]
    
    # Enhanced additional details
    additional_details = form_data.get('additional_details', [''])[0]
    dietary_restrictions = form_data.get('dietary_restrictions', [''])[0]
    health_conditions = form_data.get('health_conditions', [''])[0]
    
    # Build the comprehensive prompt
    prompt_parts = []
    
    # Header
    prompt_parts.append("RUNNER PROFILE ANALYSIS:")
    prompt_parts.append("="*50)
    
    # Basic Information
    # Vita Profile
    if vita_avatar:
        prompt_parts.append(f"Vita Avatar: {vita_avatar}")

    if vita_description:
        prompt_parts.append(f"Personal Vision: {vita_description}")
    
    if age:
        prompt_parts.append(f"Age: {age} years old")
    
    if gender:
        prompt_parts.append(f"Gender: {gender}")
    
    if mobility_restrictions:
        prompt_parts.append(f"Mobility Restrictions/Injuries: {mobility_restrictions}")
    
    # Plan Type and Structure
    if run_plan:
        plan_names = {
            'daily_fitness': 'Daily Fitness Running Program',
            'fitness_goal': 'Running with Specific Fitness Goals',
            'athletic_goal': 'Athletic Performance & Racing Program'
        }
        prompt_parts.append(f"Training Program: {plan_names.get(run_plan, run_plan)}")
        
        # Add plan type detail for daily fitness
        if run_plan == 'daily_fitness' and plan_type:
            type_names = {
                'individual': 'Individual Training Plan',
                'group': 'Group/Family Plan (designed for training with family/friends of similar age/fitness level)'
            }
            prompt_parts.append(f"Plan Structure: {type_names.get(plan_type, plan_type)}")
    
    # Initialize plan_duration_weeks at function level
    plan_duration_weeks = 12  # Default
    current_week_num = 1
    
    if plan_period:
        week_num = plan_period.replace('week_', '')
        
        # The selected week number indicates the TOTAL plan duration
        # User selected Week 8 = 8-week plan, starting at Week 1
        plan_duration_weeks = int(week_num)
        current_week_num = 1  # Always start at Week 1
        
        # Check what display option was selected
        if plan_display == 'full_plan':
            # User wants to see ALL weeks from 1 to plan_duration_weeks
            prompt_parts.append(f"Plan Duration: {plan_duration_weeks}-week comprehensive program")
            prompt_parts.append(f"Current Week: Week {current_week_num} of {plan_duration_weeks}")
            prompt_parts.append(f"IMPORTANT: Generate COMPLETE {plan_duration_weeks}-week training plan starting from Week 1")
            prompt_parts.append(f"Show progression from Week 1 through Week {plan_duration_weeks}")
        elif plan_display == 'one_day':
            # User wants only today's workout
            prompt_parts.append(f"Current Training Week: Week {current_week_num} of {plan_duration_weeks}-week program")
            prompt_parts.append(f"IMPORTANT: Generate ONLY today's specific workout for Week {current_week_num}")
            prompt_parts.append("Focus on detailed single-day workout plan")
        elif plan_display == 'this_week':
            # User wants this week's plan only
            prompt_parts.append(f"Current Training Week: Week {current_week_num} of {plan_duration_weeks}-week program")
            prompt_parts.append(f"IMPORTANT: Generate ONLY Week {current_week_num}'s training plan (7 days)")
            prompt_parts.append("Show all workouts for this week with daily breakdown")
        
        # Add periodization phase context based on Week 1 of the plan
        phase_percentage = (current_week_num / plan_duration_weeks) * 100
        if phase_percentage <= 40:
            current_phase = "Base Building Phase (aerobic development, injury prevention)"
        elif phase_percentage <= 70:
            current_phase = "Build Phase (increased intensity, sport-specific training)"
        elif phase_percentage <= 85:
            current_phase = "Peak Phase (race preparation, tapering begins)"
        else:
            current_phase = "Taper/Recovery Phase (maintain fitness, prepare for goal)"
        
        if plan_display == 'full_plan':
            prompt_parts.append(f"Starting Phase: Week 1 - {current_phase}")
        else:
            prompt_parts.append(f"Training Phase: {current_phase}")
            
        weeks_remaining = plan_duration_weeks - current_week_num
        if weeks_remaining > 0 and plan_display != 'full_plan':
            prompt_parts.append(f"Weeks Remaining: {weeks_remaining} weeks to goal achievement")
    else:
        # No plan period specified - use defaults based on goal type
        if run_plan == 'athletic_goal' and athletic_goal:
            if 'm_' in athletic_goal:
                plan_duration_weeks = 20
            elif 'hm_' in athletic_goal:
                plan_duration_weeks = 16
        elif run_plan == 'fitness_goal':
            plan_duration_weeks = 12
        elif run_plan == 'daily_fitness':
            plan_duration_weeks = 8
        
        prompt_parts.append(f"Plan Duration: {plan_duration_weeks} weeks (evidence-based duration for this goal type)")
        
        if plan_display == 'full_plan':
            prompt_parts.append(f"IMPORTANT: Generate COMPLETE {plan_duration_weeks}-week training plan starting from Week 1")
        else:
            prompt_parts.append("Starting Phase: Week 1 - Base Building Phase (establish routine, build aerobic base)")
    
    # Fitness Goals (specific to fitness_goal plan type)
    if run_plan == 'fitness_goal' and fitness_goals:
        goal_descriptions = {
            'starting': 'Beginning runner - building base fitness safely',
            'weight_loss': 'Weight management and body composition goals',
            'endurance': 'Improving cardiovascular endurance and running stamina'
        }
        selected_goals = [goal_descriptions.get(goal, goal) for goal in fitness_goals]
        prompt_parts.append(f"Primary Fitness Objectives: {'; '.join(selected_goals)}")
    
    # Athletic Goals (specific to athletic_goal plan type)
    if run_plan == 'athletic_goal' and athletic_goal:
        goal_descriptions = {
            'hm_300': 'Sub-3:00 Half Marathon (competitive recreational level)',
            'hm_230': 'Sub-2:30 Half Marathon (advanced recreational level)', 
            'hm_200': 'Sub-2:00 Half Marathon (competitive level)',
            'hm_130': 'Sub-1:30 Half Marathon (elite recreational level)',
            'm_530': 'Sub-5:30 Marathon (recreational level)',
            'm_500': 'Sub-5:00 Marathon (intermediate level)',
            'm_430': 'Sub-4:30 Marathon (advanced level)',
            'm_400': 'Sub-4:00 Marathon (competitive level)'
        }
        prompt_parts.append(f"Race Goal: {goal_descriptions.get(athletic_goal, athletic_goal)}")
    
    # Plan Display Requirements with proper date handling
    if plan_display:
        current_date = datetime.now().strftime("%B %d, %Y")
        
        # Determine effective start date
        if plan_start_date:
            try:
                start_date_obj = datetime.strptime(plan_start_date, "%Y-%m-%d")
                formatted_start_date = start_date_obj.strftime("%B %d, %Y")
                effective_start_date = formatted_start_date
            except:
                effective_start_date = current_date
        else:
            effective_start_date = current_date
        
        display_requirements = {
            'full_plan': f'Provide complete multi-week training progression starting {effective_start_date}',
            'one_day': f'Focus on detailed workout plan for TODAY ({current_date}) - adjust for plan start date if different',
            'this_week': f'Provide detailed plan for THIS WEEK starting from {effective_start_date}'
        }
        prompt_parts.append(f"Plan Scope Required: {display_requirements.get(plan_display, plan_display)}")
        
        if plan_start_date:
            prompt_parts.append(f"Training Plan Start Date: {effective_start_date}")
            if plan_start_date != current_date:
                prompt_parts.append("⚠️  IMPORTANT: Adjust timeline and current week calculations based on actual start date vs today's date")
    
    # Wellness Components - STRICT USER SELECTION ADHERENCE
    wellness_components = []
    wellness_exclusions = []
    
    if show_nutrition == 'yes':
        wellness_components.append("NUTRITION GUIDANCE REQUIRED: Include evidence-based fueling strategy with specific meal timing and hydration protocols")
    else:
        wellness_exclusions.append("DO NOT include nutrition or fueling advice - user did not select this option")
    
    if strength_training == 'yes':
        wellness_components.append("STRENGTH TRAINING REQUIRED: Include scientifically-proven running-specific strength exercises and periodization")
    else:
        wellness_exclusions.append("DO NOT include strength training exercises - user did not select this option")
        
    if mindfulness_plan == 'yes':
        wellness_components.append("MINDFULNESS INTEGRATION REQUIRED: Include evidence-based mental training, meditation, and psychological preparation techniques")
    else:
        wellness_exclusions.append("DO NOT include mindfulness, meditation, or mental training advice - user did not select this option")
    
    if wellness_components:
        prompt_parts.append("SELECTED PROGRAM COMPONENTS (INCLUDE ONLY THESE):")
        prompt_parts.extend([f"  • {component}" for component in wellness_components])
    
    if wellness_exclusions:
        prompt_parts.append("EXCLUDED COMPONENTS (DO NOT INCLUDE):")
        prompt_parts.extend([f"  • {exclusion}" for exclusion in wellness_exclusions])
    
    # Enhanced Additional Details Processing
    if additional_details:
        prompt_parts.append(f"SPECIAL CONSIDERATIONS & PREFERENCES:")
        prompt_parts.append(f"  {additional_details}")
        
        # Parse specific elements from additional details
        additional_lower = additional_details.lower()
        
        # Dietary restrictions
        dietary_keywords = ['dairy', 'lactose', 'gluten', 'vegan', 'vegetarian', 'allergy', 'intolerant']
        if any(keyword in additional_lower for keyword in dietary_keywords):
            prompt_parts.append("  ⚠️  DIETARY RESTRICTIONS NOTED - Customize nutrition recommendations accordingly")
        
        # Health conditions
        health_keywords = ['injury', 'knee', 'ankle', 'back', 'hip', 'condition', 'therapy', 'recovery', 'pain']
        if any(keyword in additional_lower for keyword in health_keywords):
            prompt_parts.append("  ⚠️  HEALTH CONDITIONS NOTED - Prioritize injury prevention and modify intensity as needed")
    
    # Extract health and dietary information explicitly
    if dietary_restrictions:
        prompt_parts.append(f"CRITICAL DIETARY RESTRICTIONS: {dietary_restrictions}")
        prompt_parts.append("⚠️ NEVER recommend any foods that conflict with these restrictions")

    if health_conditions:
        prompt_parts.append(f"HEALTH CONDITIONS TO CONSIDER: {health_conditions}")

    if mobility_restrictions:
        prompt_parts.append(f"MOBILITY RESTRICTIONS: {mobility_restrictions}")

    # Generation Requirements
    prompt_parts.append("")
    prompt_parts.append("STRICT OUTPUT REQUIREMENTS:")
    
    if plan_display == 'full_plan':
        prompt_parts.append(f"1. Generate COMPLETE {plan_duration_weeks}-week periodized training plan")
        prompt_parts.append("2. Start from Week 1 and progress through all weeks sequentially")
        prompt_parts.append("3. Show clear progression and periodization across all phases:")
        prompt_parts.append(f"   - Base Building (Weeks 1-{int(plan_duration_weeks*0.4)})")
        prompt_parts.append(f"   - Build Phase (Weeks {int(plan_duration_weeks*0.4)+1}-{int(plan_duration_weeks*0.7)})")
        prompt_parts.append(f"   - Peak Phase (Weeks {int(plan_duration_weeks*0.7)+1}-{int(plan_duration_weeks*0.85)})")
        prompt_parts.append(f"   - Taper/Recovery (Weeks {int(plan_duration_weeks*0.85)+1}-{plan_duration_weeks})")
        prompt_parts.append("4. Each week should have specific workouts with measurable goals")
    elif plan_display == 'one_day':
        prompt_parts.append("1. Generate ONLY today's specific workout in detail")
        prompt_parts.append("2. Include warm-up, main workout, and cool-down")
    elif plan_display == 'this_week':
        prompt_parts.append("1. Generate THIS WEEK's complete training plan (7 days)")
        prompt_parts.append("2. Show daily workout breakdown with rest days")
    
    prompt_parts.append("3. **RUNNING WORKOUTS ARE MANDATORY** - Always generate specific running workout details as the primary content")
    prompt_parts.append("4. Generate ONLY what the user selected for additional components (nutrition/strength/mindfulness)")
    prompt_parts.append("5. Base ALL recommendations on established sports science and peer-reviewed research")
    prompt_parts.append("6. Provide specific, measurable, and actionable guidance for running workouts:")
    prompt_parts.append("   - Specific distance or duration")
    prompt_parts.append("   - Target pace or heart rate zone")
    prompt_parts.append("   - Workout structure (warm-up, main set, cool-down)")
    prompt_parts.append("   - Key focus areas for the session")
    prompt_parts.append("7. Include safety protocols and proper progression principles")
    prompt_parts.append("8. NO fictional workouts, unproven methods, or generic advice")
    prompt_parts.append("9. Address the selected plan type and user-specified goals")
    prompt_parts.append("")
    prompt_parts.append("⚠️ CRITICAL: The response MUST start with detailed running workout information before any other components")
    
    return '\n'.join(prompt_parts)