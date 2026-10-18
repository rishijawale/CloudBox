# CloudBox — Local Cloud Storage (Flask + Docker)

A student mini-project demonstrating a cloud-storage-style web application, authentication, local file storage, folders, expiring share links, and container portability. Designed to run on Windows with PowerShell. All development and runtime services can run locally for free.

> This is an educational project, not a production cloud-storage service. Do not store sensitive or irreplaceable files in it. For real deployment, add HTTPS, rate limiting, stronger operational controls, backups, malware scanning, and a managed production database.

## Features

- Register and sign in with Werkzeug password hashing
- Per-user file ownership and isolated storage directories
- Upload multiple allowed file types (25 MB per request)
- Download and delete files
- Create nested folders; empty folders can be deleted
- Create random-token share links with `view` or `download` permission
- Share links expire after 1–30 days and can be revoked
- CSRF protection on forms
- Secure filenames, random internal storage names, ownership checks, and basic security headers
- Responsive glassmorphism UI
- Docker image with non-root runtime user and persistent `/data` volume

## Requirements

- Windows 10/11 (64-bit), current VS Code, and Python 3.10+ for local development
- Docker Desktop for Windows for the container portion (free under Docker's applicable terms)
- Docker Desktop may require WSL 2 and hardware virtualization. You do not need to work inside an Ubuntu terminal.

## A. Run locally on Windows

Open PowerShell in VS Code.

```powershell
mkdir "$HOME\CloudBox"
cd "$HOME\CloudBox"
```

If you already extracted this project ZIP, `cd` into the extracted `CloudBox` folder instead of creating a second folder.

Create and activate a virtual environment:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If activation is blocked in the current PowerShell process:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Install dependencies and run:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 and register a user. Uploaded data is stored in the `storage` folder, and the SQLite database is `cloudbox.db`.

Stop the development server with `Ctrl+C`.

### Optional: use a strong local secret

Before running, you can set a secret in the current PowerShell session:

```powershell
$env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
python app.py
```

Keep the same secret if you want existing browser sessions to remain valid. This example sets it only for the current terminal session.

## B. Install Docker Desktop

1. Use the official Windows install guide: https://docs.docker.com/desktop/setup/install/windows-install/
2. Install Docker Desktop and select the WSL 2 backend if offered.
3. If requested, enable WSL 2 and hardware virtualization according to Docker's official instructions.
4. Start Docker Desktop and wait until the engine is running.
5. In PowerShell:

```powershell
docker --version
docker info
```

If `docker info` cannot connect, Docker Desktop may still be starting, or Windows may need the setup steps requested by its installer.

## C. Build and run the container

From the folder containing `Dockerfile`:

```powershell
docker build -t cloudbox:1.0 .
```

Generate a secret and run with persistent storage:

```powershell
$secret = python -c "import secrets; print(secrets.token_hex(32))"
docker volume create cloudbox-data
docker run -d --name cloudbox `
  -p 5000:5000 `
  -e SECRET_KEY=$secret `
  -v cloudbox-data:/data `
  cloudbox:1.0
```

Open http://127.0.0.1:5000.

Useful commands:

```powershell
docker ps
docker logs cloudbox
docker stop cloudbox
docker start cloudbox
docker rm -f cloudbox
```

The named Docker volume `cloudbox-data` keeps the SQLite database and uploaded files when the container is replaced. Do not remove the volume if you want to keep its data.

To rebuild after changing code:

```powershell
docker rm -f cloudbox
docker build -t cloudbox:1.0 .
$secret = python -c "import secrets; print(secrets.token_hex(32))"
docker run -d --name cloudbox `
  -p 5000:5000 `
  -e SECRET_KEY=$secret `
  -v cloudbox-data:/data `
  cloudbox:1.0
```

For a classroom portability demonstration, show that the same image can be run on another compatible machine with Docker, then sign in and confirm the app starts. The image alone does not include your uploaded files or database; move/restore the persistent volume separately if you need the same data.

## D. Test checklist

- [ ] Register a new account with a password of at least 10 characters.
- [ ] Sign out and sign back in.
- [ ] Upload a PDF or image.
- [ ] Download the file and confirm it opens.
- [ ] Create a folder and upload a file inside it.
- [ ] Create a share link with a short expiry.
- [ ] Open the share link in a private/incognito window.
- [ ] Revoke the link from **Shared links** and confirm it no longer works.
- [ ] Try downloading a file ID while signed into a different account; it should return 404.
- [ ] Run the same app in Docker and verify it still works.
- [ ] Stop and start the container and verify files remain available.

## Project structure

```text
CloudBox/
├── app.py
├── requirements.txt
├── Dockerfile
├── .dockerignore
├── .gitignore
├── README.md
├── templates/
│   ├── base.html
│   ├── landing.html
│   ├── auth.html
│   ├── dashboard.html
│   ├── shares.html
│   ├── shared_file.html
│   └── share_unavailable.html
└── static/
    ├── css/style.css
    └── js/app.js
```

## Architecture

```text
Browser
  |
  | HTTP on localhost:5000
  v
Flask application
  |-- Flask-Login: sessions and authentication
  |-- Flask-WTF: CSRF protection
  |-- SQLAlchemy + SQLite: users, folders, file metadata, share links
  |-- Local filesystem: uploaded file bytes
  |
  v
Docker image/container (same app packaged for portability)
  |
  v
Named Docker volume mounted at /data (persistent database and files)
```

## Concepts to explain in viva

- **Containerization:** Packages an application and its runtime dependencies into an image.
- **Image vs container:** An image is the reusable template; a container is a running instance.
- **Port mapping:** `-p 5000:5000` forwards host port 5000 to container port 5000.
- **Persistent volume:** Stores application data outside the container's writable layer.
- **Authentication vs authorization:** Authentication establishes who signed in; authorization checks which files they may access.
- **Password hashing:** The database stores a password hash, not the original password.
- **Share token:** A high-entropy random token identifies a share link; expiry and revocation limit its lifetime.
- **CSRF:** Helps prevent another site from tricking a signed-in browser into submitting unwanted form actions.
- **Why SQLite:** Simple local database suitable for a student demonstration; concurrent production deployments should use a more suitable managed database.
- **Limitations:** Local disk storage, no malware scanning, no email delivery, no public hosting, and no production-grade monitoring or rate limiting.

## Troubleshooting

### `py` not recognized
Install Python from https://www.python.org/downloads/windows/ and enable the Python launcher/PATH options during setup. Reopen PowerShell.

### PowerShell says scripts are disabled
Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that PowerShell session, then activate the virtual environment again.

### Port 5000 is busy
Stop the other app or use another host port for Docker, e.g. `-p 5001:5000`, then open http://127.0.0.1:5001.

### Docker Desktop won't start
Check the official install guide and follow its WSL 2, virtualization, and Windows requirements. You can continue developing and testing the Flask app locally while resolving Docker setup.

### Lost data after removing the container
The data should persist only if the named volume was mounted as shown. Do not run `docker volume rm cloudbox-data` unless you intend to delete the project's persisted data.
