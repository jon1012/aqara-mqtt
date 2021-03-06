import logging
import time
import threading
import os
import json

#mine
import mqtt
import yamlparser
from xiaomihub import XiaomiHub

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__)

def process_gateway_messages(gateway, client):
    while True:
        try: 
            packet = gateway._queue.get()
            _LOGGER.debug("data from queuee: " + format(packet))

            sid = packet.get("sid", None)
            model = packet.get("model", "")
            data = packet.get("data", "")

            if (sid != None and data != ""):
                data_decoded = json.loads(data)
                client.publish(model, sid, data_decoded)
            gateway._queue.task_done()
        except Exception as e:
            _LOGGER.error('Error while sending from gateway to mqtt: ', str(e))

def read_motion_data(gateway, client, polling_interval, polling_models):
    first = True
    while True:
        try:
            for device_type in gateway.XIAOMI_DEVICES:
                devices = gateway.XIAOMI_DEVICES[device_type]
                for device in devices:
                    model = device.get("model", "")
                    if (model not in polling_models):
                        continue
                    sid = device['sid']

                    sensor_resp = gateway.get_from_hub(sid)
                    if (sensor_resp == None):
                        continue;
                    if (sensor_resp['sid'] != sid):
                        _LOGGER.error("Error: Response sid(" + sensor_resp['sid'] + ") differs from requested(" + sid + "). Skipping.")
                        continue;

                    data = json.loads(sensor_resp['data'])
                    state = data.get("status", None)
                    short_id = sensor_resp['short_id']
                    if ( device['data'] != data or first):
                        device['data'] = data
                        _LOGGER.debug("Polling result differs for " + str(model) + " with sid(First: " + str(first) + "): " + str(sid) + "; " + str(data))
                        client.publish(model, sid, data)
            first = False
        except Exception as e:
            _LOGGER.error('Error while sending from mqtt to gateway: ', str(e))
        time.sleep(polling_interval)

def process_mqtt_messages(gateway, client):
    while True:
        try: 
            data = client._queue.get()
            _LOGGER.debug("data from mqtt: " + format(data))

            sid = data.get("sid", None)
            values = data.get("values", dict())

            resp = gateway.write_to_hub(sid, **values)
            client._queue.task_done()
        except Exception as e:
            _LOGGER.error('Error while sending from mqtt to gateway: ', str(e))

if __name__ == "__main__":
    _LOGGER.info("Loading config file...")
    config=yamlparser.load_yaml('config/config.yaml')
    gateway_pass = yamlparser.get_gateway_password(config)
    polling_interval = config['gateway'].get("polling_interval", 2)
    polling_models = config['gateway'].get("polling_models", ['motion'])

    _LOGGER.info("Init mqtt client.")
    client = mqtt.Mqtt(config)
    client.connect()
    #only this devices can be controlled from MQTT
    client.subscribe("gateway", "+", "+", "set")
    client.subscribe("gateway", "+", "write", None)
    client.subscribe("plug", "+", "status", "set")

    gateway = XiaomiHub(gateway_pass)
    t1 = threading.Thread(target=process_gateway_messages, args=[gateway, client])
    t1.daemon = True
    t1.start()

    t2 = threading.Thread(target=process_mqtt_messages, args=[gateway, client])
    t2.daemon = True
    t2.start()

    t3 = threading.Thread(target=read_motion_data, args=[gateway, client, polling_interval, polling_models])
    t3.daemon = True
    t3.start()

    while True:
        time.sleep(10)
