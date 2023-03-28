import typing as t
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketState


logger = logging.getLogger(__name__)
app = FastAPI()
app.mount("/static", StaticFiles(directory="frontend"))

JSONType = t.Union[str, int, float, bool, None, t.Dict[str, t.Any], t.List[t.Any]] 

class ConnectionManager:
    """
    Idea is to hide choosen protocol behind this manager
    """
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}
        self.online_users: dict[str, str] = {}

    async def connect(self, connection: WebSocket):
        await connection.accept()
    
    def register_user_connection(self, username: str, connection: WebSocket):
        self.active_connections[username] = connection
        # store the connection details 
        connection.name = username
        connection.otherName = None
    
    def update_user_status(self, username: str, status: str='offline'):
        # store the connection name in the userlist 
        self.online_users[username] = status
    
    def get_user_status(self, username: str) -> str | None: 
        return self.online_users.get(username)

    def disconnect(self, connection: WebSocket):
        self.active_connections.pop(connection, None)

    async def send_message(self, connection: WebSocket,  message: dict):
        if connection.client_state == WebSocketState.CONNECTED:
            await connection.send_json(message)

    async def broadcast(self, message: JSONType):
        # TODO: gather
        for connection in self.active_connections.values():
            await self.send_message(connection, message)

    ###############
    # service layer
    ###############

    async def update_users_list(self):
        await self.broadcast({ 'type': "server_userlist", 'name': [[k,v] for k,v in self.online_users.items()]})
    
    async def login_user(self, username: str, connection: WebSocket):
        if  username in self.active_connections:
            # Already same username has logged in the server 
            # send response to client back with login failed 
            await self.send_message(connection, { "type": "server_login", "success": False})
            logger.info("login failed")
        else:
            # store the connection details 
            self.register_user_connection(username, connection)
            self.update_user_status(username, 'online')
            # notify user about successful login
            await self.send_message(connection, { "type": "server_login", "success": True })
            logger.info("Login sucess")
            await self.update_users_list()

    async def send_offer(self, username: str, offer: dict, connection: WebSocket):
        # Check the peer user has logged in the server 
        conn = self.active_connections.get(username)

        if not conn:
            # Error handling 
            logger.info("connection is None..")
            await self.send_message(connection, { "type": "server_nouser", "success": False })

        elif conn.otherName == None:
            # When user is free and availble for the offer 
            # Send the offer to peer user 
            await self.send_message(conn, { 'type': "server_offer", 'offer': offer, 'name': connection.name })

        else:
            # User has in the room, User is can't accept the offer 
            await self.send_message(connection, { "type": "server_alreadyinroom", "success": True, "name": username})
    
    async def send_answer(self, username: str, answer: dict):
        conn = self.active_connections.get(username)
        if conn:
            await self.send_message(conn, {"type": "server_answer", "answer": answer})
    
    async def send_candidate_request(self, username: str, candidate: dict):
        conn = self.active_connections.get(username)
        if conn and conn.otherName != None:
            await self.send_message(conn, { "type": "server_candidate", "candidate": candidate })
            logger.info("candidate sending --")

    async def leave(self, username: str, connection: dict):
        conn = self.active_connections.get(username)
        if conn:
            # Send response back to users who are in the room 
            await self.send_message(conn, { "type": "server_userwanttoleave" })
            await self.send_message(connection, { "type": "server_userwanttoleave" })
            self.update_user_status(username, 'online')
            self.update_user_status(connection.name, 'online')

            # Update the connection status with available 
            conn.otherName = None
            connection.otherName = None

            await self.update_users_list()
            logger.info("end room")
    
    async def busy(self, username: str):
        conn = self.active_connections.get(username)
        if conn:
            await self.send_message(conn, { "type": "server_busyuser" })
    
    async def want_to_call(self, username: str, connection: WebSocket):
        conn = self.active_connections.get(username)
        if conn:
            if conn.otherName != None and self.get_user_status(username) == 'busy':
                # User has in the room, User can't accept the offer 
                await self.send_message(connection, { "type": "server_alreadyinroom", "success": True, "name": username })
            else:
                # User is avilable, User can accept the offer 
                await self.send_message(connection, { "type": "server_alreadyinroom", "success": False, "name": username })
        else:
            # Error handling with invalid query 
            await self.send_message(connection, { "type": "server_nouser", "success": False })
    
    async def handle_ready(self, username: str, connection: WebSocket):
        conn = self.active_connections.get(username)
        if conn:
            # Update the user status with peer name
            connection.otherName = username
            conn.otherName = connection.name
            self.update_user_status(username,'busy')
            self.update_user_status(connection.name,'busy')

            # Send response to each users 
            await self.send_message(conn, { "type": "server_userready", "success": True, "peername": connection.name })
            await self.send_message(connection, { "type": "server_userready", "success": True, "peername": conn.name })
            # Send updated user list to all existing users 
            await self.update_users_list()
    
    async def handle_quit(self, username: str, connection: WebSocket):
        connection.name in self.active_connections and self.active_connections.pop(connection.name, None)
        username in self.online_users and self.online_users.pop(username, None)
        # Send updated user list to all existing users 
        await self.update_users_list()


manager = ConnectionManager()


@app.get("/")
async def get():
    return FileResponse("fronte/index.html")


@app.websocket("/ws")
async def websocket_endpoint(connection: WebSocket):

    await manager.connect(connection)
    try:
        while True:
            data = await connection.receive_json()
            a_type = data.get('type')
            match a_type:
                case "login":
                    await manager.login_user(username=data['name'], connection=connection)
                # Offer request from client
                case "offer":
                    await manager.send_offer(username=data['name'], offer=data['offer'], connection=connection)
                # Answer request from client
                case "answer":
                    print(f'>>DATA: {data}')
                    await manager.send_answer(username=data['name'], answer=data['answer'])
                # candidate request 
                case "candidate":
                    await manager.send_candidate_request(username=data['name'], candidate=data['candidate'])
                # when user want to leave from room 
                case "leave":
                    await manager.leave(username=data['name'], connection=connection)
                # When user reject the offer 
                case "busy":
                    await manager.busy(username=data['name'])
                case "want_to_call":
                    await manager.want_to_call(username=data['name'], connection=connection)
                # Once offer and answer is exchnage, ready for a room 
                case "ready":
                    await manager.handle_ready(username=data['name'], connection=connection)
                # user quit/signout 
                case "quit":
                    await manager.handle_quit(username=data['name'], connection=connection)
                case "clientping":
                    await manager.send_message(connection, { "type": "server_pong", "name": "pong"})
                # default 
                case _:
                    await manager.send_message(connection, { "type": "server_error", "message": "Unrecognized `command`: " + a_type})
    except WebSocketDisconnect as e:
        logger.exception('socket problem')
        manager.disconnect(connection)
        # await manager.broadcast(f"Client #{client_id} left the chat")