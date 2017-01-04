## ibm-tts-stt
A python script implementing IBM Watson Text to Speech and Speech to Text api.

## Installation
`
pip install -r requirements.txt
`

Copy the file auth_example.json to auth.json and update the credentials.


## Examples                                                                                            

Running for text to speech.

`                 
$ python ibm-watson.py -authfile auth.json -func tts -text Hello there
`

Running for speech to text.

`                 
$ python ibm-watson.py -authfile auth.json -func stt -inputaudiofile recordings/2nd_Test.wav
`

Running for speech to text.

`                 
$ python ibm-watson.py -authfile auth.json -func sttwa -inputaudiofile recordings/2nd_Test.wav
`