__author__ = 'Zachery Thomas'

import re
import random
import os
import json
import bson
import time
import difflib
import traceback

import config
from webex import Webex
from pymongo import MongoClient

BEARER = os.getenv('BEARER')

MONGO_USERNAME = os.getenv('MONGO_INITDB_ROOT_USERNAME')
MONGO_PASSWORD = os.getenv('MONGO_INITDB_ROOT_PASSWORD')


client = MongoClient('mongo', username=MONGO_USERNAME, password=MONGO_PASSWORD, port=27017)
trivia_db = client.trivia

clues_collection = trivia_db.clues
rooms_collection = trivia_db.rooms

def format_text(text):
    """Formats text for processing"""
    text = text.lower()
    text = text.replace('jeopardy!', '')
    text = text.replace('what is', '')
    text = text.replace('what are', '')
    text = text.replace('@', '', 1)
    text = text.strip()
    return text


def get_possible_answers(answer):
    possible_answers = [answer]

    possible_answers.append(answer.replace(' ', ''))

    if '"' in answer:
        possible_answers.append(answer.replace('"', ''))

    if '\'' in answer:
        possible_answers.append(answer.replace('\'', ''))

    if answer.endswith('s'):
        possible_answers.append(answer[:-1] + 'ies')

    if answer.endswith('s'):
        possible_answers.append(answer[:-1])

    if answer.endswith('es'):
        possible_answers.append(answer[:-2])

    if answer.endswith('ing'):
        possible_answers.append(answer[:-3])

    # try adding an s at the end
    possible_answers.append(answer + 's')

    # try adding an ed at the end
    possible_answers.append(answer + 'ed')

    # try adding an ed at the end
    possible_answers.append(answer + 'ing')

    if answer.startswith('a '):
        possible_answers += [ans[2:] for ans in possible_answers]

    elif answer.startswith('an '):
        possible_answers += [ans[3:] for ans in possible_answers]

    elif answer.startswith('the '):
        possible_answers += [ans[4:] for ans in possible_answers]

    if answer.startswith('to '):
        possible_answers += [ans[2:] for ans in possible_answers]

    permute = []
    for ans in possible_answers:
        permute += ['a ' + ans, 'an ' + ans, 'the ' + ans, 'to ' + ans]

    possible_answers += permute
    return possible_answers


def random_clue(prev_clues):
    formatted_regex = [ bson.Regex.from_native(re.compile(cat)) for cat in config.ACCEPTED_CATEGORIES ]
    for index in range(len(formatted_regex)):
        formatted_regex[index].flags ^= re.UNICODE

    while True:
        clue = list(clues_collection.aggregate([
                                                {
                                                    '$match': {
                                                        'value': { '$lte': config.MAX_CLUE_VAL, '$gt': 1 },
                                                        'category': { '$in': formatted_regex },
                                                        'air_date': { '$gt': config.MIN_DATE }
                                                    },
                                                },
                                                {
                                                    '$sample': { 'size': 1 }
                                                }
                                            ]))[0]

        print('possible clue:', clue['clue'])

        if prev_clues is None:
            return clue

        if clue['_id'] in prev_clues:
            continue

        # only word characters and spaces in answer
        if re.search(r'[^a-zA-Z0-9_ ]', clue['answer']):
            continue

        # no html in clues
        if '<' in clue['clue'] or '>' in clue['clue']:
            continue

        print('selected clue:', clue['clue'])
        return clue


def pp_clue(clue):
    comments = ""
    if clue.get('comments'):
        comments = f"With this clue: {clue['comments'].split(':')[1][:-1]}  \n"

    return f"The category is `{clue['category']}` for `${clue['value']}`:  \n" \
           f"{comments}" \
           f"**{clue['clue']}**"


def special_commands(message, room_entry):
    if message.text == '.clue':
        return pp_clue(room_entry['currentClue'])

    if message.text == '.leaderboard':
        leaderboard = [room_entry['users'][entry] for entry in room_entry['users']]

        leaderboard = sorted(leaderboard, key=lambda user: user['score'], reverse=True)

        text = f'```\n{"Name:": <20}{"Score:": <10}Accuracy:\n'
        for user in leaderboard:
            try:
                acc = int(user['totalRight'] / user['totalGuesses'] * 100)
                acc = str(acc) + '%'
            except KeyError:
                acc = 'N/A'

            text += f'{user["name"]: <20}{user["score"]: <10}{acc}\n'
        text += '```'

        return text

    if message.text == '.skip':
        if message.roomType == 'group':
            if not 'skipAttempt' in room_entry:
                newvalues = {
                    '$set': {
                        'skipAttempt': message.personId,
                    }
                }

                query = {
                    "roomId": message.roomId,
                }

                rooms_collection.update_one(query, newvalues)

                return 'Skip attempt started. Need another vote to proceed!'

            if 'skipAttempt' in room_entry:
                if room_entry['skipAttempt'] == message.personId:
                    return 'Another person besides you must vote to skip.'

        prev_clues = room_entry['previousClues'] \
                     + [room_entry['currentClue']['_id']] \
                     if 'previousClues' in room_entry else [room_entry['currentClue']['_id']]

        if len(prev_clues) > config.PREV_CLUE_CACHE:
            prev_clues = prev_clues[-config.PREV_CLUE_CACHE:]

        clue = random_clue(prev_clues)

        text = f"The correct answer for **{room_entry['currentClue']['clue']}** is: `{room_entry['currentClue']['answer']}`\n\n" \
               + pp_clue(clue)

        query = {
            "roomId": message.roomId
        }

        newvalues = {
            '$set': {
                'currentClue': clue,
            },
            '$unset': {
                'skipAttempt': message.personId,
            }
        }

        rooms_collection.update_one(query, newvalues)

        print(newvalues)
        return text


    text = '`.help` shows this output  \n' \
           '`.clue` repeats the clue  \n' \
           '`.leaderboard` displays the leaderboard  \n' \
           '`.skip` skips the clue. no points recorded  \n' \

    return text


def new_game(room):
    clue = random_clue(None)
    entry = {
        'roomId': room.id,
        'roomName': room.title,
        'users': {},
        'currentClue': clue
    }

    rooms_collection.insert_one(entry)

    text = f'Welcome to Jeopardy!  \n' \
           + pp_clue(clue)

    return text


def right_answer(message, person, room_entry):
    user = room_entry['users'].get(message.personId, {})
    score = user.get('score', 0)
    totalGuesses = user.get('totalGuesses', 0)
    totalRight = user.get('totalRight', 0)

    score += room_entry['currentClue']['value']
    totalGuesses += 1
    totalRight += 1

    prev_clues = []
    if 'previousClues' in room_entry:
        prev_clues = room_entry['previousClues'] + [room_entry['currentClue']['_id']]
    else:
        prev_clues = [room_entry['currentClue']['_id']]

    if len(prev_clues) > config.PREV_CLUE_CACHE:
        prev_clues = prev_clues[-config.PREV_CLUE_CACHE:]

    clue = random_clue(prev_clues)

    query = {
        "roomId": message.roomId
    }

    newvalues = {
        '$set': {
            'currentClue': clue,
            'previousClues': prev_clues,
            f'users.{message.personId}': {
                'name': f'{person.displayName}',
                'score': score,
                'totalGuesses': totalGuesses,
                'totalRight': totalRight
            }
        },
        '$unset': {
            'skipAttempt': message.personId,
        }
    }

    rooms_collection.update_one(query, newvalues)

    print(newvalues)

    text = f"{random.choice(config.RIGHT_TEXT)}  \n" \
           f"`${room_entry['currentClue']['value']}` for {person.firstName}!\n\n" \
           + pp_clue(clue)

    return text


def wrong_answer(message, person, room_entry, closeness):
    text = f"{random.choice(config.WRONG_TEXT) if closeness < 80 else random.choice(config.CLOSE_TEXT)}\n\n" \
        f"Subtract `${room_entry['currentClue']['value']}` from {person.firstName}"

    user = room_entry['users'].get(message.personId, {})
    score = user.get('score', 0)
    totalGuesses = user.get('totalGuesses', 0)
    totalRight = user.get('totalRight', 0)

    score -= room_entry['currentClue']['value']
    totalGuesses += 1

    query = {
        "roomId": message.roomId
    }

    newvalues = {
        '$set': {
            f'users.{message.personId}': {
                'score': score,
                'totalGuesses': totalGuesses,
                'totalRight': totalRight,
                'name': f'{person.displayName}'
            }
        }
    }

    rooms_collection.update_one(query, newvalues)

    return text

WORKIN_ON = {}

def tick(message, room, person):
    # print(message)
    # print(room)
    # print(person)
    try:
        room_entry = rooms_collection.find_one({'roomId': room.id})
        message.text = format_text(message.text)
        what_to_send = None

        print('Workin on: ', WORKIN_ON)
        if WORKIN_ON.get(room.id, {}).get(person.id):
            print('Thread already working on this')
            return
        else:
            if not WORKIN_ON.get(room.id):
                WORKIN_ON[room.id] = {}
            WORKIN_ON[room.id][person.id] = True

        # if no room entry in db, start a new game
        if not room_entry:
            resp = new_game(room)

        # else it's an ongoing game
        else:
            answer = room_entry['currentClue']['answer'].lower()
            possible_answers = get_possible_answers(answer)
            print('entered text:', message.text)
            print('answer:', possible_answers)

            if message.text.startswith('.'):
                resp = special_commands(message.text, room_entry)

            elif message.text in possible_answers:
                resp = right_answer(message, person, room_entry)

            else:
                seq = difflib.SequenceMatcher(None, message.text, answer)
                closeness = seq.ratio() * 100

                resp = wrong_answer(message, person, room_entry, closeness)

        WEBEX.api.messages.create(
            roomId = room.id,
            markdown = resp
        )

        del WORKIN_ON[room.id][person.id]

    except Exception as e:
        tb = traceback.format_exc()

        # create and reply to the message sent by a user
        WEBEX.api.messages.create(
            roomId = room.id,
            markdown = 'ERROR! I need help!:  \n```  \n{}```'.format(tb),
        )
        print('ERROR!!!')
        print(tb)

WEBEX = Webex(access_token=BEARER, post_handler=tick)
WEBEX.run()