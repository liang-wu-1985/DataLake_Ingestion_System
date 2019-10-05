#################JOB_NAME:CONVERT_RDS_TO_S3_DAILY_JOB               #################
#################Author  :WU LIANG                                  #################
#################Version :1.0.0                                     #################

import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from pyspark.sql import SQLContext
from awsglue.job import Job
from pyspark.sql.utils import *

sc = SparkContext.getOrCreate()
glueContext = GlueContext(sc)
sqlContext = SQLContext(sc)
spark = glueContext.spark_session


## @params: [JOB_NAME]
args = getResolvedOptions(sys.argv,
                          ['JOB_NAME',
                           'FIRST_FOLDER',
                           'LANDING_ZONE_BUCKET',
                           'STORING_ZONE_BUCKET',
                           'PROCESSED_DIR',
                           'RDS_MAPPING_FILE_VARIABLE',
                           'CATALOG_DATABASE'])



job = Job(glueContext)
job.init(args['JOB_NAME'], args)


########CONSTANT VARIABLES FOR DEFINED FOLDERS##########
FIRST_FOLDER=args['FIRST_FOLDER']
LANDING_ZONE_BUCKET=args['LANDING_ZONE_BUCKET']
STORING_ZONE_BUCKET=args['STORING_ZONE_BUCKET']
PROCESSED_DIR=args['PROCESSED_DIR']
RDS_MAPPING_FILE_VARIABLE=args['RDS_MAPPING_FILE_VARIABLE']
DATABASE_FROMCATALOG=args['CATALOG_DATABASE']
SID_NAME="orcl"
CONN_TYPE="oracle"
OUTPUT_FORMAT='parquet'
OUTPUT_COMPRESSION='gzip'
MODE_METHOD_OVERWRITE='overwrite'
MODE_METHOD_APPEND='append'


RDS_MAPPING_FILE='s3://'+LANDING_ZONE_BUCKET+'/'+FIRST_FOLDER+'/'+RDS_MAPPING_FILE_VARIABLE

Conf_Df = spark.read.option("header","True").csv(RDS_MAPPING_FILE)
for row in Conf_Df.rdd.collect():
    table_name=row.asDict()['TABLE']
    schema_name=row.asDict()['SCHEMA']
    feq_info=row.asDict()['FEQ']
    is_partitioned=row.asDict()['PARTITIONED']
    connstr='CONN-IDBCDB-RDS-'+schema_name
    
    # Connection‚Ìî•ñ‚ðŽæ“¾
    jdbc_conf = glueContext.extract_jdbc_conf(connection_name=connstr)
    
    # DynamicFrame‚ðì¬
    dynamicframe = glueContext.create_dynamic_frame.from_options(
                   connection_type=CONN_TYPE,
                   connection_options={
                       'url': "{0}/{1}".format(jdbc_conf['url'], SID_NAME),
                       'user': jdbc_conf['user'],
                       'password': jdbc_conf['password'],
                       'dbtable': table_name
                   })
    
    EXPORT_DF_WITH_HEADER_DIR='s3://'+STORING_ZONE_BUCKET+'/'+FIRST_FOLDER+'/'+PROCESSED_DIR+'/'+feq_info+'/'+table_name+'/'
    
    ##########################Partition table and Non-partitioned table have different process method##########################
    if is_partitioned == 'N':
        dynamicframe.toDF().repartition(5).write.parquet(EXPORT_DF_WITH_HEADER_DIR,mode=MODE_METHOD_OVERWRITE,compression=OUTPUT_COMPRESSION)
    else:
        parkey=row.asDict()['PARTITIONKEY']
        parkey_col='parkey'
        
        try:
            DF_fromCatalog=glueContext.create_dynamic_frame.from_catalog(database = DATABASE_FROMCATALOG, table_name = table_name)
        
        ###########IF DATA DOES NOT EXSIT IN STORING ZONE, CREATE NEW ONE##################
        except AnalysisException:
            dynamicframe.toDF().registerTempTable("RDS_DF")
            QUERY = "SELECT *,date_format({}, 'YYYY-MM-dd') AS {} FROM RDS_DF".format(parkey,parkey_col)
            dynamicframe_new=spark.sql(QUERY)
            if len(dynamicframe_new.head(1)) > 0:
                dynamicframe_new.repartition(1).write.partitionBy(parkey_col).save(path=EXPORT_DF_WITH_HEADER_DIR,format=OUTPUT_FORMAT,mode=MODE_METHOD_OVERWRITE,compression=OUTPUT_COMPRESSION)
        
        ###########IF DATA DOES  EXSIT IN STORING ZONE, ONLY APPEND NEW PARTITION##################
        else:
            dynamicframe.toDF().registerTempTable("RDS_DF")
            DF_fromCatalog.toDF().registerTempTable("CATALOG_DF")
            ##########################COMPASS LOG TABLES SHOULD BE THE DAY BEFORE TODAY ##########################
            QUERY = "SELECT *,date_format({}, 'YYYY-MM-dd') AS {} FROM RDS_DF WHERE {} >(select max({}) from CATALOG_DF)".format(parkey,parkey_col,parkey,parkey)
            dynamicframe_new=spark.sql(QUERY)
            if len(dynamicframe_new.head(1)) > 0 :
                dynamicframe_new.repartition(1).write.partitionBy(parkey_col).save(path=EXPORT_DF_WITH_HEADER_DIR,format=OUTPUT_FORMAT,mode=MODE_METHOD_APPEND,compression=OUTPUT_COMPRESSION)
