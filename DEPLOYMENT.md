# 🚀 Free Hosting Guide for Health Tracker

## Best Free Hosting Options

### 1. **Render.com (RECOMMENDED) ✅**
- **Free Tier**: 750 hours/month
- **Database**: PostgreSQL included free
- **Auto-deploy**: From GitHub
- **Custom Domain**: Supported
- **Sleep**: After 15 min inactivity (wakes on request)

### 2. **PythonAnywhere**
- **Free Tier**: 1 web app
- **Database**: MySQL included
- **Storage**: 512 MB
- **Bandwidth**: Limited
- **Domain**: yourusername.pythonanywhere.com

### 3. **Railway.app**
- **Free Tier**: $5 credit/month
- **Database**: PostgreSQL included
- **Easy Deploy**: From GitHub
- **Note**: May require credit card

### 4. **Vercel**
- **Free Tier**: Unlimited
- **Best for**: Static sites
- **Limitation**: Serverless functions only

### 5. **Google Cloud Run**
- **Free Tier**: 2 million requests/month
- **Database**: Need separate service
- **More Complex**: Requires Docker

---

## 📦 Step-by-Step Deployment to Render.com (Easiest)

### Prerequisites
1. GitHub account
2. Your code pushed to GitHub repository

### Step 1: Prepare Your Code

1. **Create `render.yaml`** in project root:
```yaml
services:
  - type: web
    name: health-tracker
    env: python
    buildCommand: "pip install -r requirements.txt"
    startCommand: "gunicorn app:app"
    envVars:
      - key: GEMINI_API_KEY
        sync: false
      - key: SECRET_KEY
        generateValue: true
    autoDeploy: true
```

2. **Update `requirements.txt`**:
```txt
Flask==3.0.0
Werkzeug==3.0.1
python-dotenv==1.0.0
requests==2.31.0
gunicorn==21.2.0
psycopg2-binary==2.9.9
```

3. **Create `render_app.py`** (for PostgreSQL support):
```python
import os
from app import app, init_db

# Use PostgreSQL in production
if os.environ.get('DATABASE_URL'):
    import psycopg2
    from urllib.parse import urlparse
    
    # Parse database URL
    result = urlparse(os.environ.get('DATABASE_URL'))
    username = result.username
    password = result.password
    database = result.path[1:]
    hostname = result.hostname
    port = result.port
    
    # Update database configuration
    app.config['DATABASE'] = {
        'host': hostname,
        'database': database,
        'user': username,
        'password': password,
        'port': port
    }

if __name__ == '__main__':
    init_db()
    app.run()
```

### Step 2: Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/health-tracker.git
git push -u origin main
```

### Step 3: Deploy to Render

1. Go to [render.com](https://render.com)
2. Sign up/Login with GitHub
3. Click "New +" → "Web Service"
4. Connect your GitHub repository
5. Configure:
   - **Name**: health-tracker
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
6. Add Environment Variables:
   - `GEMINI_API_KEY`: Your API key
   - `SECRET_KEY`: (auto-generated)
7. Click "Create Web Service"

### Step 4: Set Up Database

1. In Render Dashboard → "New +" → "PostgreSQL"
2. Create free PostgreSQL database
3. Copy the Internal Database URL
4. Add to your web service environment variables:
   - Key: `DATABASE_URL`
   - Value: (paste the URL)

---

## 🐍 Deployment to PythonAnywhere

### Step 1: Sign Up
1. Go to [pythonanywhere.com](https://www.pythonanywhere.com)
2. Create free account

### Step 2: Upload Code
1. Go to "Files" tab
2. Create directory: `mysite`
3. Upload all files

### Step 3: Set Up Web App
1. Go to "Web" tab
2. Click "Add a new web app"
3. Choose Flask
4. Python version: 3.9
5. Path: `/home/USERNAME/mysite/app.py`

### Step 4: Configure
1. Edit WSGI configuration file:
```python
import sys
path = '/home/USERNAME/mysite'
if path not in sys.path:
    sys.path.append(path)

from app import app as application
```

2. Set environment variables in `.env` file

### Step 5: Database
1. Go to "Databases" tab
2. Create MySQL database
3. Update app.py to use MySQL

---

## 🚂 Deployment to Railway

### Step 1: Setup
1. Go to [railway.app](https://railway.app)
2. Login with GitHub

### Step 2: Deploy
1. Click "New Project"
2. Select "Deploy from GitHub repo"
3. Choose your repository
4. Add PostgreSQL database
5. Add environment variables

### Step 3: Configure
Railway auto-detects Python and installs requirements.txt

---

## 🔧 Important Modifications for Production

### 1. Database Migration (SQLite → PostgreSQL)

Create `database_pg.py`:
```python
import os
import psycopg2
from psycopg2.extras import RealDictCursor

def get_db():
    conn = psycopg2.connect(
        os.environ.get('DATABASE_URL'),
        cursor_factory=RealDictCursor
    )
    return conn
```

### 2. Update app.py for Production

Add at the top:
```python
import os

# Check if running in production
IS_PRODUCTION = os.environ.get('DATABASE_URL') is not None

if IS_PRODUCTION:
    # Use PostgreSQL
    from database_pg import get_db
else:
    # Use SQLite locally
    # (existing get_db function)
```

### 3. Static Files Configuration

For production, add:
```python
from whitenoise import WhiteNoise
app.wsgi_app = WhiteNoise(app.wsgi_app, root='static/')
```

Add to requirements.txt:
```
whitenoise==6.5.0
```

---

## 🌐 Custom Domain Setup

### For Render.com:
1. Dashboard → Settings → Custom Domains
2. Add your domain
3. Update DNS records

### For PythonAnywhere:
1. Web tab → Add custom domain (paid feature)

---

## 📊 Free Tier Limitations

| Platform | Limitations | Best For |
|----------|------------|----------|
| **Render** | Sleeps after 15 min | Personal use |
| **PythonAnywhere** | 512MB storage, limited CPU | Light usage |
| **Railway** | $5 credit/month | Testing |
| **Vercel** | Serverless only | Static sites |
| **Heroku** | No longer free | - |

---

## 🚀 Quick Deploy Scripts

### deploy.sh (for Render)
```bash
#!/bin/bash
echo "Deploying to Render..."
git add .
git commit -m "Deploy update"
git push origin main
echo "Deployment triggered! Check Render dashboard."
```

### Local Testing with Production Database
```bash
# Set environment variable
export DATABASE_URL="postgresql://user:pass@host/db"
python app.py
```

---

## 🔒 Security Checklist

Before deploying:
- [ ] Set strong SECRET_KEY
- [ ] Remove debug mode: `app.run(debug=False)`
- [ ] Use environment variables for all secrets
- [ ] Enable HTTPS (automatic on most platforms)
- [ ] Set secure session cookies
- [ ] Validate all user inputs

---

## 📱 Monitoring Your App

### Free Monitoring Tools:
1. **UptimeRobot**: Monitor uptime
2. **Render Dashboard**: Built-in metrics
3. **LogDNA**: Free tier for logs

---

## 🆘 Troubleshooting

### App Won't Start
- Check logs in platform dashboard
- Verify all dependencies in requirements.txt
- Check environment variables

### Database Errors
- Ensure DATABASE_URL is set
- Check database connection limits
- Verify table creation

### Slow Performance
- Upgrade to paid tier
- Optimize database queries
- Use caching

---

## 💡 Pro Tips

1. **Use GitHub Actions** for auto-deploy
2. **Set up staging environment** for testing
3. **Regular backups** of database
4. **Monitor API usage** to stay in limits
5. **Use CDN** for static files

---

## 📚 Resources

- [Render Docs](https://render.com/docs)
- [PythonAnywhere Help](https://help.pythonanywhere.com)
- [Railway Docs](https://docs.railway.app)
- [Flask Deployment](https://flask.palletsprojects.com/deploying/)

---

**Choose Render.com for the easiest, most reliable free hosting!**
