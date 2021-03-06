from constants import *
import sys
import os
import time
import random
import threading
from socket import *

# importing the ADC class file
from ADC128D818 import *
# importing the Transformation file
from Conversion import *
####### CUSTOMIZE ##########
DEVICE_ADDRESS = ADC_ADDRESS.LOW_LOW
##########################
#Mode selection
if MODE_SELECT == PROGRAM_MODE.PI:
    import smbus
    i2c = smbus.SMBus(1)
if MODE_SELECT == PROGRAM_MODE.PC:
    import Adafruit_GPIO.FT232H as FT232H
    FT232H.use_FT232H() # Temporarily disable FTDI serial drivers.
    ft232h = FT232H.FT232H() #Find the first FT232H device.
    i2c = FT232H.I2CDevice(ft232h, DEVICE_ADDRESS) # Create an I2C device at address.
if MODE_SELECT == PROGRAM_MODE.PC_SIMULATE_DATA:
    i2c = 0 #can't be undefined

dumpLock = threading.Lock()

class Measure(object):
    """Encapsulates all the necessary functions and attributes required for logging the current measurement:

    Attributes:
        LOG_MARK: description
        MARK_VALUE:
        LOG_EVENT:
        LOG_INFO:
        INFO_STRING:
        IS_LOGGING:
        FINISH_LOGGING:
        DUMP_FILE:
        SESSION_DIR:
        SESSION_DIR_INIT:
    Methods:
        open_session():
        dump(myStr):
    """



    def __init__(self, channels_to_measure):#one can pass i2c address here
        '''
        Initilisation goes here
        '''
        self.LOG_MARK                  = False
        self.MARK_VALUE                = 0
        self.LOG_EVENT                 = False
        self.LOG_INFO                  = False
        self.INFO_STRING               = ""
        self.IS_LOGGING                = False
        self.FINISH_LOGGING            = None
        self.DUMP_FILE                 = None
        self.SESSION_DIR               = None
        self.SESSION_DIR_INIT          = "session_"
        self.TCP_BUFF                  = 4096
        self.adc                       = adc
        self.CHANNEL_TO_MEASURE        = channels_to_measure
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR)
    # ###########################################################################################
    def open_session(self):
        session_id=1
        while os.path.exists(LOG_DIR+"/"+self.SESSION_DIR_INIT+"%03d"%(session_id)):
            session_id+=1
        self.SESSION_DIR=self.SESSION_DIR_INIT+"%03d"%(session_id)
        os.makedirs(LOG_DIR+"/"+self.SESSION_DIR)
        self.DUMP_FILE = open(LOG_DIR+"/"+self.SESSION_DIR+"/dump.log","a")
        #print self.SESSION_DIR

    # ###########################################################################################
    def dump(self, myStr):
        dumpLock.acquire()
        now = time.time()
        newStr = time.strftime("%Y_%m_%d_%H_%M_%S \t",
                time.localtime(now))+"%14.3f"%now+"\t"+myStr
        print newStr
        sys.stdout.flush()
        self.DUMP_FILE.write(newStr+"\n")
        self.DUMP_FILE.flush()
        dumpLock.release()
    ###########################################################################################
    def logging(self):
        time.sleep(0.1)
        self.dump("Start of logging thread")
        channel=0
        avg_count = 0
	reading_count = 0
        start_time=0
        finish_time=0
        start_time=time.time()
        last_time=start_time
        myFile_name = LOG_DIR+"/"+self.SESSION_DIR+"/log_"+time.strftime("%Y_%m_%d_%H_%M_%S", time.localtime(start_time))+"_power.log"# creating new file under current session directory
        self.dump("Opening file: %s"%(myFile_name))
        myFile=open(myFile_name,"a")
        myFile.write("#start time: %13.3f\t"%(start_time))
        myFile.write("\n")
        myFile.write(LOG_HEADER)
        myFile.write("\n")

        myBuffer=[]
        avg=[0.0]*self.adc.NUMBER_OF_CHANNELS
        while True:
            try:
                now=time.time()
                if ((reading_count / len(self.CHANNEL_TO_MEASURE)) % 100 == 0): #every 100 reading set, wait a bit to empty TCP buffer. sleep(0) has not worked very well?
                    time.sleep(0.001)
                if (channel==0):
                    time.sleep(0)
                    if (self.LOG_EVENT):
                        myLine="%14.3f\t%d"%(now,EVENT_TYPE.EVENT)
                        myBuffer.append(myLine)
                        self.LOG_EVENT=False
                        continue

                    if (self.LOG_MARK):
                        myLine="%14.3f\t%d\t%d"%(now,EVENT_TYPE.MARK,self.MARK_VALUE)
                        myBuffer.append(myLine)
                        self.LOG_MARK=False
                        continue

                    if (self.LOG_INFO):
                        myLine="%14.3f\t%d\t%s"%(now,EVENT_TYPE.INFO,self.INFO_STRING)
                        myBuffer.append(myLine)
                        self.LOG_INFO=False
                        continue

                    if (self.FINISH_LOGGING):
                        finish_time=now
                        myLine = "%14.3f: logged %d measurements. duration: %8.3f seconds. finishing up this log"%(now,avg_count,finish_time-last_time)
                        self.dump(myLine)
                        start_write=time.time()
                        myFile.write("\n".join(myBuffer))
                        myFile.flush()
                        self.dump("Flushing took " + str(time.time() - now) + " seconds")
                        break

                if (CHANNEL_SENSOR_MAP[channel][0] == SENSOR_TYPE.DISABLE):
                    channel=channel+1 #we need to skip the disabled channels.
                    if (channel>=self.adc.NUMBER_OF_CHANNELS):
                        channel=0
                    continue

                # new line, reading adc channel value
                raw_reading = self.adc.read_channel(channel)
                reading_count+=1 

                #convert the readings if required
                channel_data = Conversion.convert(CHANNEL_SENSOR_MAP[channel][0], raw_reading)

                ################
                myLine="%14.3f"%(now)+"\t"+str(EVENT_TYPE.MEASUREMENT)+"\t"+"%d"%(channel)+"\t"+"%6.2f"%(channel_data)
                myBuffer.append(myLine)                

                if (DEBUG_MODE):
                    avg[channel]+=channel_data
                    avg_count+=1
                    if (avg_count % (len(self.CHANNEL_TO_MEASURE)*VERBOS_AVERAGE_WINDOW) == 0):
                        myStr = "\n--- Average over last " + str(VERBOS_AVERAGE_WINDOW) + " measurements ---\n"
                        for i in range(0, self.adc.NUMBER_OF_CHANNELS):
                            if (i in self.CHANNEL_TO_MEASURE):
                                myStr += "channel " + str(i) + " " + str(avg[i] / VERBOS_AVERAGE_WINDOW) + "\n"
                        self.dump(myStr)
                        avg = [0.0] * self.adc.NUMBER_OF_CHANNELS
                        avg_count = 0

                if (reading_count >= LOG_BUFF_COUNT):
                    finish_time=now
                    start_write=time.time()
                    myLine = "%14.3f: logged %d measurements. duration: %8.3f seconds"%(now,reading_count,finish_time-last_time)
                    self.dump(myLine)
                    myFile.write("\n".join(myBuffer))
                    myFile.write("\n")
                    #myFile.flush()
                    self.dump("Emptying buffer took " + str(time.time() - start_write) + " seconds")
                    myBuffer=[]
                    last_time=finish_time
                    reading_count=0

		channel = channel+1
                if (channel >= self.adc.NUMBER_OF_CHANNELS):
                    channel = 0

            except Exception as e:
                self.dump("ERROR: some error in logging process, passing this loop: "+str(e))
                pass

        self.dump("End of logging thread here.")
        time.sleep(0)


if __name__ == '__main__':
    #create the ADC object
    # CUSTOMIZE
    adc = ADC128D818(i2c, DEVICE_ADDRESS)

    #intialize the ADC to 8 single ended inputs, external VREF, continuous  #sampling and no masked channels or interrupts
    #sampling and no masked channels or interrupts
    channels_to_measure = []
    for ch in range(adc.NUMBER_OF_CHANNELS):
        if (CHANNEL_SENSOR_MAP[ch][0] != SENSOR_TYPE.DISABLE):
            channels_to_measure.append(ch)

    #print "Channels to measure:", channels_to_measure

    # CUSTOMIZE
    adc.initialize(ADC_MODE.MODE_1, ADC_VREF.EXT, ADC_RATE.CONTINUOUS, channels_to_measure, 0)
    ##########################
    sensorLogger = Measure(channels_to_measure)#creating instance of the class object
    sensorLogger.open_session()
    sensorLogger.dump("--------------------------------------")
    sensorLogger.dump("STARTED PROGRAM")
    sensorLogger.dump("Writing logs to folder: %s"%(LOG_DIR+"/"+sensorLogger.SESSION_DIR))
    sensorLogger.dump("Make sure your constant.py file is set. MODE_SELECT, VDD, and LOG_DIR are important for logging")
    sensorLogger.dump("Currently these values are: %d, %5.3f, %s"%(MODE_SELECT, VDD, LOG_DIR))
    sensorLogger.dump("Channels to measure: "+str(channels_to_measure))

    #Here is where channels would be calibrated
    #call adc.calibrate(channel) for each channel that has an initial biased reading.
    #e.g the motors are initially off so their current
    #consumption is 0 while the PI will already be drawing current and therefore
    #can't be calibrated to account fo a zero input response
    for ch in channels_to_measure:
        if (CHANNEL_SENSOR_MAP[ch][1]): #calibrate flag
            adc.calibrate(ch)
            sensorLogger.dump("Channel %d initial reading at calibration: %f"%(ch, adc.read_bias(ch)))   
        else:
            adc.uncalibrate(ch)
            sensorLogger.dump("Channel %d initial reading: %f"%(ch, Conversion.convert(CHANNEL_SENSOR_MAP[ch][0], adc.read_channel(ch))))
            
    # CUSTOMIZE
    # uncalibrate any channel if needed
    #adc.uncalibrate(5) #this channel should be uncalibrated to read battery
    #sensorLogger.dump("Channel %d uncalibrated to 0.0"%(5))   
    adc.write_bias(5, VDD/2.0) # this channel is for pi energy, and needs to be manually calibrated
    sensorLogger.dump("Channel %d manually calibrated to %f"%(5,adc.read_bias(5)))

    ADDR = (PWR_HOST,PWR_PORT)
    serversock=socket(AF_INET,SOCK_STREAM)
    serversock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    serversock.bind(ADDR)
    serversock.listen(5)

    sensorLogger.dump("Waiting for the client to connect to IP "+PWR_HOST)
    clientsock, add = serversock.accept()
    sensorLogger.dump("Client connected")
    corrupt_flag=False
    while True:
        try: 
            sensorLogger.dump("Waiting for a command from client")
            data=clientsock.recv(sensorLogger.TCP_BUFF)
            if data=="":
                #this would happen in case the client closes and wants to reopen.
                sensorLogger.dump("There seems to be something wrong with the socket, accepting another socket")

                # we are dependent on current session, so upon losing current
                # sesssion, we should finish our measurement and wait for next one to restart
                if TCP_CLIENT_DEPENDENT==True:
                    sensorLogger.dump("TCP_CLIENT_DEPENDENCY ist True, finishing up current session...")
                    if sensorLogger.IS_LOGGING==True:
                        sensorLogger.dump("Force finishing previous measurement")
                        sensorLogger.FINISH_LOGGING=True
                        myThread.join()
                        sensorLogger.IS_LOGGING=False
                        sensorLogger.dump("Child thread is done, this session is finished")
                    clientsock, add = serversock.accept()
                    sensorLogger.open_session()
                    sensorLogger.dump("--------------------------------------")
                    sensorLogger.dump("RESTARTING SESSION")
                    sensorLogger.dump("Writing logs to folder: %s"%(LOG_DIR+"/"+sensorLogger.SESSION_DIR))
                    sensorLogger.dump("Client connected")
                # if we are not dependent on current session, we will just
                # continue measuring, and wait for a possible connection without restart
                else:
                    sensorLogger.dump("TCP_CLIENT_DEPENDENCY ist False, ignoring the disconnection...")
                    clientsock, add = serversock.accept()
                    sensorLogger.dump("--------------------------------------")
                    sensorLogger.dump("Client connected")
                    sensorLogger.dump("CONTINUING PREVIOUS SESSOIN")
                continue
            sensorLogger.dump("Data received from client:" + repr(data))
            if (corrupt_flag==True):  #last buffer contained corrupt packet that we concatinate to this one
                sensorLogger.dump("WARNING: concatinating previous corrupt packet portion to this one")
                data=corrupt_packet + data
                corrupt_flag=False
            if not (data.endswith(PACKET_END)): # now we check if the new packet is in full form
                corrupt_packet=data.split(PACKET_END)[-1]
                corrupt_flag=True
                sensorLogger.dump("WARNING: packet seems to be corrupted and does not end with signature, considering it corrupt, and will concatinate it next time. corrupted portion: "+corrupt_packet)

            for command in data[0:data.rfind(PACKET_END)].split(PACKET_END): # only looking at full packets in data, so choosing the last occurance of PACKET_END as end of string
                if command=="":
                    continue
                #sensorLogger.dump("The number for command is: %d"%(int(command[0].encode("hex"),16)))
                if int(command[0].encode("hex"),16)==PWR_Command.PWR_START and sensorLogger.IS_LOGGING==False:
                    sensorLogger.LOG_EVENT = False
                    sensorLogger.LOG_MARK = False
                    sensorLogger.FINISH_LOGGING = False
                    sensorLogger.LOG_INFO = False
                    sensorLogger.INFO_STRING = ""
                    sensorLogger.IS_LOGGING=True
                    sensorLogger.dump("Logging thread starting from main thread")
                    myThread=threading.Thread(target=sensorLogger.logging)
                    myThread.start()
                    continue

                if int(command[0].encode("hex"),16)==PWR_Command.PWR_STOP and sensorLogger.IS_LOGGING==True:
                    sensorLogger.dump("Client wants to finish logging")
                    sensorLogger.FINISH_LOGGING=True
                    myThread.join()
                    sensorLogger.IS_LOGGING=False
                    sensorLogger.dump("Child thread is done, this session is finished")

                if int(command[0].encode("hex"),16)==PWR_Command.PWR_EVENT and sensorLogger.IS_LOGGING==True:
                    sensorLogger.dump("Client wants to record an event")
                    while(sensorLogger.LOG_EVENT):
                        pass
                    sensorLogger.LOG_EVENT=True

                if int(command[0].encode("hex"),16)==PWR_Command.PWR_MARK and sensorLogger.IS_LOGGING==True:
                    sensorLogger.dump("Client wants to make a numbered mark")
                    while(sensorLogger.LOG_MARK):
                        pass
                    sensorLogger.MARK_VALUE=int(command[1:].encode("hex"), 16)
                    sensorLogger.dump("Mark is: %d"%(sensorLogger.MARK_VALUE))
                    sensorLogger.LOG_MARK=True

                if int(command[0].encode("hex"),16)==PWR_Command.PWR_INFO and sensorLogger.IS_LOGGING==True:
                    sensorLogger.dump("Client has some info to log")
                    while(sensorLogger.LOG_INFO):
                        pass
                    sensorLogger.INFO_STRING=command[1:].decode('utf-8')
                    sensorLogger.dump("Info is: %s"%(sensorLogger.INFO_STRING))
                    sensorLogger.LOG_INFO=True

        except KeyboardInterrupt:
            sensorLogger.dump("\nInterrupted by user, waiting for logging to finish.")
            if sensorLogger.IS_LOGGING==True:
                sensorLogger.FINISH_LOGGING=True
                myThread.join()
                sensorLogger.dump("Child thread done")
            sensorLogger.dump("Now exiting program")
            time.sleep(1.0)
            exit()
