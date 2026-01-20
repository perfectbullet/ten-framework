import json, base64
import paho.mqtt.client as mqtt
import time

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("[A] Connected to broker")
        client.subscribe(TOPIC_SUB)
        print(f"[A] Subscribed to {TOPIC_SUB}")
    else:
        print(f"[A] Connection failed: {rc}")

def on_message(client, userdata, msg):
    print(f"[A] Received message on '{msg.topic}': {msg.payload.decode()}")


if __name__ == '__main__':

    #install "pip install paho-mqtt"
    BROKER = "192.168.8.127"
    PORT = 1883
    TOPIC_SUB = "ue/state"  # 订阅状态
    TOPIC_PUB = "ue/command"  # 发布命令

    client = mqtt.Client(client_id="ClientA")
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(BROKER, PORT, keepalive=30)

    # non-blocking loop
    client.loop_start()

    wav_path = r"D:\data\audios\post_0.wav"

    # 发送一些命令
    for i in range(5000):
        msg = f"command {i}"

        with open(wav_path, "rb") as f:
            audio_bytes = f.read()

        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        msg_audio = json.dumps({
            "type": "audio",
            "data": audio_b64,
            "extra": {"filename": "sound.wav"}
        })
        client.publish("ue/messages", msg_audio)

        # ===== 发送命令 =====
        msg_cmd = json.dumps({
            "type": "command",
            "data": "pause",
        })
        client.publish("ue/messages", msg_cmd)

        print(f"[A] Sent: {msg}")
        time.sleep(3)

    client.loop_stop()
    client.disconnect()
