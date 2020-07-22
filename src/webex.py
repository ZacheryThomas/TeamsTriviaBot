import sys
import json
import asyncio

import websockets
import uuid
from webexteamssdk import WebexTeamsAPI
import logging

DEVICES_URL = 'https://wdm-a.wbx2.com/wdm/api/v1/devices'

DEVICE_DATA={
    "deviceName":"pywebsocket-client",
    "deviceType":"DESKTOP",
    "localizedModel":"python",
    "model":"python",
    "name":"python-spark-client",
    "systemName":"python-spark-client",
    "systemVersion":"0.1"
}

class Webex(object):
    def __init__(self, access_token, post_handler=None):
        self.access_token = access_token
        self.api = WebexTeamsAPI(access_token=access_token)
        self.device_info = None
        self.post_handler = post_handler


    def _handle_post(self, msg):
        if msg['data']['eventType'] == 'conversation.activity':
            logging.debug(' Event Type is conversation.activity\n')
            activity = msg['data']['activity']
            if activity['verb'] == 'post':
                logging.debug('activity verb is post, message id is %s\n' % activity['id'])
                sparkmessage = self.api.messages.get(activity['id'])
                room = self.api.rooms.get(sparkmessage.roomId)
                person = self.api.people.get(sparkmessage.personId)

                if sparkmessage.personEmail in self.my_emails:
                    logging.debug('message is from myself, ignoring')
                    return

                logging.info('Message from %s: %s\n' % (sparkmessage.personEmail, sparkmessage.text))
                if self.post_handler:
                    self.post_handler(sparkmessage, room, person)


    def _get_device_info(self):
        logging.debug('getting device list')
        try:
            resp = self.api._session.get(DEVICES_URL)
            for device in resp['devices']:
                if device['name']==DEVICE_DATA['name']:
                    self.device_info = device
                    return device
        except:
            pass
        logging.info('device does not exist, creating')

        resp = self.api._session.post(DEVICES_URL, json = DEVICE_DATA)
        if resp is None:
            logging.error('could not create device')
        self.device_info = resp
        return resp

    def _get_display_name(self):
        return self.api.people.me().displayName

    def run(self):
        if self.device_info==None:
            if self._get_device_info() is None:
                logging.error('could not get/create device info')
                return

        self.my_emails = self.api.people.me().emails

        async def _run():
            logging.debug("Opening websocket connection to %s" % self.device_info['webSocketUrl'])
            async with websockets.connect(self.device_info['webSocketUrl']) as ws:
                logging.info("WebSocket Opened\n")
                msg = {'id': str(uuid.uuid4()),
                        'type': 'authorization',
                        'data': {
                                    'token': 'Bearer ' + self.access_token
                                }
                        }
                await ws.send(json.dumps(msg))

                while True:
                    message = await ws.recv()
                    logging.debug("WebSocket Received Message(raw): %s\n" % message)
                    try:
                        msg = json.loads(message)
                        loop = asyncio.get_event_loop()
                        loop.run_in_executor(None, self._handle_post, msg)
                    except:
                        logging.warning('An exception occurred while processing message. Ignoring. ')

        asyncio.get_event_loop().run_until_complete(_run())