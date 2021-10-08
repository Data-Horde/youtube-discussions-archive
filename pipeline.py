import seesaw
from seesaw.tracker import (
    GetItemFromTracker,
    PrepareStatsForTracker,
    UploadWithTracker,
    SendDoneToTracker
)
from seesaw.task import SimpleTask, LimitConcurrent
from seesaw.pipeline import Pipeline
from seesaw.project import Project
from seesaw.config import NumberConfigValue, realize
from seesaw.item import ItemInterpolation, ItemValue
from distutils.version import StrictVersion
import socket
import os
import shutil
import hashlib
import time
import discussions
import sys

if StrictVersion(seesaw.__version__) < StrictVersion('0.8.5'):
    raise Exception('This pipeline needs seesaw version 0.8.5 or higher.')

VERSION = '20211008.02'
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0'
TRACKER_ID = 'youtube-discussions'
TRACKER_HOST = 'localhost'
MULTI_ITEM_SIZE = 1  # TODO: what is this?


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
    def __init__(self, json_prefix):
        SimpleTask.__init__(self, 'PrepareDirectories')
        self.json_prefix = json_prefix

    def process(self, item):
        channel_id = item['item_name']
        dirname = '/'.join((item['data_dir'], channel_id))

        if os.path.isdir(dirname):
            shutil.rmtree(dirname)
        os.makedirs(dirname)
        item['json_file_base'] = '-'.join([
            self.json_prefix,
            channel_id,
            time.strftime('%Y%m%d-%H%M%S')
        ])
        item['item_dir'] = dirname


class MoveFiles(SimpleTask):
    def __init__(self):
        SimpleTask.__init__(self, 'MoveFiles')

    def process(self, item):
        os.rename('%(item_dir)s/%(json_file_base)s.json' % item,
              '%(data_dir)s/%(json_file_base)s.json' % item)
        shutil.rmtree('%(item_dir)s' % item)


class DiscussionsDownload(SimpleTask):
    def __init__(self):
        SimpleTask.__init__(self, 'DiscussionsDownload')

    def process(self, item):
        result, _ = discussions.main(item['item_name'], item['item_dir'])
        if not result:
            raise Exception('Unknown Error')


def get_hash(filename):
    with open(filename, 'rb') as in_file:
        return hashlib.sha1(in_file.read()).hexdigest()


CWD = os.getcwd()
PIPELINE_SHA1 = get_hash(os.path.join(CWD, 'pipeline.py'))
DISCUSSIONS_SHA1 = get_hash(os.path.join(CWD, 'discussions.py'))


def stats_id_function(item):
    return {
        'pipeline_hash': PIPELINE_SHA1,
        'discussions_hash': DISCUSSIONS_SHA1,
        'python_version': sys.version,
    }


pipeline = Pipeline(
    CheckIP(),
    GetItemFromTracker('http://{}/{}/multi={}/'
                       .format(TRACKER_HOST, TRACKER_ID, MULTI_ITEM_SIZE),
                       downloader, VERSION),
    PrepareDirectories(json_prefix=TRACKER_ID),
    DiscussionsDownload(),
    PrepareStatsForTracker(
        defaults={'downloader': downloader, 'version': VERSION},
        file_groups={
            'data': [
                ItemInterpolation('%(item_dir)s/%(json_file_base)s.json')
            ]
        },
        id_function=stats_id_function,
    ),
    MoveFiles(),
    LimitConcurrent(NumberConfigValue(min=1, max=4, default="1",
                                      name="shared:rsync_threads", title="Rsync threads",
                                      description="The maximum number of concurrent uploads."),
                    UploadWithTracker(
                        "http://%s/%s" % (TRACKER_HOST, TRACKER_ID),
                        downloader=downloader,
                        version=VERSION,
                        files=[
                            ItemInterpolation("%(data_dir)s/%(json_file_base)s.json")
                        ],
                        rsync_target_source_path=ItemInterpolation("%(data_dir)s/"),
                        rsync_extra_args=[
                            "--recursive",
                            "--partial",
                            "--partial-dir", ".rsync-tmp"
                        ]
                    ),
                    ),
    SendDoneToTracker(
        tracker_url="http://%s/%s" % (TRACKER_HOST, TRACKER_ID),
        stats=ItemValue("stats")
    )
)