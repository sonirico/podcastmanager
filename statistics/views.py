from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, Http404, HttpResponseNotFound
from django.views.generic import View, ListView
from forms import *
from chartjs.views.lines import BaseLineChartView
from models import ListenersForHistory
from django.db import connection
from datetime import datetime, timedelta
from django.shortcuts import get_object_or_404
from playlist.views import Podcast
import json


class LoginRequiredMixin(object):
    @classmethod
    def as_view(cls, **initkwargs):
        view = super(LoginRequiredMixin, cls).as_view(**initkwargs)
        return login_required(view)


class StatsView(LoginRequiredMixin, ListView):
    template_name = 'statistics/index.html'
    title = 'Stats'
    context_object_name = 'podcast_list'

    def get_queryset(self):
        return []

    def get_context_data(self, **kwargs):
        context = super(StatsView, self).get_context_data(**kwargs)
        context['title'] = self.title
        return context


class InThePastDays(LoginRequiredMixin, View):
    form_class = InThePastDaysForm
    initial = {}

    def post(self, request):
        if request.is_ajax():
            form = self.form_class(request.POST)
            if form.is_valid():
                cd = form.cleaned_data
                days = cd.get('days')
                past_day = datetime.now() - timedelta(days=days)
                listener_count = len(
                    ListenersForHistory.objects.filter(taken_at__gt=past_day).values('listener_hash')
                )
                return HttpResponse(
                    '{"listener_count": %s}' % listener_count,
                    content_type='application/json'
                )
            else:
                return HttpResponseNotFound(form.errors.as_json(), content_type='application/json')
        else:
            raise Http404


class BetweenTwoDates(LoginRequiredMixin, View):
    form_class = BetweenDatesForm
    initial = {}

    def post(self, request):
        if request.is_ajax():
            form = self.form_class(request.POST)
            if form.is_valid():
                c_data = form.cleaned_data
                start_date = c_data.get('start')
                end_date = c_data.get('end')
                listener_count = len(
                    ListenersForHistory.objects.filter(
                        taken_at__range=(start_date, end_date)
                    ).values('listener_hash')
                )
                return HttpResponse(
                    '{"listener_count": %s}' % listener_count,
                    content_type='application/json'
                )
            else:
                return HttpResponseNotFound(form.errors.as_json(), content_type='application/json')
        raise Http404


class UniqueListenersPerEpisode(LoginRequiredMixin, BaseLineChartView):
    def get_labels(self):
        return ['<img src="http://localhost:8000/static/images/covers/2192909-gyakuten_kenji_artwork_01.jpg" ']

    def get_data(self):
        return [[3], ]


class UniqueListenersPerDayJSONView(LoginRequiredMixin, BaseLineChartView):
    days = 30
    query = 'select count(*) ' \
            'from ( ' \
            'select ' \
            'listener_hash, ' \
            'Substr(taken_at, 0, 12) as day ' \
            'from statistics_listenersforhistory ' \
            'group by listener_hash, Substr(taken_at, 0, 12) ' \
            ') AS result ' \
            'GROUP BY result.day ' \
            'ORDER BY result.day DESC ' \
            'LIMIT 0,%s;' % days

    def get_labels(self):  # Thanks to http://stackoverflow.com/questions/8746014/django-group-sales-by-month
        truncate_date = connection.ops.date_trunc_sql('day', 'taken_at')
        qs = ListenersForHistory.objects.extra({'day': truncate_date}).values('day').distinct().order_by('-day')[
             :self.days]
        return [datetime.strptime(record.get('day'), '%Y-%m-%d').strftime('%d/%m') for record in qs]

    def get_data(self):
        cursor = connection.cursor()
        cursor.execute(self.query)
        return [[record[0] for record in cursor.fetchall()], ]


class UniqueListenersPerMonthJSONView(LoginRequiredMixin, BaseLineChartView):
    months = 12
    query = 'select count(*) ' \
            'from ( ' \
            'select ' \
            'listener_hash, ' \
            'Substr(taken_at, 0, 8) as month ' \
            'from statistics_listenersforhistory ' \
            'group by listener_hash, Substr(taken_at, 0, 8) ' \
            ') AS result ' \
            'GROUP BY result.month ' \
            'ORDER BY result.month DESC ' \
            'LIMIT 0, %s ; ' % months

    def get_labels(self):  # Thanks to http://stackoverflow.com/questions/8746014/django-group-sales-by-month
        truncate_date = connection.ops.date_trunc_sql('month', 'taken_at')
        qs = ListenersForHistory.objects.extra(
            {'month': truncate_date}
        ).values('month').distinct().order_by('-month')[:self.months]
        return [datetime.strptime(record.get('month'), '%Y-%m-%d').strftime('%B %y') for record in qs]

    def get_data(self):
        cursor = connection.cursor()
        cursor.execute(self.query)
        return [[record[0] for record in cursor.fetchall()], ]


class PodcastStatsView(LoginRequiredMixin, View):
    form_class = PodcastStatsForm
    initial = {}
    query = 'SELECT ' \
            'pp.id as podcast_id, ' \
            'pp.name as podcast_name, ' \
            'SUM(ph.total_unique_listeners_count) AS unique_listeners, ' \
            'COUNT(ph.total_unique_listeners_count) AS times_played, ' \
            'ROUND(avg(ph.total_unique_listeners_count), 2) AS average ' \
            'FROM playlist_playlisthistory as ph INNER JOIN playlist_episode as pe ON pe.audio_ptr_id = ph.audio_id ' \
            'INNER JOIN playlist_podcast as pp ON pp.id = pe.podcast_id ' \
            ' %s ' \
            'GROUP BY pe.podcast_id ' \
            'ORDER BY ' \
            'unique_listeners DESC, ' \
            'times_played DESC, ' \
            'average DESC, ' \
            'podcast_name,  ' \
            'podcast_id  '

    def get(self, request):
        if request.is_ajax():
            cursor = connection.cursor()
            cursor.execute(self.query % '')
            return HttpResponse(json.dumps(cursor.fetchall()), content_type='application/json')
        else:
            raise Http404

    def post(self, request):
        if request.is_ajax():
            form = self.form_class(request.POST)
            if form.is_valid():
                cd = form.cleaned_data
                podcast_name = cd.get('podcast_name')
                cursor = connection.cursor()
                cursor.execute(self.query % (' WHERE pp.name LIKE "%' + podcast_name + '%" '))
                return HttpResponse(json.dumps(cursor.fetchall()), content_type='application/json')
            else:
                return HttpResponseNotFound(form.errors.as_json(), content_type='application/json')
        else:
            raise Http404


class PodcastImageview(LoginRequiredMixin, View):  # Consider using DetailView class in  the near future
    def get(self, request, *args, **kwargs):
        id = int(kwargs.get('podcast_id'))
        podcast = get_object_or_404(Podcast, pk=id)
        data = {}
        data['id'] = id
        data['image'] = podcast.get_cover()
        return HttpResponse(json.dumps(data), content_type='application/json')
'''
select result.month, count(*)
from (
    select
        listener_hash,
        Substr(taken_at, 0, 8) as month
    from statistics_listenersforhistory
    group by listener_hash, Substr(taken_at, 0, 8)
) AS result
GROUP BY result.month;

One line
select result.month, count(*) from ( select listener_hash, Substr(taken_at, 0, 8) as month from statistics_listenersforhistory group by listener_hash, Substr(taken_at, 0, 8) ) AS result GROUP BY result.month;
select result.days, count(*) from ( select listener_hash, Substr(taken_at, 0, 12) as days from statistics_listenersforhistory group by listener_hash, Substr(taken_at, 0, 12) ) AS result GROUP BY result.days;

-- Listeners per podcast -- @deprecated

SELECT
    pp.name AS podcast_name,
    SUM(ll.total) AS total_listeners,
    count(ll.total) AS total_listeners_count
FROM
    (
        SELECT
            pe.podcast_id AS 'podcast_id',
            count(*) AS 'total'
        FROM statistics_listenersforhistory AS sl INNER JOIN playlist_playlisthistory AS ph
            ON sl.entry_history_id = ph.id INNER JOIN playlist_episode AS pe ON pe.audio_ptr_id = ph.audio_id
        GROUP BY
            ph.audio_id
        ORDER BY
            count(*) DESC
    ) AS ll INNER JOIN playlist_podcast AS pp ON ll.podcast_id = pp.id
GROUP BY
    pp.id,
    pp.name
ORDER BY
    total_listeners DESC
;



SELECT
    pp.name,
    pp.active_episode_id,
    count(ph.total_unique_listeners_count) as "times_played",
    sum(ph.total_unique_listeners_count) as "unique_listeners",
    avg(ph.total_unique_listeners_count) as "average"
FROM playlist_playlisthistory as ph INNER JOIN playlist_episode as pe ON pe.audio_ptr_id = ph.audio_id
     INNER JOIN playlist_podcast as pp ON pp.id = pe.podcast_id
GROUP BY pe.podcast_id
ORDER BY
    unique_listeners DESC,
    times_played DESC,
    average DESC
;


-- Listeners between 2 dates

SELECT COUNT(*)
FROM
(
    SELECT *
    FROM statistics_listenersforhistory as sl
    WHERE taken_at >= '2015-11-01 00:00:00' and taken_at <= '2015-11-08 00:00:00'
    GROUP BY listener_hash
);




'''