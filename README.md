# 🏃‍♂️ Personal Health Tracker

A comprehensive health and nutrition tracking application with AI-powered meal analysis, exercise tracking, and body vitals monitoring.

## Features

### 🍽️ Smart Meal Tracking
- **AI Photo Analysis**: Take a photo of your meal and get instant nutrition information
- **4 Meal Categories**: Breakfast, Lunch, Snacks, Dinner
- **Manual Entry**: Add meals with custom nutrition values
- **Automatic Nutrition Calculation**: Powered by Gemini AI and nutrition databases

### 💪 Exercise & Activity Tracking
- Log workouts with duration and calories burned
- Add notes to track workout details
- View daily activity summaries

### 📊 Body Vitals Monitoring
- Track weight, BMI, body fat percentage
- Monitor muscle mass, bone mass, body water
- Record BMR and metabolic age
- View historical trends

### 📈 Data Visualization
- Daily calorie summary cards (Consumed, Burned, Net, Remaining)
- Macronutrient breakdown charts (Protein, Fat, Carbs)
- Weekly progress tracking
- Calendar view for monthly overview

### 👤 User Management
- Secure authentication with password hashing
- Persistent sessions (7-day remember me)
- Personal profile with customizable calorie targets
- Multi-user support

## Installation

### Prerequisites
- Python 3.8+
- Google Gemini API key (for AI meal analysis)

### Setup

1. **Clone the repository**
```bash
git clone <repository-url>
cd health
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Set up environment variables**
Create a `.env` file in the project root:
```env
GEMINI_API_KEY=your_gemini_api_key_here
SECRET_KEY=your_secret_key_here
```

To get a Gemini API key:
- Visit https://makersuite.google.com/app/apikey
- Create a new API key
- Copy and paste it into your `.env` file

4. **Initialize the database**
```bash
python -c "from app import init_db; init_db()"
```

5. **Run the application**
```bash
python app.py
```

6. **Access the app**
Open your browser and navigate to:
```
http://localhost:5001
```

## Usage

### Getting Started

1. **Create an Account**
   - Click "Sign Up" on the login page
   - Enter username (min 3 characters)
   - Create password (min 6 characters)
   - Optional: Add email and full name

2. **Set Your Profile**
   - Click "Edit Profile" in the dashboard
   - Set your daily calorie target
   - Add age and height for BMI calculations

3. **Track Meals**
   - Click "+ Add" for any meal category
   - **Photo Method**: Upload a photo for AI analysis
   - **Manual Method**: Enter food items and nutrition manually

4. **Log Exercise**
   - Click "+ Add Activity"
   - Enter activity name, duration, and calories burned
   - Add optional notes

5. **Record Body Vitals**
   - Click "+ Add Vitals"
   - Enter weight and body composition metrics
   - Track changes over time

### Navigation
- Use "← Previous" and "Next →" to view different dates
- Click "Today" to return to current date
- All data updates in real-time

## Security Features

- **Password Hashing**: Bcrypt encryption for all passwords
- **Session Security**: HTTPOnly cookies with SameSite protection
- **Input Validation**: Comprehensive validation for all user inputs
- **SQL Injection Protection**: Parameterized queries throughout
- **XSS Protection**: Proper output escaping in templates

## Data Validation

### User Registration
- Username: 3+ characters, alphanumeric + underscores
- Password: 6+ characters minimum
- Email: Valid format (optional)

### Nutrition Limits
- Calories per meal: Max 5000
- Calories burned per activity: Max 2000
- Daily target: 500-10000 calories

### Profile Settings
- Age: 1-150 years
- Height: 50-300 cm
- Target calories: 500-10000

## Database Schema

The application uses SQLite with the following tables:
- `users`: User accounts and settings
- `meals`: Food entries with nutrition data
- `activities`: Exercise and calorie burn tracking
- `vitals`: Body measurements and composition
- `daily_summary`: Aggregated daily statistics

## API Endpoints

### Authentication
- `POST /api/signup` - Create new account
- `POST /api/login` - User login
- `POST /api/logout` - User logout

### User Profile
- `GET /api/user/profile` - Get profile info
- `PUT /api/user/profile` - Update profile

### Meals
- `GET /api/meal?date=YYYY-MM-DD` - Get meals for date
- `POST /api/meal` - Add new meal (photo or manual)

### Activities
- `GET /api/activity?date=YYYY-MM-DD` - Get activities
- `POST /api/activity` - Add new activity
- `DELETE /api/activity?id=X` - Delete activity

### Vitals
- `GET /api/vitals` - Get vitals history
- `POST /api/vitals` - Add vitals entry

### Summary
- `GET /api/daily-summary/YYYY-MM-DD` - Get daily totals
- `GET /api/calendar/YYYY/MM` - Get monthly overview

## Troubleshooting

### Common Issues

1. **"GEMINI_API_KEY not set" warning**
   - Ensure `.env` file exists with valid API key
   - Restart the application after adding the key

2. **Port already in use**
   - Change port in `app.py` last line: `app.run(port=5002)`

3. **Database errors**
   - Delete `database.db` and reinitialize:
   ```bash
   rm database.db
   python -c "from app import init_db; init_db()"
   ```

4. **Photo analysis not working**
   - Check Gemini API key is valid
   - Ensure image is JPG/PNG format
   - Check internet connection

## Production Deployment

For production deployment:

1. **Disable Debug Mode**
   ```python
   app.run(debug=False, host='0.0.0.0', port=5001)
   ```

2. **Use Production WSGI Server**
   ```bash
   pip install gunicorn
   gunicorn -w 4 -b 0.0.0.0:5001 app:app
   ```

3. **Set Strong Secret Key**
   Generate a secure secret key:
   ```python
   import secrets
   print(secrets.token_hex(32))
   ```

4. **Use PostgreSQL/MySQL**
   For production, migrate from SQLite to a production database

5. **Enable HTTPS**
   Use a reverse proxy (nginx) with SSL certificates

## License

This project is for personal use. Feel free to modify and adapt for your needs.

## Support

For issues or questions, please check the troubleshooting section or create an issue in the repository.

---

Built with ❤️ for personal health tracking
