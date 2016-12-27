import json
import Queue
import base64
import os
from os.path import basename
from twisted.internet import ssl, reactor
from watson_developer_cloud import TextToSpeechV1

from autobahn.twisted.websocket import connectWS
from sttClient import Utils, WSInterfaceFactory, WSInterfaceProtocol


def text_to_speech(text, file_path):
    """
    Convert given text to speech audio file saved in given path.
    """
    try:
        with open('auth.json') as authfile:
            auth_data = json.load(authfile)
            username = auth_data['tts']['username']
            password = auth_data['tts']['password']
    except:
        raise
    tts = TextToSpeechV1(
        username=username,
        password=password
    )
    voice = 'en-US_MichaelVoice'
    accept = 'audio/wav'
    with open(file_path, 'wb') as audio_file:
        audio_file.write(
            tts.synthesize(
                text, voice=voice, accept=accept
            )
        )
    return file_path


def speech_to_text(
    file_name, output_dir='output', opt_out=False,
    tokenauth=None, auth_file='auth.json',
    model='en-US_BroadbandModel', content_type='audio/wav',
    threads=1
):
    """
    Convert given audio file to text.
    """
    # logging
    # log.startLogging(sys.stdout)

    # add audio files to the processing queue
    q = Queue.Queue()
    file_number = 0
    q.put((file_number, file_name))

    hostname = "stream.watsonplatform.net"
    headers = {}
    if (opt_out is True):
        headers['X-WDC-PL-OPT-OUT'] = '1'

    try:
        with open(auth_file) as authfile:
            auth_data = json.load(authfile)
            username = auth_data['stt']['username']
            password = auth_data['stt']['password']
    except:
        raise
    # authentication header
    if tokenauth:
        headers['X-Watson-Authorization-Token'] = (
            Utils.getAuthenticationToken(
                "https://" + hostname, 'speech-to-text',
                username, password))
    else:
        string = username + ":" + password
        headers["Authorization"] = "Basic " + base64.b64encode(string)

    # create a WS server factory with our protocol
    url = "wss://" + hostname + "/speech-to-text/api/v1/recognize?model=" \
        + model
    summary = {}
    factory = WSInterfaceFactory(q, summary, output_dir, content_type,
                                 model, url, headers, debug=False)
    factory.protocol = WSInterfaceProtocol

    for i in range(min(int(threads), q.qsize())):

        factory.prepareUtterance()

        # SSL client context: default
        if factory.isSecure:
            context_factory = ssl.ClientContextFactory()
        else:
            context_factory = None
        connectWS(factory, context_factory)

    reactor.run()

    value = summary[0]
    if value['status']['code'] == 1000:
        return value['hypothesis'].encode('utf-8')
    else:
        return False


def speech_to_text_with_audio(
    audio_input, output_dir='output', opt_out=False,
    tokenauth=None, auth_file='auth.json',
    model='en-US_BroadbandModel', content_type='audio/wav',
    threads=1
):
    """
    Convert given audio file to text using speech_to_text function
    and then pass the text to text_to_speech function to get a
    verified audio of the text.
    """
    text = speech_to_text(
        file_name=audio_input, output_dir=output_dir, opt_out=opt_out,
        tokenauth=tokenauth, auth_file=auth_file,
        model=model, content_type=content_type,
        threads=threads
    )
    audio_file_name = basename(audio_input)
    audio_file_output = os.path.join(output_dir, audio_file_name)
    audio_output_path = False
    if text:
        audio_output_path = text_to_speech(text, audio_file_output)
    return {'text': text, 'audio_file': audio_output_path}


if __name__ == '__main__':
    # 1. Calling Text to Speech
    # Text to speech example
    msg = 'Hello there. This is a testing.'
    audio_path = text_to_speech(msg, 'output/output.wav')
    print('\n')
    print('Audio Path:', audio_path)

    # 2. Calling Speech to Text
    # Speech to text example
    text = speech_to_text(
        file_name='recordings/2nd_Test.wav')
    print('\n')
    print('Final Text:', text)

    # 3. Calling Speech to Text with confirmed audio
    return_data = speech_to_text_with_audio(
        audio_input='recordings/2nd_Test.wav', threads=10)
    print('\n')
    print(return_data)
