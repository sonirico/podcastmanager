# coding: UTF-8

import logging
import os
import urllib2
import feedparser
import pytz

from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from datetime import datetime
from urlgrabber.grabber import URLGrabber
from time import mktime
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist
from playlist.models import Episode, Podcast, PlayListManager
from podcastmanager.settings import DEFAULT_COVER_IMAGE, AUDIOS_URL
from tools.filehandler import make_cover
from tools.normalize import normalize
from playlist.views import update_playlist

logger = logging.getLogger(__name__)


class HeadRequest(urllib2.Request):
    def get_method(self):
        return "HEAD"

episode_template = {
    'title': '',
    'duration': 0,
    'filename': '',
    'cover': DEFAULT_COVER_IMAGE,
    'times_played': 0,

    'uri': '',
    'published': None,
    'downloaded': None,
    'podcast': None,

    # Temporary
    'type': ''
}


class DownloadManager(object):
    def __init__(self):
        self.episode = episode_template
        self.busy = False

    def is_busy(self):
        return bool(self.busy)

    def download(self, from_=0, to=0):
        self.busy = True
        all_active_podcasts = Podcast.objects.filter(active=True)
        if from_ == 0 and to == 0:
            to = all_active_podcasts.count() - 1
            # there are no podcast given a empty list
            if to < 0:
                logger.info('There is no active podcasts in database')
                return
        # if the same podcast is sounding, we must not disrupt its streaming
        c_podcast = current_podcast()  # So thats why the exclude filter from below
        if c_podcast is not None:
            all_active_podcasts = all_active_podcasts.exclude(pk=c_podcast.pk)
        for podcast in all_active_podcasts.order_by('name')[from_:to]:
            logger.info('Searching RSS for "%s"' % podcast.name)
            if podcast.feed is None or len(podcast.feed) < 1:
                logger.info('No rss found. Skipping')
            else:
                episode_item = episode_template.copy()
                episode_item['podcast'] = podcast
                episode_item['downloaded'] = timezone.now()
                episode_item = self.parse_feed(episode_item, podcast.feed)
                if episode_item:  # RSS unable to being parsed
                    download = False
                    try:
                        latest_episode = podcast.episode_set.latest('downloaded')
                        download = latest_episode.is_duplicated(episode_item) is False
                    except ObjectDoesNotExist, e:
                        logger.info('Downloading first episode for %s' % podcast.name )
                        download = True
                    if download:
                        episode_item = download_audio(episode_item)
                        # Will return False if there have been problems. See "download_file" for further details
                        if episode_item:
                            podcast.deactivate_all()
                            create_episode(episode_item)
                    else:
                        logger.info('Same episode already downloaded. Skipping')
                del episode_item  # This line should be reached
        # Finally, playlist should be updated
        update_playlist(None)
        self.busy = False

    def parse_feed(self, episode_item, rss_url):
        """

        :rtype : object
            :param rss_url: URI to feed RSS
            :return: dictionary containing parsed data related with a single episode
        """
        try:
            rss = feedparser.parse(rss_url)
            rss = feedparser.parse(rss.href)  # follow redirect/302
        except Exception, e:
            logger.info('Unable to parse this rss: %s' % rss_url)
            logger.exception(e.message)
            return False
        logger.info('Parsing rss data ... ')
        if len(rss.entries) > 0:
            # Iterates every tag in order to find the <enclosure> one. That means, and audio.
            for last_entry in rss.entries:
                if hasattr(last_entry, 'enclosures') and len(last_entry.enclosures) > 0:
                    # If there are multiple <enclosure> tags, find the one which matches @type attribute
                    found = False
                    for last_enclosure in last_entry.enclosures:
                        if hasattr(last_enclosure, 'type'):
                            episode_item['title'] = last_entry['title']
                            if hasattr(last_entry, 'published_parsed'):
                                episode_item['published'] = format_time(last_entry['published_parsed'])
                            else:
                                episode_item['published'] = None
                            episode_item['uri'] = last_enclosure['href']
                            episode_item['filename'] = os.path.basename(last_enclosure['href'])
                            episode_item['filename'] = create_file_name(episode_item)
                            if episode_item['type'] == "audio/x-m4a":
                                self.episode['type'] = "audio/mp4"
                            else:
                                try:
                                    # Makes a HEAD request to check file type
                                    request = HeadRequest(episode_item['uri'])
                                    response = urllib2.urlopen(request)
                                    response_headers = response.info()
                                    episode_item['type'] = response_headers['content-type']
                                except Exception, e:  # Just another "catch them all" handling exception
                                    logger.info('Error al intentar extraer el audio type. Asumimos mp3')
                                    logger.info(e.message)
                                    episode_item['type'] = 'audio/mpeg'
                            found = True
                            break
                    if found:
                        logger.info('Enclosure with "type" found. Returning item.')
                        return episode_item
                    else:
                        logger.info('No enclosure with "type" found. Next entry.')
                else:
                    logger.info('RSS entry has no enclosures')
        else:
            logger.info('RSS has no entries')
        return False


def format_time(time_struct):
    """
    :param time_struct: Tuple containing when the audio has been published
    :return: an aware-timezone datetime object.
    """
    try:
        return datetime.fromtimestamp(mktime(time_struct), pytz.utc)
    except Exception, e:
        logging.exception(e.message)
        return timezone.now()


def create_episode(episode_item):
    """
    :param episode_item: Dict matching Episode model fields
    :return:
    """
    if 'type' in episode_item:
        del episode_item['type']
    try:
        new_episode = Episode(**episode_item)
        new_episode.save()
        new_episode.set_active()
        # Creates the cover
        make_cover(new_episode)
    except Exception, e:
        logger.exception(e.message)


def current_podcast():
    """
    :return: Currently sounding podcast
    """
    pm = PlayListManager()
    filename = pm.get_current_file()
    if not filename:
        return None
    filename = os.path.join(AUDIOS_URL, filename)
    podcast = None
    try:
        episode = Episode.objects.get(filename=filename)
        podcast = episode.podcast
    except ObjectDoesNotExist, e:
        logger.info(e.message)
    finally:
        pm.close()
        return podcast


def create_file_name(episode_item):
    """
    :param episode_item: dict containing necessary data to compose a rigorous file name
    :return: string. audios/episodetitle-downloadedat.ext
    """
    name = normalize(episode_item.get('title'))
    now = episode_item.get('downloaded').strftime("%Y%m%d-%H%M%S")
    extension = episode_item.get('filename').split('.')[-1]
    return os.path.join(AUDIOS_URL, (name + "-" + now + "." + extension))


def download_audio(episode_item):
    path = episode_item.get('filename')
    if os.path.isfile(path):  # This file already exists, must be overwritten
        os.remove(path)
    logger.info(u'Downloading new episode: "%s" ' % episode_item.get('title'))
    grabber = URLGrabber()
    try:
        grabber.urlgrab(episode_item.get('uri'), filename=path, reget='simple')
        logger.info(u'Done')
    except Exception, e:
        logger.info(u'Unable to download')
        logger.exception(e.message)
        if os.path.isfile(path):  # A 0 byte file has been created. Must be erased.
            os.remove(path)
        return False
    # Set duration field
    audio = None
    try:
        if episode_item.get('type') == 'audio/mpeg':
            audio = MP3(path)
        elif episode_item.get('type') == 'audio/mp4':
            audio = MP4(path)
        if audio is None:
            logger.info(u'Audio type is not either mp3 nor mp4')
            return False
        else:
            episode_item['duration'] = int(audio.info.length)
            # Does the audio exceed its duration?
            max_duration = episode_item.get('podcast').get_max_duration()
            if episode_item.get('duration') >= max_duration:
                os.remove(path)
                logger.info(u'This audio exceed its max duration: %s. Skipping.' % episode_item.get('duration'))
                return False
    except Exception, e:
        logger.info(u'Unable to extract duration')
        logger.exception(e.message)
    return episode_item
