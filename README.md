App for doing chatting over WebRtc
WIP:
- support for video and audio calls

in order to run it:
0. Pre-conditions: python 3.11, virtualenv  should be installed, project root folder: signalig_server
1. Install virtualenv:
`virtualenv --python=python3.11 venv`
2. Install dependencies
`pip install -r requirements.txt`
3. Run program
`uvicorn signaling_server.server:app --reload`
4. Open in browser: http://127.0.0.1:8000/static/index.html select nickname and login
5. Repeat in new tab step 4 with other nicname
6. Select user and start chatting
