from constants_client import *
import pika
import json
import time
import sys
import argparse
import os.path as check_file
from rabbit import *

class Client():
    def __init__(self):
        self.project_id = None
        self.instance_list = list()
        self.message_for_dashboard = None
        self.message_for_scaler = None
        self.rabbit_conn = RabbitAgent()

        self.__init_slice_params()


    def __init_slice_params(self):
        with open(IS_SPACE_CONFIG_PATH, 'r') as project_file:
            raw_text = project_file.read()
            params = json.loads(raw_text)['cloud']
        self.project_id = params['project_id']
        for item in params['vnf_list']:
            if item['image'] == VNF_IMAGE_PROCESSING:
                self.instance_list.append(item['name'])


    def get_slice_status(self):
        call_response = None
        call_dict = dict()
        call_dict["command"] = "get_project_status"
        call_dict["host"] = RABBIT_SCALER_QUEUE
        call_dict["parameters"] = [self.project_id]

        response_call = self.rabbit_conn.call(RABBIT_SCALER_QUEUE, call_dict)

        print response_call['result']
        return response_call['result']


    def send_client_request(self, action="stop", 
                            list_instance=["dummy_instance"], 
                            window_time=DEFAULT_WINDOW_TIME, 
                            path_tosca=None):
        
        message_dict = dict()
        message_dict["action"] = action
        message_dict["instance"] = list_instance
        message_dict["time"] = window_time
        message_dict["project_id"] = self.project_id

        message_dict['min_memory_usage'] = 0
        message_dict['max_memory_usage'] = 0
        message_dict['min_vcpu_usage'] = 0
        message_dict['max_vcpu_usage'] = 0

        print message_dict
        self.rabbit_conn.send_message(RABBIT_CLIENT_QUEUE, json.dumps(message_dict))


def main():
    client = Client()
    for i in range(2):
        client.get_slice_status()

    client.send_client_request(action='stop', list_instance=['testscale'])
    client.send_client_request(action='start', list_instance=['testscale'])
    time.sleep(120)
    client.send_client_request(action='stop', list_instance=['testscale'])

if __name__ == "__main__":
    main()
