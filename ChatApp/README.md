# Connectly Chat App

Connectly is a locally runnable, room-based chat application built with Django and Django Channels. This guide describes the local demonstration setup; it does not claim that the application is deployed or ready for public production.

## Features

- Account sign-up, login, and logout
- Chat rooms with live browser-to-browser messages
- Saved messages and paginated history synchronization after reconnect
- Live typing indicators and online-user presence
- Theme switching and responsive page layouts

## Technology and architecture

- **Browser clients** render the Django templates and connect to the room WebSocket endpoint.
- **Django** handles HTTP pages, authentication, and application data access.
- **Django Channels** routes authenticated WebSocket connections through the ASGI application and broadcasts room events.
- **SQLite** stores accounts, rooms, and messages using Django's ORM.
- **Daphne** provides the ASGI server used by the local `runserver` command.

Messages are written to the database before live delivery. Clients can request message history by message ID, so reconnect synchronization does not depend only on events received while a browser was connected.

## Prerequisites

- Python 3.14.4 (the runtime used for the checks documented for this copy)
- SQLite support from the Python installation

The direct Python dependencies are pinned in [`requirements.txt`](requirements.txt). No Redis service is needed for the default local setup.

## Local setup and startup

Run these commands in PowerShell from the repository root. If you already have a working environment, skip virtual-environment creation and dependency installation.

```powershell
Set-Location .\ChatApp
py -3.14 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py shell -c "from chat.models import ChatRoom; ChatRoom.objects.get_or_create(slug='demo-room', defaults={'name': 'Demo Room'})"
.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Open <http://127.0.0.1:8000/> and create two accounts through the sign-up page. Keep the development server running while using the app. The demo room command is safe to repeat; it creates the room only if it does not already exist.

## Two-user presentation demo (2–3 minutes)

1. Start the server and ensure the demo room exists.
2. Open <http://127.0.0.1:8000/> in a normal browser window and a separate private/incognito window.
3. Sign in as the first user in one window and the second user in the other. If needed, create each account through sign-up first.
4. Open **Demo Room** in both windows. Show that each client sees the other user online.
5. Start typing in the first window and point out the typing indicator in the second.
6. Send a short message from the first user and a reply from the second; show that both clients receive the messages live.
7. Refresh one window and show that saved messages remain available in the room history.

## Troubleshooting

- **Django cannot start:** Run commands from the `ChatApp` directory and use `.\venv\Scripts\python.exe`; confirm dependency installation completed.
- **Database/table errors:** Run `.\venv\Scripts\python.exe manage.py migrate` before starting the server.
- **No room appears:** Run the idempotent `Demo Room` creation command from the setup section.
- **WebSocket does not connect:** Confirm the server is still running, both clients use the same host and port, both users are signed in, and both opened the same room. Check the browser developer console and the server terminal for the connection error.
- **Port 8000 is busy:** Stop the other local server or start this one on a different port, then use that same port in both browser windows.

## Verification notes

The automated suite covers account and room-page access, saved-message rendering, authenticated WebSocket connections, live messaging, typing and presence events, and paginated message-history synchronization. Theme switching and responsive layout are application features but are not covered by that automated suite.

The checked-in SQLite database should be treated as local application data, not as a distributable demo fixture. The development server is bound to localhost in the commands above; public deployment requires a separate security and operations review.
