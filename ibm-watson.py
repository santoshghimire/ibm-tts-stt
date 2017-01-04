import json
import Queue
import base64
import os
import argparse
from twisted.internet import ssl, reactor
from watson_developer_cloud import TextToSpeechV1

from autobahn.twisted.websocket import connectWS
from sttClient import Utils, WSInterfaceFactory, WSInterfaceProtocol


def text_to_speech(text, file_path, auth_file):
    """
    Convert given text to speech audio file saved in given path.
    """
    try:
        with open(auth_file) as authfile:
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
    outdir = os.path.dirname(file_path)
    if not os.path.exists(outdir):
        os.makedirs(outdir)
    with open(file_path, 'wb') as audio_file:
        audio_file.write(
            tts.synthesize(
                text, voice=voice, accept=accept
            )
        )
    return file_path


def speech_to_text(
    file_name, auth_file, output_dir='output', opt_out=False,
    tokenauth=None,
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
    audio_input, auth_file, output_dir='output', opt_out=False,
    tokenauth=None,
    model='en-US_BroadbandModel', content_type='audio/wav',
    threads=1, outaudiofile='output/output.wav'
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
    audio_output_path = False
    if text:
        audio_output_path = text_to_speech(
            text=text, file_path=outaudiofile, auth_file=auth_file)
    return {'text': text, 'audio_file': audio_output_path}


if __name__ == '__main__':

    # parse command line parameters
    parser = argparse.ArgumentParser(
        description=('Script to convert text to speech, speech to text '
                     'and speech to text with audio using IBM Watson API'))
    parser.add_argument(
        '-authfile', action='store', dest='authfile',
        help="Path to authentication file auth.json",
        required=True)
    parser.add_argument(
        '-function', action='store', dest='func', default='sttwa',
        choices=['tts', 'stt', 'sttwa'],
        help='Name of function: tts: Text to speech, '
        'stt: speech to text, sttwa: speech to text with audio'
    )
    parser.add_argument(
        '-text', action='store', dest='text',
        help='Text to convert to speech')
    parser.add_argument(
        '-inputaudiofile', action='store', dest='inputaudiofile',
        help='Path to audio file to convert to text')
    parser.add_argument(
        '-outaudiofile', action='store', dest='outaudiofile',
        default='output/output.wav',
        help='Path to the output audio file.')
    args = parser.parse_args()

    if args.func == 'tts':
        # 1. Calling Text to Speech
        # Text to speech example
        if not args.text:
            raise(ValueError, 'text value is required. Use -text argument.')
        audio_path = text_to_speech(
            text=args.text, file_path=args.outaudiofile,
            auth_file=args.authfile)
        print('Audio Path:', audio_path)
    elif args.func == 'stt':
        # 2. Calling Speech to Text
        # Speech to text example
        if not args.inputaudiofile:
            raise(
                ValueError,
                'inputaudiofile value is required.')
        text = speech_to_text(
            # 'recordings/2nd_Test.wav'
            file_name=args.inputaudiofile, auth_file=args.authfile)
        print('Final Text:', text)
    else:
        # 3. Calling Speech to Text with confirmed audio
        if not args.inputaudiofile:
            raise(
                ValueError,
                'inputaudiofile value is required.')
        return_data = speech_to_text_with_audio(
            audio_input=args.inputaudiofile, auth_file=args.authfile,
            outaudiofile=args.outaudiofile)
        print(return_data)
