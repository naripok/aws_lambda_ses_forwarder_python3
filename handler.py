import email
import json
import logging
import os
import re

import boto3
from botocore.exceptions import ClientError

#  FORWARD_MAPPING = {recipient: os.environ.get('MSG_TO_LIST') for recipient in os.environ.get('MSG_TARGET')}

with open('mapping.json', 'r') as f:
    FORWARD_MAPPING = json.load(f)
VERIFIED_FROM_EMAIL = os.environ.get('VERIFIED_FROM_EMAIL', 'tau@megali.co.uk')  # An email that is verified by SES to use as From address.
SUBJECT_PREFIX = os.environ.get('SUBJECT_PREFIX') # label to add to a list, like `[listname]`
SES_INCOMING_BUCKET = os.environ['SES_INCOMING_BUCKET']  # S3 bucket where SES stores incoming emails.
S3_PREFIX = os.environ.get('S3_PREFIX', '') # optional, if messages aren't stored in root

s3 = boto3.client('s3')
ses = boto3.client('ses')

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)


def handler(event, context):
    record = event['Records'][0]
    assert record['eventSource'] == 'aws:ses'

    o = s3.get_object(Bucket=SES_INCOMING_BUCKET, Key=S3_PREFIX+record['ses']['mail']['messageId'])
    raw_mail = o['Body'].read()
    logger.info("body: {}".format(type(raw_mail)))
    #msg = raw_mail
    msg = email.message_from_bytes(raw_mail)
    logger.info("m: {}".format(msg))

    del msg['DKIM-Signature']
    del msg['Sender']
    del msg['Return-Path']
    del msg['Reply-To']

    logger.info("keys: {}".format(msg.keys()))
    logger.info("from: {}".format(msg['From']))
    #original_from = msg['From']
    #del msg['From']
    #msg['From'] = re.sub(r'\<.+?\>', '', original_from).strip() + ' <{}>'.format(VERIFIED_FROM_EMAIL)

    msg['Reply-To'] = VERIFIED_FROM_EMAIL
    msg['Return-Path'] = VERIFIED_FROM_EMAIL

    logger.info("subject prefix: {}".format(SUBJECT_PREFIX))
    if SUBJECT_PREFIX and SUBJECT_PREFIX.lower() not in msg.get('Subject').lower():
        new_subj = ' '.join([SUBJECT_PREFIX, msg.get('Subject', '')])
        del msg['Subject']
        msg['Subject'] = new_subj
        logger.info("new subj: {}".format(msg['Subject']))

    msg_string = msg.as_string()

    for recipient in record['ses']['receipt']['recipients']:
        logger.info("recipient: {}".format(recipient))
        forwards = FORWARD_MAPPING.get(recipient, '')
        if not forwards:
            logger.warning('Recipent <{}> is not found in forwarding map. Skipping recipient.'.format(recipient))
            continue

        for address in forwards.split(','):
            logger.info("addr: {}".format(address))

            try:
                o = ses.send_raw_email(Destinations=[address], RawMessage=dict(Data=msg_string))
                logger.info('Forwarded email for <{}> to <{}>. SendRawEmail response={}'.format(recipient, address, json.dumps(o)))
            except ClientError as e: logger.error('Client error while forwarding email for <{}> to <{}>: {}'.format(recipient, address, e))

