import seesaw
from seesaw.tracker import GetItemFromTracker, PrepareStatsForTracker, \
    UploadWithTracker, SendDoneToTracker
from seesaw.task import SimpleTask, LimitConcurrent
from seesaw.pipeline import Pipeline
from seesaw.project import Project
import socket
import os
import shutil
import hashlib
import time
import discussions

VERSION = '20211008.01'
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0'
TRACKER_ID = 'youtube-discussions'
TRACKER_HOST = 'localhost'
MULTI_ITEM_SIZE = 1  # TODO


project = Project(
  title=TRACKER_ID,
  project_html="""
    <img class="project-logo" alt="Project logo" src="http://archive.org/images/glogo.png" height="50px" />
    <h2>YouTube Discussions <span class="links"><a href="https://www.youtube.com/">Website</a> &middot; <a href="http://tracker.archiveteam.org/youtube-discussions/">Leaderboard</a></span></h2>
        <p>Archiving everything from YouTube Discussions.</p>
  """,
)


class CheckIP(SimpleTask):
    def __init__(self):
        SimpleTask.__init__(self, 'CheckIP')
        self._counter = 0

    def process(self, item):
        # NEW for 2014! Check if we are behind firewall/proxy

        if self._counter <= 0:
            item.log_output('Checking IP address.')
            ip_set = set()

            ip_set.add(socket.gethostbyname('twitter.com'))
            ip_set.add(socket.gethostbyname('facebook.com'))
            ip_set.add(socket.gethostbyname('youtube.com'))
            ip_set.add(socket.gethostbyname('microsoft.com'))
            ip_set.add(socket.gethostbyname('icanhas.cheezburger.com'))
            ip_set.add(socket.gethostbyname('archiveteam.org'))

            if len(ip_set) != 6:
                item.log_output('Got IP addresses: {0}'.format(ip_set))
                item.log_output(
                    'Are you behind a firewall/proxy? That is a big no-no!')
                raise Exception(
                    'Are you behind a firewall/proxy? That is a big no-no!')

        # Check only occasionally
        if self._counter <= 0:
            self._counter = 10
        else:
            self._counter -= 1


class PrepareDirectories(SimpleTask):
    def __init__(self):
        SimpleTask.__init__(self, 'PrepareDirectories')

    def process(self, item):
        item_name = item['item_name']
        item_name_hash = hashlib.sha1(item_name.encode('utf8')).hexdigest()
        escaped_item_name = item_name_hash
        dirname = '/'.join((item['data_dir'], escaped_item_name))

        if os.path.isdir(dirname):
            shutil.rmtree(dirname)
        os.makedirs(dirname)

        item['item_dir'] = dirname


class DiscussionsDownload(SimpleTask):
    def __init__(self):
        SimpleTask.__init__(self, 'DiscussionsDownload')

    def process(self, item):
        result, _ = discussions.main(item['item_name'], item['item_dir'])
        if not result:
            raise Exception('Unknown Error')

pipeline = Pipeline(
    CheckIP(),
    # Get item from tracker
    PrepareDirectories(),
    DiscussionsDownload(),
    UploadWithTracker(),
    SendDoneToTracker()
)