# OpenMNC Backend API (`openmnc-backend`)

The official high-performance asynchronous REST API powering **OpenMNC LLP**'s company website, applicant tracking system, zero-storage media management, and content publishing engine.

---

## 🚀 Tech Stack

- **Framework:** FastAPI (Python 3.12)
- **Database Driver:** Motor (Async MongoDB Driver)
- **Database:** MongoDB Atlas (M0 Free Tier)
- **Authentication:** JWT (JSON Web Tokens) + Passlib (Bcrypt)
- **Media CDN:** Cloudinary (Zero-Storage Architecture)
- **Deployment:** Render (`render.yaml` native support)

---

## 📁 Repository Structure

```
backend/
├── models/             # Pydantic V2 data models and request/response schemas
│   ├── blog.py         # Blog posts, SEO metadata, reading times
│   ├── career.py       # Job postings & candidate applications
│   ├── contact.py      # Inquiries, lead tracking & source attribution
│   ├── service.py      # Core business vertical offerings
│   └── settings.py     # Global site settings, metrics & company contacts
├── routers/            # Modular FastAPI APIRouters
│   ├── auth.py         # Admin authentication (/api/auth)
│   ├── blogs.py        # Blog CRUD and SEO publishing (/api/blogs)
│   ├── careers.py      # Job listings & application submissions (/api/careers)
│   ├── contact.py      # Contact inquiry endpoints (/api/contact)
│   ├── media.py        # Cloudinary image upload pipeline (/api/media)
│   ├── services.py     # Service catalog endpoints (/api/services)
│   └── settings.py     # Site configuration (/api/settings)
├── auth.py             # JWT token issuance, password hashing & route dependencies
├── cloudinary_service.py # Direct-to-CDN media upload handling
├── database.py         # Async Motor connection lifecycle & collection helpers
├── google_service.py   # Google Sheets candidate sync & zero-storage resume helper
├── webhook_service.py  # Vercel / Netlify build webhook dispatchers
├── main.py             # Application entry point, CORS middleware & health check
├── seed.py             # Database initialization script
├── requirements.txt    # Production Python dependencies
├── Procfile            # Process file for cloud container runners
└── render.yaml         # One-click Render infrastructure-as-code
```

---

## ⚙️ Environment Variables

Create a `.env` file in the root of the `backend` directory (refer to `.env.example`).

> **Security Notice:** Never commit `.env` or credentials to version control. Set these variables via your cloud host's dashboard (e.g. Render Environment Variables).

| Variable Name | Required | Description |
|---|---|---|
| `MONGODB_URI` | **Yes** | MongoDB Atlas connection string (`mongodb+srv://...`) |
| `JWT_SECRET` | **Yes** | High-entropy secret key for signing admin JWT tokens |
| `JWT_ALGORITHM` | **Yes** | Hashing algorithm (default: `HS256`) |
| `JWT_EXPIRE_HOURS`| **Yes** | Token expiration window in hours (default: `72`) |
| `ADMIN_EMAIL` | **Yes** | Administrator email for login |
| `ADMIN_PASSWORD_HASH` | **Yes** | Bcrypt hash for the administrator account |
| `CLOUDINARY_CLOUD_NAME` | **Yes** | Cloudinary cloud account identifier |
| `CLOUDINARY_API_KEY` | **Yes** | Cloudinary public API key |
| `CLOUDINARY_API_SECRET` | **Yes** | Cloudinary secret API key |
| `GOOGLE_OAUTH_CLIENT_ID`| **Yes** | Google Cloud OAuth 2.0 Web Client ID for candidate authentication |
| `GOOGLE_APPS_SCRIPT_WEBHOOK_URL` | *Optional* | Webhook URL for real-time Google Sheets candidate mirroring |
| `VERCEL_DEPLOY_HOOK_URL` | *Optional* | Deploy hook triggering static regeneration when CMS content updates |
| `PORT` | *Optional* | Server listening port (default: `8000`) |

---

## 🛠️ Local Development & Setup

### 1. Prerequisites
- Python 3.10+ (Python 3.12 recommended)
- A running MongoDB Atlas cluster or local MongoDB instance

### 2. Setup Virtual Environment & Install Dependencies
```bash
python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Initialize / Seed the Database
Populates the database with the initial 6 services, core site settings, sample AI blogs, and sets the admin credentials:
```bash
python seed.py
```

### 4. Run the Development Server
```bash
uvicorn main:app --reload --port 8000
```
- API Base: `http://localhost:8000`
- Interactive OpenAPI Docs: `http://localhost:8000/docs`
- ReDoc Docs: `http://localhost:8000/redoc`
- Health Check: `http://localhost:8000/ping`

---

## 🧪 Testing & Health Checks

Verify your deployment and endpoints using `curl` or PowerShell:
```bash
# Health check
curl http://localhost:8000/ping

# Check public services listing
curl http://localhost:8000/api/services

# Verify robots.txt
curl http://localhost:8000/robots.txt
```

---

## 🚢 Deployment (Render)

1. Connect this repository (`openmnc-backend`) to **Render**.
2. Select **Web Service** $\to$ Runtime: **Python 3**.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Configure all environment variables in the Render Environment Dashboard.
