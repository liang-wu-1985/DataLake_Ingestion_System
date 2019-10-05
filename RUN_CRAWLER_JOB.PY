################JOB_NAME:RUN_CRAWLER_JOB                            #################
#################Author  :Liang Wu                                  #################
#################Version :1.0.0                                     #################


# -*- coding: utf-8 -*-
import argparse
import logging
import sys
from time import sleep
import boto3

# Setup logger
fmt = "%(asctime)s %(levelname)s %(message)s"
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter(fmt=fmt))
LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
LOGGER.addHandler(handler)

# Setup glue client
glue_client = boto3.client('glue')


def get_args():
    parser = argparse.ArgumentParser()
    # crawler is glue crawler name
    parser.add_argument("--crawler", type=str, required=True)

    # parse_known_args return (known_args, unknown_args)
    args, _ = parser.parse_known_args()
    return args


def start_crawler(crawler_name):
    glue_client.start_crawler(
        Name=crawler_name
    )


def get_crawler(crawler_name):
    resp = glue_client.get_crawler(
        Name=crawler_name
    )
    return resp


def is_ready(resp):
    state = resp['Crawler']['State']
    if state in ['READY']:
        return True
    return False


def is_succeeded(resp):
    last_state = resp['Crawler']['LastCrawl']['Status']
    if last_state in ['SUCCEEDED']:
        return True
    return False


def logging_crawler_error(resp):
    last_state = resp['Crawler']['LastCrawl']['Status']
    message = resp['Crawler']['LastCrawl']['ErrorMessage']
    LOGGER.error("Failed to crawl, Status: %s, Message: %s\n",
                 last_state, message)


def wait_for_crawler_until_ready(crawler_name):
    while(True):
        resp = get_crawler(crawler_name)
        if is_ready(resp):
            return resp
        sleep(10)


def main():
    args = get_args()
    crawler_name = args.crawler

    LOGGER.info("Wait until READY before starting crawler: %s\n", crawler_name)
    wait_for_crawler_until_ready(crawler_name)
    LOGGER.info("Start glue crawler: %s\n", crawler_name)
    start_crawler(crawler_name)
    LOGGER.info("Wait for crawler to complete: %s\n", crawler_name)
    resp = wait_for_crawler_until_ready(crawler_name)

    if not is_succeeded(resp):
        logging_crawler_error(resp)
        exit(1)
    LOGGER.info("Succeeded to crawl")


if __name__ == '__main__':
    main()
