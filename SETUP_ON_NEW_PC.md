# Setting Up Archive Demo Project on a New Windows PC

This guide provides step-by-step instructions for setting up the Archive Demo project on a new Windows development machine.

## Required Software

### 1. Python
- **Version**: Python 3.10 or higher (3.11+ recommended)
- **Download**: https://www.python.org/downloads/windows/
- **Important**: Check "Add Python to PATH" during installation
- **Verify**: Open PowerShell and run `python --version`

### 2. Node.js
- **Version**: Node.js 18.x LTS or higher (20.x LTS recommended)
- **Download**: https://nodejs.org/en/download/
- **Verify**: Run `node --version` and `npm --version`

### 3. PostgreSQL (Recommended) or SQLite (Fallback)

#### Option A: PostgreSQL (Production-like)
- **Version**: PostgreSQL 14 or higher
- **Download**: https://www.postgresql.org/download/windows/
- **During Setup**:
  - Remember the password you set for the `postgres` user
  - Keep the default port (5432)
  - Install pgAdmin4 (optional but helpful)

#### Option B: SQLite (Quick Start)
- No installation required (included with Python)
- Used automatically when `USE_SQLITE_FALLBACK=1` in `.env`

### 4. Git (Optional but Recommended)
- **Download**: https://git-scm.com/download/win
- For cloning the repository

---

## Project Setup Steps

### Step 1: Clone or Copy the Project

```powershell
# If using Git
git clone <repository-url> archive-demo
cd archive-demo

# Or if copying from USB/zip
cd archive-demo
```

### Step 2: Backend Setup

#### 2.1 Create Python Virtual Environment
```powershell
cd backend
python -m venv venv
```

#### 2.2 Activate Virtual Environment
```powershell
# In PowerShell
.\venv\Scripts\Activate.ps1

# If you get execution policy error, run this first:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

#### 2.3 Install Python Dependencies
```powershell
pip install -r requirements.txt
```

**Expected packages installed:**
- Django 5.x
- Django REST Framework 3.17+
- djangorestframework-simplejwt 5.5+
- django-cors-headers 4.9+
- psycopg (PostgreSQL adapter)
- python-dotenv

#### 2.4 Configure Environment Variables

Copy the example environment file:
```powershell
copy .env.example .env
```

Edit `.env` with your settings:

**For PostgreSQL (recommended):**
```env
DEBUG=1
SECRET_KEY=django-insecure-archive-demo-2026-long-random-secret-key-123456789
ALLOWED_HOSTS=*
CORS_ALLOW_ALL_ORIGINS=1

USE_SQLITE_FALLBACK=0

POSTGRES_DB=archive_demo
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_postgres_password_here
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

**For SQLite (quick start):**
```env
DEBUG=1
SECRET_KEY=django-insecure-archive-demo-2026-long-random-secret-key-123456789
ALLOWED_HOSTS=*
CORS_ALLOW_ALL_ORIGINS=1

USE_SQLITE_FALLBACK=1
# PostgreSQL settings ignored when using SQLite
```

#### 2.5 Create Database (PostgreSQL only)

Open pgAdmin or psql and create the database:
```sql
CREATE DATABASE archive_demo;
```

#### 2.6 Run Migrations
```powershell
python manage.py migrate
```

**Expected output**: Should show multiple migrations being applied (core, auth, token_blacklist, etc.)

#### 2.7 Create Superuser (Optional)
```powershell
python manage.py createsuperuser
```

Follow prompts to create an admin account.

#### 2.8 Test Backend
```powershell
python manage.py runserver
```

The backend should start at: http://127.0.0.1:8000/

Test the API is working:
```powershell
# In another terminal
curl http://127.0.0.1:8000/api/auth/me/
# Should return 401 (unauthorized) - this is expected
```

### Step 3: Frontend Setup

#### 3.1 Navigate to Frontend Directory
```powershell
cd ..\frontend
```

#### 3.2 Install Node Dependencies
```powershell
npm install
```

**Expected packages:**
- React 19.x
- React Router DOM 7.x
- Axios 1.x
- Vite 8.x (dev server)

#### 3.3 Configure Frontend Environment
```powershell
copy .env.example .env
```

Edit `.env`:
```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

#### 3.4 Start Frontend Dev Server
```powershell
npm run dev
```

The frontend should start at: http://localhost:5173/

---

## Running the Full Application

### Terminal 1: Backend
```powershell
cd backend
.\venv\Scripts\Activate.ps1
python manage.py runserver
```

### Terminal 2: Frontend
```powershell
cd frontend
npm run dev
```

### Access the Application
- Frontend: http://localhost:5173/
- Backend API: http://127.0.0.1:8000/
- Admin Panel: http://127.0.0.1:8000/admin/

---

## Common Pitfalls and Solutions

### Issue 1: PowerShell Execution Policy
**Error**: `cannot be loaded because running scripts is disabled`

**Solution**:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Issue 2: PostgreSQL Connection Failed
**Error**: `could not connect to server: Connection refused`

**Solutions**:
1. Ensure PostgreSQL service is running (check Services app)
2. Verify credentials in `.env` file
3. Check PostgreSQL port (default 5432)
4. For quick testing, switch to SQLite: `USE_SQLITE_FALLBACK=1`

### Issue 3: CORS Errors in Browser
**Error**: `Access-Control-Allow-Origin` header missing

**Solution**: Ensure backend `.env` has:
```env
CORS_ALLOW_ALL_ORIGINS=1
```

### Issue 4: Port Already in Use
**Error**: `That port is already in use`

**Solutions**:
- For backend: `python manage.py runserver 8001` (use different port)
- For frontend: Check `vite.config.js` or use `npm run dev -- --port 5174`

### Issue 5: Missing Static/Media Files
**Issue**: Uploads not working properly

**Solution**: The `uploads/` directory is already included in the project. Ensure it exists:
```powershell
cd backend
mkdir uploads  # if not exists
```

### Issue 6: Database Migration Errors
**Error**: `relation already exists` or similar migration conflicts

**Solution** (for development only):
```powershell
# WARNING: This deletes all data
Remove-Item db.sqlite3  # SQLite only
python manage.py migrate
```

For PostgreSQL, drop and recreate the database instead.

---

## Creating User Accounts

The system has 4 user roles (أنواع المستخدمين):

| Role | Arabic | Description |
|------|--------|-------------|
| `admin` | مدير | Full system access, user management, audit logs |
| `data_entry` | مدخل بيانات | Creates dossiers and documents, submits for review |
| `auditor` | مدقق | Reviews and approves/rejects documents from assigned data entry users |
| `reader` | قارئ | Read-only access to approved documents |

### Method 1: Using Django Admin (Recommended for initial setup)

1. First, create a superuser:
```powershell
cd backend
.\venv\Scripts\Activate.ps1
python manage.py createsuperuser
```

2. Start the backend server:
```powershell
python manage.py runserver
```

3. Open browser and go to: http://127.0.0.1:8000/admin/

4. Login with superuser credentials

5. Click on "Users" → "Add User"

6. Fill in:
   - **Username**: (e.g., admin2, data_entry1, auditor1, reader1)
   - **Password**: (set a secure password)
   - **Role**: Select from dropdown (admin, data_entry, auditor, reader)

7. For Data Entry users:
   - You can optionally assign an Auditor in the "Assigned auditor" field
   - This links the data entry user to a specific auditor for the review workflow

### Method 2: Using Django Shell (For batch creation)

```powershell
cd backend
.\venv\Scripts\Activate.ps1
python manage.py shell
```

Then run:

```python
from core.models import User, UserRole

# Create Admin
admin_user = User.objects.create_user(
    username="admin2",
    password="SecurePass123!",
    role=UserRole.ADMIN,
    first_name="Admin",
    last_name="User",
    email="admin2@example.com"
)
print(f"Created: {admin_user}")

# Create Auditor
auditor_user = User.objects.create_user(
    username="auditor1",
    password="SecurePass123!",
    role=UserRole.AUDITOR,
    first_name="Ahmed",
    last_name="Auditor",
    email="auditor1@example.com"
)
print(f"Created: {auditor_user}")

# Create Data Entry (linked to auditor)
data_entry_user = User.objects.create_user(
    username="data_entry1",
    password="SecurePass123!",
    role=UserRole.DATA_ENTRY,
    first_name="Sami",
    last_name="DataEntry",
    email="data_entry1@example.com",
    assigned_auditor=auditor_user  # Link to auditor
)
print(f"Created: {data_entry_user}")

# Create Reader
reader_user = User.objects.create_user(
    username="reader1",
    password="SecurePass123!",
    role=UserRole.READER,
    first_name="Fatima",
    last_name="Reader",
    email="reader1@example.com"
)
print(f"Created: {reader_user}")

exit()
```

### Role Permissions Summary

**Admin (مدير):**
- Full access to all features
- Can create/manage users
- Can view audit logs
- Can approve/reject any document
- Can create dossiers and documents

**Data Entry (مدخل بيانات):**
- Can create dossiers with first document
- Can add documents to non-archived dossiers
- Can edit own draft documents
- Can submit documents for review
- Cannot approve/reject documents
- Can only see own dossiers/documents

**Auditor (مدقق):**
- Can view documents from assigned data entry users
- Can approve/reject pending documents
- Can view review queue
- Cannot create/edit dossiers or documents
- Read-only access to approved documents

**Reader (قارئ):**
- Read-only access to approved documents only
- Cannot create, edit, or review anything
- Cannot see pending or draft documents

### Testing User Login

After creating users, test login via the frontend:

1. Start both backend and frontend servers
2. Go to http://localhost:5173/
3. Try logging in with different user accounts
4. Verify each role sees the appropriate menu options and pages

### Common User Setup Issues

**Issue**: Data entry user cannot see "Submit" button
- **Cause**: Document must be in DRAFT status and created by the data entry user

**Issue**: Auditor cannot see documents in review queue  
- **Cause**: Auditor must be assigned to the data entry user who created the document

**Issue**: Reader sees empty documents list
- **Cause**: Reader can only see APPROVED documents (no drafts, no pending)

---

## Testing the Setup

Run the test suite to verify everything works:

```powershell
cd backend
.\venv\Scripts\Activate.ps1
python manage.py test core.tests --verbosity=2
```

Expected: Tests should run (some may fail if you've modified code, but setup is correct if Django can run tests).

---

## Production Deployment Notes (Not for Local Setup)

**DO NOT use these for local development:**
- `DEBUG=0` in production
- Use strong `SECRET_KEY` (generate new one)
- Configure proper `ALLOWED_HOSTS`
- Use PostgreSQL (not SQLite)
- Set up proper static file serving (WhiteNoise or nginx)
- Configure HTTPS

---

## Quick Reference: Essential Commands

| Task | Command |
|------|---------|
| Activate venv | `.\venv\Scripts\Activate.ps1` |
| Install backend deps | `pip install -r requirements.txt` |
| Run migrations | `python manage.py migrate` |
| Run backend | `python manage.py runserver` |
| Run tests | `python manage.py test core.tests` |
| Install frontend deps | `npm install` |
| Run frontend | `npm run dev` |
| Build frontend | `npm run build` |

---

## Project Structure Reminder

```
archive-demo/
├── backend/              # Django backend
│   ├── config/           # Django settings
│   ├── core/             # Main app (models, views, serializers)
│   ├── uploads/          # File uploads storage
│   ├── .env              # Environment variables (create from .env.example)
│   ├── requirements.txt  # Python dependencies
│   └── manage.py         # Django management
├── frontend/             # React frontend
│   ├── src/              # React components
│   ├── .env              # Frontend env vars (create from .env.example)
│   └── package.json      # Node dependencies
└── docs/                 # Documentation
```

---

**Last Updated**: March 2026  
**Project**: Archive Demo - Document Management System
