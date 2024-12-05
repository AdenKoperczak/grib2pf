#!./venv/bin/python

import boto3
from botocore import UNSIGNED
from botocore.config import Config
import time

class AWSHandler:
    def __init__(self, product, bucketName = "noaa-mrms-pds", config = None):
        if config is None:
            config = Config(signature_version = UNSIGNED)

        self.product       = product
        self.bucketName    = bucketName
        self.client        = boto3.client("s3", config=config)
        self.mostRecentKey = None

    def update_key(self):
        now = time.gmtime()
        args = {
            "Bucket": self.bucketName,
            "Prefix": self.product + time.strftime("%Y%m%d/", now)
        }
        if self.mostRecentKey is not None:
            args["StartAfter"] = self.mostRecentKey

        pager = self.client.get_paginator("list_objects_v2")
        pages = pager.paginate(**args)

        mostRecent = None
        for page in pages:
            if 'Contents' not in page:
                continue

            last = page["Contents"][-1]
            if mostRecent is None or last["LastModified"] > mostRecent["LastModified"]:
                mostRecent = last

        if mostRecent is not None:
            self.mostRecentKey = mostRecent["Key"]

        return mostRecent is not None

    def get_url(self, expires = 60):
        return self.client.generate_presigned_url(
                'get_object',
                Params = {
                    'Bucket': self.bucketName,
                    'Key': self.mostRecentKey,
                },
                ExpiresIn = expires,
                )

if __name__ == "__main__":
    def test():
        handler = AWSHandler("CONUS/MergedBaseReflectivity_00.50/")
        handler.update_key()
        print(handler.get_url())
        while not handler.update_key():
            time.sleep(10)

        print(handler.get_url())

    test()
