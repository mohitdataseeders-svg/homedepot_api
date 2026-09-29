import json, os, requests, hashlib
import re
from ctypes.wintypes import VARIANT_BOOL
from datetime import datetime
from parsel import Selector
from colorama import Fore, init
# from db_config import *
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from pymongo import MongoClient
init(autoreset=True)
client = MongoClient('mongodb://localhost:27017/')
db = client["homedepot"]
store_category_data = db[f"products_PL"]
collection_product_details = db[f"products_Details_28_09_2026"]
# ── CONFIG ────────────────────────────────────────────────────────────
INSERT_DATE = datetime.today().strftime("%d_%m_%Y")
dire_pdp    = fr"D:\pagesave\homedepot\PDP\{INSERT_DATE}"
dire_pdp_json    = fr"D:\pagesave\homedepot\PDP_json\{INSERT_DATE}"
os.makedirs(dire_pdp, exist_ok=True)
os.makedirs(dire_pdp_json, exist_ok=True)

# collection_product_details.create_index('hashid_prod', unique=True)

# product_links = list(store_category_data.find({"status": "pending"}))
product_links = list(store_category_data.find({"status": "Pending"}))

import requests
cookies = {
    'AMCV_F6421253512D2C100A490D45%40AdobeOrg': 'MCMID|05563600488261144804549567835986824428',
    '_pxvid': '8bed3296-b66a-11f1-943e-98ade75dd7b8',
    'THD_PERSIST': '',
    'THD_CACHE_NAV_PERSIST': '',
    'thda.u': '62eeaee5-8d89-58e9-0277-3bebc77982fa',
    '_px_f394gi7Fvmc43dfg_user_id': 'OGU1NjExZjEtYjY2YS0xMWYxLThiZGMtYzE5ZjlhMzYxMTk5',
    'ajs_anonymous_id': '1cb49a76-22b3-4e79-81f8-4e21b44893e1',
    'QuantumMetricUserID': '4b7d87adb633d2c42ad951700707fc4a',
    '_gcl_au': '1.1.1103530001.1790070424',
    'forterToken': '5c40d01bbaf9489abb35afc99ac7355a_1790072267241__UDF4_31ck',
    'trx': '7893031757143069665',
    'QSI_SI_3pIUG1VWoD316xo_intercept': 'true',
    'DELIVERY_ZIP': '30006',
    'DELIVERY_ZIP_TYPE': 'USER',
    'trx': '7893031757143069665',
    '_ga_9H2R4ZXG4J': 'GS2.1.s1790158800$o3$g0$t1790158810$j60$l0$h0',
    '_ga': 'GA1.1.1201453411.1790070420',
    'HD_DC': 'origin',
    'akacd_usbeta': '3968029760~rv=94~id=e558b4447b791b4721a459acdfff3dbc',
    '_bman': '58cf8d644ed916c0b00d94f1163dd767',
    'THD_NR': '1',
    '_abck': '15D1FD00C081A6173F837A6C882F4B64~0~YAAQoEY5F6Odc9SgAQAAWzC05hANykTCH/MQlIDanooGiKNEdluLcIhQ1b0dhLDanteLTZljkmgzVhWEvsDPq9huL7HoVCZpAfaNjeb9BurWiYoQYaEblHV6Pe9B/OEw894IcxZVsG3ER/5RF2V0j2eyyW1uMjkwlnP52EFGVjwz8uUzKdtV+Q5ufaQ6JlLhQRzy+eIvpzXtKqMYVSiLN6bgFp7BO0y5q7NLhetHfYa03OhM/SVVTsCN2KKCcKraBL8mBvqqr/geLHZ42+bsuQWHzdF4X+FPIIUkE1xCsuuPt/JrwaudNR3S2Qc1x7EWulZhxtJWwSFPYHzgFyy/0pTkpYXErIDoSuH5E+bMd5fDksl3NyBz3vYAiFilrbRvh1IW3D+EnPfUnn63RIGLx8ALWgg0rpwKOGxeST/1W41xE9xhTTGE1AZaFf4IJpeflyrCelIHSP6Jo3rQ6we0RgMVrBZsmoAcTU7Vc30zyHZ3qr+SNFeqmUigDF7pf0XcC2ZF32HSuduol6TQCQEVMJV3Gx71SkmVwX6K3YBPJroWX5SX+tc5+f2hoPzA/rERxAJz7fPzNTnuNOUseYsujjHXCeFtUFyxx5iHjjcKidoRDT04VtorF75NgjOTNYdRkaOpaaflntZro2bXIZjIvCOsMhg=~-1~-1~-1~AAQAAAAG%2f%2f%2f%2f%2f4iPVax3lhFLoe7rNcJ6IOjjLdF1NjVl1+g3wU1%2f9dGTZv2x5oOyuS3OoHzEkEzMipkv1dl+WGI6J6CGyDFR+UwCmZNs6l0yoSTP~-1',
    'kndctr_F6421253512D2C100A490D45_AdobeOrg_identity': 'CiYwNTU2MzYwMDQ4ODI2MTE0NDgwNDU0OTU2NzgzNTk4NjgyNDQyOFIQCJ3n0LWONBgBKgNWQTYwA_ABnefQtY40',
    'x-maa-ttsearch': 'maalctestv1',
    'x-maa-ttSpON': 'yes',
    'x-maa-ttpageExclusion': 'true',
    'THD_SESSION': '',
    'THD_CACHE_NAV_SESSION': '',
    'THD_LOCALIZER': '%7B%22WORKFLOW%22%3A%22LOC_HISTORY_BY_IP%22%2C%22THD_FORCE_LOC%22%3A%221%22%2C%22THD_LOCSTORE%22%3A%226175%2BManhattan%20West%2023rd%20St%20-%20New%20York%2C%20NY%2B%22%2C%22THD_STRFINDERZIP%22%3A%2210010%22%2C%22THD_STORE_HOURS%22%3A%221%3B8%3A00-20%3A00%3B2%3B7%3A00-21%3A00%3B3%3B7%3A00-21%3A00%3B4%3B7%3A00-21%3A00%3B5%3B7%3A00-21%3A00%3B6%3B7%3A00-21%3A00%3B7%3B7%3A00-21%3A00%22%2C%22THD_STORE_HOURS_EXPIRY%22%3A1790580568%2C%22THD_INTERNAL%22%3A%220%22%7D',
    'thda.s': 'eb8dd1d3-2985-b429-9b47-d594389a44f6',
    'pxcts': 'f5a34cb7-bb05-11f1-a8e3-a084f2f1d7fd',
    'ads': '9c1e45381f1c15b7cb396626de062561',
    'QuantumMetricSessionID': '4b691c6d017a4312a85c2896d49f9ea5',
    'QSI_HistorySession': 'https%3A%2F%2Fwww.homedepot.com%2Fc%2Fappliance-sales~1790577015397%7Chttps%3A%2F%2Fwww.homedepot.com%2Fb%2FAppliances-Washers-Dryers-Washer-Dryer-Sets%2FSpecial-Values%2FN-5yc1vZ2fkpgvtZ7%3FNCNI-5~1790577021048%7Chttps%3A%2F%2Fwww.homedepot.com%2Fp%2Fsets%2FGE-Hotpoint-4-0-cu-ft-Top-Load-Washer-and-6-2-cu-ft-vented-Gas-Dryer-in-White%2F344323894~1790577024559',
    'salsify_session_id': '834902fd-4646-419d-abb5-6cf582b40f8e',
    'forterToken': '5c40d01bbaf9489abb35afc99ac7355a_1790578668594__UDF43-m4_31ck_',
    'akavpau_prod': '1790580468~id=29040cee0a3c40598ab971f67188cb24',
    'bm_sz': '7C7DD50219C73BBC5E429CA992BBB8C6~YAAQM1nIF7bOd52gAQAAJRfl5gFKPA7wqkT32wHUPCU4S1Syi/PliI9DBJN0kbEmyISLrPJgA9/FrcFIF7pjoTcS7FNjx08tagd67EwnPtQ9GO6Oom65qh15+xKMteXN7Kcvvf5Hrzi5f+ZptyZ73OvHkAYdAMD45PlpAjoKwMaew7eg0KWdtISYpu0iI5hE3gRUfe4CVxlVMhL8h3XomR4Ul+2ce7UGCV/46zr2QTKctEo9VlygLPLhChnR+Cpletsy2vJaFSNHeLrr6cFbiDVenKCB6Hkaqe3T6twKWGUX6LHjIaJK/Ks1+xOzdm1chNtdlE2ugvQOZBJcV2WzycAhRxotQWZGZnMX/pM6xAJEkWu2z/SE8Op5rnlzajBp3nq+2d8PiswL2vDxRN+DwqoHprd6rBnktuGRc0kmxxaH9zhy8KLMW9ttwnXwlSqzk4SoAjGfG/bhPvEdaxanCOGes337715a/qaxZ1q8NH/WLMRIYDSCE6s3o5nTZiaWfSkIpMs5NT/Mxn0p/rOfiQ==~3551544~4600116',
    '_px2': 'eyJ1IjoiZThhZjJjMTAtYmIwOS0xMWYxLWE5MDctNDc4YTUwZDZjYjZkIiwidiI6IjhiZWQzMjk2LWI2NmEtMTFmMS05NDNlLTk4YWRlNzVkZDdiOCIsInQiOjE1Mjk5NzEyMDAwMDAsImgiOiJmZjUzMjZlMmNkMDRiMzcxYjRkYWJmNzRlMjBlN2U1Y2IzMDg1NDNjNzI1ZGFjMzYyMmRiOTQyYmNkOGI0OWYzIn0=',
    '_pxde': '17968f7824faec2829f6853545b27886b49ae5d7232b67552d7ed5178cc741d9:eyJ0aW1lc3RhbXAiOjE3OTA1ODAyNzk3MDZ9',
    'AKA_A2': 'A',
    'bm_so': '54A1147B8E891951BB4DD241DEB93FBBCAB7288C7360F36244F6DDB0450CF85B~YAAQLFnIFy/seZ6gAQAAwVMK5wmn/LI8HMHv+/fr8d1Rx2pixdxKGQddtVx4i55CGIMVzCkfz6uDbDBBFK///CaMTncFwzYZGB8ACjwjbMu/hUA2Q2YP82Ui5/PfeToKOjwYw+XzrcZcvg3nHkog0DJbAfpjr7I1B8oet81fV1NRikqaQjsD5VJ2MUNBgL/oOSDdUxxhp2pxe2ahyiE9qoiqG2fDIJEKCYOJMIFDi6mEm4VTGY4zAEGOdDacmL82W5i+KnZxzCuW/4Qf70MnKhsg7p+yMYgg3UjHOznj8G/shmSD+ogRe4Jx4xPSkxFd8gpnoc5/hhA5FMnHCjJZ/91ELAOTkTrLtTRK3WaqKpdawZk2hI3P8P90pUwIHL1O6/RDq7XRQYM0y0B34g6Y3Z9u5HNzQqWrAIi2WhMoIICULcvC2UVf7CqJu0JPFbWwpBppSRSvzA07j6/VaQBzkwQtCX6/y11NregIqz92~4',
    'RT': '"z=1&dm=www.homedepot.com&si=7658c62b-1666-40ff-b192-1d8c0a5163df&ss=mukvah6t&sl=8&tt=365&obo=7&rl=1&ld=3d2jp&r=1apx5qbv2&hd=3d2jp"',
    'bm_lso': '54A1147B8E891951BB4DD241DEB93FBBCAB7288C7360F36244F6DDB0450CF85B~YAAQLFnIFy/seZ6gAQAAwVMK5wmn/LI8HMHv+/fr8d1Rx2pixdxKGQddtVx4i55CGIMVzCkfz6uDbDBBFK///CaMTncFwzYZGB8ACjwjbMu/hUA2Q2YP82Ui5/PfeToKOjwYw+XzrcZcvg3nHkog0DJbAfpjr7I1B8oet81fV1NRikqaQjsD5VJ2MUNBgL/oOSDdUxxhp2pxe2ahyiE9qoiqG2fDIJEKCYOJMIFDi6mEm4VTGY4zAEGOdDacmL82W5i+KnZxzCuW/4Qf70MnKhsg7p+yMYgg3UjHOznj8G/shmSD+ogRe4Jx4xPSkxFd8gpnoc5/hhA5FMnHCjJZ/91ELAOTkTrLtTRK3WaqKpdawZk2hI3P8P90pUwIHL1O6/RDq7XRQYM0y0B34g6Y3Z9u5HNzQqWrAIi2WhMoIICULcvC2UVf7CqJu0JPFbWwpBppSRSvzA07j6/VaQBzkwQtCX6/y11NregIqz92~4~1790582611091',
    'bm_s': 'YAAQLFnIF8LteZ6gAQAAwF0K5wb4GQYLaUZzqlJlaepZo9yo9HgoihhvfldpzxtYsLXcUMf0wEoyH8FdiJtLiCt5g6ppFwjtE+62GPN63HYMt46RpMDTGKKs8ip1YCJcrdRyHdKEEvT++uu6TmKs3vF+bex46CV1D1Lz0rgcbOrW0+idGZPPvdF0FbWdSWMBAfPDZTQueyn/vTYaEB/4duitcV/Is/swpg79TS4f48H0YTa+YS6mBYD1sU+Ja7YHWl7sc6B7JOaLIEj8/elMSNIS4QlAQvAN3srt3sRV+l708AkGGU71YhLy4al74wPCl3Etvqi3EFm8fLzni8kO8u0gbxTa2npiCRj2HrWQ0M/EWW25zXxYr6bV87keT1Wmm1NBdhTkSD8ALW5q35b14TW6pBojMt6bnr+/eUgXL+p33YdQoN4+qmuhrBhs4Q9xo7wQtituLJcSto14JZbeFZ6qzznYz+6VQPqAQk5dbK5E5Gkm4IijX0gSaeB3mcRgmx4cLzV5LM2Al2184TeERx0J+YII5TOaMgpjK66+WbdxIA/mYO5forYg+MbyH3ZtZFdDonGF1jHWoxr8KOXER2J4Gy70WG0d+Geq/45qeo0vOCbO7vTfvagFtkXW8jW+H/J8a//PJJ3HnkJclo8dFLCOtDWusrsNAdl3Xpx5xVC4h75JVHZ83bLfFfwfBYGZxKiwjvT1p94ddn+eaUGvSFD5tM0/O219r0HHiy0Y9FkYFZqG9mC6AKDpVgjCdGF5zXF/zPClTciKHT+BaJW7lj+twOXa7coE5icNAlU7YEtyv1O4ah4VnOw1JyxO2v05WnEcZsWpHsxycsmA0awYNyZgHfdouqDwHwHvdBgse/Cp7vatU+xGkZdx2V1NHo6I8iF2OpVrIiEamiHe2LlfC/ma9bhgK7L7L1DtZswka2zPN7s9u2KOcLz221aJnh71jhDa1yCTcQGiTFvvUSJDXVzU4sQmk/lk2yefdHHrD4PEdNpQrXw7uf1dwuC+A1LOQE2syXOThERztqgfo+A4QaWOe+ytY97i8FLwhcrJruqNYT8kK66io1r1RCuVZsIg8cg=',
    'bm_sc': '2~1~879802618~YAAQLFnIF8PteZ6gAQAAwF0K5wk1KJ7yfgkxX21aqL4W8XQccax5A9BqV2K+tBrezlzRTWWB+YV5wB1UOQda0ggeBBaKE54Gyt+vK6OsTfWikLgMyAJe4oCBzLVGuV5CvR3/zTMICqBuhEBuZ1dte7CEG1efnRg+TKQqHdPyum74yz+T02YG+1SVgeVU/lwAGH9tXFeuSHE37CDOoRGiPbcUZLjOKiYS7sqDXJ79jTG17pP0C8Tm4E9bkiDXmWHKqw1FNgP8zuaCqmO+1TBVbHq8JzSpbiGAAUutUA51MBtmybiuZ4a5lCBFrI92EBkm0n2IRzFneOxUOw2T2MqDPdCynY8pKnFSU7gNkJy+czHA4B4XgFqDdmCbWnerrRibt/b+Ea4f+5mO7rEm2SG4K7fKHcM76iLPsJSMQzUOKHteSDSDLnk5NMcgLZRikVB/F/qHTU6Wh8SRK2tBdxFhfCYesyeJi7p6IVTiYD2k05AOaHlAZtOw2ezmxuLfJ1l09wJzDaAgJAOaOYNkK7oupbSyWrgn9XgGWQQVdAGIli1y16LmYqYOUdxnrUUGSFjJS6VtWRBH+DPzc9/8iVIHqQefB3rbTy1iqoMRmMCWBQnYhbILuLxrWxHJSQdIKIxUxLgM1N1gGzQLl75Wf+SgIpwaPoE3lV68dxs5nmeHaPLfZdqEJ/Z3mkP89yInRhdV3q6N1EFukZVUAdiYGRy+zczmvRGECOGF2Nei17KwB20gTl4kMiOoN78FmJsBWzOIS4AlG+xMeZNRXs+CCPtxg1ZEXulTWJQ3yJRln6JVlJl3hlrYXd5WIRtoIB3sU56c9/3e3f3beI07faN9sQIe/R9Kont/48Q33btd2HldxkmpOHWeklRgc7TIgf+3nKJ+Xu+qqdR0ToXBAuEh7cjkp7GU8f3iWSFzGMDtkCOdQg==~0~0~0',
}

headers = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'accept-language': 'en-US,en;q=0.9',
    'cache-control': 'max-age=0',
    'priority': 'u=0, i',
    'referer': 'https://www.homedepot.com/p/sets/GE-Hotpoint-4-0-cu-ft-Top-Load-Washer-and-6-2-cu-ft-vented-Gas-Dryer-in-White/344323894',
    'sec-ch-ua': '"Chromium";v="154", "Google Chrome";v="154", "Not A(Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'same-origin',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36',
    # 'cookie': 'AMCV_F6421253512D2C100A490D45%40AdobeOrg=MCMID|05563600488261144804549567835986824428; _pxvid=8bed3296-b66a-11f1-943e-98ade75dd7b8; THD_PERSIST=; THD_CACHE_NAV_PERSIST=; thda.u=62eeaee5-8d89-58e9-0277-3bebc77982fa; _px_f394gi7Fvmc43dfg_user_id=OGU1NjExZjEtYjY2YS0xMWYxLThiZGMtYzE5ZjlhMzYxMTk5; ajs_anonymous_id=1cb49a76-22b3-4e79-81f8-4e21b44893e1; QuantumMetricUserID=4b7d87adb633d2c42ad951700707fc4a; _gcl_au=1.1.1103530001.1790070424; forterToken=5c40d01bbaf9489abb35afc99ac7355a_1790072267241__UDF4_31ck; trx=7893031757143069665; QSI_SI_3pIUG1VWoD316xo_intercept=true; DELIVERY_ZIP=30006; DELIVERY_ZIP_TYPE=USER; trx=7893031757143069665; _ga_9H2R4ZXG4J=GS2.1.s1790158800$o3$g0$t1790158810$j60$l0$h0; _ga=GA1.1.1201453411.1790070420; HD_DC=origin; akacd_usbeta=3968029760~rv=94~id=e558b4447b791b4721a459acdfff3dbc; _bman=58cf8d644ed916c0b00d94f1163dd767; THD_NR=1; _abck=15D1FD00C081A6173F837A6C882F4B64~0~YAAQoEY5F6Odc9SgAQAAWzC05hANykTCH/MQlIDanooGiKNEdluLcIhQ1b0dhLDanteLTZljkmgzVhWEvsDPq9huL7HoVCZpAfaNjeb9BurWiYoQYaEblHV6Pe9B/OEw894IcxZVsG3ER/5RF2V0j2eyyW1uMjkwlnP52EFGVjwz8uUzKdtV+Q5ufaQ6JlLhQRzy+eIvpzXtKqMYVSiLN6bgFp7BO0y5q7NLhetHfYa03OhM/SVVTsCN2KKCcKraBL8mBvqqr/geLHZ42+bsuQWHzdF4X+FPIIUkE1xCsuuPt/JrwaudNR3S2Qc1x7EWulZhxtJWwSFPYHzgFyy/0pTkpYXErIDoSuH5E+bMd5fDksl3NyBz3vYAiFilrbRvh1IW3D+EnPfUnn63RIGLx8ALWgg0rpwKOGxeST/1W41xE9xhTTGE1AZaFf4IJpeflyrCelIHSP6Jo3rQ6we0RgMVrBZsmoAcTU7Vc30zyHZ3qr+SNFeqmUigDF7pf0XcC2ZF32HSuduol6TQCQEVMJV3Gx71SkmVwX6K3YBPJroWX5SX+tc5+f2hoPzA/rERxAJz7fPzNTnuNOUseYsujjHXCeFtUFyxx5iHjjcKidoRDT04VtorF75NgjOTNYdRkaOpaaflntZro2bXIZjIvCOsMhg=~-1~-1~-1~AAQAAAAG%2f%2f%2f%2f%2f4iPVax3lhFLoe7rNcJ6IOjjLdF1NjVl1+g3wU1%2f9dGTZv2x5oOyuS3OoHzEkEzMipkv1dl+WGI6J6CGyDFR+UwCmZNs6l0yoSTP~-1; kndctr_F6421253512D2C100A490D45_AdobeOrg_identity=CiYwNTU2MzYwMDQ4ODI2MTE0NDgwNDU0OTU2NzgzNTk4NjgyNDQyOFIQCJ3n0LWONBgBKgNWQTYwA_ABnefQtY40; x-maa-ttsearch=maalctestv1; x-maa-ttSpON=yes; x-maa-ttpageExclusion=true; THD_SESSION=; THD_CACHE_NAV_SESSION=; THD_LOCALIZER=%7B%22WORKFLOW%22%3A%22LOC_HISTORY_BY_IP%22%2C%22THD_FORCE_LOC%22%3A%221%22%2C%22THD_LOCSTORE%22%3A%226175%2BManhattan%20West%2023rd%20St%20-%20New%20York%2C%20NY%2B%22%2C%22THD_STRFINDERZIP%22%3A%2210010%22%2C%22THD_STORE_HOURS%22%3A%221%3B8%3A00-20%3A00%3B2%3B7%3A00-21%3A00%3B3%3B7%3A00-21%3A00%3B4%3B7%3A00-21%3A00%3B5%3B7%3A00-21%3A00%3B6%3B7%3A00-21%3A00%3B7%3B7%3A00-21%3A00%22%2C%22THD_STORE_HOURS_EXPIRY%22%3A1790580568%2C%22THD_INTERNAL%22%3A%220%22%7D; thda.s=eb8dd1d3-2985-b429-9b47-d594389a44f6; pxcts=f5a34cb7-bb05-11f1-a8e3-a084f2f1d7fd; ads=9c1e45381f1c15b7cb396626de062561; QuantumMetricSessionID=4b691c6d017a4312a85c2896d49f9ea5; QSI_HistorySession=https%3A%2F%2Fwww.homedepot.com%2Fc%2Fappliance-sales~1790577015397%7Chttps%3A%2F%2Fwww.homedepot.com%2Fb%2FAppliances-Washers-Dryers-Washer-Dryer-Sets%2FSpecial-Values%2FN-5yc1vZ2fkpgvtZ7%3FNCNI-5~1790577021048%7Chttps%3A%2F%2Fwww.homedepot.com%2Fp%2Fsets%2FGE-Hotpoint-4-0-cu-ft-Top-Load-Washer-and-6-2-cu-ft-vented-Gas-Dryer-in-White%2F344323894~1790577024559; salsify_session_id=834902fd-4646-419d-abb5-6cf582b40f8e; forterToken=5c40d01bbaf9489abb35afc99ac7355a_1790578668594__UDF43-m4_31ck_; akavpau_prod=1790580468~id=29040cee0a3c40598ab971f67188cb24; bm_sz=7C7DD50219C73BBC5E429CA992BBB8C6~YAAQM1nIF7bOd52gAQAAJRfl5gFKPA7wqkT32wHUPCU4S1Syi/PliI9DBJN0kbEmyISLrPJgA9/FrcFIF7pjoTcS7FNjx08tagd67EwnPtQ9GO6Oom65qh15+xKMteXN7Kcvvf5Hrzi5f+ZptyZ73OvHkAYdAMD45PlpAjoKwMaew7eg0KWdtISYpu0iI5hE3gRUfe4CVxlVMhL8h3XomR4Ul+2ce7UGCV/46zr2QTKctEo9VlygLPLhChnR+Cpletsy2vJaFSNHeLrr6cFbiDVenKCB6Hkaqe3T6twKWGUX6LHjIaJK/Ks1+xOzdm1chNtdlE2ugvQOZBJcV2WzycAhRxotQWZGZnMX/pM6xAJEkWu2z/SE8Op5rnlzajBp3nq+2d8PiswL2vDxRN+DwqoHprd6rBnktuGRc0kmxxaH9zhy8KLMW9ttwnXwlSqzk4SoAjGfG/bhPvEdaxanCOGes337715a/qaxZ1q8NH/WLMRIYDSCE6s3o5nTZiaWfSkIpMs5NT/Mxn0p/rOfiQ==~3551544~4600116; _px2=eyJ1IjoiZThhZjJjMTAtYmIwOS0xMWYxLWE5MDctNDc4YTUwZDZjYjZkIiwidiI6IjhiZWQzMjk2LWI2NmEtMTFmMS05NDNlLTk4YWRlNzVkZDdiOCIsInQiOjE1Mjk5NzEyMDAwMDAsImgiOiJmZjUzMjZlMmNkMDRiMzcxYjRkYWJmNzRlMjBlN2U1Y2IzMDg1NDNjNzI1ZGFjMzYyMmRiOTQyYmNkOGI0OWYzIn0=; _pxde=17968f7824faec2829f6853545b27886b49ae5d7232b67552d7ed5178cc741d9:eyJ0aW1lc3RhbXAiOjE3OTA1ODAyNzk3MDZ9; AKA_A2=A; bm_so=54A1147B8E891951BB4DD241DEB93FBBCAB7288C7360F36244F6DDB0450CF85B~YAAQLFnIFy/seZ6gAQAAwVMK5wmn/LI8HMHv+/fr8d1Rx2pixdxKGQddtVx4i55CGIMVzCkfz6uDbDBBFK///CaMTncFwzYZGB8ACjwjbMu/hUA2Q2YP82Ui5/PfeToKOjwYw+XzrcZcvg3nHkog0DJbAfpjr7I1B8oet81fV1NRikqaQjsD5VJ2MUNBgL/oOSDdUxxhp2pxe2ahyiE9qoiqG2fDIJEKCYOJMIFDi6mEm4VTGY4zAEGOdDacmL82W5i+KnZxzCuW/4Qf70MnKhsg7p+yMYgg3UjHOznj8G/shmSD+ogRe4Jx4xPSkxFd8gpnoc5/hhA5FMnHCjJZ/91ELAOTkTrLtTRK3WaqKpdawZk2hI3P8P90pUwIHL1O6/RDq7XRQYM0y0B34g6Y3Z9u5HNzQqWrAIi2WhMoIICULcvC2UVf7CqJu0JPFbWwpBppSRSvzA07j6/VaQBzkwQtCX6/y11NregIqz92~4; RT="z=1&dm=www.homedepot.com&si=7658c62b-1666-40ff-b192-1d8c0a5163df&ss=mukvah6t&sl=8&tt=365&obo=7&rl=1&ld=3d2jp&r=1apx5qbv2&hd=3d2jp"; bm_lso=54A1147B8E891951BB4DD241DEB93FBBCAB7288C7360F36244F6DDB0450CF85B~YAAQLFnIFy/seZ6gAQAAwVMK5wmn/LI8HMHv+/fr8d1Rx2pixdxKGQddtVx4i55CGIMVzCkfz6uDbDBBFK///CaMTncFwzYZGB8ACjwjbMu/hUA2Q2YP82Ui5/PfeToKOjwYw+XzrcZcvg3nHkog0DJbAfpjr7I1B8oet81fV1NRikqaQjsD5VJ2MUNBgL/oOSDdUxxhp2pxe2ahyiE9qoiqG2fDIJEKCYOJMIFDi6mEm4VTGY4zAEGOdDacmL82W5i+KnZxzCuW/4Qf70MnKhsg7p+yMYgg3UjHOznj8G/shmSD+ogRe4Jx4xPSkxFd8gpnoc5/hhA5FMnHCjJZ/91ELAOTkTrLtTRK3WaqKpdawZk2hI3P8P90pUwIHL1O6/RDq7XRQYM0y0B34g6Y3Z9u5HNzQqWrAIi2WhMoIICULcvC2UVf7CqJu0JPFbWwpBppSRSvzA07j6/VaQBzkwQtCX6/y11NregIqz92~4~1790582611091; bm_s=YAAQLFnIF8LteZ6gAQAAwF0K5wb4GQYLaUZzqlJlaepZo9yo9HgoihhvfldpzxtYsLXcUMf0wEoyH8FdiJtLiCt5g6ppFwjtE+62GPN63HYMt46RpMDTGKKs8ip1YCJcrdRyHdKEEvT++uu6TmKs3vF+bex46CV1D1Lz0rgcbOrW0+idGZPPvdF0FbWdSWMBAfPDZTQueyn/vTYaEB/4duitcV/Is/swpg79TS4f48H0YTa+YS6mBYD1sU+Ja7YHWl7sc6B7JOaLIEj8/elMSNIS4QlAQvAN3srt3sRV+l708AkGGU71YhLy4al74wPCl3Etvqi3EFm8fLzni8kO8u0gbxTa2npiCRj2HrWQ0M/EWW25zXxYr6bV87keT1Wmm1NBdhTkSD8ALW5q35b14TW6pBojMt6bnr+/eUgXL+p33YdQoN4+qmuhrBhs4Q9xo7wQtituLJcSto14JZbeFZ6qzznYz+6VQPqAQk5dbK5E5Gkm4IijX0gSaeB3mcRgmx4cLzV5LM2Al2184TeERx0J+YII5TOaMgpjK66+WbdxIA/mYO5forYg+MbyH3ZtZFdDonGF1jHWoxr8KOXER2J4Gy70WG0d+Geq/45qeo0vOCbO7vTfvagFtkXW8jW+H/J8a//PJJ3HnkJclo8dFLCOtDWusrsNAdl3Xpx5xVC4h75JVHZ83bLfFfwfBYGZxKiwjvT1p94ddn+eaUGvSFD5tM0/O219r0HHiy0Y9FkYFZqG9mC6AKDpVgjCdGF5zXF/zPClTciKHT+BaJW7lj+twOXa7coE5icNAlU7YEtyv1O4ah4VnOw1JyxO2v05WnEcZsWpHsxycsmA0awYNyZgHfdouqDwHwHvdBgse/Cp7vatU+xGkZdx2V1NHo6I8iF2OpVrIiEamiHe2LlfC/ma9bhgK7L7L1DtZswka2zPN7s9u2KOcLz221aJnh71jhDa1yCTcQGiTFvvUSJDXVzU4sQmk/lk2yefdHHrD4PEdNpQrXw7uf1dwuC+A1LOQE2syXOThERztqgfo+A4QaWOe+ytY97i8FLwhcrJruqNYT8kK66io1r1RCuVZsIg8cg=; bm_sc=2~1~879802618~YAAQLFnIF8PteZ6gAQAAwF0K5wk1KJ7yfgkxX21aqL4W8XQccax5A9BqV2K+tBrezlzRTWWB+YV5wB1UOQda0ggeBBaKE54Gyt+vK6OsTfWikLgMyAJe4oCBzLVGuV5CvR3/zTMICqBuhEBuZ1dte7CEG1efnRg+TKQqHdPyum74yz+T02YG+1SVgeVU/lwAGH9tXFeuSHE37CDOoRGiPbcUZLjOKiYS7sqDXJ79jTG17pP0C8Tm4E9bkiDXmWHKqw1FNgP8zuaCqmO+1TBVbHq8JzSpbiGAAUutUA51MBtmybiuZ4a5lCBFrI92EBkm0n2IRzFneOxUOw2T2MqDPdCynY8pKnFSU7gNkJy+czHA4B4XgFqDdmCbWnerrRibt/b+Ea4f+5mO7rEm2SG4K7fKHcM76iLPsJSMQzUOKHteSDSDLnk5NMcgLZRikVB/F/qHTU6Wh8SRK2tBdxFhfCYesyeJi7p6IVTiYD2k05AOaHlAZtOw2ezmxuLfJ1l09wJzDaAgJAOaOYNkK7oupbSyWrgn9XgGWQQVdAGIli1y16LmYqYOUdxnrUUGSFjJS6VtWRBH+DPzc9/8iVIHqQefB3rbTy1iqoMRmMCWBQnYhbILuLxrWxHJSQdIKIxUxLgM1N1gGzQLl75Wf+SgIpwaPoE3lV68dxs5nmeHaPLfZdqEJ/Z3mkP89yInRhdV3q6N1EFukZVUAdiYGRy+zczmvRGECOGF2Nei17KwB20gTl4kMiOoN78FmJsBWzOIS4AlG+xMeZNRXs+CCPtxg1ZEXulTWJQ3yJRln6JVlJl3hlrYXd5WIRtoIB3sU56c9/3e3f3beI07faN9sQIe/R9Kont/48Q33btd2HldxkmpOHWeklRgc7TIgf+3nKJ+Xu+qqdR0ToXBAuEh7cjkp7GU8f3iWSFzGMDtkCOdQg==~0~0~0',
}
def scrap_store_data(doc):
    product_name = doc.get("title", "")
    product_url = doc.get("canonicalUrl", "")
    product_id = doc.get("product_id", "")
    if product_url:
        url = 'https://www.homedepot.com'+product_url
    hash_id   = hashlib.md5(url.encode('utf-8')).hexdigest()
    File_Path = os.path.join(dire_pdp, f"{hash_id}.html")

    response_text = ''

    if os.path.exists(File_Path):
        with open(File_Path, 'r', encoding='utf-8') as f:
            response_text = f.read()
        print(f"LOCAL  {Fore.GREEN}READ{Fore.RESET} || {File_Path}")
    else:
        try:
            scraper_url = f"https://api.scrape.do/?token=3a2a479f638d400b90387691739a23e684b8ae953f9&url={url}"
            r = requests.request("GET", scraper_url, headers=headers, cookies=cookies)
            print("Credit:- ", r.headers.get('Scrape.do-Request-Cost'))

            # print(response.text)
            # r = requests.request("GET", product_url, headers=headers, data=payload)
            if r.status_code == 200 and 'Powered and protected by' not in str(r.text):
                response_text = r.text
                with open(File_Path, 'w', encoding='utf-8') as f:
                    f.write(response_text)
                print(f"SAVED  {Fore.GREEN}200{Fore.RESET} || {File_Path}")
            else:
                print(f"{Fore.RED}Failed {r.status_code} | {product_url}{Fore.RESET}")
                store_category_data.update_one(
                    {'_id': doc['_id']},
                    {'$set': {'status': f'http_{r.status_code}'}}
                )
                return
        except Exception as e:
            print(f"{Fore.RED}Fetch error: {e}{Fore.RESET}")
            store_category_data.update_one(
                {'_id': doc['_id']},
                {'$set': {'status': 'fetch_error'}}
            )
            return

    # ── Cloudflare block check ────────────────────────────────────────
    if not response_text or 'just a moment' in response_text.lower():
        print(f"{Fore.YELLOW}CF Block detected — deleting HTML{Fore.RESET}")
        if os.path.exists(File_Path):
            os.remove(File_Path)
        store_category_data.update_one(
            {'_id': doc['_id']},
            {'$set': {'status': 'cf_blocked'}}
        )
        return

    # ── Parse ─────────────────────────────────────────────────────────
    sel = Selector(text=response_text)


    try:

        j_data = sel.xpath('//script[@id="thd-helmet__script--productStructureData"]//text()').get()

        if not j_data:
            raise ValueError("No ld+json Product found")

        # ── FIX #1: j_data is already a string, not a list ───────────
        try:
            product = json.loads(j_data)
        except Exception as e:
            print(e)


        product_id = product.get("productID", "")
        sku = product.get("sku", "")
        gtin13 = product.get("gtin13", "")
        model = product.get("model", "")
        product_name = product.get("name", "")
        description  = product.get("description", "")
        color        = product.get("color", "")
        width          = product.get("width", "")
        height     = product.get("height", "")
        depth     = product.get("depth", "") or ""
        weight     = product.get("weight", "") or ""
        brand        = product.get("brand", {}).get("name", "")
        ratingValue        = product.get("aggregateRating", {}).get("ratingValue", "")
        reviewCount        = product.get("aggregateRating", {}).get("reviewCount", "")
        offers       = product.get("offers", {})
        price_str        = offers.get("price", "")
        price = float(price_str) if price_str else 0.0
        print(price)
        currency     = offers.get("currencyIso", "$")
        # tagName = product['tagName']
        # description1 = c_replace(description)
        description1 = description


        images = product ['image']
        # BASE_URL = "https://apisap.fabindia.com"

        seen = set()
        unique_urls = []

        for url in images:

            seen.add(url)
            unique_urls.append(url)

        result = " | ".join(unique_urls)
        print(result)


        # ── FIX #3: stock_status default to avoid NameError ──────────
        # availability = offers.get("availability", "")
        # stock_status = "instock" if "InStock" in availability else "outofstock"

        bread_js = sel.xpath('//script[@id="thd-helmet__script--breadcrumbStructureData"]//text()').get()
        NOS_json = json.loads(bread_js)

        breadcrumb_data = NOS_json.get('breadcrumb', {})

        breadcrumb_items = breadcrumb_data.get('itemListElement', [])

        categories = [
            item.get('item', {}).get('name', '')
            for item in breadcrumb_items
            if item.get('item', {}).get('name')
        ]

        breadcrumb = " > ".join(categories)

        category = categories[-1] if categories else ''
        print(breadcrumb)
        print(category)

        # ── EXTRA PDP HEADERS (added) ─────────────────────────────────
        # Apollo state (rich product JSON)
        apollo = {}
        try:
            apollo_txt = sel.xpath('//script[contains(text(),"window.__APOLLO_STATE__")]/text()').get() or ""
            if apollo_txt:
                start_idx = apollo_txt.find('{', apollo_txt.find('__APOLLO_STATE__'))
                apollo, _ = json.JSONDecoder().raw_decode(apollo_txt[start_idx:])
        except Exception as e:
            print(f"{Fore.YELLOW}Apollo parse warning: {e}{Fore.RESET}")

        root_q = apollo.get("ROOT_QUERY", {})
        prod_node = apollo.get(f"base-catalog-{product_id}", {})
        if not prod_node:
            prod_node = next((v for k, v in apollo.items() if k.startswith("base-catalog-")), {})

        identifiers = prod_node.get("identifiers") or {}
        info_node   = prod_node.get("info") or {}
        avail_node  = prod_node.get("availabilityType") or {}
        details_node = prod_node.get("details") or {}
        taxonomy_node = prod_node.get("taxonomy") or {}
        media_node  = prod_node.get("media") or {}
        reviews_node = (prod_node.get("reviews") or {}).get("ratingsReviews") or {}
        fulfil_node = prod_node.get("fulfillment") or {}

        pricing_key  = next((k for k in prod_node if k.startswith("pricing(")), None)
        pricing_node = prod_node.get(pricing_key) or {} if pricing_key else {}
        map_detail   = pricing_node.get("mapDetail") or {}
        promo_node   = pricing_node.get("promotion") or {}
        bundle_promo = (pricing_node.get("bundlePromotionalAdjustments") or [{}])[0] or {}
        bundle_promo_dates = bundle_promo.get("dates") or {}

        bundle_spec_key = next((k for k in prod_node if k.startswith("bundleSpecificationDetails(")), None)
        bundle_spec = prod_node.get(bundle_spec_key) or {} if bundle_spec_key else {}

        # SEO Description
        seo=prod_node.get('seo',{}).get('seoDescription','')

        # Image sizes / typed images
        apollo_images = media_node.get("images") or []
        image_types = "|".join((im.get("type") or "") for im in apollo_images)
        apollo_videos = media_node.get("video", [])

        # ── VIDEO URLS — join with | ─────────────────────────────────
        videos = " | ".join([
            v.get("url", "") for v in apollo_videos if v.get("url")
        ])
        print(videos)
        # Key features
        key_features = {}
        for kf_item in ((prod_node.get("keyProductFeatures") or {}).get("keyProductFeaturesItems") or []):
            for feat in (kf_item.get("features") or []):
                key_features[feat.get("name")] = feat.get("value")

        # Specifications (grouped)
        specifications = {}
        for grp in (prod_node.get("specificationGroup") or []):
            grp_dict = {}
            for sp in (grp.get("specifications") or []):
                grp_dict[sp.get("specName")] = sp.get("specValue")
            specifications[grp.get("specTitle")] = grp_dict

        qa_key = next((k for k in root_q if k.startswith("questionsAnswers(")), None)
        qa_node = root_q.get(qa_key) or {} if qa_key else {}
        qa_results = [
            {"question": q.get("QuestionSummary"), "user": q.get("UserNickname"),
             "date": q.get("SubmissionTime"), "answers": q.get("TotalAnswerCount")}
            for q in (qa_node.get("Results") or [])
        ]

        # Meta tags
        canonical_link = sel.xpath('//link[@rel="canonical"]/@href').get() or ""

        savings_text = (sel.xpath('//p[@data-testid="product-savings"]/text()').get() or "") + (sel.xpath('//p[@data-testid="product-savings"]/text()[2]').get() or "")
        subtotal_text = sel.xpath('//p[@data-testid="subtotal"]/text()').get() or ""
        retail_text = sel.xpath('//p[@data-testid="retail-price"]/text()').get() or ""

        stock = "InStock" if avail_node.get("buyable") == "true" else "OutOfStock"
        # Store context (from __EXPERIENCE_CONTEXT__ script)
        ctx_txt = sel.xpath('//script[contains(text(),"__EXPERIENCE_CONTEXT__")]/text()').get() or ""
        m_sid = re.search(r'"storeId":\s*"(\d+)",\s*"storeName":\s*"([^"]*)",\s*"storeZip":\s*"(\d+)"', ctx_txt)
        store_id, store_name, store_zip = (m_sid.groups() if m_sid else ("", "", ""))

        try:
            f_opt = (fulfil_node.get("fulfillmentOptions") or [{}])[0]
            f_svc = (f_opt.get("services") or [{}])[0]
            f_loc = (f_svc.get("locations") or [{}])[0]

        except Exception:
            pass
        # ── END EXTRA PDP HEADERS ─────────────────────────────────────


        iso_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(iso_date)



        unique_key = f"{product_url}"
        hashid_prod = hashlib.md5(unique_key.encode("utf-8")).hexdigest()

        item =   {
            "_id":hashid_prod,
            "Product URL": canonical_link,
            "Product Name": product_name,
            "Product ID":product_id,
            "Brand": brand,
            "SKU": sku,
            "Datetime": iso_date,
            "Image URL": result,
            "Description": description1,
            "Category": category,
            "Sale Price": price,
            "Full Price": price,
            "Currency": currency,
            'Breadcrumb':breadcrumb,
            "Rating": ratingValue,
            "ReviewCount":reviewCount,
            'Stock':stock,
            "Product Type": identifiers.get("productType", ""),
            "Model Number": identifiers.get("modelNumber", ""),
            "UPC": identifiers.get("upc", "") or identifiers.get("upcGtin13", ""),
            "Availability Type": avail_node.get("type", ""),
            "Is Discontinued": avail_node.get("discontinued", ""),
            "Is Obsolete": avail_node.get("obsolete", ""),
            "Hide Price": info_node.get("hidePrice", ""),
            "Quantity Limit": info_node.get("quantityLimit", ""),
            "Returnable": info_node.get("returnable", ""),
            "Promo Type": promo_node.get("type", ""),
            "Promo Dollar Off": promo_node.get("dollarOff", "") or bundle_promo.get("dollarOff", ""),
            "Promo Percent Off": promo_node.get("percentageOff", "") or bundle_promo.get("percentageOff", ""),
            "Promo ID": bundle_promo.get("promoId", ""),
            "Promo Start": bundle_promo_dates.get("start", ""),
            "Promo End": bundle_promo_dates.get("end", ""),
            "Savings Center": promo_node.get("savingsCenter", ""),
            "Displayed Retail Price": retail_text,
            "Displayed Savings": savings_text,
            "Displayed Subtotal": subtotal_text,
            "Price Valid Until": offers.get("priceValidUntil", ""),
            "Return Policy": (offers.get("hasMerchantReturnPolicy") or {}).get("returnPolicyCategory", ""),
            "Highlights": details_node.get("highlights") or [],
            "Key Features": key_features,
            "Specifications": specifications,
            'seoDescription':seo,
            # "QA Count": qa_node.get("TotalResults", 0),
            "QA List": qa_results,
            "Videos": videos,
            "Store ID": store_id,
            "Store Name": store_name,
            "Store Zip": store_zip,
            'Page_Save': File_Path,
        }

        try:
            collection_product_details.insert_one(item)
            # ── FIX #5: correct field name 'URL' ─────────────────────
            store_category_data.update_one(
                {'_id': doc['_id']},
                {'$set': {'status': 'Done'}}
            )
            print(f"{Fore.GREEN}INSERTED{Fore.RESET} || {product_name}")

        except Exception as e:
            if 'E11000' in str(e) or 'duplicate key' in str(e).lower():
                store_category_data.update_one(
                    {'_id': doc['_id']},
                    {'$set': {'status': 'Duplicate'}}
                )
                print(f"{Fore.YELLOW}DUPLICATE{Fore.RESET}")
            else:
                print(f"{Fore.RED}Insert error: {e}{Fore.RESET}")

    except Exception as e:
        print(f"{Fore.RED}Parse error: {e} | {product_url}{Fore.RESET}")
        store_category_data.update_one(
            {'_id': doc['_id']},
            {'$set': {'status': 'Issue'}}
        )


# ── RUN ───────────────────────────────────────────────────────────────
with ThreadPoolExecutor(max_workers=1) as executor:
    futures = {executor.submit(scrap_store_data, l): l for l in product_links}
    for future in as_completed(futures):
        try:
            future.result()
        except Exception as e:
            lnk = futures[future]
            print(f"[!] Thread error for {lnk.get('_id')}: {e}")