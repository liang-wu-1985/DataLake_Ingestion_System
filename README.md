# Brief intro of Modern Serve-less DaLake system 

I wrote sets of code in here jusr for technical discussion, there ia no privacy or sentive data at all.

Considering huge data vloume from many channels as well as need to convert them into parquet format for reading effeciently, chose to use Pyspark which can easily and effecitvly ingest and convert CSV file to Parquet file.

As for work-flow tool, I chose to use Stepfunction with Glue ETL service, realized compeletly server-less framework.

Here is a diagram describing how this system work on AWS

<img width="1030" src="https://github.com/liang-wu-1985/DataLake_Ingestion_System/blob/master/images/datalake-flow.png?raw=true">
