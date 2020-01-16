# -*- coding: utf-8 -*-
from multiprocessing import Process
import importlib
import inspect
import traceback

class ProcessWrapper(Process):
    def __init__(self, ModuleName,FunctionName,**FunctionKwargs):
        self.Logger = FunctionKwargs['Loggers'].Loggers[0]['Logger']
        self.ProcessID = FunctionKwargs['ProcessID']
        Module = importlib.import_module(ModuleName)
        Function = getattr(Module,FunctionName)
        Process.__init__(self,target=Function,args=self.GetArguments(Function,**FunctionKwargs))

    def GetArguments(self,Function,**kwargs):
        args=[]
        ArgNamesList = list(inspect.signature(Function).parameters.keys())
        for ArgName in ArgNamesList:
            args.append(kwargs[ArgName])
        return tuple(args)
        
    def run(self):
        self.Logger.info('Process '+str(self.ProcessID)+' started**************************************')
        try:
            Process.run(self)
        except Exception as e:
            self.Logger.info(traceback.format_exc().strip())
            self.Logger.info('Process '+str(self.ProcessID)+' ended with errors****************************')
        else:
            self.Logger.info('Process '+str(self.ProcessID)+' ended without errors*************************')
            