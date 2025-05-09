""" import pyttsx3
engine = pyttsx3.init()

engine.setProperty('rate', 250)     # setting up new voice rate
engine.setProperty('volume',1.0)    # setting up volume level  between 0 and 1

voices = engine.getProperty('voices')
for voice in voices:
    #engine.setProperty('voice', voices[0].id)  #changing index, changes voices. 0 for male 1 for female
    engine.setProperty('voice', voices[0].id) 
    engine.say('The quick brown fox jumped over the lazy dog.')
engine.runAndWait()
"""

"""Saving Voice to a file"""
# On linux make sure that 'espeak' and 'ffmpeg' are installed
# engine.save_to_file('Hello World', 'test.mp3')
# engine.runAndWait()

# Check available languages for the tts library on your device
import pyttsx3
engine = pyttsx3.init()
for v in engine.getProperty("voices"):
    print(v.id, v.name)