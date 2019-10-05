# Brief intro of Modern Server-less DaLake system 

I produced sets of code in here just for technical discussion, there is no privacy or sensitive data at all.

Considering huge data volume from many channels as well as need to convert them into parquet format for reading efficiently, chose to use Pyspark which can easily and effectively ingest and convert CSV file to Parquet file.

As for work-flow tool, I chose to use Stepfunction with Glue ETL service, realized completely server-less framework.


Briefly explain the function of each code.

<B>DATALAKE_TRANSFORMATION_S3_DAILY_JOB.PY</B>

The most critical function over Datalake system, it's resposible for ingesting data from landing zone, and store processed parquet data to storing zone.

For better perfomance, I leveraged multiprocessing tech of Python, which helped programe fully utilized resource. be cafefull about setting numbers of processes, it should be according to the number of DPU.

For not processing data duplicately, list of processed data is stored and will compare to new target when script start each time. 

<B>SYNC_BUCKET_STORING_TO_USER_DAILY_JOB.PY</B>

This function is reposible for copying data from bucket to another bucket for different users.

<B>RUN_CRAWLER_JOB.PY</B>

This a common function which is resposible for running data-discovery procedure, data is suppoesed to be catalog for post process.

<B>OUTPUT_METADATA_DDL_WEEKLY_JOB.PY</B>

A backup script using to backup list of processed files as well as meta data of tables (after data-discovery)


Here is a diagram describing how this system works on AWS
<img width="1030" src="https://github.com/liang-wu-1985/DataLake_Ingestion_System/blob/master/images/datalake-flow.png?raw=true">
1	The Data in Landing Zone is from UDM server which is located in CoreIT. In this step, raw data without headers will be process by ETL job.

2	After raw data is processed, rich data will go to Storing Zone, this zone store all data regardless of applications, so access is strictly restricted

3	Refer to mapping information and decide data will flow to which User Zone.

4	Requested as well as authorized data will go to each User Zone. (Basically One Application One Bucket)

5	Catalog tables to central glue catalog for Storing Zone (tables discovery)

6	Catalog tables to central glue catalog for User Zone, users of each application are able to see table definitions through this step.

7	Workbench (SQL connector) and BI Tools (Tableau etc) are connected to AWS data through Athena (using JDBC driver)

8	Backup metadata and config files regularly

9	Provide access to EMR and Redshift service etc in the future
