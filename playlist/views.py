# -*- coding: utf-8 -*-

import logging
import os

import opml
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth.models import Group, User
from django.template import Template, Context

from playlist.models import Promotion, PromoCategory, Podcast, PlayListManager
from podcastmanager.settings import TWITTER_OAUTH, TWEET_TEMPLATE_PATH, COVERS_URL, DEFAULT_COVER_IMAGE, BASE_DIR
from tools.normalize import normalize
from twitter import *

logger = logging.getLogger(__name__)


def create_podcaster(podcast_nombre=''):
    """
        Crea un usuario por cada podcast en funcion del nombre de éste y los añade al grupo "podcasters"
        Si exististieran previamente usuarios en este grupo, los borra
        :param podcast_nombre:
        :return:
    """
    logger.info('Adding new podcaster ...')
    try:
        pod_group = Group.objects.get(name='podcasters')
        username = unicode(podcast_nombre)
        redone_username = normalize(username)
        if len(redone_username) > 4:
            username = redone_username[:15]
        try:
            new_user = User(username=username, is_staff=False, is_active=True)
            new_user.set_password('cambiaesto')
            new_user.save()
            pod_group.user_set.add(new_user)
            logger.info('Added. %s.' % username)
        except IntegrityError:
            logger.info('User "%s" already stored. Skipping.' % username)
    except ObjectDoesNotExist:
        logger.info('Unable to create new podcaster. Podcasters group does not exist.')


def import_from_opml(opml_file='podcasts.opml'):
    global logger
    if os.path.isfile(opml_file):
        outline = opml.parse(opml_file)
        # default_category = Categoria.objects.get(pk='2')
        logger.info('Beginning podcast import operation.')
        for podcast in outline:  # Each "outline" tag represents one podcast
            podcast_name = podcast.text  # Podcast name
            rss_url = podcast.xmlUrl  # Podcast rss
            web_url = podcast.htmlUrl  # Podcast web
            logger.info('Importing %s ...' % podcast_name)
            # Si vamos a importar un nuevo fichero opml, puede que se repitan podcast. Considerando que este nuevo
            # opml será más reciente, actualizamos tanto la web como el nombre del podcast.
            # La premisa principal, es que un RSS nunca cambia de url, ya que es el campo de comparación. En otras palabras
            # se toma como clave primaria la url del rss feed (Algo que no me gusta).
            old_podcasts = Podcast.objects.filter(feed=rss_url)
            if old_podcasts.count() == 1:
                # Podcast existente. Actualizamos datos.
                logger.info('Podcast already stored. Updating it ...')
                old_podcast = old_podcasts[0]
                old_podcast.name = podcast.text
                old_podcast.website = podcast.htmlUrl
                old_podcast.save()
            elif old_podcasts.count() > 1:  # Mas de un podcast con el mismo feed. Nunca debería entrar aquí.
                logger.info('Too many podcast for one feed.')
            else:
                # No hay podcasts coincidentes. Lo creamos.
                logger.info('Creating new podcast ...')
                new_podcast = Podcast(
                    name=podcast_name,
                    feed=rss_url,
                    website=web_url
                )
                new_podcast.save()
            create_podcaster(podcast_name)
            logger.info('Done.')
        logger.info('Importing podcast tasks : Done')
        return HttpResponse('Done all imports.')
    else:
        return HttpResponse('Unable to find the submitted opml file: ' + opml_file)

# End import_from_opml

# Crea una lista de cero. Borra las canciones que hubiera antes.
# En otras palabras, se reinicia la reproduccion


def reset_playlist(request=None):
    global logger
    logger.info('Reseting playlist.')
    # Objeto con el que manejaremos la playlist
    plm = PlayListManager()
    plm.reset_playlist()
    # Seleccionamos los podcasts activos con un audio activo
    all_active_podcasts = Podcast.objects \
        .filter(activo=True) \
        .exclude(active_episode=0) \
        .order_by('nombre')
    if not all_active_podcasts.exists():
        logger.info('No active podcasts. Aborting')
        return HttpResponseRedirect('/admin/player/')
    for podcast in all_active_podcasts:
        # ¿Que pasa si el podcast no tiene ningun audio anterior? En teoria no debería suceder porque
        # el .exclude() criba los que no tengan audio. En este punto debería tener al menos 1.
        try:
            episode = podcast.active_episode  # Episode.objects.get(pk=podcast.active_episode.id)
            if episode is not None:
                # ¿El episodio ha llegado al limite de reproducciones ?
                if episode.times_played < podcast.get_max_repro():
                    # Entonces lo incluimos en la lista
                    plm.add_song(episode.get_file_name())
                    logger.info('Added to playlist: %s' % episode.get_file_name())
        except Exception, e:
            pass

    logger.info('Reset playlist: Done.')
    plm.play()
    plm.close()
    return HttpResponseRedirect('/admin/player/')

# End reset_playlist


def update_playlist(request):
    pm = PlayListManager()
    last_sounding_song = pm.get_current_song()  # El audio que estaba sonando antes
    last_time = pm.get_current_song_time()  # El segundo donde current_song estaba
    # Remove previous playlist
    pm.reset_playlist()
    # Get episodes and promos
    all_active_podcasts = Podcast.objects.filter(active=True).exclude(active_episode=None).order_by('name')
    episodes = [podcast.active_episode for podcast in all_active_podcasts if podcast.active_episode.is_active()]
    promos = get_promo_list_by_time_interval()
    counters = {}  # Set counters for every kind of promo
    added = {}  # Stores boolean values which represent if an audio has been added to playlist.
    for interval in promos:
        counters[interval] = 0
        added[interval] = False
    duration = 0
    if len(episodes) > 0:  # The code will normally enter here
        for episode in episodes:
            print episode.duration, episode
            # Add episode
            pm.add_song(episode.get_filename())
            if episode.duration is not None:
                duration += episode.duration
            print 'Acummulate duration: ', duration
            # Add promotions
            for interval in promos:
                promo_list = promos[interval]
                if counters[interval] < len(promo_list):
                    promo = promo_list[counters[interval]]
                    print promo.duration, promo
                    if duration >= interval:
                        print 'Added: ', promo
                        pm.add_song(promo.get_filename())
                        counters[interval] += 1  # Move to the next promo
                        added[interval] = True
            if all_set(added):
                for interval in added:
                    added[interval] = False  # Reset to false and restart again
                duration = 0
            print added                
    else:  # No episodes in playlist. Should we add promos alone?
        for interval in promos:
            promo_list = promos[interval]
            for promo in promo_list:
                pm.add_song(promo.get_filename())
    # Seek the current audio position if possible
    new_playlist = pm.get_playlist_info()
    if last_sounding_song is not None:
        for audio in new_playlist:
            if audio.get('file') == last_sounding_song.get('file'):
                pm.move(audio.get('id'))
                pm.seek(audio.get('id'), last_time)
                break
        else:
            logger.info("The audio which was sounding is not here anymore.")
    pm.play()
    pm.close()
    logger.info('Playlist updated successfully ')
    return HttpResponseRedirect('/player/')



def tweet(audio):
    if audio is None:
        return False
    try:
        bird = Twitter(auth=OAuth(
            TWITTER_OAUTH['ACCESS_TOKEN'],
            TWITTER_OAUTH['ACCESS_TOKEN_SECRET'],
            TWITTER_OAUTH['CONSUMER_KEY'],
            TWITTER_OAUTH['CONSUMER_KEY_SECRET']
        ))
        if not os.path.isfile(TWEET_TEMPLATE_PATH):
            return False
        with open(TWEET_TEMPLATE_PATH) as template_file:
            template_content = template_file.read()
            template_file.close()
        template = Template(template_content)
        new_status = template.render(Context({'audio': audio}))[:140]
        try:
            if audio.get_cover() == DEFAULT_COVER_IMAGE:
                raise ValueError('Cover image is the default one.')
            with open(os.path.join(BASE_DIR, COVERS_URL, audio.get_cover()), 'rb') as cover_file:
                image_data = cover_file.read()
                # Upload cover image
                t_up = Twitter(domain='upload.twitter.com', auth=OAuth(
                    TWITTER_OAUTH['ACCESS_TOKEN'],
                    TWITTER_OAUTH['ACCESS_TOKEN_SECRET'],
                    TWITTER_OAUTH['CONSUMER_KEY'],
                    TWITTER_OAUTH['CONSUMER_KEY_SECRET']
                ))
                id_img = t_up.media.upload(media=image_data)['media_id_string']
                bird.statuses.update(status=new_status, media_ids=','.join([id_img, ]))
                logger.info('Tweet sent with media: %s' % new_status)
                cover_file.close()
        except Exception, e:
            logger.exception(e.message)
            bird.statuses.update(status=new_status)
            logger.info('Tweet sent without media: %s' % new_status)
        return True
    except Exception, e:
        logger.info('Failed to send tweet: "%s"' % tweet)
        logger.exception(e.message)
        return False


def get_promo_list_by_time_interval():
    """
    :return: Promotions grouped by their category. Key => time_interval, Value => Promotion list
    """
    promos = {}
    for category in PromoCategory.objects.values('id', 'time_interval').order_by(
            'time_interval'):  # group by time_interval
        category_obj = PromoCategory.objects.get(pk=category['id'])		
        if category_obj.promotion_set.all().count() > 0:				
            promos[category['time_interval']] = Promotion.objects \
                .filter(category__id=category['id']) \
                .order_by('title')
    return promos


def all_set(added):
    for interval in added:
        if not added[interval]:
            return False
    return True
