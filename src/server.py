__author__ = 'Zachery Thomas'

import os
import json

from bottle import post, request, run
import game

MYID = os.getenv('MYID')

@post('/messages')
def messages():
    data = json.loads(request.body.read())['data']

    room_id = data['roomId']
    room_type = data['roomType']
    person_id = data['personId']
    message_id = data['id']

    if person_id == MYID:
        return

    game.tick(room_id, room_type, person_id, message_id)
    return



if __name__ == "__main__":
    run(host='0.0.0.0', port=80)
