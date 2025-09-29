// mobile-cards.js - Mobile card interface with fixed alignment

let currentCardIndex = 0;
let cardOrder = [];
let hiddenCards = new Set();
let cardData = {};
let startX = 0;
let startY = 0;
let currentX = 0;
let currentY = 0;
let isDragging = false;

function initializeMobileCards() {
    cardData = window.cardData || {};
    
    cardOrder = ['summary'];
    
    if (cardData.profile && cardData.profile.has_profile) {
        cardOrder.push('profile');
    }
    
    if (needsNutritionCard()) {
        cardOrder.push('nutrition');
    }
    
    if (cardData.today && cardData.today.length > 0) {
        cardOrder.push('today', 'today_detail');
    }
    
    if (cardData.tomorrow && cardData.tomorrow.length > 0) {
        cardOrder.push('tomorrow', 'tomorrow_detail');
    }
    
    cardOrder.push('details');
    
    const savedHiddenCards = localStorage.getItem('hiddenCards');
    if (savedHiddenCards) {
        hiddenCards = new Set(JSON.parse(savedHiddenCards));
    }
    
    // CRITICAL FIX: Disable transitions during setup
    const container = document.getElementById('card-container');
    if (container && container.parentElement) {
        container.parentElement.classList.add('no-transition');
    }
    
    generateCards();
    setupEventListeners();
    
    // FIXED: Use proper timing to ensure DOM layout is complete
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            // Set initial positions after DOM is fully rendered
            updateCardDisplay();
            
            // Re-enable transitions after a slight delay
            setTimeout(() => {
                if (container && container.parentElement) {
                    container.parentElement.classList.remove('no-transition');
                }
            }, 100); // Increased delay to ensure stable positioning
        });
    });
}

// Enhanced updateCardDisplay function with better positioning logic
function updateCardDisplay() {
    const visibleCards = getVisibleCardOrder();
    const cards = document.querySelectorAll('.card');
    const sectionBtns = document.querySelectorAll('.section-btn');
    
    // CRITICAL: Force immediate positioning without transitions
    cards.forEach((card, index) => {
        // Remove all position classes first
        card.classList.remove('active', 'prev', 'next');
        
        // Apply inline styles for immediate positioning
        if (index === currentCardIndex) {
            card.classList.add('active');
            card.style.transform = 'translateX(0)';
            card.style.opacity = '1';
            card.style.visibility = 'visible';
            card.style.zIndex = '10';
        } else if (index < currentCardIndex) {
            card.classList.add('prev');
            card.style.transform = 'translateX(-100%)';
            card.style.opacity = '0';
            card.style.visibility = 'hidden';
            card.style.zIndex = '5';
        } else if (index > currentCardIndex) {
            card.classList.add('next');
            card.style.transform = 'translateX(100%)';
            card.style.opacity = '0';
            card.style.visibility = 'hidden';
            card.style.zIndex = '5';
        }
    });

    // Force browser to process the changes
    if (cards.length > 0) {
        cards[0].offsetHeight; // Force reflow
    }

    // Update section buttons
    sectionBtns.forEach((btn) => {
        const section = btn.dataset.section;
        const isHidden = hiddenCards.has(section);
        const visibleIndex = visibleCards.indexOf(section);
        
        btn.classList.toggle('active', visibleIndex === currentCardIndex);
        btn.classList.toggle('hidden', isHidden);
    });

    // Update counters and navigation
    document.getElementById('current-card').textContent = currentCardIndex + 1;
    document.getElementById('total-cards').textContent = visibleCards.length;

    document.getElementById('prev-btn').disabled = currentCardIndex === 0;
    document.getElementById('next-btn').disabled = currentCardIndex === visibleCards.length - 1;
    
    // Clear inline styles after a short delay to let CSS take over
    setTimeout(() => {
        cards.forEach(card => {
            card.style.transform = '';
            card.style.opacity = '';
            card.style.visibility = '';
            card.style.zIndex = '';
        });
    }, 50);
}


function needsNutritionCard() {
    const profile = cardData.profile;
    return profile && profile.has_profile && 
           (profile.nutrition || profile.strength_training || profile.mindfulness);
}

function generateCards() {
    const container = document.getElementById('card-container');
    container.innerHTML = '';
    
    const visibleCards = cardOrder.filter(cardType => !hiddenCards.has(cardType));
    
    visibleCards.forEach((cardType, index) => {
        const cardElement = document.createElement('div');
        cardElement.className = 'card';
        if (index === 0) {
            cardElement.className = 'card active';
        }
        cardElement.dataset.section = cardType;
        cardElement.dataset.index = index;
        
        switch(cardType) {
            case 'summary':
                cardElement.innerHTML = generateEnhancedSummaryCard();
                break;
            case 'profile':
                cardElement.innerHTML = generateEnhancedProfileCard();
                break;
            case 'nutrition':
                cardElement.innerHTML = generateNutritionCard();
                break;
            case 'today':
                cardElement.innerHTML = generateEnhancedTodayCard();
                break;
            case 'today_detail':
                cardElement.innerHTML = generateTodayDetailCard();
                break;
            case 'tomorrow':
                cardElement.innerHTML = generateEnhancedTomorrowCard();
                break;
            case 'tomorrow_detail':
                cardElement.innerHTML = generateTomorrowDetailCard();
                break;
            case 'details':
                cardElement.innerHTML = generateDetailsCard();
                break;
        }
        
        container.appendChild(cardElement);
    });
    
    updateSectionButtons();
    
    setTimeout(() => {
        const currentWeek = cardData.profile?.current_week || 1;
        scrollToWeek(currentWeek);
    }, 100);
}

function generateEnhancedSummaryCard() {
    const summary = cardData.summary || {};
    const daysPlan = cardData.days_plan || {};
    const calories = summary.estimated_calories;
    
    let condensedPlan = '';
    
    // CRITICAL FIX: Parse the LLM-generated content properly
    if (daysPlan.content) {
        const lines = daysPlan.content.split('\n').filter(line => line.trim());
        
        // Extract components from LLM response
        let runLine = '';
        let strengthLine = '';
        let nutritionLine = '';
        let mindfulnessLine = '';
        
        lines.forEach(line => {
            const trimmedLine = line.trim();
            const lowerLine = trimmedLine.toLowerCase();
            
            // Match various formats: "- Run:", "Run:", "• Run:", etc.
            if (lowerLine.match(/^[-•]?\s*run:/i)) {
                runLine = trimmedLine.replace(/^[-•]?\s*run:\s*/i, '').trim();
            } else if (lowerLine.match(/^[-•]?\s*strength:/i)) {
                strengthLine = trimmedLine.replace(/^[-•]?\s*strength:\s*/i, '').trim();
            } else if (lowerLine.match(/^[-•]?\s*nutrition:/i)) {
                nutritionLine = trimmedLine.replace(/^[-•]?\s*nutrition:\s*/i, '').trim();
            } else if (lowerLine.match(/^[-•]?\s*mindfulness:/i)) {
                mindfulnessLine = trimmedLine.replace(/^[-•]?\s*mindfulness:\s*/i, '').trim();
            }
        });
        
        const planComponents = [];
        
        if (runLine) {
            planComponents.push(`<p style="margin: 8px 0; line-height: 1.5; font-size: 13px;"><strong>🏃 Run:</strong> ${runLine}</p>`);
        }
        
        if (strengthLine) {
            planComponents.push(`<p style="margin: 8px 0; line-height: 1.5; font-size: 13px;"><strong>💪 Strength:</strong> ${strengthLine}</p>`);
        }
        
        if (nutritionLine) {
            planComponents.push(`<p style="margin: 8px 0; line-height: 1.5; font-size: 13px;"><strong>🥗 Nutrition:</strong> ${nutritionLine}</p>`);
        }
        
        if (mindfulnessLine) {
            planComponents.push(`<p style="margin: 8px 0; line-height: 1.5; font-size: 13px;"><strong>🧘 Mindfulness:</strong> ${mindfulnessLine}</p>`);
        }
        
        condensedPlan = planComponents.join('');
    }
    
    // If no plan components found, show debugging message
    if (!condensedPlan) {
        condensedPlan = `<p style="font-size: 12px; color: #999;">No plan details available. Debug: ${daysPlan.content ? 'Content exists but not parsed' : 'No content from LLM'}</p>`;
    }
    
    let calorieSection = '';
    if (calories) {
        const envAdjustmentText = calories.environmental_adjustment > 0 ? 
            `<p style="font-size: 10px; margin: 4px 0; color: #C92A2A;">+${calories.environmental_adjustment}% heat/humidity adjustment</p>` : '';
        
        calorieSection = `
            <div class="profile-section" style="background: linear-gradient(135deg, #FFE5E5, #FFD6D6); border: 2px solid #FF6B6B; margin-top: 10px; padding: 12px;">
                <h3 style="font-size: 14px; margin-bottom: 6px; color: #C92A2A;">Target Calories Burn</h3>
                <p style="font-size: 20px; font-weight: bold; color: #C92A2A; margin: 8px 0;">${calories.estimated_calories} cal</p>
                <p style="font-size: 11px; margin: 4px 0;">Intensity: ${calories.intensity_level} (MET: ${calories.met_value})</p>
                ${envAdjustmentText}
                <p style="font-size: 10px; margin: 4px 0; color: #666;">Dewpoint impact: ${calories.dewpoint_impact}</p>
            </div>
        `;
    }
    
    let secondBestSection = '';
    if (summary.second_best_time) {
        secondBestSection = `
            <div class="profile-section" style="background: linear-gradient(135deg, #FFF8E1, #FFECB3); border: 1px solid #FF9800; margin-top: 10px;">
                <h3 style="font-size: 14px; margin-bottom: 6px;">Second Best Weather</h3>
                <p style="font-size: 12px;"><strong>Time:</strong> ${summary.second_best_time.day} ${summary.second_best_time.time}</p>
                <p style="font-size: 12px;"><strong>Score:</strong> ${summary.second_best_time.score}/5.0 - ${getScoreDescription(summary.second_best_time.score)}</p>
                <p style="font-size: 12px;"><strong>Why:</strong> ${summary.second_best_time.reason}</p>
            </div>
        `;
    }
    
    return `
        <h2 style="margin-top: 0; margin-bottom: 12px;">🗓️ Today's Plan Summary</h2>

        <div class="profile-section" style="background: linear-gradient(135deg, #E3F2FD, #BBDEFB); border: 2px solid #2196F3; padding: 20px;">
            <h3 style="font-size: 16px; margin-bottom: 12px; color: #1976D2;">Today's Plan</h3>
            <div style="min-height: 120px;">
                ${condensedPlan || '<p style="font-size: 12px;">No plan details available</p>'}
            </div>
        </div>
        
        ${calorieSection}
        
        <div class="profile-section" style="background: linear-gradient(135deg, #E8F5E9, #C8E6C9); border: 1px solid #4CAF50; border-radius: 8px; padding: 12px; margin: 10px 0;">
            <h3 style="font-size: 14px; margin-top: 0; margin-bottom: 6px; color: #2E7D32;">Best Weather</h3>
            <p style="font-size: 12px;"><strong>Best Time:</strong> ${summary.best_time?.day || 'N/A'} ${summary.best_time?.time || 'N/A'}</p>
            <p style="font-size: 12px;"><strong>Score:</strong> ${summary.best_time?.score || 'N/A'}/5.0 - ${getScoreDescription(summary.best_time?.score)}</p>
            <p style="font-size: 12px;"><strong>Why:</strong> ${summary.best_time?.reason || 'Optimal running conditions'}</p>
        </div>
        ${secondBestSection}
    `;
}

function generateEnhancedProfileCard() {
    const profile = cardData.profile || {};
    
    if (!profile.has_profile) {
        return `
            <h2>📋 Run Plan</h2>
            <div class="profile-section">
                <p>No runner profile information was provided. Fill out the profile section in the main form to see personalized training plans and recommendations.</p>
            </div>
        `;
    }
    
    const today = new Date();
    const currentDayIndex = today.getDay();
    const monday = new Date(today);
    monday.setDate(today.getDate() - currentDayIndex + 1);
    
    const formatDate = (date) => date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    const sunday = new Date(monday);
    sunday.setDate(monday.getDate() + 6);
    
    const weekRange = `${formatDate(monday)} - ${formatDate(sunday)}, ${today.getFullYear()}`;
    
    const todayName = today.toLocaleDateString('en-US', { weekday: 'short' });
    
    let scrollableWeeksHtml = '';
    if (profile.all_weeks_plan && profile.all_weeks_plan.length > 0) {
        const currentWeek = profile.current_week || 1;
        const totalWeeks = profile.total_weeks || profile.all_weeks_plan.length;
        
        scrollableWeeksHtml = `
            <div class="scrollable-weeks-container">
                <div class="week-navigation">
                    <span class="current-week-indicator">Week ${currentWeek} of ${totalWeeks}</span>
                </div>
                <div class="weeks-scroll-container" id="weeks-scroll-container">
                    ${profile.all_weeks_plan.map(weekData => {
                        const weekNum = weekData.week_number;
                        const isCurrent = weekData.is_current;
                        const phase = weekData.phase;
                        
                        const weekPlanHtml = weekData.weekly_plan.map(day => {
                            const dayClass = day.completed ? 'completed' : (isCurrent && day.day === todayName ? 'current' : '');
                            const statusText = day.completed ? '✅' : (isCurrent && day.day === todayName ? '📍 Today' : '');
                            
                            return `
                                <div class="day-plan ${dayClass}">
                                    <span class="day">${day.day}</span>
                                    <span class="workout">${day.workout}</span>
                                    <span class="status">${statusText}</span>
                                </div>
                            `;
                        }).join('');
                        
                        return `
                            <div class="week-plan ${isCurrent ? 'current-week' : ''}" id="week-${weekNum}" data-week="${weekNum}">
                                <h4 class="week-header">⏳ Week ${weekNum} - ${phase}</h4>
                                <div class="weekly-plan">${weekPlanHtml}</div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `;
    }

    return `
        <h2>🥇🏃‍♂️🏃‍♀️🏃 Your Running Plan</h2>
        
        <div class="profile-section" style="background: linear-gradient(135deg, #E3F2FD, #BBDEFB); border: 2px solid #2196F3; margin-bottom: 15px;">
            <h3 style="font-size: 15px; margin-bottom: 10px; color: #1976D2;">🏃 Current Goal</h3>
            <p style="font-size: 13px; margin-bottom: 4px;"><strong>Plan Type:</strong> ${cardData.profile?.plan || 'No plan selected'}</p>
            <p style="font-size: 13px;"><strong>Week:</strong> ${cardData.profile?.week || 'Not specified'}</p>
        </div>
        
        ${scrollableWeeksHtml}
    `;
}

function generateNutritionCard() {
    const profile = cardData.profile || {};
    let cardContent = '<h2>🥑 Nutrition & Fitness</h2>';
    
    // DEBUG: Log what we received
    console.log('=== NUTRITION CARD DEBUG ===');
    console.log('Full profile data:', profile);
    console.log('Has nutrition?', !!profile.nutrition);
    console.log('Has strength_training?', !!profile.strength_training);
    console.log('Has mindfulness?', !!profile.mindfulness);
    
    if (profile.nutrition) {
        console.log('Nutrition type:', typeof profile.nutrition);
        console.log('Nutrition content:', profile.nutrition);
    }
    
    if (profile.strength_training) {
        console.log('Strength type:', typeof profile.strength_training);
        console.log('Strength content:', profile.strength_training);
    }
    
    if (profile.mindfulness) {
        console.log('Mindfulness type:', typeof profile.mindfulness);
        console.log('Mindfulness content:', profile.mindfulness);
    }
    console.log('=== END DEBUG ===');
    
    let hasContent = false;
    
    // Nutrition Section
    if (profile.nutrition) {
        const nutritionData = typeof profile.nutrition === 'object' ? profile.nutrition : null;
        
        if (nutritionData) {
            hasContent = true;
            cardContent += `
                <div class="profile-section" style="background: linear-gradient(135deg, rgba(232, 245, 233, 0.9), rgba(200, 230, 201, 0.8)); padding: 15px; border-radius: 8px; position: relative; border: 2px solid #4CAF50; margin-bottom: 15px;">
                    <div style="position: absolute; top: 8px; right: 12px; font-size: 35px; opacity: 0.8; filter: drop-shadow(2px 2px 4px rgba(76, 175, 80, 0.3)); transform: rotate(-10deg);">🥗</div>
                    <h3>🍎 Nutrition Focus</h3>
                    <p style="font-size: 12px;"><strong>Pre-run:</strong> ${nutritionData.pre_run || 'Not specified'}</p>
                    <p style="font-size: 12px;"><strong>During run:</strong> ${nutritionData.during || 'Not specified'}</p>
                    <p style="font-size: 12px;"><strong>Post-run:</strong> ${nutritionData.post_run || 'Not specified'}</p>
                    ${profile.dietary_restrictions ? `<p style="font-size: 11px; margin-top: 8px; padding: 6px; background: rgba(255,255,255,0.5); border-radius: 4px;"><strong>⚠️ Dietary notes:</strong> ${profile.dietary_restrictions}</p>` : ''}
                </div>
            `;
        } else {
            console.warn('Nutrition exists but is not an object');
        }
    } else {
        console.warn('No nutrition data in profile');
    }
    
    // Strength Training Section
    if (profile.strength_training) {
        const strengthData = typeof profile.strength_training === 'object' ? profile.strength_training : null;
        
        if (strengthData) {
            hasContent = true;
            cardContent += `
                <div class="profile-section" style="background: linear-gradient(135deg, rgba(255, 243, 224, 0.9), rgba(255, 224, 178, 0.8)); padding: 15px; border-radius: 8px; position: relative; border: 2px solid #FF9800; margin-bottom: 15px;">
                    <div style="position: absolute; top: 8px; right: 12px; font-size: 35px; opacity: 0.8; filter: drop-shadow(2px 2px 4px rgba(255, 152, 0, 0.3)); transform: rotate(15deg);">🏋️</div>
                    <h3>💪 Strength Training</h3>
                    <p style="font-size: 12px;"><strong>Schedule:</strong> ${strengthData.schedule || 'Not specified'}</p>
                    <p style="font-size: 12px;"><strong>Focus:</strong> ${strengthData.focus || 'Not specified'}</p>
                    <p style="font-size: 12px;"><strong>Exercises:</strong> ${strengthData.exercises || 'Not specified'}</p>
                    <p style="font-size: 12px;"><strong>Duration:</strong> ${strengthData.duration || 'Not specified'}</p>
                </div>
            `;
        } else {
            console.warn('Strength training exists but is not an object');
        }
    } else {
        console.warn('No strength training data in profile');
    }
    
    // Mindfulness Section
    if (profile.mindfulness) {
        const mindfulnessData = typeof profile.mindfulness === 'object' ? profile.mindfulness : null;
        
        if (mindfulnessData) {
            hasContent = true;
            cardContent += `
                <div class="profile-section" style="background: linear-gradient(135deg, rgba(243, 229, 245, 0.9), rgba(225, 190, 231, 0.8)); padding: 15px; border-radius: 8px; position: relative; border: 2px solid #9C27B0;">
                    <div style="position: absolute; top: 8px; right: 12px; font-size: 35px; opacity: 0.8; filter: drop-shadow(2px 2px 4px rgba(156, 39, 176, 0.3)); animation: pulse 3s ease-in-out infinite;">🧘</div>
                    <h3>🪷 Mindfulness Plan</h3>
                    <p style="font-size: 12px;"><strong>Daily Practice:</strong> ${mindfulnessData.practice || 'Not specified'}</p>
                    <p style="font-size: 12px;"><strong>Focus Areas:</strong> ${mindfulnessData.focus || 'Not specified'}</p>
                    <p style="font-size: 12px;"><strong>Running Integration:</strong> ${mindfulnessData.running || 'Not specified'}</p>
                    <p style="font-size: 12px;"><strong>Recovery:</strong> ${mindfulnessData.recovery || 'Not specified'}</p>
                </div>
            `;
        } else {
            console.warn('Mindfulness exists but is not an object');
        }
    } else {
        console.warn('No mindfulness data in profile');
    }
    
    if (!hasContent) {
        cardContent += `
            <div class="profile-section">
                <p>No wellness components selected.</p>
            </div>
        `;
    }
    
    return cardContent;
}

function generateEnhancedTodayCard() {
    const todayData = cardData.today || [];
    
    if (todayData.length === 0) {
        return `
            <h2>☀️ Today's Forecast</h2>
            <div class="profile-section">
                <p>No forecast data available for today.</p>
            </div>
        `;
    }
    
    const hoursHtml = todayData.map(hour => generateColorCodedHourCard(hour)).join('');
    
    return `
        <h2>☀️ Today's Forecast</h2>
        ${hoursHtml}
    `;
}

function generateEnhancedTomorrowCard() {
    const tomorrowData = cardData.tomorrow || [];
    
    if (tomorrowData.length === 0) {
        return `
            <h2>🌅 Tomorrow's Forecast</h2>
            <div class="profile-section">
                <p>No forecast data available for tomorrow.</p>
            </div>
        `;
    }
    
    const hoursHtml = tomorrowData.map(hour => generateColorCodedHourCard(hour)).join('');
    
    return `
        <h2>🌅 Tomorrow's Forecast</h2>
        ${hoursHtml}
    `;
}

function generateTodayDetailCard() {
    const todayData = cardData.today || [];
    
    if (todayData.length === 0) {
        return `
            <h2>Today's Detailed Forecast</h2>
            <div class="profile-section">
                <p>No forecast data available for today.</p>
            </div>
        `;
    }
    
    const hoursHtml = todayData.map(hour => generateDetailedHourCard(hour)).join('');
    
    return `
        <h2>Today's Detailed Forecast</h2>
        <p style="font-size: 12px; color: #666; margin-bottom: 15px;">Complete recommendations for each hour</p>
        ${hoursHtml}
    `;
}

function generateTomorrowDetailCard() {
    const tomorrowData = cardData.tomorrow || [];
    
    if (tomorrowData.length === 0) {
        return `
            <h2>Tomorrow's Detailed Forecast</h2>
            <div class="profile-section">
                <p>No forecast data available for tomorrow.</p>
            </div>
        `;
    }
    
    const hoursHtml = tomorrowData.map(hour => generateDetailedHourCard(hour)).join('');
    
    return `
        <h2>Tomorrow's Detailed Forecast</h2>
        <p style="font-size: 12px; color: #666; margin-bottom: 15px;">Complete recommendations for each hour</p>
        ${hoursHtml}
    `;
}

function generateDetailedHourCard(hour) {
    const scoreClass = getScoreClass(hour.score);
    const conditionClass = getConditionClass(hour.score);
    const weatherIcon = getAdvancedWeatherIcon(hour.temp, hour.forecast, hour.time, hour.precip);
    
    let statusDisplay = '';
    if (hour.score >= 4.5) {
        statusDisplay = "EXCELLENT";
    } else if (hour.score >= 4.0) {
        statusDisplay = "FAVORABLE";
    } else if (hour.score >= 3.5) {
        statusDisplay = "DECENT";
    } else if (hour.score >= 3.0) {
        statusDisplay = "MODERATE";
    } else if (hour.score >= 2.0) {
        statusDisplay = "STRESSFUL";
    } else {
        statusDisplay = "UNSAFE";
    }
    
    const fullRecommendation = hour.full_recommendation || hour.recommendation;
    
    return `
        <div class="forecast-hour ${conditionClass}" style="margin-bottom: 15px;">
            <div class="hour-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div class="hour-time" style="font-size: 14px; font-weight: bold;">${hour.time}</div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span class="hour-score ${scoreClass}" style="font-size: 13px; padding: 4px 8px;">${hour.score}/5</span>
                    <span style="font-size: 11px; color: ${getScoreColor(hour.score)}; font-weight: bold;">${statusDisplay}</span>
                </div>
            </div>
            <div class="weather-details">
                <div class="weather-item">${weatherIcon} <strong>${hour.temp}F</strong></div>
                <div class="weather-item">${hour.wind}mph</div>
                <div class="weather-item">${hour.humidity}%</div>
                <div class="weather-item">${hour.precip}%</div>
            </div>
            <div style="margin-top: 8px; padding: 6px; background: rgba(33, 150, 243, 0.15); border-left: 3px solid #2196F3; border-radius: 5px; font-size: 12px;">
                <strong>Conditions:</strong> ${hour.forecast || 'N/A'}
            </div>
            <div class="recommendation" style="margin-top: 8px; font-size: 12px; line-height: 1.4;">
                <strong>Full Recommendations:</strong><br>
                ${fullRecommendation}
            </div>
        </div>
    `;
}

function generateColorCodedHourCard(hour) {
    const scoreClass = getScoreClass(hour.score);
    const conditionClass = getConditionClass(hour.score);
    const weatherIcon = getAdvancedWeatherIcon(hour.temp, hour.forecast, hour.time, hour.precip);
    
    let statusDisplay = '';
    if (hour.score >= 4.5) {
        statusDisplay = "⭐ EXCELLENT";
    } else if (hour.score >= 4.0) {
        statusDisplay = "🌟 FAVORABLE";
    } else if (hour.score >= 3.5) {
        statusDisplay = "✨ DECENT";
    } else if (hour.score >= 3.0) {
        statusDisplay = "🧡 MODERATE";
    } else if (hour.score >= 2.0) {
        statusDisplay = "⛔ STRESSFUL";
    } else {
        statusDisplay = "🚫 UNSAFE";
    }
    
    // ENHANCED FILTERING: Remove generic condition messages and "Comfortable temperature" only if there's other content
    let displayRecommendation = hour.recommendation || '';
    
    // Try to split by common separators
    const parts = displayRecommendation.split(/[.!?]|[•·●◦▪▫□■]/);
    
    // If we have multiple parts, filter out generic messages
    if (parts.length > 1) {
        const meaningfulParts = parts
            .map(p => p.trim())
            .filter(p => {
                if (p.length === 0) return false;
                const lower = p.toLowerCase();
                // Filter out these generic messages
                return !(
                    lower.includes('comfortable temperature') ||
                    lower.includes('good to excellent conditions') ||
                    lower.includes('excellent conditions') ||
                    lower.includes('good conditions') ||
                    lower.includes('fair conditions') ||
                    lower.includes('perfect conditions') ||
                    lower.includes('ideal conditions')
                );
            });
        
        // Use the first meaningful part if found, otherwise keep original
        if (meaningfulParts.length > 0) {
            displayRecommendation = meaningfulParts[0];
        }
    }
    // If it's the ONLY content, keep it as-is
    
    // Final cleanup
    displayRecommendation = displayRecommendation
        .replace(/^[-•·●◦▪▫□■]\s*/, '')
        .replace(/^\d+\.\s*/, '')
        .replace(/^[,;]\s*/, '')
        .trim();

    return `
        <div class="forecast-hour ${conditionClass}">
            <div class="hour-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div class="hour-time" style="font-size: 14px; font-weight: bold;">${hour.time}</div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span class="hour-score ${scoreClass}" style="font-size: 13px; padding: 4px 8px;">${hour.score}/5</span>
                    <span style="font-size: 11px; color: ${getScoreColor(hour.score)}; font-weight: bold;">${statusDisplay}</span>
                </div>
            </div>
            <div class="weather-details">
                <div class="weather-item">${weatherIcon} <strong>${hour.temp}°F</strong></div>
                <div class="weather-item">💨 ${hour.wind}mph</div>
                <div class="weather-item">💧 ${hour.humidity}%</div>
                <div class="weather-item">🌧️ ${hour.precip}%</div>
            </div>
            <div style="margin-top: 8px; padding: 6px; background: rgba(33, 150, 243, 0.15); border-left: 3px solid #2196F3; border-radius: 5px; font-size: 12px;">
                <strong> Conditions:</strong> ${hour.forecast || 'N/A'}
            </div>
            <div class="recommendation" style="margin-top: 8px;">
                💡 ${displayRecommendation}
            </div>
        </div>
    `;
}

function generateDetailsCard() {
    const details = cardData.details || {};
    
    return `
        <h2>🔍 Technical Details</h2>
        <div class="profile-section">
            <h3>🌡️ Heat Stress Analysis</h3>
            <p><strong>Peak Heat Index:</strong> ${details.heat_stress?.peak_heat_index || 'N/A'}</p>
            <p><strong>Dewpoint Range:</strong> ${details.heat_stress?.dewpoint_range || 'N/A'}</p>
            <p><strong>UV Index:</strong> ${details.heat_stress?.uv_index || 'N/A'}</p>
        </div>
        
        <div class="profile-section">
            <h3>💨 Wind Patterns</h3>
            <p><strong>Morning:</strong> ${details.wind_patterns?.morning || 'N/A'}</p>
            <p><strong>Afternoon:</strong> ${details.wind_patterns?.afternoon || 'N/A'}</p>
            <p><strong>Direction:</strong> ${details.wind_patterns?.direction || 'N/A'}</p>
        </div>

        <div class="profile-section">
            <h3>🌧️ Precipitation</h3>
            <p><strong>Today:</strong> ${details.precipitation?.today || 'N/A'}</p>
            <p><strong>Tomorrow:</strong> ${details.precipitation?.tomorrow || 'N/A'}</p>
            <p><strong>Type:</strong> ${details.precipitation?.type || 'N/A'}</p>
        </div>

        <div class="profile-section">
            <h3>🫁 Air Quality</h3>
            <p><strong>AQI:</strong> ${details.air_quality?.aqi || 'N/A'} (${details.air_quality?.category || 'Unknown'})</p>
            <p><strong>Restrictions:</strong> ${details.air_quality?.restrictions || 'No information available'}</p>
        </div>
    `;
}

function getAdvancedWeatherIcon(temp, forecast, time, precip) {
    const hour = parseInt(time.split(':')[0]);
    const isNight = hour < 6 || hour > 19;
    const forecastLower = (forecast || '').toLowerCase();
    
    if (precip > 50) return '🌧️';
    if (precip > 20) return '🌦️';
    
    if (forecastLower.includes('thunder') || forecastLower.includes('storm')) return '⛈️';
    if (forecastLower.includes('rain')) return '🌧️';
    if (forecastLower.includes('snow')) return '🌨️';
    if (forecastLower.includes('fog')) return '🌫️';
    
    if (forecastLower.includes('overcast') || forecastLower.includes('cloudy')) return '☁️';
    if (forecastLower.includes('partly') && forecastLower.includes('cloud')) return '⛅';
    
    if (isNight) {
        if (forecastLower.includes('clear')) return '🌙';
        return '🌃';
    } else if (hour < 8) {
        return '🌅';
    } else if (hour > 17) {
        return '🌇';
    }
    
    if (temp >= 85) return '🌡️';
    if (forecastLower.includes('sunny') || forecastLower.includes('clear')) return '☀️';
    
    return '🌤️';
}

function getScoreColor(score) {
    if (score >= 4.5) return '#2E7D32';
    if (score >= 4.0) return '#4CAF50';
    if (score >= 3.5) return '#8BC34A';
    if (score >= 3.0) return '#FF9800';
    if (score >= 2.0) return '#FF5722';
    return '#F44336';
}

function getScoreDescription(score) {
    if (score >= 4.5) return 'perfect';
    if (score >= 4.0) return 'great';
    if (score >= 3.5) return 'good';
    if (score >= 3.0) return 'manageable';
    if (score >= 2.0) return 'poor';
    return 'avoid';
}

function getConditionClass(score) {
    if (score >= 4.5) return 'perfect-conditions';
    if (score >= 4.0) return 'great-conditions';
    if (score >= 3.5) return 'good-conditions';
    if (score >= 3.0) return 'manageable-conditions';
    if (score >= 2.0) return 'poor-conditions';
    return 'avoid-outdoors';
}

function getScoreClass(score) {
    if (score >= 4.5) return 'perfect';
    if (score >= 4.0) return 'great';
    if (score >= 3.5) return 'good';
    if (score >= 3.0) return 'manageable';
    if (score >= 2.0) return 'poor';
    return 'avoid';
}

function updateSectionButtons() {
    const sectionSelector = document.querySelector('.section-selector');
    sectionSelector.innerHTML = '';
    
    const buttonIcons = {
        summary: '📊',
        profile: '🎯',
        nutrition: '🥑',
        today: '☀️',
        today_detail: '📅',
        tomorrow: '🌅',
        tomorrow_detail: '🌄',
        details: '🔍'
    };
    
    cardOrder.forEach((section) => {
        const button = document.createElement('button');
        const isHidden = hiddenCards.has(section);
        const visibleCards = getVisibleCardOrder();
        const visibleIndex = visibleCards.indexOf(section);
        
        button.className = `section-btn ${visibleIndex === currentCardIndex ? 'active' : ''} ${isHidden ? 'hidden' : ''}`;
        button.dataset.section = section;
        button.textContent = buttonIcons[section] || '📄';
        button.title = getButtonTitle(section);
        
        if (!isHidden) {
            button.addEventListener('click', () => goToCard(visibleIndex));
        }
        
        sectionSelector.appendChild(button);
    });
}

function getButtonTitle(section) {
    const titles = {
        summary: 'Summary',
        profile: 'Run Plan',
        nutrition: 'Nutrition & Fitness',
        today: 'Today',
        today_detail: 'Today Detail',
        tomorrow: 'Tomorrow',
        tomorrow_detail: 'Tomorrow Detail',
        details: 'Details'
    };
    return titles[section] || section;
}

function getVisibleCardOrder() {
    return cardOrder.filter(cardType => !hiddenCards.has(cardType));
}

function updateCardDisplay() {
    const visibleCards = getVisibleCardOrder();
    const cards = document.querySelectorAll('.card');
    const sectionBtns = document.querySelectorAll('.section-btn');
    
    cards.forEach((card, index) => {
        card.classList.remove('active', 'prev', 'next');
        
        if (index === currentCardIndex) {
            card.classList.add('active');
        } else if (index < currentCardIndex) {
            card.classList.add('prev');
        } else if (index > currentCardIndex) {
            card.classList.add('next');
        }
    });

    sectionBtns.forEach((btn) => {
        const section = btn.dataset.section;
        const isHidden = hiddenCards.has(section);
        const visibleIndex = visibleCards.indexOf(section);
        
        btn.classList.toggle('active', visibleIndex === currentCardIndex);
        btn.classList.toggle('hidden', isHidden);
    });

    document.getElementById('current-card').textContent = currentCardIndex + 1;
    document.getElementById('total-cards').textContent = visibleCards.length;

    document.getElementById('prev-btn').disabled = currentCardIndex === 0;
    document.getElementById('next-btn').disabled = currentCardIndex === visibleCards.length - 1;
}

function nextCard() {
    const visibleCards = getVisibleCardOrder();
    if (currentCardIndex < visibleCards.length - 1) {
        currentCardIndex++;
        updateCardDisplay();
    }
}

function previousCard() {
    if (currentCardIndex > 0) {
        currentCardIndex--;
        updateCardDisplay();
    }
}

function goToCard(index) {
    const visibleCards = getVisibleCardOrder();
    if (index >= 0 && index < visibleCards.length) {
        currentCardIndex = index;
        updateCardDisplay();
    }
}

function toggleCardVisibility() {
    const currentSection = getVisibleCardOrder()[currentCardIndex];
    if (hiddenCards.has(currentSection)) {
        hiddenCards.delete(currentSection);
    } else {
        hiddenCards.add(currentSection);
    }
    
    localStorage.setItem('hiddenCards', JSON.stringify([...hiddenCards]));
    generateCards();
    
    const visibleCards = getVisibleCardOrder();
    if (currentCardIndex >= visibleCards.length) {
        currentCardIndex = Math.max(0, visibleCards.length - 1);
    }
    
    updateCardDisplay();
}

function openReorderModal() {
    const modal = document.getElementById('reorder-modal');
    if (modal) {
        modal.style.display = 'block';
        populateReorderList();
    }
}

function populateReorderList() {
    const list = document.getElementById('reorder-list');
    if (!list) return;
    
    const buttonLabels = {
        summary: '📊 Summary',
        profile: '🎯 Run Plan',
        nutrition: '🥑 Nutrition & Fitness',
        today: '☀️ Today',
        today_detail: '📅 Today Detail',
        tomorrow: '🌅 Tomorrow',
        tomorrow_detail: '🌄 Tomorrow Detail',
        details: '🔍 Details'
    };
    
    list.innerHTML = '';
    cardOrder.forEach(section => {
        const item = document.createElement('div');
        const isHidden = hiddenCards.has(section);
        
        item.className = `reorder-item ${isHidden ? 'hidden-item' : ''}`;
        item.dataset.section = section;
        item.draggable = true;
        item.innerHTML = `
            <span class="drag-handle">⋮⋮</span>
            <span>${buttonLabels[section]}</span>
            <button onclick="toggleCardInModal('${section}')" style="margin-left: auto; padding: 2px 6px; font-size: 12px; border: none; border-radius: 4px; background: ${isHidden ? '#4CAF50' : '#F44336'}; color: white;">
                ${isHidden ? 'Show' : 'Hide'}
            </button>
        `;
        list.appendChild(item);
    });
    
    enableDragAndDrop();
}

function toggleCardInModal(section) {
    if (hiddenCards.has(section)) {
        hiddenCards.delete(section);
    } else {
        hiddenCards.add(section);
    }
    populateReorderList();
}

function applyReorder() {
    const items = Array.from(document.querySelectorAll('.reorder-item'));
    const newOrder = items.map(item => item.dataset.section);
    
    cardOrder = newOrder;
    
    localStorage.setItem('hiddenCards', JSON.stringify([...hiddenCards]));
    localStorage.setItem('cardOrder', JSON.stringify(cardOrder));
    
    generateCards();
    currentCardIndex = 0;
    updateCardDisplay();
    closeReorderModal();
}

function closeReorderModal() {
    const modal = document.getElementById('reorder-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

function enableDragAndDrop() {
    let draggedElement = null;
    const items = document.querySelectorAll('.reorder-item');
    
    items.forEach(item => {
        item.addEventListener('dragstart', (e) => {
            draggedElement = item;
            item.style.opacity = '0.5';
        });
        
        item.addEventListener('dragend', () => {
            item.style.opacity = '1';
            draggedElement = null;
        });
        
        item.addEventListener('dragover', (e) => {
            e.preventDefault();
        });
        
        item.addEventListener('drop', (e) => {
            e.preventDefault();
            if (draggedElement && draggedElement !== item) {
                const parent = item.parentNode;
                const itemRect = item.getBoundingClientRect();
                const midpoint = itemRect.top + itemRect.height / 2;
                
                if (e.clientY < midpoint) {
                    parent.insertBefore(draggedElement, item);
                } else {
                    parent.insertBefore(draggedElement, item.nextSibling);
                }
            }
        });
    });
}

function setupEventListeners() {
    const cardContainer = document.querySelector('.card-container');
    
    cardContainer.addEventListener('touchstart', handleTouchStart, { passive: false });
    cardContainer.addEventListener('touchmove', handleTouchMove, { passive: false });
    cardContainer.addEventListener('touchend', handleTouchEnd);
    
    document.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowLeft') previousCard();
        if (e.key === 'ArrowRight') nextCard();
    });
    
    document.getElementById('prev-btn').addEventListener('click', previousCard);
    document.getElementById('next-btn').addEventListener('click', nextCard);
}

function handleTouchStart(e) {
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
    isDragging = false;
}

function handleTouchMove(e) {
    if (!startX || !startY) return;
    
    currentX = e.touches[0].clientX;
    currentY = e.touches[0].clientY;
    
    const diffX = Math.abs(currentX - startX);
    const diffY = Math.abs(currentY - startY);
    
    if (diffX > diffY && diffX > 10) {
        isDragging = true;
        e.preventDefault();
    }
}

function handleTouchEnd() {
    if (!isDragging || !startX) return;
    
    const diffX = currentX - startX;
    const threshold = 50;
    
    if (Math.abs(diffX) > threshold) {
        if (diffX > 0) {
            previousCard();
        } else {
            nextCard();
        }
    }
    
    startX = 0;
    startY = 0;
    currentX = 0;
    currentY = 0;
    isDragging = false;
}

function scrollToWeek(weekNumber) {
    const weekElement = document.getElementById(`week-${weekNumber}`);
    if (weekElement) {
        weekElement.scrollIntoView({ 
            behavior: 'smooth', 
            block: 'center' 
        });
    }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeMobileCards);
} else {
    initializeMobileCards();
}

// Hide touch indicator after 3 seconds
setTimeout(() => {
    const indicator = document.querySelector('.touch-indicator');
    if (indicator) {
        indicator.style.display = 'none';
    }
}, 3000);

// Card initialization function
(() => {
  function initCards() {
    const container = document.querySelector('.card-container');
    if (!container) return;

    // keep transitions off while we set initial positions
    container.classList.add('no-transition');

    const tryInit = () => {
      const cards = Array.from(container.querySelectorAll('.card'));
      if (cards.length === 0) return false; // not ready yet

      // pick the card that should be active (existing .active or first)
      let active = cards.find(c => c.classList.contains('active'));
      if (!active) {
        active = cards[0];
        cards.forEach(c => c.classList.remove('active', 'prev'));
        active.classList.add('active');
      }

      // set inline positions so browser has concrete layout (no transitions)
      cards.forEach(c => {
        if (c === active) {
          c.style.transform = 'translateX(0)';
          c.style.opacity = '1';
          c.style.pointerEvents = 'auto';
        } else {
          c.style.transform = 'translateX(100%)';
          c.style.opacity = '0';
          c.style.pointerEvents = 'none';
        }
      });

      // force layout/read so the browser paints these styles
      container.getBoundingClientRect();

      // Wait two frames to ensure paint completed, then re-enable transitions
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          container.classList.remove('no-transition');

          // remove the inline styles shortly after so CSS classes control animations
          setTimeout(() => {
            cards.forEach(c => {
              c.style.transform = '';
              c.style.opacity = '';
              c.style.pointerEvents = '';
            });
          }, 40);
        });
      });

      return true;
    };

    // Try immediately, otherwise observe DOM changes and retry
    if (!tryInit()) {
      const mo = new MutationObserver((mutations, obs) => {
        if (tryInit()) obs.disconnect();
      });
      mo.observe(container, { childList: true, subtree: true });

      // fallback attempt after 2s (so we don't keep observing forever)
      setTimeout(() => { tryInit(); mo.disconnect(); }, 2000);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCards);
  } else {
    initCards();
  }
})();