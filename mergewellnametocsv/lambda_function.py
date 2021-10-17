import os
import boto3
import csv
import sys
import io
from datetime  import datetime
import logging
import pymysql
import pandas as pd


#logger settings
loglevel=os.environ["LOGLEVEL"]
logger = logging.getLogger()
if loglevel =='INFO' :
    logger.setLevel(logging.INFO)
elif loglevel == 'DEBUG' :
    logger.setLevel(logging.DEBUG)
else :
   logger.setLevel(logging.NOTSET)


#rds settings
rds_host=os.environ["HOSTNAME"]
name=os.environ["DBUSER"]
password=os.environ["DBPWD"]
db_name=os.environ["DBNAME"]

    
#Create connection to MySQL
try:
    conn = pymysql.connect(host=rds_host, user=name, passwd=password, db=db_name, connect_timeout=5)
except pymysql.MySQLError as e:
    logger.error("ERROR: Unexpected error: Could not connect to MySQL instance.")
    logger.error(e)
    sys.exit()
logger.debug ('Success connection')
logger.info("SUCCESS: Connection to RDS MySQL instance succeeded")

def lambda_handler(event, context):
    logger.debug(event)
    try:
        
        #Get input file details and set output file details
        input_bucket_name = event["Records"][0]["s3"]["bucket"]["name"]
        input_s3_file_name = event["Records"][0]["s3"]["object"]["key"]
        output_bucket_name=os.environ["OUTPUT_BUCKET"]
        output_s3_file_name=input_s3_file_name
        logger.debug(input_bucket_name)
        logger.debug(input_s3_file_name)
        
        #Read CSV from S3 into Pandas
        s3_client = boto3.client('s3')
        resp = s3_client.get_object(Bucket=input_bucket_name, Key=input_s3_file_name)
        logger.debug("Before reading into pandas")
        df= pd.read_csv(resp['Body'], sep=',')
        logger.debug("Values in pandas dataframe")
        logger.debug(df.head(2))
        
        #Extract data from input file
        for col in df.head(1):
            if 'client_name' in df.columns :
                clientname=''.join(df.client_name.unique())
            if 'rig_name' in df.columns :
                rigname=''.join(df.rig_name.unique())
            if 'job_date' in df.columns :
                jobdate=datetime.strptime(''.join(df.job_date.unique()),"%m/%d/%Y").strftime("%Y-%m-%d")
           
        
        logger.debug( "The client_name in file is "+clientname)
        logger.debug( "The rig_name in file is "+rigname)
        logger.debug( "The job_date in file is "+jobdate)
        
       
        #Build the sql for RDS to fetch well_name
        sqlstmt=f"select well_name from mydb.client_master where client_name like '%" +clientname +"%' and rig_name like '%"+rigname+"%' and job_date='"+jobdate+"'"
        
        logger.debug('Before query for filter match')
    
        #Count for duplicates in RDS
        item_count = 0

        #Query RDS using sql statement above
        with conn.cursor() as cur:
            logger.debug(sqlstmt)
            cur.execute(sqlstmt)
            for row in cur:
             item_count += 1
             logger.info(row)
             wellname=row[0]
             logger.debug('The well name is '+wellname)
             logger.debug('Fetched '+str(item_count)+' rows')

        logger.debug('After query for filter match')
        
        if  wellname != "" :
            #Add well_name column to pandas
            df["well_name"]=wellname
            logger.debug(df.head(5))
            logger.debug(df.well_name.unique())
        else :
            df["well_name"]=wellname
            logger.error('Missing well_name for client_name '+clientname + ' rig_name '+rigname+' job_date '+jobdate+' in RDS')
        
        csv_buffer=io.StringIO()
        df.to_csv(csv_buffer,index=False)
        response = s3_client.put_object(
            Bucket=output_bucket_name,Key=output_s3_file_name,Body=csv_buffer.getvalue())
        logger.info(response)

    except Exception as err:
        logger.error(err)