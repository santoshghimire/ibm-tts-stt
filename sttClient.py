#
# Copyright IBM Corp. 2014
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

# Author: Daniel Bolanos
# Date:   2015

# coding=utf-8
import json                        # json
import threading                   # multi threading
import os                          # for listing directories
import Queue                       # queue used for thread syncronization
import sys                         # system calls
import argparse                    # for parsing arguments
import base64                      # necessary to encode in base64
                                   # according to the RFC2045 standard
import requests                    # python HTTP requests library

# WebSockets
from autobahn.twisted.websocket import WebSocketClientProtocol, \
    WebSocketClientFactory, connectWS
from twisted.python import log
from twisted.internet import ssl, reactor


class Utils:

    @staticmethod
    def getAuthenticationToken(hostname, serviceName, username, password):

        uri = hostname + "/authorization/api/v1/token?url=" + hostname + '/' \
              + serviceName + "/api"
        uri = uri.replace("wss://", "https://")
        uri = uri.replace("ws://", "https://")
        resp = requests.get(uri, auth=(username, password), verify=False,
                            headers={'Accept': 'application/json'},
                            timeout=(30, 30))
        # print resp.text
        jsonObject = resp.json()
        return jsonObject['token']


class WSInterfaceFactory(WebSocketClientFactory):

    def __init__(self, queue, summary, dirOutput, contentType, model,
                 url=None, headers=None, debug=None):

        WebSocketClientFactory.__init__(self, url=url, headers=headers)
        self.queue = queue
        self.summary = summary
        self.dirOutput = dirOutput
        self.contentType = contentType
        self.model = model
        self.queueProto = Queue.Queue()

        self.openHandshakeTimeout = 10
        self.closeHandshakeTimeout = 10

        # start the thread that takes care of ending the reactor so
        # the script can finish automatically (without ctrl+c)
        endingThread = threading.Thread(target=self.endReactor, args=())
        endingThread.daemon = True
        endingThread.start()

    def prepareUtterance(self):

        try:
            utt = self.queue.get_nowait()
            self.queueProto.put(utt)
            return True
        except Queue.Empty:
            # print "getUtterance: no more utterances to process, queue is empty!"
            return False

    def endReactor(self):

        self.queue.join()
        # print "about to stop the reactor!"
        reactor.stop()

    # this function gets called every time connectWS is called (once
    # per WebSocket connection/session)
    def buildProtocol(self, addr):

        try:
            utt = self.queueProto.get_nowait()
            proto = WSInterfaceProtocol(self, self.queue, self.summary,
                                        self.dirOutput, self.contentType)
            proto.setUtterance(utt)
            return proto
        except Queue.Empty:
            # print ("queue should not be empty, otherwise this function "
            #        "should not have been called")
            return None


# WebSockets interface to the STT service
#
# note: an object of this class is created for each WebSocket
# connection, every time we call connectWS
class WSInterfaceProtocol(WebSocketClientProtocol):

    def __init__(self, factory, queue, summary, dirOutput, contentType):
        self.factory = factory
        self.queue = queue
        self.summary = summary
        self.dirOutput = dirOutput
        self.contentType = contentType
        self.packetRate = 20
        self.listeningMessages = 0
        self.timeFirstInterim = -1
        self.bytesSent = 0
        self.chunkSize = 2000     # in bytes
        super(self.__class__, self).__init__()
        # print "contentType: " + str(self.contentType) + " queueSize: " + \
        #     str(self.queue.qsize())

    def setUtterance(self, utt):

        self.uttNumber = utt[0]
        self.uttFilename = utt[1]
        self.summary[self.uttNumber] = {"hypothesis": "",
                                        "status": {"code": "", "reason": ""}}
        self.fileJson = self.dirOutput + "/" + str(self.uttNumber) + \
                        ".json.txt"
        try:
            os.remove(self.fileJson)
        except OSError:
            pass

    # helper method that sends a chunk of audio if needed (as required
    # what the specified pacing is)
    def maybeSendChunk(self, data):

        def sendChunk(chunk, final=False):
            self.bytesSent += len(chunk)
            self.sendMessage(chunk, isBinary=True)
            if final:
                self.sendMessage(b'', isBinary=True)

        if (self.bytesSent + self.chunkSize >= len(data)):
            if (len(data) > self.bytesSent):
                sendChunk(data[self.bytesSent:len(data)], True)
                return
        sendChunk(data[self.bytesSent:self.bytesSent + self.chunkSize])
        self.factory.reactor.callLater(0.01, self.maybeSendChunk, data=data)
        return

    def onConnect(self, response):
        # print "onConnect, server connected: {0}".format(response.peer)
        pass

    def onOpen(self):
        # print "onOpen"
        data = {"action": "start", "content-type": str(self.contentType),
                "continuous": True, "interim_results": True,
                "inactivity_timeout": 600}
        data['word_confidence'] = True
        data['timestamps'] = True
        data['max_alternatives'] = 3
        # print "sendMessage(init)"
        # send the initialization parameters
        self.sendMessage(json.dumps(data).encode('utf8'))

        # start sending audio right away (it will get buffered in the
        # STT service)
        # print self.uttFilename
        f = open(str(self.uttFilename), 'rb')
        self.bytesSent = 0
        dataFile = f.read()
        self.maybeSendChunk(dataFile)
        # print "onOpen ends"

    def onMessage(self, payload, isBinary):

        if isBinary:
            # print("Binary message received: {0} bytes".format(len(payload)))
            pass
        else:
            # print(u"Text message received: {0}".format(payload.decode('utf8')))

            # if uninitialized, receive the initialization response
            # from the server
            jsonObject = json.loads(payload.decode('utf8'))
            if 'state' in jsonObject:
                self.listeningMessages += 1
                if (self.listeningMessages == 2):
                    # print "sending close 1000"
                    # close the connection
                    self.sendClose(1000)

            # if in streaming
            elif 'results' in jsonObject:
                jsonObject = json.loads(payload.decode('utf8'))
                hypothesis = ""
                # empty hypothesis
                if (len(jsonObject['results']) == 0):
                    # print "empty hypothesis!"
                    pass
                # regular hypothesis
                else:
                    # dump the message to the output directory
                    jsonObject = json.loads(payload.decode('utf8'))
                    f = open(self.fileJson, "a")
                    f.write(json.dumps(jsonObject, indent=4, sort_keys=True))
                    f.close()

                    res = jsonObject['results'][0]
                    hypothesis = res['alternatives'][0]['transcript']
                    bFinal = (res['final'] == True)
                    if bFinal:
                        print "final hypothesis: \"" + hypothesis + "\""
                        self.summary[self.uttNumber]['hypothesis'] += hypothesis
                    else:
                        print "interim hyp: \"" + hypothesis + "\""

    def onClose(self, wasClean, code, reason):

        # print("onClose")
        # print("WebSocket connection closed: {0}".format(reason), "code: ",
        #       code, "clean: ", wasClean, "reason: ", reason)
        self.summary[self.uttNumber]['status']['code'] = code
        self.summary[self.uttNumber]['status']['reason'] = reason

        # create a new WebSocket connection if there are still
        # utterances in the queue that need to be processed
        self.queue.task_done()

        if self.factory.prepareUtterance() == False:
            return

        # SSL client context: default
        if self.factory.isSecure:
            contextFactory = ssl.ClientContextFactory()
        else:
            contextFactory = None
        connectWS(self.factory, contextFactory)


# function to check that a value is a positive integer
def check_positive_int(value):
    ivalue = int(value)
    if ivalue < 1:
        raise argparse.ArgumentTypeError(
            "\"%s\" is an invalid positive int value" % value)
    return ivalue


# function to check the credentials format
def check_credentials(credentials):
    elements = credentials.split(":")
    if (len(elements) == 2):
        return elements
    else:
        raise argparse.ArgumentTypeError(
            "\"%s\" is not a valid format for the credentials " % credentials)


def stt(
    file_name, output_dir='output', opt_out=False,
    tokenauth=None, auth_file='auth.json',
    model='en-US_BroadbandModel', content_type='audio/wav',
    threads=1
):

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
            contextFactory = ssl.ClientContextFactory()
        else:
            contextFactory = None
        connectWS(factory, contextFactory)

    reactor.run()

    value = summary[0]
    if value['status']['code'] == 1000:
        # print ('Final result', value['hypothesis'].encode('utf-8'))
        return value['hypothesis'].encode('utf-8')
    else:
        # print (str(key) + ": ", value['status']['code'], " REASON: ",
        #        value['status']['reason'])
        return False


if __name__ == '__main__':
    text = stt(file_name='recordings/Test_1.wav')
    print(text)
