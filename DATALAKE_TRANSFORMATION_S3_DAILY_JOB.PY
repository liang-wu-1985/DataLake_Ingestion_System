#################JOB_NAME:DATALAKE_TRANSFORMATION_S3_DAILY_JOB                                  #################
#################Author  :WU Liang                                                              #################
#################Version :1.0.0                                                                 #################
#################MODIFICATION DETAIL                                                            #################
#################2019.05.11      ADD MERGE FUNCTION                                             #################
#################2019.05.14      HEAD_LIST USING AST CHANGE UNICODE TO LIST TYPE                #################
#################2019.05.17      UPDATE RENAMECOLUMNS FUNCTION                                  #################
#################2019.05.31      EXCLUDE EMPTY FILE                                             #################
#################2019.05.31      ADD SUMMARY REPORT FEATURE                                     #################
#################2019.06.04      ADD CODE BUCKET                                                #################
#################2019.06.10      ADD TYPE LIST  (deleted and go back to ALL STRING VERSION)     #################
#################2019.06.10      OVERWRITE FUNCTION WHEN STORE PARQUET IN BUCKET                #################
#################2019.06.21      EMPTY FILES FLUSH TO PROCESSED LIST                            #################

import ast  # ##CONVERT UNICODE OBJECT TO LIST###
import datetime
import json
import multiprocessing as mp
import os
import sys
import time
from multiprocessing.pool import ThreadPool

import pytz

import boto3
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import SQLContext
from pyspark.sql import functions as F
from pyspark.sql.functions import (array, col, create_map, from_unixtime, lit,
                                   struct, udf, unix_timestamp)
from pyspark.sql.types import *
from pyspark.sql.types import DateType
from pyspark.sql.utils import \
    AnalysisException  # ##CATCH IF FILES NOT IN DIRECTORY

s3 = boto3.resource('s3')


## @params: [JOB_NAME]
args = getResolvedOptions(sys.argv,
                          ['JOB_NAME',
                           'FIRST_FOLDER',
                           'LANDING_ZONE_BUCKET',
                           'STORING_ZONE_BUCKET',
                           'CODE_BUCKET',
                           'PROCESSED_DIR',
                           'METADATA_MAPPING_FILE_VARIABLE',
                           'METADATA_LAYOUT_CHANGED_VARIABLE',
                           'GROUP_MAPPING_FILE_VARIABLE',
                           'IS_SYNC_ALL_MODE',
                           'MERGE_OR_NOT',
                           'SNS_ARN'])


sc = SparkContext()
glueContext = GlueContext(sc)
sqlContext = SQLContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)
os.environ["NLS_LANG"]= "JAPANESE_JAPAN.AL32UTF8"



########CONSTANT VARIABLES FOR DEFINED FOLDERS##########
FIRST_FOLDER=args['FIRST_FOLDER']
LANDING_ZONE_BUCKET=args['LANDING_ZONE_BUCKET']
STORING_ZONE_BUCKET=args['STORING_ZONE_BUCKET']
CODE_BUCKET=args['CODE_BUCKET']
PROCESSED_DIR=args['PROCESSED_DIR']
METADATA_MAPPING_FILE_VARIABLE=args['METADATA_MAPPING_FILE_VARIABLE']
METADATA_LAYOUT_CHANGED_VARIABLE=args['METADATA_LAYOUT_CHANGED_VARIABLE']
GROUP_MAPPING_FILE_VARIABLE=args['GROUP_MAPPING_FILE_VARIABLE']
IS_SYNC_ALL_MODE=args['IS_SYNC_ALL_MODE']
MERGE_OR_NOT=args['MERGE_OR_NOT']
SNS_ARN=args['SNS_ARN']

JOB_STATUS="SUCCEEDED"

SOURCE_PRE_FOLDER_SYNC=FIRST_FOLDER+"/"+PROCESSED_DIR

########################################################################## START : REPLACE TO JOB MODE#######################################################################

#############DATA TYPE DICTIONARY##############
List_Types_Dict =	{
    1 : StringType(),
    2 : FloatType(),
    3 : DecimalType(),
    4 : LongType(),
    5 : TimestampType(),
    6 : DateType(),
    7 : BooleanType()
}


########CONSTANT VARIABLES FOR FAILED OBJECTS##########
FAILED_MATCHING_FILES_PATH='s3://'+STORING_ZONE_BUCKET+'/'+FIRST_FOLDER+'/FAILED_TO_CONVERT'
FAILED_FILENAME_HEAD_FORMAT=['FILENAME','HEADER_LIST','HEADER_CNT','META_HEADER_LIST','META_HEADER_CNT','START_EXEC_TIME','TYPE']
UNMATCH_TYPE='UNMATCH'
OUTOFCONFIG_TYPE='OUTOFCONFIG'
IRREGULAR_TYPE='IRREGULAR'



########CONSTANT VARIABLES OF META DATA FOR MAPPING DATALAKE FILES##########
METADATA_MAPPING_FILE='s3://{}/{}'.format(CODE_BUCKET,METADATA_MAPPING_FILE_VARIABLE)
METADATA_LAYOUT_CHANGED_FILE='s3://{}/{}'.format(CODE_BUCKET,METADATA_LAYOUT_CHANGED_VARIABLE)
GROUP_MAPPING_FILE='s3://{}/{}'.format(CODE_BUCKET,GROUP_MAPPING_FILE_VARIABLE)

########CONSTANT VARIABLES OF LIST WHICH HAS BEEN PROCESSED, THEN WE SHOULD EXCLUDE IT##########
PROCESSED_OBJECT_FILE='config/processed_list.json'




########CONSTANT VARIABLES OF HOW TO WRITE PROCESSED FILES INTO S3##########
EXTENSION=23 #the length of '_YYYMMDD_HHMMSS.CSV.GZ'
OUTPUT_FORMAT='parquet'
OUTPUT_COMPRESSION='gzip'
MODE_METHOD_APPEND='append'
MODE_METHOD_OVERWRITE='overwrite'
PARTITIONBY='TRANSFERRED_DATE'
OUTCONFIG_LIST=[]
UNMATCH_LIST=[]
IRREGULAR_LIST=[]
PROCESSED_OBJECT_LIST_THIS_TIME=[]

########UDF FOR CONVERTING STRING TO DATE##########
func =udf(lambda x: datetime.datetime.strptime(x,'%Y/%m/%d'), DateType())


########GET DATAFRAME OF ALL METADATA FILES##########
Conf_Df = spark.read.option("header","True").csv(METADATA_MAPPING_FILE)
Conf_Df_1 = Conf_Df.withColumn('STARTDATE', func(col('STARTDATE')))
Conf_Df_2 = Conf_Df_1.withColumn('ENDDATE', func(col('ENDDATE')))

####CACHE METADATA FILE####
Conf_Df_2=Conf_Df_2.cache()


########GET DATAFRAME OF ALL METADATA FILES##########
def matchcolwithTypes(df,type_list):
    if len(df.columns)==len(type_list):
        for col_sig, col_type_num in zip(df.columns, type_list):
            ################IF THE TYPE IS TIMESTAMP##############
            if col_type_num == 5:
                df= df.withColumn(col_sig,to_timestamp(col_sig, "yyyyy/mm/dd hh:mm:ss"))
            else:
                df=df.withColumn(col_sig,df[col_sig].cast(List_Types_Dict[col_type_num]))
        return df
    else:
        err_msg="THE NUM OF TYPE LIST IN CONFIG IS NOT MATCHING NUM IN TARGET FILE: " + df.columns
        send_notify_to_sns(SNS_ARN,err_msg)



########GET NOW IN JAPAN TIME ZONE##########
def getNowtime():
    my_date = datetime.datetime.now(pytz.timezone('Japan'))
    return my_date.strftime("%Y-%m-%d %H:%M:%S")




########NOTIFY FUNCTION##########
def send_notify_to_sns(sns_arn,err_msg):
    sns = boto3.client('sns', region_name='ap-southeast-1')
    subject="【Daily Report】DATALAKE_TRANSFORMATION_S3_DAILY_JOB "+ getNowtime()
    sns.publish(
            TopicArn=sns_arn,    
            Message=err_msg,    
            Subject=subject
            )



########REPORT OF SENDING ##########
def send_completed_mail(PROCESSED_OBJECT_LIST,UNMATCH_LIST,OUTCONFIG_LIST,IRREGULAR_LIST,JOB_STATUS,JOB_START_TIME,JOB_END_TIME):

    PROCESSED_FILES_NUMBERS=len(PROCESSED_OBJECT_LIST)
    UNMATCH_FILES_NUMBERS=len(UNMATCH_LIST)
    OUTCONFIG_FILES_NUMBERS=len(OUTCONFIG_LIST)
    IRREGULAR_FILES_NUMBERS=len(IRREGULAR_LIST)
    
    msg = """
        
        DATALAKE_TRANSFORMATION_S3_DAILY_JOB PROCESS COMPLETED
    
        ------------------------------------------------------------------------------------
        SUMMARY OF THE PROCESS:
        ------------------------------------------------------------------------------------
        {a:<20}    :   {PROCESSED_FILES_NUMBERS}
        {b:<20}    :   {UNMATCH_FILES_NUMBERS}
        {c:<20}    :   {OUTCONFIG_FILES_NUMBERS}
        {d:<20}    :   {IRREGULAR_FILES_NUMBERS}
        {e:<20}    :   {JOB_STATUS}
        {f:<20}    :   {JOB_START_TIME}
        {g:<20}    :   {JOB_END_TIME}
        ------------------------------------------------------------------------------------
        
        AS FOR THE DETAIL OF EXCEPTION FILES, PLEASE REFER TO FAILED_PROCESS_LIST_DB VIA ATHENA ON AWS

        ----------------------SQL IS AF FOLLOWS####---------------------------


        SELECT FILENAME,HEADER_CNT,META_HEADER_CNT,TYPE FROM "FAILED_PROCESS_LIST_DB"."FAILED_TO_CONVERT" WHERE START_EXEC_TIME > '{JOB_START_TIME}'
        
        """.format(a='PROCESSED_FILES_NUMBERS', b = 'UNMATCH_FILES_NUMBERS', c = 'OUTCONFIG_FILES_NUMBERS', d = 'IRREGULAR_FILES_NUMBERS',e = 'JOB_STATUS', f = 'JOB_START_TIME', g = 'JOB_END_TIME', PROCESSED_FILES_NUMBERS=PROCESSED_FILES_NUMBERS,UNMATCH_FILES_NUMBERS=UNMATCH_FILES_NUMBERS,OUTCONFIG_FILES_NUMBERS=OUTCONFIG_FILES_NUMBERS,IRREGULAR_FILES_NUMBERS=IRREGULAR_FILES_NUMBERS,JOB_STATUS=JOB_STATUS,JOB_START_TIME=JOB_START_TIME,JOB_END_TIME=JOB_END_TIME )
    
    send_notify_to_sns(SNS_ARN,msg)


################GET JOB START TIME#####################
JOB_START_TIME=getNowtime()


########CHECK IF THERE ARE DUPLICATED COLUMNS IN ENTRY##########  
for row in Conf_Df.rdd.collect():
    unicode_list=row.asDict()['HEADLIST']
    table=row.asDict()['TABLE']
    list=[e.encode('utf-8') for e in unicode_list.strip('[]').split(',')]
    if len(list)<>len(set(list)):
        err_msg = "METADATA_MAPPING_FILE HAS DUPLICATED COLUMNS IN ENTRY: " + table
        send_notify_to_sns(SNS_ARN,err_msg)
        sys.exit()



########GET DATAFRAME OF LAYOUT CHANGED FILES##########
Layout_changed_Df = spark.read.option("header","True").csv(METADATA_LAYOUT_CHANGED_FILE)

def merge_repartition_table(TABLE_PATH,BUCKET_NAME):
    BUCKETNAME_WITH_S3='s3://'+BUCKET_NAME+'/'
    try:
        tmp_df=spark.read.option("header", "True").option("mergeSchema", "True").parquet(BUCKETNAME_WITH_S3+TABLE_PATH)
        ########EXPORT AND REPARTITION TABLE##########    
        LAYOUTCHANGED_MARK='_LAYOUTCHANGED'
        EXPORT_DF_WITH_HEADER_DIR=BUCKETNAME_WITH_S3+TABLE_PATH+LAYOUTCHANGED_MARK
        tmp_df.repartition(1).write.option("encoding", "UTF-8").partitionBy(PARTITIONBY).save(path=EXPORT_DF_WITH_HEADER_DIR,format=OUTPUT_FORMAT,mode=MODE_METHOD_OVERWRITE,compression=OUTPUT_COMPRESSION)
    except AnalysisException:
        err_msg="THE TABLE YOU WANT TO MERGE IS NOT IN YOUR PROCESSED DIRECTORY: " + BUCKETNAME_WITH_S3+TABLE_PATH+"_LAYOUTCHANGED"
        JOB_STATUS="COMPLETED WITH ERRORS"
        send_notify_to_sns(SNS_ARN,err_msg)
        

########THE FUNCTION OF GETTING LIST OF OBJECT##########
def convert_from_bucket_to_list(BCKNAME):
    MY_BUCKET = s3.Bucket(BCKNAME)
    list=[]
    for object in MY_BUCKET.objects.all():
        if object.key.split("/")[0]==FIRST_FOLDER:  ####ONLY PROCESS THE FIRST FOLDER WHICH CALLED 'structure'
            list.append(object.key)
    return list
    


########THE FUNCTION OF GETTING LIST OF PROCESSED LIST FILE##########
def get_list_from_file(BCKNAME,PROCESSED_OBJECT_FILE):
    try:
        content_object = s3.Object(BCKNAME, PROCESSED_OBJECT_FILE)
        file_content = content_object.get()['Body'].read().decode('utf-8')
        json_content = json.loads(file_content)
    except Exception as e:
        json_content=[]
        
    return json_content
    
    
def process_list(object):
    try:
        if 'CSV.GZ' in object.upper():   ###FIND FILES WHICH CONTAINS CSV.GZ###
            fullfilename=object.split("/")[-1]   ###GET FILE NAME BEHIND FOLDER###
            if fullfilename[-EXTENSION]=='_':
                tablename=fullfilename[:-EXTENSION]
                tbldate_org=fullfilename[-EXTENSION+1:-EXTENSION+9]
                
                ##############IN CASE OF OTHER CSV.GZ FILES EXSIT##########################
                try:
                    import datetime
                    tbldate = datetime.datetime.strptime(tbldate_org,'%Y%m%d')
                except Exception as e:
                    err_msg="THIS CSV.GZ IS NOT STANDARD FORMAT : " + object + "   " + e.message
                    JOB_STATUS="COMPLETED WITH ERRORS"
                    send_notify_to_sns(SNS_ARN,err_msg)
                    return
    
                
                ########MATCH FILENAME WITH CONFIG TABLENAME##########
                Conf_Df_2.registerTempTable("conf_table")
                QUERY_CONFTBL = "SELECT HEADLIST,TYPELIST,FEQ FROM conf_table where STARTDATE <= '{}' and ENDDATE > '{}' and TABLE='{}'".format(tbldate,tbldate,tablename)
                executed_DF=spark.sql(QUERY_CONFTBL)
                
                ########IF FILENAME MATCHED CONFIG TABLENAME##########
                if len(executed_DF.head(1)) == 1:
                
                    ########CHANGE UNICODE TO LIST##########
                    head_list=ast.literal_eval(executed_DF.select('*').collect()[0].__getitem__("HEADLIST"))
                    #type_list=ast.literal_eval(executed_DF.select('*').collect()[0].__getitem__("TYPELIST"))
                    
                    ###GET TYPE OF WEEKLY OR DAILY OR WEEKLY###
                    feq_info=executed_DF.select('*').collect()[0].__getitem__("FEQ")                           
                    exsit_file_path='s3://'+LANDING_ZONE_BUCKET+'/'+object
    
                    
                    ###############CREATE DATAFRAME FROM RAW DATA###############
                    df_datafile=spark.read.option("header", "false").csv(exsit_file_path)
                    
                    ########IF NUMS OF HEADERS ARE NOT MATCHED##########
                    if len(df_datafile.columns) <> len(head_list):
                        if len(df_datafile.columns) <> 0:
                            now_time=getNowtime()
                            tmp=(object,''.join(df_datafile.columns),str(len(df_datafile.columns)),','.join(head_list),str(len(head_list)),now_time,UNMATCH_TYPE)
                            UNMATCH_LIST.append(tmp)
                        else:
                            ########MARK WHAT OBJECT HAS BEEN PROCESSED########
                            PROCESSED_OBJECT_LIST.append(object)
                            PROCESSED_OBJECT_LIST_THIS_TIME.append(object)

                        
                    ########IF NUMS OF HEADERS ARE MATCHED, UPDATE HEADER WITH REAL HEADER OF CONFIGTABLE##########
                    else:
                        newColumns=head_list
                        tbldate_str=tbldate.strftime("%Y-%m-%d")
    
                        #########MATCH TYPE OF COLUMN#########
                        #DF_matchTypes=matchcolwithTypes(df_datafile,type_list)
    
    
                        #EXPORT_DF_WITH_HEADER_DIR='s3://'+STORING_ZONE_BUCKET+'/'+FIRST_FOLDER+'/'+PROCESSED_DIR+'/'+feq_info+'/'+tablename+'/'

                        DF_updatedCols = df_datafile.toDF(*newColumns)
                        #DF_updatedCols_withDate=DF_updatedCols.withColumn(PARTITIONBY, lit(tbldate_str))

                        EXPORT_DF_WITH_HEADER_DIR="s3://{}/{}/{}/{}/{}/{}={}".format(STORING_ZONE_BUCKET,FIRST_FOLDER,PROCESSED_DIR,feq_info,tablename,PARTITIONBY,tbldate_str)
                        
                        #DF_updatedCols_withDate.repartition(1).write.option("encoding", "UTF-8").partitionBy(PARTITIONBY).save(path=EXPORT_DF_WITH_HEADER_DIR,format=OUTPUT_FORMAT,mode=MODE_METHOD_APPEND,compression=OUTPUT_COMPRESSION)
                        DF_updatedCols.repartition(1).write.save(path=EXPORT_DF_WITH_HEADER_DIR,format=OUTPUT_FORMAT,mode=MODE_METHOD_OVERWRITE,compression=OUTPUT_COMPRESSION)
                        
                        ########MARK WHAT OBJECT HAS BEEN PROCESSED########
                        PROCESSED_OBJECT_LIST.append(object)
                        PROCESSED_OBJECT_LIST_THIS_TIME.append(object)
                        
                ########IF FILE IS NOT IN METADATA MAPPING FILE##########       
                else:
                    now_time=getNowtime()
                    tmp=(object,'','','','',now_time,OUTOFCONFIG_TYPE)
                    OUTCONFIG_LIST.append(tmp)
            
            ########IF FILE HAS A IRREGULAR FORMAT##########           
            else:
                now_time=getNowtime()
                tmp=(fullfilename,'','','','',now_time,IRREGULAR_TYPE)
                IRREGULAR_LIST.append(tmp)
                
    except Exception as e: 
        JOB_STATUS="COMPLETED WITH ERRORS"
        msg="SOME EXCEPTIONS HAPPENED WHILE PROCESSING OBJECT: " + object + e
        send_notify_to_sns(SNS_ARN,msg)
        
    
    ########OUTPUT ALL PROCESSED FILES INCLUDING PREVIOUS LIST##########
    

###GET LIST OF OBEJECT OF BUCKET
OBJECT_LIST=convert_from_bucket_to_list(LANDING_ZONE_BUCKET)


###GET LIST OF PROCESSED OBJECT PREVIOUSLY
PROCESSED_OBJECT_LIST=get_list_from_file(CODE_BUCKET,PROCESSED_OBJECT_FILE)


###REMOVE PROCESSED LIST FROM ALL OBJECTS LIST
GOING_TO_PROCESS_LIST=(set(OBJECT_LIST)-set(PROCESSED_OBJECT_LIST))


#######################START STATUS MONITOR OF LOOP PROCESS#####################################################
results = []
def log_result(retval):
    results.append(retval)
    if len(results) % (len(GOING_TO_PROCESS_LIST)//1000) == 0:
        print('{:.0%} done'.format(len(results)/len(GOING_TO_PROCESS_LIST)))

#######################END STATUS MONITOR OF LOOP PROCESS#####################################################

##########################USING MUTIPLE-THREADS TO PROCESS EACH CSV.GZ FILE######################################################################
##########################PROCESS NUMBERS SHOULD BE CLOSE TO DPUs          ######################################################################
pool = ThreadPool(processes=120)
for object in GOING_TO_PROCESS_LIST:
    pool.apply_async(process_list,[object])
   
pool.close()
pool.join() ############## WAIT FOR ALL CHILD PROCESSES TO CLOSE.###################


#########################OUTPUT CONFIG AND FAILED FILES INTO S3######################################

if len(PROCESSED_OBJECT_LIST)>0:
    PROCESSED_OBJECT_JSON = json.dumps(PROCESSED_OBJECT_LIST)
    obj = s3.Object(CODE_BUCKET,PROCESSED_OBJECT_FILE)
    obj.put(Body=PROCESSED_OBJECT_JSON)

if len(UNMATCH_LIST)>0:
    unmatch_df=spark.createDataFrame(UNMATCH_LIST,FAILED_FILENAME_HEAD_FORMAT)
    unmatch_df.repartition(1).write.parquet(FAILED_MATCHING_FILES_PATH,mode=MODE_METHOD_APPEND,compression=OUTPUT_COMPRESSION)

if len(OUTCONFIG_LIST)>0:
    outconf_df=spark.createDataFrame(OUTCONFIG_LIST,FAILED_FILENAME_HEAD_FORMAT)
    outconf_df.repartition(1).write.parquet(FAILED_MATCHING_FILES_PATH,mode=MODE_METHOD_APPEND,compression=OUTPUT_COMPRESSION)

if len(IRREGULAR_LIST)>0:
    irre_df=spark.createDataFrame(IRREGULAR_LIST,FAILED_FILENAME_HEAD_FORMAT)
    irre_df.repartition(1).write.parquet(FAILED_MATCHING_FILES_PATH,mode=MODE_METHOD_APPEND,compression=OUTPUT_COMPRESSION)



########MERGE DATAFILE WHICH HAS LAYOUT CHANGED##########  
if MERGE_OR_NOT == "True":
    for row in Layout_changed_Df.rdd.collect():
        table_name=row.asDict()['TABLE']
        feq_name=row.asDict()['FEQ']
        table_path=FIRST_FOLDER+'/'+PROCESSED_DIR+'/'+feq_name+'/'+table_name
        print table_path
        merge_repartition_table(table_path,STORING_ZONE_BUCKET)


################GET JOB END TIME#####################
JOB_END_TIME=getNowtime()


################SEND REPORT OF COMPLETED JOB#####################
send_completed_mail(PROCESSED_OBJECT_LIST_THIS_TIME,UNMATCH_LIST,OUTCONFIG_LIST,IRREGULAR_LIST,JOB_STATUS,JOB_START_TIME,JOB_END_TIME)


########################################################################## END : REPLACE TO JOB MODE#######################################################################

job.commit()
