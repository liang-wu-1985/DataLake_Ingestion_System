#################JOB_NAME:OUTPUT_METADATA_DDL_JOB                   #################
#################Author  :Akira (WU Liang <liang.wu@axa.co.jp>)     #################
#################Version :1.0.0                                     #################
#################2019.06.04      ADD CODE BUCKET                    #################

import argparse
import datetime
import logging
import sys
from time import sleep

import pytz

import boto3

# Setup logger
fmt = "%(asctime)s %(levelname)s %(message)s"
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter(fmt=fmt))
LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
LOGGER.addHandler(handler)


region_var = 'ap-southeast-1'  # Change the region for the script to run
glue_client = boto3.client('glue',region_name=region_var)  

def get_args():
    parser = argparse.ArgumentParser()
    # crawler is glue crawler name
    parser.add_argument("--FIRST_FOLDER", type=str, required=True)
    parser.add_argument("--LANDING_ZONE_BUCKET", type=str, required=True)
    parser.add_argument("--CODE_BUCKET", type=str, required=True)	
    parser.add_argument("--DATABASE_LIST", type=str, required=True)
    parser.add_argument("--METADATA_DDL_PATH", type=str, required=True)

    # parse_known_args return (known_args, unknown_args)
    args, _ = parser.parse_known_args()
    return args



########GET THE STRING OF CURRENT TIME##########
def getNowtime():
    my_date = datetime.datetime.now(pytz.timezone('Japan'))
    return my_date.strftime("%Y%m%d_%H%M%S")
    
    

# Definite a function for starting an Athena query
def run_query(query, database, s3_output):
	client = boto3.client('athena')
	response = client.start_query_execution(
		QueryString=query,
		QueryExecutionContext={
			'Database': database
			},
		ResultConfiguration={
			'OutputLocation': s3_output,
			}
		)
	print('Completed '+s3_output+' with Execution ID: ' + response['QueryExecutionId'])
	

args = get_args()
FIRST_FOLDER = args.FIRST_FOLDER
LANDING_ZONE_BUCKET = args.LANDING_ZONE_BUCKET
CODE_BUCKET = args.CODE_BUCKET
DATABASE_STRING = args.DATABASE_LIST
METADATA_DDL_PATH = args.METADATA_DDL_PATH

######## Change the S3 location where the query will write DDL files#########
s3_var = 's3://{}/backup/{}_{}'.format(CODE_BUCKET,METADATA_DDL_PATH,getNowtime())

DATABASE_LIST=DATABASE_STRING.split(',')

# Create a list for all the Glue Tables
for databaseName in DATABASE_LIST:
 responseGetTables = glue_client.get_tables( DatabaseName = databaseName )
 tableList = responseGetTables['TableList']
 # Loop through the tableList and write out the table DDL to respective directory in S3 using the run_query function
 for tableDict in tableList:
 	try:
 		print('')
 		tableName = tableDict['Name']
 		#print('-- tableName: '+tableName)  # Optionally you can print out the names of the tables
 		run_query("show create table "+tableName, databaseName, s3_var+'/'+databaseName+"/"+tableName)
 	except:
 		print("There was an error with "+tableName+" in database "+databaseName)
