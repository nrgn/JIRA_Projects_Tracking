# -*- coding: utf-8 -*-

import os
import datetime

PortNumber = 8000
JiraWrapper = {}
ExecutiveProcesses=[]
InputDataDict={}
DataTypes=['Online','Offline']
CacheData={'Online':{'RequestData':False,'AlreadyRequestedKeys':[],'LastOutputData':[],'LastOutputDataDate':datetime.date(1800,1,1)},
           'Offline':{'RequestData':False,'AlreadyRequestedKeys':[],'LastOutputData':[],'LastOutputDataDate':datetime.date(1800,1,1)}} 
ProjectListUpdated=False
CompletedProjects=[]

ProjectsDataFile='ProjectsData.xml'
ExtDataFile='ExternalData.xml'
AuthorizationDataFile='Authorization.xml'

JIRAServer='https://jira.com/'

ProjectBudgetField='Field_1'
ProjectStartDateField='Field_2'
ProjectDueDateField='Field_3'

def GetProjectRootFolder():
    return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))