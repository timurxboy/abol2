import pika
import os
import json


def send_message(event_type, image_data):
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=os.getenv('RABBITMQ_HOST')))
    channel = connection.channel()

    channel.queue_declare(queue='image')

    message = {
        'event': event_type,
        'image': image_data,
    }

    channel.basic_publish(
        exchange='',
        routing_key='image',
        body=json.dumps(message)
    )

    connection.close()
