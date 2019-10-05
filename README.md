# Brief intro of Modern Serve-less DaLake system 

I wrote sets of code in here just for technical discussion, there is no privacy or sensitive data at all.

Considering huge data volume from many channels as well as need to convert them into parquet format for reading efficiently, chose to use Pyspark which can easily and effectively ingest and convert CSV file to Parquet file.

As for work-flow tool, I chose to use Stepfunction with Glue ETL service, realized completely server-less framework.

Here is a diagram describing how this system work on AWS

<img width="1030" src="https://github.com/liang-wu-1985/DataLake_Ingestion_System/blob/master/images/datalake-flow.png?raw=true">
