from flask import Flask, jsonify, request, render_template, Response
from flask_cors import CORS
from flask_debugtoolbar import DebugToolbarExtension
import jira.client
from jira.client import JIRA
import wincertstore
import os
import json
import xml.etree.ElementTree as ET
import datetime
from gevent.pywsgi import WSGIServer
from multiprocessing import Process
import time

from MultiProgress import ProcessWrapper
from Logger import Loggers

from Project_Info import UpdateProjectList,GetProjectsInfo,UpdateProjectsInfo,ParseFileFullName,GetFullFileNamesInFolder,GetProjectsFromFile,GetDataFile,GetExcludedProjects,UpdateProjectDict,SaveProjectsDataDictionary
from SavedDataHandling import GetSavedDictionaryWithWorklogs
import Project_Info
from Globals import GetProjectRootFolder

import Globals
from Globals import CacheData
from Globals import JiraWrapper
from Globals import InputDataDict
from Globals import ExecutiveProcesses
from Globals import DataTypes
from Globals import ProjectListUpdated
from Globals import AuthorizationDataFile
from Globals import ProjectsDataFile
from Globals import JIRAServer


app = Flask(__name__)
CORS(app)


class JIRA_Wrapper:
    def __init__(self,JIRA_Server,AuthorizationDataFileNameInCurrentFolder):
        self.JIRA_Server=JIRA_Server
        self.AuthorizationDataFileNameInCurrentFolder = AuthorizationDataFileNameInCurrentFolder
        self.jira = self.GetJIRA(self.JIRA_Server,self.AuthorizationDataFileNameInCurrentFolder)

    def __getstate__(self): #For Pickling
        d = self.__dict__.copy()
        del d['jira']
        return d

    def __setstate__(self, d): #For Unpickling
       self.__dict__.update(d)
       self.__dict__.update({'jira':self.GetJIRA(d['JIRA_Server'],d['AuthorizationDataFileNameInCurrentFolder'])})

    def GetAuthInfo(self,RelativeNameOfFileInCurrentFolder):
        CurrentPath=os.path.dirname(os.path.dirname(os.path.dirname(__file__))) #To get __file__.parent.parent directory
        AuthFileFullName = os.path.join(CurrentPath,RelativeNameOfFileInCurrentFolder).replace("\\","/")
        XMLTree=ET.parse(AuthFileFullName)
        XMLRoot=XMLTree.getroot()
        UserName=XMLRoot.find("username").text
        UserPassword=XMLRoot.find("password").text
        return UserName,UserPassword

    def GetJIRA(self,JIRA_Server,AuthorizationDataFileNameInCurrentFolder):
        certfile = wincertstore.CertFile()
        certfile.addstore("CA")
        certfile.addstore("ROOT")
        options = {'server': JIRA_Server,'verify':certfile.name}
        UserName,UserPassword = self.GetAuthInfo(AuthorizationDataFileNameInCurrentFolder)
        return JIRA(options,basic_auth=(UserName,UserPassword))

def GetQueriesForInputData(Parametersdict):
    jql="" #Request in JIRA Query Language
    jqls=[]

    UpdateParamsWithAllKeys(Parametersdict,["StartDates","EndDates","Users","Projects"])

    if len(Parametersdict["StartDates"])>0:
        for i in range(len(Parametersdict["StartDates"])):
            jql=""
            jql=jql+'worklogDate >= ' + Parametersdict["StartDates"][i] #Jira API selects worklog date in local time zone
            jql=jql+' and '
            jql=jql+'worklogDate <= ' + Parametersdict["EndDates"][i] #Jira API selects worklog date in local time zone
            jqls.append(jql)

    jql=""
    if len(Parametersdict["Projects"])>0:
        jql=jql+'labels in ('
        for i in range(len(Parametersdict["Projects"])):
            if i == 0:
                jql=jql+'"'+Parametersdict["Projects"][i]+'"'
            else:
                jql=jql+","+'"'+Parametersdict["Projects"][i]+'"'
        jql=jql+')'

    if len(Parametersdict["Projects"])>0 and len(Parametersdict["Users"])>0:
        jql=jql+' and '

    if len(Parametersdict["Users"])>0:
        jql=jql+'worklogAuthor in ('
        for i in range(len(Parametersdict["Users"])):
            if i == 0:
                jql=jql+'"'+Parametersdict["Users"][i]+'"'
            else:
                jql=jql+","+'"'+Parametersdict["Users"][i]+'"'
        jql=jql+')'

    if jql !="":
        if len(jqls) == 0:
            jqls.append(jql)
        else:
            for i in range(len(jqls)):
                jqls[i]=jqls[i]+' and '
                jqls[i]=jqls[i]+jql

    for i in range(len(jqls)):
        if jqls[i] != "":
            jqls[i]=jqls[i]+' and '
            jqls[i]=jqls[i]+'timespent > 0'

    return jqls

def ReadInputData(Request):
    global InputDataDict

    if Request.method == "POST":
        data = "POST_" + Request.form["RequestParameters"]
    elif Request.method == "GET":
        data = Request.args.get("RequestParameters")

    InputDataDict=json.loads(data)

def GetNewParams(DataType='Online'):
    global CacheData
    global InputDataDict

    KeyList=ParamsToKeys(InputDataDict)
    NewKeyList=GetNewKeyList(KeyList,DataType)
    NewInputParams=KeyListToInputParams(NewKeyList)

    if len(NewInputParams)>0:
        CacheData[DataType]['RequestData'] = True
        print("New parameters received")

    return NewInputParams,NewKeyList

def UpdateParamsWithAllKeys(Params,KeyList):
    for i in range(len(KeyList)):
        if KeyList[i] not in Params:
            Params.update({KeyList[i]:[]})

def KeyListToInputParams(KeyList): #KeyList - list of dictionaries
    InputParams={}
    ValueFound=False

    for i in range(len(KeyList)):
        for k,v in KeyList[i].items():
            if k in InputParams:
                ValueFound=False
                for j in range(len(InputParams[k])):
                    if InputParams[k][j] == v:
                        ValueFound=True
                        break
                if ValueFound != True:
                    InputParams[k].append(v)
            else:
                InputParams.update({k:[v]})

    return InputParams

def GetNewKeyList(KeyList,DataType='Online'):
    global CacheData
    NewKeyList=[]
    KeyFound=False

    for i in range(len(KeyList)):
        KeyFound=False
        for j in range(len(CacheData[DataType]['AlreadyRequestedKeys'])):
            if KeyList[i] == CacheData[DataType]['AlreadyRequestedKeys'][j]:
                KeyFound=True
                break
        if KeyFound != True:
            NewKeyList.append(KeyList[i])

    return NewKeyList

def ParamsToKeys(Parametersdict):
    Dates=[]
    DatesDct={}
    Params=[] #Matrix - 1st dimension - 3 elements; 2nd dimension - List of elements from Parameters dictionary
    KeyList=[]#List of Dictionaries
    DictKeys=[]
    Counter=0
    ParamDict={}

    for i in range(len(Parametersdict["StartDates"])):
        DatesDct={"StartDates":Parametersdict["StartDates"][i]}
        DatesDct.update({"EndDates":Parametersdict["EndDates"][i]})
        Dates.append(DatesDct)

    if len(Dates)>0:
        DictKeys.append('Dates')
        Params.append(Dates)
    if len(Parametersdict["Users"])>0:
        DictKeys.append('Users')
        Params.append(Parametersdict["Users"])
    if len(Parametersdict["Projects"])>0:
        DictKeys.append('Projects')
        Params.append(Parametersdict["Projects"])
    ParamsToKeysRec(Counter,Params,KeyList,ParamDict,DictKeys)

    return KeyList

def ParamsToKeysRec(Counter,Params=[],KeyList=[],ParamDict={},DictKeys=[]):
    Dct={}
    for i in range(len(Params[Counter])):
        Dct=ParamDict.copy()
        if DictKeys[Counter] == 'Dates':
            Dct.update({"StartDates":Params[Counter][i]["StartDates"]})
            Dct.update({"EndDates":Params[Counter][i]["EndDates"]})
        else:
            Dct.update({DictKeys[Counter]:Params[Counter][i]})
        if len(Params)>Counter+1:
            ParamsToKeysRec(Counter+1,Params,KeyList,Dct,DictKeys)
        else:
            KeyList.append(Dct)

def CheckRequestPeriodIsOver(CurrentDate,NumberOfDaysInPeriod=1,DataType='Online'):
    global CacheData
    global ProjectListUpdated

    DateDifference=CurrentDate-CacheData[DataType]['LastOutputDataDate']
    print('DateDifference',DateDifference)
    if DateDifference.days >= NumberOfDaysInPeriod:
        CacheData[DataType]['AlreadyRequestedKeys'].clear()
        CacheData[DataType]['LastOutputData'].clear()
        CacheData[DataType]['RequestData'] = True
        Project_Info.AllProjectsDataUpdated=False
        Project_Info.AlreadyRequestedProjects.clear()
        ProjectListUpdated=False
        print('Request period is over. Data will be requested')

def GetDictionaryWithWorklogs(Parametersdict,DataType='Online',OtherJiraWrapper=''):
    global CacheData
    global JiraWrapper
    jqls=[]

    if OtherJiraWrapper != '':
        JW = OtherJiraWrapper
    else:
        JW = JiraWrapper

    print('Parametersdict',Parametersdict)

    NewIssuesStartID=len(CacheData[DataType]['LastOutputData'])
    jqls=GetQueriesForInputData(Parametersdict)
    for i in range(len(jqls)):
        print('jqls[i]',jqls[i])
        issues = JW.jira.search_issues(jqls[i],maxResults=1000,json_result=True,fields='labels,environment,worklog,summary,status,issuelinks,parent,subtasks')
        #print(issues["issues"])
        #Append worklogs requested via method "worklogs(issueid)" in case of number of retrieved worklogs exceeds 20 (limitation in search_issues method)
        for j in range(len(issues["issues"])):
            if issues["issues"][j]["fields"]["worklog"]["total"]>issues["issues"][j]["fields"]["worklog"]["maxResults"]:
                Worklogs=JW.jira.worklogs(issues["issues"][j]["id"])
                AppendNewWorklogs(issues["issues"][j]["fields"]["worklog"]["worklogs"],Worklogs)
                issues["issues"][j]["fields"]["worklog"]["maxResults"]=len(issues["issues"][j]["fields"]["worklog"]["worklogs"])

        #AppendSavedIssuesWithStatus('Completed')
        #AppendSavedIssuesWithStatus('Done')
        CacheData[DataType]['LastOutputData'].append(issues)
    NewIssuesEndID=len(CacheData[DataType]['LastOutputData'])-1

    return NewIssuesStartID,NewIssuesEndID

def RunOtherTasks(IssuesList):
    global JiraWrapper
    global ExecutiveProcesses
    kwargs={}

    CurrentPath=GetProjectRootFolder()
    LogsFolder=os.path.join(CurrentPath,'Logs')
    if not os.path.exists(LogsFolder):
        os.mkdir(LogsFolder)

    #Wait for termination of previous processes tasks
    for ExeProcess in ExecutiveProcesses:
        if isinstance(ExeProcess, Process):
            ExeProcess.join()

    ExecutiveProcesses.clear()
    #Run Update Projects Information process
    kwargs.clear()
    kwargs.update({'ProcessID':0})#Process identifier
    kwargs.update({'Loggers':Loggers(1,'Process_'+str(kwargs['ProcessID']),LogsFolder)})#Loggers object
    kwargs.update({'JiraWrapper':JiraWrapper})#Function parameter
    kwargs.update({'IssuesList':IssuesList})#Function parameter
    kwargs.update({'ProjectsXMLDict':{}})#Function parameter
    ExecutiveProcesses.append(ProcessWrapper(ModuleName='Project_Info',FunctionName='UpdateProjectsInfo',**kwargs))
    #Run Save Projects Issues Data process
    kwargs.clear()
    kwargs.update({'ProcessID':1})#Process identifier
    kwargs.update({'Loggers':Loggers(1,'Process_'+str(kwargs['ProcessID']),LogsFolder)})#Loggers object
    kwargs.update({'IssuesList':IssuesList})#Function parameter
    ExecutiveProcesses.append(ProcessWrapper(ModuleName='JiraPythonClientObj_gevent',FunctionName='SaveIssuesForAnalysis',**kwargs))
    #Start tasks processes
    for ExeProcess in ExecutiveProcesses:
        ExeProcess.start()

def AppendNewWorklogs(IssueWorklogs=[],Worklogs=[]):
    WorklogFound=False
    NewWorklogDict={}
    UpdateAuthorDict={}

    for i in range(len(Worklogs)):
        WorklogFound = False
        for j in range(len(IssueWorklogs)):
            if Worklogs[i].id == IssueWorklogs[j]["id"]:
                WorklogFound = True
                break;
        if WorklogFound == False:
            NewWorklogDict.clear()
            NewWorklogDict.update({"id":Worklogs[i].id})
            NewWorklogDict.update({"issueId":Worklogs[i].issueId})
            NewWorklogDict.update({"timeSpentSeconds":Worklogs[i].timeSpentSeconds})
            NewWorklogDict.update({"started":Worklogs[i].started})
            UpdateAuthorDict.clear()
            UpdateAuthorDict.update({"key":Worklogs[i].updateAuthor.key})
            UpdateAuthorDict.update({"displayName":Worklogs[i].updateAuthor.displayName})
            NewWorklogDict.update({"updateAuthor":UpdateAuthorDict.copy()})
            IssueWorklogs.append(NewWorklogDict.copy())

def SaveIssuesForAnalysis(IssuesList,ProcessID,Loggers):
    ProcessLogger=Loggers.Loggers[0]['Logger']
    ProcessLogger.info('Start saving issues for analysis')
    ProjectList=[]
    #Get Folder with saved worklogs (Create this folder if it does not exist)
    CurrentPath=GetProjectRootFolder()
    WorklogsFolder=os.path.join(CurrentPath,'Worklogs')
    if not os.path.exists(WorklogsFolder):
        os.mkdir(WorklogsFolder)
    #Get files with saved worklogs
    FilesInFolder=GetFullFileNamesInFolder(WorklogsFolder)
    #Get list of projects
    ProjectsInfoList=GetProjectsInfo(CurrentPath)
    ProjectList.extend(ProjectsInfoList[i]['BudgetLabel'] for i in range(len(ProjectsInfoList)))

    #Prepare List of dictionaries for each file: {'File':'','Content':[]}}
    DataForSave=[]
    for Issues in IssuesList:
        for issue in Issues["issues"]:
            #Get file where issue has to be written
            ChangedIssueLabels=ChangeIssueLabels(issue["fields"]["labels"])
            IssueFile = GetIssueFile(WorklogsFolder,FilesInFolder,ChangedIssueLabels,ProjectList)
            #Prepare Dictionary for issue
            DataFound = False
            DataID = 0
            for i in range(len(DataForSave)):
                if DataForSave[i]['File'] == IssueFile:
                    DataFound = True
                    DataID = i
                    break
            if DataFound == False:
                DataForSave.append({'File':IssueFile,'Content':[]})
                DataID = len(DataForSave)-1
            #Append issue to the dictionary with id = DataID in list of dictionaries
            DataForSave[DataID]['Content'].append(issue)

    #Extend DataForSave by different issues from from file (by issues which were not in Issues parameter)
    for SaveData in DataForSave:
        with open(SaveData['File'],'r') as IssueJSONFile:
            JSONData = IssueJSONFile.read()
        if JSONData != '':
            JSONData=json.loads(JSONData)
            for i in range(len(JSONData)-1,-1,-1):
                for issue in SaveData['Content']:
                    if JSONData[i]['id'] == issue['id']:
                        del JSONData[i]
                        break
            SaveData['Content'].extend(JSONData)

    #Save Dictionary with issues
    for data in DataForSave:
        with open(data['File'],'w') as IssueJSONFile:
            json.dump(data['Content'],IssueJSONFile)

    ProcessLogger.info('End saving issues for analysis')



def GetIssueFile(Folder,FilesInFolder,IssueLabels,ProjectList):
    IssueFile=''
    #Get file based on issue label
    for f in FilesInFolder:
        FileInfo=ParseFileFullName(f)
        if FileInfo['FileNameWithoutExtension'] in IssueLabels:
            IssueFile = f
            break
    #Compose file based on list of projects
    if IssueFile == '':
        for p in ProjectList:
            if p in IssueLabels:
                IssueFile=p + '.json'
                IssueFile=os.path.join(Folder,IssueFile).replace("\\","/")
                break
    #Compose file based on first label
    if IssueFile == '':
        if len(IssueLabels) >= 1:
            if IssueLabels[0] != '':
                IssueFile=IssueLabels[0] + '.json'
                IssueFile=os.path.join(Folder,IssueFile).replace("\\","/")
    #Compose file for issues without label
    if IssueFile == '':
        IssueFile='Issues_without_Label.json'
        IssueFile=os.path.join(Folder,IssueFile).replace("\\","/")
    #Append file to the list of files and create file on disk
    if IssueFile not in FilesInFolder:
        FilesInFolder.append(IssueFile)
        File = open(IssueFile,'w+')
        File.close()

    return IssueFile

def ChangeIssueLabels(IssueLabels):
    ChangedIssueLabels=[]

    for IssueLabel in IssueLabels:
        ChangedIssueLabels.append(IssueLabel.replace('/','_').strip())

    return ChangedIssueLabels

def GetData(DataType):
    global JiraWrapper
    global CacheData
    global ProjectListUpdated

    NewInputParametersdict={}
    NewKeyList=[]
    CurrentDate=datetime.datetime.now().date()

    CheckRequestPeriodIsOver(CurrentDate,NumberOfDaysInPeriod=1,DataType=DataType)
    NewInputParametersdict,NewKeyList = GetNewParams(DataType)

    if ProjectListUpdated == False:
        UpdateProjectList()
        ProjectListUpdated=True
    else:
        print('Project list is up to date')

    if InputDataDict["AnalyzeSavedData"] == False:
        if CacheData[DataType]['RequestData'] == True:
            if not JiraWrapper:
                JiraWrapper=JIRA_Wrapper(JIRAServer,"data/"+AuthorizationDataFile)
            NewIssuesStartID,NewIssuesEndID=GetDictionaryWithWorklogs(NewInputParametersdict,DataType)
            if NewIssuesEndID >= NewIssuesStartID:
                RunOtherTasks(CacheData[DataType]['LastOutputData'][NewIssuesStartID:NewIssuesEndID+1])
        else:
            print("Data from JIRA is not requested. Existed Data Retrieved")
    else:
        if CacheData[DataType]['RequestData'] == True:
            GetSavedDictionaryWithWorklogs(NewInputParametersdict,DataType,StatusNames=[])
        else:
            print("Data from saved issues is not requested. Existed Data Retrieved")

    CacheData[DataType]['RequestData'] = False
    CacheData[DataType]['LastOutputDataDate'] = CurrentDate
    CacheData[DataType]['AlreadyRequestedKeys'].extend(NewKeyList)



#The following decorator can be specified instead of app.add_url_rule
#@app.route('/process_data/', methods=['GET','POST'])
def Request_Worklogs():
    global InputDataDict
    global DataTypes
    global CacheData
    DataType=''

    ReadInputData(request)
    DataType=DataTypes[int(InputDataDict["AnalyzeSavedData"])]
    GetData(DataType)

    return json.dumps(CacheData[DataType]['LastOutputData'])

def ConfirmExecutiveProcessesCompletion():
    #Wait for termination of previous processes tasks
    for ExeProcess in ExecutiveProcesses:
        if isinstance(ExeProcess, Process):
            ExeProcess.join()
    return json.dumps({'Updated':1})

def RequestAllProjects(JiraWrapper,ProcessID,Loggers,CompletedProjects):
    ProcessLogger=Loggers.Loggers[0]['Logger']
    ProcessLogger.info('Request of All Projects Started')

    ExcludedProjects=GetExcludedProjects()
    CurrentPath=GetProjectRootFolder()
    ProjectsDataFileFullName=GetDataFile(CurrentPath,ProjectsDataFile)
    ProjectsFromProjectsData,ProjectsXMLDict = GetProjectsFromFile(ProjectsDataFileFullName,ExcludedProjects,'Project')

    Counter=0
    NumberOfProjects=len(ProjectsXMLDict['Root']['Project'])
    for Project in ProjectsXMLDict['Root']['Project']:
        NewIssuesStartID,NewIssuesEndID=GetDictionaryWithWorklogs({'Projects':[Project['BudgetLabel']]},DataType='Online',OtherJiraWrapper=JiraWrapper)
        SaveIssuesForAnalysis(CacheData['Online']['LastOutputData'][NewIssuesStartID:NewIssuesEndID+1],ProcessID,Loggers)
        ProcessLogger.info('Issues of project '+str(Counter+1)+' from '+str(NumberOfProjects)+' ('+ Project['BudgetLabel']+') were saved')
        #Set Project's Completion information
        if CheckIssuesCompleted(CacheData['Online']['LastOutputData'][NewIssuesStartID:NewIssuesEndID+1]) == True:
            ProjectDict,Updated=UpdateProjectDict(ProjectDict=Project,Info={'BudgetLabel':Project['BudgetLabel']},IssuesCompletion={'AllIssuesCompleted':'X','CompletenessCheckDate':datetime.datetime.now().strftime('%d.%m.%Y')})
            CompletedProjects.append(Project['BudgetLabel'])
            ProcessLogger.info('All issues of project '+str(Counter+1)+' from '+str(NumberOfProjects)+' ('+ Project['BudgetLabel']+') are completed')
        else:
            ProjectDict,Updated=UpdateProjectDict(ProjectDict=Project,Info={'BudgetLabel':Project['BudgetLabel']},IssuesCompletion={'AllIssuesCompleted':'','CompletenessCheckDate':datetime.datetime.now().strftime('%d.%m.%Y')})
            ProcessLogger.info('Some issues of project '+str(Counter+1)+' from '+str(NumberOfProjects)+' ('+ Project['BudgetLabel']+') are not completed')
        SaveProjectsDataDictionary(ProjectsXMLDict,ProjectsDataFileFullName) #Save each change in ProjectsXMLDict
        #Set Project's info
        ProcessLogger.info('NewIssuesStartID '+str(NewIssuesStartID))
        ProcessLogger.info('NewIssuesEndID '+str(NewIssuesEndID))
        ProcessLogger.info('Length of CacheData[Online][LastOutputData] '+str(len(CacheData['Online']['LastOutputData'])))
        for i in range(NewIssuesStartID,NewIssuesEndID+1):
            ProcessLogger.info('Length of CacheData[Online][LastOutputData]['+str(i)+'][issues] '+str(len(CacheData['Online']['LastOutputData'][i]["issues"])))
            if len(CacheData['Online']['LastOutputData'][i]["issues"]) > 0:
                UpdateProjectsInfo(JiraWrapper,[{"issues":[CacheData['Online']['LastOutputData'][i]["issues"][0]]}],ProcessID,Loggers,ProjectsXMLDict)
        Counter=Counter+1
        time.sleep(20)

    #GetSavedDictionaryWithWorklogs(NewInputParametersdict,DataType='Offline',StatusNames=[])
    ProcessLogger.info('Request of All Projects Ended')

def CheckIssuesCompleted(IssuesList):
    IssuesListCompleted=True

    if len(IssuesList)==0:
        IssuesListCompleted=False

    for Issues in IssuesList:
        if len(Issues["issues"])==0:
            IssuesListCompleted=False
        else:
            for issue in Issues["issues"]:
                if issue['fields']['status']['name'] != 'Completed' and issue['fields']['status']['name'] != 'Done':
                    IssuesListCompleted=False
                    break
        if IssuesListCompleted==False:
            break

    return IssuesListCompleted


def RequestAllProjectsDataAndDefineCompleteness():
    global JiraWrapper
    global CacheData
    kwargs={}

    print('Request for all projects and completeness definition started')

    CurrentPath=GetProjectRootFolder()
    LogsFolder=os.path.join(CurrentPath,'Logs')
    if not os.path.exists(LogsFolder):
        os.mkdir(LogsFolder)

    if not JiraWrapper:
        JiraWrapper=JIRA_Wrapper(JIRAServer,"data/"+AuthorizationDataFile)

    #Run request of all projects
    kwargs.clear()
    kwargs.update({'ProcessID':3})#Process identifier
    kwargs.update({'Loggers':Loggers(1,'Process_'+str(kwargs['ProcessID']),LogsFolder)})#Loggers object
    kwargs.update({'JiraWrapper':JiraWrapper})#Function parameter
    kwargs.update({'CompletedProjects':[]})#Function parameter
    RequestAllProjectProcess=ProcessWrapper(ModuleName='JiraPythonClientObj_gevent',FunctionName='RequestAllProjects',**kwargs)
    RequestAllProjectProcess.start()
    RequestAllProjectProcess.join()

    print('LastOutputData',len(CacheData['Online']['LastOutputData']))
    print('NumberOfCompletedProjects',len(kwargs['CompletedProjects']))
    print('CompletedProjects',kwargs['CompletedProjects'])

    print('Request for all projects and completeness definition ended')

    return json.dumps({'NumberOfCompletedProjects':len(kwargs['CompletedProjects']),'CompletedProjects':kwargs['CompletedProjects']})



if __name__== "__main__" :
    app.add_url_rule(rule='/request_worklogs/',endpoint='request_worklogs',view_func=Request_Worklogs,methods=['GET','POST'])
    app.add_url_rule(rule='/project_info/',endpoint='project_info',view_func=ConfirmExecutiveProcessesCompletion,methods=['GET','POST'])
    app.add_url_rule(rule='/project_completeness/',endpoint='project_completeness',view_func=RequestAllProjectsDataAndDefineCompleteness,methods=['GET','POST'])
    http_server = WSGIServer(('0.0.0.0', Globals.PortNumber), app) #or app.run(host='0.0.0.0',port=8000)
    print('Server started at port:',Globals.PortNumber)
    try:
        http_server.serve_forever()
    except KeyboardInterrupt:
        http_server.stop()
    
