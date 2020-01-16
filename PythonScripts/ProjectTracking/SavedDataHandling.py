# -*- coding: utf-8 -*-

from Project_Info import GetFullFileNamesInFolder
import os
import json
from pytz import timezone
import datetime

from Globals import CacheData,GetProjectRootFolder
from Project_Info import ParseFileFullName

def GetSavedDictionaryWithWorklogs(InputParametersdict,DataType='Offline',StatusNames=[]):    
    #Get worklogs folder
    CurrentPath=GetProjectRootFolder()
    WorklogsFolder=os.path.join(CurrentPath,'Worklogs')
    if not os.path.exists(WorklogsFolder):
        return    
    #Get files with saved worklogs
    FilesInFolder=GetFullFileNamesInFolder(WorklogsFolder)
    #Get issues from files
    for f in FilesInFolder:
        CacheData[DataType]['LastOutputData'].append(GetIssuesFromFile(f,InputParametersdict,StatusNames))
    

def GetIssuesFromFile(FullFileName,InputParametersdict,StatusNames=[]):#StatusNames=['Completed','In Progress','Open','Done']
    SelectedIssues=[]
    #Read JSON data with issues into dictionary
    FileInfo=ParseFileFullName(FullFileName)
    with open(FullFileName,'r') as IssuesJSONFile:
        Issues=json.load(IssuesJSONFile)
    
    print('Number of issues in file '+FileInfo['FileNameWithoutExtension']+":",len(Issues))
    for issue in Issues:
        SelectIssue=True
        
        #Filter Status
        if len(StatusNames)>0:
            DataFound=False
            if issue['fields']['status']['name'] in StatusNames:
                DataFound = True
            SelectIssue = DataFound
        
        #Filter Projects
        if SelectIssue == True:
            if 'Projects' in InputParametersdict:
                DataFound=False
                for label in issue['fields']['labels']:
                    if label in InputParametersdict['Projects']:
                        DataFound = True
                        break
                SelectIssue = DataFound
        
        #Filter Users and Dates
        if SelectIssue == True:
            if 'Users' in InputParametersdict or 'StartDates' in InputParametersdict and 'EndDates' in InputParametersdict:
                WorklogFound = False
                for worklog in issue['fields']['worklog']['worklogs']:
                    WorklogFound = True
                    #Filter Users
                    if 'Users' in InputParametersdict:
                        DataFound = False
                        if worklog['updateAuthor']['displayName'] in InputParametersdict['Users']:
                            DataFound = True
                        WorklogFound = DataFound
                    
                    #Filter Dates
                    if WorklogFound == True:
                        if 'StartDates' in InputParametersdict and 'EndDates' in InputParametersdict:
                            DataFound = False
                            JDT = worklog['started']
                            JiraLocalDate = datetime.datetime(int(JDT[:4]),int(JDT[5:7]),int(JDT[8:10]),int(JDT[11:13]),int(JDT[14:16]),int(JDT[17:19]),int(JDT[20:23]+'000'),timezone('UTC')).astimezone(timezone('Europe/Moscow')).date()
                            for i in range(len(InputParametersdict['StartDates'])):
                                InputStartLocalDate = datetime.datetime.strptime(InputParametersdict['StartDates'][i],'%Y-%m-%d').date()
                                InputEndLocalDate = datetime.datetime.strptime(InputParametersdict['EndDates'][i],'%Y-%m-%d').date()
                                if JiraLocalDate >= InputStartLocalDate and JiraLocalDate <= InputEndLocalDate:
                                    DataFound = True
                                    break
                            WorklogFound = DataFound
 
                    if WorklogFound == True:
                        break
                SelectIssue = WorklogFound

        if SelectIssue == True:
            SelectedIssues.append(issue.copy())
    
    print('Number of selected issues from file '+FileInfo['FileNameWithoutExtension']+":",len(SelectedIssues))
    return {'issues':SelectedIssues.copy()}