import ssl
from websocket import ABNF
from websocket import create_connection
from queue import Queue
import threading
import traceback
import json
import time


# class for recognizer in websocket
class Funasr_websocket_recognizer:
    """
    python asr recognizer lib

    """

    def __init__(
        self,
        host="127.0.0.1",
        port="30035",
        is_ssl=True,
        chunk_size="0, 10, 5",
        chunk_interval=10,
        mode="offline",
        wav_name="default",
    ):
        """
        host: server host ip
        port: server port
        is_ssl: True for wss protocal, False for ws
        """
        try:
            if is_ssl == True:
                ssl_context = ssl.SSLContext()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                uri = "wss://{}:{}".format(host, port)
                ssl_opt = {"cert_reqs": ssl.CERT_NONE}
            else:
                uri = "ws://{}:{}".format(host, port)
                ssl_context = None
                ssl_opt = None
            self.host = host
            self.port = port

            self.msg_queue = Queue()  # used for recognized result text

            print("connect to url", uri)
            self.websocket = create_connection(uri, ssl=ssl_context, sslopt=ssl_opt)

            self.thread_msg = threading.Thread(
                target=Funasr_websocket_recognizer.thread_rec_msg, args=(self,)
            )
            self.thread_msg.start()
            chunk_size = [int(x) for x in chunk_size.split(",")]
            stride = int(60 * chunk_size[1] / chunk_interval / 1000 * 16000 * 2)
            chunk_num = (len(audio_bytes) - 1) // stride + 1

            message = json.dumps(
                {
                    "mode": mode,
                    "chunk_size": chunk_size,
                    "encoder_chunk_look_back": 4,
                    "decoder_chunk_look_back": 1,
                    "chunk_interval": chunk_interval,
                    "wav_name": wav_name,
                    "is_speaking": True,
                    "hotwords": "金属浇铸 30\n阿里巴巴 20",
                    "itn": True,
                }
            )

            self.websocket.send(message)

            print("send json", message)

        except Exception as e:
            print("Exception:", e)
            traceback.print_exc()

    # threads for rev msg
    def thread_rec_msg(self):
        try:
            while True:
                msg = self.websocket.recv()
                if msg is None or len(msg) == 0:
                    continue
                msg = json.loads(msg)
# 示例msg: {'is_final': False, 'mode': '2pass-online', 'text': '家来', 'wav_name': 'default'}
# 示例msg2：{'is_final': True, 'mue, 'mode': '2pass-offline', 'stamp_sents': [{'end': 5195, 'punc': '。', 'start': 880, 'text_seg': '欢  迎 大 家 来 体 验 达 摩 院 推 出 的 语 音 识 别 模 型', 'ts_list': [[880, 1120], [1120, 1380], [1380, 1540], [1540, 1780], [1780, 2020], [2020, 2180], [2180, 2480], [2480, 2600], [2600, 2780], [2780, 3040], [迎 大 家 来 体 验 达 摩 院 推 出 的 语 音 识 别 模 型', 'ts_list': [[880, 1120], [1120, 1380], [1380, 1540], [1540, 1780], [1780, 2020], [2020, 2180], [2180, 2480], [2480, 2600], [2600, 2780], [2780, 3040], [40], [1540, 1780], [1780, 2020], [2020, 2180], [2180, 2480], [2480, 2600], [2600, 2780], [2780, 3040], [3040, 3240], [3240, 3479], [3479, 3699], [3699, 3899], [3899, 4180], [4180, 4420], [4420, 4620], [4620, 3040, 3240], [3240, 3479], [3479, 3699], [3699, 3899], [3899, 4180], [4180, 4420], [4420, 4620], [4620, 4780], [4780, 5195]]}], 'text': '欢迎大家来体验达摩院推出的语音识别模型。', 'timestamp': '[[880,1120],[1120,1380],[1380,1540],[1540,1780],[1780,2020],[2020,2180],[2180,2480],[2480,2600],[2600,2780],[2780,3040],[3040,3240],[3240,3479],[3479,3699],[3699,3899],[3899,4180],[4180,4420],[4420,4620],[4620,4780],[4780,5195]]', 'wav_name': 'default'}
# mode： 2pass-online表示一句话还未结束 ， 2pass-offline 表示一句话结束
                self.msg_queue.put(msg)
        except Exception as e:
            print("client closed")

    # feed data to asr engine, wait_time means waiting for result until time out
    def feed_chunk(self, chunk, wait_time=0.01):
        try:
            self.websocket.send(chunk, ABNF.OPCODE_BINARY)
            # loop to check if there is a message, timeout in 0.01s
            while True:
                msg = self.msg_queue.get(timeout=wait_time)
                if self.msg_queue.empty():
                    break

            return msg
        except:
            return ""

    def close(self, timeout=1):
        message = json.dumps({"is_speaking": False})
        self.websocket.send(message)
        # sleep for timeout seconds to wait for result
        time.sleep(timeout)
        msg = ""
        while not self.msg_queue.empty():
            msg = self.msg_queue.get()

        self.websocket.close()
        # only resturn the last msg
        return msg


if __name__ == "__main__":

    print("example for Funasr_websocket_recognizer")
    import wave

    # wav_path = "/Users/zhifu/Downloads/modelscope_models/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch/example/asr_example.wav"
    wav_path = "D:/zenking_work/funasr_work/workspace/FunASR/runtime/funasr_api/asr_example.wav"
    with wave.open(wav_path, "rb") as wav_file:
        params = wav_file.getparams()
        frames = wav_file.readframes(wav_file.getnframes())
        audio_bytes = bytes(frames)

    stride = int(60 * 10 / 10 / 1000 * 16000 * 2)
    chunk_num = (len(audio_bytes) - 1) // stride + 1
    # create an recognizer
    rcg = Funasr_websocket_recognizer(
        host="192.168.8.230", port="30095", is_ssl=True, mode="2pass", chunk_size="5, 10, 5"
    )
    # loop to send chunk
    for i in range(chunk_num):

        beg = i * stride
        data = audio_bytes[beg : beg + stride]

        text = rcg.feed_chunk(data, wait_time=0.02)
        if len(text) > 0:
            print("text", text)
        time.sleep(0.05)

    # get last message
    text = rcg.close(timeout=3)
    print("text", text)
