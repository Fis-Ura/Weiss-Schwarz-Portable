import asyncio
import websockets
import requests
import json
import sys
import time
import base64

PPSSPP_MATCH_API = 'http://report.ppsspp.org/match/list'
PPSSPP_DEFAULT_PATH = '/debugger'

# Hacked up Python version of the JS code sample at https://github.com/unknownbrackets/ppsspp-api-samples

class PPSSPP:
    def __init__(self):
        self.socket_ = None
        self.pendingTickets_ = {}
        self.listeners_ = {}

    async def autoConnect(self):
        if self.socket_ is not None:
            raise ValueError('Already connected, disconnect first')

        try:
            listing = requests.get(PPSSPP_MATCH_API).json()
            await self.tryNextEndpoint_(listing)
            # async with websockets.connect(PPSSPP_MATCH_API) as websocket:
            #     listing = await websocket.recv()
            #     await self.tryNextEndpoint_(json.loads(listing))
        except Exception as e:
            raise ValueError(f"Couldn't connect: {e}")

    async def connect(self, uri):
        if self.socket_ is not None:
            raise ValueError('Already connected, disconnect first')

        try:
            self.socket_ = await websockets.connect(uri, compression=None)
            await self.setupSocket_()
        except Exception as e:
            raise ValueError(f"Couldn't connect to {uri}: {e}")

    async def disconnect(self):
        if self.socket_ is None:
            raise ValueError('Not connected')

        self.failAllPending_('Disconnected from PPSSPP')
        await self.socket_.close()
        self.socket_ = None

    async def setupSocket_(self):
        async def receive_handler(message):
            try:
                data = json.loads(message)
                if data['event'] == 'error':
                    self.handleError_(data['message'], data.get('level'))
                handled = False
                if 'ticket' in data:
                    handled = self.handleTicket_(data['ticket'], data)
                self.handleMessage_(data, handled)
            except Exception as e:
                self.handleError_(f"Failed to parse message from PPSSPP: {str(e)}", level='ERROR')

        self.socket_.receive = receive_handler

        async def close_handler():
            if self.onClose:
                self.onClose()
            self.failAllPending_('PPSSPP disconnected')
            self.socket_ = None

        self.socket_.on_close = close_handler

    async def tryNextEndpoint_(self, listing):
        if not listing or len(listing) == 0:
            raise ValueError("Couldn't connect automatically. Is PPSSPP connected to the same network?")

        for entry in listing:
            endpoint = f"ws://{entry['ip']}:{entry['p']}{PPSSPP_DEFAULT_PATH}"
            try:
                await self.connect(endpoint)
                return
            except Exception as e:
                pass
        raise ValueError("Couldn't connect to any endpoint")

    async def send(self, data):
        if self.socket_ is None:
            raise ValueError('Not connected')

        err = ValueError('PPSSPP returned an error')

        if data['event'] in ['cpu.stepping', 'cpu.resume']:
            await self.socket_.send(json.dumps(data))
            return None

        ticket = self.makeTicket_()
        self.pendingTickets_[ticket] = asyncio.Future()

        await self.socket_.send(json.dumps({ **data, 'ticket': ticket }))

        try:
            result = await self.receive_full_response(ticket)
            del self.pendingTickets_[ticket]
            if result['event'] == 'error':
                err.name = 'DebuggerError'
                err.message = result['message']
                err.originalMessage = result
                raise err
            return result
        except asyncio.TimeoutError:
            del self.pendingTickets_[ticket]
            raise err
        
    async def receive_full_response(self, ticket, timeout=5):
        start_time = time.time()
        response = ''
        while True:
            if time.time() - start_time > timeout:
                raise TimeoutError("Timeout waiting for response")

            response = await self.socket_.recv()
            response_data = json.loads(response)
            if response_data.get('ticket') == ticket:
                break
        return response_data

    # Turns out JS is not python who would've thought,
    # below code needs fixing
    def listen(self, eventName, handler):
        if eventName not in self.listeners_:
            self.listeners_[eventName] = []
        self.listeners_[eventName].append(handler)

        def remove_listener():
            self.listeners_[eventName].remove(handler)

        return {'remove': remove_listener}

    def handleTicket_(self, ticket, data):
        if ticket in self.pendingTickets_:
            self.pendingTickets_[ticket].set_result(data)
            return True
        self.handleError_(f"Received mismatched ticket: {json.dumps(data)}", level='ERROR')
        return False

    def handleMessage_(self, data, handled):
        handled = self.executeHandlers_(data['event'], data, handled)
        self.executeHandlers_('*', data, handled)

    def executeHandlers_(self, name, data, handled):
        if name in self.listeners_:
            for handler in self.listeners_[name]:
                if handler(data, handled):
                    handled = True
        return handled

    def handleError_(self, message, level=None):
        if self.onError:
            self.onError(message, level)
        elif level == 'ERROR':
            print(message, file=sys.stderr)
        else:
            print(message)

    def makeTicket_(self):
        import random
        import string
        ticket = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(8))
        if ticket in self.pendingTickets_:
            return self.makeTicket_()
        return ticket

    def failAllPending_(self, message):
        data = {'event': 'error', 'message': message, 'level': 'ERROR'}
        for ticket, future in self.pendingTickets_.items():
            future.set_result(data)
        self.pendingTickets_ = {}

STRINGS = dict()
# HASH_FUNCTION_ADDR = 0x0881E738
# HASH_FUNCTION_ADDR = 0x08811D80 # files only, a0
# HASH_FUNCTION_ADDR = 0x088105F0 # VOICE only, a1
HASH_FUNCTION_ADDR = 0x0880FCA4 # FINAL only, a1

async def main():
    ppsspp = PPSSPP()

    try:
        await ppsspp.autoConnect()

        # Introduce ourselves to PPSSPP. Here, '1.0.0' should be the version of your script.
        version_data = {'event': 'version', 'name': 'string-collector', 'version': '0.1.0'}
        result = await ppsspp.send(version_data)
        print('Connected to', result['name'], 'version', result['version'])

        # Check what game's running
        game_status_data = {'event': 'game.status'}
        result = await ppsspp.send(game_status_data)
        if result['game'] is None:
            print("You aren't playing any game yet? Boring.")
        elif result['game']['id'] != "ULJS00422" or result['game']['version'] != "1.02":
            print("Wrong game loaded! Expected ULJS00422 (1.02) but got", result['game']['id'], "(%s)" % result['game']['version'])
            return
        else:
            print('Playing', result['game']['title'], '(', result['game']['id'], 'version', result['game']['version'], ')')
        
        # Can we grab functions?
        # game_status_data = {'event': 'hle.func.list'}
        # result = await ppsspp.send(game_status_data)
        # if result['functions'] is None:
        #     print("No functions?")
        # else:
        #     pass
        
        print(f"Hooking up with 0x{HASH_FUNCTION_ADDR:08X}...")
        
        # Breaking point
        game_status_data = {'event': 'cpu.breakpoint.add', "address": HASH_FUNCTION_ADDR}
        result = await ppsspp.send(game_status_data)

        async def cpu_stepping_handler(info):
            # The PC register tells us where the breakpoint was, and is sent automatically.
            # Just ignore if it's not ours.
            if info['pc'] != HASH_FUNCTION_ADDR:
                return

            # Grab the parameters.
            result = await ppsspp.send({'event': 'cpu.getReg', 'name': 'a1'})
            str_addr = result['uintValue']
            
            # Collect string
            await read_string_at(ppsspp, str_addr)
            # Resume
            await ppsspp.send({'event': 'cpu.resume'})

        print('Collecting strings, press Ctrl-C to stop...')
        
        # Resume the thing cuz Python slow
        game_status_data = {'event': 'cpu.resume'}
        await ppsspp.send(game_status_data)
        while True:
            response = await ppsspp.socket_.recv()
            response_data = json.loads(response)
            if response_data.get('event') == 'cpu.stepping':
                await cpu_stepping_handler(response_data)
    except Exception as err:
        print('Something went wrong:', err)
    finally:
        await ppsspp.disconnect()


async def read_string_at(ppsspp: PPSSPP, addr):
    result = await ppsspp.send({'event': 'memory.readString', 'address': addr})
    STRINGS[result["value"]] = None

try:
    asyncio.run(main())
except KeyboardInterrupt:
    pass
finally:
    print("Saving collected strings...")
    try:
        with open("_found_strings.txt", "r", encoding="utf8") as file:
            lines = file.read().split("\n")
        
        for line in lines:
            STRINGS[line] = None
    except FileNotFoundError:
        pass
    with open("_found_strings.txt", "w", encoding="utf8") as f:
        f.write('\n'.join(list(STRINGS.keys())))