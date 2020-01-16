# -*- coding: utf-8 -*-

import logging
import os

class Loggers:
    def __init__(self,NumberOfLogFiles,LoggersBaseName,LoggersPath):
        self.NumberOfLogFiles = NumberOfLogFiles
        self.LoggersBaseName = LoggersBaseName
        self.LoggersPath = LoggersPath
        self.Loggers=self.GetLoggers(self.NumberOfLogFiles,self.LoggersBaseName,self.LoggersPath)
    
    def __getstate__(self): #For Pickling
        d = self.__dict__.copy()
        del d['Loggers']
        return d
    
    def __setstate__(self, d): #For Unpickling
       self.__dict__.update(d)
       self.__dict__.update({'Loggers':self.GetLoggers(d['NumberOfLogFiles'],d['LoggersBaseName'],d['LoggersPath'])})
        
    def Get_Logger(self,LoggerName,FullLogFileName):
        logger = logging.getLogger(LoggerName)
        formatter = logging.Formatter('%(asctime)s PID %(process)d: %(message)s',datefmt = '%d.%m.%Y %H:%M:%S')
        fileHandler = logging.FileHandler(FullLogFileName) #Default mode = 'a'
        fileHandler.setFormatter(formatter)
        logger.setLevel(logging.DEBUG)
        logger.addHandler(fileHandler)
        return logger

    def GetLoggers(self,NumberOfLogFiles,LoggersBaseName,LoggersPath):
        Loggers=[]
        ProcessLogger={}
        for i in range(NumberOfLogFiles):
            ProcessLogger.clear()
            ProcessLogger.update({'Name':LoggersBaseName+'_Log_'+str(i)})
            ProcessLogger.update({'Logger':self.Get_Logger(ProcessLogger['Name'],os.path.join(LoggersPath,ProcessLogger['Name']+'.log'))})
            Loggers.append(ProcessLogger.copy())
        return Loggers
        
    