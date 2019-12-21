import requests

class TeamsApi(object):
    def __init__(self, bearer):
        self.bearer = bearer
        self.headers = {"Authorization": "Bearer {}".format(self.bearer)}

    def get_message(self, message_id):
        """Calls message api to get text based on message_id"""
        res = requests.get(url="https://api.ciscospark.com/v1/messages/{}".format(message_id),
                           headers=self.headers)

        print(res.json())
        text = res.json()['text']

        return text


    def send_message(self, text, room_id):
        """Sends message to api based on markdown and room_id"""
        res = requests.post(url="https://api.ciscospark.com/v1/messages",
                            headers=self.headers,
                            data={
                                "text": text,
                                "roomId": room_id
                            })

        return res


    def get_room_name(self, room_id):
        """Calls room api to get room name based on room_id"""
        res = requests.get(url="https://api.ciscospark.com/v1/rooms/{}".format(room_id),
                           headers=self.headers)

        room_name = res.json()['title']

        return room_name


    def get_person_name(self, person_id):
        """Calls room api to get person name based on personId"""
        res = requests.get(url="https://api.ciscospark.com/v1/people/{}".format(person_id),
                           headers=self.headers)

        print(res.json())
        name = res.json()['firstName']

        return name