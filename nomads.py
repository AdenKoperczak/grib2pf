
import requests
from datetime import datetime, timedelta, UTC



# https://nomads.ncep.noaa.gov/pub/data/nccf/com/rtma/prod/rtma2p5_ru.20250606/rtma2p5_ru.t2045z.2dvarges_ndfd.grb2
RTMA2P5_RU_BASE_URL = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/rtma/prod/rtma2p5_ru.{date}/rtma2p5_ru.t{time}z.2dvaranl_ndfd.grb2"
RTMA2P5_RU_LIST_URL = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/rtma/prod/rtma2p5_ru.{date}"
def rtma2p5_ru_get_url(time = None):
    if time is None:
        time = datetime.now(UTC) - timedelta(minutes=15)

    time = time.replace(microsecond = 0,
                        second = 0,
                        minute = time.minute - (time.minute % 15))

    url = RTMA2P5_RU_BASE_URL.format(date = time.strftime("%Y%m%d"),
                                     time = time.strftime("%H%M"))

    try:
        listed = requests.get(RTMA2P5_RU_LIST_URL.format(
            date = time.strftime("%Y%m%d")))
    except:
        return None

    if listed.ok and url.split("/")[-1] in listed.content.decode("utf-8"):
        return url
    return None
