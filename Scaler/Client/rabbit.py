from constants_rabbit import *
import pika
import json
import time

class RabbitAgent():
    def __init__(self):
        self.response = None
        self.credentials = pika.PlainCredentials(username=RABBIT_USER, password=RABBIT_PASSWD)
        self.parameters = pika.ConnectionParameters(RABBIT_IP, RABBIT_PORT, '/', self.credentials, socket_timeout=60)
        self.connection = pika.BlockingConnection(self.parameters)
        self.channel = self.connection.channel()

        self.channel.queue_declare(queue=RABBIT_SCALER_QUEUE)

        result = self.channel.queue_declare(exclusive=True)
        self.queue_name = result.method.queue

        self.channel.basic_consume(self.on_response, no_ack=True,
                                   queue=self.queue_name)

    def delete_conn(self):
        self.channel.queue_delete(queue=self.queue_name)
        self.connection.close()
        self.channel = None
        self.connection = None
        self.parameters = None
        self.credentials = None

    def on_response(self, ch, method, props, body):
        self.response = json.loads(body)

    def call(self, host, message_dict):
        self.response = None
        self.channel.basic_publish(exchange='',
                                   routing_key=host,
                                   properties=pika.BasicProperties(
                                         reply_to = self.queue_name,
                                         ),
                                   body=json.dumps(message_dict))
        while self.response is None:
            self.connection.process_data_events()
            time.sleep(0.5)
        return (self.response)
    
    def send_message(self, queue, message):
        self.channel.basic_publish(exchange='',
                                   routing_key=queue,
                                   body=message)


class RabbitClient():
    def __init__(self):
    	self.response = None
        self.credentials = pika.PlainCredentials(username=RABBIT_USER, password=RABBIT_PASSWD)
        self.parameters = pika.ConnectionParameters(RABBIT_IP, RABBIT_PORT, '/', self.credentials, socket_timeout=60)
        self.connection = pika.BlockingConnection(self.parameters)
        self.channel = self.connection.channel()
        
        self.channel.queue_declare(queue=RABBIT_CLIENT_QUEUE)


    def read_client_queue(self):
        self.response = None
        result = self.channel.basic_get(no_ack=True, queue=RABBIT_CLIENT_QUEUE)
        if result[2] is not None:
            self.response = json.loads(result[2])


def main():
    rabbit = Rabbit()


if __name__ == "__main__":
    main()
