# Intro Modern Serve-less DaLake system 

I wrote this code in here jusr for technical discussion, there ia no privacy or sentive data at all.

Considering data vloume from many channels as well as need to convert them into parquet format for reading effeciently, chose to use Pyspark which can easily and effecitvly ingest and convert CSV file to Parquet file.

As for work-flow tool, I chose to use Stepfunction with Glue ETL service, realized compeletly server-less framework.

Here is a diagram describing how this system work on AWS

<img width="1030" alt="add-my-username" src="https://user-images.githubusercontent.com/18093541/datalake-flow.png">
