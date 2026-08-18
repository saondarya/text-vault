# 📁 Text Vault

A lightweight, multi-device cloud text and code manager built with **Flask** (backend) and **Vanilla HTML/CSS/JS** (frontend). Zero build steps, blazing fast, and 100% deployable to **Vercel** in one project.

---

## ✨ Features

- 🔐 **Multi-Device Authentication**: Access your personal vault securely from your phone, tablet, laptop, or desktop with username & password (JWT + secure password hashing).
- 📂 **Folder Hierarchy**: Create, rename, move, duplicate, and delete nested folders at any depth.
- 📦 **Download Folder as `.zip`**: Download any folder and all its nested subfolders & files as a `.zip` archive.
- 📋 **Copy Entire Folder to Clipboard**: Copy all files in a folder and its subfolders formatted as path-based text snippets with one click.
- 🗂️ **Local Folder & Multi-File Upload**: Select a folder from your computer (`webkitdirectory` / drag-and-drop), and Text Vault automatically reconstructs the entire folder hierarchy and imports all text and code files.
- 📝 **Distraction-Free Text Editor**:
  - Auto-save with live status indicators (`Saved` / `Unsaved changes`).
  - **One-Click Copy Text**: Copy file text to clipboard with instant toast notification (or from the file list).
  - **Quick Download & Duplicate**: Download individual files or duplicate files directly from the file list or editor.
  - Live stats: lines, word count, character count, and file size.
  - Tab indentation support.
- 🔍 **Instant Global Search**: Press <kbd>Ctrl</kbd> + <kbd>K</kbd> (or <kbd>Cmd</kbd> + <kbd>K</kbd>) to search across all file names, contents, and folders in real time.
- ⬇️ **Vault Backup & Export**: Export your complete vault structure and files as JSON in one click.

---

## 🛠️ Tech Stack

| Layer | Technology | Details |
|-------|------------|---------|
| **Frontend** | Vanilla HTML5 + Modern CSS + Vanilla JS (`public/`) | Zero build dependencies, mobile-responsive |
| **Backend** | Python Flask (`api/index.py`, `api/db.py`) | REST API + Serverless handler |
| **Database** | SQLite (Local) / PostgreSQL (Neon for Vercel) | Auto-migrated schema with foreign key cascades |
| **Deployment** | Vercel | Serverless Python Function + Static Public CDN |

---

## 📁 Project Structure

```
EXL/
├── api/
│   ├── index.py          # Flask API endpoints (auth, folders, files, import, search)
│   └── db.py             # SQLite & PostgreSQL database helper with fallback
├── public/
│   ├── index.html        # Single-page UI with modals and tree explorer
│   ├── css/
│   │   └── style.css     # Modern dark-theme responsive design
│   └── js/
│       └── app.js        # Client state, folder tree, editor, importer, search
├── tests/
│   └── test_api.py       # Automated unit test suite
├── requirements.txt      # Python dependencies
├── vercel.json           # Vercel serverless routing
├── run_local.py          # Local development server entrypoint
└── README.md
```

---

## 🚀 Running Locally

### 1. Prerequisites
- Python 3.10+ installed

### 2. Setup & Run
```bash
# 1. Create a virtual environment
python3 -m venv venv

# 2. Activate the virtual environment
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the local server
python run_local.py
```

### 3. Open in Browser
Visit **[http://localhost:5001](http://localhost:5001)**

> [!NOTE]
> When running locally, all data is automatically stored in `data/vault.db` (SQLite).

---

## 🌐 Deploying to Vercel (Multi-Device Cloud Access)

To access your vault from any phone, laptop, or other device worldwide, deploy it for free on Vercel:

### Step 1: Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit: Text Vault"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo-name>.git
git push -u origin main
```

### Step 2: Set Up a Free PostgreSQL Database (Neon)
Since Vercel serverless functions are stateless, use a persistent database:
1. Create a free account at [neon.tech](https://neon.tech).
2. Create a new database project and copy the **Connection string** (e.g. `postgresql://user:password@ep-xyz.us-east-2.aws.neon.tech/neondb?sslmode=require`).

### Step 3: Deploy on Vercel
1. Go to [vercel.com](https://vercel.com) and click **"Add New..." → "Project"**.
2. Select your GitHub repository.
3. In **Settings → Environment Variables**, add:

| Environment Variable | Value |
|----------------------|-------|
| `DATABASE_URL` | Your Neon PostgreSQL connection string |
| `JWT_SECRET` | A long random string (e.g. `your-super-secret-jwt-key-32-chars-long`) |

4. Click **Deploy**.

Your app is now live at `https://<your-project>.vercel.app`! You can log in from any phone or computer using your credentials.

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| <kbd>Ctrl</kbd> / <kbd>Cmd</kbd> + <kbd>S</kbd> | Save current file |
| <kbd>Ctrl</kbd> / <kbd>Cmd</kbd> + <kbd>K</kbd> | Open global search |
| <kbd>Ctrl</kbd> / <kbd>Cmd</kbd> + <kbd>Shift</kbd> + <kbd>C</kbd> | Copy entire file text to clipboard |
| <kbd>Tab</kbd> in editor | Insert 2 spaces |
| <kbd>Esc</kbd> | Close any open modal or mobile sidebar |

---

## 🧪 Running Tests

```bash
python -m unittest discover -s tests -p "test_*.py"
```

---

## 📄 License

MIT License
