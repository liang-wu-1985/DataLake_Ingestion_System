#################JOB_NAME:SYNC_BUCKET_STORING_TO_USER_DAILY_JOB     #################
#################Author  :Liang Wu                                  #################
#################Version :1.0.0                                     #################
#################2019.06.03 ADD FUNCTION OF BACKUP CONFIG           #################
#################2019.06.04 ADD CODE BUCKET                         #################


import sys
import os
import json
import boto3
import datetime
import ast   ###CONVERT UNICODE OBJECT TO LIST###
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import SQLContext
from pyspark.sql.functions import col,udf
from pyspark.sql.functions import unix_timestamp
from pyspark.sql.functions import from_unixtime
from pyspark.sql.types import DateType
from pyspark.sql.functions import array, create_map, struct
from pyspark.sql.functions import lit
from pyspark.sql import functions as F
from pyspark.sql.types import *
from pyspark.sql.utils import AnalysisException  ###CATCH IF FILES NOT IN DIRECTORY
s3 = boto3.resource('s3')
from multiprocessing.pool import ThreadPool
import multiprocessing as mp
import time
import pytz

## @params: [JOB_NAME]
args = getResolvedOptions(sys.argv,
                          ['JOB_NAME',
                           'FIRST_FOLDER',
                           'LANDING_ZONE_BUCKET', 
                           'CODE_BUCKET',                          
                           'STORING_ZONE_BUCKET',
                           'PROCESSED_DIR',
                           'METADATA_LAYOUT_CHANGED_VARIABLE',
                           'GROUP_MAPPING_FILE_VARIABLE'])


sc = SparkContext()
glueContext = GlueContext(sc)
sqlContext = SQLContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'],args)


########CONSTANT VARIABLES FOR DEFINED FOLDERS##########
FIRST_FOLDER=args['FIRST_FOLDER']
LANDING_ZONE_BUCKET=args['LANDING_ZONE_BUCKET']
CODE_BUCKET=args['CODE_BUCKET']
STORING_ZONE_BUCKET=args['STORING_ZONE_BUCKET']
PROCESSED_DIR=args['PROCESSED_DIR']
METADATA_LAYOUT_CHANGED_VARIABLE=args['METADATA_LAYOUT_CHANGED_VARIABLE']
GROUP_MAPPING_FILE_VARIABLE=args['GROUP_MAPPING_FILE_VARIABLE']
SOURCE_PRE_FOLDER_SYNC=FIRST_FOLDER+"/"+PROCESSED_DIR

########CONSTANT VARIABLES FOR FAILED OBJECTS##########
FAILED_MATCHING_FILES_PATH='s3://'+STORING_ZONE_BUCKET+'/'+FIRST_FOLDER+'/FAILED_TO_CONVERT'
FAILED_FILENAME_HEAD_FORMAT=['FILENAME','HEADER_LIST','HEADER_CNT','META_HEADER_LIST','META_HEADER_CNT','START_EXEC_TIME','TYPE']
UNMATCH_TYPE='UNMATCH'
OUTOFCONFIG_TYPE='OUTOFCONFIG'
IRREGULAR_TYPE='IRREGULAR'


########CONSTANT VARIABLES OF META DATA FOR MAPPING DATALAKE FILES##########
METADATA_LAYOUT_CHANGED_FILE='s3://{}/{}'.format(CODE_BUCKET,METADATA_LAYOUT_CHANGED_VARIABLE)
GROUP_MAPPING_FILE='s3://{}/{}'.format(CODE_BUCKET,GROUP_MAPPING_FILE_VARIABLE)


########SYNC BUCKETS IF DESTINATION HAS FILES WHICH ARE NOT IN SOURCE, DELETE THEM##########
Conf_Df = spark.read.option("header","True").csv(GROUP_MAPPING_FILE)
Layout_changed_Df = spark.read.option("header","True").csv(METADATA_LAYOUT_CHANGED_FILE)

############CACHE DF###############
Layout_changed_Df=Layout_changed_Df.cache()



########GET THE STRING OF CURRENT TIME##########
def getNowtime():
    my_date = datetime.datetime.now(pytz.timezone('Japan'))
    return my_date.strftime("%Y%m%d_%H%M%S")
    
    

########BACKUP CONFIG FOLDER##########
def backupConfig():
    sync_command = "aws s3 sync s3://{}/config ".format(CODE_BUCKET) + "s3://{}/backup/conf_{}/".format(CODE_BUCKET,getNowtime())
    os.system(sync_command)
    
    
 ########SYNC STORING BUCKET TO USER BUCKET##########   
def sync_bucket(row):
    table_name=row.asDict()['TABLE']
    group_name=row.asDict()['GROUP']
    feq_name=row.asDict()['FEQ']
    user_bucket=row.asDict()['USER_BUCKET']
    LAYOUTCHANGED_MARK='_LAYOUTCHANGED'
    layoutchanged_list=Layout_changed_Df.select('TABLE').rdd.map(lambda row : row[0]).collect()    ############GET THE LIST OF TABLES WHOSE LAYOUT HAS BEEN CHANGED############
    
    
    ########################--delete (boolean) Files that exist in the destination but not in the source are deleted during sync.############################################
    if table_name in layoutchanged_list:
        sync_command = "aws s3 sync s3://"+STORING_ZONE_BUCKET+"/"+SOURCE_PRE_FOLDER_SYNC+"/"+feq_name+"/"+table_name+LAYOUTCHANGED_MARK+"/ "+"s3://"+user_bucket+"/"+FIRST_FOLDER+"/"+group_name+"/"+feq_name+"/"+table_name+"/ --delete"
        os.system(sync_command)
    else:
        sync_command = "aws s3 sync s3://"+STORING_ZONE_BUCKET+"/"+SOURCE_PRE_FOLDER_SYNC+"/"+feq_name+"/"+table_name+"/ "+"s3://"+user_bucket+"/"+FIRST_FOLDER+"/"+group_name+"/"+feq_name+"/"+table_name+"/ --delete"
        os.system(sync_command)
    
############SYNC BUCKETS IN ASYNC MODE##########################
pool = ThreadPool(processes=10)

for row in Conf_Df.rdd.collect():
    pool.apply_async(sync_bucket,[row])
    
pool.close()
pool.join() ############## WAIT FOR ALL CHILD PROCESSES TO CLOSE.###################

########BACKUP CONFIG FOLDER##########
backupConfig()


job.commit()
