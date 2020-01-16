# -*- coding: utf-8 -*-

import os
import xml.etree.ElementTree as ET
import datetime
import json
import xmltodict
import dicttoxml
from xml.dom.minidom import parseString

from Globals import GetProjectRootFolder
from Globals import ExtDataFile
from Globals import ProjectsDataFile
from Globals import ProjectBudgetField
from Globals import ProjectStartDateField
from Globals import ProjectDueDateField

AllProjectsDataUpdated=False
AlreadyRequestedProjects=[]


def GetDataFile(CurrentDir,DataFileName,CreateIfNotExist=False):
    DataFileFullName=''
    
    ProjectsDataFolder=os.path.join(CurrentDir,'data')
    if os.path.exists(ProjectsDataFolder):
        DataFileFullName = os.path.join(ProjectsDataFolder,DataFileName)
        if not os.path.exists(DataFileFullName):
            if CreateIfNotExist == True:
                open(DataFileFullName, 'w+').close()
            else:
                DataFileFullName=''
        
    return DataFileFullName

def GetProjectsInfo(CurrentDir):
    ProjectsInfoList=[]
    ProjectInfo={}
    ProjectElements=[]
    
    ProjectsFileFullName=GetDataFile(CurrentDir,ProjectsDataFile)
    if ProjectsFileFullName != '':
        XMLTree=ET.parse(ProjectsFileFullName)
        XMLRoot=XMLTree.getroot()
        ProjectElements=XMLRoot.findall('Project')
        for ProjectElement in ProjectElements:
            ProjectInfo.clear()
            for Info in ProjectElement:
                if Info.tag in ['BudgetLabel','Budget','StartDate','DueDate']:
                    ProjectInfo.update({Info.tag:Info.text})
            ProjectsInfoList.append(ProjectInfo.copy())
    return ProjectsInfoList


def ParseFileFullName(FileFullName):
    FilePath = os.path.dirname(FileFullName)
    if FilePath.rfind("/") != len(FilePath)-1:
        FilePath +="/"
    FileName=FileFullName.replace(FilePath,"")
    if FileName.find("/",0,1)  >= 0:
        FileName = FileName.replace("/","",1)
    FVal=FileName.rfind(".")-len(FileName)
    FileExtension=FileName[FVal:]
    FileNameWithoutExtension=FileName[:FVal]
    return {'FileFullName':FileFullName,'FilePath':FilePath,'FileName':FileName,'FileNameWithoutExtension':FileNameWithoutExtension,'FileExtension':FileExtension}


def GetIssueProject(IssueLabels,ProjectsInfo):
    global AlreadyRequestedProjects
    IssueProject=''
    ProjectNumber=-1

    for i in range(len(ProjectsInfo)):
        if ProjectsInfo[i]['BudgetLabel'] in IssueLabels and ProjectsInfo[i]['BudgetLabel'] not in AlreadyRequestedProjects:
            IssueProject=ProjectsInfo[i]['BudgetLabel']
            ProjectNumber = i
            break
    return IssueProject,ProjectNumber


def GetProjectInfo(jira,Issue,IssueProject,Loggers):
    ProcessLogger=Loggers.Loggers[0]['Logger']
    ProjectInfo={}
    jql=''
    
    #Define existance of parent link
    if 'issuelinks' in Issue["fields"]:
        if len(Issue["fields"]["issuelinks"])!=0:
            for link in Issue["fields"]["issuelinks"]:
                if link["type"]["name"] == "parent-child" and "inwardIssue" in link:#InwardIssue means Parent Issue
                    jql='issuekey = ' + '"' + link["inwardIssue"]["key"] + '"'
                    ProcessLogger.info('Current issue: '+Issue['key']+'. Parent issue: '+link["inwardIssue"]["key"])
                    break
    
    #Define existance of parent task
    if 'parent' in Issue["fields"]:
        jql='issuekey = ' + '"' + Issue["fields"]["parent"]["key"] + '"'
        ProcessLogger.info('Current issue: '+Issue['key']+'. Parent issue: '+Issue["fields"]["parent"]["key"])
    
    #Get project information
    if jql != '':#From parent issue
        ParentIssue = jira.search_issues(jql,maxResults=1,json_result=True,fields='labels,environment,worklog,summary,status,issuelinks,parent,subtasks,customfield_10103,customfield_12340,customfield_10253,customfield_10252')
        if "issues" in ParentIssue:
            ProjectInfo=GetProjectInfo(jira,ParentIssue["issues"][0],IssueProject,Loggers)
    else:#From current issue
        Budget,StartDate,DueDate=GetCheckedProjectInfoData(Issue,Loggers)
        if Budget != '' and StartDate != '' and DueDate != '':
            ProjectInfo.update({"BudgetLabel":IssueProject})
            ProjectInfo.update({"Budget":Budget})#Implementation Effort (in days)
            ProjectInfo.update({"StartDate":StartDate})#Development Start
            ProjectInfo.update({"DueDate":DueDate})#Planned Delivery Date                       
            ProcessLogger.info('Information for project '+IssueProject+' from issue '+Issue['key']+': '+json.dumps(ProjectInfo))
    
    return ProjectInfo
        

def GetCheckedProjectInfoData(Issue,Loggers):
    ProcessLogger=Loggers.Loggers[0]['Logger']
    Budget=''
    StartDate=''
    DueDate=''
    
    if ProjectBudgetField in Issue["fields"] and ProjectStartDateField in Issue["fields"] and ProjectDueDateField in Issue["fields"]:
        IssueBudget=Issue["fields"][ProjectBudgetField]
        IssueStartDate=Issue["fields"][ProjectStartDateField]
        IssueDueDate=Issue["fields"][ProjectDueDateField]
        
        if IssueBudget != None and IssueBudget != '':
            Budget=str(float(IssueBudget)*8*3600)
        if IssueStartDate != None and IssueStartDate != '':
            StartDate=datetime.datetime.strptime(IssueStartDate,'%Y-%m-%d').strftime('%d.%m.%Y')
        if IssueDueDate != None and IssueDueDate != '':
            DueDate=datetime.datetime.strptime(IssueDueDate,'%Y-%m-%d').strftime('%d.%m.%Y')
    else:
        ProcessLogger.info('Issue '+Issue["key"]+' does not contain all project information fields')
    
    return Budget,StartDate,DueDate
    

def UpdateProjectsInfo(JiraWrapper,IssuesList,ProcessID,Loggers,ProjectsXMLDict={}):
    ProcessLogger=Loggers.Loggers[0]['Logger']
    ProcessLogger.info('Start update of projects information')
    global AllProjectsDataUpdated
    global AlreadyRequestedProjects
    ProjectInfoDict={}
    
    if AllProjectsDataUpdated:
        ProcessLogger.info('All Projects data are updated. File with projects data will not be read')
        ProcessLogger.info('End update of projects information')
        return
    
    CurrentPath=GetProjectRootFolder()
    #Get projects which information was not read 
    ProjectsInfoList=GetProjectsInfo(CurrentPath)
    ProjectsWithoutInfo=[]
    for i in range(len(ProjectsInfoList)-1,-1,-1):
        for k in ProjectsInfoList[i]:
            if ProjectsInfoList[i][k] == '' or ProjectsInfoList[i][k] == None:
                ProjectsWithoutInfo.append(ProjectsInfoList[i].copy())
                del ProjectsInfoList[i]
                break
    if len(ProjectsWithoutInfo) == 0:
        AllProjectsDataUpdated = True
        ProcessLogger.info('All Projects data, read from file, are updated')
        ProcessLogger.info('End update of projects information')
        return
        
    #Update projects with received data
    NumberOfProjectsWithoutInfo=len(ProjectsWithoutInfo)
    for Issues in IssuesList:
        for issue in Issues["issues"]:
            if len(ProjectsWithoutInfo) == 0:
                break
            IssueProject,ProjectNumber = GetIssueProject(issue["fields"]["labels"],ProjectsWithoutInfo)
            if IssueProject !='':
                ProcessLogger.info('Start reading information for project '+IssueProject)
                AlreadyRequestedProjects.append(IssueProject)
                ProjectInfoDict.clear()
                ProjectInfoDict=GetProjectInfo(JiraWrapper.jira,issue,IssueProject,Loggers)
                if len(ProjectInfoDict.keys()) > 0:
                    ProjectsInfoList.append(ProjectInfoDict.copy())
                    del ProjectsWithoutInfo[ProjectNumber]
                ProcessLogger.info('End reading information for project '+IssueProject)
        
    #Save projects back in file only in case of at least one project data were updated
    if len(ProjectsWithoutInfo) != NumberOfProjectsWithoutInfo:
        #Add into ProjectsInfoList data from ProjectsWithoutInfo which were not deleted (as they have no estimates in root jira item)
        for ProjectInfo in ProjectsWithoutInfo:
            ProjectsInfoList.append(ProjectInfo.copy())
        #Save updated projects back in file
        SaveProjectsInfo(CurrentPath,ProjectsInfoList,ProjectsXMLDict)
    
    if len(ProjectsWithoutInfo) == 0:
        AllProjectsDataUpdated = True
        ProcessLogger.info('All Projects data were updated in current request')
    
    ProcessLogger.info('End update of projects information')
    
    
def SaveProjectsInfo(CurrentDir,ProjectsInfoList,ProjectsXMLDict={}):    
    ExcludedProjects=GetExcludedProjects()
    ProjectsFileFullName=GetDataFile(CurrentDir,ProjectsDataFile)
    if len(ProjectsXMLDict) == 0:
        ProjectsFromProjectsData,ProjectsXMLDict = GetProjectsFromFile(ProjectsFileFullName,ExcludedProjects,'Project')
    
    for ProjectInfo in ProjectsInfoList:        
        for Project in ProjectsXMLDict['Root']['Project']:
            if ProjectInfo['BudgetLabel'] == Project['BudgetLabel']:
                ProjectDict,Updated=UpdateProjectDict(ProjectDict=Project,Info={'BudgetLabel':ProjectInfo['BudgetLabel'],'Budget':ProjectInfo['Budget'],'StartDate':ProjectInfo['StartDate'],'DueDate':ProjectInfo['DueDate']})
                break
    
    SaveProjectsDataDictionary(ProjectsXMLDict,ProjectsFileFullName)
    

def GetFullFileNamesInFolder(FolderName,IncludeSubfolders = True):
    FilesInFolder = []
    
    if IncludeSubfolders:
        for root, dirs, files in os.walk(FolderName):
            for f in files:
                FilesInFolder.append(os.path.join(root,f).replace("\\","/"))
    else:
        for root, dirs, files in os.walk(FolderName):
            for f in files:
                FilesInFolder.append(os.path.join(root,f).replace("\\","/"))
            break
    return FilesInFolder





def GetProjectsFromFile(FileFullName,ExcludedProjects,ParentKeyForBudgetLabel):
    ProjectsFromFile=[]
    XMLDict={}
    ProjectFound=False
    
    #File has to be created out of this function
    #Read projects data from file
    with open(FileFullName,'r') as DataFile:
        XMLData=DataFile.read()
    
    if XMLData != '':
        XMLDict=json.loads(json.dumps(xmltodict.parse(XMLData)))
        for i in range(len(XMLDict['Root'][ParentKeyForBudgetLabel])):
            if XMLDict['Root'][ParentKeyForBudgetLabel][i]['BudgetLabel'] not in ExcludedProjects:
                ProjectFound=False
                for Project in ProjectsFromFile:
                    if Project == XMLDict['Root'][ParentKeyForBudgetLabel][i]['BudgetLabel']:
                        ProjectFound = True
                        break
                if ProjectFound == False:
                    ProjectsFromFile.append(XMLDict['Root'][ParentKeyForBudgetLabel][i]['BudgetLabel'])
            
    return ProjectsFromFile,XMLDict

def UpdateProjectList():
    ProjectListUpdated=False
    ExcludedProjects=GetExcludedProjects()
    
    CurrentPath=GetProjectRootFolder()
    ProjectsDataFileFullName=GetDataFile(CurrentPath,ProjectsDataFile,CreateIfNotExist=True)
    ExtDataFileFullName=GetDataFile(CurrentPath,ExtDataFile)
    
    ProjectsFromExt,ExtXMLDict = GetProjectsFromFile(ExtDataFileFullName,ExcludedProjects,'Entry')
    ProjectsFromProjectsData,ProjectsXMLDict = GetProjectsFromFile(ProjectsDataFileFullName,ExcludedProjects,'Project')
    
    if 'Root' not in ProjectsXMLDict:
        ProjectsXMLDict.update({'Root':{'Project':[]}})
    else:
        if 'Project' not in ProjectsXMLDict['Root']:
            ProjectsXMLDict['Root'].update({'Project':[]})
    
    for Project in ProjectsXMLDict['Root']['Project']:
        ProjectDict,Updated=UpdateProjectDict(ProjectDict=Project,Info={'BudgetLabel':Project['BudgetLabel']})
        if Updated:
            ProjectListUpdated=True
        
    for ExtProject in ProjectsFromExt:
        if ExtProject not in ProjectsFromProjectsData:
            ProjectDict,Updated=UpdateProjectDict(ProjectDict={},Info={'BudgetLabel':ExtProject})
            ProjectsXMLDict['Root']['Project'].append(ProjectDict)
            if Updated:
                ProjectListUpdated=True
    
    if ProjectListUpdated==True:
        SaveProjectsDataDictionary(ProjectsXMLDict,ProjectsDataFileFullName)
        print('List of projects was updated')

def SaveProjectsDataDictionary(ProjectsXMLDict,ProjectsDataFileFullName):
    my_item_func = lambda x: 'Project'
    xml=dicttoxml.dicttoxml(ProjectsXMLDict['Root']['Project'],root=True,custom_root='Root',attr_type=False,item_func=my_item_func)    
    with open(ProjectsDataFileFullName,'w') as DataFile:
        DataFile.write(parseString(xml).toprettyxml())

def UpdateProjectDict(ProjectDict={},Info={},IssuesCompletion={},EffortEstimations={}):#EffortEstimations={'EEACD':EEACD_Value,...}; Info={'BudgetLabel':BudgetLabel_Value,'Budget':Budget_Value,...}; IssuesCompletion={'AllIssuesCompleted':Value,'CompletenessCheckDate':Value}
    Updated=False
    if 'BudgetLabel' in Info:
        if Info['BudgetLabel'] != '':
            #Update project information structure
            if 'BudgetLabel' not in ProjectDict:
                ProjectDict.update({'BudgetLabel':''})
                Updated=True
            if 'Budget' not in ProjectDict:
                ProjectDict.update({'Budget':''})
                Updated=True
            if 'StartDate' not in ProjectDict:
                ProjectDict.update({'StartDate':''})
                Updated=True
            if 'DueDate' not in ProjectDict:
                ProjectDict.update({'DueDate':''})
                Updated=True
            #Update project issues completion structure
            if 'IssuesCompletion' not in ProjectDict:
                ProjectDict.update({'IssuesCompletion':{'AllIssuesCompleted':'','CompletenessCheckDate':'01.01.1800'}})
                Updated=True
            else:
                if 'AllIssuesCompleted' not in ProjectDict['IssuesCompletion']:
                    ProjectDict['IssuesCompletion'].update({'AllIssuesCompleted':''})            
                    Updated=True
                if 'CompletenessCheckDate' not in ProjectDict['IssuesCompletion']:
                    ProjectDict['IssuesCompletion'].update({'CompletenessCheckDate':'01.01.1800'})
                    Updated=True
            #Update project effort estimation structure
            EffortEstimationsList=GetEffortEstimations()
            if 'EffortEstimation' not in ProjectDict: 
                ProjectDict.update({'EffortEstimation':{}})
                for EE in EffortEstimationsList:
                    ProjectDict['EffortEstimation'].update({EE:''})
                Updated=True
            else:
                for EE in EffortEstimationsList:
                    if EE not in ProjectDict['EffortEstimation']:
                        ProjectDict['EffortEstimation'].update({EE:''})
                        Updated=True
                
            #Update values
            for Key,Value in Info.items():
                ProjectDict[Key]=Value
                Updated=True
            for Key,Value in IssuesCompletion.items():
                ProjectDict['IssuesCompletion'][Key]=Value
                Updated=True
            for Key,Value in EffortEstimations.items():
                ProjectDict['EffortEstimation'][Key]=Value
                Updated=True
            
    return ProjectDict,Updated
      
def GetEffortEstimations():
    return ['Development','Test','Other']


def GetExcludedProjects():
    return ['Project1','Project2']
