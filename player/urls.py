#!/usr/bin/env python
# -*- coding: utf-8 -*-
from django.conf.urls import url
from player import views
from playlist import views as playlist_view
from views import PlayerView
from django.contrib.auth.decorators import login_required

urlpatterns = [
    url(r'^$', login_required(PlayerView.as_view()), name='player'),
    url(r'^live/$', views.live),
    url(r'^live/tweet/$', views.post_tweet),
    url(r'^live/out/$', views.out),
    url(r'^mpd_action/(?P<action>\w+)$', views.mpd_action),
    url(r'^mpd_action_play_song/(?P<song_pos>\d+)$', views.mpd_play_song),
    url(r'^mpd_status/$', views.mpd_status),
    url(r'^update_list/$', playlist_view.update_playlist),
    url(r'^reset_list/$', playlist_view.reset_playlist),
    #url(r'^player/get_cover/(?P<episode_id>)$', views.get_cover)),
    url(r'^mpd_rewfor/(?P<percent>\d+)$', views.mpd_rewfor),
]

