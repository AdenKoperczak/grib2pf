
import requests
from datetime import datetime, timedelta



# https://nomads.ncep.noaa.gov/pub/data/nccf/com/rtma/prod/rtma2p5_ru.20250606/rtma2p5_ru.t2045z.2dvarges_ndfd.grb2
RTMA2P5_RU_BASE_URL = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/rtma/prod/rtma2p5_ru.{date}/rtma2p5_ru.t{time}z.2dvaranl_ndfd.grb2"
def rtma2p5_ru_get_url(time = None):
    if time is None:
        time = datetime.now() - timedelta(minutes = 17)

    time = time.replace(microsecond = 0,
                        second = 0,
                        minute = time.minute - (time.minute % 15))

    return RTMA2P5_RU_BASE_URL.format(date = time.strftime("%Y%m%d"),
                                      time = time.strftime("%H%M"))
