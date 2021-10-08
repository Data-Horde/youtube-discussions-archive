from base64 import b64decode, b64encode

import requests
from json import loads, dumps
from time import time, sleep
from sys import argv
from pathlib import Path
from datetime import datetime


class DownloadException(Exception):
    pass


class YouTubeError(Exception):
    pass

# todo: check for accuracy, add/test ratelimit checks if needed, additional language locking (headers)/ gl US


def approxnumtoint(num: str):
    if num[-1] == "K":
        print(num)
        print(int(float(num[:-1].replace(",", "")) * 1000))
        return int(float(num[:-1].replace(",", "")) * 1000)
    if num[-1] == "M":
        print(num)
        print(int(float(num[:-1].replace(",", "")) * 1000000))
        return int(float(num[:-1].replace(",", "")) * 1000000)
    return int(num.replace(",", ""))


def joinruns(runs):
    mys = ""
    for run in runs:
        mys += run["text"]
    return mys


mysession = requests.session()
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0'
INNERTUBE_API_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
INNERTUBE_CLIENT_VERSION = "2.20210924.00.00"


# function from coletdjnz https://github.com/coletdjnz/yt-dlp-dev/blob/3ed23d92b524811d9afa3d95358687b083326e58/yt_dlp/extractor/youtube.py#L4392-L4406
def _generate_discussion_continuation(channel_id):
    """
    Generates initial discussion section continuation token from given video id
    """
    ch_id = bytes(channel_id.encode('utf-8'))

    def _generate_secondary_token():
        first = b64decode('EgpkaXNjdXNzaW9uqgM2IiASGA==')
        second = b64decode('KAEwAXgCOAFCEGNvbW1lbnRzLXNlY3Rpb24=')
        return b64encode(first + ch_id + second)

    first = b64decode('4qmFsgJ4Ehg=')
    second = b64decode('Glw=')
    return b64encode(first + ch_id + second + _generate_secondary_token()).decode('utf-8')


def docontinuation(continuation, endpoint="browse"):
    tries = 0
    while True:
        last_error = None
        try:
            r = mysession.post(
                f"https://www.youtube.com/youtubei/v1/{endpoint}?key={INNERTUBE_API_KEY}",
                json={"context": {
                    "client": {"hl": "en", "clientName": "WEB", "clientVersion": INNERTUBE_CLIENT_VERSION, "timeZone": "UTC"},
                    "user": {"lockedSafetyMode": False}}, "continuation": continuation},
                headers={
                    "x-youtube-client-name": "1",
                    "x-youtube-client-version": INNERTUBE_API_KEY,
                    "User-Agent": USER_AGENT},
                allow_redirects=False)

            myrjson = r.json()
            myrjsonkeys = myrjson.keys()
            if "error" in myrjsonkeys:
                if "message" in myrjson["error"].keys():
                    if (myrjson["error"][
                            "message"] == "Requested entity was not found." and r.status_code == 404) or (
                            myrjson["error"][
                                "message"] == "The caller does not have permission" and r.status_code == 403):
                        if endpoint == "comment/get_comment_replies":
                            print("INFO: Treating as end of replies.")
                            return [{"appendContinuationItemsAction": {"continuationItems": [{}]}}]
                        elif endpoint == "browse":
                            print("INFO: Treating as end of comments.")
                            return [{"reloadContinuationItemsCommand": {"continuationItems": [{}]}}]
                    raise YouTubeError(f'Youtube said: {myrjson["error"]["message"]}')
                else:
                    raise YouTubeError(f"Error from YouTube, no error message provided")
            elif "contents" in myrjsonkeys:
                raise DownloadException(
                    "Contents key detected in response, which indicates that we have not received discussion tab data. Retrieving discussion tab data for this channel is likely not possible. This error typically occurs on automatically-generated YouTube channels. Aborting.")
            elif "continuationContents" in myrjsonkeys:
                raise DownloadException(
                    "continuationContents key detected in response, which indicates that we have not received discussion tab data. Retrieving discussion tab data for this channel is likely not possible. This error typically occurs on automatically-generated YouTube channels. Aborting.")
            elif "onResponseReceivedEndpoints" in myrjsonkeys and r.status_code == 200:
                return myrjson["onResponseReceivedEndpoints"]
            elif r.status_code == 404:
                raise DownloadException("404 status code retrieved, aborting.")
            elif r.status_code != 200:
                raise YouTubeError(f"Non-200 status code received ({r.status_code})")
            elif "onResponseReceivedEndpoints" not in myrjsonkeys:
                raise YouTubeError(f"Invalid Response: onResponseReceivedEndpoints missing from response.")
        except YouTubeError as e:
            print("WARNING: Youtube error: " + str(e))
            last_error = e
        except (IndexError, KeyError, AttributeError, TypeError) as e:
            print("WARNING: Invalid Response: Response is not JSON-formatted")
            last_error = e
        except requests.exceptions.RequestException as e:
            print("WARNING: Requests error: " + str(e))
            last_error = e
        if tries > 5:
            if last_error:
                raise last_error
            raise DownloadException("Retries exhausted, unknown error, aborting")
        tries += 1
        timetosleep = 10 * (2 ** (
                    tries - 2))  # 5, 10, 20, 40, 80, 160, 320, 640, 1280, 2560 https://findwork.dev/blog/advanced-usage-python-requests-timeouts-retries-hooks/
        print("INFO:", datetime.now(), ": Sleeping", timetosleep, "seconds")
        sleep(timetosleep)


def extractcomment(comment, is_reply=False):
    comment_channel_ids = set()
    commentroot = {}
    try:
        if not is_reply:
            itemint = comment["commentThreadRenderer"]["comment"]["commentRenderer"]
        else:
            itemint = comment["commentRenderer"]
    except:
        print(comment)

    if "simpleText" in itemint["authorText"].keys():
        commentroot["authorText"] = itemint["authorText"]["simpleText"]
    else:
        print("WARNING: Author name not provided, setting to blank.")
        commentroot["authorText"] = ""
    commentroot["authorThumbnail"] = itemint["authorThumbnail"]["thumbnails"][0][
        "url"]  # joinurls(itemint["authorThumbnail"]["thumbnails"])
    if "browseId" in itemint["authorEndpoint"]["browseEndpoint"].keys():
        commentroot["authorEndpoint"] = itemint["authorEndpoint"]["browseEndpoint"]["browseId"]
        comment_channel_ids.add(commentroot["authorEndpoint"])
    else:
        print("WARNING: Author UCID not provided, setting to blank.")
        commentroot["authorEndpoint"] = ""
    if "runs" in itemint["contentText"].keys():
        commentroot["contentText"] = joinruns(itemint["contentText"]["runs"])
    else:
        print("WARNING: Missing contentText runs, setting to blank.")
        commentroot["contentText"] = ""
    commentroot["publishedTimeText"] = joinruns(itemint["publishedTimeText"]["runs"]).removesuffix(" (edited)")
    commentroot["creatorHeart"] = "creatorHeart" in itemint["actionButtons"][
        "commentActionButtonsRenderer"].keys()  # accurate enough?
    commentroot["commentId"] = itemint["commentId"]
    commentroot["edited"] = " (edited)" in joinruns(
        itemint["publishedTimeText"]["runs"])  # hopefully this works for all languages
    if "voteCount" in itemint.keys():
        commentroot["voteCount"] = approxnumtoint(itemint["voteCount"]["simpleText"])
    else:
        commentroot["voteCount"] = 0

    addcnt = 1
    if not is_reply:
        commentroot["replies"] = []
        if "replies" in comment["commentThreadRenderer"].keys():
            creplycntruns = \
            comment["commentThreadRenderer"]["replies"]["commentRepliesRenderer"]["viewReplies"]["buttonRenderer"][
                "text"]["runs"]
            if len(creplycntruns) == 2 or len(creplycntruns) == 1:
                commentroot["expected_replies"] = 1
            else:
                commentroot["expected_replies"] = int(creplycntruns[1]["text"])
            myjrind = docontinuation(
                comment["commentThreadRenderer"]["replies"]["commentRepliesRenderer"]["contents"][0][
                    "continuationItemRenderer"]["continuationEndpoint"]["continuationCommand"]["token"],
                "comment/get_comment_replies")
            if "continuationItems" in myjrind[0]["appendContinuationItemsAction"].keys():
                myjr = myjrind[0]["appendContinuationItemsAction"]["continuationItems"]
            else:
                print("WARNING: Missing continuationItems key, treating as end of comments.")
                return commentroot, addcnt, comment_channel_ids

            while True:
                for itemr in myjr:
                    if "commentRenderer" in itemr.keys():
                        reply, _, reply_channel_ids = extractcomment(itemr, True)
                        commentroot["replies"].append(reply)
                        comment_channel_ids.update(reply_channel_ids)
                        addcnt += 1

                if "continuationItemRenderer" in myjr[-1].keys():
                    myjrin = docontinuation(myjr[-1]["continuationItemRenderer"]["button"]["buttonRenderer"]["command"][
                                                "continuationCommand"]["token"], "comment/get_comment_replies")

                    if "continuationItems" in myjrin[0]["appendContinuationItemsAction"].keys():
                        myjr = myjrin[0]["appendContinuationItemsAction"]["continuationItems"]
                    else:
                        print("WARNING: Missing continuationItems key, treating as end of replies.")
                        break
                else:
                    break
        else:
            commentroot["expected_replies"] = 0

        if len(commentroot["replies"]) != commentroot["expected_replies"]:
            print("WARNING: Number of retrieved replies does not equal number of expected replies.")

    return commentroot, addcnt, comment_channel_ids


def main(channel_id, download_dir, json_file_base=None):
    timestamp = time()
    cont = docontinuation(_generate_discussion_continuation(channel_id))

    if "continuationItems" in cont[1]["reloadContinuationItemsCommand"].keys():
        myj = cont[1]["reloadContinuationItemsCommand"]["continuationItems"]
    else:
        myj = [{}]
        print("WARNING: Missing continuationItems key, treating as end of comments.")

    commentscount = int(
        cont[0]["reloadContinuationItemsCommand"]["continuationItems"][0]["commentsHeaderRenderer"]["countText"][
            "runs"][0]["text"].replace(",", ""))

    print(commentscount)

    comments = []
    commentcnt = 0
    channel_ids = set()
    while True:
        for item in myj:
            if "commentThreadRenderer" in item.keys():
                commentfinal, addcnt, comment_channel_ids = extractcomment(item)
                comments.append(commentfinal)
                channel_ids.update(comment_channel_ids)
                commentcnt += addcnt

        if "continuationItemRenderer" in myj[-1].keys():
            myjino = docontinuation(
                myj[-1]["continuationItemRenderer"]["continuationEndpoint"]["continuationCommand"]["token"])

            if "continuationItems" in myjino[0]["appendContinuationItemsAction"].keys():
                myj = myjino[0]["appendContinuationItemsAction"]["continuationItems"]
            else:
                print("WARNING: Missing continuationItems key, treating as end of comments.")
                break

            print(str(commentcnt) + "/" + str(commentscount) + ", " + str(100 * (commentcnt / commentscount)) + "%")
        else:
            try:
                print(str(commentcnt) + "/" + str(commentscount) + ", " + str(100 * (commentcnt / commentscount)) + "%")
            except ZeroDivisionError:
                print("0/0, 100.0%")
            break

    if commentcnt != commentscount:
        print(
            "INFO: Number of retrieved comments does not equal expected count. This is a common occurence due to inaccuracies in YouTube's counting system and can safely be ignored in most cases.")

    # minify JSON https://stackoverflow.com/a/33233406
    base = json_file_base or channel_id
    open(Path(download_dir, base + ".json"), "w").write(
        dumps({"UCID": channel_id, "expected_count": commentscount, "timestamp": timestamp, "comments": comments},
              separators=(',', ':')))

    print("Success!")
    return True, channel_ids


if len(argv) == 2:
    res = main(argv[1], '.')
    print(res)
else:
    print("""YouTube Discussion Tab Downloader by tech234a
    ***THIS SCRIPT IS EXPERIMENTAL***
    Rate-limit checks are untested. Additionally, further accuracy checks should be performed.
    USAGE: python3 discussions.py [Channel UCID]
    REQUIREMENTS: requests (pip install requests)
    NOTES: Only provide 1 channel UCID at a time. Usernames/channel URLs are not supported.""")
